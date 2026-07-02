import json
import time

import aiohttp
from fastapi import HTTPException

from . import server_common as _common
from .server_common import (
    FEDERATION_PROXY_TIMEOUT,
    RELAY_TTL,
    AnnounceRequest,
    AnnounceResponse,
    _DIR_PREFIX,
    _REG_PREFIX,
    _check_rate_limit,
    app,
)

# ── 本地注册/心跳接口 ─────────────────────────────────────────

@app.post("/announce", response_model=AnnounceResponse)
async def announce(req: AnnounceRequest):
    """Agent 上报自身 DID 和物理地址（注册 / 心跳）。TTL 到期自动清除。"""
    _check_rate_limit(req.did)
    from agent_net.relay import server as server_module

    await server_module._verify_announce(req)
    now = time.time()
    value = json.dumps({
        "did": req.did,
        "endpoint": req.endpoint,
        "relay": req.relay,
        "public_ip": req.public_ip,
        "public_port": req.public_port,
        "updated_at": now,
    })
    await _common._redis.setex(f"{_REG_PREFIX}{req.did}", RELAY_TTL, value)
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
      1. 查本地注册表（Redis key 存在即在线）→ 命中直接返回
      2. 查 peer_directory → 找到所在 relay → 代理转发 GET /lookup/{did}
      3. 全部未命中 → 404
    """
    # 1. 本地查找（key 存在 = TTL 未过期 = 在线）
    raw = await _common._redis.get(f"{_REG_PREFIX}{did}")
    if raw:
        info = json.loads(raw)
        return {**info, "online": True}

    # 2. 联邦 1 跳查找
    peer_raw = await _common._redis.get(f"{_DIR_PREFIX}{did}")
    if peer_raw:
        peer_entry = json.loads(peer_raw)
        peer_relay_url = peer_entry["relay_url"]
        from agent_net.relay import server as server_module

        data = await server_module._proxy_lookup(peer_relay_url, did)
        if data is not None:
            data["_via_relay"] = peer_relay_url
            return data

    raise HTTPException(status_code=404, detail=f"DID not found: {did}")



__all__ = [name for name in globals() if not name.startswith("__")]
