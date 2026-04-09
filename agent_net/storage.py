"""
SQLite 本地存储层 - 通讯录、消息队列、Agent注册表、Push注册表
"""
import json
import time
import uuid
import secrets
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

            CREATE TABLE IF NOT EXISTS push_registrations (
                registration_id TEXT PRIMARY KEY,
                did TEXT NOT NULL,
                callback_url TEXT NOT NULL,
                callback_type TEXT DEFAULT 'webhook',
                callback_secret TEXT NOT NULL,
                push_key TEXT,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(did, callback_url, callback_type)
            );
            CREATE INDEX IF NOT EXISTS idx_push_registrations_did ON push_registrations(did);
            CREATE INDEX IF NOT EXISTS idx_push_registrations_expires ON push_registrations(expires_at);
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

    # 初始化 Enclave 相关表
    await init_enclave_tables()


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

    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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

    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
        if callback_url and callback_type:
            result = await db.execute(
                "DELETE FROM push_registrations WHERE did=? AND callback_url=? AND callback_type=?",
                (did, callback_url, callback_type)
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
    async with aiosqlite.connect(DB_PATH) as db:
        result = await db.execute(
            "DELETE FROM push_registrations WHERE expires_at <= ?",
            (now,)
        )
        await db.commit()
        return result.rowcount


# ── Enclave Tables (ADR-013) ────────────────────────────────────────

async def init_enclave_tables():
    """初始化 Enclave 相关表（在 init_db 中调用）"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            -- Enclave 项目组
            CREATE TABLE IF NOT EXISTS enclaves (
                enclave_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                owner_did TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                vault_backend TEXT DEFAULT 'local',
                vault_config TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            -- 成员 + 角色
            CREATE TABLE IF NOT EXISTS enclave_members (
                enclave_id TEXT NOT NULL,
                did TEXT NOT NULL,
                role TEXT NOT NULL,
                permissions TEXT DEFAULT 'rw',
                handbook TEXT,
                joined_at REAL NOT NULL,
                PRIMARY KEY (enclave_id, did),
                FOREIGN KEY (enclave_id) REFERENCES enclaves(enclave_id)
            );

            -- Playbook 定义
            CREATE TABLE IF NOT EXISTS playbooks (
                playbook_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                stages TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_by TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            -- Playbook 执行实例
            CREATE TABLE IF NOT EXISTS playbook_runs (
                run_id TEXT PRIMARY KEY,
                enclave_id TEXT NOT NULL,
                playbook_id TEXT NOT NULL,
                playbook_name TEXT DEFAULT '',
                current_stage TEXT,
                status TEXT DEFAULT 'running',
                context TEXT DEFAULT '{}',
                started_at REAL NOT NULL,
                completed_at REAL,
                FOREIGN KEY (enclave_id) REFERENCES enclaves(enclave_id),
                FOREIGN KEY (playbook_id) REFERENCES playbooks(playbook_id)
            );

            -- 阶段执行记录
            CREATE TABLE IF NOT EXISTS stage_executions (
                run_id TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                assigned_did TEXT,
                status TEXT DEFAULT 'pending',
                task_id TEXT,
                output_ref TEXT,
                started_at REAL,
                completed_at REAL,
                PRIMARY KEY (run_id, stage_name),
                FOREIGN KEY (run_id) REFERENCES playbook_runs(run_id)
            );

            -- Vault 存储（LocalVaultBackend 使用）
            CREATE TABLE IF NOT EXISTS enclave_vault (
                enclave_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                updated_by TEXT NOT NULL,
                updated_at REAL NOT NULL,
                message TEXT DEFAULT '',
                PRIMARY KEY (enclave_id, key)
            );

            -- Vault 历史版本
            CREATE TABLE IF NOT EXISTS enclave_vault_history (
                enclave_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                version INTEGER NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at REAL NOT NULL,
                message TEXT DEFAULT '',
                action TEXT DEFAULT 'update'  -- create / update / delete
            );

            -- 索引
            CREATE INDEX IF NOT EXISTS idx_enclaves_owner ON enclaves(owner_did);
            CREATE INDEX IF NOT EXISTS idx_enclaves_status ON enclaves(status);
            CREATE INDEX IF NOT EXISTS idx_enclave_members_did ON enclave_members(did);
            CREATE INDEX IF NOT EXISTS idx_playbook_runs_enclave ON playbook_runs(enclave_id);
            CREATE INDEX IF NOT EXISTS idx_playbook_runs_status ON playbook_runs(status);
            CREATE INDEX IF NOT EXISTS idx_stage_executions_task ON stage_executions(task_id);
            CREATE INDEX IF NOT EXISTS idx_vault_history_enclave_key ON enclave_vault_history(enclave_id, key);
        """)
        await db.commit()


