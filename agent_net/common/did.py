"""
DID 生成与解析 —— node 和 relay 共用

包含:
- DIDGenerator: 生成新的 DID (did:agent, did:agentnexus)
- DIDResolver: 解析 DID 到 DID Document（注册表路由模式）

符合 WG DID Resolution v1.0 规范 (corpollc/qntm)
"""
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING, Optional

from nacl.signing import SigningKey, VerifyKey

from agent_net.common import crypto

if TYPE_CHECKING:
    from agent_net.common.did_methods.base import DIDMethodHandler


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
    通用 DID 解析器（注册表路由模式）

    通过注册 DIDMethodHandler 来支持不同的 DID 方法。
    默认不注册任何方法，需要调用 register_*_handlers() 来注册。

    符合 WG DID Resolution v1.0 规范 (corpollc/qntm)
    """

    _handlers: dict[str, "DIDMethodHandler"] = {}  # 类级别共享

    def __init__(self):
        """初始化解析器"""
        pass

    @classmethod
    def register(cls, handler: "DIDMethodHandler") -> None:
        """
        注册一个 DID 方法处理器。

        Args:
            handler: DIDMethodHandler 子类实例
        """
        cls._handlers[handler.method] = handler

    @classmethod
    def reset_handlers(cls) -> None:
        """
        清空所有已注册的 handler。

        仅用于测试：防止测试间状态污染。
        """
        cls._handlers.clear()

    @classmethod
    def get_registered_methods(cls) -> list[str]:
        """获取所有已注册的方法名"""
        return list(cls._handlers.keys())

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
        parts = did.split(":", 2)
        if len(parts) < 3:
            raise DIDMethodUnsupportedError(f"Invalid DID format: '{did}'")

        method = parts[1]
        method_specific_id = parts[2]

        # 查找已注册的 handler
        handler = self._handlers.get(method)
        if not handler:
            raise DIDMethodUnsupportedError(f"Unsupported DID method: '{method}'")

        return await handler.resolve(did, method_specific_id)

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

    注意：db_path 参数已废弃，现在通过注册的 handler 来处理。
    如果需要解析 did:agent，需要先调用 register_daemon_handlers(db_path)。
    """
    import asyncio

    resolver = DIDResolver()
    return asyncio.run(resolver.resolve(did))
