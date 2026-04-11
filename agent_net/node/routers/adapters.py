"""Platform Adapters 和 Skill Registry"""
import secrets
import uuid

from fastapi import APIRouter, Header, HTTPException

from agent_net.adapters import AdapterRegistry, register_adapter
from agent_net.adapters.openclaw import OpenClawAdapter
from agent_net.adapters.webhook import WebhookAdapter
from agent_net.node._auth import _require_token
from agent_net.router import router as msg_router
from agent_net.storage import get_agent, register_skill, unregister_skill, list_skills, get_skill

router = APIRouter()


@router.post("/adapters/{platform}/invoke")
async def api_adapter_invoke(platform: str, payload: dict, authorization: str = Header(None)):
    _require_token(authorization)
    adapter = AdapterRegistry.get(platform)
    if not adapter:
        raise HTTPException(404, f"Unknown platform: {platform}")
    result = await adapter.inbound(payload)
    if "error" in result:
        status = result.pop("status", 500)
        raise HTTPException(status, result["error"])
    return result


@router.post("/adapters/{platform}/register")
async def api_adapter_register(platform: str, payload: dict, authorization: str = Header(None)):
    _require_token(authorization)
    agent_did = payload.get("agent_did")
    if not agent_did:
        raise HTTPException(400, "Missing agent_did")
    agent = await get_agent(agent_did)
    if not agent:
        raise HTTPException(404, f"Agent not found: {agent_did}")

    import agent_net.storage as _storage
    if platform == "openclaw":
        adapter = OpenClawAdapter(agent_did, msg_router, _storage)
    elif platform == "webhook":
        webhook_secret = payload.get("webhook_secret", secrets.token_hex(16))
        callback_url = payload.get("callback_url")
        adapter = WebhookAdapter(agent_did, msg_router, _storage, webhook_secret, callback_url)
    else:
        raise HTTPException(400, f"Unknown platform: {platform}")

    register_adapter(adapter)
    return {"status": "ok", "platform": platform, "agent_did": agent_did, "manifest": adapter.skill_manifest()}


@router.get("/skills")
async def api_list_skills(agent_did: str = None, capability: str = None):
    skills = await list_skills(agent_did, capability)
    return {"skills": skills}


@router.get("/skills/{skill_id}")
async def api_get_skill(skill_id: str):
    skill = await get_skill(skill_id)
    if not skill:
        raise HTTPException(404, f"Skill not found: {skill_id}")
    return skill


@router.post("/skills/register")
async def api_register_skill(payload: dict, authorization: str = Header(None)):
    _require_token(authorization)
    agent_did = payload.get("agent_did")
    name = payload.get("name")
    capabilities = payload.get("capabilities", [])
    actions = payload.get("actions", [])
    if not agent_did or not name or not actions:
        raise HTTPException(400, "Missing required fields: agent_did, name, actions")
    agent = await get_agent(agent_did)
    if not agent:
        raise HTTPException(404, f"Agent not found: {agent_did}")
    skill_id = f"skill_{uuid.uuid4().hex[:8]}_{name}"
    await register_skill(skill_id, agent_did, name, capabilities, actions)
    return {"status": "ok", "skill_id": skill_id}


@router.delete("/skills/{skill_id}")
async def api_unregister_skill(skill_id: str, authorization: str = Header(None)):
    _require_token(authorization)
    success = await unregister_skill(skill_id)
    if not success:
        raise HTTPException(404, f"Skill not found: {skill_id}")
    return {"status": "ok"}
