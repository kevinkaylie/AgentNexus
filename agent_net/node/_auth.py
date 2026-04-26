"""
Token 管理与 DID 绑定

共享状态：_daemon_token, _TOKEN_DID_BINDINGS
"""
import hashlib
import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Header

from agent_net.common.constants import DATA_DIR, DAEMON_TOKEN_FILE

USER_TOKEN_DIR = Path.home() / ".agentnexus"
USER_TOKEN_FILE = USER_TOKEN_DIR / "daemon_token.txt"

_daemon_token: str = ""
_TOKEN_DID_BINDINGS: dict[str, list[str]] = {}


def init_daemon_token() -> str:
    global _daemon_token
    os.makedirs(DATA_DIR, exist_ok=True)

    if USER_TOKEN_FILE.exists():
        t = USER_TOKEN_FILE.read_text().strip()
        if t:
            with open(DAEMON_TOKEN_FILE, "w") as f:
                f.write(t)
            try:
                os.chmod(DAEMON_TOKEN_FILE, 0o600)
            except Exception:
                pass
            _daemon_token = t
            return t

    if os.path.exists(DAEMON_TOKEN_FILE):
        with open(DAEMON_TOKEN_FILE, "r") as f:
            t = f.read().strip()
        if t:
            USER_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
            USER_TOKEN_FILE.write_text(t)
            try:
                os.chmod(USER_TOKEN_FILE, 0o600)
            except Exception:
                pass
            _daemon_token = t
            return t

    token = secrets.token_hex(32)
    with open(DAEMON_TOKEN_FILE, "w") as f:
        f.write(token)
    try:
        os.chmod(DAEMON_TOKEN_FILE, 0o600)
    except Exception:
        pass
    USER_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    USER_TOKEN_FILE.write_text(token)
    try:
        os.chmod(USER_TOKEN_FILE, 0o600)
    except Exception:
        pass
    print(f"[Node] Token generated → {DAEMON_TOKEN_FILE}")
    _daemon_token = token
    return token


def get_token() -> str:
    return _daemon_token


def _require_token(authorization: Optional[str] = Header(None)):
    if not _daemon_token:
        return
    if authorization != f"Bearer {_daemon_token}":
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing token")


def bind_token_to_did(did: str) -> None:
    token_hash = hashlib.sha256(_daemon_token.encode()).hexdigest()
    if token_hash not in _TOKEN_DID_BINDINGS:
        _TOKEN_DID_BINDINGS[token_hash] = []
    if did not in _TOKEN_DID_BINDINGS[token_hash]:
        _TOKEN_DID_BINDINGS[token_hash].append(did)


def verify_token_did_binding(did: str) -> bool:
    if not _daemon_token:
        return True
    token_hash = hashlib.sha256(_daemon_token.encode()).hexdigest()
    return did in _TOKEN_DID_BINDINGS.get(token_hash, [])


async def _verify_actor(actor_did: str) -> dict:
    """校验 actor_did 是本 Daemon 管理的 DID。"""
    if not actor_did:
        raise HTTPException(400, "Missing actor DID")
    from agent_net.storage import get_agent
    agent = await get_agent(actor_did)
    if not agent:
        raise HTTPException(403, f"DID not managed by this daemon: {actor_did}")
    return agent


async def _verify_actor_is_owner(actor_did: str) -> dict:
    """校验 actor_did 是本 Daemon 管理的 Owner DID。"""
    if not actor_did:
        raise HTTPException(400, "Missing owner DID")
    from agent_net.storage import get_owner
    owner = await get_owner(actor_did)
    if not owner:
        raise HTTPException(403, f"Not a registered owner: {actor_did}")
    return owner


async def _verify_actor_is_secretary(actor_did: str) -> dict:
    """校验 actor_did 是本地注册的 Secretary 子 Agent。"""
    from agent_net.storage import is_secretary
    sec = await is_secretary(actor_did)
    if not sec:
        raise HTTPException(403, f"Not a registered secretary: {actor_did}")
    return sec


async def _verify_actor_can_access_did(actor_did: str, target_did: str) -> dict:
    """允许 DID 本人或其 Owner 访问目标 DID。"""
    actor = await _verify_actor(actor_did)
    if actor_did == target_did:
        return actor

    from agent_net.storage import get_agent
    target = await get_agent(target_did)
    if not target:
        raise HTTPException(404, f"Agent not found: {target_did}")
    if target.get("owner_did") == actor_did:
        await _verify_actor_is_owner(actor_did)
        return actor
    raise HTTPException(403, f"{actor_did} cannot access {target_did}")


async def _verify_actor_is_enclave_member(enclave_id: str, actor_did: str) -> dict:
    """校验 actor_did 是 Enclave 成员。"""
    await _verify_actor(actor_did)
    from agent_net.storage import get_enclave, get_enclave_member
    enclave = await get_enclave(enclave_id)
    if not enclave:
        raise HTTPException(404, f"Enclave not found: {enclave_id}")
    member = await get_enclave_member(enclave_id, actor_did)
    if not member:
        raise HTTPException(403, f"Not a member of enclave {enclave_id}: {actor_did}")
    return member


async def _verify_actor_is_enclave_owner(enclave_id: str, actor_did: str) -> dict:
    """校验 actor_did 是 Enclave owner。"""
    await _verify_actor(actor_did)
    from agent_net.storage import get_enclave
    enclave = await get_enclave(enclave_id)
    if not enclave:
        raise HTTPException(404, f"Enclave not found: {enclave_id}")
    if enclave["owner_did"] != actor_did:
        raise HTTPException(403, f"Not the owner of enclave {enclave_id}")
    return enclave
