"""
agent_net.node.daemon
本地节点后端服务 —— 负责：
  1. 本地 Agent 注册与管理（含私钥持久化、NexusProfile 名片）
  2. P2P 打洞（STUN 探测）
  3. 连接 Relay 服务器（announce 心跳）
  4. 消息路由（local → P2P → relay → offline）
  5. 握手入口 + Gatekeeper 访问控制
  6. 节点 Relay 配置管理（local_relay / seed_relays）
  7. 写接口 Token 鉴权（防止局域网未授权修改）
监听: 0.0.0.0:8765
"""
import asyncio
import json
import os
import secrets
import time
import uuid
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

import aiohttp

from agent_net.common.constants import (
    NODE_CONFIG_FILE, DATA_DIR, DAEMON_TOKEN_FILE,
    RELAY_HEARTBEAT_INTERVAL, FEDERATION_PROXY_TIMEOUT,
)
from agent_net.common.did import DIDGenerator, AgentProfile, DIDResolver, DIDError, build_services_from_profile
from agent_net.common.profile import canonical_announce
from agent_net.storage import (
    init_db, register_agent, list_local_agents, get_agent,
    fetch_inbox, fetch_session, search_agents_by_capability, upsert_contact,
    list_pending, get_pending, resolve_pending,
    store_private_key, get_private_key, update_agent_profile,
    add_certification, get_certifications,
    register_skill, unregister_skill, list_skills, get_skill,
    # Enclave (ADR-013)
    create_enclave, get_enclave, list_enclaves, update_enclave, delete_enclave,
    add_enclave_member, get_enclave_member, list_enclave_members,
    update_enclave_member, remove_enclave_member,
    vault_get, vault_put, vault_list, vault_history, vault_delete,
    create_playbook, get_playbook,
    create_playbook_run, get_playbook_run, get_latest_playbook_run, update_playbook_run,
    create_stage_execution, get_stage_execution, get_stage_execution_by_task,
    update_stage_execution, list_stage_executions,
)
from agent_net.router import router
from agent_net.stun import get_public_endpoint
from agent_net.node.gatekeeper import gatekeeper, GateDecision
from agent_net.adapters import AdapterRegistry, register_adapter
from agent_net.adapters.openclaw import OpenClawAdapter
from agent_net.adapters.webhook import WebhookAdapter

NODE_PORT = 8765
_public_endpoint: dict | None = None
_heartbeat_task: asyncio.Task | None = None
_daemon_token: str = ""

# did -> asyncio.Future，握手 PENDING 时挂起，resolve 后唤醒
_handshake_waiters: dict[str, asyncio.Future] = {}


# ── Token 管理 ────────────────────────────────────────────────

# 用户级 Token 路径（供 SDK 和 MCP 使用）
USER_TOKEN_DIR = Path.home() / ".agentnexus"
USER_TOKEN_FILE = USER_TOKEN_DIR / "daemon_token.txt"


