"""
Governance Attestation Integration

集成外部治理认证服务（MolTrust, APS），支持 validate-capabilities API。

v0.9.6 新增。
"""
from __future__ import annotations

import aiohttp
import base64
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class GovernanceAttestation:
    """
    治理认证结果

    注（ADR-014 P1）：
    - spend_limit 是外部治理服务返回的参考信息，不覆盖 ADR-004 定义的实际消费额度
    - 实际消费额度由 AgentNexus L 级决定：L1=$0, L2=$10, L3=$100, L4=$1000
    - grade_to_level 返回的 L 级仅用于风险评估，不改变 Gatekeeper 的权限决策
    """
    signal_type: str                    # "governance_attestation"
    issuer: str                         # "api.moltrust.ch" / "gateway.aeoess.com"
    subject: str                        # agent DID
    decision: str                       # "permit" | "conditional" | "deny"
    scopes: list[str] = field(default_factory=list)
    spend_limit: int = 0                # 参考：外部治理服务的建议额度（不用于实际控制）
    validity_window: dict = field(default_factory=dict)
    trust_score: int = 0                # 0-100
    passport_grade: int = 0             # 0-3, maps to L1-L4 (参考)
    expires_at: Optional[str] = None
    raw_response: dict = field(default_factory=dict)
    jws: str = ""

    @property
    def is_permitted(self) -> bool:
        """是否允许"""
        return self.decision in ("permit", "conditional")

    @property
    def grade_to_level(self) -> int:
        """
        将 passport_grade 映射到 AgentNexus L 级（参考）

        注：此映射仅用于风险评估和 attestation_bonus 计算，
        不改变 Gatekeeper 基于 ADR-004 的权限决策。
        """
        # MolTrust: 0=grade0, 1=grade1, 2=grade2, 3=grade3
        # AgentNexus: L1=grade0, L2=grade1, L3=grade2, L4=grade3
        return min(4, max(1, self.passport_grade + 1))

    def to_dict(self) -> dict:
        return {
            "signal_type": self.signal_type,
            "issuer": self.issuer,
            "subject": self.subject,
            "decision": self.decision,
            "scopes": self.scopes,
            "spend_limit": self.spend_limit,
            "validity_window": self.validity_window,
            "trust_score": self.trust_score,
            "passport_grade": self.passport_grade,
            "expires_at": self.expires_at,
            "jws": self.jws,
        }


@dataclass
class CapabilityRequest:
    """能力请求"""
    scope: str
    resource: Optional[str] = None
    max_amount_usd: Optional[int] = None

    def to_dict(self) -> dict:
        d = {"scope": self.scope}
        if self.resource:
            d["resource"] = self.resource
        if self.max_amount_usd is not None:
            d["max_amount_usd"] = self.max_amount_usd
        return d


# ---------------------------------------------------------------------------
# Governance Client 抽象基类
# ---------------------------------------------------------------------------

class GovernanceClient(ABC):
    """治理服务客户端抽象基类"""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @abstractmethod
    async def validate_capabilities(
        self,
        agent_did: str,
        requested: list[CapabilityRequest],
        context: Optional[dict] = None,
    ) -> GovernanceAttestation:
        """
        验证 Agent 能力

        Args:
            agent_did: Agent DID
            requested: 请求的能力列表
            context: 额外上下文（task_class, evaluation_timestamp 等）

        Returns:
            GovernanceAttestation
        """
        pass

    @abstractmethod
    def get_jwks_url(self) -> str:
        """获取 JWKS URL"""
        pass

    async def fetch_jwks(self) -> dict:
        """获取 JWKS"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.get_jwks_url(),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status != 200:
                    raise ValueError(f"Failed to fetch JWKS: {resp.status}")
                return await resp.json()


# ---------------------------------------------------------------------------
# MolTrust Client
# ---------------------------------------------------------------------------

class MolTrustClient(GovernanceClient):
    """
    MolTrust MoltGuard 客户端

    API 文档: https://api.moltrust.ch/docs
    端点: POST /guard/governance/validate-capabilities
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.moltrust.ch",
        timeout: float = 5.0,
    ):
        super().__init__(base_url, api_key, timeout)

    def get_jwks_url(self) -> str:
        # MolTrust JWKS 通过 did:web 获取
        return f"{self.base_url}/.well-known/jwks.json"

    async def validate_capabilities(
        self,
        agent_did: str,
        requested: list[CapabilityRequest],
        context: Optional[dict] = None,
    ) -> GovernanceAttestation:
        url = f"{self.base_url}/guard/governance/validate-capabilities"

        payload = {
            "agent_did": agent_did,
            "requested_capabilities": [r.to_dict() for r in requested],
            "context": context or {},
        }

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ValueError(f"MolTrust API error: {resp.status} - {text}")

                data = await resp.json()

        return self._parse_response(data)

    def _parse_response(self, data: dict) -> GovernanceAttestation:
        """解析 MolTrust 响应"""
        constraints = data.get("active_constraints", {})

        return GovernanceAttestation(
            signal_type=data.get("signal_type", "governance_attestation"),
            issuer=data.get("iss", "api.moltrust.ch"),
            subject=data.get("sub", ""),
            decision=data.get("decision", "deny"),
            scopes=constraints.get("scope", []),
            spend_limit=constraints.get("spend_limit", 0),
            validity_window=constraints.get("validity_window", {}),
            trust_score=data.get("trust_score", 0),
            passport_grade=constraints.get("passport_grade", 0),
            expires_at=data.get("expires_at"),
            raw_response=data,
            jws=data.get("jws", ""),
        )


