"""Agent 管理、DID 解析、密钥导出导入"""
import asyncio
import uuid

import aiohttp
from fastapi import APIRouter, Depends, HTTPException

from agent_net.common.did import DIDGenerator, AgentProfile, DIDResolver, DIDError, build_services_from_profile
from agent_net.node._auth import _require_token, bind_token_to_did
from agent_net.node._config import (
    get_relay_url, get_public_endpoint_cached,
    announce_to_relay, federation_announce,
    heartbeat_loop, NODE_PORT, _heartbeat_task,
)
from agent_net.node._models import (
    RegisterRequest, UpdateCardRequest, CertifyRequest,
    ExportRequest, ImportRequest,
)
from agent_net.storage import (
    register_agent, list_local_agents, get_agent, search_agents_by_capability,
    get_private_key, update_agent_profile, add_certification, get_certifications,
)

router = APIRouter()


@router.post("/agents/register")
async def api_register_agent(req: RegisterRequest, _=Depends(_require_token)):
    import agent_net.node.routers.agents as _self
    global _heartbeat_task_ref
    RELAY_URL = get_relay_url()
    _public_endpoint = get_public_endpoint_cached()

    if req.did:
        did = req.did
        agent_did_obj = DIDGenerator.create_new(req.name)
        signing_key = agent_did_obj.private_key
    elif req.did_format == "agent":
        agent_did_obj = DIDGenerator.create_new(req.name)
        did = agent_did_obj.did
        signing_key = agent_did_obj.private_key
    else:
        agent_did_obj, _ = DIDGenerator.create_agentnexus(req.name)
        did = agent_did_obj.did
        signing_key = agent_did_obj.private_key

    endpoint = f"http://localhost:{NODE_PORT}"
    if _public_endpoint:
        endpoint = f"http://{_public_endpoint['public_ip']}:{_public_endpoint['public_port']}"

    profile = AgentProfile(
        id=did, name=req.name, type=req.type,
        capabilities=req.capabilities, location=req.location,
        endpoints={"p2p": endpoint, "relay": RELAY_URL},
    )
    profile_dict = profile.to_dict()
    profile_dict["description"] = req.description
    profile_dict["tags"] = req.tags or req.capabilities
    profile_dict["is_public"] = req.is_public
    profile_dict["public_key_hex"] = signing_key.verify_key.encode().hex()

    from nacl.encoding import HexEncoder
    pk_hex = signing_key.encode(HexEncoder).decode()
    await register_agent(did, profile_dict, is_local=True, private_key_hex=pk_hex)

    bind_token_to_did(did)

    # 启动心跳（模块级 task 引用）
    import agent_net.node._config as _cfg
    if _cfg._heartbeat_task is None or _cfg._heartbeat_task.done():
        _cfg._heartbeat_task = asyncio.create_task(heartbeat_loop(did, endpoint))

    await announce_to_relay(did, endpoint)

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
        asyncio.create_task(federation_announce(did, RELAY_URL, nexus_profile_dict))

    return {
        "did": did,
        "profile": profile.to_json_ld(),
        "nexus_profile": nexus_profile_dict,
        "is_public": req.is_public,
    }


@router.get("/agents/local")
async def api_list_local_agents():
    agents = await list_local_agents()
    return {"agents": agents, "count": len(agents)}


@router.get("/agents/search/{keyword}")
async def api_search_agents(keyword: str):
    results = await search_agents_by_capability(keyword)
    return {"agents": results, "count": len(results)}


@router.get("/resolve/{did:path}")
async def api_resolve_did(did: str):
    from nacl.signing import SigningKey
    from agent_net.node._config import load_node_config
    resolver = DIDResolver()

    agent = await get_agent(did)
    if agent:
        profile = agent.get("profile", {}) if isinstance(agent.get("profile"), dict) else {}
        pubkey_bytes = None
        private_key_hex = await get_private_key(did)
        if private_key_hex:
            try:
                sk = SigningKey(bytes.fromhex(private_key_hex))
                pubkey_bytes = sk.verify_key.encode()
            except Exception:
                pass
        if not pubkey_bytes:
            pubkey_hex = profile.get("public_key_hex")
            if pubkey_hex:
                try:
                    pubkey_bytes = bytes.fromhex(pubkey_hex)
                except ValueError:
                    pass
        if pubkey_bytes:
            node_config = load_node_config()
            relay_url = node_config.get("local_relay", "")
            services = build_services_from_profile(profile, relay_url)
            from agent_net.common.did_methods.utils import build_did_document
            doc = build_did_document(did, pubkey_bytes, services)
            return {"didDocument": doc, "source": "local_db"}

    try:
        result = await resolver.resolve(did)
        return {"didDocument": result.did_document, "source": "cryptographic"}
    except DIDError:
        pass

    node_config = load_node_config()
    relay_url = node_config.get("local_relay", "")
    if relay_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{relay_url.rstrip('/')}/resolve/{did}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        data["_via_relay"] = relay_url
                        return data
        except Exception:
            pass

    raise HTTPException(status_code=404, detail=f"Cannot resolve DID: {did}")


