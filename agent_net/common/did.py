"""
DID 生成与解析 —— node 和 relay 共用

包含:
- DIDGenerator: 生成新的 DID (did:agent, did:agentnexus)
- DIDResolver: 解析 DID 到 DID Document (支持 did:agent, did:agentnexus, did:key, did:web)

符合 WG DID Resolution v1.0 规范 (corpollc/qntm)
"""
import hashlib
import json
import time
import uuid
import aiosqlite
from dataclasses import dataclass, field, asdict
from typing import Optional

import httpx
from nacl.signing import SigningKey, VerifyKey

from agent_net.common import crypto


# ── DID 错误类型 ──────────────────────────────────────────

class DIDError(Exception):
    """DID 相关错误的基类"""
    pass


class DIDNotFoundError(DIDError):
    """DID 无法解析（网络错误、404、DNS 失败）"""
    pass


class DIDKeyTypeUnsupportedError(DIDError):
    """解析的密钥不是 Ed25519"""
    pass


class DIDKeyExtractionError(DIDError):
    """DID Document 存在但密钥提取失败"""
    pass


class DIDMethodUnsupportedError(DIDError):
    """DID 方法不被此解析器识别"""
    pass


# ── DID 解析结果 ──────────────────────────────────────────

@dataclass
class DIDResolutionResult:
    """WG DID Resolution v1.0 解析结果"""
    did: str
    method: str
    public_key: bytes  # 32-byte Ed25519 public key
    did_document: Optional[dict] = None
    metadata: dict = field(default_factory=dict)

    def to_wg_format(self) -> dict:
        """
        转换为 WG 规范格式:
        { public_key: bytes(32), method: string, metadata: map }
        """
        return {
            "public_key": self.public_key,
            "method": self.method,
            "metadata": self.metadata,
        }


# ── AgentProfile ─────────────────────────────────────────

@dataclass
class AgentProfile:
    """Agent Profile - 保持与 identity/__init__.py 兼容"""
    id: str
    name: str
    type: str = "GeneralAgent"
    capabilities: list = field(default_factory=list)
    location: str = ""
    endpoints: dict = field(default_factory=dict)
    context: str = "https://agent-net.io/v1"
    created_at: float = field(default_factory=time.time)

    def to_json_ld(self) -> dict:
        return {
            "@context": self.context,
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "capabilities": self.capabilities,
            "location": self.location,
            "endpoints": self.endpoints,
        }

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentProfile":
        data.pop("context", None)
        return cls(**data)


# ── DID Generator ────────────────────────────────────────

@dataclass
class AgentDID:
    did: str
    private_key: SigningKey
    verify_key: VerifyKey


class DIDGenerator:
    """DID 生成器 —— 生成 did:agent 和 did:agentnexus 格式的 DID"""

    @staticmethod
    def create_new(name: str = "") -> AgentDID:
        """生成新的 did:agent:<hex> 格式 DID（向后兼容）"""
        sk = SigningKey.generate()
        unique = f"{name}-{uuid.uuid4()}-{time.time()}"
        hash_val = hashlib.sha256(unique.encode()).hexdigest()[:16]
        did = f"did:agent:{hash_val}"
        return AgentDID(did=did, private_key=sk, verify_key=sk.verify_key)

    @staticmethod
    def create_agentnexus(name: str = "") -> tuple[AgentDID, str]:
        """
        生成新的 did:agentnexus:<multikey> 格式 DID

        返回: (AgentDID 对象, multikey 字符串)

        multikey 格式: z + base58btc(multicodec_prefix || ed25519_pubkey)
        """
        sk = SigningKey.generate()
        pk_bytes = sk.verify_key.encode()
        multikey = crypto.encode_multikey_ed25519(pk_bytes)
        did = f"did:agentnexus:{multikey}"
        return AgentDID(did=did, private_key=sk, verify_key=sk.verify_key), multikey


# ── DID Resolver ──────────────────────────────────────────

DB_PATH = None  # 由调用者设置


def _set_db_path(path):
    global DB_PATH
    DB_PATH = path


