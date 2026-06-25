import json
import time

from fastapi import HTTPException

from . import server_common as _common
from .server_common import (
    DIDError,
    DIDResolver,
    _ANPN_PREFIX,
    _DIR_PREFIX,
    _PEERS_KEY,
    _REG_PREFIX,
    app,
    build_services_from_profile,
)

# ── Relay 身份端点 ───────────────────────────────────────────

@app.get("/.well-known/did.json")
async def get_relay_did_json():
    """
    返回 Relay 自身的 DID Document（did:web 方法标准路径）

    外部可通过 did:web:relay.agentnexus.top 解析此 Relay 的身份
    """
    if not _common._relay_did_document:
        raise HTTPException(status_code=500, detail="Relay identity not initialized")
    return _common._relay_did_document


# ── 调试 / 健康 ───────────────────────────────────────────────

# Lazy import at module level to avoid repeated imports in resolve_did
def _get_build_did_document():
    from agent_net.common.did_methods.utils import build_did_document
    return build_did_document


@app.get("/resolve/{did:path}")
async def resolve_did(did: str):
    """
    W3C DID Resolution — 返回 DID Document + service 数组

    解析优先级:
      1. 查本地注册表 → 用 announce 中的 pubkey 构建 DID Doc + service
      2. 查 PeerDirectory → 含 relay service
      3. DIDResolver（含所有已注册方法：agentnexus, key, web, meeet）
      4. 404
    """
    resolver = DIDResolver()
    build_did_document = _get_build_did_document()

    # 1. 本地注册表
    raw = await _common._redis.get(f"{_REG_PREFIX}{did}")
    if raw:
        info = json.loads(raw)
        pubkey_hex = info.get("pubkey_hex") or info.get("public_key_hex")
        if pubkey_hex:
            try:
                pubkey_bytes = bytes.fromhex(pubkey_hex)
                relay_url = ""
                services = build_services_from_profile(info, relay_url)
                doc = build_did_document(did, pubkey_bytes, services)
                return {"didDocument": doc, "source": "local_registry"}
            except Exception:
                pass

    # 2. PeerDirectory
    peer_raw = await _common._redis.get(f"{_DIR_PREFIX}{did}")
    if peer_raw:
        peer_entry = json.loads(peer_raw)
        pubkey_hex = peer_entry.get("pubkey_hex") or peer_entry.get("public_key_hex")
        relay_url = peer_entry.get("relay_url", "")
        if pubkey_hex:
            try:
                pubkey_bytes = bytes.fromhex(pubkey_hex)
                services = build_services_from_profile(peer_entry, relay_url)
                doc = build_did_document(did, pubkey_bytes, services)
                return {"didDocument": doc, "source": "peer_directory", "_via_relay": relay_url}
            except Exception:
                pass

    # 3. DIDResolver（含所有已注册方法）
    try:
        result = await resolver.resolve(did)
        doc = result.did_document
        response = {"didDocument": doc, "source": "resolver"}

        # 对于 meeet，添加额外的 metadata
        if result.method == "meeet":
            response["didDocumentMetadata"] = {
                "source": result.metadata.get("source", "meeet_solana"),
                "meeet_reputation_score": result.metadata.get("meeet_reputation_score", 0),
                "x402_score": result.metadata.get("x402_score", 0),
            }

        return response
    except DIDError:
        pass

    raise HTTPException(status_code=404, detail=f"Cannot resolve DID: {did}")


@app.get("/agents")
async def list_agents():
    """列出本地注册的所有 Agent（调试用）"""
    agents = []
    async for key in _common._redis.scan_iter(f"{_REG_PREFIX}*"):
        raw = await _common._redis.get(key)
        if raw:
            info = json.loads(raw)
            agents.append({**info, "online": True})
    return {"agents": agents, "count": len(agents)}


@app.get("/health")
async def health():
    reg_count = 0
    async for _ in _common._redis.scan_iter(f"{_REG_PREFIX}*"):
        reg_count += 1
    peer_count = await _common._redis.scard(_PEERS_KEY)
    dir_count = 0
    async for _ in _common._redis.scan_iter(f"{_DIR_PREFIX}*"):
        dir_count += 1
    # ANPN stats
    anpn_count = 0
    async for _ in _common._redis.scan_iter(f"{_ANPN_PREFIX}*"):
        anpn_count += 1
    return {
        "status": "ok",
        "relay_did": _common._relay_did,
        "relay_host": _common._relay_host,
        "registered": reg_count,
        "peers": peer_count,
        "peer_directory": dir_count,
        "anpn_endpoints": anpn_count,
        "timestamp": time.time(),
    }



__all__ = [name for name in globals() if not name.startswith("__")]
