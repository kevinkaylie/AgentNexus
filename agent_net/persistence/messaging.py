"""Agents, owners, messaging, skills, and push persistence."""
from __future__ import annotations

import json
import secrets
import time
import uuid
from typing import Optional

import aiosqlite

from .context import connect, get_db_path
from .schemas import (
    _column_exists,
    _safe_migrate,
    init_coordination_tables,
    init_enclave_tables,
    init_secretary_tables,
    init_trust_tables,
)


async def store_message(from_did: str, to_did: str, content: str,
                        session_id: str = "", reply_to: int | None = None,
                        message_type: str | None = None, protocol: str | None = None,
                        content_encoding: str | None = None,
                        message_id: str | None = None):
    """存储离线消息。D-SEC-09: 支持 message_id 持久化。"""
    if not message_id:
        message_id = f"msg_{uuid.uuid4().hex[:16]}"
    async with connect() as db:
        await db.execute(
            "INSERT INTO messages (from_did, to_did, content, timestamp, session_id, reply_to, message_type, protocol, content_encoding, message_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (from_did, to_did, content, time.time(), session_id, reply_to, message_type, protocol, content_encoding, message_id)
        )
        await db.commit()


async def fetch_inbox(did: str) -> list[dict]:
    async with connect() as db:
        async with db.execute(
            "SELECT id, from_did, content, timestamp, session_id, reply_to, message_type, protocol, content_encoding, message_id "
            "FROM messages WHERE to_did=? AND delivered=0 ORDER BY timestamp",
            (did,)
        ) as cursor:
            rows = await cursor.fetchall()
        if rows:
            ids = [r[0] for r in rows]
            await db.execute(
                f"UPDATE messages SET delivered=1 WHERE id IN ({','.join('?'*len(ids))})", ids
            )
            await db.commit()
    return [{"id": r[0], "from": r[1], "content": r[2], "timestamp": r[3],
             "session_id": r[4] or "", "reply_to": r[5],
             "message_type": r[6], "protocol": r[7], "content_encoding": r[8],
             "message_id": r[9]} for r in rows]


