"""
节点配置与 Relay 通信

共享状态：_node_cfg, RELAY_URL, _public_endpoint, _heartbeat_task, _cleanup_push_task
"""
import asyncio
import json
import os
import time
from typing import Optional

import aiohttp

from agent_net.common.constants import (
    NODE_CONFIG_FILE, DATA_DIR,
    RELAY_HEARTBEAT_INTERVAL, FEDERATION_PROXY_TIMEOUT,
)
from agent_net.common.profile import canonical_announce
from agent_net.storage import get_private_key

NODE_PORT = 8765

_node_cfg: dict = {}
RELAY_URL: str = "http://localhost:9000"
_public_endpoint: Optional[dict] = None
_heartbeat_task: Optional[asyncio.Task] = None
_cleanup_push_task: Optional[asyncio.Task] = None


def load_node_config() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(NODE_CONFIG_FILE):
        try:
            with open(NODE_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"local_relay": "http://localhost:9000", "seed_relays": []}


def save_node_config(cfg: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(NODE_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def init_config():
    global _node_cfg, RELAY_URL
    _node_cfg = load_node_config()
    RELAY_URL = _node_cfg["local_relay"]


def get_config() -> dict:
    return _node_cfg


def get_relay_url() -> str:
    return RELAY_URL


def set_relay_url(url: str):
    global RELAY_URL
    RELAY_URL = url


def set_public_endpoint(ep: Optional[dict]):
    global _public_endpoint
    _public_endpoint = ep


def get_public_endpoint_cached() -> Optional[dict]:
    return _public_endpoint


async def announce_to_relay(did: str, endpoint: str, relay_url: Optional[str] = None):
    url = relay_url or RELAY_URL
    payload: dict = {
        "did": did,
        "endpoint": endpoint,
        "public_ip": _public_endpoint.get("public_ip") if _public_endpoint else None,
        "public_port": _public_endpoint.get("public_port") if _public_endpoint else None,
    }
    pk_hex = await get_private_key(did)
    if pk_hex:
        from nacl.signing import SigningKey as _SK
        from nacl.encoding import RawEncoder as _RE, HexEncoder as _HE
        sk = _SK(bytes.fromhex(pk_hex))
        ts = time.time()
        canonical = canonical_announce(
            did, endpoint, ts, payload.get("public_ip"), payload.get("public_port"),
        )
        sig = sk.sign(canonical, encoder=_RE).signature.hex()
        payload["pubkey"] = sk.verify_key.encode(_HE).decode()
        payload["timestamp"] = ts
        payload["signature"] = sig
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"{url}/announce", json=payload,
                         timeout=aiohttp.ClientTimeout(total=5))
    except Exception:
        pass


async def federation_announce(did: str, local_relay: str, profile_dict: Optional[dict] = None):
    cfg = load_node_config()
    for seed in cfg.get("seed_relays", []):
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"{seed}/federation/announce",
                    json={"did": did, "relay_url": local_relay, "profile": profile_dict},
                    timeout=aiohttp.ClientTimeout(total=FEDERATION_PROXY_TIMEOUT),
                )
        except Exception:
            pass


async def heartbeat_loop(did: str, endpoint: str, interval: int = RELAY_HEARTBEAT_INTERVAL):
    while True:
        await announce_to_relay(did, endpoint)
        await asyncio.sleep(interval)


async def cleanup_expired_push_registrations_loop():
    while True:
        await asyncio.sleep(300)
        try:
            from agent_net.storage import cleanup_expired_push_registrations
            deleted = await cleanup_expired_push_registrations()
            if deleted > 0:
                print(f"[Node] Cleaned up {deleted} expired push registrations")
        except Exception as e:
            print(f"[Node] Push cleanup error: {e}")


async def resolve_from_relay(did: str):
    """从 relay 查询 DID 端点，写入本地通讯录"""
    from agent_net.storage import upsert_contact
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{RELAY_URL}/lookup/{did}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    await upsert_contact(did, data["endpoint"], RELAY_URL)
    except Exception:
        pass
