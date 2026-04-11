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
