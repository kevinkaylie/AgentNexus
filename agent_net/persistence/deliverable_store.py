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
_ARTIFACT_SELECT = """
    SELECT artifact_id, coordination_session_id, run_id, stage, artifact_type,
           producer_did, content_ref, content_hash, schema_version, created_at
    FROM artifacts
"""
_RECEIPT_SELECT = """
    SELECT receipt_id, coordination_session_id, run_id, stage, receipt_type,
           issuer_did, decision, subject_artifact_id, evidence_refs, signature, created_at
    FROM receipts
"""
_DECISION_REQUEST_SELECT = """
    SELECT decision_id, owner_did, coordination_session_id, run_id, stage,
           requested_by_did, question, options_json, recommended_option,
           risk_level, evidence_refs, status, response_json, created_at,
           resolved_at
    FROM decision_requests
"""
# ── Artifact CRUD ──────────────────────────────────────────────────────

def _artifact_row_to_dict(row: tuple) -> dict:
    return {
        "artifact_id": row[0],
        "coordination_session_id": row[1],
        "run_id": row[2] or "",
        "stage": row[3],
        "artifact_type": row[4],
        "producer_did": row[5],
        "content_ref": row[6],
        "content_hash": row[7] or "",
        "schema_version": row[8] or "1",
        "created_at": row[9],
    }


