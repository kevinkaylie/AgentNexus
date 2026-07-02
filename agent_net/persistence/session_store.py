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
_COORDINATION_SESSION_SELECT = """
    SELECT coordination_session_id, root_session_id, owner_did, controller_did,
           objective, enclave_id, playbook_id, playbook_version, playbook_fingerprint,
           playbook_run_id, current_stage, status, policy_json, context_snapshot,
           stage_snapshots, intake_session_id, parent_session_id, created_at, updated_at
    FROM coordination_sessions
"""
# ── Coordination Session CRUD ──────────────────────────────────────────

def _coord_session_row_to_dict(row: tuple) -> dict:
    return {
        "coordination_session_id": row[0],
        "root_session_id": row[1],
        "owner_did": row[2],
        "controller_did": row[3],
        "objective": row[4],
        "enclave_id": row[5],
        "playbook_id": row[6],
        "playbook_version": row[7] or "1",
        "playbook_fingerprint": row[8] or "",
        "playbook_run_id": row[9],
        "current_stage": row[10] or "",
        "status": row[11],
        "policy_json": json.loads(row[12]) if row[12] else {},
        "context_snapshot": json.loads(row[13]) if row[13] else None,
        "stage_snapshots": json.loads(row[14]) if row[14] else [],
        "intake_session_id": row[15],
        "parent_session_id": row[16],
        "created_at": row[17],
        "updated_at": row[18],
    }


async def _enrich_coordination_session_runtime(sess: dict) -> dict:
    """Return runtime fields as a projection from the primary PlaybookRun."""
    run_id = sess.get("playbook_run_id") or ""
    if not run_id:
        return sess
    run = await get_playbook_run(run_id)
    if not run:
        return sess
    context = run.get("context") or {}
    sess["status"] = run.get("status") or sess.get("status", "")
    sess["current_stage"] = run.get("current_stage") or ""
    sess["stage_snapshots"] = context.get("stage_snapshots") or context.get("stages") or []
    sess["primary_run"] = run
    return sess


