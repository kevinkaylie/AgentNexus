"""Code Review Collaboration Profile v1 —— AgentNexus 侧 L0 服务接口（binding RC2 §4）。

端点（``/coordination/code-review/v1`` 简写为 A）：

- ``POST A/messages``            入站协作消息 → 202 TransportAck（先持久化再 ACK）
- ``GET  A/messages/{message_id}``  MessageView（含异步回执与错误）
- ``POST A/artifacts``           产物上传 → 201 ArtifactRef（服务端计算摘要）
- ``GET  A/artifacts/{id}/raw``  原始字节（ETag/Content-Length，读取上限）

本模块在 2026-09-21 代码评审后按 B1–B7 重写，关键设计：

- **独立服务凭据（B1/B2）**：不再用 Daemon token + 信封 ``sender_id`` 判断身份。
  ``Authorization: Bearer`` → 登记在册的 principal（角色、可代表 DID、允许的
  instance/project/session）；未登记任何凭据一律拒绝。``sender_id``/``issuer_id``/
  ``producer_id`` 必须落在 principal 可代表范围内，不得自报。
- **资源级授权（B2）**：读取消息/产物必须命中 principal 的 session 范围；产物还要核
  保留期（过期 → 410 ``artifact_expired``），不再"知道 ID 就能读"。
- **冻结 schema 校验（B5）**：接收前用 ``envelope.schema.json`` 校验信封**及其按 type 的
  payload``（含 assignment 的 enforcement_requirements），产物引用用
  ``artifact_ref.schema.json`` 校验后再返回。
- **上传契约与不可变（B3/B4）**：只接受契约七字段 DTO；``retention_until`` 严格解析、
  持久化并原样返回；Vault key 以内容摘要寻址，失败请求不会覆盖已登记字节；
  幂等按 ``(principal, Idempotency-Key)`` 映射到原 artifact_id。
- **原子入站与可重启补偿（B6）**：消息、回执、完成状态在同一事务提交；``GET`` 时对
  仍为 ``stored`` 的回执消息做一次可重放补偿。

角色要求（§15.7）：本部署登记了角色时按角色硬校验；**未登记任何角色**时降级为
"部署约定"（``declared_only``）——允许写入但不得声称强制隔离，也不得运行符合性
授权测试（CP-24）。凭据登记与角色登记是两件事：前者决定"你是谁"（必须存在），
后者决定"本部署是否声称强制隔离"。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response

from agent_net.code_review import (
    PROFILE_VERSION,
    DigestError,
    ProfileError,
    ServicePrincipal,
    artifact_body_bytes,
    artifact_projection,
    error_envelope,
    parse_envelope,
    parse_strict_json,
    projection_digest,
    report_digest,
)
from agent_net.code_review import frozen
from agent_net.code_review.errors import read_limit_error
from agent_net.code_review.service_auth import (
    READ_ROLES,
    parse_bearer,
    require_receipt_authority,
)

from agent_net.persistence.code_review_store import (
    commit_artifact_with_idempotency,
    create_profile_receipt,
    get_message,
    list_unprocessed_messages,
    register_service_principal,
    reserve_artifact_idempotency,
    resolve_assignment_binding,
    resolve_profile_session,
    resolve_roles,
    resolve_service_principal,
    roles_configured,
    service_principals_configured,
    set_message_state,
    store_message_with_receipt,
    store_receipt_message,
    unsupported_requirements,
)
from agent_net.persistence.deliverable_store import get_artifact
from agent_net.persistence.enclave import vault_put
from agent_net.persistence.session_store import get_coordination_session

router = APIRouter()

PREFIX = "/coordination/code-review/v1"

#: 本端点接受的入站消息类型（其余类型明确不支持：返回 unsupported_capability）
INBOUND_TYPES = ("assignment", "cancel_request", "receipt", "error")

#: 入站类型 → 所需角色
REQUIRED_ROLE_BY_TYPE: Dict[str, str] = {
    "assignment": "coordinator",
    "cancel_request": "coordinator",
    "error": "coordinator",
}

#: 本部署对产物保留期的承诺（秒）；超出即 422 data_policy_denied（RC2 §4）
DEFAULT_RETENTION_COMMITMENT_SEC = 180 * 24 * 3600

#: 允许上传产物的执行状态（与 code_review_store 保持一致；终态/取消一律拒绝）
_SUBMITTABLE_EXECUTION_STATES = ("pending", "running")

#: 契约 §4 规定的上传 DTO 字段集合（**唯一**允许的字段；其余一律拒绝，评审 B3）
ARTIFACT_UPLOAD_FIELDS = (
    "run_id",
    "attempt_id",
    "assignment_epoch",
    "artifact_body",
    "media_type",
    "schema_version",
    "retention_until",
)

#: ArtifactRef 响应字段（与冻结 artifact_ref.schema.json 对齐；**不含** enforcement，
#: 该字段曾被多返回并使 HCZJ 严格校验拒绝，评审 B3）
ARTIFACT_REF_FIELDS = (
    "artifact_id",
    "producer_id",
    "media_type",
    "schema_version",
    "digest_algorithm",
    "digest",
    "byte_length",
    "locator",
    "access_scope",
    "retention_until",
    "replaces",
)


# ── 错误信封 ──────────────────────────────────────────────────────────


def register_error_handler(app) -> None:
    """把 :class:`ProfileError` 映射为 ``code_review.error.v1`` 响应。

    只影响显式抛出 ProfileError 的新接口；既有路由仍使用原来的
    ``{"detail": ...}`` 语义，避免改变非 Profile 路径。

    同时为本 Profile 前缀的**所有**响应补 ``Cache-Control: no-store``（RC2 §1：
    "所有响应 Cache-Control: no-store"）——FastAPI 不会自动加，因此在中间件里按前缀限定。
    """

    @app.exception_handler(ProfileError)
    async def _handle(request: Request, exc: ProfileError):  # pragma: no cover - 集成路径
        # 冻结 error.schema.json 要求 correlation_id **非空**（minLength 1）。若错误发生在
        # 取到 correlation id 之前（或调用方没给头），就地补一个服务端生成的 id 并回显为
        # 响应头，否则响应体不是合法的 code_review.error.v1 —— HTTP 契约矩阵正是这样
        # 一次性抓出 20 多处"字段存在但不合法"的响应（复审遗留的 wire 不一致类问题）。
        envelope = error_envelope(exc)
        if not envelope.get("correlation_id"):
            envelope["correlation_id"] = (
                request.headers.get("X-Correlation-Id") or f"corr-srv-{uuid.uuid4().hex[:16]}"
            )
        headers = {"X-Correlation-Id": envelope["correlation_id"], "Cache-Control": "no-store"}
        return JSONResponse(
            status_code=exc.http_status, content=envelope, headers=headers
        )

    @app.middleware("http")
    async def _profile_transport_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(PREFIX):
            response.headers["Cache-Control"] = "no-store"
            # RC2 §1：**除原始字节读取外**均为 application/json; charset=utf-8。
            # raw 端点必须原样返回其 media_type（不做任何改写）。
            content_type = response.headers.get("Content-Type", "")
            if (
                content_type.startswith("application/json")
                and "charset" not in content_type.lower()
                and not request.url.path.endswith("/raw")
            ):
                response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response


def _correlation_id(*candidates: Optional[str]) -> str:
    for value in candidates:
        if value:
            return value
    return ""


def _require_correlation_header(header: Optional[str]) -> str:
    """RC2 §1：**新增接口必带** ``X-Correlation-Id``；缺失即拒绝。

    上一版只在"头与信封不一致"时报错，头缺失时静默用信封值，等于没有强制该头。
    """
    if not header or not header.strip():
        raise ProfileError(
            "invalid_output",
            "新增接口必须携带 X-Correlation-Id（RC2 §1）",
            scope="envelope",
        )
    return header.strip()


def _iso(ts: float) -> str:
    """float 时间戳 → RFC3339 Z（冻结 schema 要求的时间口径）。"""
    return (
        _dt.datetime.fromtimestamp(float(ts), tz=_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_iso(value: str) -> float:
    """严格解析 RFC3339 Z；失败抛 ``invalid_output``（不接受数字时间戳，评审 B3）。"""
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProfileError(
            "invalid_output",
            "retention_until 必须是 RFC3339 UTC 字符串（以 Z 结尾）",
            scope="artifact",
        )
    try:
        parsed = _dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProfileError(
            "invalid_output", f"retention_until 不是合法 RFC3339 时间：{value}", scope="artifact"
        ) from exc
    return parsed.timestamp()


# ── 服务凭据与主体（B1） ──────────────────────────────────────────────


async def require_service_principal(
    authorization: Optional[str] = Header(None),
) -> ServicePrincipal:
    """认证依赖：Bearer → 登记 principal。**缺配置即拒绝**（RC2 §1）。

    这里刻意不复用 ``_require_token``：Daemon token 是单机管理凭据，只要 token 对就能
    访问，无法绑定主体与资源范围（评审 B1 的冒充正是由此而来）。
    """
    if not await service_principals_configured():
        raise ProfileError(
            "authority_denied",
            "本部署未登记任何 Profile 服务凭据，拒绝所有服务接口调用"
            "（不得沿用『未配置则放行』，RC2 §1）",
            scope="authorization",
            http_status=401,
        )
    credential = parse_bearer(authorization)
    row = await resolve_service_principal(credential)
    if row is None:
        raise ProfileError(
            "authority_denied", "服务凭据无效", scope="authorization", http_status=401
        )
    return ServicePrincipal.from_row(row)


async def _enforcement_level(principal: ServicePrincipal, role: str) -> str:
    """角色授权：有角色表则硬校验（enforced），否则声明为部署约定（declared_only）。

    凭据登记（``code_review_service_principals``）与角色登记（``code_review_role_grants``）
    是两件事：前者必须存在，否则请求已被 ``require_service_principal`` 拒绝；后者决定
    本部署是否声称"强制隔离"。两者都登记时按角色硬校验。
    """
    if not await roles_configured():
        return "declared_only"
    roles = await resolve_roles(principal.principal_id)
    if role not in roles:
        raise ProfileError(
            "authority_denied",
            f"主体 {principal.principal_id} 不具备所需角色 {role}",
            scope="authorization",
        )
    return "enforced"


async def _authorize(
    principal: ServicePrincipal,
    *,
    role: str,
    profile_session_id: str = "",
    instance_id: str = "",
    project_id: str = "",
) -> str:
    """角色 + 资源授权；返回强制级别。"""
    principal.require_role(role)
    principal.require_resource(
        profile_session_id=profile_session_id,
        instance_id=instance_id,
        project_id=project_id,
    )
    return await _enforcement_level(principal, role)


# ── 视图 ──────────────────────────────────────────────────────────────


def _message_view(message: Dict[str, Any]) -> Dict[str, Any]:
    """MessageView（RC2 §4）：**只**这四个字段，receipts 为 Profile receipt 信封。"""
    return {
        "message_id": message["message_id"],
        "state": message["state"],
        "receipts": list(message.get("receipts") or []),
        "error": message.get("error"),
    }


def _receipt_envelope(
    record: Dict[str, Any],
    *,
    envelope: Dict[str, Any],
    receiver_id: str,
) -> Dict[str, Any]:
    """把内部回执记录包装为 Profile ``receipt`` 信封（RC2 §4 要求 invoices 是信封）。"""
    payload: Dict[str, Any] = {
        "schema": "code_review.receipt.v1",
        "receipt_id": record["receipt_id"],
        "kind": record["kind"],
        "issuer_id": record["issuer_id"],
        "subject_ref": record["subject_ref"],
        "run_id": record["run_id"] or envelope.get("run_id", ""),
        "attempt_id": record["attempt_id"],
        "decision": record["decision"],
        "created_at": _iso(record["created_at"]),
        "authority_ref": record["authority_ref"],
        "evidence_refs": record["evidence_refs"],
    }
    if record.get("report_digest"):
        payload["report_digest"] = record["report_digest"]
    if record.get("reason_code"):
        payload["reason_code"] = record["reason_code"]

    return {
        "profile": PROFILE_VERSION,
        "message_id": f"rcptmsg_{record['receipt_id']}",
        "type": "receipt",
        "sender_id": record["issuer_id"],
        "receiver_id": receiver_id or envelope.get("sender_id", ""),
        "session_id": envelope.get("session_id", ""),
        "correlation_id": envelope.get("correlation_id", ""),
        "causation_id": envelope.get("message_id", ""),
        "created_at": _iso(record["created_at"]),
        "run_id": payload["run_id"],
        "attempt_id": record["attempt_id"],
        "payload": payload,
    }


def _require_consistent_ids(envelope: Dict[str, Any]) -> None:
    """信封与 payload 的关联 ID 必须一致（评审 B5 的"双方关联 ID"核验）。

    冻结 schema 分别约束了两侧的**存在性**，但不比较取值；若不一致，后续以哪一侧为准都会
    产生歧义（例如信封 run_id 与 payload run_id 指向不同 Run）。
    """
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return
    for field in ("run_id", "attempt_id", "assignment_epoch"):
        if field not in payload or field not in envelope:
            continue
        if envelope[field] != payload[field]:
            raise ProfileError(
                "input_mismatch",
                f"信封 {field} 与 payload {field} 不一致",
                scope="envelope",
            )


def declared_enforcement_requirements(payload: Dict[str, Any]) -> Dict[str, str]:
    """从 Assignment payload 提取 ``{constraint: level}``（§15.5）。"""
    requirements = payload.get("enforcement_requirements")
    if not isinstance(requirements, list) or not requirements:
        # 评审 B5：缺省为空数组曾被当成"无要求"从而放行未冻结的任务，这里必须拒绝。
        raise ProfileError(
            "invalid_output",
            "assignment 必须显式声明 enforcement_requirements（不得缺省绕过约束）",
            scope="assignment",
        )
    declared: Dict[str, str] = {}
    for item in requirements:
        if not isinstance(item, dict) or not item.get("constraint") or not item.get("level"):
            raise ProfileError(
                "invalid_output",
                "enforcement_requirements 每项必须含 constraint 与 level",
                scope="assignment",
            )
        declared[str(item["constraint"])] = str(item["level"])
    return declared


# ── POST A/messages ───────────────────────────────────────────────────


@router.post(PREFIX + "/messages", status_code=202)
async def api_receive_message(
    request: Request,
    x_correlation_id: Optional[str] = Header(None),
    idempotency_key: Optional[str] = Header(None),
    principal: ServicePrincipal = Depends(require_service_principal),
):
    """接收入站协作消息：先持久化，再返回 TransportAck（**不是** Profile Receipt）。"""
    correlation_id = _require_correlation_header(x_correlation_id)
    # §1 + §4（2026-09-22 评审裁决）：A/messages 的幂等键**必须**通过 Idempotency-Key 头
    # 传递，取值**必须等于** envelope.message_id —— 两者是同一个逻辑幂等键，不分别建记录。
    # 缺少/空头 → 422 input_mismatch（在解析正文前先拒绝，属传输层要求）；值不一致 →
    # 解析后 409 idempotency_conflict。两种情况都不得写入。
    if idempotency_key is None or not idempotency_key.strip():
        raise ProfileError(
            "input_mismatch",
            "POST A/messages 必须携带 Idempotency-Key，且取值等于信封 message_id（RC2 §1/§4）",
            scope="message",
            correlation_id=correlation_id,
        )
    idempotency_key = idempotency_key.strip()

    raw = await request.body()
    if len(raw) > 4 * 1024 * 1024:
        raise read_limit_error("json_response_max_bytes", len(raw), correlation_id)

    envelope = parse_envelope(raw)
    if envelope.get("correlation_id") != correlation_id:
        raise ProfileError(
            "invalid_output",
            "信封 correlation_id 必须与 X-Correlation-Id 头一致（RC2 §1）",
            scope="envelope",
            correlation_id=correlation_id,
        )

    if idempotency_key != envelope["message_id"]:
        raise ProfileError(
            "idempotency_conflict",
            "Idempotency-Key 必须等于信封 message_id（同一逻辑幂等键，RC2 §1/§4）",
            scope="message",
            correlation_id=correlation_id,
        )

    # 先判定本适配层是否支持该类型，再对支持的类型的 payload 做冻结 schema 校验。
    msg_type = envelope["type"]
    if msg_type not in INBOUND_TYPES:
        raise ProfileError(
            "unsupported_capability",
            f"本适配层不支持入站消息类型 {msg_type}（支持：{','.join(INBOUND_TYPES)}）",
            scope="message_routing",
            correlation_id=correlation_id,
        )

    # B5：用冻结 schema 校验信封**及其 payload**（含按 type 的必需信封字段）。
    frozen.validate_envelope(envelope)
    _require_consistent_ids(envelope)

    # B1：sender 必须由认证主体代表，不得自报。
    actor_did = principal.require_bound_did(envelope.get("sender_id", ""), what="信封 sender_id")

    # ── R3-1：未知/歧义资源**不得**被当成放行条件 ─────────────────────────
    # 上一版在查不到 session 时把空字符串交给 require_resource；而后者在"目标为空但凭据
    # 登记了任意资源范围"时不拒绝，于是未授权 session 的合法回执被 202 并持久化。
    # 现在：session 必须解析到**唯一**已登记 Profile 会话，否则一律拒绝——"查不到"不是许可。
    session_id = envelope.get("session_id") or ""
    if not session_id:
        raise ProfileError(
            "input_mismatch",
            "入站消息必须携带 session_id（RC2 §3）",
            scope="message",
            correlation_id=correlation_id,
        )
    session_state, profile_session = await resolve_profile_session(
        coordination_session_id=session_id
    )
    if session_state == "ambiguous":
        raise ProfileError(
            "idempotency_conflict",
            "该 session_id 对应多条 Profile 会话，无法判定唯一权威，拒绝处理",
            scope="message",
            correlation_id=correlation_id,
        )
    if session_state == "not_found":
        raise ProfileError(
            "stale_assignment",
            f"未登记的 Session/Run：{session_id}。新 Run 必须先经受信任的部署初始化流程建立"
            "绑定，本端点不接受以“查不到”作为创建或放行条件（RC2 §4）",
            scope="message",
            correlation_id=correlation_id,
        )
    assert profile_session is not None
    profile_session_id = profile_session["profile_session_id"]

    # R3-1（续）：session 与 Run 的**受信任关联**必须自洽——信封声明的 run_id 必须等于该
    # session 已绑定的 external_run_id，否则这条消息在引用另一个 Run 的资源。
    declared_run = envelope.get("run_id") or ""
    bound_run = profile_session.get("external_run_id") or ""
    if declared_run and bound_run and declared_run != bound_run:
        raise ProfileError(
            "stale_assignment",
            f"信封 run_id（{declared_run}）与该 Session 绑定的 Run（{bound_run}）不一致",
            scope="message",
            correlation_id=correlation_id,
        )

    if msg_type == "receipt":
        payload = envelope.get("payload") or {}
        kind = payload.get("kind", "")
        # R2-4：必需角色必须来自 kind 映射本身。上一版把 required_role 置 None 后又用
        # `required_role or "coordinator"` 求强制级别，导致合法的 validator / publisher
        # 也被要求 coordinator（复现：403「不具备所需角色 coordinator」）。
        required_role = require_receipt_authority(
            principal, kind, payload.get("issuer_id", "")
        )
    else:
        required_role = REQUIRED_ROLE_BY_TYPE.get(msg_type, "coordinator")
        if msg_type == "assignment":
            # §1：external_coordinator_id 取已认证 Coordinator，不取 worker 自报值。
            # assignment 的 coordinator_id 必须由认证主体代表，否则同名 Run 的归属无从判定。
            payload = envelope.get("payload") or {}
            principal.require_bound_did(
                payload.get("coordinator_id", ""), what="assignment.coordinator_id"
            )

    principal.require_role(required_role)
    principal.require_session(profile_session_id)
    enforcement = await _enforcement_level(principal, required_role)

    # B6 / R2-3：回执、inbox 与 processed **同一事务**提交；幂等投影先在事务内校验，
    # 冲突时不留下任何业务记录。
    if msg_type == "receipt":
        payload = envelope.get("payload") or {}
        message, state, receipt_envelope = await store_receipt_message(
            envelope["message_id"],
            envelope=envelope,
            profile_session_id=profile_session_id,
            receipt_id=payload.get("receipt_id") or f"rcpt_{uuid.uuid4().hex[:16]}",
            kind=payload.get("kind", ""),
            issuer_id=payload.get("issuer_id", actor_did),
            subject_kind=(payload.get("subject_ref") or {}).get("kind", "delivery"),
            subject_id=(payload.get("subject_ref") or {}).get("id", ""),
            decision=payload.get("decision", "confirmed"),
            external_run_id=envelope.get("run_id", "") or "",
            external_attempt_id=payload.get("attempt_id") or envelope.get("attempt_id"),
            report_digest=payload.get("report_digest"),
            authority_ref=payload.get("authority_ref", ""),
            reason_code=payload.get("reason_code", ""),
            evidence_refs=payload.get("evidence_refs") or [],
            enforcement=enforcement,
        )
        frozen.validate_envelope(receipt_envelope)
    else:
        message, state = await store_message_with_receipt(
            envelope["message_id"],
            envelope=envelope,
            profile_session_id=profile_session_id,
        )

    # §15.5：接单阶段按强制能力注册 fail-closed。未真正强制的必需约束一律拒绝，
    # 且**不启动任何模型调用**（CP-25）。重放同样复核，保证同一消息的结果一致
    # （否则调用方会从 202 误判为已接单）。
    if msg_type == "assignment" and (message or {}).get("state") != "processed":
        declared = declared_enforcement_requirements(envelope.get("payload") or {})
        missing = await unsupported_requirements(declared)
        if missing:
            error = ProfileError(
                "enforcement_unavailable",
                f"本部署无法强制以下必需能力：{','.join(missing)}",
                scope="enforcement",
                correlation_id=correlation_id,
                # 细节必须放 extensions：error.schema.json 是 additionalProperties:false
                extra={"extensions": {"unsatisfied": missing, "declared": declared}},
            )
            await set_message_state(
                envelope["message_id"], "rejected", error=error_envelope(error)
            )
            raise error
        if (message or {}).get("state") == "rejected":
            # 能力已补齐：恢复为已存储，允许后续处理
            await set_message_state(envelope["message_id"], "stored", error=None)

    # TransportAck 严格三字段（RC2 §4）；重放与 enforcement 不再额外回显，避免 DTO 漂移。
    return {
        "message_id": envelope["message_id"],
        "status": "stored",
        "status_url": f"{PREFIX}/messages/{envelope['message_id']}",
    }


# ── GET A/messages/{message_id} ───────────────────────────────────────


@router.get(PREFIX + "/messages/{message_id}")
async def api_get_message(
    message_id: str,
    x_correlation_id: Optional[str] = Header(None),
    principal: ServicePrincipal = Depends(require_service_principal),
):
    """MessageView：查询成功返回 200，业务失败体现在 ``error`` 字段（RC2 §7）。"""
    _require_correlation_header(x_correlation_id)
    message = await get_message(message_id)
    if message is None:
        raise ProfileError("input_mismatch", f"消息不存在：{message_id}", scope="message")

    # B2 / R2-2：当事人身份**不能**免除 session 范围限制。
    # 上一版 `if not is_party:` 让任何当事人 DID 直接读到消息，同一个 DID 在多个 session
    # 使用时凭据的 session 限制形同虚设。
    is_party = message["sender_id"] in principal.dids or message["receiver_id"] in principal.dids
    if message["profile_session_id"]:
        principal.require_session(message["profile_session_id"])
    if not is_party:
        principal.require_any_role(READ_ROLES)
    elif not message["profile_session_id"] and not (principal.sessions or principal.instances or principal.projects):
        raise ProfileError(
            "authority_denied",
            f"主体 {principal.principal_id} 未登记任何资源范围，拒绝读取未绑定 session 的消息",
            scope="authorization",
        )

    # B6：补偿——回执消息若因上次崩溃停在 stored，这里在同一条可重放路径上完成处理。
    if message["state"] == "stored" and message["message_type"] == "receipt" and not message["receipts"]:
        await _complete_pending_receipt(message)

    refreshed = await get_message(message_id)
    return _message_view(refreshed or message)


async def _complete_pending_receipt(message: Dict[str, Any]) -> None:
    """把停在 ``stored`` 的回执消息补完（inbox 已提交、回执未写的崩溃窗口）。"""
    envelope = message["envelope"]
    payload = envelope.get("payload") or {}
    kind = payload.get("kind", "")
    receipt = await create_profile_receipt(
        payload.get("receipt_id") or f"rcpt_{uuid.uuid4().hex[:16]}",
        profile_session_id=message["profile_session_id"],
        kind=kind,
        decision=payload.get("decision", "confirmed"),
        issuer_id=payload.get("issuer_id", envelope.get("sender_id", "")),
        subject_kind=(payload.get("subject_ref") or {}).get("kind", "delivery"),
        subject_id=(payload.get("subject_ref") or {}).get("id", ""),
        external_run_id=envelope.get("run_id", "") or "",
        external_attempt_id=envelope.get("attempt_id"),
        report_digest=payload.get("report_digest"),
        authority_ref=payload.get("authority_ref", ""),
        reason_code=payload.get("reason_code", ""),
        evidence_refs=payload.get("evidence_refs") or [],
        enforcement="declared_only",
    )
    receipt_envelope = _receipt_envelope(
        receipt, envelope=envelope, receiver_id=envelope.get("sender_id", "")
    )
    frozen.validate_envelope(receipt_envelope)
    await set_message_state(message["message_id"], "processed", receipts=[receipt_envelope])


async def reprocess_pending_messages() -> int:
    """启动/巡检用：把未处理的回执消息补完，返回处理条数（B6 可重启消费者）。"""
    processed = 0
    for message in await list_unprocessed_messages():
        if message["message_type"] != "receipt" or message["receipts"]:
            continue
        await _complete_pending_receipt(message)
        processed += 1
    return processed


# ── POST A/artifacts ──────────────────────────────────────────────────


@router.post(PREFIX + "/artifacts", status_code=201)
async def api_submit_artifact(
    request: Request,
    x_correlation_id: Optional[str] = Header(None),
    idempotency_key: Optional[str] = Header(None),
    x_actor_did: Optional[str] = Header(None),
    principal: ServicePrincipal = Depends(require_service_principal),
):
    """上传产物：服务端计算摘要（§15.3），不接受调用方自报摘要（RC2 §4）。"""
    correlation_id = _require_correlation_header(x_correlation_id)
    raw = await request.body()
    if len(raw) > 16 * 1024 * 1024:
        raise read_limit_error("artifact_max_bytes", len(raw), correlation_id)

    # 复审遗留 P2：上传也必须遵守 §3 的严格 JSON——拒绝重复键、NaN/Infinity 与 BOM，
    # 不能只在信封路径严格。
    body = parse_strict_json(raw, scope="artifact")
    if not isinstance(body, dict):
        raise ProfileError("invalid_output", "请求体必须是 JSON 对象", scope="artifact")

    # B3：只接受契约 DTO 七字段；producer_id/actor_did/artifact_id 等一律拒绝。
    unknown = sorted(set(body) - set(ARTIFACT_UPLOAD_FIELDS))
    if unknown:
        raise ProfileError(
            "invalid_output",
            f"上传 DTO 只接受契约字段 {list(ARTIFACT_UPLOAD_FIELDS)}，收到未声明字段：{unknown}",
            scope="artifact",
        )
    for field in ("run_id", "attempt_id", "assignment_epoch", "artifact_body", "media_type", "schema_version"):
        if body.get(field) in (None, ""):
            raise ProfileError("invalid_output", f"缺少必填字段 {field}", scope="artifact")

    artifact_body = body["artifact_body"]
    try:
        artifact_body_bytes(artifact_body)  # 严格 UTF-8 校验（拒绝 BOM/孤立 surrogate）
        digest, byte_length = report_digest(artifact_body)
    except DigestError as exc:
        raise ProfileError("invalid_output", str(exc), scope="artifact") from exc

    # B3：保留期必须严格解析并使用字符串时间，不得静默置 null。
    if "retention_until" not in body:
        raise ProfileError(
            "data_policy_denied",
            "上传必须声明 retention_until；本部署无法在未声明时承诺保留期",
            scope="retention",
            http_status=422,
        )
    retention_ts = _parse_iso(body["retention_until"])
    server_commitment = time.time() + DEFAULT_RETENTION_COMMITMENT_SEC
    if retention_ts > server_commitment:
        raise ProfileError(
            "data_policy_denied",
            "无法承诺所请求的保留期",
            scope="retention",
            # RC2 §4 规定保留期拒绝为 422；同一 code 的授权场景为 403（RC2 §7），
            # 因此这里显式指定状态码，并由 scope 区分原因（评审 R2-2）。
            http_status=422,
        )

    # B3：producer 由认证主体决定，不从请求体读取。
    producer_did = principal.acting_did(x_actor_did)
    principal.require_role("worker")

    # ── B2 / R2-2 / R3-2：上传必须绑定**真实**分配 ─────────────────────────
    # 上一版只按 external_run_id 查 session，查不到就得到空 session，随后
    # require_resource 在"目标 session 为空且凭据登记了任意范围"时放行——于是
    # unregistered-run / unassigned-attempt / epoch=999 都能 201（评审 R2-2 复现）。
    session_state, profile_session = await resolve_profile_session(
        external_run_id=body["run_id"]
    )
    if session_state == "ambiguous":
        raise ProfileError(
            "idempotency_conflict",
            "该 Run 对应多个 Coordinator 的同名会话，无法判定唯一权威，拒绝上传",
            scope="artifact",
        )
    if session_state == "not_found":
        raise ProfileError(
            "input_mismatch",
            f"未知 Run：{body['run_id']}（不得用未登记的 Run 上传产物）",
            scope="artifact",
        )
    assert profile_session is not None
    profile_session_id = profile_session["profile_session_id"]
    principal.require_session(profile_session_id)

    # assignment_epoch 必须是**严格整数**（bool/小数/字符串都是格式错误）。
    epoch = _strict_positive_int(body["assignment_epoch"], field="assignment_epoch")

    binding_state, binding = await resolve_assignment_binding(
        profile_session_id=profile_session_id,
        external_run_id=body["run_id"],
        external_attempt_id=body["attempt_id"],
    )
    if binding_state == "unknown_run":
        raise ProfileError(
            "stale_assignment",
            "该 Attempt 未被分配（run_id/attempt_id 不构成已登记分配）",
            scope="artifact",
        )
    if binding_state == "ambiguous":
        raise ProfileError(
            "stale_assignment",
            "该 (run, attempt) 对应多条分配，无法判定唯一 Coordinator，拒绝上传",
            scope="artifact",
        )
    assert binding is not None
    # 这些检查是**快速失败**，真正的围栏在 commit_artifact_with_idempotency 的事务内
    # 重新读取并复检（评审 R3-2：提前查询不构成取消/epoch/deadline 的原子围栏）。
    if epoch != int(binding["assignment_epoch"]):
        raise ProfileError(
            "stale_assignment",
            f"assignment_epoch 不是当前分配（请求 {epoch} / 当前 {binding['assignment_epoch']}）",
            scope="artifact",
        )
    if binding["status"] not in _SUBMITTABLE_EXECUTION_STATES:
        raise ProfileError(
            "stale_assignment",
            f"分配已不处于可提交状态（{binding['status']}）",
            scope="artifact",
        )
    if binding.get("lease_expires_at") is not None and float(binding["lease_expires_at"]) < time.time():
        raise ProfileError("stale_assignment", "分配租约已过期", scope="artifact")
    if binding["deadline"] and float(binding["deadline"]) < time.time():
        raise ProfileError("deadline_exceeded", "分配已超过 deadline", scope="artifact")
    # 第四轮复审：这里的比较**同样不得加真值守卫**。空的 Coordinator 不是"无需核对"，
    # 而是"无法证明该 Attempt 的 Coordinator 归属"——不能围栏的分配不得提交产物。
    if not (binding.get("external_coordinator_id") or ""):
        raise ProfileError(
            "stale_assignment",
            "该分配未绑定 Coordinator，无法证明归属，拒绝上传",
            scope="artifact",
        )
    if (binding.get("worker_did") or "") != producer_did:
        raise ProfileError(
            "authority_denied",
            f"认证主体 {producer_did} 不是该 Attempt 的已分配 worker"
            f"（当前 {binding.get('worker_did') or '空'}）",
            scope="authorization",
        )
    enforcement = await _enforcement_level(principal, "worker")

    # B4 / R3-4：幂等键是契约要求（RC2 §4）；**投影摘要**用于比较，不用 HTTP 原始字节
    # （否则仅改排版就会被判 delivery_conflict）。
    if not idempotency_key:
        raise ProfileError(
            "input_mismatch",
            "产物上传必须带 Idempotency-Key（否则无法区分重放与新建，RC2 §4）",
            scope="artifact",
        )
    projection = projection_digest(
        artifact_projection(body),
        namespace=(principal.principal_id, "artifact_upload", profile_session_id),
    )
    candidate_id = f"art_{uuid.uuid4().hex[:16]}"
    outcome, artifact_id = await reserve_artifact_idempotency(
        principal.principal_id,
        "artifact_upload",
        profile_session_id,
        idempotency_key,
        candidate_id,
        projection,
    )
    if outcome == "replayed":
        existing = await get_artifact(artifact_id)
        if existing is None:
            raise ProfileError(
                "delivery_conflict",
                "幂等映射指向的产物不存在，拒绝伪造重放",
                scope="artifact",
            )
        return _artifact_ref(existing, producer_did, body)

    session_id = (profile_session or {}).get("coordination_session_id", "")
    enclave_id = "default"
    if session_id:
        local_session = await get_coordination_session(session_id)
        if local_session:
            enclave_id = local_session.get("enclave_id") or "default"

    # B4：Vault key 以内容摘要寻址 → 同一 locator 不可能出现不同字节；
    # 失败请求也不会覆盖已登记产物的原始字节。
    digest_hex = digest.split(":", 1)[1]
    locator_key = f"code-review/{profile_session_id}/{digest_hex}.body"
    try:
        await vault_put(enclave_id, locator_key, artifact_body, producer_did)
    except Exception as exc:  # §15.3/RC2 §4：存储失败必须失败，不得截断正文冒充成功
        # 幂等预留保持 pending：同 key 重试可续用同一 artifact_id（评审 R2-1）
        raise ProfileError(
            "temporarily_unavailable",
            f"产物存储失败，未登记 artifact：{exc}",
            scope="artifact_storage",
            retryable=True,
        ) from exc

    # R2-1 / R3-2 / R3-3：提交事务内**复检分配**并把产物登记与幂等置 committed 一起提交；
    # 同命名空间同键已 committed 时直接返回原产物（并发同 key 不再以主键冲突收场）。
    outcome, record = await commit_artifact_with_idempotency(
        principal_id=principal.principal_id,
        action="artifact_upload",
        resource_scope=profile_session_id,
        idempotency_key=idempotency_key,
        artifact_id=artifact_id,
        coordination_session_id=session_id,
        profile_session_id=profile_session_id,
        run_id=body["run_id"],
        stage="code_review",
        artifact_type="CodeReviewReport",
        producer_did=producer_did,
        content_ref=f"vault://{enclave_id}/{locator_key}",
        content_hash=digest,
        schema_version=body["schema_version"],
        media_type=body["media_type"],
        byte_length=byte_length,
        access_scope="service_private",
        retention_until=retention_ts,
        retention_until_text=body["retention_until"],
        digest_algorithm="sha256-bytes-v1",
        assignment_execution_id=binding["execution_id"],
        # R3-2（P1）：身份元组必须整体带入事务复检——只比 epoch/worker 会漏掉
        # "上传期间改绑 Attempt 或 Coordinator"。
        expected_attempt_id=binding["external_attempt_id"],
        expected_coordinator_id=binding["external_coordinator_id"],
        expected_epoch=epoch,
        expected_worker_did=producer_did,
    )
    return _artifact_ref(record, producer_did, body)


def _strict_positive_int(value: Any, *, field: str) -> int:
    """严格正整数（评审保留建议）：拒绝 bool、小数与非数字字符串。

    上一版直接 ``int(value)``：``True`` → 1、``"3"`` → 3、``3.9`` → 3，都悄悄通过。
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProfileError(
            "invalid_output",
            f"{field} 必须是正整数（不接受布尔、小数或字符串），实际 {type(value).__name__}",
            scope="artifact",
        )
    if value < 1:
        raise ProfileError("invalid_output", f"{field} 必须 ≥ 1", scope="artifact")
    return value


