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
            "ALTER TABLE agents ADD COLUMN owner_did TEXT DEFAULT NULL",
            "ALTER TABLE messages ADD COLUMN session_id TEXT DEFAULT ''",
            "ALTER TABLE messages ADD COLUMN reply_to INTEGER DEFAULT NULL",
            "ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT NULL",
            "ALTER TABLE messages ADD COLUMN protocol TEXT DEFAULT NULL",
            "ALTER TABLE messages ADD COLUMN content_encoding TEXT DEFAULT NULL",
            "ALTER TABLE agents ADD COLUMN worker_type TEXT DEFAULT 'resident'",
            "ALTER TABLE messages ADD COLUMN message_id TEXT",
        ]:
            try:
                await db.execute(alter)
                await db.commit()
            except Exception:
                pass  # 列已存在，忽略

        # 向后兼容：添加索引（若已存在则忽略错误）
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents(owner_did)",
        ]:
            try:
                await db.execute(idx)
                await db.commit()
            except Exception:
                pass

    # 初始化 Enclave 相关表
    await init_enclave_tables()

    # 初始化秘书编排相关表
    await init_secretary_tables()

    # 初始化信任网络相关表
    await init_trust_tables()


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
                         private_key_hex: Optional[str] = None,
                         worker_type: str = "resident"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO agents (did, profile, is_local, last_seen, private_key_hex, worker_type) VALUES (?, ?, ?, ?, ?, ?)",
            (did, json.dumps(profile), int(is_local), time.time(), private_key_hex, worker_type)
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
            "SELECT did, profile, is_local, last_seen, owner_did, worker_type FROM agents WHERE did=?", (did,)
        ) as cursor:
            row = await cursor.fetchone()
    if row:
        return {"did": row[0], "profile": json.loads(row[1]), "is_local": bool(row[2]), "last_seen": row[3], "owner_did": row[4], "worker_type": row[5]}
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Owner（个人主 DID）相关函数 — v1.0-04
# ══════════════════════════════════════════════════════════════════════════════

async def register_owner(name: str) -> dict:
    """
    注册个人主 DID。
    返回 {did, public_key_hex, profile}。
    """
    from agent_net.common.did import DIDGenerator, AgentProfile
    from agent_net.node._config import get_relay_url, get_public_endpoint_cached, NODE_PORT

    agent_did_obj, _ = DIDGenerator.create_agentnexus(name)
    did = agent_did_obj.did
    signing_key = agent_did_obj.private_key

    _public_endpoint = get_public_endpoint_cached()
    endpoint = f"http://localhost:{NODE_PORT}"
    if _public_endpoint:
        endpoint = f"http://{_public_endpoint['public_ip']}:{_public_endpoint['public_port']}"

    RELAY_URL = get_relay_url()
    profile = AgentProfile(
        id=did, name=name, type="owner",
        capabilities=[], location=None,
        endpoints={"p2p": endpoint, "relay": RELAY_URL},
    )
    profile_dict = profile.to_dict()
    profile_dict["public_key_hex"] = signing_key.verify_key.encode().hex()

    from nacl.encoding import HexEncoder
    pk_hex = signing_key.encode(HexEncoder).decode()
    await register_agent(did, profile_dict, is_local=True, private_key_hex=pk_hex)

    return {"did": did, "public_key_hex": pk_hex, "profile": profile_dict}


