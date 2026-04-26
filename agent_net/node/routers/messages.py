"""消息收发、通讯录、STUN、deliver"""
import json
import logging
import time
import uuid
from collections import OrderedDict

import aiohttp
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

from agent_net.node._auth import (
    _require_token,
    _verify_actor,
    _verify_actor_can_access_did,
    _verify_actor_is_owner,
)
from agent_net.node._config import get_relay_url, resolve_from_relay
from agent_net.node._models import SendMessageRequest, AddContactRequest
from agent_net.router import router as msg_router
from agent_net.storage import fetch_inbox, fetch_session, upsert_contact
from agent_net.storage import fetch_owner_inbox, fetch_owner_messages, fetch_owner_message_stats
from agent_net.storage import get_owner

router = APIRouter()

_SEEN_MESSAGE_IDS: OrderedDict[str, float] = OrderedDict()
_REPLAY_WINDOW_SECONDS = 60
_SEEN_TTL_SECONDS = 120
_SIGNED_FIELDS = {
    "from", "to", "content", "session_id", "message_id", "timestamp",
    "message_type", "protocol", "reply_to", "content_encoding",
}


def _canonical_message(payload: dict) -> bytes:
    signed = {k: payload.get(k) for k in sorted(_SIGNED_FIELDS) if k in payload}
    return json.dumps(signed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _check_replay(message_id: str, timestamp: float) -> None:
    now = time.time()
    expired = [mid for mid, seen_at in _SEEN_MESSAGE_IDS.items() if now - seen_at > _SEEN_TTL_SECONDS]
    for mid in expired:
        _SEEN_MESSAGE_IDS.pop(mid, None)
    if abs(now - float(timestamp)) > _REPLAY_WINDOW_SECONDS:
        raise HTTPException(403, "Message timestamp out of window")
    if message_id in _SEEN_MESSAGE_IDS:
        raise HTTPException(403, "Duplicate message_id")
    _SEEN_MESSAGE_IDS[message_id] = now
    while len(_SEEN_MESSAGE_IDS) > 4096:
        _SEEN_MESSAGE_IDS.popitem(last=False)


async def _resolve_public_key_hex(did: str) -> str | None:
    from agent_net.storage import get_agent
    agent = await get_agent(did)
    if agent:
        profile = agent.get("profile", {}) or {}
        pubkey_hex = profile.get("public_key_hex")
        if pubkey_hex:
            return pubkey_hex
    if did.startswith("did:agentnexus:"):
        try:
            from agent_net.common.did import decode_multibase_pubkey
            return decode_multibase_pubkey(did.split(":")[-1]).hex()
        except Exception:
            return None
    return None


async def _actor_owns_did(actor_did: str, did: str) -> bool:
    if actor_did == did:
        return True
    from agent_net.storage import get_agent
    agent = await get_agent(did)
    return bool(agent and agent.get("owner_did") == actor_did)


async def _verify_deliver_signature(payload: dict) -> None:
    signature = payload.get("signature")
    if not signature:
        logger.warning("Unsigned delivery from %s to %s (message_id=%s)",
                       payload.get("from"), payload.get("to"), payload.get("message_id"))
        return
    message_id = payload.get("message_id")
    timestamp = payload.get("timestamp")
    if not message_id or timestamp is None:
        raise HTTPException(400, "Signed delivery requires message_id and timestamp")
    _check_replay(message_id, float(timestamp))

    from_did = payload.get("from")
    pubkey_hex = await _resolve_public_key_hex(from_did)
    if not pubkey_hex:
        raise HTTPException(403, "Cannot resolve sender public key")
    try:
        from nacl.signing import VerifyKey
        VerifyKey(bytes.fromhex(pubkey_hex)).verify(_canonical_message(payload), bytes.fromhex(signature))
    except Exception:
        raise HTTPException(403, "Invalid message signature")


@router.post("/messages/send")
async def api_send_message(req: SendMessageRequest, _=Depends(_require_token)):
    await _verify_actor(req.from_did)
    if not msg_router.is_local(req.to_did):
        await resolve_from_relay(req.to_did)

    content_encoding = None
    if isinstance(req.content, str):
        content_str = req.content
    else:
        content_str = json.dumps(req.content)
        content_encoding = "json"

    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:16]}"
    t0 = time.time()
    result = await msg_router.route_message(
        req.from_did, req.to_did, content_str, session_id, req.reply_to,
        message_type=req.message_type, protocol=req.protocol,
        content_encoding=content_encoding, message_id=req.message_id,
    )

    # 自动记录交互（0.9-05）
    try:
        from agent_net.storage import record_interaction
        success = result.get("status") == "delivered"
        await record_interaction(
            from_did=req.from_did, to_did=req.to_did,
            interaction_type="message", success=success,
            response_time_ms=(time.time() - t0) * 1000,
        )
    except Exception:
        pass  # 记录失败不影响消息投递

    return result