def _init_daemon_token() -> str:
    """首次启动生成 token 并写入文件；后续读取已有 token。

    Token 同时写入两个位置：
    - 项目目录 data/daemon_token.txt（本地开发）
    - 用户目录 ~/.agentnexus/daemon_token.txt（SDK 全局使用）
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    # 优先从用户目录读取（跨项目共享）
    if USER_TOKEN_FILE.exists():
        with open(USER_TOKEN_FILE, "r") as f:
            t = f.read().strip()
        if t:
            # 同步到项目目录（确保一致）
            with open(DAEMON_TOKEN_FILE, "w") as f:
                f.write(t)
            try:
                os.chmod(DAEMON_TOKEN_FILE, 0o600)
            except Exception:
                pass
            return t

    # 其次从项目目录读取
    if os.path.exists(DAEMON_TOKEN_FILE):
        with open(DAEMON_TOKEN_FILE, "r") as f:
            t = f.read().strip()
        if t:
            # 同步到用户目录
            USER_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
            with open(USER_TOKEN_FILE, "w") as f:
                f.write(t)
            try:
                os.chmod(USER_TOKEN_FILE, 0o600)
            except Exception:
                pass
            return t

    # 生成新 token
    token = secrets.token_hex(32)

    # 写入项目目录
    with open(DAEMON_TOKEN_FILE, "w") as f:
        f.write(token)
    try:
        os.chmod(DAEMON_TOKEN_FILE, 0o600)
    except Exception:
        pass

    # 写入用户目录
    USER_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    with open(USER_TOKEN_FILE, "w") as f:
        f.write(token)
    try:
        os.chmod(USER_TOKEN_FILE, 0o600)
    except Exception:
        pass

    print(f"[Node] Token generated → {DAEMON_TOKEN_FILE}")
    print(f"[Node] Token (user)    → {USER_TOKEN_FILE}")
    return token


def _require_token(authorization: Optional[str] = Header(None)):
    """写接口鉴权依赖：Authorization: Bearer <token>"""
    if not _daemon_token:
        return   # token 未初始化（测试或首次启动前），放行
    if authorization != f"Bearer {_daemon_token}":
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing token")


# Token-DID 绑定存储（用于 Push 回调安全验证）
# {token_hash: [did1, did2, ...]}
_TOKEN_DID_BINDINGS: dict[str, list[str]] = {}


def _bind_token_to_did(did: str) -> None:
    """将当前 Token 绑定到指定 DID"""
    import hashlib
    token_hash = hashlib.sha256(_daemon_token.encode()).hexdigest()
    if token_hash not in _TOKEN_DID_BINDINGS:
        _TOKEN_DID_BINDINGS[token_hash] = []
    if did not in _TOKEN_DID_BINDINGS[token_hash]:
        _TOKEN_DID_BINDINGS[token_hash].append(did)


def _verify_token_did_binding(did: str) -> bool:
    """验证 Token 是否绑定到指定 DID"""
    import hashlib
    if not _daemon_token:
        return True  # 无 Token 时放行（测试模式）
    token_hash = hashlib.sha256(_daemon_token.encode()).hexdigest()
    return did in _TOKEN_DID_BINDINGS.get(token_hash, [])


# ── 节点配置（node_config.json） ─────────────────────────────

def _load_node_config() -> dict:
    """读取节点 relay 配置，若不存在则返回默认值"""
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(NODE_CONFIG_FILE):
        try:
            with open(NODE_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"local_relay": "http://localhost:9000", "seed_relays": []}


def _save_node_config(cfg: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(NODE_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


_node_cfg = _load_node_config()
RELAY_URL: str = _node_cfg["local_relay"]


# ── Relay 通信 ────────────────────────────────────────────────

async def _announce_to_relay(did: str, endpoint: str, relay_url: str | None = None):
    url = relay_url or RELAY_URL
    payload: dict = {
        "did": did,
        "endpoint": endpoint,
        "public_ip": _public_endpoint.get("public_ip") if _public_endpoint else None,
        "public_port": _public_endpoint.get("public_port") if _public_endpoint else None,
    }
    # 签名 announce 请求
    pk_hex = await get_private_key(did)
    if pk_hex:
        from nacl.signing import SigningKey as _SK
        from nacl.encoding import HexEncoder as _HE, RawEncoder as _RE
        sk = _SK(bytes.fromhex(pk_hex))
        ts = time.time()
        canonical = canonical_announce(
            did, endpoint, ts, payload.get("public_ip"), payload.get("public_port"),
        )
        sig = sk.sign(canonical, encoder=_RE).signature.hex()
        payload["pubkey"] = sk.verify_key.encode(_HE).decode()
        payload["timestamp"] = ts
        payload["signature"] = sig
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"{url}/announce", json=payload,
                         timeout=aiohttp.ClientTimeout(total=5))
    except Exception:
        pass


async def _federation_announce(did: str, local_relay: str, profile_dict: dict | None = None):
    """向所有种子站发送公开 Agent 的联邦公告（fire-and-forget）"""
    cfg = _load_node_config()
    for seed in cfg.get("seed_relays", []):
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"{seed}/federation/announce",
                    json={"did": did, "relay_url": local_relay, "profile": profile_dict},
                    timeout=aiohttp.ClientTimeout(total=FEDERATION_PROXY_TIMEOUT),
                )
        except Exception:
            pass


async def _heartbeat_loop(did: str, endpoint: str, interval: int = RELAY_HEARTBEAT_INTERVAL):
    while True:
        await _announce_to_relay(did, endpoint)
        await asyncio.sleep(interval)


async def _cleanup_expired_push_registrations():
    """定时清理过期的 Push 注册（每 5 分钟）"""
    while True:
        await asyncio.sleep(300)  # 5 分钟
        try:
            from agent_net.storage import cleanup_expired_push_registrations
            deleted = await cleanup_expired_push_registrations()
            if deleted > 0:
                print(f"[Node] Cleaned up {deleted} expired push registrations")
        except Exception as e:
            print(f"[Node] Push cleanup error: {e}")


_cleanup_push_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _public_endpoint, _heartbeat_task, _cleanup_push_task, RELAY_URL, _node_cfg, _daemon_token
    await init_db()
    _daemon_token = _init_daemon_token()
    _node_cfg = _load_node_config()
    RELAY_URL = _node_cfg["local_relay"]
    _public_endpoint = await get_public_endpoint()

    # 注册 DID 方法 handlers（ADR-009）
    from agent_net.common.did_methods import register_daemon_handlers
    from agent_net.storage import DB_PATH
    register_daemon_handlers(str(DB_PATH))

    # 初始化 PlaybookEngine（ADR-013 §4）
    from agent_net.enclave.playbook import init_playbook_engine
    init_playbook_engine(daemon_url=f"http://localhost:{NODE_PORT}", token=_daemon_token)

    # 启动 Push 注册过期清理任务（v0.9）
    _cleanup_push_task = asyncio.create_task(_cleanup_expired_push_registrations())

    print(f"[Node] Started. Public endpoint: {_public_endpoint}")
    print(f"[Node] Local relay: {RELAY_URL}")
    yield
    if _heartbeat_task:
        _heartbeat_task.cancel()
    if _cleanup_push_task:
        _cleanup_push_task.cancel()


app = FastAPI(title="AgentNet Node Daemon", version="0.6.0", lifespan=lifespan)


# ── 请求模型 ──────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    type: str = "GeneralAgent"
    capabilities: list[str] = []
    location: str = ""
    did: Optional[str] = None
    is_public: bool = False
    description: str = ""
    tags: list[str] = []
    did_format: str = "agentnexus"  # "agentnexus" | "agent" (legacy)


class SendMessageRequest(BaseModel):
    from_did: str
    to_did: str
    content: str | dict  # str for free text, dict for Action Layer
    session_id: str = ""
    reply_to: int | None = None
    message_type: Optional[str] = None  # Action Layer: task_propose, task_claim, resource_sync, state_notify
    protocol: Optional[str] = None      # e.g., "nexus_v1"


class AddContactRequest(BaseModel):
    did: str
    endpoint: str
    relay: Optional[str] = None


class ResolveRequest(BaseModel):
    did: str
    action: str   # 'allow' | 'deny'


class UpdateCardRequest(BaseModel):
    """名片可更新的字段（均为可选）"""
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class CertifyRequest(BaseModel):
    """认证请求：issuer 为 target_did 签发认证"""
    issuer_did: str
    claim: str
    evidence: str = ""


class RuntimeVerifyRequest(BaseModel):
    """RuntimeVerifier 验证请求"""
    agent_did: str
    agent_public_key: str                        # hex 或 multibase z...
    trusted_cas: Optional[dict] = None           # {ca_did: pubkey_hex}，覆盖默认配置


# ── Agent 管理 API ────────────────────────────────────────────

@app.post("/agents/register")
async def api_register_agent(req: RegisterRequest, _=Depends(_require_token)):
    global _heartbeat_task

    # 生成 DID：默认使用 did:agentnexus 格式（W3C 兼容），支持回退到 did:agent（旧格式）
    if req.did:
        did = req.did
        agent_did_obj = DIDGenerator.create_new(req.name)
        signing_key = agent_did_obj.private_key
    elif req.did_format == "agent":
        agent_did_obj = DIDGenerator.create_new(req.name)
        did = agent_did_obj.did
        signing_key = agent_did_obj.private_key
    else:
        # did:agentnexus (默认)
        agent_did_obj, _ = DIDGenerator.create_agentnexus(req.name)
        did = agent_did_obj.did
        signing_key = agent_did_obj.private_key

    endpoint = f"http://localhost:{NODE_PORT}"
    if _public_endpoint:
        endpoint = f"http://{_public_endpoint['public_ip']}:{_public_endpoint['public_port']}"

    profile = AgentProfile(
        id=did, name=req.name, type=req.type,
        capabilities=req.capabilities, location=req.location,
        endpoints={"p2p": endpoint, "relay": RELAY_URL},
    )
    # 将名片专属字段和 is_public 存入 profile dict
    profile_dict = profile.to_dict()
    profile_dict["description"] = req.description
    profile_dict["tags"] = req.tags or req.capabilities
    profile_dict["is_public"] = req.is_public
    profile_dict["public_key_hex"] = signing_key.verify_key.encode().hex()

    from nacl.encoding import HexEncoder
    pk_hex = signing_key.encode(HexEncoder).decode()
    await register_agent(did, profile_dict, is_local=True, private_key_hex=pk_hex)

    # 绑定 Token 到 DID（用于 Push 回调安全验证）
    _bind_token_to_did(did)

    # 不注册 local session：daemon 注册 ≠ 有活跃 MCP 消费者。
    # 消息应落 DB（offline），由 MCP 轮询 fetch_inbox 取出。

    if _heartbeat_task is None or _heartbeat_task.done():
        _heartbeat_task = asyncio.create_task(_heartbeat_loop(did, endpoint))

    await _announce_to_relay(did, endpoint)

    # 生成 NexusProfile 名片（签名在 daemon 内完成，私钥不出户）
    nexus_profile_dict = None
    try:
        from agent_net.common.profile import NexusProfile
        nexus_profile = NexusProfile.create(
            did=did, signing_key=signing_key,
            name=req.name, description=req.description,
            tags=req.tags or req.capabilities,
            relay=RELAY_URL,
            direct=endpoint if _public_endpoint else None,
        )
        nexus_profile_dict = nexus_profile.to_dict()
    except Exception:
        pass

    if req.is_public:
        asyncio.create_task(_federation_announce(did, RELAY_URL, nexus_profile_dict))

    return {
        "did": did,
        "profile": profile.to_json_ld(),
        "nexus_profile": nexus_profile_dict,
        "is_public": req.is_public,
    }


@app.get("/agents/local")
async def api_list_local_agents():
    agents = await list_local_agents()
    return {"agents": agents, "count": len(agents)}


@app.get("/agents/search/{keyword}")
async def api_search_agents(keyword: str):
    results = await search_agents_by_capability(keyword)
    return {"agents": results, "count": len(results)}


@app.get("/resolve/{did:path}")
async def api_resolve_did(did: str):
    """
    W3C DID Resolution — 返回 DID Document + service 数组

    解析优先级:
      1. 本地 agent (is_local=1) → 从私钥推导公钥，构建 DID Doc + services
      2. 非本地 agent → 从 profile 中的 public_key_hex 构建
      3. did:agentnexus 纯密码学解析（无需数据库）
      4. 转发到 relay（若已配置）
      5. 404
    """
    from nacl.signing import SigningKey

    resolver = DIDResolver()

    # 1 & 2: 查本地数据库
    agent = await get_agent(did)
    if agent:
        profile = agent.get("profile", {}) if isinstance(agent.get("profile"), dict) else {}
        pubkey_bytes = None

        # 优先从私钥推导
        private_key_hex = await get_private_key(did)
        if private_key_hex:
            try:
                sk = SigningKey(bytes.fromhex(private_key_hex))
                pubkey_bytes = sk.verify_key.encode()
            except Exception:
                pass

        # 回退到 profile 中的 public_key_hex
        if not pubkey_bytes:
            pubkey_hex = profile.get("public_key_hex")
            if pubkey_hex:
                try:
                    pubkey_bytes = bytes.fromhex(pubkey_hex)
                except ValueError:
                    pass

        if pubkey_bytes:
            node_config = _load_node_config()
            relay_url = node_config.get("local_relay", "")
            services = build_services_from_profile(profile, relay_url)
            # 使用 utils 中的 build_did_document
            from agent_net.common.did_methods.utils import build_did_document
            doc = build_did_document(did, pubkey_bytes, services)
            return {"didDocument": doc, "source": "local_db"}

    # 3. did:agentnexus 纯密码学解析
    try:
        result = await resolver.resolve(did)
        return {"didDocument": result.did_document, "source": "cryptographic"}
    except DIDError:
        pass

    # 4. 转发到 relay
    node_config = _load_node_config()
    relay_url = node_config.get("local_relay", "")
    if relay_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{relay_url.rstrip('/')}/resolve/{did}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        data["_via_relay"] = relay_url
                        return data
        except Exception:
            pass

    raise HTTPException(status_code=404, detail=f"Cannot resolve DID: {did}")


@app.get("/agents/{did}")
async def api_get_agent(did: str):
    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@app.get("/agents/{did}/profile")
async def api_get_nexus_profile(did: str):
    """生成并返回 Agent 的 NexusProfile 名片（需有持久化私钥）"""
    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, "Agent not found")
    pk_hex = await get_private_key(did)
    if not pk_hex:
        raise HTTPException(409, "Private key not available for this agent")
    from agent_net.common.profile import NexusProfile
    from nacl.signing import SigningKey
    from nacl.encoding import HexEncoder
    signing_key = SigningKey(bytes.fromhex(pk_hex))
    p = agent["profile"]
    nexus = NexusProfile.create(
        did=did,
        signing_key=signing_key,
        name=p.get("name", ""),
        description=p.get("description", ""),
        tags=p.get("tags") or p.get("capabilities", []),
        relay=RELAY_URL,
        direct=p.get("endpoints", {}).get("p2p"),
    )
    # 追加已有的认证（不影响 content 签名）
    for cert in p.get("certifications", []):
        nexus.add_certification(cert)
    return nexus.to_dict()


@app.patch("/agents/{did}/card")
async def api_update_card(did: str, req: UpdateCardRequest, _=Depends(_require_token)):
    """更新 Agent 名片字段（name/description/tags），在 daemon 内重新签名，私钥不出户"""
    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, "Agent not found")
    pk_hex = await get_private_key(did)
    if not pk_hex:
        raise HTTPException(409, "Private key not available for this agent")

    # 构造更新字段，只覆盖请求中非 None 的项
    update_fields: dict = {}
    if req.name is not None:
        update_fields["name"] = req.name
    if req.description is not None:
        update_fields["description"] = req.description
    if req.tags is not None:
        update_fields["tags"] = req.tags

    if update_fields:
        await update_agent_profile(did, update_fields)

    # 重新读取更新后的 profile，在 daemon 内签名生成新名片
    agent = await get_agent(did)
    p = agent["profile"]
    from agent_net.common.profile import NexusProfile
    from nacl.signing import SigningKey
    from nacl.encoding import HexEncoder
    signing_key = SigningKey(bytes.fromhex(pk_hex))
    nexus = NexusProfile.create(
        did=did,
        signing_key=signing_key,
        name=p.get("name", ""),
        description=p.get("description", ""),
        tags=p.get("tags") or p.get("capabilities", []),
        relay=RELAY_URL,
        direct=p.get("endpoints", {}).get("p2p"),
    )

    # 若 is_public，重新向联邦广播更新后的名片
    if p.get("is_public"):
        asyncio.create_task(_federation_announce(did, RELAY_URL, nexus.to_dict()))

    return {"status": "ok", "profile": nexus.to_dict()}


@app.post("/agents/{did}/certify")
async def api_certify_agent(did: str, req: CertifyRequest, _=Depends(_require_token)):
    """为 Agent 签发认证：issuer 用自己的私钥签名，认证追加到目标 Agent 的 profile"""
    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, "Target agent not found")
    # issuer 必须是本地 Agent 且有私钥
    issuer_pk_hex = await get_private_key(req.issuer_did)
    if not issuer_pk_hex:
        raise HTTPException(409, f"Private key not available for issuer {req.issuer_did}")
    from agent_net.common.profile import create_certification
    from nacl.signing import SigningKey
    issuer_sk = SigningKey(bytes.fromhex(issuer_pk_hex))
    cert = create_certification(
        target_did=did,
        issuer_did=req.issuer_did,
        issuer_signing_key=issuer_sk,
        claim=req.claim,
        evidence=req.evidence,
    )
    await add_certification(did, cert)
    return {"status": "ok", "certification": cert}


@app.get("/agents/{did}/certifications")
async def api_get_certifications(did: str):
    """获取 Agent 的所有认证"""
    certs = await get_certifications(did)
    return {"certifications": certs, "count": len(certs)}


# ── 密钥导出/导入 API ──────────────────────────────────────────

class ExportRequest(BaseModel):
    password: str


class ImportRequest(BaseModel):
    data: str   # export_agent() 返回的 JSON bytes → base64 or raw str
    password: str


@app.get("/agents/{did}/export")
async def api_export_agent(did: str, password: str, _=Depends(_require_token)):
    """
    导出 Agent 身份包（加密）

    Query params:
        password: 加密密码
    """
    from agent_net.common.keystore import export_agent as _export_agent

    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, "Agent not found")

    private_key_hex = await get_private_key(did)
    if not private_key_hex:
        raise HTTPException(400, "No private key stored for this agent")

    profile = agent.get("profile", {}) or {}
    certs = await get_certifications(did)

    encrypted_bytes = _export_agent(
        did=did,
        private_key_hex=private_key_hex,
        profile=profile,
        password=password,
        certifications=certs,
    )
    return {"data": encrypted_bytes.decode("utf-8")}


@app.post("/agents/import")
async def api_import_agent(req: ImportRequest, _=Depends(_require_token)):
    """
    导入 Agent 身份包（解密后注册到本地数据库）

    如 DID 已存在则更新私钥和 profile。
    """
    from agent_net.common.keystore import import_agent as _import_agent

    try:
        payload = _import_agent(req.data.encode("utf-8"), req.password)
    except ValueError as e:
        raise HTTPException(400, str(e))

    did = payload["did"]
    private_key_hex = payload["private_key_hex"]
    profile = payload.get("profile", {})
    certs = payload.get("certifications", [])

    # 注册到本地数据库（upsert 语义）
    await register_agent(did, profile, is_local=True, private_key_hex=private_key_hex)

    # 恢复认证
    for cert in certs:
        try:
            await add_certification(did, cert)
        except Exception:
            pass

    return {"status": "ok", "did": did, "certifications_restored": len(certs)}


# ── 消息 API ──────────────────────────────────────────────────

@app.post("/messages/send")
async def api_send_message(req: SendMessageRequest):
    if not router.is_local(req.to_did):
        await _resolve_from_relay(req.to_did)

    # Convert content to string for storage (dict -> json string)
    # Mark content_encoding when content is serialized from dict
    content_encoding = None
    if isinstance(req.content, str):
        content_str = req.content
    else:
        content_str = json.dumps(req.content)
        content_encoding = "json"

    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:16]}"

    return await router.route_message(
        req.from_did,
        req.to_did,
        content_str,
        session_id,
        req.reply_to,
        message_type=req.message_type,
        protocol=req.protocol,
        content_encoding=content_encoding,
    )


@app.get("/messages/inbox/{did}")
async def api_fetch_inbox(did: str):
    messages = await fetch_inbox(did)
    return {"messages": messages, "count": len(messages)}


@app.get("/messages/all/{did}")
async def api_all_messages(did: str, limit: int = 100):
    """
    获取 Agent 的所有消息（含已投递）。

    用于 Discussion Protocol 的历史查询。
    """
    from agent_net.storage import DB_PATH
    import aiosqlite

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, from_did, content, timestamp, session_id, reply_to, message_type, protocol, content_encoding "
            "FROM messages WHERE to_did=? ORDER BY timestamp DESC LIMIT ?",
            (did, limit),
        ) as cursor:
            rows = await cursor.fetchall()

    messages = [{
        "id": r[0],
        "from": r[1],
        "content": r[2],
        "timestamp": r[3],
        "session_id": r[4] or "",
        "reply_to": r[5],
        "message_type": r[6],
        "protocol": r[7],
        "content_encoding": r[8],
    } for r in rows]

    return {"messages": messages, "count": len(messages)}


@app.get("/messages/session/{session_id}")
async def api_fetch_session(session_id: str):
    messages = await fetch_session(session_id)
    return {"messages": messages, "count": len(messages), "session_id": session_id}


# ── 通讯录 / STUN ─────────────────────────────────────────────

@app.post("/contacts/add")
async def api_add_contact(req: AddContactRequest, _=Depends(_require_token)):
    await upsert_contact(req.did, req.endpoint, req.relay)
    return {"status": "ok"}


@app.get("/stun/endpoint")
async def api_stun_endpoint():
    ep = await get_public_endpoint()
    return ep or {"error": "STUN failed"}


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time()}


# ── RuntimeVerifier ───────────────────────────────────────────

@app.post("/runtime/verify")
async def api_runtime_verify(req: RuntimeVerifyRequest):
    """
    RuntimeVerifier.verify() HTTP 入口。

    供 8-step agent identity pipeline 调用（step 1 身份验证）。
    返回 RuntimeVerification 完整字段。

    trusted_cas 可由调用方按需传入（覆盖 daemon 默认配置）；
    不传则使用空 CA 列表（trust_level 最高 L2）。
    """
    from agent_net.common.runtime_verifier import (
        AgentNexusRuntimeVerifier,
        make_storage_cert_fetcher,
    )

    verifier = AgentNexusRuntimeVerifier(
        resolver=DIDResolver(),
        trusted_cas=req.trusted_cas,
        cert_fetcher=make_storage_cert_fetcher(),
    )
    result = await verifier.verify(req.agent_did, req.agent_public_key)
    return result.to_dict()


# ── 握手入口（含 Gatekeeper 检查点）─────────────────────────

@app.post("/handshake/init")
async def api_handshake_init(init_packet: dict):
    from agent_net.common.handshake import HandshakeManager
    from nacl.signing import SigningKey

    sender_did = init_packet.get("sender_did")
    if not sender_did:
        raise HTTPException(400, "Missing sender_did")

    decision = await gatekeeper.check(sender_did, init_packet)

    if decision == GateDecision.DENY:
        raise HTTPException(403, f"Access denied for {sender_did}")

    if decision == GateDecision.PENDING:
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        gatekeeper.register_pending_future(sender_did, fut)
        try:
            action = await asyncio.wait_for(fut, timeout=300)
        except asyncio.TimeoutError:
            return JSONResponse(status_code=408, content={
                "status": "timeout", "did": sender_did
            })
        if action != "allow":
            raise HTTPException(403, f"Access denied for {sender_did}")

    local_sk = SigningKey.generate()
    mgr = HandshakeManager(local_sk)
    challenge = mgr.process_init(init_packet)
    return {"status": "challenge", "packet": challenge}


# ── Gatekeeper 管理接口 ───────────────────────────────────────

@app.get("/gate/pending")
async def api_list_pending():
    items = await list_pending()
    return {"pending": items, "count": len(items)}


@app.post("/gate/resolve")
async def api_resolve(req: ResolveRequest, _=Depends(_require_token)):
    if req.action not in ("allow", "deny"):
        raise HTTPException(400, "action must be 'allow' or 'deny'")
    ok = await gatekeeper.resolve(req.did, req.action)
    if not ok:
        raise HTTPException(404, f"No pending request for {req.did}")
    return {"status": "ok", "did": req.did, "action": req.action}


@app.post("/gate/whitelist/add")
async def api_whitelist_add(payload: dict, _=Depends(_require_token)):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.whitelist_add(did)
    return {"status": "ok", "did": did}


@app.post("/gate/whitelist/remove")
async def api_whitelist_remove(payload: dict, _=Depends(_require_token)):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.whitelist_remove(did)
    return {"status": "ok", "did": did}


@app.post("/gate/blacklist/add")
async def api_blacklist_add(payload: dict, _=Depends(_require_token)):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.blacklist_add(did)
    return {"status": "ok", "did": did}


@app.post("/gate/blacklist/remove")
async def api_blacklist_remove(payload: dict, _=Depends(_require_token)):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.blacklist_remove(did)
    return {"status": "ok", "did": did}


@app.post("/gate/mode")
async def api_set_mode(payload: dict, _=Depends(_require_token)):
    mode = payload.get("mode")
    if mode not in ("public", "private", "ask"):
        raise HTTPException(400, "mode must be public | private | ask")
    from agent_net.node.gatekeeper import save_mode
    save_mode(mode)
    return {"status": "ok", "mode": mode}


@app.get("/gate/mode")
async def api_get_mode():
    from agent_net.node.gatekeeper import load_mode
    return {"mode": load_mode()}


# ── 节点配置管理 API ──────────────────────────────────────────

@app.get("/node/config")
async def api_get_config():
    return _load_node_config()


@app.post("/node/config/local-relay")
async def api_set_local_relay(payload: dict, _=Depends(_require_token)):
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(400, "Missing url")
    cfg = _load_node_config()
    cfg["local_relay"] = url
    _save_node_config(cfg)
    global RELAY_URL
    RELAY_URL = url
    return {"status": "ok", "local_relay": url}


@app.post("/node/config/relay/add")
async def api_add_seed_relay(payload: dict, _=Depends(_require_token)):
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(400, "Missing url")
    cfg = _load_node_config()
    seeds = cfg.setdefault("seed_relays", [])
    if url not in seeds:
        seeds.append(url)
    _save_node_config(cfg)
    # 向种子站注册本 relay
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"{url}/federation/join",
                json={"relay_url": RELAY_URL},
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except Exception:
        pass
    return {"status": "ok", "seed_relays": seeds}


@app.post("/node/config/relay/remove")
async def api_remove_seed_relay(payload: dict, _=Depends(_require_token)):
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(400, "Missing url")
    cfg = _load_node_config()
    seeds = cfg.get("seed_relays", [])
    if url in seeds:
        seeds.remove(url)
    cfg["seed_relays"] = seeds
    _save_node_config(cfg)
    return {"status": "ok", "seed_relays": seeds}


# ── 内部工具 ──────────────────────────────────────────────────

@app.post("/deliver")
async def api_deliver(payload: dict):
    from_did = payload.get("from")
    to_did = payload.get("to")
    content = payload.get("content")
    if not all([from_did, to_did, content]):
        raise HTTPException(400, "Missing fields")
    session_id = payload.get("session_id", "")
    reply_to = payload.get("reply_to")
    message_type = payload.get("message_type")
    protocol = payload.get("protocol")
    return await router.route_message(from_did, to_did, content, session_id, reply_to,
                                      message_type=message_type, protocol=protocol)


# ── Platform Adapters (ADR-010) ─────────────────────────────────────

@app.post("/adapters/{platform}/invoke")
async def api_adapter_invoke(platform: str, payload: dict, authorization: str = Header(None)):
    """
    External platform → AgentNexus via adapter.

    Args:
        platform: Platform name (openclaw, webhook, etc.)
        payload: Platform-specific request
    """
    _require_token(authorization)

    adapter = AdapterRegistry.get(platform)
    if not adapter:
        raise HTTPException(404, f"Unknown platform: {platform}")

    result = await adapter.inbound(payload)
    if "error" in result:
        status = result.pop("status", 500)
        raise HTTPException(status, result["error"])

    return result


@app.post("/adapters/{platform}/register")
async def api_adapter_register(platform: str, payload: dict, authorization: str = Header(None)):
    """
    Register a platform adapter for an Agent.

    Args:
        platform: Platform name
        payload: {"agent_did": "...", "webhook_secret": "..." (for webhook)}
    """
    _require_token(authorization)

    agent_did = payload.get("agent_did")
    if not agent_did:
        raise HTTPException(400, "Missing agent_did")

    # Verify agent exists
    agent = await get_agent(agent_did)
    if not agent:
        raise HTTPException(404, f"Agent not found: {agent_did}")

    # Create and register adapter
    if platform == "openclaw":
        adapter = OpenClawAdapter(agent_did, router, __import__("agent_net.storage", fromlist=[""]))
    elif platform == "webhook":
        webhook_secret = payload.get("webhook_secret", secrets.token_hex(16))
        callback_url = payload.get("callback_url")
        adapter = WebhookAdapter(agent_did, router, __import__("agent_net.storage", fromlist=[""]),
                                 webhook_secret, callback_url)
    else:
        raise HTTPException(400, f"Unknown platform: {platform}")

    register_adapter(adapter)

    return {
        "status": "ok",
        "platform": platform,
        "agent_did": agent_did,
        "manifest": adapter.skill_manifest(),
    }


# ── Skill Registry (ADR-010) ─────────────────────────────────────────

@app.get("/skills")
async def api_list_skills(agent_did: Optional[str] = None, capability: Optional[str] = None):
    """List registered Skills, optionally filtered by Agent or capability."""
    skills = await list_skills(agent_did, capability)
    return {"skills": skills}


@app.get("/skills/{skill_id}")
async def api_get_skill(skill_id: str):
    """Get Skill details."""
    skill = await get_skill(skill_id)
    if not skill:
        raise HTTPException(404, f"Skill not found: {skill_id}")
    return skill


@app.post("/skills/register")
async def api_register_skill(payload: dict, authorization: str = Header(None)):
    """
    Register a Skill for an Agent.

    Args:
        payload: {
            "agent_did": "...",
            "name": "translate",
            "capabilities": ["Translation"],
            "actions": ["translate_text", "detect_language"]
        }
    """
    _require_token(authorization)

    agent_did = payload.get("agent_did")
    name = payload.get("name")
    capabilities = payload.get("capabilities", [])
    actions = payload.get("actions", [])

    if not agent_did or not name or not actions:
        raise HTTPException(400, "Missing required fields: agent_did, name, actions")

    # Verify agent exists
    agent = await get_agent(agent_did)
    if not agent:
        raise HTTPException(404, f"Agent not found: {agent_did}")

    skill_id = f"skill_{uuid.uuid4().hex[:8]}_{name}"
    await register_skill(skill_id, agent_did, name, capabilities, actions)

    return {"status": "ok", "skill_id": skill_id}


@app.delete("/skills/{skill_id}")
async def api_unregister_skill(skill_id: str, authorization: str = Header(None)):
    """Unregister a Skill."""
    _require_token(authorization)

    success = await unregister_skill(skill_id)
    if not success:
        raise HTTPException(404, f"Skill not found: {skill_id}")

    return {"status": "ok"}


async def _resolve_from_relay(did: str):
    """从 relay 查询 DID 端点，写入本地通讯录"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{RELAY_URL}/lookup/{did}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    await upsert_contact(did, data["endpoint"], RELAY_URL)
    except Exception:
        pass