async def register_secretary(owner_did: str, name: str = "Secretary") -> dict:
    """
    D-SEC-02: 在指定 owner 下注册一个秘书子 Agent。
    秘书的 profile.type = "secretary"，worker_type = "resident"。
    返回 {did, public_key_hex, profile}。
    """
    from agent_net.common.did import DIDGenerator, AgentProfile
    from agent_net.node._config import get_relay_url, get_public_endpoint_cached, NODE_PORT

    agent_did_obj, _ = DIDGenerator.create_agentnexus(name)
    did = agent_did_obj.did
    signing_key = agent_did_obj.private_key

    _public_endpoint = get_public_endpoint_cached()
    endpoint = f"http://localhost:{NODE_PORT}"
    if _public_endpoint:
        endpoint = f"http://{_public_endpoint['public_ip']}:{_public_endpoint['public_port']}"

    RELAY_URL = get_relay_url()
    profile = AgentProfile(
        id=did, name=name, type="secretary",
        capabilities=["orchestrate", "intake", "dispatch"], location=None,
        endpoints={"p2p": endpoint, "relay": RELAY_URL},
    )
    profile_dict = profile.to_dict()
    profile_dict["public_key_hex"] = signing_key.verify_key.encode().hex()

    from nacl.encoding import HexEncoder
    pk_hex = signing_key.encode(HexEncoder).decode()
    await register_agent(did, profile_dict, is_local=True, private_key_hex=pk_hex, worker_type="resident")

    # 绑定到 owner
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE agents SET owner_did=? WHERE did=?", (owner_did, did))
        await db.commit()

    return {"did": did, "public_key_hex": pk_hex, "profile": profile_dict}


async def bind_agent(owner_did: str, agent_did: str) -> bool:
    """
    将 Agent 绑定到主 DID。
    返回 True 表示成功，False 表示 Agent 不存在或已是其他 owner 的子 Agent。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # 检查 agent 存在且未绑定
        async with db.execute(
            "SELECT did, owner_did FROM agents WHERE did=?", (agent_did,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        if row[1] is not None and row[1] != owner_did:
            return False  # 已绑定到其他 owner

        await db.execute(
            "UPDATE agents SET owner_did=? WHERE did=?", (owner_did, agent_did)
        )
        await db.commit()
    return True


async def unbind_agent(owner_did: str, agent_did: str) -> bool:
    """
    解绑 Agent 与主 DID 的关系。
    返回 True 表示成功，False 表示关系不存在。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT did FROM agents WHERE did=? AND owner_did=?", (agent_did, owner_did)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return False

        await db.execute(
            "UPDATE agents SET owner_did=NULL WHERE did=?", (agent_did,)
        )
        await db.commit()
    return True


async def list_owned_agents(owner_did: str) -> list[dict]:
    """
    列出主 DID 下的所有子 Agent。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT did, profile, last_seen FROM agents WHERE owner_did=? ORDER BY last_seen DESC",
            (owner_did,)
        ) as cur:
            rows = await cur.fetchall()
    return [{"did": r[0], "profile": json.loads(r[1]), "last_seen": r[2]} for r in rows]


async def list_workers(owner_did: str) -> list[dict]:
    """
    D-SEC-01: 返回 owner 下所有非秘书子 Agent 的 Worker Registry 信息。
    包含 did / worker_type / profile_type / capabilities / tags / online / last_seen。
    在线判定：router.is_local(did) 为真则视为在线。
    """
    from agent_net.router import router as _router

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT did, profile, last_seen, worker_type FROM agents "
            "WHERE owner_did=? ORDER BY last_seen DESC",
            (owner_did,),
        ) as cur:
            rows = await cur.fetchall()

    result = []
    for r in rows:
        profile = json.loads(r[1])
        if profile.get("type") == "secretary":
            continue
        result.append({
            "did": r[0],
            "worker_type": r[3] or "resident",
            "profile_type": profile.get("type", "agent"),
            "capabilities": profile.get("capabilities", []),
            "tags": profile.get("tags", []),
            "last_seen": r[2],
            "online": _router.is_local(r[0]),
        })
    return result


async def set_worker_type(did: str, worker_type: str) -> bool:
    """D-SEC-01: 设置 Agent 的 worker_type。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE agents SET worker_type=? WHERE did=?",
            (worker_type, did),
        )
        await db.commit()
    return True


# ── Phase B: Worker Presence & Registry v2 ──────────────────────────

