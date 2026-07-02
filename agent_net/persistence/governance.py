"""Trust and governance persistence."""
from __future__ import annotations

import json
import secrets
import time
import uuid
from typing import Optional

import aiosqlite

from .context import connect, get_db_path


# ── Trust Edges CRUD ─────────────────────────────────────────────────────

async def add_trust_edge(
    from_did: str,
    to_did: str,
    score: float,
    evidence: Optional[str] = None,
):
    """添加信任边"""
    async with connect() as db:
        await db.execute(
            """INSERT OR REPLACE INTO trust_edges
               (from_did, to_did, score, timestamp, evidence)
               VALUES (?, ?, ?, ?, ?)""",
            (from_did, to_did, score, time.time(), evidence)
        )
        await db.commit()


async def get_trust_edge(from_did: str, to_did: str) -> Optional[dict]:
    """获取信任边"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM trust_edges WHERE from_did = ? AND to_did = ?",
            (from_did, to_did)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "from_did": row["from_did"],
        "to_did": row["to_did"],
        "score": row["score"],
        "timestamp": row["timestamp"],
        "evidence": row["evidence"],
    }


async def list_trust_edges_from(from_did: str) -> list[dict]:
    """列出从某 DID 发出的信任边"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM trust_edges WHERE from_did = ?",
            (from_did,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def remove_trust_edge(from_did: str, to_did: str) -> bool:
    """删除信任边"""
    async with connect() as db:
        result = await db.execute(
            "DELETE FROM trust_edges WHERE from_did = ? AND to_did = ?",
            (from_did, to_did)
        )
        await db.commit()
        return result.rowcount > 0


# ── Interactions CRUD ────────────────────────────────────────────────────

async def record_interaction(
    from_did: str,
    to_did: str,
    interaction_type: str,
    success: bool,
    response_time_ms: Optional[float] = None,
) -> int:
    """记录交互"""
    async with connect() as db:
        cursor = await db.execute(
            """INSERT INTO interactions
               (from_did, to_did, interaction_type, success, response_time_ms, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (from_did, to_did, interaction_type, int(success), response_time_ms, time.time())
        )
        await db.commit()
        return cursor.lastrowid or 0


async def get_interactions(
    agent_did: str,
    time_window_days: int = 30,
) -> list[dict]:
    """获取交互历史"""
    now = time.time()
    window_start = now - time_window_days * 86400
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM interactions
               WHERE to_did = ? AND timestamp >= ?
               ORDER BY timestamp DESC""",
            (agent_did, window_start)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ── Governance Attestations CRUD ─────────────────────────────────────────

async def save_governance_attestation(
    agent_did: str,
    issuer: str,
    attestation: dict,
    expires_at: float,
):
    """缓存治理认证"""
    async with connect() as db:
        await db.execute(
            """INSERT OR REPLACE INTO governance_attestations
               (agent_did, issuer, attestation_json, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (agent_did, issuer, json.dumps(attestation), expires_at, time.time())
        )
        await db.commit()


async def get_governance_attestation(
    agent_did: str,
    issuer: str,
) -> Optional[dict]:
    """获取缓存的治理认证"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM governance_attestations
               WHERE agent_did = ? AND issuer = ? AND expires_at > ?""",
            (agent_did, issuer, time.time())
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "agent_did": row["agent_did"],
        "issuer": row["issuer"],
        "attestation": json.loads(row["attestation_json"]),
        "expires_at": row["expires_at"],
    }


async def get_all_governance_attestations(agent_did: str) -> list[dict]:
    """获取 Agent 的所有有效治理认证"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM governance_attestations
               WHERE agent_did = ? AND expires_at > ?""",
            (agent_did, time.time())
        ) as cursor:
            rows = await cursor.fetchall()
    return [
        {
            "agent_did": row["agent_did"],
            "issuer": row["issuer"],
            "attestation": json.loads(row["attestation_json"]),
            "expires_at": row["expires_at"],
        }
        for row in rows
    ]


async def cleanup_expired_attestations() -> int:
    """清理过期的治理认证"""
    async with connect() as db:
        result = await db.execute(
            "DELETE FROM governance_attestations WHERE expires_at < ?",
            (time.time(),)
        )
        await db.commit()
        return result.rowcount