# ── Push Registration API (ADR-012 L3/L5) ───────────────────────────

class PushRegisterRequest(BaseModel):
    did: str
    callback_url: str
    callback_type: str = "webhook"  # webhook / sse / platform
    push_key: Optional[str] = None   # 平台侧标识符
    expires: int = 3600              # TTL 秒数


class PushRefreshRequest(BaseModel):
    did: str
    callback_url: str
    callback_type: str = "webhook"
    expires: int = 3600


@app.post("/push/register")
async def api_push_register(req: PushRegisterRequest, _=Depends(_require_token)):
    """
    注册 Push 唤醒方式（ADR-012 §3）

    安全约束：
    1. did 参数必须与 Bearer Token 绑定的 DID 一致
    2. callback_url 默认仅允许 localhost（SSRF 防护），可配置白名单
    """
    # 安全检查 1：验证 did 是否与 token 绑定的 DID 一致
    if not _verify_token_did_binding(req.did):
        raise HTTPException(
            status_code=403,
            detail=f"Token not bound to DID: {req.did}. Register the agent first."
        )

    # 安全检查 2：SSRF 防护
    from urllib.parse import urlparse
    parsed = urlparse(req.callback_url)

    # 从配置读取 SSRF 白名单
    ssrf_allow_localhost_only = _node_cfg.get("ssrf_allow_localhost_only", True)
    ssrf_allowed_hosts = _node_cfg.get("ssrf_allowed_hosts", [])

    is_localhost = parsed.hostname in ("127.0.0.1", "localhost", "::1")
    is_allowed_host = parsed.hostname in ssrf_allowed_hosts

    if ssrf_allow_localhost_only and not is_localhost:
        # 严格模式：仅允许 localhost
        raise HTTPException(
            status_code=400,
            detail=f"SSRF protection: callback_url must be localhost. Got: {parsed.hostname}"
        )
    elif not is_localhost and not is_allowed_host:
        # 宽松模式：检查白名单
        raise HTTPException(
            status_code=400,
            detail=f"SSRF protection: hostname '{parsed.hostname}' not in allowed list"
        )

    from agent_net.storage import create_push_registration
    result = await create_push_registration(
        did=req.did,
        callback_url=req.callback_url,
        callback_type=req.callback_type,
        push_key=req.push_key,
        expires_seconds=req.expires,
    )

    return {
        "status": "ok",
        "registration_id": result["registration_id"],
        "expires_at": result["expires_at"],
        "callback_secret": result["callback_secret"],  # 仅注册时返回一次
    }