async def get_worker_presence(did: str, heartbeat_ttl: float = 300.0) -> dict:
    """D-SEC-01 Phase B: 获取 Worker 的 presence 状态。

    返回:
        presence: available / busy / offline / blocked / needs_human
        presence_source: local / push / heartbeat / manual
        presence_ttl: remote 的剩余有效秒数；local 为 null
        active_run_id: 当前活跃的 run_id，无则为 null
        active_stage: 当前活跃的 stage_name，无则为 null
        load: active stage_execution 数量
    """
    from agent_net.router import router as _router

    agent = await get_agent(did)
    if not agent:
        return {"presence": "offline", "presence_source": "local", "presence_ttl": None,
                "active_run_id": None, "active_stage": None, "load": 0}

    is_local = _router.is_local(did)
    last_seen = agent.get("last_seen", 0)
    now = time.time()

    # 检查是否被手动标记为 blocked
    from agent_net.storage import _WORKER_BLOCKED
    is_blocked = _WORKER_BLOCKED.get(did, False)

    # 计算 load — active stage_execution 数量
    load = await _count_active_stage_executions(did)

    # 判定 active run
    active_run_id = None
    active_stage = None
    if load > 0:
        active_info = await _get_active_stage_info(did)
        if active_info:
            active_run_id = active_info["run_id"]
            active_stage = active_info["stage_name"]

    # Presence 判定
    if is_blocked:
        presence = "blocked"
        presence_source = "manual"
        presence_ttl_val = None
    elif is_local:
        # 本地 Agent：实时判定
        presence = "busy" if load > 0 else "available"
        presence_source = "local"
        presence_ttl_val = None
    elif last_seen and (now - last_seen) < heartbeat_ttl:
        # 远端但心跳有效
        presence = "busy" if load > 0 else "available"
        presence_source = "heartbeat"
        presence_ttl_val = max(0, heartbeat_ttl - (now - last_seen))
    else:
        # 检查 Push registration
        try:
            regs = await get_active_push_registrations(did)
            if regs:
                presence = "busy" if load > 0 else "available"
                presence_source = "push"
                presence_ttl_val = None  # Push TTL 由注册过期决定
            else:
                presence = "offline"
                presence_source = "local"
                presence_ttl_val = None
        except Exception:
            presence = "offline"
            presence_source = "local"
            presence_ttl_val = None

    # 如果有 active run 但处于 failed/paused 状态，标记 needs_human
    if active_run_id and presence not in ("blocked", "needs_human"):
        run = await get_playbook_run(active_run_id)
        if run and run.get("status") in ("failed", "paused"):
            presence = "needs_human"

    return {
        "presence": presence,
        "presence_source": presence_source,
        "presence_ttl": round(presence_ttl_val, 1) if presence_ttl_val is not None else None,
        "active_run_id": active_run_id,
        "active_stage": active_stage,
        "load": load,
    }


# 手动标记 blocked 的内存存储（Phase B 简单实现）
_WORKER_BLOCKED: dict[str, str] = {}


async def set_worker_blocked(did: str, blocked: bool, reason: str = "") -> bool:
    """D-SEC-01 Phase B: 手动标记 Worker 为 blocked 或解除。"""
    agent = await get_agent(did)
    if not agent:
        return False
    if blocked:
        _WORKER_BLOCKED[did] = reason
    else:
        _WORKER_BLOCKED.pop(did, None)
    return True


