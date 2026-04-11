"""握手、Gatekeeper、RuntimeVerifier"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from agent_net.common.did import DIDResolver
from agent_net.node._auth import _require_token
from agent_net.node._models import ResolveRequest, RuntimeVerifyRequest
from agent_net.node.gatekeeper import gatekeeper, GateDecision
from agent_net.storage import list_pending

router = APIRouter()


@router.post("/runtime/verify")
async def api_runtime_verify(req: RuntimeVerifyRequest):
    from agent_net.common.runtime_verifier import (
        AgentNexusRuntimeVerifier, make_storage_cert_fetcher,
    )
    verifier = AgentNexusRuntimeVerifier(
        resolver=DIDResolver(),
        trusted_cas=req.trusted_cas,
        cert_fetcher=make_storage_cert_fetcher(),
    )
    result = await verifier.verify(req.agent_did, req.agent_public_key)
    return result.to_dict()


@router.post("/handshake/init")
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
            return JSONResponse(status_code=408, content={"status": "timeout", "did": sender_did})
        if action != "allow":
            raise HTTPException(403, f"Access denied for {sender_did}")

    local_sk = SigningKey.generate()
    mgr = HandshakeManager(local_sk)
    challenge = mgr.process_init(init_packet)
    return {"status": "challenge", "packet": challenge}


@router.get("/gate/pending")
async def api_list_pending():
    items = await list_pending()
    return {"pending": items, "count": len(items)}


@router.post("/gate/resolve")
async def api_resolve(req: ResolveRequest, _=Depends(_require_token)):
    if req.action not in ("allow", "deny"):
        raise HTTPException(400, "action must be 'allow' or 'deny'")
    ok = await gatekeeper.resolve(req.did, req.action)
    if not ok:
        raise HTTPException(404, f"No pending request for {req.did}")
    return {"status": "ok", "did": req.did, "action": req.action}


@router.post("/gate/whitelist/add")
async def api_whitelist_add(payload: dict, _=Depends(_require_token)):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.whitelist_add(did)
    return {"status": "ok", "did": did}


@router.post("/gate/whitelist/remove")
async def api_whitelist_remove(payload: dict, _=Depends(_require_token)):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.whitelist_remove(did)
    return {"status": "ok", "did": did}


@router.post("/gate/blacklist/add")
async def api_blacklist_add(payload: dict, _=Depends(_require_token)):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.blacklist_add(did)
    return {"status": "ok", "did": did}


@router.post("/gate/blacklist/remove")
async def api_blacklist_remove(payload: dict, _=Depends(_require_token)):
    did = payload.get("did")
    if not did:
        raise HTTPException(400, "Missing did")
    gatekeeper.blacklist_remove(did)
    return {"status": "ok", "did": did}


@router.post("/gate/mode")
async def api_set_mode(payload: dict, _=Depends(_require_token)):
    mode = payload.get("mode")
    if mode not in ("public", "private", "ask"):
        raise HTTPException(400, "mode must be public | private | ask")
    from agent_net.node.gatekeeper import save_mode
    save_mode(mode)
    return {"status": "ok", "mode": mode}


@router.get("/gate/mode")
async def api_get_mode():
    from agent_net.node.gatekeeper import load_mode
    return {"mode": load_mode()}


@router.get("/node/config")
async def api_get_config():
    from agent_net.node._config import load_node_config
    return load_node_config()


@router.post("/node/config/local-relay")
async def api_set_local_relay(payload: dict, _=Depends(_require_token)):
    import aiohttp
    from agent_net.node._config import load_node_config, save_node_config, set_relay_url
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(400, "Missing url")
    cfg = load_node_config()
    cfg["local_relay"] = url
    save_node_config(cfg)
    set_relay_url(url)
    return {"status": "ok", "local_relay": url}


@router.post("/node/config/relay/add")
async def api_add_seed_relay(payload: dict, _=Depends(_require_token)):
    import aiohttp
    from agent_net.node._config import load_node_config, save_node_config, get_relay_url
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(400, "Missing url")
    cfg = load_node_config()
    seeds = cfg.setdefault("seed_relays", [])
    if url not in seeds:
        seeds.append(url)
    save_node_config(cfg)
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"{url}/federation/join",
                json={"relay_url": get_relay_url()},
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except Exception:
        pass
    return {"status": "ok", "seed_relays": seeds}


@router.post("/node/config/relay/remove")
async def api_remove_seed_relay(payload: dict, _=Depends(_require_token)):
    from agent_net.node._config import load_node_config, save_node_config
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(400, "Missing url")
    cfg = load_node_config()
    seeds = cfg.get("seed_relays", [])
    if url in seeds:
        seeds.remove(url)
    cfg["seed_relays"] = seeds
    save_node_config(cfg)
    return {"status": "ok", "seed_relays": seeds}
