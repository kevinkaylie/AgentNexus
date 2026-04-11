"""消息收发、通讯录、STUN、deliver"""
import json
import time
import uuid

import aiohttp
from fastapi import APIRouter, Depends, HTTPException

from agent_net.node._auth import _require_token
from agent_net.node._config import get_relay_url, resolve_from_relay
from agent_net.node._models import SendMessageRequest, AddContactRequest
from agent_net.router import router as msg_router
from agent_net.storage import fetch_inbox, fetch_session, upsert_contact

router = APIRouter()


@router.post("/messages/send")
async def api_send_message(req: SendMessageRequest):
    if not msg_router.is_local(req.to_did):
        await resolve_from_relay(req.to_did)

    content_encoding = None
    if isinstance(req.content, str):
        content_str = req.content
    else:
        content_str = json.dumps(req.content)
        content_encoding = "json"

    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:16]}"
    return await msg_router.route_message(
        req.from_did, req.to_did, content_str, session_id, req.reply_to,
        message_type=req.message_type, protocol=req.protocol,
        content_encoding=content_encoding,
    )


@router.get("/messages/inbox/{did}")
async def api_fetch_inbox(did: str):
    messages = await fetch_inbox(did)
    return {"messages": messages, "count": len(messages)}


@router.get("/messages/all/{did}")
async def api_all_messages(did: str, limit: int = 100):
    from agent_net.storage import DB_PATH
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, from_did, content, timestamp, session_id, reply_to, "
            "message_type, protocol, content_encoding "
            "FROM messages WHERE to_did=? ORDER BY timestamp DESC LIMIT ?",
            (did, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    messages = [{
        "id": r[0], "from": r[1], "content": r[2], "timestamp": r[3],
        "session_id": r[4] or "", "reply_to": r[5],
        "message_type": r[6], "protocol": r[7], "content_encoding": r[8],
    } for r in rows]
    return {"messages": messages, "count": len(messages)}


@router.get("/messages/session/{session_id}")
async def api_fetch_session(session_id: str):
    messages = await fetch_session(session_id)
    return {"messages": messages, "count": len(messages), "session_id": session_id}


@router.post("/contacts/add")
async def api_add_contact(req: AddContactRequest, _=Depends(_require_token)):
    await upsert_contact(req.did, req.endpoint, req.relay)
    return {"status": "ok"}


@router.get("/stun/endpoint")
async def api_stun_endpoint():
    from agent_net.stun import get_public_endpoint
    ep = await get_public_endpoint()
    return ep or {"error": "STUN failed"}


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time()}


@router.post("/deliver")
async def api_deliver(payload: dict):
    from_did = payload.get("from")
    to_did = payload.get("to")
    content = payload.get("content")
    if not all([from_did, to_did, content]):
        raise HTTPException(400, "Missing fields")
    return await msg_router.route_message(
        from_did, to_did, content,
        payload.get("session_id", ""), payload.get("reply_to"),
        message_type=payload.get("message_type"),
        protocol=payload.get("protocol"),
    )