async def list_workers_v2(
    owner_did: str,
    role: str = None,
    presence: str = None,
    heartbeat_ttl: float = 300.0,
) -> list[dict]:
    """D-SEC-01 Phase B: 返回 owner 下所有非秘书子 Agent 的 Worker Registry 信息（含 presence）。

    支持按 role（capabilities/profile_type 匹配）和 presence 状态过滤。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT did, profile, last_seen, worker_type, owner_did FROM agents "
            "WHERE owner_did=? ORDER BY last_seen DESC",
            (owner_did,),
        ) as cur:
            rows = await cur.fetchall()

    result = []
    for r in rows:
        profile = json.loads(r[1])
        if profile.get("type") == "secretary":
            continue

        did = r[0]
        presence_info = await get_worker_presence(did, heartbeat_ttl)

        # Presence 过滤
        if presence and presence_info["presence"] != presence:
            continue

        # Role 过滤：匹配 capabilities 或 profile_type
        if role:
            caps = [c.lower() for c in profile.get("capabilities", [])]
            profile_type = profile.get("type", "").lower()
            if role.lower() not in caps and role.lower() != profile_type:
                continue

        result.append({
            "did": did,
            "owner_did": r[4],
            "worker_type": r[3] or "resident",
            "profile_type": profile.get("type", "agent"),
            "capabilities": profile.get("capabilities", []),
            "tags": profile.get("tags", []),
            "last_seen": r[2],
            "presence": presence_info["presence"],
            "presence_source": presence_info["presence_source"],
            "presence_ttl": presence_info["presence_ttl"],
            "active_run_id": presence_info["active_run_id"],
            "active_stage": presence_info["active_stage"],
            "load": presence_info["load"],
        })
    return result


async def _count_active_stage_executions(did: str) -> int:
    """计算 Worker 当前活跃的 stage_execution 数量。"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM stage_executions WHERE assigned_did=? AND status='active'",
            (did,),
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def _get_active_stage_info(did: str) -> Optional[dict]:
    """获取 Worker 当前活跃的 stage 信息。"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT run_id, stage_name FROM stage_executions "
            "WHERE assigned_did=? AND status='active' ORDER BY started_at DESC LIMIT 1",
            (did,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return {"run_id": row[0], "stage_name": row[1]}


async def get_owner(owner_did: str) -> Optional[dict]:
    """
    获取主 DID 信息（验证它是 owner 类型）。
    """
    agent = await get_agent(owner_did)
    if not agent:
        return None
    profile = agent.get("profile", {})
    if profile.get("type") != "owner":
        return None
    return agent


# ══════════════════════════════════════════════════════════════════════════════
# Capability Token CRUD — v1.0-08
# ══════════════════════════════════════════════════════════════════════════════

async def save_capability_token(token: dict) -> str:
    """
    保存 Capability Token 到数据库。
    返回 token_id。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO capability_tokens (
                token_id, version, issuer_did, subject_did, enclave_id,
                scope_json, constraints_json, validity_json, revocation_endpoint,
                evaluated_constraint_hash, signature, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                token["token_id"],
                token.get("version", 1),
                token["issuer_did"],
                token["subject_did"],
                token.get("enclave_id"),
                json.dumps(token["scope"]),
                json.dumps(token["constraints"]),
                json.dumps(token["validity"]),
                token["revocation_endpoint"],
                token["evaluated_constraint_hash"],
                token["signature"],
                "active",
                token.get("created_at", time.time()),
            )
        )
        await db.commit()

        # 如果有委托链，写入 delegation_chain_links
        parent_id = token.get("_parent_token_id")
        parent_hash = token.get("_parent_scope_hash")
        if parent_id and parent_hash:
            await db.execute(
                """INSERT INTO delegation_chain_links (
                    child_token_id, parent_token_id, parent_scope_hash, depth
                ) VALUES (?, ?, ?, 1)""",
                (token["token_id"], parent_id, parent_hash)
            )
            await db.commit()

    return token["token_id"]