# ---------------------------------------------------------------------------
# APS Client
# ---------------------------------------------------------------------------

class APSClient(GovernanceClient):
    """
    APS (Agent Passport System) 客户端

    端点: POST /api/v1/public/validate-capabilities
    """

    def __init__(
        self,
        base_url: str = "https://gateway.aeoess.com",
        timeout: float = 5.0,
    ):
        # APS 不需要 API Key
        super().__init__(base_url, None, timeout)

    def get_jwks_url(self) -> str:
        return f"{self.base_url}/.well-known/jwks.json"

    async def validate_capabilities(
        self,
        agent_did: str,
        requested: list[CapabilityRequest],
        context: Optional[dict] = None,
    ) -> GovernanceAttestation:
        url = f"{self.base_url}/api/v1/public/validate-capabilities"

        payload = {
            "agent_did": agent_did,
            "requested_capabilities": [r.to_dict() for r in requested],
            "context": context or {},
        }

        headers = {
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ValueError(f"APS API error: {resp.status} - {text}")

                data = await resp.json()

        return self._parse_response(data)

    def _parse_response(self, data: dict) -> GovernanceAttestation:
        """解析 APS 响应"""
        constraints = data.get("active_constraints", {})

        return GovernanceAttestation(
            signal_type=data.get("signal_type", "governance_attestation"),
            issuer=data.get("iss", "gateway.aeoess.com"),
            subject=data.get("sub", ""),
            decision=data.get("decision", "deny"),
            scopes=constraints.get("scope", []),
            spend_limit=constraints.get("spend_limit", 0),
            validity_window=constraints.get("validity_window", {}),
            trust_score=data.get("trust_score", 0),
            passport_grade=data.get("passport_grade", 0),
            expires_at=data.get("expires_at"),
            raw_response=data,
            jws=data.get("sig", ""),
        )


# ---------------------------------------------------------------------------
# JWS 验证
# ---------------------------------------------------------------------------

def verify_jws(jws: str, public_key_hex: str) -> bool:
    """
    验证 JWS (EdDSA) 签名

    Args:
        jws: JWS compact 格式 (header.payload.signature)
        public_key_hex: Ed25519 公钥 (hex)

    Returns:
        True if valid
    """
    try:
        parts = jws.split(".")
        if len(parts) != 3:
            return False

        header_b64, payload_b64, signature_b64 = parts

        # 解码签名
        signature = base64.urlsafe_b64decode(signature_b64 + "==")

        # 签名输入
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

        # 验证
        verify_key = VerifyKey(bytes.fromhex(public_key_hex))
        verify_key.verify(signing_input, signature)

        return True
    except (BadSignatureError, ValueError, Exception):
        return False


def extract_jwk_public_key(jwks: dict, kid: str) -> Optional[str]:
    """
    从 JWKS 提取公钥

    Args:
        jwks: JWKS JSON
        kid: Key ID

    Returns:
        Ed25519 公钥 (hex) 或 None
    """
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            # Ed25519 公钥在 x 字段 (base64url)
            x = key.get("x", "")
            if x:
                return base64.urlsafe_b64decode(x + "==").hex()
    return None


def get_jws_kid(jws: str) -> Optional[str]:
    """从 JWS header 提取 kid"""
    try:
        parts = jws.split(".")
        if len(parts) != 3:
            return None
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "=="))
        return header.get("kid")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Governance Registry
# ---------------------------------------------------------------------------

