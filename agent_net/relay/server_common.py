"""
Relay/Signaling Server - 种子节点信令服务器
职责：
  1. 接收 Agent 上报 DID + 物理地址（注册/心跳）
  2. 根据 DID 查询目标 Agent 的地址（本地 + 1 跳联邦）
  3. 联邦管理：加入 peer relay 网络，接收公开 Agent 的跨 relay 公告
  4. 健康检查
  5. 暴露自身 DID Document（did:web 方法）
运行方式: python main.py relay start [--host <domain>]
存储：Redis（注册表 TTL 到期自动清除，替代内存清理循环）
"""
import os
import json
import time
import asyncio
import aiohttp
import redis.asyncio as aioredis
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from nacl.signing import SigningKey

from agent_net.common.constants import (
    RELAY_TTL, FEDERATION_PROXY_TIMEOUT, REDIS_URL,
    ANNOUNCE_CLOCK_SKEW, ANNOUNCE_RATE_WINDOW, ANNOUNCE_RATE_MAX,
    RELAY_JOIN_VERIFY_TIMEOUT, ANNOUNCE_PUBKEY_PREFIX,
    RELAY_HOST, RELAY_IDENTITY_FILE,
)
from agent_net.common.profile import (
    NexusProfile, verify_signed_payload, canonical_announce,
)
from agent_net.common.did import DIDResolver, DIDError, build_services_from_profile
from agent_net.common import crypto
from agent_net.common.did_methods.utils import compute_x402_score

# ── Redis 客户端 ─────────────────────────────────────────────
_redis: aioredis.Redis | None = None

# Key schema:
#   relay:reg:{did}      → JSON, TTL=RELAY_TTL  (announce / heartbeat)
#   relay:peers          → Redis SET of peer relay URLs
#   relay:peerdir:{did}  → JSON, no TTL          (public agent directory)
#   relay:anpn:{did}:{protocol} → JSON, TTL=86400 (ANPN protocol endpoint)
#   relay:anpn:idx:{did} → Redis SET of protocols (ANPN index)

_REG_PREFIX = "relay:reg:"
_PEERS_KEY  = "relay:peers"
_DIR_PREFIX = "relay:peerdir:"
_ANPN_PREFIX = "relay:anpn:"
_ANPN_IDX_PREFIX = "relay:anpn:idx:"
_ANPN_TTL = 86400  # 24 hours


# ── Relay 身份管理 ──────────────────────────────────────────

_relay_signing_key: SigningKey | None = None
_relay_did: str = ""
_relay_did_document: dict = {}
_relay_host: str = ""  # 实际使用的域名


def _load_or_create_relay_identity() -> tuple[SigningKey, str]:
    """
    加载或创建 Relay 身份

    Returns: (SigningKey, did_string)
    """
    identity_file = Path(RELAY_IDENTITY_FILE)

    if identity_file.exists():
        # 加载现有身份
        data = json.loads(identity_file.read_text(encoding="utf-8"))
        sk = SigningKey(bytes.fromhex(data["private_key_hex"]))
        did = data["did"]
        return sk, did

    # 生成新身份
    sk = SigningKey.generate()
    pk_bytes = sk.verify_key.encode()
    did = f"did:web:{RELAY_HOST}"

    # 持久化
    identity_file.parent.mkdir(parents=True, exist_ok=True)
    identity_file.write_text(json.dumps({
        "private_key_hex": sk.encode().hex(),
        "public_key_hex": pk_bytes.hex(),
        "did": did,
        "created_at": time.time(),
    }, indent=2), encoding="utf-8")

    return sk, did


def _build_relay_did_document(did: str, pubkey_bytes: bytes) -> dict:
    """构建 Relay 的 DID Document"""
    multikey = crypto.encode_multikey_ed25519(pubkey_bytes)

    # X25519 for keyAgreement
    try:
        x25519_bytes = crypto.ed25519_pub_to_x25519(pubkey_bytes)
        x_multikey = crypto.encode_multikey_x25519(x25519_bytes)
    except Exception:
        x_multikey = None

    # 从 did 提取域名
    domain = did.replace("did:web:", "")

    doc = {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/ed25519-2020/v1",
        ],
        "id": did,
        "verificationMethod": [{
            "id": f"{did}#relay-key-1",
            "type": "Ed25519VerificationKey2018",
            "controller": did,
            "publicKeyMultibase": multikey,
        }],
        "authentication": [f"{did}#relay-key-1"],
        "assertionMethod": [f"{did}#relay-key-1"],
        "service": [{
            "id": "#relay-service",
            "type": "AgentRelayService",
            "serviceEndpoint": f"https://{domain}",
        }],
    }

    if x_multikey:
        doc["keyAgreement"] = [{
            "id": f"{did}#key-agreement-1",
            "type": "X25519KeyAgreementKey2019",
            "controller": did,
            "publicKeyMultibase": x_multikey,
        }]

    return doc


def init_relay_identity():
    """
    初始化 Relay 身份（在 uvicorn 启动前调用）

    从 main.py 的 relay_start() 调用
    """
    global _relay_signing_key, _relay_did, _relay_did_document, _relay_host

    _relay_signing_key, _relay_did = _load_or_create_relay_identity()
    pk_bytes = _relay_signing_key.verify_key.encode()
    _relay_did_document = _build_relay_did_document(_relay_did, pk_bytes)
    _relay_host = _relay_did.replace("did:web:", "")

    print(f"[AgentNet Relay] Identity initialized: {_relay_did}")