def _artifact_ref(record: Dict[str, Any], producer_did: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """构造并校验 ArtifactRef（冻结 schema 校验后才返回，评审 B3）。

    评审 R2「协议边界」：`retention_until` 必须**原样**回显请求值——上一版把请求字符串
    解析成 float 后再反格式化成秒级 ISO，微秒被截断，因此不能声称"原样返回"。
    """
    retention_text = record.get("retention_until_text") or (
        body.get("retention_until") if isinstance(body.get("retention_until"), str) else ""
    )
    if not retention_text and record.get("retention_until"):
        retention_text = _iso(record["retention_until"])
    ref = {
        "artifact_id": record["artifact_id"],
        "producer_id": record.get("producer_did") or producer_did,
        "media_type": record.get("media_type") or body.get("media_type", "application/json"),
        "schema_version": record.get("schema_version") or body.get("schema_version", ""),
        "digest_algorithm": record.get("digest_algorithm") or "sha256-bytes-v1",
        "digest": record.get("content_hash") or "",
        "byte_length": record.get("byte_length") or 0,
        "locator": f"agentnexus-artifact:{record['artifact_id']}",
        "access_scope": record.get("access_scope") or "service_private",
        "retention_until": retention_text or None,
        "replaces": record.get("replaces"),
    }
    ref = {key: ref[key] for key in ARTIFACT_REF_FIELDS}
    frozen.validate_artifact_ref(ref)
    return ref


# ── GET A/artifacts/{artifact_id}/raw ─────────────────────────────────


@router.get(PREFIX + "/artifacts/{artifact_id}/raw")
async def api_get_artifact_raw(
    artifact_id: str,
    if_match: Optional[str] = Header(None),
    range_header: Optional[str] = Header(None, alias="Range"),
    x_correlation_id: Optional[str] = Header(None),
    principal: ServicePrincipal = Depends(require_service_principal),
):
    """原始字节读取：完整字节 + ETag；不做截断、不重序列化（RC2 §4/§10.1）。"""
    correlation_id = _require_correlation_header(x_correlation_id)

    # 复审遗留 P2：本端点不声明 Range 支持，必须**显式拒绝**而不是静默返回完整字节
    # （否则调用方会以为拿到的是部分内容）。
    if range_header:
        raise ProfileError(
            "invalid_output",
            "本端点不支持 Range 请求（RC2 §4 只定义完整原始字节读取）",
            scope="artifact_read",
            correlation_id=correlation_id,
        )

    artifact = await get_artifact(artifact_id)
    if artifact is None:
        raise ProfileError(
            "evidence_unavailable", f"产物不存在：{artifact_id}", scope="artifact_read",
            correlation_id=correlation_id,
        )

    # B2：资源授权 + 保留期。仅持服务凭据不足以读取他人 Run 的产物。
    # 同一 session/Run 的服务身份即可读（含该产物的 producer 本人）；
    # 跨 session 一律拒绝，不论角色。
    principal.require_session(artifact.get("profile_session_id") or "")
    producer = artifact.get("producer_did") or ""
    if not (principal.roles & READ_ROLES) and producer not in principal.dids:
        raise ProfileError(
            "authority_denied",
            f"主体 {principal.principal_id} 既无读取角色，也不是该产物的生产者",
            scope="authorization",
        )

    retention = artifact.get("retention_until")
    if retention and float(retention) < time.time():
        raise ProfileError(
            "artifact_expired",
            "产物已超过保留期",
            scope="artifact_read",
            correlation_id=correlation_id,
        )

    expected = artifact.get("content_hash") or ""
    if if_match and expected and if_match.strip('"') != expected:
        # RC2 §2 要求 If-Match 不匹配返回 **412**（不是 409；409 用于存储字节与登记摘要
        # 不一致这类真实冲突）。
        raise ProfileError(
            "evidence_digest_mismatch",
            "If-Match 摘要与已登记产物不一致",
            scope="artifact_read",
            correlation_id=correlation_id,
            http_status=412,
        )

    locator = artifact.get("content_ref") or ""
    if not locator.startswith("vault://"):
        raise ProfileError(
            "evidence_unavailable",
            "产物 locator 不可解析（非 vault 引用）",
            scope="artifact_read",
            correlation_id=correlation_id,
        )
    _, _, rest = locator.partition("vault://")
    enclave_id, _, key = rest.partition("/")
    from agent_net.persistence.enclave import vault_get

    entry = await vault_get(enclave_id, key)
    if entry is None:
        raise ProfileError(
            "evidence_unavailable", "产物字节不可读", scope="artifact_read",
            correlation_id=correlation_id,
        )

    body = entry["value"]
    if isinstance(body, str):
        data = body.encode("utf-8")
    else:  # pragma: no cover - Vault 存字符串
        data = bytes(body)

    if len(data) > 16 * 1024 * 1024:
        raise read_limit_error("raw_report_max_bytes", len(data), correlation_id)

    actual = f"sha256:{hashlib.sha256(data).hexdigest()}"
    if expected and actual != expected:
        raise ProfileError(
            "evidence_digest_mismatch",
            "存储字节摘要与登记摘要不一致",
            scope="artifact_read",
            correlation_id=correlation_id,
        )

    return Response(
        content=data,
        media_type=artifact.get("media_type") or "application/octet-stream",
        headers={
            "Content-Length": str(len(data)),
            "ETag": f'"{actual}"',
            "Cache-Control": "no-store",
        },
    )


# ── 供部署脚本/测试登记服务凭据 ───────────────────────────────────────


async def provision_service_credential(
    credential: str,
    *,
    principal_id: str,
    roles: list,
    dids: Optional[list] = None,
    instances: Optional[list] = None,
    projects: Optional[list] = None,
    sessions: Optional[list] = None,
) -> Dict[str, Any]:
    """登记服务凭据（部署初始化入口；明文不入库，只存 sha256）。"""
    return await register_service_principal(
        credential,
        principal_id=principal_id,
        roles=list(roles),
        dids=list(dids or []),
        instances=list(instances or []),
        projects=list(projects or []),
        sessions=list(sessions or []),
    )


__all__ = [
    "router",
    "register_error_handler",
    "require_service_principal",
    "provision_service_credential",
    "reprocess_pending_messages",
    "declared_enforcement_requirements",
]