@app.post("/push/refresh")
async def api_push_refresh(req: PushRefreshRequest, _=Depends(_require_token)):
    """续约 Push 注册 TTL"""
    from agent_net.storage import refresh_push_registration
    new_expires = await refresh_push_registration(
        did=req.did,
        callback_url=req.callback_url,
        callback_type=req.callback_type,
        expires_seconds=req.expires,
    )
    if new_expires is None:
        raise HTTPException(404, "Registration not found or expired")
    return {"status": "ok", "expires_at": new_expires}


@app.delete("/push/{did}")
async def api_push_unregister(did: str, _=Depends(_require_token)):
    """主动注销 Push 注册"""
    from agent_net.storage import delete_push_registration
    deleted = await delete_push_registration(did)
    return {"status": "ok", "deleted": deleted}


@app.get("/push/{did}")
async def api_push_status(did: str):
    """查询 Push 注册状态（公开）"""
    from agent_net.storage import get_active_push_registrations
    regs = await get_active_push_registrations(did)
    # 不返回 callback_secret
    return {
        "status": "ok",
        "registrations": [{
            "registration_id": r["registration_id"],
            "callback_url": r["callback_url"],
            "callback_type": r["callback_type"],
            "expires_at": r["expires_at"],
        } for r in regs],
        "count": len(regs),
    }


