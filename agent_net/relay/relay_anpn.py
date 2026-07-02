import json
import time

import aiohttp
from fastapi import HTTPException

from . import server_common as _common
from .server_common import (
    ANNOUNCE_CLOCK_SKEW,
    ANNOUNCE_PUBKEY_PREFIX,
    FEDERATION_PROXY_TIMEOUT,
    AnpnDiscoverResponse,
    AnpnLookupResponse,
    AnpnRegisterRequest,
    AnpnRegisterResponse,
    _ANPN_IDX_PREFIX,
    _ANPN_PREFIX,
    _ANPN_TTL,
    _DIR_PREFIX,
    _check_rate_limit,
    app,
    verify_signed_payload,
)

# ── ANPN (Agent Nexus Protocol) 端点 ──────────────────────────

@app.get("/.well-known/agent.json")
async def get_agent_json():
    """
    返回 Relay 身份和能力声明（ANPN v0.7.5）
    """
    if not _common._relay_did_document:
        raise HTTPException(status_code=500, detail="Relay identity not initialized")

    # 从 DID Document 提取公钥
    pubkey_multibase = None
    if _common._relay_did_document.get("verificationMethod"):
        vm = _common._relay_did_document["verificationMethod"][0]
        pubkey_multibase = vm.get("publicKeyMultibase")

    # 构建 services 数组
    services = []
    for svc in _common._relay_did_document.get("service", []):
        services.append({
            "type": svc.get("type", "AgentRelayService"),
            "endpoint": svc.get("serviceEndpoint", f"https://{_common._relay_host}"),
        })

    # ANPN 协议能力
    capabilities = {
        "protocols": ["anpn/1.0", "did:agentnexus", "did:web"],
    }

    return {
        "identity": {
            "did": _common._relay_did,
            "publicKey": pubkey_multibase,
            "oatr_issuer_id": _common._relay_host,
        },
        "services": services,
        "capabilities": capabilities,
    }


async def _verify_anpn_register(req: AnpnRegisterRequest) -> None:
    """验证 ANPN 注册请求的签名"""
    if not req.signature or req.timestamp is None:
        raise HTTPException(401, "Missing signature/timestamp in ANPN register request")

    # 时钟偏差检查
    skew = abs(time.time() - req.timestamp)
    if skew > ANNOUNCE_CLOCK_SKEW:
        raise HTTPException(401, f"ANPN timestamp too stale ({skew:.0f}s skew)")

    # 获取该 DID 的公钥（从 TOFU 存储）
    pk_key = f"{ANNOUNCE_PUBKEY_PREFIX}{req.did}"
    stored_pk = await _common._redis.get(pk_key)
    if not stored_pk:
        raise HTTPException(404, f"Unknown DID: {req.did} (must announce first)")

    # 构建签名 payload: did|protocol|endpoint|timestamp
    payload = f"{req.did}|{req.protocol}|{req.endpoint}|{req.timestamp}"
    try:
        verify_signed_payload(payload, req.signature, stored_pk)
    except Exception:
        raise HTTPException(401, "Invalid ANPN register signature")


@app.post("/relay/anpn-register", response_model=AnpnRegisterResponse)
async def anpn_register(req: AnpnRegisterRequest):
    """
    注册 Agent 的协议端点（ANPN）
    TTL=86400秒，同时维护索引 relay:anpn:idx:{did}
    Protocol 统一转小写存储（semi-structured 规范化）
    """
    _check_rate_limit(req.did)
    from agent_net.relay import server as server_module

    await server_module._verify_anpn_register(req)

    now = time.time()
    expires_at = now + _ANPN_TTL

    # Protocol 规范化：统一转小写
    normalized_protocol = req.protocol.lower()

    # 存储协议端点（使用规范化后的 protocol）
    value = json.dumps({
        "did": req.did,
        "protocol": normalized_protocol,
        "endpoint": req.endpoint,
        "updated_at": now,
    })
    anpn_key = f"{_ANPN_PREFIX}{req.did}:{normalized_protocol}"
    await _common._redis.setex(anpn_key, _ANPN_TTL, value)

    # 维护索引（使用规范化后的 protocol）
    idx_key = f"{_ANPN_IDX_PREFIX}{req.did}"
    await _common._redis.sadd(idx_key, normalized_protocol)
    await _common._redis.expire(idx_key, _ANPN_TTL)

    return AnpnRegisterResponse(
        status="ok",
        did=req.did,
        protocol=normalized_protocol,
        expires_at=expires_at,
    )


async def _proxy_anpn_lookup(peer_relay_url: str, did: str, protocol: str) -> dict | None:
    """向 peer relay 代理查询 ANPN（1跳）"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{peer_relay_url}/relay/anpn-lookup/{did}/{protocol}",
                timeout=aiohttp.ClientTimeout(total=FEDERATION_PROXY_TIMEOUT),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return None


@app.get("/relay/anpn-lookup/{did}/{protocol}")
async def anpn_lookup(did: str, protocol: str):
    """
    查询 Agent 的协议端点（本地 + 1跳联邦代理）
    Protocol 统一转小写查询（semi-structured 规范化）
    """
    # Protocol 规范化：统一转小写
    normalized_protocol = protocol.lower()

    # 本地查询（使用规范化后的 protocol）
    anpn_key = f"{_ANPN_PREFIX}{did}:{normalized_protocol}"
    raw = await _common._redis.get(anpn_key)
    if raw:
        info = json.loads(raw)
        return AnpnLookupResponse(
            did=info["did"],
            protocol=info["protocol"],
            endpoint=info["endpoint"],
            updated_at=info["updated_at"],
        )

    # 联邦代理查询（1跳）
    # 先查该 DID 是否在 peer_directory 中
    peer_raw = await _common._redis.get(f"{_DIR_PREFIX}{did}")
    if peer_raw:
        peer_entry = json.loads(peer_raw)
        peer_relay_url = peer_entry.get("relay_url")
        if peer_relay_url:
            data = await _proxy_anpn_lookup(peer_relay_url, did, normalized_protocol)
            if data is not None:
                data["_via_relay"] = peer_relay_url
                return data

    raise HTTPException(status_code=404, detail=f"ANPN endpoint not found: {did}/{normalized_protocol}")


@app.get("/relay/anpn-discover/{did}")
async def anpn_discover(did: str):
    """
    发现 Agent 支持的所有协议（从索引批量查询）
    """
    idx_key = f"{_ANPN_IDX_PREFIX}{did}"
    protocols = await _common._redis.smembers(idx_key)

    if not protocols:
        raise HTTPException(status_code=404, detail=f"No ANPN protocols found for: {did}")

    # 批量查询详情
    result = []
    for proto in protocols:
        anpn_key = f"{_ANPN_PREFIX}{did}:{proto}"
        raw = await _common._redis.get(anpn_key)
        if raw:
            info = json.loads(raw)
            result.append({
                "protocol": info["protocol"],
                "endpoint": info["endpoint"],
                "updated_at": info["updated_at"],
            })

    return AnpnDiscoverResponse(
        did=did,
        protocols=result,
    )



__all__ = [name for name in globals() if not name.startswith("__")]