# ── Enclave CRUD ─────────────────────────────────────────────────────

async def create_enclave(
    enclave_id: str,
    name: str,
    owner_did: str,
    vault_backend: str = "local",
    vault_config: dict = None,
) -> str:
    """创建 Enclave"""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO enclaves
               (enclave_id, name, owner_did, vault_backend, vault_config, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (enclave_id, name, owner_did, vault_backend, json.dumps(vault_config or {}), now, now)
        )
        await db.commit()
    return enclave_id


async def get_enclave(enclave_id: str) -> Optional[dict]:
    """获取 Enclave 详情"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM enclaves WHERE enclave_id = ?", (enclave_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "enclave_id": row["enclave_id"],
        "name": row["name"],
        "owner_did": row["owner_did"],
        "status": row["status"],
        "vault_backend": row["vault_backend"],
        "vault_config": json.loads(row["vault_config"] or "{}"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def list_enclaves(did: str = None, status: str = None) -> list[dict]:
    """列出 Enclave，可按成员 DID 或状态过滤"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if did:
            # 按成员 DID 查询
            query = """
                SELECT e.* FROM enclaves e
                JOIN enclave_members em ON e.enclave_id = em.enclave_id
                WHERE em.did = ?
            """
            params = [did]
            if status:
                query += " AND e.status = ?"
                params.append(status)
        else:
            query = "SELECT * FROM enclaves"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status)
        query += " ORDER BY created_at DESC"

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    return [{
        "enclave_id": r["enclave_id"],
        "name": r["name"],
        "owner_did": r["owner_did"],
        "status": r["status"],
        "vault_backend": r["vault_backend"],
        "vault_config": json.loads(r["vault_config"] or "{}"),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    } for r in rows]


