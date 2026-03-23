"""
Relay/Signaling Server - 种子节点信令服务器
职责：
  1. 接收 Agent 上报 DID + 物理地址（注册/心跳）
  2. 根据 DID 查询目标 Agent 的地址（本地 + 1 跳联邦）
  3. 联邦管理：加入 peer relay 网络，接收公开 Agent 的跨 relay 公告
  4. 健康检查
运行方式: python main.py relay start
"""
import time
import asyncio
import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from agent_net.common.constants import RELAY_TTL, RELAY_CLEANUP_INTERVAL, FEDERATION_PROXY_TIMEOUT

# ── 本地注册表（内存，生产可换 Redis） ───────────────────────
_registry: dict[str, dict] = {}
_registry_lock = asyncio.Lock()

# ── 联邦数据结构 ─────────────────────────────────────────────
# peer relay URL 集合（通过 /federation/join 加入）
_peers: set[str] = set()
_peers_lock = asyncio.Lock()

# DID → peer relay URL（公开 Agent 经联邦通告写入）
_peer_directory: dict[str, dict] = {}  # did -> {relay_url, profile, updated_at}
_peer_dir_lock = asyncio.Lock()


async def _cleanup_loop():
    """定期清理过期本地注册条目"""
    while True:
        await asyncio.sleep(RELAY_CLEANUP_INTERVAL)
        now = time.time()
        async with _registry_lock:
            expired = [did for did, info in _registry.items()
                       if now - info["updated_at"] > RELAY_TTL]
            for did in expired:
                del _registry[did]


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="AgentNet Relay/Signaling Server", version="0.2.0", lifespan=lifespan)


# ── 请求/响应模型 ─────────────────────────────────────────────

class AnnounceRequest(BaseModel):
    did: str
    endpoint: str
    relay: Optional[str] = None
    public_ip: Optional[str] = None
    public_port: Optional[int] = None


class AnnounceResponse(BaseModel):
    status: str
    did: str
    updated_at: float


class LookupResponse(BaseModel):
    did: str
    endpoint: str
    relay: Optional[str]
    public_ip: Optional[str]
    public_port: Optional[int]
    updated_at: float
    online: bool


class FederationJoinRequest(BaseModel):
    relay_url: str  # 请求方 relay 的可达地址


class FederationAnnounceRequest(BaseModel):
    did: str
    relay_url: str   # 该 Agent 所在的 relay 地址
    profile: Optional[dict] = None  # NexusProfile.to_dict()，可选


# ── 本地注册/心跳接口 ─────────────────────────────────────────

@app.post("/announce", response_model=AnnounceResponse)
async def announce(req: AnnounceRequest):
    """Agent 上报自身 DID 和物理地址（注册 / 心跳）"""
    now = time.time()
    async with _registry_lock:
        _registry[req.did] = {
            "did": req.did,
            "endpoint": req.endpoint,
            "relay": req.relay,
            "public_ip": req.public_ip,
            "public_port": req.public_port,
            "updated_at": now,
        }
    return AnnounceResponse(status="ok", did=req.did, updated_at=now)


async def _proxy_lookup(peer_relay_url: str, did: str) -> dict | None:
    """向 peer relay 代理查询 DID（1 跳），失败返回 None"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{peer_relay_url}/lookup/{did}",
                timeout=aiohttp.ClientTimeout(total=FEDERATION_PROXY_TIMEOUT),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return None


@app.get("/lookup/{did}")
async def lookup(did: str):
    """
    DID 查询（含 1 跳联邦代理）：
      1. 查本地注册表 → 命中直接返回
      2. 查 peer_directory → 找到所在 relay → 代理转发 GET /lookup/{did}
      3. 全部未命中 → 404
    """
    # 1. 本地查找
    async with _registry_lock:
        info = _registry.get(did)
    if info:
        online = (time.time() - info["updated_at"]) < RELAY_TTL
        return {**info, "online": online}

    # 2. 联邦 1 跳查找
    async with _peer_dir_lock:
        peer_entry = _peer_directory.get(did)

    if peer_entry:
        peer_relay_url = peer_entry["relay_url"]
        data = await _proxy_lookup(peer_relay_url, did)
        if data is not None:
            data["_via_relay"] = peer_relay_url
            return data

    raise HTTPException(status_code=404, detail=f"DID not found: {did}")


# ── 联邦管理接口 ─────────────────────────────────────────────

@app.post("/federation/join")
async def federation_join(req: FederationJoinRequest):
    """
    另一个 relay 请求加入联邦（报名成为已知 peer）。
    加入后，本 relay 在 /lookup miss 时会查询 peer_directory。
    """
    async with _peers_lock:
        _peers.add(req.relay_url)
    return {"status": "ok", "relay_url": req.relay_url, "peers_count": len(_peers)}


@app.post("/federation/announce")
async def federation_announce(req: FederationAnnounceRequest):
    """
    本地 relay 代表公开 Agent 向种子站公告（is_public=True 触发）。
    写入 peer_directory：did → {relay_url, profile, updated_at}
    """
    async with _peer_dir_lock:
        _peer_directory[req.did] = {
            "relay_url": req.relay_url,
            "profile": req.profile,
            "updated_at": time.time(),
        }
    return {"status": "ok", "did": req.did}


@app.get("/federation/peers")
async def federation_peers():
    """列出已知 peer relay（调试用）"""
    async with _peers_lock:
        peers = list(_peers)
    return {"peers": peers, "count": len(peers)}


@app.get("/federation/directory")
async def federation_directory():
    """列出 peer_directory 中的公开 Agent（调试用）"""
    async with _peer_dir_lock:
        entries = [
            {"did": did, **info}
            for did, info in _peer_directory.items()
        ]
    return {"entries": entries, "count": len(entries)}


# ── 消息中转 ─────────────────────────────────────────────────

@app.post("/relay")
async def relay_message(payload: dict):
    """消息中转：转发给目标节点的 /deliver 端点"""
    to_did = payload.get("to")
    if not to_did:
        raise HTTPException(status_code=400, detail="Missing 'to' field")

    async with _registry_lock:
        info = _registry.get(to_did)

    if not info:
        raise HTTPException(status_code=404, detail=f"DID not found: {to_did}")

    online = (time.time() - info["updated_at"]) < RELAY_TTL
    if not online:
        raise HTTPException(status_code=503, detail="Target node offline")

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{info['endpoint']}/deliver",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return {"status": "relayed"}
                raise HTTPException(status_code=502, detail="Delivery failed")
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── 调试 / 健康 ───────────────────────────────────────────────

@app.get("/agents")
async def list_agents():
    """列出本地注册的所有 Agent（调试用）"""
    now = time.time()
    async with _registry_lock:
        result = [
            {**info, "online": (now - info["updated_at"]) < RELAY_TTL}
            for info in _registry.values()
        ]
    return {"agents": result, "count": len(result)}


@app.get("/health")
async def health():
    async with _registry_lock:
        reg_count = len(_registry)
    async with _peers_lock:
        peer_count = len(_peers)
    async with _peer_dir_lock:
        dir_count = len(_peer_directory)
    return {
        "status": "ok",
        "registered": reg_count,
        "peers": peer_count,
        "peer_directory": dir_count,
        "timestamp": time.time(),
    }