async def get_capability_token(token_id: str) -> Optional[dict]:
    """
    查询 Capability Token。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT token_id, version, issuer_did, subject_did, enclave_id,
                      scope_json, constraints_json, validity_json, revocation_endpoint,
                      evaluated_constraint_hash, signature, status, created_at, revoked_at
               FROM capability_tokens WHERE token_id=?""",
            (token_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None

    # 查询委托链
    chain = await get_delegation_chain(token_id)

    return {
        "token_id": row[0],
        "version": row[1],
        "issuer_did": row[2],
        "subject_did": row[3],
        "enclave_id": row[4],
        "scope": json.loads(row[5]),
        "constraints": json.loads(row[6]),
        "validity": json.loads(row[7]),
        "revocation_endpoint": row[8],
        "evaluated_constraint_hash": row[9],
        "signature": row[10],
        "status": row[11],
        "created_at": row[12],
        "revoked_at": row[13],
        "_parent_token_id": chain[0]["parent_token_id"] if chain else None,
        "_parent_scope_hash": chain[0]["parent_scope_hash"] if chain else None,
    }


async def list_capability_tokens_by_did(did: str, status: str = "active") -> list[dict]:
    """
    查询某 DID 持有的所有 Token。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT token_id, version, issuer_did, subject_did, enclave_id,
                      scope_json, constraints_json, validity_json, revocation_endpoint,
                      evaluated_constraint_hash, signature, status, created_at
               FROM capability_tokens WHERE subject_did=? AND status=?""",
            (did, status)
        ) as cur:
            rows = await cur.fetchall()
    return [{
        "token_id": r[0],
        "version": r[1],
        "issuer_did": r[2],
        "subject_did": r[3],
        "enclave_id": r[4],
        "scope": json.loads(r[5]),
        "constraints": json.loads(r[6]),
        "validity": json.loads(r[7]),
        "revocation_endpoint": r[8],
        "evaluated_constraint_hash": r[9],
        "signature": r[10],
        "status": r[11],
        "created_at": r[12],
    } for r in rows]


async def revoke_capability_token(token_id: str) -> bool:
    """
    撤销 Token。返回 True 表示成功，False 表示 Token 不存在或已撤销。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT token_id, status FROM capability_tokens WHERE token_id=?", (token_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row or row[1] != "active":
            return False

        await db.execute(
            "UPDATE capability_tokens SET status='revoked', revoked_at=? WHERE token_id=?",
            (time.time(), token_id)
        )
        await db.commit()
    return True


async def add_delegation_link(child_token_id: str, parent_token_id: str, parent_scope_hash: str, depth: int = 1) -> None:
    """
    添加委托链链接。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO delegation_chain_links (
                child_token_id, parent_token_id, parent_scope_hash, depth
            ) VALUES (?, ?, ?, ?)""",
            (child_token_id, parent_token_id, parent_scope_hash, depth)
        )
        await db.commit()


async def get_delegation_chain(token_id: str) -> list[dict]:
    """
    查询 Token 的委托链。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT child_token_id, parent_token_id, parent_scope_hash, depth
               FROM delegation_chain_links WHERE child_token_id=?""",
            (token_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [{
        "child_token_id": r[0],
        "parent_token_id": r[1],
        "parent_scope_hash": r[2],
        "depth": r[3],
    } for r in rows]


async def is_token_revoked(token_id: str) -> bool:
    """
    检查 Token 是否已撤销。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT status FROM capability_tokens WHERE token_id=?", (token_id,)
        ) as cur:
            row = await cur.fetchone()
    return row is not None and row[0] != "active"


async def store_message(from_did: str, to_did: str, content: str,
                        session_id: str = "", reply_to: int | None = None,
                        message_type: str | None = None, protocol: str | None = None,
                        content_encoding: str | None = None,
                        message_id: str | None = None):
    """存储离线消息。D-SEC-09: 支持 message_id 持久化。"""
    import uuid
    if not message_id:
        message_id = f"msg_{uuid.uuid4().hex[:16]}"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (from_did, to_did, content, timestamp, session_id, reply_to, message_type, protocol, content_encoding, message_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (from_did, to_did, content, time.time(), session_id, reply_to, message_type, protocol, content_encoding, message_id)
        )
        await db.commit()