def _create_redis() -> aioredis.Redis:
    """Factory — monkeypatch this in tests to inject fakeredis."""
    return aioredis.from_url(REDIS_URL, decode_responses=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis

    # 确保身份已初始化
    if _relay_signing_key is None:
        init_relay_identity()

    # Resolve through the compatibility module so existing monkeypatches of
    # agent_net.relay.server._create_redis keep working after the split.
    from agent_net.relay import server as server_module

    _redis = server_module._create_redis()
    await _redis.ping()

    # 注册 DID 方法 handlers（ADR-009）
    from agent_net.common.did_methods import register_relay_handlers
    register_relay_handlers(_redis)

    yield
    await _redis.aclose()


app = FastAPI(title="AgentNet Relay/Signaling Server", version="0.6.0", lifespan=lifespan)


# ── 请求/响应模型 ─────────────────────────────────────────────

class AnnounceRequest(BaseModel):
    did: str
    endpoint: str
    relay: Optional[str] = None
    public_ip: Optional[str] = None
    public_port: Optional[int] = None
    # 签名验证字段
    pubkey: Optional[str] = None       # Ed25519 verify key, hex
    timestamp: Optional[float] = None  # Unix timestamp（被签名）
    signature: Optional[str] = None    # Ed25519 签名, hex


class AnnounceResponse(BaseModel):
    status: str
    did: str
    updated_at: float


class LookupResponse(BaseModel):
    did: str
    endpoint: str
    relay: Optional[str]
    public_ip: Optional[str]
    public_port: Optional[int]
    updated_at: float
    online: bool


class FederationJoinRequest(BaseModel):
    relay_url: str


class FederationAnnounceRequest(BaseModel):
    did: str
    relay_url: str
    profile: Optional[dict] = None


# ── ANPN 请求/响应模型 ─────────────────────────────────────────

class AnpnRegisterRequest(BaseModel):
    did: str
    protocol: str
    endpoint: str
    signature: str
    timestamp: float


class AnpnRegisterResponse(BaseModel):
    status: str
    did: str
    protocol: str
    expires_at: float


class AnpnLookupResponse(BaseModel):
    did: str
    protocol: str
    endpoint: str
    updated_at: float


class AnpnDiscoverResponse(BaseModel):
    did: str
    protocols: list[dict]


# ── 速率限制 ─────────────────────────────────────────────────

_rate_limits: dict[str, list[float]] = defaultdict(list)
_rate_call_count = 0


def _check_rate_limit(key: str) -> None:
    """按 key（DID 或 URL）限速，超限抛 429。"""
    global _rate_call_count
    now = time.time()
    window = _rate_limits[key]
    _rate_limits[key] = [t for t in window if now - t < ANNOUNCE_RATE_WINDOW]
    if len(_rate_limits[key]) >= ANNOUNCE_RATE_MAX:
        raise HTTPException(429, "Rate limit exceeded")
    _rate_limits[key].append(now)
    # 每 100 次调用清理过期 key
    _rate_call_count += 1
    if _rate_call_count >= 100:
        _rate_call_count = 0
        stale = [k for k, v in _rate_limits.items() if not v or now - v[-1] > ANNOUNCE_RATE_WINDOW]
        for k in stale:
            del _rate_limits[k]


# ── 签名验证 ─────────────────────────────────────────────────

async def _verify_announce(req: AnnounceRequest) -> None:
    """验证 /announce 请求的 Ed25519 签名 + TOFU 公钥绑定。"""
    if not req.pubkey or not req.signature or req.timestamp is None:
        raise HTTPException(401, "Missing pubkey/signature/timestamp in announce request")

    # 1. 时钟偏差检查（防重放）
    skew = abs(time.time() - req.timestamp)
    if skew > ANNOUNCE_CLOCK_SKEW:
        raise HTTPException(401, f"Announce timestamp too stale ({skew:.0f}s skew)")

    # 2. 签名验证
    payload = canonical_announce(
        req.did, req.endpoint, req.timestamp, req.public_ip, req.public_port,
    )
    try:
        verify_signed_payload(payload, req.signature, req.pubkey)
    except Exception:
        raise HTTPException(401, "Invalid announce signature")

    # 3. TOFU: 首次存储公钥，后续校验一致
    pk_key = f"{ANNOUNCE_PUBKEY_PREFIX}{req.did}"
    stored_pk = await _redis.get(pk_key)
    if stored_pk:
        if stored_pk != req.pubkey:
            raise HTTPException(403, "Pubkey mismatch for DID (TOFU violation)")
    else:
        await _redis.set(pk_key, req.pubkey)


async def _verify_federation_announce(req) -> None:
    """验证 /federation/announce 的 NexusProfile 签名。"""
    if not req.profile:
        raise HTTPException(401, "Missing profile in federation announce")

    try:
        profile = NexusProfile.from_dict(req.profile)
    except (KeyError, TypeError) as e:
        raise HTTPException(400, f"Invalid profile structure: {e}")

    if profile.did != req.did:
        raise HTTPException(400, f"Profile DID '{profile.did}' does not match request DID '{req.did}'")

    try:
        profile.verify()
    except ValueError as e:
        raise HTTPException(401, f"Profile has no signature: {e}")
    except Exception:
        raise HTTPException(401, "Profile signature verification failed")


async def _verify_federation_join(req) -> None:
    """回调验证加入联邦的 relay 确实在运行。"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{req.relay_url}/health",
                timeout=aiohttp.ClientTimeout(total=RELAY_JOIN_VERIFY_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    raise HTTPException(400, f"Relay at {req.relay_url} health check failed (status {resp.status})")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Cannot reach relay at {req.relay_url}: {e}")



__all__ = [name for name in globals() if not name.startswith("__")]
