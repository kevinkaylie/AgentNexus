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

    _redis = _create_redis()
    await _redis.ping()
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


# ── 本地注册/心跳接口 ─────────────────────────────────────────

@app.post("/announce", response_model=AnnounceResponse)
async def announce(req: AnnounceRequest):
    """Agent 上报自身 DID 和物理地址（注册 / 心跳）。TTL 到期自动清除。"""
    _check_rate_limit(req.did)
    await _verify_announce(req)
    now = time.time()
    value = json.dumps({
        "did": req.did,
        "endpoint": req.endpoint,
        "relay": req.relay,
        "public_ip": req.public_ip,
        "public_port": req.public_port,
        "updated_at": now,
    })
    await _redis.setex(f"{_REG_PREFIX}{req.did}", RELAY_TTL, value)
    return AnnounceResponse(status="ok", did=req.did, updated_at=now)


async def _proxy_lookup(peer_relay_url: str, did: str) -> dict | None:
    """向 peer relay 代理查询 DID（1 跳），失败返回 None"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{peer_relay_url}/lookup/{did}",
                timeout=aiohttp.ClientTimeout(total=FEDERATION_PROXY_TIMEOUT),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return None


@app.get("/lookup/{did}")
async def lookup(did: str):
    """
    DID 查询（含 1 跳联邦代理）：
      1. 查本地注册表（Redis key 存在即在线）→ 命中直接返回
      2. 查 peer_directory → 找到所在 relay → 代理转发 GET /lookup/{did}
      3. 全部未命中 → 404
    """
    # 1. 本地查找（key 存在 = TTL 未过期 = 在线）
    raw = await _redis.get(f"{_REG_PREFIX}{did}")
    if raw:
        info = json.loads(raw)
        return {**info, "online": True}

    # 2. 联邦 1 跳查找
    peer_raw = await _redis.get(f"{_DIR_PREFIX}{did}")
    if peer_raw:
        peer_entry = json.loads(peer_raw)
        peer_relay_url = peer_entry["relay_url"]
        data = await _proxy_lookup(peer_relay_url, did)
        if data is not None:
            data["_via_relay"] = peer_relay_url
            return data

    raise HTTPException(status_code=404, detail=f"DID not found: {did}")


# ── 联邦管理接口 ─────────────────────────────────────────────

@app.post("/federation/join")
async def federation_join(req: FederationJoinRequest):
    """另一个 relay 请求加入联邦（报名成为已知 peer）。"""
    _check_rate_limit(req.relay_url)
    await _verify_federation_join(req)
    await _redis.sadd(_PEERS_KEY, req.relay_url)
    count = await _redis.scard(_PEERS_KEY)
    return {"status": "ok", "relay_url": req.relay_url, "peers_count": count}


@app.post("/federation/announce")
async def federation_announce(req: FederationAnnounceRequest):
    """本地 relay 代表公开 Agent 向种子站公告（is_public=True 触发）。"""
    _check_rate_limit(req.did)
    await _verify_federation_announce(req)
    value = json.dumps({
        "relay_url": req.relay_url,
        "profile": req.profile,
        "updated_at": time.time(),
    })
    await _redis.set(f"{_DIR_PREFIX}{req.did}", value)
    return {"status": "ok", "did": req.did}


@app.get("/federation/peers")
async def federation_peers():
    """列出已知 peer relay（调试用）"""
    peers = list(await _redis.smembers(_PEERS_KEY))
    return {"peers": peers, "count": len(peers)}


@app.get("/federation/directory")
async def federation_directory():
    """列出 peer_directory 中的公开 Agent（调试用）"""
    entries = []
    async for key in _redis.scan_iter(f"{_DIR_PREFIX}*"):
        raw = await _redis.get(key)
        if raw:
            did = key[len(_DIR_PREFIX):]
            info = json.loads(raw)
            entries.append({"did": did, **info})
    return {"entries": entries, "count": len(entries)}


# ── 消息中转 ─────────────────────────────────────────────────

@app.post("/relay")
async def relay_message(payload: dict):
    """消息中转：转发给目标节点的 /deliver 端点"""
    to_did = payload.get("to")
    if not to_did:
        raise HTTPException(status_code=400, detail="Missing 'to' field")

    raw = await _redis.get(f"{_REG_PREFIX}{to_did}")
    if not raw:
        raise HTTPException(status_code=404, detail=f"DID not found: {to_did}")

    info = json.loads(raw)
    endpoint = info.get("endpoint")
    if not endpoint:
        raise HTTPException(status_code=400, detail=f"Agent {to_did} has no endpoint")

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{endpoint}/deliver",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return {"status": "relayed"}
                raise HTTPException(status_code=502, detail="Delivery failed")
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Relay 身份端点 ───────────────────────────────────────────

@app.get("/.well-known/did.json")
async def get_relay_did_json():
    """
    返回 Relay 自身的 DID Document（did:web 方法标准路径）

    外部可通过 did:web:relay.agentnexus.top 解析此 Relay 的身份
    """
    if not _relay_did_document:
        raise HTTPException(status_code=500, detail="Relay identity not initialized")
    return _relay_did_document


# ── 调试 / 健康 ───────────────────────────────────────────────

@app.get("/resolve/{did:path}")
async def resolve_did(did: str):
    """
    W3C DID Resolution — 返回 DID Document + service 数组

    解析优先级:
      1. 查本地注册表 → 用 announce 中的 pubkey 构建 DID Doc + service
      2. 查 PeerDirectory → 含 relay service
      3. 纯密码学解析 (did:agentnexus multikey) — 无需网络
      4. 404
    """
    resolver = DIDResolver()

    # 1. 本地注册表
    raw = await _redis.get(f"{_REG_PREFIX}{did}")
    if raw:
        info = json.loads(raw)
        pubkey_hex = info.get("pubkey_hex") or info.get("public_key_hex")
        if pubkey_hex:
            try:
                pubkey_bytes = bytes.fromhex(pubkey_hex)
                relay_url = ""
                services = build_services_from_profile(info, relay_url)
                doc = resolver._build_did_document(did, pubkey_bytes, services)
                return {"didDocument": doc, "source": "local_registry"}
            except Exception:
                pass

    # 2. PeerDirectory
    peer_raw = await _redis.get(f"{_DIR_PREFIX}{did}")
    if peer_raw:
        peer_entry = json.loads(peer_raw)
        pubkey_hex = peer_entry.get("pubkey_hex") or peer_entry.get("public_key_hex")
        relay_url = peer_entry.get("relay_url", "")
        if pubkey_hex:
            try:
                pubkey_bytes = bytes.fromhex(pubkey_hex)
                services = build_services_from_profile(peer_entry, relay_url)
                doc = resolver._build_did_document(did, pubkey_bytes, services)
                return {"didDocument": doc, "source": "peer_directory", "_via_relay": relay_url}
            except Exception:
                pass

    # 3. 纯密码学解析 (did:agentnexus)
    try:
        result = await resolver.resolve(did)
        doc = result.did_document
        return {"didDocument": doc, "source": "cryptographic"}
    except DIDError:
        pass

    raise HTTPException(status_code=404, detail=f"Cannot resolve DID: {did}")


@app.get("/agents")
async def list_agents():
    """列出本地注册的所有 Agent（调试用）"""
    agents = []
    async for key in _redis.scan_iter(f"{_REG_PREFIX}*"):
        raw = await _redis.get(key)
        if raw:
            info = json.loads(raw)
            agents.append({**info, "online": True})
    return {"agents": agents, "count": len(agents)}


@app.get("/health")
async def health():
    reg_count = 0
    async for _ in _redis.scan_iter(f"{_REG_PREFIX}*"):
        reg_count += 1
    peer_count = await _redis.scard(_PEERS_KEY)
    dir_count = 0
    async for _ in _redis.scan_iter(f"{_DIR_PREFIX}*"):
        dir_count += 1
    # ANPN stats
    anpn_count = 0
    async for _ in _redis.scan_iter(f"{_ANPN_PREFIX}*"):
        anpn_count += 1
    return {
        "status": "ok",
        "relay_did": _relay_did,
        "relay_host": _relay_host,
        "registered": reg_count,
        "peers": peer_count,
        "peer_directory": dir_count,
        "anpn_endpoints": anpn_count,
        "timestamp": time.time(),
    }


# ── ANPN (Agent Nexus Protocol) 端点 ──────────────────────────

@app.get("/.well-known/agent.json")
async def get_agent_json():
    """
    返回 Relay 身份和能力声明（ANPN v0.7.5）
    """
    if not _relay_did_document:
        raise HTTPException(status_code=500, detail="Relay identity not initialized")

    # 从 DID Document 提取公钥
    pubkey_multibase = None
    if _relay_did_document.get("verificationMethod"):
        vm = _relay_did_document["verificationMethod"][0]
        pubkey_multibase = vm.get("publicKeyMultibase")

    # 构建 services 数组
    services = []
    for svc in _relay_did_document.get("service", []):
        services.append({
            "type": svc.get("type", "AgentRelayService"),
            "endpoint": svc.get("serviceEndpoint", f"https://{_relay_host}"),
        })

    # ANPN 协议能力
    capabilities = {
        "protocols": ["anpn/1.0", "did:agentnexus", "did:web"],
    }

    return {
        "identity": {
            "did": _relay_did,
            "publicKey": pubkey_multibase,
            "oatr_issuer_id": _relay_host,
        },
        "services": services,
        "capabilities": capabilities,
    }


async def _verify_anpn_register(req: AnpnRegisterRequest) -> None:
    """验证 ANPN 注册请求的签名"""
    if not req.signature or req.timestamp is None:
        raise HTTPException(401, "Missing signature/timestamp in ANPN register request")

    # 时钟偏差检查
    skew = abs(time.time() - req.timestamp)
    if skew > ANNOUNCE_CLOCK_SKEW:
        raise HTTPException(401, f"ANPN timestamp too stale ({skew:.0f}s skew)")

    # 获取该 DID 的公钥（从 TOFU 存储）
    pk_key = f"{ANNOUNCE_PUBKEY_PREFIX}{req.did}"
    stored_pk = await _redis.get(pk_key)
    if not stored_pk:
        raise HTTPException(404, f"Unknown DID: {req.did} (must announce first)")

    # 构建签名 payload: did|protocol|endpoint|timestamp
    payload = f"{req.did}|{req.protocol}|{req.endpoint}|{req.timestamp}"
    try:
        verify_signed_payload(payload, req.signature, stored_pk)
    except Exception:
        raise HTTPException(401, "Invalid ANPN register signature")


@app.post("/relay/anpn-register", response_model=AnpnRegisterResponse)
async def anpn_register(req: AnpnRegisterRequest):
    """
    注册 Agent 的协议端点（ANPN）
    TTL=86400秒，同时维护索引 relay:anpn:idx:{did}
    Protocol 统一转小写存储（semi-structured 规范化）
    """
    _check_rate_limit(req.did)
    await _verify_anpn_register(req)

    now = time.time()
    expires_at = now + _ANPN_TTL

    # Protocol 规范化：统一转小写
    normalized_protocol = req.protocol.lower()

    # 存储协议端点（使用规范化后的 protocol）
    value = json.dumps({
        "did": req.did,
        "protocol": normalized_protocol,
        "endpoint": req.endpoint,
        "updated_at": now,
    })
    anpn_key = f"{_ANPN_PREFIX}{req.did}:{normalized_protocol}"
    await _redis.setex(anpn_key, _ANPN_TTL, value)

    # 维护索引（使用规范化后的 protocol）
    idx_key = f"{_ANPN_IDX_PREFIX}{req.did}"
    await _redis.sadd(idx_key, normalized_protocol)
    await _redis.expire(idx_key, _ANPN_TTL)

    return AnpnRegisterResponse(
        status="ok",
        did=req.did,
        protocol=normalized_protocol,
        expires_at=expires_at,
    )


async def _proxy_anpn_lookup(peer_relay_url: str, did: str, protocol: str) -> dict | None:
    """向 peer relay 代理查询 ANPN（1跳）"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{peer_relay_url}/relay/anpn-lookup/{did}/{protocol}",
                timeout=aiohttp.ClientTimeout(total=FEDERATION_PROXY_TIMEOUT),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return None