class DIDResolver:
    """
    通用 DID 解析器

    支持的方法:
    - did:agentnexus:<multikey>  (本地代理 + 本地存储)
    - did:agent:<hex>           (本地存储，向后兼容)
    - did:key:<multikey>        (多基算法)
    - did:web:<domain>          (远程 HTTPS)

    符合 WG DID Resolution v1.0 规范 (corpollc/qntm)
    """

    def __init__(self, db_path: str = None):
        """
        初始化解析器

        Args:
            db_path: SQLite 数据库路径（用于本地代理查询）
        """
        self.db_path = db_path

    async def _get_local_agent_key(self, did: str) -> Optional[bytes]:
        """从本地数据库查询代理的公钥"""
        if not self.db_path:
            return None

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT profile FROM agents WHERE did=?", (did,)
            ) as cur:
                row = await cur.fetchone()

        if not row:
            return None

        try:
            profile = json.loads(row[0])
            # 期望 profile 中包含 public_key_hex 字段
            pubkey_hex = profile.get("public_key_hex")
            if pubkey_hex:
                return bytes.fromhex(pubkey_hex)
        except (json.JSONDecodeError, ValueError):
            pass

        return None

    async def resolve(self, did: str) -> DIDResolutionResult:
        """
        解析 DID URI 到 Ed25519 公钥和 DID Document

        返回 DIDResolutionResult，包含:
        - did: 原始 DID 字符串
        - method: DID 方法名
        - public_key: 32字节 Ed25519 公钥
        - did_document: 符合 W3C DID Core 的 DID Document
        - metadata: 方法特定的元数据

        抛出符合 WG 规范的错误:
        - DIDNotFoundError: DID 无法解析
        - DIDKeyTypeUnsupportedError: 密钥类型不支持
        - DIDKeyExtractionError: 密钥提取失败
        - DIDMethodUnsupportedError: DID 方法不支持
        """
        if not did.startswith("did:"):
            raise DIDMethodUnsupportedError(f"Invalid DID: must start with 'did:', got '{did}'")

        # 解析 DID 方法
        parts = did.split(":", 3)
        if len(parts) < 3:
            raise DIDMethodUnsupportedError(f"Invalid DID format: '{did}'")

        method = parts[1]

        if method == "agentnexus":
            return await self._resolve_agentnexus(did, parts[2])
        elif method == "agent":
            return await self._resolve_agent(did, parts[2])
        elif method == "key":
            return await self._resolve_key(did, parts[2])
        elif method == "web":
            return await self._resolve_web(did, parts[2])
        else:
            raise DIDMethodUnsupportedError(f"Unsupported DID method: '{method}'")

    async def _resolve_agentnexus(self, did: str, key_part: str) -> DIDResolutionResult:
        """解析 did:agentnexus:<multikey>"""
        try:
            pubkey_bytes = crypto.decode_multikey_ed25519(key_part)
        except ValueError as e:
            raise DIDKeyExtractionError(f"Failed to decode did:agentnexus multikey: {e}")

        # 构建 DID Document
        did_document = self._build_did_document(did, pubkey_bytes)

        return DIDResolutionResult(
            did=did,
            method="agentnexus",
            public_key=pubkey_bytes,
            did_document=did_document,
            metadata={"version": "1.0", "created": time.strftime("%Y-%m-%dT%H:%M:%SZ")},
        )

    async def _resolve_agent(self, did: str, key_part: str) -> DIDResolutionResult:
        """
        解析 did:agent:<hex> —— 向后兼容现有代理
        从本地数据库查找公钥
        """
        # 尝试从本地数据库获取
        pubkey_bytes = await self._get_local_agent_key(did)

        if not pubkey_bytes:
            # 回退：从 hex 字符串解析（如果 key_part 是有效的 32 字节 hex）
            if len(key_part) == 32:
                try:
                    pubkey_bytes = bytes.fromhex(key_part)
                except ValueError:
                    pass

        if not pubkey_bytes:
            # 尝试通过 generate_did 逻辑重建（基于哈希）
            # 这不是一个可靠的回退，因为哈希不是可逆的
            raise DIDNotFoundError(
                f"Cannot resolve did:agent without local database entry: {did}"
            )

        did_document = self._build_did_document(did, pubkey_bytes)

        return DIDResolutionResult(
            did=did,
            method="agent",
            public_key=pubkey_bytes,
            did_document=did_document,
            metadata={"version": "legacy", "backward_compat": True},
        )

    async def _resolve_key(self, did: str, key_part: str) -> DIDResolutionResult:
        """解析 did:key:<multikey>"""
        try:
            pubkey_bytes = crypto.decode_multikey_ed25519(key_part)
        except ValueError as e:
            raise DIDKeyTypeUnsupportedError(f"Failed to decode did:key: {e}")

        did_document = self._build_did_document(did, pubkey_bytes)

        return DIDResolutionResult(
            did=did,
            method="key",
            public_key=pubkey_bytes,
            did_document=did_document,
            metadata={"version": "1.0"},
        )

    async def _resolve_web(self, did: str, domain: str) -> DIDResolutionResult:
        """
        解析 did:web:<domain> — 从 HTTPS 端点获取 DID Document
        """
        # URL 解码（处理转义的冒号等）
        import urllib.parse
        domain = urllib.parse.unquote(domain)

        # 确定 DID Document URL
        if "/" in domain:
            # did:web:example.com/path -> https://example.com/path/did.json
            doc_url = f"https://{domain}/did.json"
        else:
            # did:web:example.com -> https://example.com/.well-known/did.json
            doc_url = f"https://{domain}/.well-known/did.json"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    doc_url,
                    headers={"User-Agent": "AgentNexus/1.0 DID Resolver"}
                )
                response.raise_for_status()
                did_doc = response.json()
        except httpx.HTTPError as e:
            raise DIDNotFoundError(f"Failed to fetch did:web document from {doc_url}: {e}")
        except json.JSONDecodeError as e:
            raise DIDKeyExtractionError(f"Invalid JSON in did:web document from {doc_url}: {e}")

        # 从 DID Document 提取 Ed25519 公钥
        pubkey_bytes = self._extract_ed25519_key_from_doc(did_doc)

        if not pubkey_bytes:
            raise DIDKeyExtractionError(f"No Ed25519 key found in did:web document from {doc_url}")

        return DIDResolutionResult(
            did=did,
            method="web",
            public_key=pubkey_bytes,
            did_document=did_doc,
            metadata={"resolved_url": doc_url, "version": "1.0"},
        )

    def _extract_ed25519_key_from_doc(self, doc: dict) -> Optional[bytes]:
        """
        从 DID Document 提取 Ed25519 公钥

        按优先级检查:
        1. publicKeyMultibase (Ed25519VerificationKey2020) - 去掉 'z' 前缀和 multicodec 前缀
        2. publicKeyBase58 (Ed25519VerificationKey2018) - base58 解码
        3. publicKeyJwk (OKP, crv: Ed25519) - base64url 解码 x 字段

        参考: WG DID Resolution v1.0 §3.1.1
        """
        verification_methods = doc.get("verificationMethod", [])

        for vm in verification_methods:
            vm_type = vm.get("type", "")

            # 优先级 1: publicKeyMultibase + Ed25519VerificationKey2020
            if vm_type == "Ed25519VerificationKey2020" and "publicKeyMultibase" in vm:
                try:
                    multikey = vm["publicKeyMultibase"]
                    # multikey 格式: z + base58(multicodec || pubkey)
                    # Ed25519 multicodec = 0xed01
                    return crypto.decode_multikey_ed25519(multikey)
                except (ValueError, KeyError):
                    continue

            # 优先级 2: publicKeyBase58 + Ed25519VerificationKey2018
            if vm_type == "Ed25519VerificationKey2018" and "publicKeyBase58" in vm:
                try:
                    b58_key = vm["publicKeyBase58"]
                    return crypto._base58_decode(b58_key)
                except (ValueError, KeyError):
                    continue

            # 优先级 3: publicKeyJwk + OKP + Ed25519
            if vm_type == "Ed25519VerificationKey2020" and "publicKeyJwk" in vm:
                try:
                    jwk = vm["publicKeyJwk"]
                    if jwk.get("kty") == "OKP" and jwk.get("crv") == "Ed25519":
                        import base64
                        x_raw = jwk["x"]
                        # base64url 解码
                        x_raw = x_raw + "=" * (4 - len(x_raw) % 4)
                        x_raw = x_raw.replace("-", "+").replace("_", "/")
                        return base64.b64decode(x_raw)
                except (ValueError, KeyError, Exception):
                    continue

        return None

    def _build_did_document(self, did: str, pubkey_bytes: bytes,
                            services: list[dict] | None = None) -> dict:
        """
        构建符合 W3C DID Core 和 did:agentnexus 规范的 DID Document

        包含:
        - Ed25519VerificationKey2018 (authentication, assertion)
        - X25519KeyAgreementKey2019 (keyAgreement，用于 ECDH)
        - service 数组（可选，由调用者传入）
        """
        # Ed25519 multikey
        ed_multikey = crypto.encode_multikey_ed25519(pubkey_bytes)

        # X25519 multikey (通过 Ed25519→X25519 推导)
        try:
            x25519_bytes = crypto.ed25519_pub_to_x25519(pubkey_bytes)
            x_multikey = crypto.encode_multikey_x25519(x25519_bytes)
        except Exception:
            # 如果推导失败，跳过 keyAgreement
            x_multikey = None

        doc = {
            "@context": [
                "https://www.w3.org/ns/did/v1",
                "https://w3id.org/security/suites/ed25519-2020/v1",
            ],
            "id": did,
            "verificationMethod": [{
                "id": f"{did}#agent-1",
                "type": "Ed25519VerificationKey2018",
                "controller": did,
                "publicKeyMultibase": ed_multikey,
            }],
            "authentication": [f"{did}#agent-1"],
            "assertionMethod": [f"{did}#agent-1"],
        }

        if x_multikey:
            doc["keyAgreement"] = [{
                "id": f"{did}#key-agreement-1",
                "type": "X25519KeyAgreementKey2019",
                "controller": did,
                "publicKeyMultibase": x_multikey,
            }]

        if services:
            doc["service"] = services

        return doc

    # ── WG 规范兼容方法 ─────────────────────────────────

    async def resolve_did(self, did_uri: str) -> dict:
        """
        WG DID Resolution v1.0 兼容接口

        resolve_did(did_uri: string) → { public_key: bytes(32), method: string, metadata: map }

        此方法直接符合 WG 规范，适合与 qntm、AgentID、APS 等系统互操作。
        """
        result = await self.resolve(did_uri)
        return result.to_wg_format()

    def ed25519_to_x25519(self, public_key: bytes) -> bytes:
        """
        Ed25519 → X25519 公钥推导

        用于 keyAgreement (ECDH)
        """
        return crypto.ed25519_pub_to_x25519(public_key)

    def derive_sender_id(self, public_key: bytes) -> str:
        """
        从 Ed25519 公钥推导 sender_id

        算法: sender_id = SHA-256(public_key)[0:16]
        返回: lowercase hex 字符串
        """
        return crypto.derive_sender_id(public_key)