async def create_artifact(
    artifact_id: str,
    coordination_session_id: str,
    run_id: str,
    stage: str,
    artifact_type: str,
    producer_did: str,
    content_ref: str,
    content_hash: str = "",
    schema_version: str = "1",
) -> dict:
    ts = time.time()
    async with connect() as db:
        await db.execute(
            """INSERT INTO artifacts
               (artifact_id, coordination_session_id, run_id, stage, artifact_type,
                producer_did, content_ref, content_hash, schema_version, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (artifact_id, coordination_session_id, run_id, stage, artifact_type,
             producer_did, content_ref, content_hash, schema_version, ts),
        )
        await db.commit()
    return {
        "artifact_id": artifact_id,
        "coordination_session_id": coordination_session_id,
        "run_id": run_id,
        "stage": stage,
        "artifact_type": artifact_type,
        "producer_did": producer_did,
        "content_ref": content_ref,
        "content_hash": content_hash,
        "schema_version": schema_version,
        "created_at": ts,
    }


async def get_artifact(artifact_id: str) -> dict | None:
    async with connect() as db:
        row = await db.execute(
            _ARTIFACT_SELECT + " WHERE artifact_id=?",
            (artifact_id,),
        )
        row = await row.fetchone()
        await db.commit()
    return _artifact_row_to_dict(row) if row else None


async def list_artifacts(
    coordination_session_id: str, stage: str | None = None, run_id: str | None = None
) -> list[dict]:
    query = _ARTIFACT_SELECT + " WHERE coordination_session_id=?"
    params: list = [coordination_session_id]
    if run_id is not None:
        query += " AND run_id=?"
        params.append(run_id)
    if stage:
        query += " AND stage=?"
        params.append(stage)
    query += " ORDER BY created_at ASC"

    async with connect() as db:
        rows = await db.execute(query, tuple(params))
        rows = await rows.fetchall()
        await db.commit()
    return [_artifact_row_to_dict(r) for r in rows]


# ── Receipt CRUD ───────────────────────────────────────────────────────

def _receipt_row_to_dict(row: tuple) -> dict:
    return {
        "receipt_id": row[0],
        "coordination_session_id": row[1],
        "run_id": row[2] or "",
        "stage": row[3],
        "receipt_type": row[4],
        "issuer_did": row[5],
        "decision": row[6],
        "subject_artifact_id": row[7] or "",
        "evidence_refs": json.loads(row[8]) if row[8] else [],
        "signature": row[9] or "",
        "created_at": row[10],
    }


async def create_receipt(
    receipt_id: str,
    coordination_session_id: str,
    run_id: str,
    stage: str,
    receipt_type: str,
    issuer_did: str,
    decision: str,
    subject_artifact_id: str = "",
    evidence_refs: list[str] | None = None,
    signature: str = "",
) -> dict:
    ts = time.time()
    evidence_json = json.dumps(evidence_refs) if evidence_refs else "[]"
    async with connect() as db:
        await db.execute(
            """INSERT INTO receipts
               (receipt_id, coordination_session_id, run_id, stage, receipt_type,
                issuer_did, decision, subject_artifact_id, evidence_refs,
                signature, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (receipt_id, coordination_session_id, run_id, stage, receipt_type,
             issuer_did, decision, subject_artifact_id, evidence_json,
             signature, ts),
        )
        await db.commit()
    return {
        "receipt_id": receipt_id,
        "coordination_session_id": coordination_session_id,
        "run_id": run_id,
        "stage": stage,
        "receipt_type": receipt_type,
        "issuer_did": issuer_did,
        "decision": decision,
        "subject_artifact_id": subject_artifact_id,
        "evidence_refs": evidence_refs or [],
        "signature": signature,
        "created_at": ts,
    }


async def get_receipt(receipt_id: str) -> dict | None:
    async with connect() as db:
        row = await db.execute(
            _RECEIPT_SELECT + " WHERE receipt_id=?",
            (receipt_id,),
        )
        row = await row.fetchone()
        await db.commit()
    return _receipt_row_to_dict(row) if row else None


async def list_receipts(
    coordination_session_id: str, stage: str | None = None, run_id: str | None = None
) -> list[dict]:
    query = _RECEIPT_SELECT + " WHERE coordination_session_id=?"
    params: list = [coordination_session_id]
    if run_id is not None:
        query += " AND run_id=?"
        params.append(run_id)
    if stage:
        query += " AND stage=?"
        params.append(stage)
    query += " ORDER BY created_at ASC"

    async with connect() as db:
        rows = await db.execute(query, tuple(params))
        rows = await rows.fetchall()
        await db.commit()
    return [_receipt_row_to_dict(r) for r in rows]


# ── Decision Request CRUD ────────────────────────────────────────────────

def _decision_request_row_to_dict(row: tuple) -> dict:
    return {
        "decision_id": row[0],
        "owner_did": row[1],
        "coordination_session_id": row[2],
        "run_id": row[3] or "",
        "stage": row[4] or "",
        "requested_by_did": row[5],
        "question": row[6],
        "options": json.loads(row[7]) if row[7] else [],
        "recommended_option": row[8] or "",
        "risk_level": row[9] or "normal",
        "evidence_refs": json.loads(row[10]) if row[10] else [],
        "status": row[11],
        "response": json.loads(row[12]) if row[12] else {},
        "created_at": row[13],
        "resolved_at": row[14],
    }


async def create_decision_request(
    decision_id: str,
    owner_did: str,
    coordination_session_id: str,
    requested_by_did: str,
    question: str,
    run_id: str = "",
    stage: str = "",
    options: list[str | dict] | None = None,
    recommended_option: str = "",
    risk_level: str = "normal",
    evidence_refs: list[str] | None = None,
) -> dict:
    ts = time.time()
    options_json = json.dumps(options or [], ensure_ascii=False)
    evidence_json = json.dumps(evidence_refs or [], ensure_ascii=False)
    async with connect() as db:
        await db.execute(
            """INSERT INTO decision_requests
               (decision_id, owner_did, coordination_session_id, run_id, stage,
                requested_by_did, question, options_json, recommended_option,
                risk_level, evidence_refs, status, response_json, created_at,
                resolved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '{}', ?, NULL)""",
            (
                decision_id, owner_did, coordination_session_id, run_id, stage,
                requested_by_did, question, options_json, recommended_option,
                risk_level, evidence_json, ts,
            ),
        )
        await db.commit()
    return {
        "decision_id": decision_id,
        "owner_did": owner_did,
        "coordination_session_id": coordination_session_id,
        "run_id": run_id,
        "stage": stage,
        "requested_by_did": requested_by_did,
        "question": question,
        "options": options or [],
        "recommended_option": recommended_option,
        "risk_level": risk_level,
        "evidence_refs": evidence_refs or [],
        "status": "pending",
        "response": {},
        "created_at": ts,
        "resolved_at": None,
    }


async def get_decision_request(decision_id: str) -> dict | None:
    async with connect() as db:
        row = await db.execute(
            _DECISION_REQUEST_SELECT + " WHERE decision_id=?",
            (decision_id,),
        )
        row = await row.fetchone()
        await db.commit()
    return _decision_request_row_to_dict(row) if row else None


async def list_decision_requests(
    owner_did: str | None = None,
    coordination_session_id: str | None = None,
    run_id: str | None = None,
    stage: str | None = None,
    status: str | None = None,
) -> list[dict]:
    query = _DECISION_REQUEST_SELECT + " WHERE 1=1"
    params: list = []
    if owner_did:
        query += " AND owner_did=?"
        params.append(owner_did)
    if coordination_session_id:
        query += " AND coordination_session_id=?"
        params.append(coordination_session_id)
    if run_id is not None:
        query += " AND run_id=?"
        params.append(run_id)
    if stage:
        query += " AND stage=?"
        params.append(stage)
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY created_at ASC"

    async with connect() as db:
        rows = await db.execute(query, tuple(params))
        rows = await rows.fetchall()
        await db.commit()
    return [_decision_request_row_to_dict(r) for r in rows]


async def resolve_decision_request(
    decision_id: str,
    *,
    status: str,
    response: dict,
) -> dict | None:
    ts = time.time()
    async with connect() as db:
        await db.execute(
            """UPDATE decision_requests
               SET status=?, response_json=?, resolved_at=?
               WHERE decision_id=?""",
            (status, json.dumps(response, ensure_ascii=False), ts, decision_id),
        )
        await db.commit()
    return await get_decision_request(decision_id)


# ── Closure Record CRUD ────────────────────────────────────────────────

def _closure_row_to_dict(row: tuple) -> dict:
    return {
        "closure_id": row[0],
        "coordination_session_id": row[1],
        "actor_did": row[2],
        "status": row[3],
        "sla_status": row[4],
        "sla_metrics": json.loads(row[5]) if row[5] else {},
        "receipt_id": row[6] or "",
        "evidence_refs": json.loads(row[7]) if row[7] else [],
        "created_at": row[8],
    }


async def create_closure_record(
    closure_id: str,
    coordination_session_id: str,
    actor_did: str,
    status: str,
    sla_status: str,
    sla_metrics: dict | None = None,
    receipt_id: str = "",
    evidence_refs: list[str] | None = None,
) -> dict:
    ts = time.time()
    metrics_json = json.dumps(sla_metrics) if sla_metrics else "{}"
    evidence_json = json.dumps(evidence_refs) if evidence_refs else "[]"
    async with connect() as db:
        await db.execute(
            """INSERT INTO closure_records
               (closure_id, coordination_session_id, actor_did, status,
                sla_status, sla_metrics, receipt_id, evidence_refs, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (closure_id, coordination_session_id, actor_did, status,
             sla_status, metrics_json, receipt_id, evidence_json, ts),
        )
        await db.commit()
    return {
        "closure_id": closure_id,
        "coordination_session_id": coordination_session_id,
        "actor_did": actor_did,
        "status": status,
        "sla_status": sla_status,
        "sla_metrics": sla_metrics or {},
        "receipt_id": receipt_id,
        "evidence_refs": evidence_refs or [],
        "created_at": ts,
    }


async def get_closure_record(closure_id: str) -> dict | None:
    async with connect() as db:
        row = await db.execute(
            "SELECT * FROM closure_records WHERE closure_id=?",
            (closure_id,),
        )
        row = await row.fetchone()
        await db.commit()
    return _closure_row_to_dict(row) if row else None


async def list_closure_records(
    coordination_session_id: str, status: str | None = None
) -> list[dict]:
    query = "SELECT * FROM closure_records WHERE coordination_session_id=?"
    params: list = [coordination_session_id]
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY created_at ASC"

    async with connect() as db:
        rows = await db.execute(query, tuple(params))
        rows = await rows.fetchall()
        await db.commit()
    return [_closure_row_to_dict(r) for r in rows]

