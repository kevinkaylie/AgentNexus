import json
import time

import aiohttp
from fastapi import HTTPException

from . import server_common as _common
from .server_common import (
    FederationAnnounceRequest,
    FederationJoinRequest,
    _DIR_PREFIX,
    _PEERS_KEY,
    _REG_PREFIX,
    _check_rate_limit,
    app,
)

# ── 联邦管理接口 ─────────────────────────────────────────────

@app.post("/federation/join")
async def federation_join(req: FederationJoinRequest):
    """另一个 relay 请求加入联邦（报名成为已知 peer）。"""
    _check_rate_limit(req.relay_url)
    from agent_net.relay import server as server_module

    await server_module._verify_federation_join(req)
    await _common._redis.sadd(_PEERS_KEY, req.relay_url)
    count = await _common._redis.scard(_PEERS_KEY)
    return {"status": "ok", "relay_url": req.relay_url, "peers_count": count}


@app.post("/federation/announce")
async def federation_announce(req: FederationAnnounceRequest):
    """本地 relay 代表公开 Agent 向种子站公告（is_public=True 触发）。"""
    _check_rate_limit(req.did)
    from agent_net.relay import server as server_module

    await server_module._verify_federation_announce(req)
    value = json.dumps({
        "relay_url": req.relay_url,
        "profile": req.profile,
        "updated_at": time.time(),
    })
    await _common._redis.set(f"{_DIR_PREFIX}{req.did}", value)
    return {"status": "ok", "did": req.did}


@app.get("/federation/peers")
async def federation_peers():
    """列出已知 peer relay（调试用）"""
    peers = list(await _common._redis.smembers(_PEERS_KEY))
    return {"peers": peers, "count": len(peers)}


@app.get("/federation/directory")
async def federation_directory():
    """列出 peer_directory 中的公开 Agent（调试用）"""
    entries = []
    async for key in _common._redis.scan_iter(f"{_DIR_PREFIX}*"):
        raw = await _common._redis.get(key)
        if raw:
            did = key[len(_DIR_PREFIX):]
            info = json.loads(raw)
            entries.append({"did": did, **info})
    return {"entries": entries, "count": len(entries)}


# ── 消息中转 ─────────────────────────────────────────────────

@app.post("/relay")
async def relay_message(payload: dict):
    """消息中转：转发给目标节点的 /deliver 端点"""
    to_did = payload.get("to")
    if not to_did:
        raise HTTPException(status_code=400, detail="Missing 'to' field")

    raw = await _common._redis.get(f"{_REG_PREFIX}{to_did}")
    if not raw:
        raise HTTPException(status_code=404, detail=f"DID not found: {to_did}")

    info = json.loads(raw)
    endpoint = info.get("endpoint")
    if not endpoint:
        raise HTTPException(status_code=400, detail=f"Agent {to_did} has no endpoint")

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{endpoint}/deliver",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return {"status": "relayed"}
                raise HTTPException(status_code=502, detail="Delivery failed")
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=str(e))



__all__ = [name for name in globals() if not name.startswith("__")]
