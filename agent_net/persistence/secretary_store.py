"""Secretary, coordination, artifact, receipt, and execution persistence."""
from __future__ import annotations

import json
import secrets
import time
import uuid
from typing import Optional

import aiosqlite

from .context import connect, get_db_path
from .core import get_agent
from .enclave import get_playbook_run, get_stage_executions_for_run, vault_put
async def create_intake(
    session_id: str,
    owner_did: str,
    actor_did: str,
    objective: str,
    required_roles: list[str],
    preferred_playbook: str = None,
    source_channel: str = None,
    source_message_ref: str = None,
    constraints: dict = None,
) -> dict:
    """D-SEC-02: 创建 intake 记录。"""
    now = time.time()
    async with connect() as db:
        await db.execute(
            "INSERT INTO secretary_intakes "
            "(session_id, owner_did, actor_did, status, objective, required_roles, "
            " preferred_playbook, source_channel, source_message_ref, constraints_json, "
            " created_at, updated_at) "
            "VALUES (?, ?, ?, 'intake', ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id, owner_did, actor_did, objective,
                json.dumps(required_roles),
                preferred_playbook, source_channel, source_message_ref,
                json.dumps(constraints or {}),
                now, now,
            ),
        )
        await db.commit()
    return {
        "session_id": session_id,
        "owner_did": owner_did,
        "actor_did": actor_did,
        "status": "intake",
        "objective": objective,
        "required_roles": required_roles,
        "preferred_playbook": preferred_playbook,
        "selected_workers": {},
    }


async def get_intake(session_id: str) -> Optional[dict]:
    """D-SEC-02: 获取 intake 记录。"""
    async with connect() as db:
        async with db.execute(
            "SELECT * FROM secretary_intakes WHERE session_id=?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return {
        "session_id": row[0],
        "owner_did": row[1],
        "actor_did": row[2],
        "status": row[3],
        "objective": row[4],
        "required_roles": json.loads(row[5]),
        "preferred_playbook": row[6],
        "selected_workers": json.loads(row[7]) if row[7] else {},
        "run_id": row[8],
        "coordination_session_id": row[9],
        "source_channel": row[10],
        "source_message_ref": row[11],
        "constraints": json.loads(row[12]) if row[12] else {},
        "created_at": row[13],
        "updated_at": row[14],
    }


async def update_intake(session_id: str, **kwargs) -> bool:
    """D-SEC-02: 更新 intake 状态（如 selected_workers, status, run_id）。"""
    allowed_fields = {
        "status", "selected_workers", "run_id", "coordination_session_id", "objective",
        "preferred_playbook", "constraints_json",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not updates:
        return False

    # JSON 序列化
    if "selected_workers" in updates and isinstance(updates["selected_workers"], dict):
        updates["selected_workers"] = json.dumps(updates["selected_workers"])
    if "constraints_json" in updates and isinstance(updates["constraints_json"], dict):
        updates["constraints_json"] = json.dumps(updates["constraints_json"])

    updates["updated_at"] = time.time()
    set_clause = ", ".join(f"{k}=?" for k in updates.keys())
    values = list(updates.values()) + [session_id]

    async with connect() as db:
        cur = await db.execute(
            f"UPDATE secretary_intakes SET {set_clause} WHERE session_id=?", values
        )
        await db.commit()
        return cur.rowcount > 0


async def list_intakes(owner_did: str, status: str = None) -> list[dict]:
    """D-SEC-02: 列出 owner 的 intake 记录。"""
    async with connect() as db:
        if status:
            async with db.execute(
                "SELECT * FROM secretary_intakes WHERE owner_did=? AND status=? ORDER BY created_at DESC",
                (owner_did, status),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM secretary_intakes WHERE owner_did=? ORDER BY created_at DESC",
                (owner_did,),
            ) as cur:
                rows = await cur.fetchall()

    result = []
    for row in rows:
        result.append({
            "session_id": row[0],
            "owner_did": row[1],
            "actor_did": row[2],
            "status": row[3],
            "objective": row[4],
            "required_roles": json.loads(row[5]),
            "preferred_playbook": row[6],
            "selected_workers": json.loads(row[7]) if row[7] else {},
            "run_id": row[8],
            "coordination_session_id": row[9],
            "source_channel": row[10],
            "source_message_ref": row[11],
            "constraints": json.loads(row[12]) if row[12] else {},
            "created_at": row[13],
            "updated_at": row[14],
        })
    return result


async def is_secretary(did: str) -> Optional[dict]:
    """D-SEC-02: 检查 did 是否是 owner 绑定的 secretary 子 Agent。
    如果是，返回 agent 记录；否则返回 None。
    """
    agent = await get_agent(did)
    if not agent:
        return None
    profile = agent.get("profile", {})
    if profile.get("type") != "secretary":
        return None
    return agent


# ══════════════════════════════════════════════════════════════════════════════
# D-SEC-05: Delivery Manifest
# ══════════════════════════════════════════════════════════════════════════════

async def store_stage_manifest(
    run_id: str,
    stage_name: str,
    status: str,
    artifacts: list[dict],
    required_outputs: list[str] | None = None,
    produced_by: str = "",
) -> dict:
    """
    D-SEC-05: 生成并存储 Stage Delivery Manifest 到 Vault。
    返回 manifest dict。
    """
    import time
    manifest_id = f"manifest_{stage_name}_{run_id}"
    manifest = {
        "manifest_id": manifest_id,
        "run_id": run_id,
        "stage_name": stage_name,
        "status": status,
        "artifacts": artifacts,
        "required_outputs": required_outputs or [],
        "missing_outputs": [r for r in (required_outputs or []) if r not in [a["kind"] for a in artifacts]],
        "produced_by": produced_by,
        "created_at": time.time(),
    }

    # 写入 Vault: manifests/{run_id}/{stage}
    # 需要找到对应的 enclave_id
    run = await get_playbook_run(run_id)
    if not run:
        return manifest

    vault_key = f"manifests/{run_id}/{stage_name}"
    try:
        await vault_put(
            enclave_id=run["enclave_id"],
            key=vault_key,
            value=json.dumps(manifest, separators=(",", ":"), ensure_ascii=False),
            author_did=produced_by or run.get("owner_did", ""),
            message=f"Stage manifest: {stage_name}",
        )
    except Exception:
        pass  # Vault 写入失败不影响 manifest 返回

    return manifest


async def store_final_manifest(
    run_id: str,
    status: str,
    summary: str,
    stage_manifest_ids: list[str],
    final_artifacts: list[dict],
    produced_by: str = "",
) -> dict:
    """
    D-SEC-05: 生成并存储 Final Delivery Manifest 到 Vault。
    返回 manifest dict。
    """
    import time
    manifest_id = f"manifest_final_{run_id}"
    manifest = {
        "manifest_id": manifest_id,
        "run_id": run_id,
        "status": status,
        "summary": summary,
        "stage_manifests": stage_manifest_ids,
        "final_artifacts": final_artifacts,
        "final_status": status,
        "produced_by": produced_by,
        "created_at": time.time(),
    }

    run = await get_playbook_run(run_id)
    if not run:
        return manifest

    vault_key = f"manifests/{run_id}/final"
    try:
        await vault_put(
            enclave_id=run["enclave_id"],
            key=vault_key,
            value=json.dumps(manifest, separators=(",", ":"), ensure_ascii=False),
            author_did=produced_by or run.get("owner_did", ""),
            message="Final delivery manifest",
        )
    except Exception:
        pass

    return manifest