# ── Enclave API (ADR-013) ───────────────────────────────────────────────

class CreateEnclaveRequest(BaseModel):
    name: str
    owner_did: str
    vault_backend: str = "local"
    vault_config: dict = {}
    members: dict = {}  # {role: {did, handbook, permissions}}


class UpdateEnclaveRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    vault_backend: str | None = None
    vault_config: dict | None = None


class AddMemberRequest(BaseModel):
    did: str
    role: str
    permissions: str = "rw"
    handbook: str = ""


class UpdateMemberRequest(BaseModel):
    role: str | None = None
    permissions: str | None = None
    handbook: str | None = None


class VaultPutRequest(BaseModel):
    value: str
    author_did: str
    message: str = ""


class CreatePlaybookRunRequest(BaseModel):
    playbook_id: str | None = None
    playbook: dict | None = None  # 内联定义


def _check_vault_permission(member: dict, required: str) -> None:
    """检查 Vault 权限"""
    if not member:
        raise HTTPException(403, "Not a member of this enclave")
    perms = member.get("permissions", "rw")
    if required == "rw" and perms == "r":
        raise HTTPException(403, "Read-only access")
    if required == "admin" and perms != "admin":
        raise HTTPException(403, "Admin access required")


# Enclave CRUD

@app.post("/enclaves")
async def api_create_enclave(req: CreateEnclaveRequest, _=Depends(_require_token)):
    """创建 Enclave"""
    from agent_net.enclave.models import Enclave
    enclave_id = Enclave.gen_id()

    # 创建 Enclave
    await create_enclave(
        enclave_id=enclave_id,
        name=req.name,
        owner_did=req.owner_did,
        vault_backend=req.vault_backend,
        vault_config=req.vault_config,
    )

    # 添加成员
    for role, member_data in req.members.items():
        await add_enclave_member(
            enclave_id=enclave_id,
            did=member_data["did"],
            role=role,
            permissions=member_data.get("permissions", "rw"),
            handbook=member_data.get("handbook", ""),
        )

    # Owner 默认是 admin
    owner_member = await get_enclave_member(enclave_id, req.owner_did)
    if not owner_member:
        await add_enclave_member(
            enclave_id=enclave_id,
            did=req.owner_did,
            role="owner",
            permissions="admin",
            handbook="Enclave owner",
        )

    return {"status": "ok", "enclave_id": enclave_id}