async def update_enclave(enclave_id: str, **kwargs) -> bool:
    """更新 Enclave 属性"""
    allowed = {"name", "status", "vault_backend", "vault_config"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    updates["updated_at"] = time.time()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [enclave_id]

    async with aiosqlite.connect(DB_PATH) as db:
        result = await db.execute(
            f"UPDATE enclaves SET {set_clause} WHERE enclave_id = ?", values
        )
        await db.commit()
        return result.rowcount > 0


async def delete_enclave(enclave_id: str) -> bool:
    """归档 Enclave（软删除）"""
    return await update_enclave(enclave_id, status="archived")


# ── Enclave Members CRUD ────────────────────────────────────────────

async def add_enclave_member(
    enclave_id: str,
    did: str,
    role: str,
    permissions: str = "rw",
    handbook: str = "",
) -> bool:
    """添加成员"""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO enclave_members
                   (enclave_id, did, role, permissions, handbook, joined_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (enclave_id, did, role, permissions, handbook, now)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False  # 已存在


async def get_enclave_member(enclave_id: str, did: str) -> Optional[dict]:
    """获取单个成员"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM enclave_members WHERE enclave_id = ? AND did = ?",
            (enclave_id, did)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "enclave_id": row["enclave_id"],
        "did": row["did"],
        "role": row["role"],
        "permissions": row["permissions"],
        "handbook": row["handbook"] or "",
        "joined_at": row["joined_at"],
    }


async def list_enclave_members(enclave_id: str) -> list[dict]:
    """列出 Enclave 所有成员"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM enclave_members WHERE enclave_id = ? ORDER BY joined_at",
            (enclave_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    return [{
        "enclave_id": r["enclave_id"],
        "did": r["did"],
        "role": r["role"],
        "permissions": r["permissions"],
        "handbook": r["handbook"] or "",
        "joined_at": r["joined_at"],
    } for r in rows]


async def update_enclave_member(enclave_id: str, did: str, **kwargs) -> bool:
    """更新成员属性"""
    allowed = {"role", "permissions", "handbook"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [enclave_id, did]

    async with aiosqlite.connect(DB_PATH) as db:
        result = await db.execute(
            f"UPDATE enclave_members SET {set_clause} WHERE enclave_id = ? AND did = ?",
            values
        )
        await db.commit()
        return result.rowcount > 0


async def remove_enclave_member(enclave_id: str, did: str) -> bool:
    """移除成员"""
    async with aiosqlite.connect(DB_PATH) as db:
        result = await db.execute(
            "DELETE FROM enclave_members WHERE enclave_id = ? AND did = ?",
            (enclave_id, did)
        )
        await db.commit()
        return result.rowcount > 0


# ── Vault Operations ──────────────────────────────────────────────────

async def vault_get(enclave_id: str, key: str, version: int = None) -> Optional[dict]:
    """读取 Vault 文档"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if version:
            async with db.execute(
                """SELECT * FROM enclave_vault_history
                   WHERE enclave_id = ? AND key = ? AND version = ?""",
                (enclave_id, key, version)
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute(
                "SELECT * FROM enclave_vault WHERE enclave_id = ? AND key = ?",
                (enclave_id, key)
            ) as cursor:
                row = await cursor.fetchone()

    if not row:
        return None
    return {
        "key": row["key"],
        "value": row["value"],
        "version": row["version"],
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
        "message": row["message"] or "",
    }


async def vault_put(
    enclave_id: str,
    key: str,
    value: str,
    author_did: str,
    message: str = "",
) -> dict:
    """写入 Vault 文档"""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        # 检查是否已存在
        async with db.execute(
            "SELECT version FROM enclave_vault WHERE enclave_id = ? AND key = ?",
            (enclave_id, key)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            new_version = row[0] + 1
            action = "update"
            await db.execute(
                """UPDATE enclave_vault
                   SET value = ?, version = ?, updated_by = ?, updated_at = ?, message = ?
                   WHERE enclave_id = ? AND key = ?""",
                (value, new_version, author_did, now, message, enclave_id, key)
            )
        else:
            new_version = 1
            action = "create"
            await db.execute(
                """INSERT INTO enclave_vault
                   (enclave_id, key, value, version, updated_by, updated_at, message)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (enclave_id, key, value, new_version, author_did, now, message)
            )

        # 写入历史
        await db.execute(
            """INSERT INTO enclave_vault_history
               (enclave_id, key, value, version, updated_by, updated_at, message, action)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (enclave_id, key, value, new_version, author_did, now, message, action)
        )

        await db.commit()

    return {
        "key": key,
        "version": new_version,
        "updated_by": author_did,
        "updated_at": now,
        "action": action,
    }


async def vault_list(enclave_id: str, prefix: str = "") -> list[dict]:
    """列出 Vault 文档"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if prefix:
            async with db.execute(
                """SELECT key, version, updated_by, updated_at, message
                   FROM enclave_vault
                   WHERE enclave_id = ? AND key LIKE ?
                   ORDER BY key""",
                (enclave_id, f"{prefix}%")
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """SELECT key, version, updated_by, updated_at, message
                   FROM enclave_vault WHERE enclave_id = ? ORDER BY key""",
                (enclave_id,)
            ) as cursor:
                rows = await cursor.fetchall()

    return [{
        "key": r["key"],
        "version": r["version"],
        "updated_by": r["updated_by"],
        "updated_at": r["updated_at"],
        "message": r["message"] or "",
    } for r in rows]


async def vault_history(enclave_id: str, key: str, limit: int = 10) -> list[dict]:
    """查看文档历史"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT version, updated_by, updated_at, message, action
               FROM enclave_vault_history
               WHERE enclave_id = ? AND key = ?
               ORDER BY version DESC LIMIT ?""",
            (enclave_id, key, limit)
        ) as cursor:
            rows = await cursor.fetchall()

    return [{
        "key": key,
        "version": r["version"],
        "updated_by": r["updated_by"],
        "updated_at": r["updated_at"],
        "message": r["message"] or "",
        "action": r["action"] or "update",
    } for r in rows]


async def vault_delete(enclave_id: str, key: str, author_did: str) -> bool:
    """删除 Vault 文档"""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        # 检查是否存在
        async with db.execute(
            "SELECT version FROM enclave_vault WHERE enclave_id = ? AND key = ?",
            (enclave_id, key)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return False

        # 写入历史（标记删除）
        await db.execute(
            """INSERT INTO enclave_vault_history
               (enclave_id, key, value, version, updated_by, updated_at, message, action)
               VALUES (?, ?, '', ?, ?, ?, '', 'delete')""",
            (enclave_id, key, row[0] + 1, author_did, now)
        )

        # 删除
        await db.execute(
            "DELETE FROM enclave_vault WHERE enclave_id = ? AND key = ?",
            (enclave_id, key)
        )
        await db.commit()
        return True


# ── Playbook Operations ──────────────────────────────────────────────

async def create_playbook(
    playbook_id: str,
    name: str,
    stages: list[dict],
    description: str = "",
    created_by: str = "",
) -> str:
    """创建 Playbook"""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO playbooks
               (playbook_id, name, stages, description, created_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (playbook_id, name, json.dumps(stages), description, created_by, now)
        )
        await db.commit()
    return playbook_id


async def get_playbook(playbook_id: str) -> Optional[dict]:
    """获取 Playbook"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM playbooks WHERE playbook_id = ?", (playbook_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "playbook_id": row["playbook_id"],
        "name": row["name"],
        "stages": json.loads(row["stages"]),
        "description": row["description"] or "",
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


async def create_playbook_run(
    run_id: str,
    enclave_id: str,
    playbook_id: str,
    playbook_name: str = "",
) -> str:
    """创建 Playbook 执行实例"""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO playbook_runs
               (run_id, enclave_id, playbook_id, playbook_name, started_at)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, enclave_id, playbook_id, playbook_name, now)
        )
        await db.commit()
    return run_id


async def get_playbook_run(run_id: str) -> Optional[dict]:
    """获取 Playbook 执行实例"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM playbook_runs WHERE run_id = ?", (run_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "enclave_id": row["enclave_id"],
        "playbook_id": row["playbook_id"],
        "playbook_name": row["playbook_name"],
        "current_stage": row["current_stage"] or "",
        "status": row["status"],
        "context": json.loads(row["context"] or "{}"),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


async def get_latest_playbook_run(enclave_id: str) -> Optional[dict]:
    """获取 Enclave 最新的 Playbook 执行实例"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM playbook_runs
               WHERE enclave_id = ?
               ORDER BY started_at DESC
               LIMIT 1""",
            (enclave_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "enclave_id": row["enclave_id"],
        "playbook_id": row["playbook_id"],
        "playbook_name": row["playbook_name"],
        "current_stage": row["current_stage"] or "",
        "status": row["status"],
        "context": json.loads(row["context"] or "{}"),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


async def update_playbook_run(run_id: str, **kwargs) -> bool:
    """更新 Playbook 执行实例"""
    allowed = {"current_stage", "status", "context", "completed_at"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    # 处理 context 的 JSON 序列化
    if "context" in updates:
        updates["context"] = json.dumps(updates["context"])

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [run_id]

    async with aiosqlite.connect(DB_PATH) as db:
        result = await db.execute(
            f"UPDATE playbook_runs SET {set_clause} WHERE run_id = ?", values
        )
        await db.commit()
        return result.rowcount > 0


async def create_stage_execution(
    run_id: str,
    stage_name: str,
    assigned_did: str = "",
    task_id: str = "",
) -> bool:
    """创建阶段执行记录"""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO stage_executions
                   (run_id, stage_name, assigned_did, status, task_id, started_at)
                   VALUES (?, ?, ?, 'active', ?, ?)""",
                (run_id, stage_name, assigned_did, task_id, now)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_stage_execution(run_id: str, stage_name: str) -> Optional[dict]:
    """获取阶段执行记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM stage_executions WHERE run_id = ? AND stage_name = ?",
            (run_id, stage_name)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "stage_name": row["stage_name"],
        "assigned_did": row["assigned_did"] or "",
        "status": row["status"],
        "task_id": row["task_id"] or "",
        "output_ref": row["output_ref"] or "",
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


async def get_stage_execution_by_task(task_id: str) -> Optional[dict]:
    """通过 task_id 获取阶段执行记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM stage_executions WHERE task_id = ?",
            (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "stage_name": row["stage_name"],
        "assigned_did": row["assigned_did"] or "",
        "status": row["status"],
        "task_id": row["task_id"] or "",
        "output_ref": row["output_ref"] or "",
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


async def update_stage_execution(run_id: str, stage_name: str, **kwargs) -> bool:
    """更新阶段执行记录"""
    allowed = {"status", "output_ref", "completed_at"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [run_id, stage_name]

    async with aiosqlite.connect(DB_PATH) as db:
        result = await db.execute(
            f"UPDATE stage_executions SET {set_clause} WHERE run_id = ? AND stage_name = ?",
            values
        )
        await db.commit()
        return result.rowcount > 0


async def list_stage_executions(run_id: str) -> list[dict]:
    """列出 Playbook Run 的所有阶段"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM stage_executions WHERE run_id = ? ORDER BY started_at",
            (run_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    return [{
        "run_id": r["run_id"],
        "stage_name": r["stage_name"],
        "assigned_did": r["assigned_did"] or "",
        "status": r["status"],
        "task_id": r["task_id"] or "",
        "output_ref": r["output_ref"] or "",
        "started_at": r["started_at"],
        "completed_at": r["completed_at"],
    } for r in rows]
