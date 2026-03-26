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
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

import aiohttp

from agent_net.common.constants import (
    NODE_CONFIG_FILE, DATA_DIR, DAEMON_TOKEN_FILE,
    RELAY_HEARTBEAT_INTERVAL, FEDERATION_PROXY_TIMEOUT,
)
from agent_net.common.did import DIDGenerator, AgentProfile
from agent_net.common.profile import canonical_announce
from agent_net.storage import (
    init_db, register_agent, list_local_agents, get_agent,
    fetch_inbox, fetch_session, search_agents_by_capability, upsert_contact,
    list_pending, get_pending, resolve_pending,
    store_private_key, get_private_key, update_agent_profile,
    add_certification, get_certifications,
)
from agent_net.router import router
from agent_net.stun import get_public_endpoint
from agent_net.node.gatekeeper import gatekeeper, GateDecision

NODE_PORT = 8765
_public_endpoint: dict | None = None
_heartbeat_task: asyncio.Task | None = None
_daemon_token: str = ""

# did -> asyncio.Future，握手 PENDING 时挂起，resolve 后唤醒
_handshake_waiters: dict[str, asyncio.Future] = {}


# ── Token 管理 ────────────────────────────────────────────────

def _init_daemon_token() -> str:
    """首次启动生成 token 并写入文件；后续读取已有 token。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(DAEMON_TOKEN_FILE):
        with open(DAEMON_TOKEN_FILE, "r") as f:
            t = f.read().strip()
        if t:
            return t
    token = secrets.token_hex(32)
    with open(DAEMON_TOKEN_FILE, "w") as f:
        f.write(token)
    try:
        os.chmod(DAEMON_TOKEN_FILE, 0o600)   # Unix：仅 owner 可读
    except Exception:
        pass
    print(f"[Node] Token generated → {DAEMON_TOKEN_FILE}")
    return token


def _require_token(authorization: Optional[str] = Header(None)):
    """写接口鉴权依赖：Authorization: Bearer <token>"""
    if not _daemon_token:
        return   # token 未初始化（测试或首次启动前），放行
    if authorization != f"Bearer {_daemon_token}":
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing token")


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _public_endpoint, _heartbeat_task, RELAY_URL, _node_cfg, _daemon_token
    await init_db()
    _daemon_token = _init_daemon_token()
    _node_cfg = _load_node_config()
    RELAY_URL = _node_cfg["local_relay"]
    _public_endpoint = await get_public_endpoint()
    print(f"[Node] Started. Public endpoint: {_public_endpoint}")
    print(f"[Node] Local relay: {RELAY_URL}")
    yield
    if _heartbeat_task:
        _heartbeat_task.cancel()


app = FastAPI(title="AgentNet Node Daemon", version="0.5.0", lifespan=lifespan)


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


class SendMessageRequest(BaseModel):
    from_did: str
    to_did: str
    content: str
    session_id: str = ""
    reply_to: int | None = None


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


# ── Agent 管理 API ────────────────────────────────────────────

@app.post("/agents/register")
async def api_register_agent(req: RegisterRequest, _=Depends(_require_token)):
    global _heartbeat_task

    agent_did_obj = DIDGenerator.create_new(req.name)
    did = req.did or agent_did_obj.did
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

    from nacl.encoding import HexEncoder
    pk_hex = signing_key.encode(HexEncoder).decode()
    await register_agent(did, profile_dict, is_local=True, private_key_hex=pk_hex)
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
    return {"results": results, "count": len(results)}


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

    return nexus.to_dict()


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


# ── 消息 API ──────────────────────────────────────────────────

@app.post("/messages/send")
async def api_send_message(req: SendMessageRequest):
    if not router.is_local(req.to_did):
        await _resolve_from_relay(req.to_did)
    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:16]}"
    return await router.route_message(req.from_did, req.to_did, req.content,
                                      session_id, req.reply_to)


@app.get("/messages/inbox/{did}")
async def api_fetch_inbox(did: str):
    messages = await fetch_inbox(did)
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
    return await router.route_message(from_did, to_did, content, session_id, reply_to)


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


def run(host: str = "0.0.0.0", port: int = NODE_PORT):
    uvicorn.run(app, host=host, port=port, log_level="info")