# ── Service 辅助函数 ──────────────────────────────────────

def build_services_from_profile(profile: dict, relay_url: str = "") -> list[dict]:
    """
    从 agent profile 或 NexusProfile content 提取 service 列表

    Args:
        profile: agent profile dict (含 endpoints 或 endpoint 字段)
        relay_url: relay 服务 URL（如已知）

    Returns:
        符合 W3C DID Core service 规范的列表
    """
    services = []

    if relay_url:
        services.append({
            "id": "#relay",
            "type": "AgentRelay",
            "serviceEndpoint": relay_url,
        })

    # 支持多种 endpoint 字段格式
    endpoints = profile.get("endpoints", {})
    if isinstance(endpoints, dict):
        p2p = endpoints.get("p2p") or endpoints.get("direct")
        if p2p:
            services.append({
                "id": "#agent",
                "type": "AgentEndpoint",
                "serviceEndpoint": p2p,
            })
        relay_ep = endpoints.get("relay")
        if relay_ep and not relay_url:
            services.append({
                "id": "#relay",
                "type": "AgentRelay",
                "serviceEndpoint": relay_ep,
            })
    elif isinstance(endpoints, str) and endpoints:
        services.append({
            "id": "#agent",
            "type": "AgentEndpoint",
            "serviceEndpoint": endpoints,
        })

    # 兼容旧 endpoint 字段
    endpoint = profile.get("endpoint")
    if endpoint and not any(s["id"] == "#agent" for s in services):
        services.append({
            "id": "#agent",
            "type": "AgentEndpoint",
            "serviceEndpoint": endpoint,
        })

    return services


# ── 便捷函数 ──────────────────────────────────────────────

def create_agentnexus_did(name: str = "") -> tuple[str, str, str]:
    """
    便捷函数：生成 did:agentnexus DID

    返回: (did_string, private_key_hex, public_key_hex)
    """
    sk = SigningKey.generate()
    pk_bytes = sk.verify_key.encode()
    multikey = crypto.encode_multikey_ed25519(pk_bytes)
    did = f"did:agentnexus:{multikey}"
    return did, sk.encode().hex(), pk_bytes.hex()


def resolve_did_sync(did: str, db_path: str = None) -> DIDResolutionResult:
    """
    同步版本的 DID 解析（用于不支持 async 的场景）

    内部使用 asyncio.run()
    """
    import asyncio

    resolver = DIDResolver(db_path=db_path)
    return asyncio.run(resolver.resolve(did))
