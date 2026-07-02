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
# ── Objective Execution CRUD ──────────────────────────────────────────

_OBJECTIVE_EXECUTION_SELECT = """
    SELECT execution_id, coordination_session_id, run_id, stage,
           worker_did, backend_kind, status, lease_expires_at, attempt,
           external_session_id, artifact_id, receipt_id, result_hash,
           error, metadata, created_at, updated_at, completed_at
    FROM objective_executions
"""


def _obj_exec_row_to_dict(row: tuple) -> dict:
    return {
        "execution_id": row[0],
        "coordination_session_id": row[1],
        "run_id": row[2],
        "stage": row[3],
        "worker_did": row[4],
        "backend_kind": row[5],
        "status": row[6],
        "lease_expires_at": row[7],
        "attempt": row[8] or 1,
        "external_session_id": row[9] or "",
        "artifact_id": row[10] or "",
        "receipt_id": row[11] or "",
        "result_hash": row[12] or "",
        "error": row[13] or "",
        "metadata": json.loads(row[14]) if row[14] else {},
        "created_at": row[15],
        "updated_at": row[16],
        "completed_at": row[17],
    }


async def create_objective_execution(
    execution_id: str,
    coordination_session_id: str,
    run_id: str,
    stage: str,
    worker_did: str,
    backend_kind: str,
    status: str = "pending",
    lease_expires_at: float | None = None,
    attempt: int = 1,
    external_session_id: str = "",
    metadata: dict | None = None,
) -> dict:
    ts = time.time()
    meta_json = json.dumps(metadata) if metadata else "{}"
    async with connect() as db:
        await db.execute(
            """INSERT INTO objective_executions
               (execution_id, coordination_session_id, run_id, stage,
                worker_did, backend_kind, status, lease_expires_at, attempt,
                external_session_id, metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (execution_id, coordination_session_id, run_id, stage,
             worker_did, backend_kind, status, lease_expires_at, attempt,
             external_session_id, meta_json, ts, ts),
        )
        await db.commit()
    return await get_objective_execution(execution_id)


async def get_objective_execution(execution_id: str) -> dict | None:
    async with connect() as db:
        async with db.execute(
            f"{_OBJECTIVE_EXECUTION_SELECT} WHERE execution_id=?",
            (execution_id,),
        ) as cur:
            row = await cur.fetchone()
    return _obj_exec_row_to_dict(row) if row else None


async def list_objective_executions(
    coordination_session_id: str,
    run_id: str | None = None,
    stage: str | None = None,
    status: str | None = None,
) -> list[dict]:
    conditions = ["coordination_session_id = ?"]
    params: list = [coordination_session_id]
    if run_id is not None:
        conditions.append("run_id = ?")
        params.append(run_id)
    if stage is not None:
        conditions.append("stage = ?")
        params.append(stage)
    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    where = " AND ".join(conditions)
    async with connect() as db:
        async with db.execute(
            f"{_OBJECTIVE_EXECUTION_SELECT} WHERE {where} ORDER BY created_at DESC",
            tuple(params),
        ) as cur:
            rows = await cur.fetchall()
    return [_obj_exec_row_to_dict(r) for r in rows]


async def update_objective_execution(execution_id: str, **kwargs) -> bool:
    """Update execution fields. Returns True if row existed, False otherwise."""
    allowed = {
        "status", "lease_expires_at", "external_session_id",
        "metadata", "error", "completed_at",
    }
    updates = {}
    for k, v in kwargs.items():
        if k in allowed:
            updates[k] = v

    if not updates:
        return False

    if "metadata" in updates and isinstance(updates["metadata"], dict):
        updates["metadata"] = json.dumps(updates["metadata"])

    updates["updated_at"] = time.time()

    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [execution_id]

    async with connect() as db:
        cursor = await db.execute(
            f"UPDATE objective_executions SET {set_clause} WHERE execution_id=?",
            tuple(values),
        )
        await db.commit()
        return cursor.rowcount > 0


async def mark_execution_result(
    execution_id: str,
    *,
    artifact_id: str,
    receipt_id: str,
    result_hash: str,
    status: str,
) -> dict:
    """Idempotent result submission.

    If the same execution already has a result with the same hash,
    return the existing record. Raises ValueError if execution not found.
    """
    existing = await get_objective_execution(execution_id)
    if existing is None:
        raise ValueError(f"Execution {execution_id} not found")

    # Idempotency: if already has same result_hash, return existing
    if existing["result_hash"] and existing["result_hash"] == result_hash:
        return existing

    ts = time.time()
    async with connect() as db:
        await db.execute(
            """UPDATE objective_executions
               SET status=?, artifact_id=?, receipt_id=?, result_hash=?,
                   completed_at=?, updated_at=?
               WHERE execution_id=?""",
            (status, artifact_id, receipt_id, result_hash, ts, ts, execution_id),
        )
        await db.commit()
    return await get_objective_execution(execution_id)


# ── Delegation CRUD ────────────────────────────────────────────────────

def _delegation_row_to_dict(row: tuple) -> dict:
    return {
        "delegation_id": row[0],
        "coordination_session_id": row[1],
        "stage": row[2],
        "role": row[3],
        "delegator_did": row[4],
        "delegatee_did": row[5],
        "capability_token_id": row[6] or "",
        "runtime_kind": row[7] or "native_worker",
        "protocol": row[8] or "agentnexus-native",
        "session_id": row[9] or "",
        "status": row[10],
        "created_at": row[11],
        "updated_at": row[12],
    }


async def create_delegation(
    delegation_id: str,
    coordination_session_id: str,
    stage: str,
    role: str,
    delegator_did: str,
    delegatee_did: str,
    capability_token_id: str = "",
    runtime_kind: str = "native_worker",
    protocol: str = "agentnexus-native",
    session_id: str = "",
) -> dict:
    ts = time.time()
    async with connect() as db:
        await db.execute(
            """INSERT INTO delegations
               (delegation_id, coordination_session_id, stage, role,
                delegator_did, delegatee_did, capability_token_id,
                runtime_kind, protocol, session_id, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (delegation_id, coordination_session_id, stage, role,
             delegator_did, delegatee_did, capability_token_id,
             runtime_kind, protocol, session_id, ts, ts),
        )
        await db.commit()
    return {
        "delegation_id": delegation_id,
        "coordination_session_id": coordination_session_id,
        "stage": stage,
        "role": role,
        "delegator_did": delegator_did,
        "delegatee_did": delegatee_did,
        "capability_token_id": capability_token_id,
        "runtime_kind": runtime_kind,
        "protocol": protocol,
        "session_id": session_id,
        "status": "pending",
        "created_at": ts,
        "updated_at": ts,
    }


async def get_delegation(delegation_id: str) -> dict | None:
    async with connect() as db:
        row = await db.execute(
            "SELECT * FROM delegations WHERE delegation_id=?",
            (delegation_id,),
        )
        row = await row.fetchone()
        await db.commit()
    return _delegation_row_to_dict(row) if row else None


async def update_delegation(delegation_id: str, status: str) -> bool:
    async with connect() as db:
        result = await db.execute(
            "UPDATE delegations SET status=?, updated_at=? WHERE delegation_id=?",
            (status, time.time(), delegation_id),
        )
        await db.commit()
        return result.rowcount > 0


async def list_delegations(coordination_session_id: str) -> list[dict]:
    async with connect() as db:
        rows = await db.execute(
            "SELECT * FROM delegations WHERE coordination_session_id=? ORDER BY created_at ASC",
            (coordination_session_id,),
        )
        rows = await rows.fetchall()
        await db.commit()
    return [_delegation_row_to_dict(r) for r in rows]