@app.get("/enclaves")
async def api_list_enclaves(did: str = None, status: str = None):
    """列出 Enclave（按成员 DID 过滤）"""
    enclaves = await list_enclaves(did=did, status=status)
    # 补充成员信息
    result = []
    for enc in enclaves:
        members = await list_enclave_members(enc["enclave_id"])
        enc["members"] = members
        result.append(enc)
    return {"status": "ok", "enclaves": result, "count": len(result)}


@app.get("/enclaves/{enclave_id}")
async def api_get_enclave(enclave_id: str):
    """获取 Enclave 详情"""
    enc = await get_enclave(enclave_id)
    if not enc:
        raise HTTPException(404, "Enclave not found")
    members = await list_enclave_members(enclave_id)
    enc["members"] = members
    return {"status": "ok", **enc}


@app.patch("/enclaves/{enclave_id}")
async def api_update_enclave(enclave_id: str, req: UpdateEnclaveRequest, _=Depends(_require_token)):
    """更新 Enclave"""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    ok = await update_enclave(enclave_id, **updates)
    if not ok:
        raise HTTPException(404, "Enclave not found")
    return {"status": "ok"}


@app.delete("/enclaves/{enclave_id}")
async def api_delete_enclave(enclave_id: str, _=Depends(_require_token)):
    """归档 Enclave"""
    ok = await delete_enclave(enclave_id)
    if not ok:
        raise HTTPException(404, "Enclave not found")
    return {"status": "ok", "archived": True}