async def fetch_inbox(did: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
                retry_count INTEGER DEFAULT 0,
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

            -- Capability Tokens（v1.0-08）
            CREATE TABLE IF NOT EXISTS capability_tokens (
                token_id TEXT PRIMARY KEY,
                version INTEGER DEFAULT 1,
                issuer_did TEXT NOT NULL,
                subject_did TEXT NOT NULL,
                enclave_id TEXT,
                scope_json TEXT NOT NULL,
                constraints_json TEXT NOT NULL,
                validity_json TEXT NOT NULL,
                revocation_endpoint TEXT NOT NULL,
                evaluated_constraint_hash TEXT NOT NULL,
                signature TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at REAL NOT NULL,
                revoked_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_ct_subject ON capability_tokens(subject_did);
            CREATE INDEX IF NOT EXISTS idx_ct_enclave ON capability_tokens(enclave_id);
            CREATE INDEX IF NOT EXISTS idx_ct_status ON capability_tokens(status);

            -- 委托链关系（v1.0-08）
            CREATE TABLE IF NOT EXISTS delegation_chain_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                child_token_id TEXT NOT NULL,
                parent_token_id TEXT NOT NULL,
                parent_scope_hash TEXT NOT NULL,
                depth INTEGER DEFAULT 1,
                FOREIGN KEY (child_token_id) REFERENCES capability_tokens(token_id),
                FOREIGN KEY (parent_token_id) REFERENCES capability_tokens(token_id)
            );
            CREATE INDEX IF NOT EXISTS idx_dcl_child ON delegation_chain_links(child_token_id);
            CREATE INDEX IF NOT EXISTS idx_dcl_parent ON delegation_chain_links(parent_token_id);
        """)
        await db.commit()

        # 向后兼容：stage_executions 新增字段（v1.0-08）
        for alter in [
            "ALTER TABLE stage_executions ADD COLUMN evaluated_constraint_hash TEXT",
            "ALTER TABLE stage_executions ADD COLUMN capability_token_id TEXT",
            "ALTER TABLE stage_executions ADD COLUMN retry_count INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(alter)
                await db.commit()
            except Exception:
                pass  # 列已存在，忽略


# ── Trust & Governance Tables (ADR-014) ───────────────────────────────────

async def init_trust_tables():
    """初始化信任网络和治理认证相关表"""
    async with aiosqlite.connect(DB_PATH) as db:
        # 检查表是否已存在，避免重复创建
        existing = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trust_edges'"
        )
        row = await existing.fetchone()
        if row is not None:
            # 表已存在，跳过
            await db.commit()
            return
        await db.executescript("""
            -- 信任边（Web of Trust）
            CREATE TABLE IF NOT EXISTS trust_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_did TEXT NOT NULL,
                to_did TEXT NOT NULL,
                score REAL NOT NULL,
                timestamp REAL NOT NULL,
                evidence TEXT,
                UNIQUE(from_did, to_did)
            );
            CREATE INDEX IF NOT EXISTS idx_trust_edges_from ON trust_edges(from_did);
            CREATE INDEX IF NOT EXISTS idx_trust_edges_to ON trust_edges(to_did);

            -- 交互记录
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_did TEXT NOT NULL,
                to_did TEXT NOT NULL,
                interaction_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                response_time_ms REAL,
                timestamp REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_interactions_to_did ON interactions(to_did, timestamp);

            -- 声誉缓存
            CREATE TABLE IF NOT EXISTS reputation_cache (
                agent_did TEXT PRIMARY KEY,
                base_score REAL NOT NULL,
                behavior_delta REAL NOT NULL,
                attestation_bonus REAL NOT NULL,
                trust_level INTEGER NOT NULL,
                updated_at REAL NOT NULL
            );

            -- 治理认证缓存
            CREATE TABLE IF NOT EXISTS governance_attestations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_did TEXT NOT NULL,
                issuer TEXT NOT NULL,
                attestation_json TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(agent_did, issuer)
            );
            CREATE INDEX IF NOT EXISTS idx_governance_attestations_did ON governance_attestations(agent_did);
            CREATE INDEX IF NOT EXISTS idx_governance_attestations_expires ON governance_attestations(expires_at);
        """)
        await db.commit()


# ── Trust Edges CRUD ─────────────────────────────────────────────────────

async def add_trust_edge(
    from_did: str,
    to_did: str,
    score: float,
    evidence: Optional[str] = None,
):
    """添加信任边"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO trust_edges
               (from_did, to_did, score, timestamp, evidence)
               VALUES (?, ?, ?, ?, ?)""",
            (from_did, to_did, score, time.time(), evidence)
        )
        await db.commit()


async def get_trust_edge(from_did: str, to_did: str) -> Optional[dict]:
    """获取信任边"""
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM trust_edges WHERE from_did = ?",
            (from_did,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def remove_trust_edge(from_did: str, to_did: str) -> bool:
    """删除信任边"""
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
        result = await db.execute(
            "DELETE FROM governance_attestations WHERE expires_at < ?",
            (time.time(),)
        )
        await db.commit()
        return result.rowcount


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
    """Create or reassign a stage execution record."""
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
            await db.execute(
                """UPDATE stage_executions
                   SET assigned_did = ?, status = 'active', task_id = ?,
                       output_ref = '', retry_count = COALESCE(retry_count, 0) + 1,
                       started_at = ?, completed_at = NULL
                   WHERE run_id = ? AND stage_name = ?""",
                (assigned_did, task_id, now, run_id, stage_name)
            )
            await db.commit()
            return True


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
        "retry_count": row["retry_count"] or 0,
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
        "retry_count": row["retry_count"] or 0,
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


async def get_stage_executions_for_run(run_id: str) -> list[dict]:
    """获取 Run 下所有阶段执行记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM stage_executions WHERE run_id = ? ORDER BY started_at",
            (run_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    results = []
    for row in rows:
        results.append({
            "run_id": row["run_id"],
            "stage_name": row["stage_name"],
            "assigned_did": row["assigned_did"] or "",
            "status": row["status"],
            "task_id": row["task_id"] or "",
            "output_ref": row["output_ref"] or "",
            "retry_count": row["retry_count"] or 0,
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        })
    return results


async def update_stage_execution(run_id: str, stage_name: str, **kwargs) -> bool:
    """更新阶段执行记录"""
    allowed = {
        "status", "output_ref", "completed_at", "assigned_did",
        "task_id", "started_at", "retry_count",
    }
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
        "retry_count": r["retry_count"] or 0,
        "started_at": r["started_at"],
        "completed_at": r["completed_at"],
    } for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# 秘书编排相关 — D-SEC-01 / D-SEC-02
