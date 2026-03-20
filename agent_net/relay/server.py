"""
Relay/Signaling Server - 种子节点信令服务器
职责：
  1. 接收 Agent 上报 DID + 物理地址（注册/心跳）
  2. 根据 DID 查询目标 Agent 的地址
  3. 健康检查
运行方式: uvicorn agent_net.relay.server:app --host 0.0.0.0 --port 9000
"""
import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

# ── 内存注册表（生产环境可替换为 Redis/DB） ───────────────
_registry: dict[str, dict] = {}
_registry_lock = asyncio.Lock()

# 超时清理间隔（秒）
_TTL = 120
_CLEANUP_INTERVAL = 60


async def _cleanup_loop():
    """定期清理过期注册条目"""
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        now = time.time()
        async with _registry_lock:
            expired = [did for did, info in _registry.items()
                       if now - info["updated_at"] > _TTL]
            for did in expired:
                del _registry[did]


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="AgentNet Relay/Signaling Server", version="0.1.0", lifespan=lifespan)


# ── 请求/响应模型 ─────────────────────────────────────────

class AnnounceRequest(BaseModel):
    did: str
    endpoint: str                  # 节点可达地址，如 http://1.2.3.4:8765
    relay: Optional[str] = None    # 该节点自身的中转地址（可选）
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
    online: bool                   # updated_at 在 TTL 内视为在线


# ── 接口 ─────────────────────────────────────────────────

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


@app.get("/lookup/{did}", response_model=LookupResponse)
async def lookup(did: str):
    """根据 DID 查询目标 Agent 的地址信息"""
    async with _registry_lock:
        info = _registry.get(did)
    if not info:
        raise HTTPException(status_code=404, detail=f"DID not found: {did}")
    online = (time.time() - info["updated_at"]) < _TTL
    return LookupResponse(**info, online=online)


@app.get("/agents")
async def list_agents():
    """列出当前所有已注册的 Agent（调试用）"""
    now = time.time()
    async with _registry_lock:
        result = [
            {**info, "online": (now - info["updated_at"]) < _TTL}
            for info in _registry.values()
        ]
    return {"agents": result, "count": len(result)}


@app.post("/relay")
async def relay_message(payload: dict):
    """
    消息中转：将消息转发给目标节点的 /deliver 端点
    若目标不在线则返回 404，由调用方决定是否离线存储
    """
    import aiohttp
    to_did = payload.get("to")
    if not to_did:
        raise HTTPException(status_code=400, detail="Missing 'to' field")

    async with _registry_lock:
        info = _registry.get(to_did)

    if not info:
        raise HTTPException(status_code=404, detail=f"DID not found: {to_did}")

    online = (time.time() - info["updated_at"]) < _TTL
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


@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "registered": len(_registry),
        "timestamp": time.time(),
    }