async def create_coordination_session(
    coordination_session_id: str,
    owner_did: str,
    controller_did: str,
    objective: str,
    enclave_id: str = "",
    playbook_id: str = "coding.v1",
    playbook_run_id: str = "",
    current_stage: str = "clarify",
    stage_snapshots: list[dict] | None = None,
    playbook_version: str = "1",
    playbook_fingerprint: str = "",
    intake_session_id: str | None = None,
    parent_session_id: str | None = None,
    policy: dict | None = None,
    context_snapshot: dict | None = None,
    root_session_id: str | None = None,
    status: str = "running",
) -> dict:
    ts = time.time()
    policy_json = json.dumps(policy) if policy else json.dumps(
        {"complexity": "medium", "risk_level": "normal", "cost_policy": "balanced"}
    )
    context_json = json.dumps(context_snapshot) if context_snapshot else None
    if stage_snapshots is None:
        stage_snapshots = [
            {"name": "clarify", "role": "clarifier", "next": "design", "on_reject": ""},
            {"name": "design", "role": "designer", "next": "design_review", "on_reject": ""},
            {"name": "design_review", "role": "reviewer", "next": "implement", "on_reject": "design"},
            {"name": "implement", "role": "developer", "next": "code_review", "on_reject": ""},
            {"name": "code_review", "role": "reviewer", "next": "test", "on_reject": "implement"},
            {"name": "test", "role": "tester", "next": "final", "on_reject": "implement"},
            {"name": "final", "role": "coordinator", "next": "", "on_reject": ""},
        ]
    stage_snapshots_json = json.dumps(stage_snapshots)

    async with connect() as db:
        await db.execute(
            """INSERT INTO coordination_sessions
                (coordination_session_id, root_session_id, owner_did, controller_did,
                 objective, enclave_id, playbook_id, playbook_version, playbook_fingerprint,
                 playbook_run_id, current_stage, status, policy_json, context_snapshot,
                 stage_snapshots, intake_session_id, parent_session_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (coordination_session_id, root_session_id, owner_did, controller_did,
             objective, enclave_id, playbook_id, playbook_version, playbook_fingerprint,
             playbook_run_id, current_stage, status, policy_json, context_json,
             stage_snapshots_json, intake_session_id, parent_session_id, ts, ts),
        )
        await db.commit()
    async with connect() as db:
        row = await db.execute(
            _COORDINATION_SESSION_SELECT + " WHERE coordination_session_id=?",
            (coordination_session_id,),
        )
        row = await row.fetchone()
        await db.commit()
    return await _enrich_coordination_session_runtime(_coord_session_row_to_dict(row))


async def get_coordination_session(coordination_session_id: str) -> dict | None:
    async with connect() as db:
        row = await db.execute(
            _COORDINATION_SESSION_SELECT + " WHERE coordination_session_id=?",
            (coordination_session_id,),
        )
        row = await row.fetchone()
        await db.commit()
    return await _enrich_coordination_session_runtime(_coord_session_row_to_dict(row)) if row else None


async def list_coordination_sessions(
    owner_did: str | None = None,
    status: str | None = None,
    playbook_id: str | None = None,
) -> list[dict]:
    query = _COORDINATION_SESSION_SELECT + " WHERE 1=1"
    params: list = []
    if owner_did:
        query += " AND owner_did=?"
        params.append(owner_did)
    if playbook_id:
        query += " AND playbook_id=?"
        params.append(playbook_id)
    query += " ORDER BY created_at DESC"

    async with connect() as db:
        rows = await db.execute(query, tuple(params))
        rows = await rows.fetchall()
        await db.commit()
    sessions = [await _enrich_coordination_session_runtime(_coord_session_row_to_dict(r)) for r in rows]
    if status:
        sessions = [s for s in sessions if s.get("status") == status]
    return sessions


async def update_coordination_session(
    coordination_session_id: str, **kwargs
) -> bool:
    allowed = {"policy_json", "context_snapshot", "root_session_id",
               "intake_session_id", "controller_did"}
    updates = {}
    for k, v in kwargs.items():
        if k in allowed:
            if k == "policy_json" and isinstance(v, dict):
                updates[k] = json.dumps(v)
            elif k == "context_snapshot" and isinstance(v, dict):
                updates[k] = json.dumps(v)
            elif k == "context_snapshot" and v is None:
                updates[k] = None
            else:
                updates[k] = v
    if not updates:
        return False

    updates["updated_at"] = time.time()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [coordination_session_id]

    async with connect() as db:
        result = await db.execute(
            f"UPDATE coordination_sessions SET {set_clause} WHERE coordination_session_id=?",
            values,
        )
        await db.commit()
        return result.rowcount > 0


# ── Session Link CRUD ──────────────────────────────────────────────────

def _session_link_row_to_dict(row: tuple) -> dict:
    return {
        "link_id": row[0],
        "coordination_session_id": row[1],
        "from_session_id": row[2],
        "to_session_id": row[3],
        "link_type": row[4],
        "reason": row[5],
        "created_at": row[6],
    }


async def create_session_link(
    link_id: str,
    coordination_session_id: str,
    from_session_id: str,
    to_session_id: str,
    link_type: str,
    reason: str = "",
) -> dict:
    ts = time.time()
    async with connect() as db:
        await db.execute(
            """INSERT INTO session_links
               (link_id, coordination_session_id, from_session_id, to_session_id,
                link_type, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (link_id, coordination_session_id, from_session_id, to_session_id,
             link_type, reason, ts),
        )
        await db.commit()
    return {
        "link_id": link_id,
        "coordination_session_id": coordination_session_id,
        "from_session_id": from_session_id,
        "to_session_id": to_session_id,
        "link_type": link_type,
        "reason": reason,
        "created_at": ts,
    }


async def get_session_links(
    coordination_session_id: str, link_type: str | None = None
) -> list[dict]:
    query = "SELECT * FROM session_links WHERE coordination_session_id=?"
    params: list = [coordination_session_id]
    if link_type:
        query += " AND link_type=?"
        params.append(link_type)
    query += " ORDER BY created_at"

    async with connect() as db:
        rows = await db.execute(query, tuple(params))
        rows = await rows.fetchall()
        await db.commit()
    return [_session_link_row_to_dict(r) for r in rows]


async def get_session_link_by_child(to_session_id: str) -> dict | None:
    async with connect() as db:
        row = await db.execute(
            "SELECT * FROM session_links WHERE to_session_id=? ORDER BY created_at DESC LIMIT 1",
            (to_session_id,),
        )
        row = await row.fetchone()
        await db.commit()
    return _session_link_row_to_dict(row) if row else None


# ── Runtime Event CRUD ─────────────────────────────────────────────────

def _runtime_event_row_to_dict(row: tuple) -> dict:
    return {
        "event_id": row[0],
        "coordination_session_id": row[1],
        "event_type": row[2],
        "stage": row[3] or "",
        "actor_did": row[4] or "",
        "session_id": row[5] or "",
        "run_id": row[6] or "",
        "delegation_id": row[7] or "",
        "artifact_id": row[8] or "",
        "receipt_id": row[9] or "",
        "payload": json.loads(row[10]) if row[10] else {},
        "created_at": row[11],
    }


async def emit_event(
    coordination_session_id: str,
    event_type: str,
    stage: str = "",
    actor_did: str = "",
    session_id: str = "",
    run_id: str = "",
    delegation_id: str = "",
    artifact_id: str = "",
    receipt_id: str = "",
    payload: dict | None = None,
) -> dict:
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    return await create_runtime_event(
        event_id=event_id,
        coordination_session_id=coordination_session_id,
        event_type=event_type,
        stage=stage,
        actor_did=actor_did,
        session_id=session_id,
        run_id=run_id,
        delegation_id=delegation_id,
        artifact_id=artifact_id,
        receipt_id=receipt_id,
        payload=payload,
    )


async def create_runtime_event(
    event_id: str,
    coordination_session_id: str,
    event_type: str,
    stage: str = "",
    actor_did: str = "",
    session_id: str = "",
    run_id: str = "",
    delegation_id: str = "",
    artifact_id: str = "",
    receipt_id: str = "",
    payload: dict | None = None,
) -> dict:
    payload_json = json.dumps(payload) if payload else "{}"
    ts = time.time()
    async with connect() as db:
        await db.execute(
            """INSERT INTO runtime_events
               (event_id, coordination_session_id, event_type, stage, actor_did,
                session_id, run_id, delegation_id, artifact_id, receipt_id,
                payload, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, coordination_session_id, event_type, stage, actor_did,
             session_id, run_id, delegation_id, artifact_id, receipt_id,
             payload_json, ts),
        )
        await db.commit()
    return {
        "event_id": event_id,
        "coordination_session_id": coordination_session_id,
        "event_type": event_type,
        "stage": stage,
        "actor_did": actor_did,
        "session_id": session_id,
        "run_id": run_id,
        "delegation_id": delegation_id,
        "artifact_id": artifact_id,
        "receipt_id": receipt_id,
        "payload": payload or {},
        "created_at": ts,
    }


async def get_runtime_events(
    coordination_session_id: str,
    stage: str | None = None,
    event_type: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM runtime_events WHERE coordination_session_id=?"
    params: list = [coordination_session_id]
    if stage:
        query += " AND stage=?"
        params.append(stage)
    if event_type:
        query += " AND event_type=?"
        params.append(event_type)
    query += " ORDER BY created_at ASC"

    async with connect() as db:
        rows = await db.execute(query, tuple(params))
        rows = await rows.fetchall()
        await db.commit()
    return [_runtime_event_row_to_dict(r) for r in rows]


