"""
SQLite 本地存储层 - 通讯录、消息队列、Agent注册表
"""
import json
import time
import aiosqlite
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "agent_net.db"


async def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                did TEXT PRIMARY KEY,
                profile TEXT NOT NULL,
                is_local INTEGER DEFAULT 0,
                last_seen REAL,
                private_key_hex TEXT
            );
            -- 向后兼容：为旧数据库追加列（若已存在则忽略错误）

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_did TEXT NOT NULL,
                to_did TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                delivered INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS contacts (
                did TEXT PRIMARY KEY,
                endpoint TEXT,
                relay TEXT,
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS pending_requests (
                did TEXT PRIMARY KEY,
                init_packet TEXT NOT NULL,
                requested_at REAL NOT NULL,
                status TEXT DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS skills (
                skill_id TEXT PRIMARY KEY,
                agent_did TEXT NOT NULL,
                name TEXT NOT NULL,
                capabilities TEXT,
                actions TEXT NOT NULL,
                platform TEXT DEFAULT 'native',
                created_at REAL NOT NULL,
                FOREIGN KEY (agent_did) REFERENCES agents(did)
            );
        """)
        await db.commit()
        # 向后兼容：为旧数据库追加列（若已存在则忽略错误）
        for alter in [
            "ALTER TABLE agents ADD COLUMN private_key_hex TEXT",
            "ALTER TABLE messages ADD COLUMN session_id TEXT DEFAULT ''",
            "ALTER TABLE messages ADD COLUMN reply_to INTEGER DEFAULT NULL",
            "ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT NULL",
            "ALTER TABLE messages ADD COLUMN protocol TEXT DEFAULT NULL",
            "ALTER TABLE messages ADD COLUMN content_encoding TEXT DEFAULT NULL",
        ]:
            try:
                await db.execute(alter)
                await db.commit()
            except Exception:
                pass  # 列已存在，忽略


async def add_pending(did: str, init_packet: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO pending_requests (did, init_packet, requested_at, status) VALUES (?, ?, ?, 'pending')",
            (did, json.dumps(init_packet), time.time())
        )
        await db.commit()


async def list_pending() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT did, init_packet, requested_at, status FROM pending_requests WHERE status='pending' ORDER BY requested_at"
        ) as cur:
            rows = await cur.fetchall()
    return [{"did": r[0], "init_packet": json.loads(r[1]), "requested_at": r[2], "status": r[3]} for r in rows]


async def get_pending(did: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT did, init_packet, requested_at, status FROM pending_requests WHERE did=?", (did,)
        ) as cur:
            row = await cur.fetchone()
    if row:
        return {"did": row[0], "init_packet": json.loads(row[1]), "requested_at": row[2], "status": row[3]}
    return None


async def resolve_pending(did: str, action: str) -> bool:
    """action: 'allow' | 'deny'"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT did FROM pending_requests WHERE did=? AND status='pending'", (did,)) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        await db.execute("UPDATE pending_requests SET status=? WHERE did=?", (action, did))
        await db.commit()
    return True


async def register_agent(did: str, profile: dict, is_local: bool = True,
                         private_key_hex: Optional[str] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO agents (did, profile, is_local, last_seen, private_key_hex) VALUES (?, ?, ?, ?, ?)",
            (did, json.dumps(profile), int(is_local), time.time(), private_key_hex)
        )
        await db.commit()


async def store_private_key(did: str, private_key_hex: str):
    """持久化 Agent 私钥（hex）"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE agents SET private_key_hex=? WHERE did=?",
            (private_key_hex, did)
        )
        await db.commit()


async def get_private_key(did: str) -> Optional[str]:
    """获取 Agent 私钥 hex，未存储返回 None"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT private_key_hex FROM agents WHERE did=?", (did,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row and row[0] else None


async def list_local_agents() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT did, profile, last_seen FROM agents WHERE is_local=1"
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"did": r[0], "profile": json.loads(r[1]), "last_seen": r[2]} for r in rows]


