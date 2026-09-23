"""Code Review Collaboration Profile v1 —— Profile 专用持久化。

依据：Profile §15.4（词表与持久化映射）、§15.6（external ID 与 epoch 围栏）、
§15.7（角色授权）、binding RC2 §4/§5。

设计约束：

- 仅新增表与新增列，不改既有非 Profile 路径的语义；
- 唯一关联键包含 ``coordinator_id``，**不按裸 run_id 全局关联**（§15.6）；
- 幂等以"业务键 + 投影/摘要"判定：相同返回原记录，不同返回冲突（§15.8）；
- 角色授权在**无任何授权记录**时降级为"部署约定"（unenforced），
  由调用方决定是否允许写入，且不得声称强制隔离（§15.7）。
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from agent_net.code_review.errors import ProfileError
from agent_net.code_review.projection import message_projection, projection_digest
from agent_net.code_review.validation import PROFILE_VERSION as PROFILE_MESSAGE_PROFILE_VERSION

from .context import connect
from .objective_store import get_objective_execution
from .session_store import get_coordination_session

# ── Profile 会话 ──────────────────────────────────────────────────────

_SESSION_SELECT = """
    SELECT profile_session_id, coordination_session_id, coordinator_id, external_run_id,
           review_revision, review_policy_sha256, activation_revision, target_revision,
           target_json, adapter_version, role_enforcement, created_at, updated_at
    FROM code_review_profile_sessions
"""


def _session_row(row: tuple) -> Dict[str, Any]:
    return {
        "profile_session_id": row[0],
        "coordination_session_id": row[1],
        "coordinator_id": row[2],
        "external_run_id": row[3],
        "review_revision": row[4],
        "review_policy_sha256": row[5],
        "activation_revision": row[6],
        "target_revision": row[7],
        "target": json.loads(row[8]) if row[8] else {},
        "adapter_version": row[9] or "",
        "role_enforcement": row[10] or "unenforced",
        "created_at": row[11],
        "updated_at": row[12],
    }


async def create_profile_session(
    profile_session_id: str,
    *,
    coordination_session_id: str,
    coordinator_id: str,
    external_run_id: str,
    review_revision: int = 1,
    review_policy_sha256: str = "",
    activation_revision: Optional[int] = None,
    target_revision: Optional[int] = None,
    target: Optional[Dict[str, Any]] = None,
    adapter_version: str = "",
    role_enforcement: str = "unenforced",
) -> Dict[str, Any]:
    """登记一个 Profile 会话。

    ``(coordinator_id, external_run_id)`` 唯一；重复登记时若既有记录一致则返回原记录，
    不一致抛 ``idempotency_conflict``（§15.6：不同 Coordinator 的同名 ID 不得碰撞）。
    """
    existing = await get_profile_session(
        coordinator_id=coordinator_id, external_run_id=external_run_id
    )
    if existing:
        same = (
            existing["coordination_session_id"] == coordination_session_id
            and existing["review_revision"] == review_revision
            and existing["review_policy_sha256"] == review_policy_sha256
        )
        if same:
            return existing
        raise ProfileError(
            "idempotency_conflict",
            "同一 (coordinator_id, external_run_id) 已登记且内容不同",
            scope="profile_session",
        )

    now = time.time()
    async with connect() as db:
        await db.execute(
            """INSERT INTO code_review_profile_sessions
               (profile_session_id, coordination_session_id, coordinator_id, external_run_id,
                review_revision, review_policy_sha256, activation_revision, target_revision,
                target_json, adapter_version, role_enforcement, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile_session_id,
                coordination_session_id,
                coordinator_id,
                external_run_id,
                review_revision,
                review_policy_sha256,
                activation_revision,
                target_revision,
                json.dumps(target or {}),
                adapter_version,
                role_enforcement,
                now,
                now,
            ),
        )
        await db.commit()
    session = await get_profile_session(profile_session_id=profile_session_id)
    assert session is not None
    return session


