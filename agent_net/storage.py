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
        """)
        await db.commit()
        # 向后兼容：为旧数据库追加 private_key_hex 列
        try:
            await db.execute("ALTER TABLE agents ADD COLUMN private_key_hex TEXT")
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


async def store_message(from_did: str, to_did: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (from_did, to_did, content, timestamp) VALUES (?, ?, ?, ?)",
            (from_did, to_did, content, time.time())
        )
        await db.commit()


async def fetch_inbox(did: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, from_did, content, timestamp FROM messages WHERE to_did=? AND delivered=0 ORDER BY timestamp",
            (did,)
        ) as cursor:
            rows = await cursor.fetchall()
        if rows:
            ids = [r[0] for r in rows]
            await db.execute(
                f"UPDATE messages SET delivered=1 WHERE id IN ({','.join('?'*len(ids))})", ids
            )
            await db.commit()
    return [{"id": r[0], "from": r[1], "content": r[2], "timestamp": r[3]} for r in rows]


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