async def fetch_session(session_id: str) -> list[dict]:
    """按 session_id 查询完整会话历史（含已读消息）"""
    async with connect() as db:
        async with db.execute(
            "SELECT id, from_did, to_did, content, timestamp, reply_to, delivered, message_type, protocol, content_encoding, message_id "
            "FROM messages WHERE session_id=? ORDER BY timestamp",
            (session_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"id": r[0], "from": r[1], "to": r[2], "content": r[3],
             "timestamp": r[4], "reply_to": r[5], "delivered": bool(r[6]),
             "message_type": r[7], "protocol": r[8], "content_encoding": r[9],
             "message_id": r[10]} for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# Owner 消息聚合函数 — v1.0-06
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_owner_inbox(owner_did: str, limit: int = 50, offset: int = 0) -> dict:
    """
    聚合主 DID 下所有子 Agent 的未读消息。
    返回 {owner_did, messages, total_unread}。
    """
    async with connect() as db:
        # 查询所有子 Agent 的未读消息
        async with db.execute(
            """SELECT m.id, m.from_did, m.to_did, m.content, m.timestamp,
                      m.session_id, m.message_type, m.protocol,
                      a.profile
               FROM messages m
               JOIN agents a ON m.to_did = a.did
               WHERE a.owner_did = ? AND m.delivered = 0
               ORDER BY m.timestamp DESC
               LIMIT ? OFFSET ?""",
            (owner_did, limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()

        # 统计总数
        async with db.execute(
            """SELECT COUNT(*) FROM messages m
               JOIN agents a ON m.to_did = a.did
               WHERE a.owner_did = ? AND m.delivered = 0""",
            (owner_did,)
        ) as cursor:
            total = await cursor.fetchone()
            total_unread = total[0] if total else 0

    messages = []
    for r in rows:
        profile = json.loads(r[8]) if r[8] else {}
        messages.append({
            "id": r[0],
            "from_did": r[1],
            "to_did": r[2],
            "to_agent_name": profile.get("name", ""),
            "content": r[3],
            "timestamp": r[4],
            "session_id": r[5] or "",
            "message_type": r[6],
            "protocol": r[7],
        })
    return {"owner_did": owner_did, "messages": messages, "total_unread": total_unread}


async def fetch_owner_messages(owner_did: str, limit: int = 100, offset: int = 0) -> dict:
    """
    聚合主 DID 下所有子 Agent 的全部消息（分页）。
    返回 {owner_did, messages, total}。
    """
    async with connect() as db:
        async with db.execute(
            """SELECT m.id, m.from_did, m.to_did, m.content, m.timestamp,
                      m.session_id, m.message_type, m.protocol, m.delivered,
                      a.profile
               FROM messages m
               JOIN agents a ON m.to_did = a.did
               WHERE a.owner_did = ?
               ORDER BY m.timestamp DESC
               LIMIT ? OFFSET ?""",
            (owner_did, limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()

        # 统计总数
        async with db.execute(
            """SELECT COUNT(*) FROM messages m
               JOIN agents a ON m.to_did = a.did
               WHERE a.owner_did = ?""",
            (owner_did,)
        ) as cursor:
            total = await cursor.fetchone()
            total_count = total[0] if total else 0

    messages = []
    for r in rows:
        profile = json.loads(r[9]) if r[9] else {}
        messages.append({
            "id": r[0],
            "from_did": r[1],
            "to_did": r[2],
            "to_agent_name": profile.get("name", ""),
            "content": r[3],
            "timestamp": r[4],
            "session_id": r[5] or "",
            "message_type": r[6],
            "protocol": r[7],
            "delivered": bool(r[8]),
        })
    return {"owner_did": owner_did, "messages": messages, "total": total_count}


async def fetch_owner_message_stats(owner_did: str) -> dict:
    """
    各子 Agent 的消息统计（未读数、最后消息时间）。
    返回 {owner_did, stats: [{did, name, unread_count, last_message_at}]}。
    """
    async with connect() as db:
        async with db.execute(
            """SELECT a.did, a.profile,
                      COUNT(CASE WHEN m.delivered = 0 THEN 1 END) as unread_count,
                      MAX(m.timestamp) as last_message_at
               FROM agents a
               LEFT JOIN messages m ON m.to_did = a.did
               WHERE a.owner_did = ?
               GROUP BY a.did
               ORDER BY unread_count DESC""",
            (owner_did,)
        ) as cursor:
            rows = await cursor.fetchall()

    stats = []
    for r in rows:
        profile = json.loads(r[1]) if r[1] else {}
        stats.append({
            "did": r[0],
            "name": profile.get("name", ""),
            "unread_count": r[2] or 0,
            "last_message_at": r[3] or None,
        })
    return {"owner_did": owner_did, "stats": stats}


async def search_agents_by_capability(keyword: str) -> list[dict]:
    async with connect() as db:
        async with db.execute(
            "SELECT did, profile FROM agents WHERE profile LIKE ?",
            (f"%{keyword}%",)
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"did": r[0], "profile": json.loads(r[1])} for r in rows]


async def update_agent_profile(did: str, fields: dict) -> bool:
    """更新已有 Agent 的 profile 字段，返回是否找到目标记录"""
    async with connect() as db:
        async with db.execute("SELECT profile FROM agents WHERE did=?", (did,)) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        profile = json.loads(row[0])
        # capabilities 支持追加或覆盖
        if "capabilities" in fields:
            profile["capabilities"] = fields.pop("capabilities")
        profile.update(fields)
        await db.execute(
            "UPDATE agents SET profile=?, last_seen=? WHERE did=?",
            (json.dumps(profile), time.time(), did)
        )
        await db.commit()
    return True


async def delete_agent(did: str) -> bool:
    """删除本地 Agent，返回是否找到目标记录"""
    async with connect() as db:
        async with db.execute("SELECT did FROM agents WHERE did=?", (did,)) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        await db.execute("DELETE FROM agents WHERE did=?", (did,))
        await db.commit()
    return True


async def add_certification(did: str, cert: dict) -> bool:
    """为 Agent 追加一条认证到 profile.certifications"""
    async with connect() as db:
        async with db.execute("SELECT profile FROM agents WHERE did=?", (did,)) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        profile = json.loads(row[0])
        certs = profile.setdefault("certifications", [])
        certs.append(cert)
        await db.execute(
            "UPDATE agents SET profile=? WHERE did=?",
            (json.dumps(profile), did)
        )
        await db.commit()
    return True


async def get_certifications(did: str) -> list[dict]:
    """获取 Agent 的所有认证"""
    async with connect() as db:
        async with db.execute("SELECT profile FROM agents WHERE did=?", (did,)) as cur:
            row = await cur.fetchone()
    if not row:
        return []
    profile = json.loads(row[0])
    return profile.get("certifications", [])


async def upsert_contact(did: str, endpoint: str, relay: str = None):
    async with connect() as db:
        await db.execute(
            "INSERT OR REPLACE INTO contacts (did, endpoint, relay, updated_at) VALUES (?, ?, ?, ?)",
            (did, endpoint, relay, time.time())
        )
        await db.commit()


async def get_contact(did: str) -> Optional[dict]:
    async with connect() as db:
        async with db.execute(
            "SELECT did, endpoint, relay FROM contacts WHERE did=?", (did,)
        ) as cursor:
            row = await cursor.fetchone()
    if row:
        return {"did": row[0], "endpoint": row[1], "relay": row[2]}
    return None

