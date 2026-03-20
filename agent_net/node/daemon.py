"""
agent_net.node.daemon
本地节点后端服务 —— 仅负责：
  1. 本地 Agent 注册与管理
  2. P2P 打洞（STUN 探测）
  3. 连接 Relay 服务器（announce 心跳）
  4. 消息路由（local → P2P → relay → offline）
  5. 握手入口 + Gatekeeper 访问控制
监听: 0.0.0.0:8765
"""
import asyncio
import time
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

import aiohttp

from agent_net.common.did import DIDGenerator, AgentProfile
from agent_net.storage import (
    init_db, register_agent, list_local_agents, get_agent,
    fetch_inbox, search_agents_by_capability, upsert_contact,
    list_pending, get_pending, resolve_pending,
)
from agent_net.router import router
from agent_net.stun import get_public_endpoint
from agent_net.node.gatekeeper import gatekeeper, GateDecision

RELAY_URL = "http://localhost:9000"
NODE_PORT = 8765
_public_endpoint: dict | None = None
_heartbeat_task: asyncio.Task | None = None

# did -> asyncio.Future，握手 PENDING 时挂起，resolve 后唤醒
_handshake_waiters: dict[str, asyncio.Future] = {}


async def _announce_to_relay(did: str, endpoint: str):
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"{RELAY_URL}/announce", json={
                "did": did,
                "endpoint": endpoint,
                "public_ip": _public_endpoint.get("public_ip") if _public_endpoint else None,
                "public_port": _public_endpoint.get("public_port") if _public_endpoint else None,
            }, timeout=aiohttp.ClientTimeout(total=5))
    except Exception:
        pass


async def _heartbeat_loop(did: str, endpoint: str, interval: int = 60):
    while True:
        await _announce_to_relay(did, endpoint)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _public_endpoint, _heartbeat_task
    await init_db()
    _public_endpoint = await get_public_endpoint()
    print(f"[Node] Started. Public endpoint: {_public_endpoint}")
    yield
    if _heartbeat_task:
        _heartbeat_task.cancel()


app = FastAPI(title="AgentNet Node Daemon", version="0.1.0", lifespan=lifespan)


# ── 请求模型 ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    type: str = "GeneralAgent"
    capabilities: list[str] = []
    location: str = ""
    did: Optional[str] = None


class SendMessageRequest(BaseModel):
    from_did: str
    to_did: str
    content: str


class AddContactRequest(BaseModel):
    did: str
    endpoint: str
    relay: Optional[str] = None


class ResolveRequest(BaseModel):
    did: str
    action: str   # 'allow' | 'deny'


# ── API ───────────────────────────────────────────────────

@app.post("/agents/register")
async def api_register_agent(req: RegisterRequest):
    global _heartbeat_task
    did = req.did or DIDGenerator.create_new(req.name).did
    endpoint = f"http://localhost:{NODE_PORT}"
    if _public_endpoint:
        endpoint = f"http://{_public_endpoint['public_ip']}:{_public_endpoint['public_port']}"

    profile = AgentProfile(
        id=did, name=req.name, type=req.type,
        capabilities=req.capabilities, location=req.location,
        endpoints={"p2p": endpoint, "relay": RELAY_URL},
    )
    await register_agent(did, profile.to_dict(), is_local=True)
    router.register_local_session(did)

    if _heartbeat_task is None or _heartbeat_task.done():
        _heartbeat_task = asyncio.create_task(_heartbeat_loop(did, endpoint))

    await _announce_to_relay(did, endpoint)
    return {"did": did, "profile": profile.to_json_ld()}


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


@app.post("/messages/send")
async def api_send_message(req: SendMessageRequest):
    if not router.is_local(req.to_did):
        await _resolve_from_relay(req.to_did)
    return await router.route_message(req.from_did, req.to_did, req.content)


@app.get("/messages/inbox/{did}")
async def api_fetch_inbox(did: str):
    messages = await fetch_inbox(did)
    return {"messages": messages, "count": len(messages)}


@app.post("/contacts/add")
async def api_add_contact(req: AddContactRequest):
    await upsert_contact(req.did, req.endpoint, req.relay)
    return {"status": "ok"}


@app.get("/stun/endpoint")
async def api_stun_endpoint():
    ep = await get_public_endpoint()
    return ep or {"error": "STUN failed"}


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time()}


# ── 握手入口（含 Gatekeeper 检查点）─────────────────────

@app.post("/handshake/init")
async def api_handshake_init(init_packet: dict):
    """
    远程节点发来握手 INIT 包，经 Gatekeeper 决策：
      ALLOW   → 继续握手，返回 CHALLENGE
      DENY    → 403
      PENDING → 202，挂起等待人工审批（超时 300s 自动拒绝）
    """
    from agent_net.common.handshake import HandshakeManager
    from nacl.signing import SigningKey

    sender_did = init_packet.get("sender_did")
    if not sender_did:
        raise HTTPException(400, "Missing sender_did")

    decision = await gatekeeper.check(sender_did, init_packet)

    if decision == GateDecision.DENY:
        raise HTTPException(403, f"Access denied for {sender_did}")

    if decision == GateDecision.PENDING:
        # 挂起协程，等待 resolve 唤醒（最长 300s）
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

    # ALLOW（或 PENDING 审批通过）— 生成 CHALLENGE
    local_sk = SigningKey.generate()   # 节点临时身份，生产环境应持久化
    mgr = HandshakeManager(local_sk)
    challenge = mgr.process_init(init_packet)
    return {"status": "challenge", "packet": challenge}


# ── Gatekeeper 管理接口 ───────────────────────────────────

@app.get("/gate/pending")
async def api_list_pending():
    items = await list_pending()
    return {"pending": items, "count": len(items)}


@app.post("/gate/resolve")
async def api_resolve(req: ResolveRequest):
    if req.action not in ("allow", "deny"):
        raise HTTPException(400, "action must be 'allow' or 'deny'")
    ok = await gatekeeper.resolve(req.did, req.action)
    if not ok:
        raise HTTPException(404, f"No pending request for {req.did}")
    return {"status": "ok", "did": req.did, "action": req.action}


@app.post("/gate/whitelist/add")
async def api_whitelist_add(payload: dict):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.whitelist_add(did)
    return {"status": "ok", "did": did}


@app.post("/gate/whitelist/remove")
async def api_whitelist_remove(payload: dict):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.whitelist_remove(did)
    return {"status": "ok", "did": did}


@app.post("/gate/blacklist/add")
async def api_blacklist_add(payload: dict):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.blacklist_add(did)
    return {"status": "ok", "did": did}


@app.post("/gate/blacklist/remove")
async def api_blacklist_remove(payload: dict):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.blacklist_remove(did)
    return {"status": "ok", "did": did}


@app.post("/gate/mode")
async def api_set_mode(payload: dict):
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


# ── 内部工具 ──────────────────────────────────────────────

@app.post("/deliver")
async def api_deliver(payload: dict):
    from_did = payload.get("from")
    to_did = payload.get("to")
    content = payload.get("content")
    if not all([from_did, to_did, content]):
        raise HTTPException(400, "Missing fields")
    return await router.route_message(from_did, to_did, content)


async def _resolve_from_relay(did: str):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{RELAY_URL}/lookup/{did}",
                             timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    await upsert_contact(did, data["endpoint"], RELAY_URL)
    except Exception:
        pass


def run(host: str = "0.0.0.0", port: int = NODE_PORT):
    uvicorn.run(app, host=host, port=port, log_level="info")