@app.get("/relay/anpn-lookup/{did}/{protocol}")
async def anpn_lookup(did: str, protocol: str):
    """
    查询 Agent 的协议端点（本地 + 1跳联邦代理）
    Protocol 统一转小写查询（semi-structured 规范化）
    """
    # Protocol 规范化：统一转小写
    normalized_protocol = protocol.lower()

    # 本地查询（使用规范化后的 protocol）
    anpn_key = f"{_ANPN_PREFIX}{did}:{normalized_protocol}"
    raw = await _redis.get(anpn_key)
    if raw:
        info = json.loads(raw)
        return AnpnLookupResponse(
            did=info["did"],
            protocol=info["protocol"],
            endpoint=info["endpoint"],
            updated_at=info["updated_at"],
        )

    # 联邦代理查询（1跳）
    # 先查该 DID 是否在 peer_directory 中
    peer_raw = await _redis.get(f"{_DIR_PREFIX}{did}")
    if peer_raw:
        peer_entry = json.loads(peer_raw)
        peer_relay_url = peer_entry.get("relay_url")
        if peer_relay_url:
            data = await _proxy_anpn_lookup(peer_relay_url, did, normalized_protocol)
            if data is not None:
                data["_via_relay"] = peer_relay_url
                return data

    raise HTTPException(status_code=404, detail=f"ANPN endpoint not found: {did}/{normalized_protocol}")


@app.get("/relay/anpn-discover/{did}")
async def anpn_discover(did: str):
    """
    发现 Agent 支持的所有协议（从索引批量查询）
    """
    idx_key = f"{_ANPN_IDX_PREFIX}{did}"
    protocols = await _redis.smembers(idx_key)

    if not protocols:
        raise HTTPException(status_code=404, detail=f"No ANPN protocols found for: {did}")

    # 批量查询详情
    result = []
    for proto in protocols:
        anpn_key = f"{_ANPN_PREFIX}{did}:{proto}"
        raw = await _redis.get(anpn_key)
        if raw:
            info = json.loads(raw)
            result.append({
                "protocol": info["protocol"],
                "endpoint": info["endpoint"],
                "updated_at": info["updated_at"],
            })

    return AnpnDiscoverResponse(
        did=did,
        protocols=result,
    )