# Member Management

@app.post("/enclaves/{enclave_id}/members")
async def api_add_member(enclave_id: str, req: AddMemberRequest, _=Depends(_require_token)):
    """添加成员"""
    # 检查 Enclave 存在
    enc = await get_enclave(enclave_id)
    if not enc:
        raise HTTPException(404, "Enclave not found")

    ok = await add_enclave_member(
        enclave_id=enclave_id,
        did=req.did,
        role=req.role,
        permissions=req.permissions,
        handbook=req.handbook,
    )
    if not ok:
        raise HTTPException(409, "Member already exists")
    return {"status": "ok"}


@app.delete("/enclaves/{enclave_id}/members/{did}")
async def api_remove_member(enclave_id: str, did: str, _=Depends(_require_token)):
    """移除成员"""
    ok = await remove_enclave_member(enclave_id, did)
    if not ok:
        raise HTTPException(404, "Member not found")
    return {"status": "ok"}


@app.patch("/enclaves/{enclave_id}/members/{did}")
async def api_update_member(enclave_id: str, did: str, req: UpdateMemberRequest, _=Depends(_require_token)):
    """更新成员属性"""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    ok = await update_enclave_member(enclave_id, did, **updates)
    if not ok:
        raise HTTPException(404, "Member not found")
    return {"status": "ok"}


# Vault Operations

@app.get("/enclaves/{enclave_id}/vault")
async def api_vault_list(enclave_id: str, prefix: str = "", author_did: str = None):
    """列出 Vault 文档"""
    enc = await get_enclave(enclave_id)
    if not enc:
        raise HTTPException(404, "Enclave not found")

    # 权限检查（需要是成员）
    if author_did:
        member = await get_enclave_member(enclave_id, author_did)
        if not member:
            raise HTTPException(403, "Not a member of this enclave")

    entries = await vault_list(enclave_id, prefix)
    return {"status": "ok", "entries": entries, "count": len(entries)}


@app.get("/enclaves/{enclave_id}/vault/{key:path}")
async def api_vault_get(enclave_id: str, key: str, version: str = None, author_did: str = None):
    """读取 Vault 文档"""
    enc = await get_enclave(enclave_id)
    if not enc:
        raise HTTPException(404, "Enclave not found")

    # 权限检查（需要是成员）
    if author_did:
        member = await get_enclave_member(enclave_id, author_did)
        if not member:
            raise HTTPException(403, "Not a member of this enclave")

    entry = await vault_get(enclave_id, key, version=int(version) if version else None)
    if not entry:
        raise HTTPException(404, f"Key not found: {key}")
    return {"status": "ok", **entry}