class GovernanceRegistry:
    """
    治理服务注册表

    管理多个治理服务客户端，聚合验证结果。
    """

    def __init__(self):
        self.clients: dict[str, GovernanceClient] = {}
        self.jwks_cache: dict[str, tuple[dict, float]] = {}  # url -> (jwks, timestamp)
        self.jwks_ttl: int = 3600  # 1 hour

    def register(self, name: str, client: GovernanceClient) -> None:
        """注册治理服务客户端"""
        self.clients[name] = client

    def unregister(self, name: str) -> bool:
        """注销治理服务客户端"""
        if name in self.clients:
            del self.clients[name]
            return True
        return False

    async def validate_capabilities(
        self,
        agent_did: str,
        requested: list[CapabilityRequest],
        context: Optional[dict] = None,
        clients: Optional[list[str]] = None,
    ) -> dict[str, GovernanceAttestation]:
        """
        调用所有注册的治理服务验证能力

        Args:
            agent_did: Agent DID
            requested: 请求的能力列表
            context: 额外上下文
            clients: 指定客户端名称列表，None 表示全部

        Returns:
            {client_name: GovernanceAttestation}
        """
        results = {}

        to_call = clients or list(self.clients.keys())

        for name in to_call:
            client = self.clients.get(name)
            if client is None:
                continue

            try:
                attestation = await client.validate_capabilities(
                    agent_did, requested, context
                )
                results[name] = attestation
            except Exception as e:
                # 失败时创建 deny attestation
                results[name] = GovernanceAttestation(
                    signal_type="governance_attestation",
                    issuer=name,
                    subject=agent_did,
                    decision="deny",
                    raw_response={"error": str(e)},
                )

        return results

    async def verify_attestation(
        self,
        attestation: GovernanceAttestation,
        client_name: Optional[str] = None,
        require_jws: bool = False,
    ) -> bool:
        """
        验证 attestation 的 JWS 签名（ADR-014 S1）

        步骤：
        1. 检查 expires_at 过期（强制拒绝过期 attestation）
        2. 获取 JWKS（带缓存）
        3. 验证 JWS 签名

        Args:
            attestation: 治理认证
            client_name: 客户端名称（用于获取 JWKS）
            require_jws: 是否要求必须有 JWS 签名（默认 False）

        Returns:
            True if valid
        """
        # 1. 检查过期（重放攻击防护）
        if attestation.expires_at:
            try:
                expires_dt = datetime.fromisoformat(
                    attestation.expires_at.replace("Z", "+00:00")
                )
                if datetime.now(timezone.utc) > expires_dt:
                    return False  # 过期 attestation 拒绝
            except Exception:
                pass  # 解析失败时继续验证签名

        if not attestation.jws:
            # 无签名
            if require_jws:
                return False  # 要求签名但无签名，拒绝
            # 信任 issuer（但需要检查过期）
            return True

        # 查找客户端
        client = None
        if client_name:
            client = self.clients.get(client_name)
        else:
            # 通过 issuer 查找
            for name, c in self.clients.items():
                if c.base_url in attestation.issuer or attestation.issuer in c.base_url:
                    client = c
                    break

        if client is None:
            logger.warning(f"JWS verification failed: client not found for issuer={attestation.issuer}")
            return False

        # 获取 JWKS
        jwks_url = client.get_jwks_url()

        # 检查缓存
        cached = self.jwks_cache.get(jwks_url)
        if cached and time.time() - cached[1] < self.jwks_ttl:
            jwks = cached[0]
        else:
            try:
                jwks = await client.fetch_jwks()
                self.jwks_cache[jwks_url] = (jwks, time.time())
            except Exception as e:
                logger.warning(f"JWS verification failed: JWKS fetch error for {jwks_url}: {e}")
                return False

        # 提取 kid
        kid = get_jws_kid(attestation.jws)
        if not kid:
            logger.warning(f"JWS verification failed: no kid in JWS header")
            return False

        # 提取公钥
        public_key_hex = extract_jwk_public_key(jwks, kid)
        if not public_key_hex:
            logger.warning(f"JWS verification failed: public key not found for kid={kid}")
            return False

        # 验证签名
        valid = verify_jws(attestation.jws, public_key_hex)
        if not valid:
            logger.warning(f"JWS verification failed: invalid signature for subject={attestation.subject}")
        return valid

    def get_highest_trust(self, results: dict[str, GovernanceAttestation]) -> GovernanceAttestation:
        """
        从多个结果中获取最高信任级别的 attestation

        优先级: permit > conditional > deny
        同 decision 时按 trust_score 排序
        """
        if not results:
            return GovernanceAttestation(
                signal_type="governance_attestation",
                issuer="none",
                subject="",
                decision="deny",
            )

        # 排序：decision 权重 + trust_score
        decision_weight = {"permit": 2, "conditional": 1, "deny": 0}

        def sort_key(att: GovernanceAttestation) -> tuple:
            return (
                decision_weight.get(att.decision, 0),
                att.trust_score,
            )

        return max(results.values(), key=sort_key)


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def create_default_registry(moltrust_api_key: Optional[str] = None) -> GovernanceRegistry:
    """
    创建默认治理服务注册表

    Args:
        moltrust_api_key: MolTrust API Key（可选，无则不注册 MolTrust）

    Returns:
        GovernanceRegistry
    """
    registry = GovernanceRegistry()

    # 注册 APS（无需 API Key）
    registry.register("aps", APSClient())

    # 注册 MolTrust（需要 API Key）
    if moltrust_api_key:
        registry.register("moltrust", MolTrustClient(api_key=moltrust_api_key))

    return registry