@router.get("/agents/{did}")
async def api_get_agent(did: str):
    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.get("/agents/{did}/profile")
async def api_get_nexus_profile(did: str):
    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, "Agent not found")
    pk_hex = await get_private_key(did)
    if not pk_hex:
        raise HTTPException(409, "Private key not available for this agent")
    from agent_net.common.profile import NexusProfile
    from nacl.signing import SigningKey
    signing_key = SigningKey(bytes.fromhex(pk_hex))
    p = agent["profile"]
    nexus = NexusProfile.create(
        did=did, signing_key=signing_key,
        name=p.get("name", ""), description=p.get("description", ""),
        tags=p.get("tags") or p.get("capabilities", []),
        relay=get_relay_url(),
        direct=p.get("endpoints", {}).get("p2p"),
    )
    for cert in p.get("certifications", []):
        nexus.add_certification(cert)
    return nexus.to_dict()


@router.patch("/agents/{did}/card")
async def api_update_card(did: str, req: UpdateCardRequest, _=Depends(_require_token)):
    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, "Agent not found")
    pk_hex = await get_private_key(did)
    if not pk_hex:
        raise HTTPException(409, "Private key not available for this agent")

    update_fields: dict = {}
    if req.name is not None:
        update_fields["name"] = req.name
    if req.description is not None:
        update_fields["description"] = req.description
    if req.tags is not None:
        update_fields["tags"] = req.tags
    if update_fields:
        await update_agent_profile(did, update_fields)

    agent = await get_agent(did)
    p = agent["profile"]
    from agent_net.common.profile import NexusProfile
    from nacl.signing import SigningKey
    signing_key = SigningKey(bytes.fromhex(pk_hex))
    nexus = NexusProfile.create(
        did=did, signing_key=signing_key,
        name=p.get("name", ""), description=p.get("description", ""),
        tags=p.get("tags") or p.get("capabilities", []),
        relay=get_relay_url(),
        direct=p.get("endpoints", {}).get("p2p"),
    )
    if p.get("is_public"):
        asyncio.create_task(federation_announce(did, get_relay_url(), nexus.to_dict()))
    return {"status": "ok", "profile": nexus.to_dict()}


@router.post("/agents/{did}/certify")
async def api_certify_agent(did: str, req: CertifyRequest, _=Depends(_require_token)):
    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, "Target agent not found")
    issuer_pk_hex = await get_private_key(req.issuer_did)
    if not issuer_pk_hex:
        raise HTTPException(409, f"Private key not available for issuer {req.issuer_did}")
    from agent_net.common.profile import create_certification
    from nacl.signing import SigningKey
    issuer_sk = SigningKey(bytes.fromhex(issuer_pk_hex))
    cert = create_certification(
        target_did=did, issuer_did=req.issuer_did,
        issuer_signing_key=issuer_sk, claim=req.claim, evidence=req.evidence,
    )
    await add_certification(did, cert)
    return {"status": "ok", "certification": cert}


@router.get("/agents/{did}/certifications")
async def api_get_certifications(did: str):
    certs = await get_certifications(did)
    return {"certifications": certs, "count": len(certs)}


@router.get("/agents/{did}/export")
async def api_export_agent(did: str, password: str, _=Depends(_require_token)):
    from agent_net.common.keystore import export_agent as _export_agent
    agent = await get_agent(did)
    if not agent:
        raise HTTPException(404, "Agent not found")
    private_key_hex = await get_private_key(did)
    if not private_key_hex:
        raise HTTPException(400, "No private key stored for this agent")
    profile = agent.get("profile", {}) or {}
    certs = await get_certifications(did)
    encrypted_bytes = _export_agent(
        did=did, private_key_hex=private_key_hex,
        profile=profile, password=password, certifications=certs,
    )
    return {"data": encrypted_bytes.decode("utf-8")}


@router.post("/agents/import")
async def api_import_agent(req: ImportRequest, _=Depends(_require_token)):
    from agent_net.common.keystore import import_agent as _import_agent
    try:
        payload = _import_agent(req.data.encode("utf-8"), req.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    did = payload["did"]
    private_key_hex = payload["private_key_hex"]
    profile = payload.get("profile", {})
    certs = payload.get("certifications", [])
    await register_agent(did, profile, is_local=True, private_key_hex=private_key_hex)
    for cert in certs:
        try:
            await add_certification(did, cert)
        except Exception:
            pass
    return {"status": "ok", "did": did, "certifications_restored": len(certs)}