async def get_profile_session(
    profile_session_id: Optional[str] = None,
    *,
    coordinator_id: Optional[str] = None,
    external_run_id: Optional[str] = None,
    coordination_session_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """按 profile_session_id 或 (coordinator_id, external_run_id) 或本地会话 ID 查询。"""
    conditions: List[str] = []
    params: List[Any] = []
    if profile_session_id:
        conditions.append("profile_session_id = ?")
        params.append(profile_session_id)
    if coordinator_id is not None:
        conditions.append("coordinator_id = ?")
        params.append(coordinator_id)
    if external_run_id is not None:
        conditions.append("external_run_id = ?")
        params.append(external_run_id)
    if coordination_session_id is not None:
        conditions.append("coordination_session_id = ?")
        params.append(coordination_session_id)
    if not conditions:
        raise ValueError("必须给出至少一个查询条件")
    async with connect() as db:
        async with db.execute(
            f"{_SESSION_SELECT} WHERE {' AND '.join(conditions)}", tuple(params)
        ) as cur:
            row = await cur.fetchone()
    return _session_row(row) if row else None


async def update_profile_session(profile_session_id: str, **fields: Any) -> bool:
    """更新 activation/target/adapter 等可变字段。"""
    allowed = {
        "activation_revision",
        "target_revision",
        "target_json",
        "adapter_version",
        "role_enforcement",
        "review_revision",
        "review_policy_sha256",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = time.time()
    assignments = ", ".join(f"{k}=?" for k in updates)
    async with connect() as db:
        cur = await db.execute(
            f"UPDATE code_review_profile_sessions SET {assignments} WHERE profile_session_id=?",
            (*updates.values(), profile_session_id),
        )
        await db.commit()
        return cur.rowcount > 0


# ── §15.6：epoch 单调分配与执行绑定 ───────────────────────────────────


async def next_assignment_epoch(profile_session_id: str, external_run_id: str) -> int:
    """为同一 Run 分配单调递增的 assignment_epoch。

    epoch 由唯一 Coordinator 权威分配；AgentNexus 只镜像（§15.6）。
    本函数用于本地发起分配时的候选值，调用方必须接受远端更高值。
    """
    async with connect() as db:
        async with db.execute(
            """SELECT MAX(assignment_epoch) FROM code_review_deliveries
               WHERE profile_session_id = ? AND external_run_id = ?""",
            (profile_session_id, external_run_id),
        ) as cur:
            row = await cur.fetchone()
        from_deliveries = (row[0] or 0) if row else 0
        async with db.execute(
            """SELECT MAX(assignment_epoch) FROM objective_executions
               WHERE profile_session_id = ? AND external_run_id = ?""",
            (profile_session_id, external_run_id),
        ) as cur:
            row = await cur.fetchone()
        from_executions = (row[0] or 0) if row else 0
    return max(from_deliveries, from_executions) + 1


async def bind_execution_assignment(
    execution_id: str,
    *,
    profile_session_id: str,
    external_coordinator_id: str,
    external_run_id: str,
    external_attempt_id: str,
    assignment_epoch: int,
    input_manifest_digest: str = "",
    output_schema: str = "",
    deadline: Optional[float] = None,
    enforcement: Optional[Dict[str, Any]] = None,
) -> bool:
    """把本地执行绑定到 Profile 分配（§15.6 的四个 external 字段 + 分配元数据）。

    评审 R5-1：**绑定入口拒绝空/缺失的身份字段**。空的 `external_coordinator_id` 会让
    §1 要求的"Coordinator 进入 Run/Attempt 唯一关联键"落空，也让提交事务的身份围栏
    失去比较基准（此前允许写入空值，随后改绑到有效 Coordinator 时旧上传仍被放行）。
    不可围栏的绑定不得写入——在这里拒绝，比在上传时兜底更早、更明确。
    """
    required = {
        "profile_session_id": profile_session_id,
        "external_coordinator_id": external_coordinator_id,
        "external_run_id": external_run_id,
        "external_attempt_id": external_attempt_id,
    }
    blank = sorted(name for name, value in required.items() if not str(value or "").strip())
    if blank:
        raise ProfileError(
            "input_mismatch",
            f"分配绑定缺少必需的受信任身份字段：{','.join(blank)}"
            "（§1：external_coordinator_id 取受信任部署注册，不得为空）",
            scope="assignment",
        )
    if int(assignment_epoch or 0) < 1:
        raise ProfileError(
            "input_mismatch", "assignment_epoch 必须是正整数", scope="assignment"
        )
    async with connect() as db:
        cur = await db.execute(
            """UPDATE objective_executions
               SET profile_session_id=?, external_coordinator_id=?, external_run_id=?,
                   external_attempt_id=?, assignment_epoch=?, input_manifest_digest=?,
                   output_schema=?, deadline=?, enforcement_json=?, updated_at=?
               WHERE execution_id=?""",
            (
                profile_session_id,
                external_coordinator_id,
                external_run_id,
                external_attempt_id,
                int(assignment_epoch),
                input_manifest_digest,
                output_schema,
                deadline,
                json.dumps(enforcement or {}),
                time.time(),
                execution_id,
            ),
        )
        await db.commit()
        return cur.rowcount > 0


# ── 交付（§7 / §15.6 CAS / §15.8 幂等） ───────────────────────────────

_DELIVERY_SELECT = """
    SELECT delivery_id, profile_session_id, external_run_id, external_attempt_id,
           assignment_epoch, input_manifest_digest, artifact_id, artifact_digest,
           byte_length, schema_version, status, reason_code, replaces_delivery_id,
           correction_no, created_at, updated_at
    FROM code_review_deliveries
"""


def _delivery_row(row: tuple) -> Dict[str, Any]:
    return {
        "delivery_id": row[0],
        "profile_session_id": row[1],
        "external_run_id": row[2],
        "external_attempt_id": row[3],
        "assignment_epoch": row[4],
        "input_manifest_digest": row[5],
        "artifact_id": row[6],
        "artifact_digest": row[7],
        "byte_length": row[8],
        "schema_version": row[9],
        "status": row[10],
        "reason_code": row[11] or "",
        "replaces_delivery_id": row[12],
        "correction_no": row[13],
        "created_at": row[14],
        "updated_at": row[15],
    }


async def create_delivery(
    delivery_id: str,
    *,
    profile_session_id: str,
    external_run_id: str,
    external_attempt_id: str,
    assignment_epoch: int,
    input_manifest_digest: str,
    artifact_id: str,
    artifact_digest: str,
    byte_length: int,
    schema_version: str,
    replaces_delivery_id: Optional[str] = None,
    correction_no: Optional[int] = None,
) -> Tuple[Dict[str, Any], str]:
    """登记交付。返回 ``(记录, "created"|"replayed")``。

    - 相同 delivery_id + 相同 digest → 重放，返回原记录（**不得** 409）；
    - 相同 delivery_id + 不同 digest → ``delivery_conflict``；
    - 绑定 Run/Attempt/epoch 与既有记录不一致 → ``delivery_conflict``（不允许换目标）。
    """
    existing = await get_delivery(delivery_id)
    if existing:
        if existing["artifact_digest"] != artifact_digest:
            raise ProfileError(
                "delivery_conflict",
                f"delivery_id {delivery_id} 已存在且摘要不同",
                scope="delivery",
            )
        if (
            existing["external_run_id"] != external_run_id
            or existing["external_attempt_id"] != external_attempt_id
            or existing["assignment_epoch"] != int(assignment_epoch)
        ):
            raise ProfileError(
                "delivery_conflict",
                f"delivery_id {delivery_id} 的 Run/Attempt/epoch 与既有记录不一致",
                scope="delivery",
            )
        return existing, "replayed"

    if correction_no is not None and correction_no != 1:
        raise ProfileError(
            "invalid_output", "correction_no 只能为 1（§15.8 仅允许一次纠正）", scope="delivery"
        )
    if correction_no == 1 and not replaces_delivery_id:
        raise ProfileError(
            "invalid_output", "纠正交付必须携带 replaces_delivery_id（§15.8）", scope="delivery"
        )

    now = time.time()
    async with connect() as db:
        await db.execute(
            """INSERT INTO code_review_deliveries
               (delivery_id, profile_session_id, external_run_id, external_attempt_id,
                assignment_epoch, input_manifest_digest, artifact_id, artifact_digest,
                byte_length, schema_version, status, replaces_delivery_id, correction_no,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'received', ?, ?, ?, ?)""",
            (
                delivery_id,
                profile_session_id,
                external_run_id,
                external_attempt_id,
                int(assignment_epoch),
                input_manifest_digest,
                artifact_id,
                artifact_digest,
                int(byte_length),
                schema_version,
                replaces_delivery_id,
                correction_no,
                now,
                now,
            ),
        )
        await db.commit()
    created = await get_delivery(delivery_id)
    assert created is not None
    return created, "created"


async def get_delivery(delivery_id: str) -> Optional[Dict[str, Any]]:
    async with connect() as db:
        async with db.execute(
            f"{_DELIVERY_SELECT} WHERE delivery_id=?", (delivery_id,)
        ) as cur:
            row = await cur.fetchone()
    return _delivery_row(row) if row else None


async def list_deliveries(
    profile_session_id: str,
    external_run_id: Optional[str] = None,
    external_attempt_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conditions = ["profile_session_id = ?"]
    params: List[Any] = [profile_session_id]
    if external_run_id is not None:
        conditions.append("external_run_id = ?")
        params.append(external_run_id)
    if external_attempt_id is not None:
        conditions.append("external_attempt_id = ?")
        params.append(external_attempt_id)
    async with connect() as db:
        async with db.execute(
            f"{_DELIVERY_SELECT} WHERE {' AND '.join(conditions)} ORDER BY created_at ASC",
            tuple(params),
        ) as cur:
            rows = await cur.fetchall()
    return [_delivery_row(r) for r in rows]


async def update_delivery_status(delivery_id: str, status: str, reason_code: str = "") -> bool:
    async with connect() as db:
        cur = await db.execute(
            """UPDATE code_review_deliveries
               SET status=?, reason_code=?, updated_at=?
               WHERE delivery_id=?""",
            (status, reason_code, time.time(), delivery_id),
        )
        await db.commit()
        return cur.rowcount > 0


# ── Profile 回执（§7 / §15.4 / §15.7） ────────────────────────────────

_RECEIPT_SELECT = """
    SELECT receipt_id, profile_session_id, kind, decision, issuer_id, subject_kind,
           subject_id, external_run_id, external_attempt_id, report_digest,
           authority_ref, reason_code, evidence_refs, signature, enforcement, created_at
    FROM code_review_receipts
"""


def _receipt_row(row: tuple) -> Dict[str, Any]:
    return {
        "receipt_id": row[0],
        "profile_session_id": row[1],
        "kind": row[2],
        "decision": row[3],
        "issuer_id": row[4],
        "subject_ref": {"kind": row[5], "id": row[6]},
        "run_id": row[7],
        "attempt_id": row[8],
        "report_digest": row[9],
        "authority_ref": row[10] or "",
        "reason_code": row[11] or "",
        "evidence_refs": json.loads(row[12]) if row[12] else [],
        "signature": row[13] or "",
        "enforcement": row[14] or "",
        "created_at": row[15],
    }


async def create_profile_receipt(
    receipt_id: str,
    *,
    profile_session_id: str,
    kind: str,
    issuer_id: str,
    subject_kind: str,
    subject_id: str,
    external_run_id: str = "",
    external_attempt_id: Optional[str] = None,
    decision: str = "confirmed",
    report_digest: Optional[str] = None,
    authority_ref: str = "",
    reason_code: str = "",
    evidence_refs: Optional[List[Any]] = None,
    signature: str = "",
    enforcement: str = "",
) -> Dict[str, Any]:
    """写入 ``code_review.receipt.v1`` 记录（幂等：相同 receipt_id 直接返回原记录）。"""
    if kind not in ("received", "validated", "accepted", "published"):
        raise ProfileError("invalid_output", f"未知 receipt kind：{kind}", scope="receipt")
    if decision not in ("confirmed", "rejected"):
        raise ProfileError("invalid_output", f"未知 receipt decision：{decision}", scope="receipt")
    if decision == "rejected" and not reason_code:
        raise ProfileError("invalid_output", "rejected 回执必须给出 reason_code（§7）", scope="receipt")

    existing = await get_profile_receipt(receipt_id)
    if existing:
        return existing

    async with connect() as db:
        await db.execute(
            """INSERT INTO code_review_receipts
               (receipt_id, profile_session_id, kind, decision, issuer_id, subject_kind,
                subject_id, external_run_id, external_attempt_id, report_digest,
                authority_ref, reason_code, evidence_refs, signature, enforcement, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt_id,
                profile_session_id,
                kind,
                decision,
                issuer_id,
                subject_kind,
                subject_id,
                external_run_id,
                external_attempt_id,
                report_digest,
                authority_ref,
                reason_code,
                json.dumps(evidence_refs or []),
                signature,
                enforcement,
                time.time(),
            ),
        )
        await db.commit()
    created = await get_profile_receipt(receipt_id)
    assert created is not None
    return created


async def get_profile_receipt(receipt_id: str) -> Optional[Dict[str, Any]]:
    async with connect() as db:
        async with db.execute(
            f"{_RECEIPT_SELECT} WHERE receipt_id=?", (receipt_id,)
        ) as cur:
            row = await cur.fetchone()
    return _receipt_row(row) if row else None


async def list_profile_receipts(
    profile_session_id: str,
    external_run_id: Optional[str] = None,
    kind: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conditions = ["profile_session_id = ?"]
    params: List[Any] = [profile_session_id]
    if external_run_id is not None:
        conditions.append("external_run_id = ?")
        params.append(external_run_id)
    if kind is not None:
        conditions.append("kind = ?")
        params.append(kind)
    async with connect() as db:
        async with db.execute(
            f"{_RECEIPT_SELECT} WHERE {' AND '.join(conditions)} ORDER BY created_at ASC",
            tuple(params),
        ) as cur:
            rows = await cur.fetchall()
    return [_receipt_row(r) for r in rows]


# ── 协作消息 inbox（binding RC2 §4） ──────────────────────────────────

_MESSAGE_SELECT = """
    SELECT message_id, profile_session_id, message_type, direction, sender_id, receiver_id,
           correlation_id, causation_id, external_run_id, external_attempt_id,
           assignment_epoch, payload_digest, envelope_json, state, receipts_json,
           error_json, created_at, updated_at, projection_digest
    FROM code_review_messages
"""


def _message_row(row: tuple) -> Dict[str, Any]:
    return {
        "message_id": row[0],
        "profile_session_id": row[1],
        "message_type": row[2],
        "direction": row[3],
        "sender_id": row[4],
        "receiver_id": row[5],
        "correlation_id": row[6] or "",
        "causation_id": row[7],
        "run_id": row[8] or "",
        "attempt_id": row[9] or "",
        "assignment_epoch": row[10],
        "payload_digest": row[11] or "",
        "envelope": json.loads(row[12]),
        "state": row[13],
        "receipts": json.loads(row[14]) if row[14] else [],
        "error": json.loads(row[15]) if row[15] else None,
        "created_at": row[16],
        "updated_at": row[17],
        # 评审 R3-4：幂等按**业务投影**比较，投影摘要随行持久化
        "projection_digest": (row[18] or "") if len(row) > 18 else "",
    }


async def store_message(
    message_id: str,
    *,
    envelope: Dict[str, Any],
    profile_session_id: str = "",
    direction: str = "inbound",
    payload_digest: str = "",
) -> Tuple[Dict[str, Any], str]:
    """持久化消息（先落库再返回 ACK）。返回 ``(记录, "created"|"replayed")``。

    幂等按**业务投影**比较（RC2 §7，评审 R3-4）：同 ``message_id`` 且投影相同 →
    重放；投影不同 → ``idempotency_conflict``。仅追踪字段（``created_at`` 等）变化的
    重放不再被误判为冲突。
    """
    projection = projection_digest(message_projection(envelope))
    existing = await get_message(message_id)
    if existing:
        if existing["projection_digest"] != projection:
            raise ProfileError(
                "idempotency_conflict",
                f"message_id {message_id} 已存在且业务投影不同",
                scope="message",
            )
        return existing, "replayed"

    now = time.time()
    async with connect() as db:
        await db.execute(
            """INSERT INTO code_review_messages
               (message_id, profile_session_id, message_type, direction, sender_id, receiver_id,
                correlation_id, causation_id, external_run_id, external_attempt_id,
                assignment_epoch, payload_digest, envelope_json, projection_digest,
                state, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'stored', ?, ?)""",
            (
                message_id,
                profile_session_id,
                envelope.get("type", ""),
                direction,
                envelope.get("sender_id", ""),
                envelope.get("receiver_id", ""),
                envelope.get("correlation_id", ""),
                envelope.get("causation_id"),
                envelope.get("run_id", ""),
                envelope.get("attempt_id", ""),
                envelope.get("assignment_epoch"),
                payload_digest,
                json.dumps(envelope, ensure_ascii=False, sort_keys=True),
                projection,
                now,
                now,
            ),
        )
        await db.commit()
    created = await get_message(message_id)
    assert created is not None
    return created, "created"


async def get_message(message_id: str) -> Optional[Dict[str, Any]]:
    async with connect() as db:
        async with db.execute(
            f"{_MESSAGE_SELECT} WHERE message_id=?", (message_id,)
        ) as cur:
            row = await cur.fetchone()
    return _message_row(row) if row else None


async def set_message_state(
    message_id: str,
    state: str,
    *,
    receipts: Optional[List[Any]] = None,
    error: Optional[Dict[str, Any]] = None,
) -> bool:
    """更新消息处理状态（stored/processed/rejected）与回执/错误。"""
    if state not in ("stored", "processed", "rejected"):
        raise ValueError(f"未知 message state：{state}")
    async with connect() as db:
        cur = await db.execute(
            """UPDATE code_review_messages
               SET state=?, receipts_json=COALESCE(?, receipts_json),
                   error_json=?, updated_at=?
               WHERE message_id=?""",
            (
                state,
                json.dumps(receipts) if receipts is not None else None,
                json.dumps(error) if error is not None else None,
                time.time(),
                message_id,
            ),
        )
        await db.commit()
        return cur.rowcount > 0


# ── §15.7 角色授权 ────────────────────────────────────────────────────

PROFILE_ROLES = (
    "requester",
    "coordinator",
    "worker",
    "validator",
    "publisher",
    "policy_admin",
    "evidence_reader",
)


async def grant_role(
    principal_id: str,
    role: str,
    *,
    instance_id: str = "",
    project_id: str = "",
    profile_session_id: str = "",
) -> Dict[str, Any]:
    """登记凭据主体的角色（服务端登记，正文自报无效）。"""
    if role not in PROFILE_ROLES:
        raise ValueError(f"未登记的角色：{role}")
    if not principal_id:
        raise ValueError("principal_id 必填")
    async with connect() as db:
        await db.execute(
            """INSERT OR IGNORE INTO code_review_role_grants
               (principal_id, role, instance_id, project_id, profile_session_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (principal_id, role, instance_id, project_id, profile_session_id, time.time()),
        )
        await db.commit()
    return {
        "principal_id": principal_id,
        "role": role,
        "instance_id": instance_id,
        "project_id": project_id,
        "profile_session_id": profile_session_id,
    }


async def list_role_grants(principal_id: Optional[str] = None) -> List[Dict[str, Any]]:
    async with connect() as db:
        if principal_id:
            cur = await db.execute(
                """SELECT principal_id, role, instance_id, project_id, profile_session_id
                   FROM code_review_role_grants WHERE principal_id=?""",
                (principal_id,),
            )
        else:
            cur = await db.execute(
                """SELECT principal_id, role, instance_id, project_id, profile_session_id
                   FROM code_review_role_grants"""
            )
        rows = await cur.fetchall()
    return [
        {
            "principal_id": r[0],
            "role": r[1],
            "instance_id": r[2],
            "project_id": r[3],
            "profile_session_id": r[4],
        }
        for r in rows
    ]


async def roles_configured() -> bool:
    """部署是否登记了任何角色。

    ``False`` 表示只能按"部署约定"运行：不得声称强制隔离，也不得运行
    符合性授权测试（Profile §15.7、CP-24）。
    """
    async with connect() as db:
        async with db.execute("SELECT COUNT(1) FROM code_review_role_grants") as cur:
            row = await cur.fetchone()
    return bool(row and row[0])


async def resolve_roles(
    principal_id: str,
    *,
    instance_id: str = "",
    project_id: str = "",
    profile_session_id: str = "",
) -> set:
    """解析主体在给定范围内的角色集合（范围为空表示全局授权）。"""
    async with connect() as db:
        async with db.execute(
            """SELECT role, instance_id, project_id, profile_session_id
               FROM code_review_role_grants WHERE principal_id=?""",
            (principal_id,),
        ) as cur:
            rows = await cur.fetchall()
    roles = set()
    for role, inst, proj, sess in rows:
        if inst and instance_id and inst != instance_id:
            continue
        if proj and project_id and proj != project_id:
            continue
        if sess and profile_session_id and sess != profile_session_id:
            continue
        roles.add(role)
    return roles


# ── §15.5 强制能力注册（"无法支持的能力"声明） ────────────────────────

ENFORCEMENT_LEVELS = ("enforced", "declared_only", "unsupported")


async def set_enforcement(constraint_name: str, level: str, component: str = "") -> Dict[str, Any]:
    """登记某约束在本部署的强制级别。未登记的约束一律视为 not enforced。"""
    if level not in ENFORCEMENT_LEVELS:
        raise ValueError(f"未知强制级别：{level}")
    if level in ("enforced", "declared_only") and not component:
        raise ValueError("enforced/declared_only 必须给出执行组件（RC2 §1）")
    async with connect() as db:
        await db.execute(
            """INSERT INTO code_review_enforcement (constraint_name, level, component, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(constraint_name) DO UPDATE SET
                 level=excluded.level, component=excluded.component, updated_at=excluded.updated_at""",
            (constraint_name, level, component, time.time()),
        )
        await db.commit()
    return {"constraint": constraint_name, "level": level, "component": component}


async def list_enforcement() -> List[Dict[str, Any]]:
    async with connect() as db:
        async with db.execute(
            "SELECT constraint_name, level, component FROM code_review_enforcement"
        ) as cur:
            rows = await cur.fetchall()
    return [{"constraint": r[0], "level": r[1], "component": r[2] or ""} for r in rows]


async def unsupported_requirements(required: Dict[str, str]) -> List[str]:
    """返回**未真正强制**的必需约束列表。

    ``required`` 形如 ``{"token_cost_budget": "enforced", ...}``，来自 Assignment 的
    ``enforcement_requirements``。本部署注册表里级别不是 ``enforced`` 的项一律返回，
    调用方必须 fail-closed 返回 ``enforcement_unavailable``（§15.5 / CP-25）。
    """
    registered = {row["constraint"]: row["level"] for row in await list_enforcement()}
    missing: List[str] = []
    for constraint, declared in required.items():
        if declared == "unsupported":
            continue  # 任务本就不要求该能力
        if registered.get(constraint) != "enforced":
            missing.append(constraint)
    return missing


# ── §15.6 交付提交（单事务 CAS） ──────────────────────────────────────

#: 允许提交交付的执行状态（其余状态一律 stale_assignment / superseded_input）
_SUBMITTABLE_EXECUTION_STATES = ("pending", "running")


async def commit_profile_delivery(
    execution_id: str,
    *,
    actor_did: str,
    artifact_type: str,
    artifact_body: str,
    media_type: str,
    schema_version: str,
    summary: str,
    run_state: str,
    outcome: Optional[str],
    domain_status: str,
    enforcement: str,
    receipt_issuer: str = "",
    validator_issuer: str = "",
    retention_until: Optional[float] = None,
    report_input_manifest_digest: str = "",
) -> Dict[str, Any]:
    """在**单个本地事务**内完成 Profile 交付的 CAS + 落库。

    事务内依次校验（§15.6）：执行存在、Profile 绑定、允许状态、租约未过期、
    未超 deadline、`result_hash` 幂等；随后写入 artifact（含 §15.3 的
    `content_hash`/`byte_length` 元数据）、交付记录与 ``received``/``validated``
    回执（**不签发 accepted**——那是 Coordinator 的权威动作），最后更新执行行。

    产物字节先写入 Vault，再进入事务：若 CAS 失败，Vault 中会留下无引用的孤儿
    条目（不产生 artifact/delivery 记录，因而不构成可见产物）。

    返回 ``{"delivery_id", "artifact_id", "artifact_ref", "receipts", "replayed", ...}``。
    """
    from agent_net.code_review.digest import DigestError, artifact_body_bytes, report_digest

    try:
        artifact_body_bytes(artifact_body)
        digest, byte_length = report_digest(artifact_body)
    except DigestError as exc:
        raise ProfileError("invalid_output", str(exc), scope="delivery") from exc

    execution = await get_objective_execution(execution_id)
    if execution is None:
        raise ProfileError(
            "input_mismatch", f"执行不存在：{execution_id}", scope="delivery"
        )
    if not execution.get("profile_session_id"):
        raise ProfileError(
            "input_mismatch",
            "该执行未绑定 Profile 会话；不得经 Profile 交付入口提交",
            scope="delivery",
        )

    session = await get_coordination_session(execution["coordination_session_id"])
    enclave_id = (session or {}).get("enclave_id") or "default"
    artifact_id = f"art_{uuid.uuid4().hex[:16]}"
    vault_key = f"code-review/{execution['profile_session_id']}/{artifact_id}.body"
    try:
        from .enclave import vault_put

        await vault_put(enclave_id, vault_key, artifact_body, actor_did)
    except Exception as exc:  # §15.3：存储失败必须失败，不得截断正文冒充成功
        raise ProfileError(
            "temporarily_unavailable",
            f"产物存储失败，未登记交付：{exc}",
            scope="artifact_storage",
            retryable=True,
        ) from exc
    content_ref = f"vault://{enclave_id}/{vault_key}"

    now = time.time()
    delivery_id = f"del_{uuid.uuid4().hex[:16]}"
    received_receipt_id = f"rcpt_{uuid.uuid4().hex[:16]}"
    validated_receipt_id = f"rcpt_{uuid.uuid4().hex[:16]}" if validator_issuer else ""

    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                """SELECT status, lease_expires_at, deadline, result_hash, artifact_id,
                          receipt_id, external_run_id, external_attempt_id,
                          assignment_epoch, profile_session_id
                   FROM objective_executions WHERE execution_id=?""",
                (execution_id,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                raise ProfileError("input_mismatch", "执行不存在", scope="delivery")

            status, lease_expires_at, deadline, existing_hash = row[0], row[1], row[2], row[3]

            # 幂等：同摘要重放
            if existing_hash:
                if existing_hash == digest:
                    await db.rollback()
                    return await _replay_profile_delivery(execution_id, digest)
                raise ProfileError(
                    "delivery_conflict",
                    "该执行已提交过不同摘要的交付",
                    scope="delivery",
                )

            if status not in _SUBMITTABLE_EXECUTION_STATES:
                raise ProfileError(
                    "stale_assignment",
                    f"执行状态 {status} 不接受交付（旧 epoch 或已终结）",
                    scope="delivery",
                )
            if lease_expires_at is not None and lease_expires_at < now:
                raise ProfileError(
                    "stale_assignment", "租约已过期，不再接受交付", scope="delivery"
                )
            if deadline is not None and now > deadline:
                raise ProfileError(
                    "deadline_exceeded", "已超过 Run deadline", scope="delivery"
                )

            # CP-04：报告声明的输入清单必须与本次分配冻结的一致
            assigned_manifest = execution.get("input_manifest_digest") or ""
            if assigned_manifest and report_input_manifest_digest != assigned_manifest:
                raise ProfileError(
                    "input_mismatch",
                    "报告声明的 input_manifest_digest 与分配冻结值不一致",
                    scope="delivery",
                )

            await db.execute(
                """INSERT INTO artifacts
                   (artifact_id, coordination_session_id, run_id, stage, artifact_type,
                    producer_did, content_ref, content_hash, schema_version, created_at,
                    media_type, byte_length, access_scope, retention_until,
                    digest_algorithm, profile_session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    artifact_id,
                    execution["coordination_session_id"],
                    execution["run_id"],
                    execution["stage"],
                    artifact_type,
                    execution["worker_did"],
                    content_ref,
                    digest,
                    schema_version,
                    now,
                    media_type,
                    byte_length,
                    "service_private",
                    retention_until,
                    "sha256-bytes-v1",
                    execution["profile_session_id"],
                ),
            )

            delivery_status = "validated" if validated_receipt_id else "received"
            await db.execute(
                """INSERT INTO code_review_deliveries
                   (delivery_id, profile_session_id, external_run_id, external_attempt_id,
                    assignment_epoch, input_manifest_digest, artifact_id, artifact_digest,
                    byte_length, schema_version, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    delivery_id,
                    execution["profile_session_id"],
                    execution.get("external_run_id") or "",
                    execution.get("external_attempt_id") or "",
                    int(execution.get("assignment_epoch") or 0),
                    execution.get("input_manifest_digest") or "",
                    artifact_id,
                    digest,
                    byte_length,
                    schema_version,
                    delivery_status,
                    now,
                    now,
                ),
            )

            receipt_specs = [
                (received_receipt_id, "received", receipt_issuer or actor_did),
            ]
            if validated_receipt_id:
                receipt_specs.append((validated_receipt_id, "validated", validator_issuer))
            for rcpt_id, kind, issuer in receipt_specs:
                await db.execute(
                    """INSERT INTO code_review_receipts
                       (receipt_id, profile_session_id, kind, decision, issuer_id,
                        subject_kind, subject_id, external_run_id, external_attempt_id,
                        report_digest, authority_ref, reason_code, evidence_refs,
                        signature, enforcement, created_at)
                       VALUES (?, ?, ?, 'confirmed', ?, 'delivery', ?, ?, ?, ?, ?, '', '[]', '', ?, ?)""",
                    (
                        rcpt_id,
                        execution["profile_session_id"],
                        kind,
                        issuer,
                        delivery_id,
                        execution.get("external_run_id") or "",
                        execution.get("external_attempt_id"),
                        digest,
                        "",
                        enforcement,
                        now,
                    ),
                )

            await db.execute(
                """UPDATE objective_executions
                   SET status=?, artifact_id=?, receipt_id=?, result_hash=?, completed_at=?,
                       updated_at=?
                   WHERE execution_id=?""",
                (run_state, artifact_id, received_receipt_id, digest, now, now, execution_id),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    receipts = [
        await get_profile_receipt(rid)
        for rid, _kind, _issuer in [
            (received_receipt_id, "received", receipt_issuer or actor_did),
            *([(validated_receipt_id, "validated", validator_issuer)] if validated_receipt_id else []),
        ]
    ]
    return {
        "delivery_id": delivery_id,
        "artifact_id": artifact_id,
        "artifact_ref": {
            "artifact_id": artifact_id,
            "producer_id": execution["worker_did"],
            "media_type": media_type,
            "schema_version": schema_version,
            "digest_algorithm": "sha256-bytes-v1",
            "digest": digest,
            "byte_length": byte_length,
            "locator": f"agentnexus-artifact:{artifact_id}",
            "access_scope": "service_private",
            "retention_until": retention_until,
        },
        "receipts": [r for r in receipts if r],
        "replayed": False,
        "run_state": run_state,
        "outcome": outcome,
        "domain_status": domain_status,
        "enforcement": enforcement,
        "summary": summary,
    }


async def _replay_profile_delivery(execution_id: str, digest: str) -> Dict[str, Any]:
    """幂等重放：返回既有 artifact/交付/回执，不重复签发。"""
    execution = await get_objective_execution(execution_id)
    artifact_id = (execution or {}).get("artifact_id") or ""
    deliveries = await list_deliveries(
        (execution or {}).get("profile_session_id") or "",
        external_run_id=(execution or {}).get("external_run_id") or None,
        external_attempt_id=(execution or {}).get("external_attempt_id") or None,
    )
    receipts = await list_profile_receipts(
        (execution or {}).get("profile_session_id") or "",
        (execution or {}).get("external_run_id") or None,
    )
    return {
        "delivery_id": deliveries[-1]["delivery_id"] if deliveries else "",
        "artifact_id": artifact_id,
        "artifact_ref": None,
        "receipts": receipts,
        "replayed": True,
        "digest": digest,
    }


# ── 评审 B1：服务接口独立凭据登记 ─────────────────────────────────────


def _principal_row(row: tuple) -> Dict[str, Any]:
    return {
        "token_sha256": row[0],
        "principal_id": row[1],
        "roles": json.loads(row[2]) if row[2] else [],
        "dids": json.loads(row[3]) if row[3] else [],
        "instances": json.loads(row[4]) if row[4] else [],
        "projects": json.loads(row[5]) if row[5] else [],
        "sessions": json.loads(row[6]) if row[6] else [],
        "created_at": row[7],
        "updated_at": row[8],
    }


async def register_service_principal(
    credential: str,
    *,
    principal_id: str,
    roles: List[str],
    dids: Optional[List[str]] = None,
    instances: Optional[List[str]] = None,
    projects: Optional[List[str]] = None,
    sessions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """登记一条服务凭据（凭据只存 sha256 摘要，不存明文）。

    重复登记同一凭据即更新其投影；``principal_id`` 不可为空（否则等于没有主体绑定）。
    """
    if not credential or not principal_id:
        raise ProfileError("input_mismatch", "凭据与 principal_id 均不得为空", scope="authorization")
    token_sha256 = hashlib.sha256(credential.encode("utf-8")).hexdigest()
    now = time.time()
    async with connect() as db:
        await db.execute(
            """INSERT INTO code_review_service_principals
               (token_sha256, principal_id, roles_json, dids_json, instances_json,
                projects_json, sessions_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(token_sha256) DO UPDATE SET
                 principal_id=excluded.principal_id,
                 roles_json=excluded.roles_json,
                 dids_json=excluded.dids_json,
                 instances_json=excluded.instances_json,
                 projects_json=excluded.projects_json,
                 sessions_json=excluded.sessions_json,
                 updated_at=excluded.updated_at""",
            (
                token_sha256,
                principal_id,
                json.dumps(list(roles or [])),
                json.dumps(list(dids or [])),
                json.dumps(list(instances or [])),
                json.dumps(list(projects or [])),
                json.dumps(list(sessions or [])),
                now,
                now,
            ),
        )
        await db.commit()
    return {
        "token_sha256": token_sha256,
        "principal_id": principal_id,
        "roles": list(roles or []),
        "dids": list(dids or []),
        "instances": list(instances or []),
        "projects": list(projects or []),
        "sessions": list(sessions or []),
        "created_at": now,
        "updated_at": now,
    }


async def resolve_service_principal(credential: str) -> Optional[Dict[str, Any]]:
    """按凭据解析 principal；未登记返回 ``None``。"""
    if not credential:
        return None
    token_sha256 = hashlib.sha256(credential.encode("utf-8")).hexdigest()
    async with connect() as db:
        async with db.execute(
            """SELECT token_sha256, principal_id, roles_json, dids_json, instances_json,
                      projects_json, sessions_json, created_at, updated_at
               FROM code_review_service_principals WHERE token_sha256=?""",
            (token_sha256,),
        ) as cur:
            row = await cur.fetchone()
    return _principal_row(row) if row else None


async def service_principals_configured() -> bool:
    """是否登记了任何服务凭据；未登记时服务接口必须**拒绝**而不是放行（RC2 §1）。"""
    async with connect() as db:
        async with db.execute("SELECT COUNT(*) FROM code_review_service_principals") as cur:
            (count,) = await cur.fetchone()
    return bool(count)


async def clear_service_principals() -> None:
    """清空凭据登记（测试隔离用，生产不应调用）。"""
    async with connect() as db:
        await db.execute("DELETE FROM code_review_service_principals")
        await db.commit()


# ── 评审 B4：上传幂等映射 ─────────────────────────────────────────────


async def reserve_artifact_idempotency(
    principal_id: str,
    action: str,
    resource_scope: str,
    idempotency_key: str,
    artifact_id: str,
    request_digest: str,
) -> Tuple[str, str]:
    """预留 ``(principal, action, resource_scope, Idempotency-Key)`` → artifact。

    评审 B4 / R2-1 / R3-4：

    - ``created``：本次可继续登记（新预留，或**续用**上次未提交成功的预留）；
    - ``replayed``：已有 **committed** 的相同投影，返回原 artifact_id；
    - 只有"同命名空间 + 同 key + **不同业务投影摘要**"才是 ``delivery_conflict``。

    ``action`` / ``resource_scope`` 实现 RC2 §7 的"幂等键按认证 principal + 动作 +
    资源范围隔离"：同一 key 换到别的资源范围属于**不同操作**，不按冲突处理。
    """
    if not idempotency_key:
        raise ProfileError("input_mismatch", "产物上传必须带 Idempotency-Key", scope="artifact")
    now = time.time()
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                """SELECT artifact_id, request_digest, state FROM code_review_artifact_idempotency
                   WHERE principal_id=? AND action=? AND resource_scope=? AND idempotency_key=?""",
                (principal_id, action, resource_scope, idempotency_key),
            ) as cur:
                row = await cur.fetchone()
            if row:
                existing_artifact, existing_digest, state = row[0], row[1], (row[2] or "pending")
                if existing_digest != request_digest:
                    await db.rollback()
                    raise ProfileError(
                        "delivery_conflict",
                        "同一 Idempotency-Key 在相同资源范围内的业务投影不同",
                        scope="artifact",
                    )
                await db.commit()
                # pending 说明上次没提交成功：允许续用同一 artifact_id 重试
                return ("replayed" if state == "committed" else "created"), existing_artifact
            await db.execute(
                """INSERT INTO code_review_artifact_idempotency
                   (principal_id, action, resource_scope, idempotency_key, artifact_id,
                    request_digest, state, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (
                    principal_id,
                    action,
                    resource_scope,
                    idempotency_key,
                    artifact_id,
                    request_digest,
                    now,
                    now,
                ),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return "created", artifact_id


async def commit_artifact_with_idempotency(
    *,
    principal_id: str,
    action: str,
    resource_scope: str,
    idempotency_key: str,
    artifact_id: str,
    coordination_session_id: str,
    profile_session_id: str,
    run_id: str,
    stage: str,
    artifact_type: str,
    producer_did: str,
    content_ref: str,
    content_hash: str,
    schema_version: str,
    media_type: str,
    byte_length: int,
    access_scope: str,
    retention_until: Optional[float],
    retention_until_text: str,
    digest_algorithm: str,
    assignment_execution_id: str,
    expected_attempt_id: str,
    expected_coordinator_id: str,
    expected_epoch: int,
    expected_worker_did: str,
) -> Tuple[str, Dict[str, Any]]:
    """**同一事务**内复检分配有效性、登记产物并把幂等映射置为 committed。

    返回 ``(状态, 记录)``：``created`` 表示本次登记成功；``replayed`` 表示同命名空间同键
    已经 committed，返回**已存在**的产物（评审 R3-3：并发同 key 不得以主键冲突收场）。

    修复三个问题：

    - **R2-1**：产物行与映射状态一起提交，任一步失败整体回滚，映射保持 pending 可重试；
    - **R3-2**：分配有效性（worker / Coordinator / Attempt / epoch / 租约 / deadline /
      执行状态）在**提交事务内**重新读取并校验——提前查询不构成原子围栏，否则
      "查完绑定再被取消"的窗口仍会登记产物；
    - **R3-3**：事务内先看映射状态；已 committed 直接返回原 artifact，不再无条件 INSERT
      （两个并发同 key 请求此前会在第二阶段主键冲突并返回非契约 500）。
    - **保留建议**：``retention_until_text`` 一并**写库**，不再只靠内存赋值回显。
    """
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        # 评审 R3-2（P2）：时间戳必须在**取得写锁之后**读取。写在 BEGIN 之前时，事务若在
        # 写锁上等待，租约可能在等待期间过期，而检查仍用等待前的旧时间通过。
        now = time.time()
        try:
            # 1) 幂等状态：已 committed 说明同命名空间同键的请求已经成功
            async with db.execute(
                """SELECT artifact_id, state FROM code_review_artifact_idempotency
                   WHERE principal_id=? AND action=? AND resource_scope=? AND idempotency_key=?""",
                (principal_id, action, resource_scope, idempotency_key),
            ) as cur:
                idem = await cur.fetchone()
            if idem and (idem[1] or "") == "committed":
                existing = await _artifact_by_id(db, idem[0])
                await db.commit()
                if existing is None:
                    raise ProfileError(
                        "idempotency_conflict",
                        "幂等映射已 committed 但找不到对应产物，拒绝伪造重放",
                        scope="artifact",
                    )
                return "replayed", existing
            if idem and idem[0] != artifact_id:
                raise ProfileError(
                    "idempotency_conflict",
                    "幂等预留与本次 artifact_id 不匹配",
                    scope="artifact",
                )
            if idem is None:
                raise ProfileError(
                    "idempotency_conflict",
                    "没有该命名空间的幂等预留，拒绝登记产物",
                    scope="artifact",
                )

            # 2) R3-2：在事务内复检分配（含 Attempt / Coordinator 改绑与取锁后的时间）
            await _verify_assignment_in_transaction(
                db,
                execution_id=assignment_execution_id,
                profile_session_id=profile_session_id,
                external_run_id=run_id,
                expected_attempt_id=expected_attempt_id,
                expected_coordinator_id=expected_coordinator_id,
                expected_epoch=expected_epoch,
                expected_worker_did=expected_worker_did,
            )

            # 3) 登记产物（含 retention 原文）
            await db.execute(
                """INSERT INTO artifacts
                   (artifact_id, coordination_session_id, run_id, stage, artifact_type,
                    producer_did, content_ref, content_hash, schema_version, created_at,
                    media_type, byte_length, access_scope, retention_until,
                    digest_algorithm, profile_session_id, retention_until_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    artifact_id,
                    coordination_session_id,
                    run_id,
                    stage,
                    artifact_type,
                    producer_did,
                    content_ref,
                    content_hash,
                    schema_version,
                    now,
                    media_type,
                    byte_length,
                    access_scope,
                    retention_until,
                    digest_algorithm,
                    profile_session_id,
                    retention_until_text,
                ),
            )
            # 4) 置 committed（带命名空间，且必须是本次预留）
            cur = await db.execute(
                """UPDATE code_review_artifact_idempotency
                   SET state='committed', updated_at=?
                   WHERE principal_id=? AND action=? AND resource_scope=?
                     AND idempotency_key=? AND artifact_id=?""",
                (now, principal_id, action, resource_scope, idempotency_key, artifact_id),
            )
            if cur.rowcount == 0:
                raise ProfileError(
                    "idempotency_conflict",
                    "幂等预留与产物登记不匹配（预留不属于本次上传）",
                    scope="artifact",
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return "created", {
        "artifact_id": artifact_id,
        "coordination_session_id": coordination_session_id,
        "run_id": run_id,
        "stage": stage,
        "artifact_type": artifact_type,
        "producer_did": producer_did,
        "content_ref": content_ref,
        "content_hash": content_hash,
        "schema_version": schema_version,
        "media_type": media_type,
        "byte_length": byte_length,
        "access_scope": access_scope,
        "retention_until": retention_until,
        "retention_until_text": retention_until_text,
        "digest_algorithm": digest_algorithm,
        "profile_session_id": profile_session_id,
        "created_at": now,
    }


async def _artifact_by_id(db, artifact_id: str) -> Optional[Dict[str, Any]]:
    from .deliverable_store import _ARTIFACT_SELECT, _artifact_row_to_dict

    async with db.execute(_ARTIFACT_SELECT + " WHERE artifact_id=?", (artifact_id,)) as cur:
        row = await cur.fetchone()
    return _artifact_row_to_dict(row) if row else None


#: 允许提交产物的执行状态（终态/取消一律拒绝）
_ASSIGNABLE_SUBMIT_STATES = ("pending", "running")


async def _verify_assignment_in_transaction(
    db,
    *,
    execution_id: str,
    profile_session_id: str,
    external_run_id: str,
    expected_attempt_id: str,
    expected_coordinator_id: str,
    expected_epoch: int,
    expected_worker_did: str,
) -> None:
    """在提交事务内复检分配（评审 R3-2，含第三/四轮复审的缺口）。

    必须在**已取得写锁之后**调用：

    - **身份元组完整核对**：`(external_coordinator_id, external_run_id, external_attempt_id)`
      与 assignment_epoch 都要与本次请求读取时一致。第三轮复审指出上一版读了 Attempt 与
      Coordinator 却**没有比较**；第四轮复审进一步指出比较**不能加真值守卫**——空字符串是
      可比较的值，预期值为空时跳过比较会让"从空 ID 改绑到另一 Coordinator"逃过围栏。
    - **过期判断必须用取锁后的时间**：时间戳由本函数在持锁后自行读取，调用方无法传入陈旧值；
      否则事务在写锁上等待期间租约过期仍会放行。
    """
    checked_at = time.time()
    async with db.execute(
        """SELECT profile_session_id, external_run_id, external_attempt_id, external_coordinator_id,
                  worker_did, assignment_epoch, status, lease_expires_at, deadline
           FROM objective_executions WHERE execution_id=?""",
        (execution_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise ProfileError("stale_assignment", "分配在执行前已不存在", scope="artifact")
    (
        session_id,
        run_id,
        attempt_id,
        coordinator_id,
        worker_did,
        epoch,
        status,
        lease_expires_at,
        deadline,
    ) = row
    if session_id != profile_session_id or run_id != external_run_id:
        raise ProfileError("stale_assignment", "分配已被改绑到其它 Run/session", scope="artifact")
    # 三处身份比较**都不得加真值守卫**：`if expected_x and ...` 在预期值为空字符串时会
    # 直接跳过比较，于是"从空 ID 改绑到另一 Coordinator/Attempt"不被发现（第四轮复审
    # 复现：空 external_coordinator_id → 改绑另一 Coordinator → 旧上传仍 201 并登记产物）。
    # 空值是**可比较的值**，不是"无需比较"的信号。
    if (attempt_id or "") != (expected_attempt_id or ""):
        raise ProfileError(
            "stale_assignment",
            f"分配的 Attempt 已被改绑（请求 {expected_attempt_id or '空'} / 当前 {attempt_id or '空'}）",
            scope="artifact",
        )
    if (coordinator_id or "") != (expected_coordinator_id or ""):
        raise ProfileError(
            "stale_assignment",
            "分配的 Coordinator 已被改绑"
            f"（请求 {expected_coordinator_id or '空'} / 当前 {coordinator_id or '空'}）",
            scope="artifact",
        )
    if int(epoch or 0) != int(expected_epoch):
        raise ProfileError("stale_assignment", "分配 epoch 已变化", scope="artifact")
    if (worker_did or "") != (expected_worker_did or ""):
        raise ProfileError(
            "authority_denied",
            f"认证主体与分配的 worker 不一致（请求 {expected_worker_did or '空'} / 当前 {worker_did or '空'}）",
            scope="authorization",
        )
    if (status or "") not in _ASSIGNABLE_SUBMIT_STATES:
        raise ProfileError(
            "stale_assignment", f"分配已不处于可提交状态（{status}）", scope="artifact"
        )
    if lease_expires_at is not None and float(lease_expires_at) < checked_at:
        raise ProfileError("stale_assignment", "分配租约已过期", scope="artifact")
    if deadline is not None and float(deadline) < checked_at:
        raise ProfileError("deadline_exceeded", "分配已超过 deadline", scope="artifact")


async def resolve_assignment_binding(
    *, profile_session_id: str, external_run_id: str, external_attempt_id: str
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """按 ``(session, run, attempt)`` 解析**唯一**分配绑定（评审 R2-2）。

    返回 ``(状态, 绑定)``，状态为：

    - ``ok``：恰好一条绑定；
    - ``unknown_run``：没有任何绑定 —— 上传的 run/attempt/epoch 只是可任意填写的标签；
    - ``ambiguous``：多于一条 —— 无法判定唯一 Coordinator/分配，必须拒绝。
    """
    async with connect() as db:
        async with db.execute(
            """SELECT execution_id, coordination_session_id, worker_did, status,
                      assignment_epoch, deadline, external_coordinator_id, lease_expires_at
               FROM objective_executions
               WHERE profile_session_id=? AND external_run_id=? AND external_attempt_id=?""",
            (profile_session_id, external_run_id, external_attempt_id),
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        return "unknown_run", None
    if len(rows) > 1:
        return "ambiguous", None
    row = rows[0]
    return "ok", {
        "execution_id": row[0],
        "coordination_session_id": row[1] or "",
        "worker_did": row[2] or "",
        "status": row[3] or "",
        "assignment_epoch": row[4] or 0,
        "deadline": row[5],
        "external_coordinator_id": row[6] or "",
        "lease_expires_at": row[7],
        "external_attempt_id": external_attempt_id,
    }


async def resolve_profile_session(
    *,
    coordination_session_id: Optional[str] = None,
    coordinator_id: Optional[str] = None,
    external_run_id: Optional[str] = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """解析**唯一** Profile 会话（评审 R3-1 与"同名 Run 歧义"建议）。

    返回 ``(状态, 会话)``：``ok`` / ``not_found`` / ``ambiguous``。

    上一版直接 ``fetchone()`` 取第一条：既把"查不到"当成空 session 继续放行（R3-1），
    也在不同 Coordinator 出现同名 Run 时**任意挑一条**。两种情况这里都显式暴露给调用方。
    """
    conditions: List[str] = []
    params: List[Any] = []
    if coordination_session_id:
        conditions.append("coordination_session_id = ?")
        params.append(coordination_session_id)
    if coordinator_id:
        conditions.append("coordinator_id = ?")
        params.append(coordinator_id)
    if external_run_id:
        conditions.append("external_run_id = ?")
        params.append(external_run_id)
    if not conditions:
        raise ValueError("必须给出至少一个查询条件")
    async with connect() as db:
        async with db.execute(
            f"{_SESSION_SELECT} WHERE {' AND '.join(conditions)}", tuple(params)
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        return "not_found", None
    if len(rows) > 1:
        return "ambiguous", None
    return "ok", _session_row(rows[0])


#: 允许上传产物的执行状态（终态/取消一律拒绝）
_SUBMITTABLE_ASSIGNMENT_STATES = ("pending", "running")


async def store_receipt_message(
    message_id: str,
    *,
    envelope: Dict[str, Any],
    profile_session_id: str,
    receipt_id: str,
    kind: str,
    issuer_id: str,
    subject_kind: str,
    subject_id: str,
    decision: str,
    external_run_id: str,
    external_attempt_id: Optional[str],
    report_digest: Optional[str],
    authority_ref: str,
    reason_code: str,
    evidence_refs: List[Any],
    enforcement: str,
) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    """**同一事务**校验幂等投影、写业务回执、写 inbox 并置 processed（评审 R2-3）。

    上一版先单独 ``create_profile_receipt`` 提交，再写 inbox：冲突消息虽然返回 409，
    但新回执已经落库（复现 ``REJECTED_MESSAGE_SIDE_EFFECT 409 receipt_persisted True``）；
    进程在两步之间退出还会留下没有 inbox 的权威记录。

    本函数先在事务内完成**全部**校验（消息投影、回执投影），任何冲突都在写入前抛出，
    因此冲突无副作用；随后回执、inbox、processed 一起提交，故障窗口不再存在。
    """
    if kind not in ("received", "validated", "accepted", "published"):
        raise ProfileError("invalid_output", f"未知 receipt kind：{kind}", scope="receipt")
    if decision not in ("confirmed", "rejected"):
        raise ProfileError("invalid_output", f"未知 receipt decision：{decision}", scope="receipt")
    if decision == "rejected" and not reason_code:
        raise ProfileError("invalid_output", "rejected 回执必须给出 reason_code（§7）", scope="receipt")

    now = time.time()
    projection = projection_digest(message_projection(envelope))
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            # 1) 消息幂等投影：同 message_id 必须同**业务投影**（§7 / 评审 R3-4）
            async with db.execute(
                "SELECT projection_digest, state FROM code_review_messages WHERE message_id=?",
                (message_id,),
            ) as cur:
                message_row = await cur.fetchone()
            if message_row is not None:
                stored_projection = message_row[0] or ""
                if stored_projection != projection:
                    raise ProfileError(
                        "idempotency_conflict",
                        f"message_id {message_id} 已存在且业务投影不同",
                        scope="message",
                    )

            # 2) 回执幂等投影：同 receipt_id 必须同投影
            async with db.execute(
                """SELECT profile_session_id, kind, decision, issuer_id, subject_kind, subject_id,
                          external_run_id, external_attempt_id, report_digest, authority_ref,
                          reason_code, evidence_refs
                   FROM code_review_receipts WHERE receipt_id=?""",
                (receipt_id,),
            ) as cur:
                receipt_row = await cur.fetchone()
            if receipt_row is not None:
                actual = (
                    receipt_row[0] or "",
                    receipt_row[1] or "",
                    receipt_row[2] or "",
                    receipt_row[3] or "",
                    receipt_row[4] or "",
                    receipt_row[5] or "",
                    receipt_row[6] or "",
                    receipt_row[7],
                    receipt_row[8],
                    receipt_row[9] or "",
                    receipt_row[10] or "",
                    json.loads(receipt_row[11]) if receipt_row[11] else [],
                )
                expected = (
                    profile_session_id,
                    kind,
                    decision,
                    issuer_id,
                    subject_kind,
                    subject_id,
                    external_run_id,
                    external_attempt_id,
                    report_digest,
                    authority_ref,
                    reason_code,
                    list(evidence_refs or []),
                )
                if actual != expected:
                    raise ProfileError(
                        "idempotency_conflict",
                        f"receipt_id {receipt_id} 已存在且投影不同（不得静默重放为旧回执）",
                        scope="receipt",
                    )
            else:
                await db.execute(
                    """INSERT INTO code_review_receipts
                       (receipt_id, profile_session_id, kind, decision, issuer_id, subject_kind,
                        subject_id, external_run_id, external_attempt_id, report_digest,
                        authority_ref, reason_code, evidence_refs, signature, enforcement, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)""",
                    (
                        receipt_id,
                        profile_session_id,
                        kind,
                        decision,
                        issuer_id,
                        subject_kind,
                        subject_id,
                        external_run_id,
                        external_attempt_id,
                        report_digest,
                        authority_ref,
                        reason_code,
                        json.dumps(list(evidence_refs or [])),
                        enforcement,
                        now,
                    ),
                )

            # 3) 回执信封（MessageView 对外暴露的就是它）
            receipt_envelope = _receipt_envelope_for_store(
                receipt_id=receipt_id,
                kind=kind,
                issuer_id=issuer_id,
                subject_kind=subject_kind,
                subject_id=subject_id,
                decision=decision,
                external_run_id=external_run_id or envelope.get("run_id", ""),
                external_attempt_id=external_attempt_id,
                report_digest=report_digest,
                authority_ref=authority_ref,
                reason_code=reason_code,
                evidence_refs=list(evidence_refs or []),
                created_at=now,
                envelope=envelope,
            )

            # 4) inbox + processed，与上面同事务
            if message_row is None:
                await db.execute(
                    """INSERT INTO code_review_messages
                       (message_id, profile_session_id, message_type, direction, sender_id, receiver_id,
                        correlation_id, causation_id, external_run_id, external_attempt_id,
                        assignment_epoch, payload_digest, envelope_json, projection_digest,
                        state, receipts_json, created_at, updated_at)
                       VALUES (?, ?, ?, 'inbound', ?, ?, ?, ?, ?, ?, ?, '', ?, ?, 'processed', ?, ?, ?)""",
                    (
                        message_id,
                        profile_session_id,
                        envelope.get("type", ""),
                        envelope.get("sender_id", ""),
                        envelope.get("receiver_id", ""),
                        envelope.get("correlation_id", ""),
                        envelope.get("causation_id"),
                        envelope.get("run_id", ""),
                        envelope.get("attempt_id", ""),
                        envelope.get("assignment_epoch"),
                        json.dumps(envelope, ensure_ascii=False, sort_keys=True),
                        projection,
                        json.dumps([receipt_envelope]),
                        now,
                        now,
                    ),
                )
                state = "created"
            else:
                await db.execute(
                    """UPDATE code_review_messages
                       SET state='processed', receipts_json=?, updated_at=?
                       WHERE message_id=?""",
                    (json.dumps([receipt_envelope]), now, message_id),
                )
                state = "replayed"
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    message = await get_message(message_id)
    assert message is not None
    return message, state, receipt_envelope


def _receipt_envelope_for_store(
    *,
    receipt_id: str,
    kind: str,
    issuer_id: str,
    subject_kind: str,
    subject_id: str,
    decision: str,
    external_run_id: str,
    external_attempt_id: Optional[str],
    report_digest: Optional[str],
    authority_ref: str,
    reason_code: str,
    evidence_refs: List[Any],
    created_at: float,
    envelope: Dict[str, Any],
) -> Dict[str, Any]:
    """构造 Profile ``receipt`` 信封（与路由器同一形状；存库便于 MessageView 直接返回）。"""
    payload: Dict[str, Any] = {
        "schema": "code_review.receipt.v1",
        "receipt_id": receipt_id,
        "kind": kind,
        "issuer_id": issuer_id,
        "subject_ref": {"kind": subject_kind, "id": subject_id},
        "run_id": external_run_id,
        "attempt_id": external_attempt_id,
        "decision": decision,
        "created_at": _iso_utc(created_at),
        "authority_ref": authority_ref,
        "evidence_refs": list(evidence_refs or []),
    }
    if report_digest:
        payload["report_digest"] = report_digest
    if reason_code:
        payload["reason_code"] = reason_code
    return {
        "profile": PROFILE_MESSAGE_PROFILE_VERSION,
        "message_id": f"rcptmsg_{receipt_id}",
        "type": "receipt",
        "sender_id": issuer_id,
        "receiver_id": envelope.get("sender_id", ""),
        "session_id": envelope.get("session_id", ""),
        "correlation_id": envelope.get("correlation_id", ""),
        "causation_id": envelope.get("message_id", ""),
        "created_at": _iso_utc(created_at),
        "run_id": external_run_id,
        "attempt_id": external_attempt_id,
        "payload": payload,
    }


def _iso_utc(ts: float) -> str:
    import datetime as _dt

    return (
        _dt.datetime.fromtimestamp(float(ts), tz=_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )



# ── 评审 B6：消息 + 回执 + 完成状态原子化、可重启补偿 ─────────────────


async def store_message_with_receipt(
    message_id: str,
    *,
    envelope: Dict[str, Any],
    profile_session_id: str = "",
    direction: str = "inbound",
    payload_digest: str = "",
    receipt: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], str]:
    """在**一个事务**内落消息、（可选）落回执并把状态推进到 processed。

    原实现先提交 ``store_message``，再单独写回执：中途崩溃会留下 ``stored`` 且
    ``receipts=[]`` 的消息，而重放因为状态已不是 ``created`` 而**永远跳过处理**
    （评审 B6 复现：500 → 重试 202 → stored/[]）。这里把三步放进同一事务，
    要么全成功，要么全不生效，于是重放能安全地重新处理。
    """
    projection = projection_digest(message_projection(envelope))
    existing = await get_message(message_id)
    if existing:
        # 评审 R3-4：按业务投影比较（§7），只改追踪字段的重放必须被接受
        if existing["projection_digest"] != projection:
            raise ProfileError(
                "idempotency_conflict",
                f"message_id {message_id} 已存在且业务投影不同",
                scope="message",
            )
        if existing["state"] == "processed":
            return existing, "replayed"

    now = time.time()
    final_state = "processed" if receipt is not None else "stored"
    receipts_json = json.dumps([receipt]) if receipt is not None else None
    async with connect() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            if existing is None:
                await db.execute(
                    """INSERT INTO code_review_messages
                       (message_id, profile_session_id, message_type, direction, sender_id, receiver_id,
                        correlation_id, causation_id, external_run_id, external_attempt_id,
                        assignment_epoch, payload_digest, envelope_json, projection_digest,
                        state, receipts_json, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        message_id,
                        profile_session_id,
                        envelope.get("type", ""),
                        direction,
                        envelope.get("sender_id", ""),
                        envelope.get("receiver_id", ""),
                        envelope.get("correlation_id", ""),
                        envelope.get("causation_id"),
                        envelope.get("run_id", ""),
                        envelope.get("attempt_id", ""),
                        envelope.get("assignment_epoch"),
                        payload_digest,
                        json.dumps(envelope, ensure_ascii=False, sort_keys=True),
                        projection,
                        final_state,
                        receipts_json,
                        now,
                        now,
                    ),
                )
            else:
                await db.execute(
                    """UPDATE code_review_messages
                       SET state=?, receipts_json=COALESCE(?, receipts_json), updated_at=?
                       WHERE message_id=?""",
                    (final_state, receipts_json, now, message_id),
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    message = await get_message(message_id)
    assert message is not None
    return message, ("replayed" if existing is not None else "created")


async def list_unprocessed_messages(message_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """列出仍为 ``stored`` 的消息——重启后可补偿处理的集合（B6）。"""
    sql = f"{_MESSAGE_SELECT} WHERE state='stored'"
    params: tuple = ()
    if message_type:
        sql += " AND message_type=?"
        params = (message_type,)
    sql += " ORDER BY created_at"
    async with connect() as db:
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [_message_row(row) for row in rows]