# ══════════════════════════════════════════════════════════════════════════════

async def init_secretary_tables():
    """初始化 secretary_intakes 表。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS secretary_intakes (
                session_id TEXT PRIMARY KEY,
                owner_did TEXT NOT NULL,
                actor_did TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'intake',
                objective TEXT NOT NULL,
                required_roles TEXT NOT NULL,
                preferred_playbook TEXT,
                selected_workers TEXT,
                run_id TEXT,
                source_channel TEXT,
                source_message_ref TEXT,
                constraints_json TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_intakes_owner ON secretary_intakes(owner_did);
            CREATE INDEX IF NOT EXISTS idx_intakes_status ON secretary_intakes(status);
            CREATE INDEX IF NOT EXISTS idx_intakes_run ON secretary_intakes(run_id);
        """)
        await db.commit()


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
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
        "source_channel": row[9],
        "source_message_ref": row[10],
        "constraints": json.loads(row[11]) if row[11] else {},
        "created_at": row[12],
        "updated_at": row[13],
    }


async def update_intake(session_id: str, **kwargs) -> bool:
    """D-SEC-02: 更新 intake 状态（如 selected_workers, status, run_id）。"""
    allowed_fields = {
        "status", "selected_workers", "run_id", "objective",
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

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE secretary_intakes SET {set_clause} WHERE session_id=?", values
        )
        await db.commit()
    return True


async def list_intakes(owner_did: str, status: str = None) -> list[dict]:
    """D-SEC-02: 列出 owner 的 intake 记录。"""
    async with aiosqlite.connect(DB_PATH) as db:
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
            "source_channel": row[9],
            "source_message_ref": row[10],
            "constraints": json.loads(row[11]) if row[11] else {},
            "created_at": row[12],
            "updated_at": row[13],
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