@app.put("/enclaves/{enclave_id}/vault/{key:path}")
async def api_vault_put(enclave_id: str, key: str, req: VaultPutRequest, _=Depends(_require_token)):
    """写入 Vault 文档"""
    enc = await get_enclave(enclave_id)
    if not enc:
        raise HTTPException(404, "Enclave not found")

    # 权限检查（需要写权限）
    member = await get_enclave_member(enclave_id, req.author_did)
    _check_vault_permission(member, "rw")

    result = await vault_put(
        enclave_id=enclave_id,
        key=key,
        value=req.value,
        author_did=req.author_did,
        message=req.message,
    )
    return {"status": "ok", **result}


@app.delete("/enclaves/{enclave_id}/vault/{key:path}")
async def api_vault_delete(enclave_id: str, key: str, author_did: str, _=Depends(_require_token)):
    """删除 Vault 文档"""
    enc = await get_enclave(enclave_id)
    if not enc:
        raise HTTPException(404, "Enclave not found")

    # 权限检查（需要写权限）
    member = await get_enclave_member(enclave_id, author_did)
    _check_vault_permission(member, "rw")

    ok = await vault_delete(enclave_id, key, author_did)
    if not ok:
        raise HTTPException(404, f"Key not found: {key}")
    return {"status": "ok", "deleted": True}


@app.get("/enclaves/{enclave_id}/vault/{key:path}/history")
async def api_vault_history(enclave_id: str, key: str, limit: int = 10, author_did: str = None):
    """查看文档历史"""
    enc = await get_enclave(enclave_id)
    if not enc:
        raise HTTPException(404, "Enclave not found")

    # 权限检查（需要是成员）
    if author_did:
        member = await get_enclave_member(enclave_id, author_did)
        if not member:
            raise HTTPException(403, "Not a member of this enclave")

    history = await vault_history(enclave_id, key, limit)
    return {"status": "ok", "history": history}


# Playbook Execution

@app.post("/enclaves/{enclave_id}/runs")
async def api_create_playbook_run(enclave_id: str, req: CreatePlaybookRunRequest, _=Depends(_require_token)):
    """启动 Playbook"""
    from agent_net.enclave.models import Playbook, PlaybookRun, Stage

    enc = await get_enclave(enclave_id)
    if not enc:
        raise HTTPException(404, "Enclave not found")

    # 获取或创建 Playbook
    if req.playbook_id:
        playbook = await get_playbook(req.playbook_id)
        if not playbook:
            raise HTTPException(404, "Playbook not found")
    elif req.playbook:
        # 内联定义
        playbook_id = Playbook.gen_id()
        stages = [Stage.from_dict(s) for s in req.playbook.get("stages", [])]
        await create_playbook(
            playbook_id=playbook_id,
            name=req.playbook.get("name", "inline"),
            stages=[s.to_dict() for s in stages],
            description=req.playbook.get("description", ""),
            created_by="",  # TODO: 从 token 获取
        )
        playbook = await get_playbook(playbook_id)
    else:
        raise HTTPException(400, "Either playbook_id or playbook is required")

    # 创建 Run
    run_id = PlaybookRun.gen_id()
    await create_playbook_run(
        run_id=run_id,
        enclave_id=enclave_id,
        playbook_id=playbook["playbook_id"],
        playbook_name=playbook["name"],
    )

    # 启动第一个阶段
    stages = playbook["stages"]
    if stages:
        first_stage = stages[0]
        # 找到该角色对应的成员
        members = await list_enclave_members(enclave_id)
        assigned_did = None
        for m in members:
            if m["role"] == first_stage["role"]:
                assigned_did = m["did"]
                break

        if assigned_did:
            # 创建阶段执行记录
            await create_stage_execution(
                run_id=run_id,
                stage_name=first_stage["name"],
                assigned_did=assigned_did,
            )
            # 更新 Run 的 current_stage
            await update_playbook_run(run_id, current_stage=first_stage["name"])

    return {
        "status": "ok",
        "run_id": run_id,
        "current_stage": stages[0]["name"] if stages else None,
        "assigned_did": assigned_did if stages else None,
    }


@app.get("/enclaves/{enclave_id}/runs")
async def api_get_latest_playbook_run(enclave_id: str):
    """查询 Enclave 最新的 Playbook 执行状态"""
    run = await get_latest_playbook_run(enclave_id)
    if not run:
        raise HTTPException(404, "No playbook runs found for this enclave")

    # 获取阶段执行记录
    stage_executions = await list_stage_executions(run["run_id"])

    # 获取 Playbook 定义
    playbook = await get_playbook(run["playbook_id"])

    # 构建阶段状态映射
    stages_status = {}
    if playbook:
        for stage in playbook["stages"]:
            stage_name = stage["name"]
            exec_record = next(
                (e for e in stage_executions if e["stage_name"] == stage_name),
                None
            )
            stages_status[stage_name] = {
                "status": exec_record["status"] if exec_record else "pending",
                "assigned_did": exec_record["assigned_did"] if exec_record else "",
                "task_id": exec_record["task_id"] if exec_record else "",
                "output_ref": exec_record["output_ref"] if exec_record else "",
            }

    return {
        "status": "ok",
        "run_id": run["run_id"],
        "playbook_name": run["playbook_name"],
        "current_stage": run["current_stage"],
        "run_status": run["status"],
        "stages": stages_status,
        "started_at": run["started_at"],
        "completed_at": run.get("completed_at"),
    }


@app.get("/enclaves/{enclave_id}/runs/{run_id}")
async def api_get_playbook_run(enclave_id: str, run_id: str):
    """查询 Playbook 执行状态"""
    run = await get_playbook_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run["enclave_id"] != enclave_id:
        raise HTTPException(404, "Run not found in this enclave")

    # 获取阶段执行记录
    stage_executions = await list_stage_executions(run_id)

    # 获取 Playbook 定义
    playbook = await get_playbook(run["playbook_id"])

    # 构建阶段状态映射
    stages_status = {}
    if playbook:
        for stage in playbook["stages"]:
            stage_name = stage["name"]
            exec_record = next(
                (e for e in stage_executions if e["stage_name"] == stage_name),
                None
            )
            stages_status[stage_name] = {
                "status": exec_record["status"] if exec_record else "pending",
                "assigned_did": exec_record["assigned_did"] if exec_record else "",
                "task_id": exec_record["task_id"] if exec_record else "",
                "output_ref": exec_record["output_ref"] if exec_record else "",
            }

    return {
        "status": "ok",
        "run_id": run["run_id"],
        "playbook_name": run["playbook_name"],
        "current_stage": run["current_stage"],
        "run_status": run["status"],
        "stages": stages_status,
        "started_at": run["started_at"],
        "completed_at": run.get("completed_at"),
    }


def run(host: str = "0.0.0.0", port: int = NODE_PORT):
    uvicorn.run(app, host=host, port=port, log_level="info")