@router.get("/messages/inbox/{did}")
async def api_fetch_inbox(did: str, actor_did: str, _=Depends(_require_token)):
    await _verify_actor_can_access_did(actor_did, did)
    messages = await fetch_inbox(did)
    return {"messages": messages, "count": len(messages), "note": "message_id included for replay protection"}


@router.get("/messages/all/{did}")
async def api_all_messages(did: str, actor_did: str, limit: int = 100, _=Depends(_require_token)):
    await _verify_actor_can_access_did(actor_did, did)
    from agent_net.storage import DB_PATH
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, from_did, content, timestamp, session_id, reply_to, "
            "message_type, protocol, content_encoding, message_id "
            "FROM messages WHERE to_did=? ORDER BY timestamp DESC LIMIT ?",
            (did, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    messages = [{
        "id": r[0], "from": r[1], "content": r[2], "timestamp": r[3],
        "session_id": r[4] or "", "reply_to": r[5],
        "message_type": r[6], "protocol": r[7], "content_encoding": r[8],
        "message_id": r[9],
    } for r in rows]
    return {"messages": messages, "count": len(messages)}


@router.get("/messages/session/{session_id}")
async def api_fetch_session(session_id: str, actor_did: str, _=Depends(_require_token)):
    await _verify_actor(actor_did)
    messages = await fetch_session(session_id)

    # S1 优化：收集去重后的 DIDs 再批量校验，避免每条消息一次 DB 查询
    related_dids: set[str] = set()
    related_dids.add(actor_did)
    for msg in messages:
        fd = msg.get("from")
        td = msg.get("to")
        if fd:
            related_dids.add(fd)
        if td:
            related_dids.add(td)

    from agent_net.storage import get_agent
    did_cache: dict[str, dict | None] = {}
    for did in related_dids:
        if did == actor_did:
            did_cache[did] = {"did": did}
            continue
        did_cache[did] = await get_agent(did)

    allowed = False
    for msg in messages:
        from_did = msg.get("from")
        to_did = msg.get("to")
        if from_did == actor_did or to_did == actor_did:
            allowed = True
            break
        target_did = from_did or to_did
        target = did_cache.get(target_did)
        if target and target.get("owner_did") == actor_did:
            allowed = True
            break
    if not allowed:
        raise HTTPException(403, "Actor is not a participant in this session")
    return {"messages": messages, "count": len(messages), "session_id": session_id, "note": "message_id included for replay protection"}


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
    await _verify_deliver_signature(payload)
    return await msg_router.route_message(
        from_did, to_did, content,
        payload.get("session_id", ""), payload.get("reply_to"),
        message_type=payload.get("message_type"),
        protocol=payload.get("protocol"),
        content_encoding=payload.get("content_encoding"),
        message_id=payload.get("message_id"),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Owner 消息中心端点 — v1.0-06
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/owner/messages/inbox")
async def api_owner_inbox(owner_did: str, actor_did: str, limit: int = 50, offset: int = 0, _=Depends(_require_token)):
    """
    聚合主 DID 下所有子 Agent 的未读消息。
    """
    await _verify_actor_is_owner(actor_did)
    if actor_did != owner_did:
        raise HTTPException(403, "Actor cannot access another owner's inbox")
    owner = await get_owner(owner_did)
    if not owner:
        raise HTTPException(404, "Owner not found")
    return await fetch_owner_inbox(owner_did, limit, offset)


@router.get("/owner/messages/all")
async def api_owner_messages(owner_did: str, actor_did: str, limit: int = 100, offset: int = 0, _=Depends(_require_token)):
    """
    聚合主 DID 下所有子 Agent 的全部消息（分页）。
    """
    await _verify_actor_is_owner(actor_did)
    if actor_did != owner_did:
        raise HTTPException(403, "Actor cannot access another owner's messages")
    owner = await get_owner(owner_did)
    if not owner:
        raise HTTPException(404, "Owner not found")
    return await fetch_owner_messages(owner_did, limit, offset)


@router.get("/owner/messages/stats")
async def api_owner_stats(owner_did: str, actor_did: str, _=Depends(_require_token)):
    """
    各子 Agent 的消息统计。
    """
    await _verify_actor_is_owner(actor_did)
    if actor_did != owner_did:
        raise HTTPException(403, "Actor cannot access another owner's stats")
    owner = await get_owner(owner_did)
    if not owner:
        raise HTTPException(404, "Owner not found")
    return await fetch_owner_message_stats(owner_did)
