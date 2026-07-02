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


# ── Skill Registry (ADR-010) ─────────────────────────────────────

async def register_skill(skill_id: str, agent_did: str, name: str,
                         capabilities: list[str], actions: list[str],
                         platform: str = "native") -> str:
    """注册 Skill，关联到具体 Agent"""
    async with connect() as db:
        await db.execute(
            "INSERT OR REPLACE INTO skills (skill_id, agent_did, name, capabilities, actions, platform, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (skill_id, agent_did, name, json.dumps(capabilities), json.dumps(actions), platform, time.time())
        )
        await db.commit()
    return skill_id


async def unregister_skill(skill_id: str) -> bool:
    """注销 Skill，返回是否找到目标记录"""
    async with connect() as db:
        async with db.execute("SELECT skill_id FROM skills WHERE skill_id=?", (skill_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        await db.execute("DELETE FROM skills WHERE skill_id=?", (skill_id,))
        await db.commit()
    return True


async def list_skills(agent_did: str = None, capability: str = None) -> list[dict]:
    """列出已注册 Skill，可按 Agent 或能力过滤"""
    async with connect() as db:
        query = "SELECT skill_id, agent_did, name, capabilities, actions, platform, created_at FROM skills"
        params = []
        conditions = []

        if agent_did:
            conditions.append("agent_did = ?")
            params.append(agent_did)
        if capability:
            conditions.append("capabilities LIKE ?")
            params.append(f'%"{capability}"%')

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC"

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    return [{
        "skill_id": r[0],
        "agent_did": r[1],
        "name": r[2],
        "capabilities": json.loads(r[3]) if r[3] else [],
        "actions": json.loads(r[4]) if r[4] else [],
        "platform": r[5],
        "created_at": r[6]
    } for r in rows]


async def get_skill(skill_id: str) -> Optional[dict]:
    """获取 Skill 详情"""
    async with connect() as db:
        async with db.execute(
            "SELECT skill_id, agent_did, name, capabilities, actions, platform, created_at FROM skills WHERE skill_id=?",
            (skill_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if row:
        return {
            "skill_id": row[0],
            "agent_did": row[1],
            "name": row[2],
            "capabilities": json.loads(row[3]) if row[3] else [],
            "actions": json.loads(row[4]) if row[4] else [],
            "platform": row[5],
            "created_at": row[6]
        }
    return None


# ── Push Registrations (ADR-012 L3/L5) ─────────────────────────────

async def create_push_registration(did: str, callback_url: str,
                                    callback_type: str = "webhook",
                                    push_key: str = None,
                                    expires_seconds: int = 3600) -> dict:
    """
    创建 Push 注册

    Args:
        did: Agent DID
        callback_url: 回调 URL
        callback_type: webhook / sse / platform
        push_key: 平台侧标识符（可选）
        expires_seconds: 过期时间（秒），默认 1 小时

    Returns:
        dict: 包含 registration_id, callback_secret, expires_at
    """
    registration_id = f"reg_{uuid.uuid4().hex[:16]}"
    callback_secret = f"sk_{secrets.token_hex(24)}"
    expires_at = time.time() + expires_seconds
    created_at = time.time()

    async with connect() as db:
        # 删除同一 DID + URL + type 的旧注册
        await db.execute(
            "DELETE FROM push_registrations WHERE did=? AND callback_url=? AND callback_type=?",
            (did, callback_url, callback_type)
        )
        await db.execute(
            "INSERT INTO push_registrations (registration_id, did, callback_url, callback_type, callback_secret, push_key, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (registration_id, did, callback_url, callback_type, callback_secret, push_key, expires_at, created_at)
        )
        await db.commit()

    return {
        "registration_id": registration_id,
        "callback_secret": callback_secret,
        "expires_at": expires_at,
        "created_at": created_at,
    }


async def get_active_push_registrations(did: str) -> list[dict]:
    """获取 DID 的所有有效 Push 注册（未过期）"""
    now = time.time()
    async with connect() as db:
        async with db.execute(
            "SELECT registration_id, did, callback_url, callback_type, callback_secret, push_key, expires_at, created_at "
            "FROM push_registrations WHERE did=? AND expires_at > ?",
            (did, now)
        ) as cursor:
            rows = await cursor.fetchall()

    return [{
        "registration_id": r[0],
        "did": r[1],
        "callback_url": r[2],
        "callback_type": r[3],
        "callback_secret": r[4],
        "push_key": r[5],
        "expires_at": r[6],
        "created_at": r[7],
    } for r in rows]


async def get_push_registration(did: str) -> Optional[dict]:
    """获取 DID 的单个有效注册（返回最新的一个）"""
    regs = await get_active_push_registrations(did)
    if regs:
        return regs[0]
    return None


async def refresh_push_registration(did: str, callback_url: str,
                                     callback_type: str = "webhook",
                                     expires_seconds: int = 3600) -> Optional[float]:
    """
    续约 Push 注册的 TTL

    Returns:
        新的 expires_at，或 None 如果注册不存在
    """
    now = time.time()
    new_expires_at = now + expires_seconds

    async with connect() as db:
        result = await db.execute(
            "UPDATE push_registrations SET expires_at=? WHERE did=? AND callback_url=? AND callback_type=? AND expires_at > ?",
            (new_expires_at, did, callback_url, callback_type, now)
        )
        await db.commit()
        if result.rowcount > 0:
            return new_expires_at
    return None


async def delete_push_registration(did: str, callback_url: str = None,
                                    callback_type: str = None) -> int:
    """
    删除 Push 注册

    Args:
        did: Agent DID
        callback_url: 可选，不提供则删除该 DID 的所有注册
        callback_type: 可选，配合 callback_url 使用

    Returns:
        删除的记录数
    """
    async with connect() as db:
        if callback_url and callback_type:
            result = await db.execute(
                "DELETE FROM push_registrations WHERE did=? AND callback_url=? AND callback_type=?",
                (did, callback_url, callback_type)
            )
        elif callback_url:
            result = await db.execute(
                "DELETE FROM push_registrations WHERE did=? AND callback_url=?",
                (did, callback_url)
            )
        else:
            result = await db.execute(
                "DELETE FROM push_registrations WHERE did=?",
                (did,)
            )
        await db.commit()
        return result.rowcount


async def cleanup_expired_push_registrations() -> int:
    """清理所有过期的 Push 注册，返回删除的记录数"""
    now = time.time()
    async with connect() as db:
        result = await db.execute(
            "DELETE FROM push_registrations WHERE expires_at <= ?",
            (now,)
        )
        await db.commit()
        return result.rowcount
