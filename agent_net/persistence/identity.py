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


from .skills_push import get_active_push_registrations

async def add_pending(did: str, init_packet: dict):
    async with connect() as db:
        await db.execute(
            "INSERT OR REPLACE INTO pending_requests (did, init_packet, requested_at, status) VALUES (?, ?, ?, 'pending')",
            (did, json.dumps(init_packet), time.time())
        )
        await db.commit()


async def list_pending() -> list[dict]:
    async with connect() as db:
        async with db.execute(
            "SELECT did, init_packet, requested_at, status FROM pending_requests WHERE status='pending' ORDER BY requested_at"
        ) as cur:
            rows = await cur.fetchall()
    return [{"did": r[0], "init_packet": json.loads(r[1]), "requested_at": r[2], "status": r[3]} for r in rows]


async def get_pending(did: str) -> Optional[dict]:
    async with connect() as db:
        async with db.execute(
            "SELECT did, init_packet, requested_at, status FROM pending_requests WHERE did=?", (did,)
        ) as cur:
            row = await cur.fetchone()
    if row:
        return {"did": row[0], "init_packet": json.loads(row[1]), "requested_at": row[2], "status": row[3]}
    return None


async def resolve_pending(did: str, action: str) -> bool:
    """action: 'allow' | 'deny'"""
    async with connect() as db:
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
    async with connect() as db:
        await db.execute(
            "INSERT OR REPLACE INTO agents (did, profile, is_local, last_seen, private_key_hex, worker_type) VALUES (?, ?, ?, ?, ?, ?)",
            (did, json.dumps(profile), int(is_local), time.time(), private_key_hex, worker_type)
        )
        await db.commit()


async def store_private_key(did: str, private_key_hex: str):
    """持久化 Agent 私钥（hex）"""
    async with connect() as db:
        await db.execute(
            "UPDATE agents SET private_key_hex=? WHERE did=?",
            (private_key_hex, did)
        )
        await db.commit()


async def get_private_key(did: str) -> Optional[str]:
    """获取 Agent 私钥 hex，未存储返回 None"""
    async with connect() as db:
        async with db.execute(
            "SELECT private_key_hex FROM agents WHERE did=?", (did,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row and row[0] else None


async def list_local_agents() -> list[dict]:
    async with connect() as db:
        async with db.execute(
            "SELECT did, profile, last_seen FROM agents WHERE is_local=1"
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"did": r[0], "profile": json.loads(r[1]), "last_seen": r[2]} for r in rows]


async def get_agent(did: str) -> Optional[dict]:
    async with connect() as db:
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
    async with connect() as db:
        await db.execute("UPDATE agents SET owner_did=? WHERE did=?", (owner_did, did))
        await db.commit()

    return {"did": did, "public_key_hex": pk_hex, "profile": profile_dict}


async def bind_agent(owner_did: str, agent_did: str) -> bool:
    """
    将 Agent 绑定到主 DID。
    返回 True 表示成功，False 表示 Agent 不存在或已是其他 owner 的子 Agent。
    """
    async with connect() as db:
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
    async with connect() as db:
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
    async with connect() as db:
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

    async with connect() as db:
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
    async with connect() as db:
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
        from .enclave import get_playbook_run

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
    async with connect() as db:
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
    async with connect() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM stage_executions WHERE assigned_did=? AND status='active'",
            (did,),
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def _get_active_stage_info(did: str) -> Optional[dict]:
    """获取 Worker 当前活跃的 stage 信息。"""
    async with connect() as db:
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
    async with connect() as db:
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
    async with connect() as db:
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
    async with connect() as db:
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
    async with connect() as db:
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
    async with connect() as db:
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
    async with connect() as db:
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
    async with connect() as db:
        async with db.execute(
            "SELECT status FROM capability_tokens WHERE token_id=?", (token_id,)
        ) as cur:
            row = await cur.fetchone()
    return row is not None and row[0] != "active"


