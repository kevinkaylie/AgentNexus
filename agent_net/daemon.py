"""
Agent-Net-Daemon - 后端核心服务
提供HTTP API供MCP Server调用，管理本地Agent注册、消息路由、STUN探测
"""
import asyncio
import json
import time
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from .identity import generate_did, AgentProfile
from .storage import (
    init_db, register_agent, list_local_agents, get_agent,
    fetch_inbox, search_agents_by_capability, upsert_contact
)
from .router import router
from .stun import get_public_endpoint

app = FastAPI(title="AgentNet Daemon", version="0.1.0")

# 启动时缓存的公网端点
_public_endpoint: dict | None = None


@app.on_event("startup")
async def startup():
    await init_db()
    global _public_endpoint
    _public_endpoint = await get_public_endpoint()
    print(f"[AgentNet] Daemon started. Public endpoint: {_public_endpoint}")


# ── 请求模型 ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    type: str = "GeneralAgent"
    capabilities: list[str] = []
    location: str = ""
    did: Optional[str] = None  # 可指定DID，否则自动生成


class SendMessageRequest(BaseModel):
    from_did: str
    to_did: str
    content: str


class AddContactRequest(BaseModel):
    did: str
    endpoint: str
    relay: Optional[str] = None


# ── API 端点 ──────────────────────────────────────────────

@app.post("/agents/register")
async def api_register_agent(req: RegisterRequest):
    did = req.did or generate_did(req.name)
    endpoint = f"http://localhost:8765"
    if _public_endpoint:
        endpoint = f"http://{_public_endpoint['public_ip']}:{_public_endpoint['public_port']}"

    profile = AgentProfile(
        id=did,
        name=req.name,
        type=req.type,
        capabilities=req.capabilities,
        location=req.location,
        endpoints={"p2p": endpoint, "relay": ""},
    )
    await register_agent(did, profile.to_dict(), is_local=True)
    router.register_local_session(did)
    return {"did": did, "profile": profile.to_json_ld()}


@app.get("/agents/local")
async def api_list_local_agents():
    agents = await list_local_agents()
    return {"agents": agents, "count": len(agents)}


@app.get("/agents/{did}")
async def api_get_agent(did: str):
    agent = await get_agent(did)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.post("/messages/send")
async def api_send_message(req: SendMessageRequest):
    result = await router.route_message(req.from_did, req.to_did, req.content)
    return result


@app.get("/messages/inbox/{did}")
async def api_fetch_inbox(did: str):
    messages = await fetch_inbox(did)
    return {"messages": messages, "count": len(messages)}


@app.get("/agents/search/{keyword}")
async def api_search_agents(keyword: str):
    results = await search_agents_by_capability(keyword)
    return {"results": results, "count": len(results)}


@app.post("/contacts/add")
async def api_add_contact(req: AddContactRequest):
    await upsert_contact(req.did, req.endpoint, req.relay)
    return {"status": "ok"}


@app.get("/stun/endpoint")
async def api_stun_endpoint():
    ep = await get_public_endpoint()
    return ep or {"error": "STUN failed"}


@app.post("/deliver")
async def api_deliver(payload: dict):
    """接收来自远程节点的消息投递"""
    from_did = payload.get("from")
    to_did = payload.get("to")
    content = payload.get("content")
    if not all([from_did, to_did, content]):
        raise HTTPException(status_code=400, detail="Missing fields")
    result = await router.route_message(from_did, to_did, content)
    return result


def run_daemon(host: str = "0.0.0.0", port: int = 8765):
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_daemon()