async def get_agent(did: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT did, profile, is_local, last_seen FROM agents WHERE did=?", (did,)
        ) as cursor:
            row = await cursor.fetchone()
    if row:
        return {"did": row[0], "profile": json.loads(row[1]), "is_local": bool(row[2]), "last_seen": row[3]}
    return None


async def store_message(from_did: str, to_did: str, content: str,
                        session_id: str = "", reply_to: int | None = None,
                        message_type: str | None = None, protocol: str | None = None,
                        content_encoding: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (from_did, to_did, content, timestamp, session_id, reply_to, message_type, protocol, content_encoding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (from_did, to_did, content, time.time(), session_id, reply_to, message_type, protocol, content_encoding)
        )
        await db.commit()


async def fetch_inbox(did: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, from_did, content, timestamp, session_id, reply_to, message_type, protocol, content_encoding "
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
             "message_type": r[6], "protocol": r[7], "content_encoding": r[8]} for r in rows]


async def fetch_session(session_id: str) -> list[dict]:
    """按 session_id 查询完整会话历史（含已读消息）"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, from_did, to_did, content, timestamp, reply_to, delivered, message_type, protocol, content_encoding "
            "FROM messages WHERE session_id=? ORDER BY timestamp",
            (session_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"id": r[0], "from": r[1], "to": r[2], "content": r[3],
             "timestamp": r[4], "reply_to": r[5], "delivered": bool(r[6]),
             "message_type": r[7], "protocol": r[8], "content_encoding": r[9]} for r in rows]


async def search_agents_by_capability(keyword: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT did, profile FROM agents WHERE profile LIKE ?",
            (f"%{keyword}%",)
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"did": r[0], "profile": json.loads(r[1])} for r in rows]


async def update_agent_profile(did: str, fields: dict) -> bool:
    """更新已有 Agent 的 profile 字段，返回是否找到目标记录"""
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT did FROM agents WHERE did=?", (did,)) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        await db.execute("DELETE FROM agents WHERE did=?", (did,))
        await db.commit()
    return True


async def add_certification(did: str, cert: dict) -> bool:
    """为 Agent 追加一条认证到 profile.certifications"""
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT profile FROM agents WHERE did=?", (did,)) as cur:
            row = await cur.fetchone()
    if not row:
        return []
    profile = json.loads(row[0])
    return profile.get("certifications", [])


async def upsert_contact(did: str, endpoint: str, relay: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO contacts (did, endpoint, relay, updated_at) VALUES (?, ?, ?, ?)",
            (did, endpoint, relay, time.time())
        )
        await db.commit()


async def get_contact(did: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT did, endpoint, relay FROM contacts WHERE did=?", (did,)
        ) as cursor:
            row = await cursor.fetchone()
    if row:
        return {"did": row[0], "endpoint": row[1], "relay": row[2]}
    return None


# ── Skill Registry (ADR-010) ─────────────────────────────────────

async def register_skill(skill_id: str, agent_did: str, name: str,
                         capabilities: list[str], actions: list[str],
                         platform: str = "native") -> str:
    """注册 Skill，关联到具体 Agent"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO skills (skill_id, agent_did, name, capabilities, actions, platform, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (skill_id, agent_did, name, json.dumps(capabilities), json.dumps(actions), platform, time.time())
        )
        await db.commit()
    return skill_id


async def unregister_skill(skill_id: str) -> bool:
    """注销 Skill，返回是否找到目标记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT skill_id FROM skills WHERE skill_id=?", (skill_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        await db.execute("DELETE FROM skills WHERE skill_id=?", (skill_id,))
        await db.commit()
    return True


async def list_skills(agent_did: str = None, capability: str = None) -> list[dict]:
    """列出已注册 Skill，可按 Agent 或能力过滤"""
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
