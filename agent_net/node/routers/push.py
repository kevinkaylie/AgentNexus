"""Push 注册 API (ADR-012 L3/L5)"""
from fastapi import APIRouter, Depends, HTTPException

from agent_net.node._auth import _require_token, verify_token_did_binding
from agent_net.node._config import get_config
from agent_net.node._models import PushRegisterRequest, PushRefreshRequest
from agent_net.storage import (
    create_push_registration, refresh_push_registration,
    delete_push_registration, get_active_push_registrations,
)

router = APIRouter()


@router.post("/push/register")
async def api_push_register(req: PushRegisterRequest, _=Depends(_require_token)):
    if not verify_token_did_binding(req.did):
        raise HTTPException(403, f"Token not bound to DID: {req.did}. Register the agent first.")

    from urllib.parse import urlparse
    parsed = urlparse(req.callback_url)
    node_cfg = get_config()
    ssrf_allow_localhost_only = node_cfg.get("ssrf_allow_localhost_only", True)
    ssrf_allowed_hosts = node_cfg.get("ssrf_allowed_hosts", [])
    is_localhost = parsed.hostname in ("127.0.0.1", "localhost", "::1")
    is_allowed_host = parsed.hostname in ssrf_allowed_hosts

    if ssrf_allow_localhost_only and not is_localhost:
        raise HTTPException(400, f"SSRF protection: callback_url must be localhost. Got: {parsed.hostname}")
    elif not is_localhost and not is_allowed_host:
        raise HTTPException(400, f"SSRF protection: hostname '{parsed.hostname}' not in allowed list")

    result = await create_push_registration(
        did=req.did, callback_url=req.callback_url,
        callback_type=req.callback_type, push_key=req.push_key,
        expires_seconds=req.expires,
    )
    return {
        "status": "ok",
        "registration_id": result["registration_id"],
        "expires_at": result["expires_at"],
        "callback_secret": result["callback_secret"],
    }


@router.post("/push/refresh")
async def api_push_refresh(req: PushRefreshRequest, _=Depends(_require_token)):
    new_expires = await refresh_push_registration(
        did=req.did, callback_url=req.callback_url,
        callback_type=req.callback_type, expires_seconds=req.expires,
    )
    if new_expires is None:
        raise HTTPException(404, "Registration not found or expired")
    return {"status": "ok", "expires_at": new_expires}


@router.delete("/push/{did}")
async def api_push_unregister(did: str, _=Depends(_require_token)):
    deleted = await delete_push_registration(did)
    return {"status": "ok", "deleted": deleted}


@router.get("/push/{did}")
async def api_push_status(did: str):
    regs = await get_active_push_registrations(did)
    return {
        "status": "ok",
        "registrations": [{
            "registration_id": r["registration_id"],
            "callback_url": r["callback_url"],
            "callback_type": r["callback_type"],
            "expires_at": r["expires_at"],
        } for r in regs],
        "count": len(regs),
    }
