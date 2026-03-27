"""
AgentNexus RuntimeVerifier

实现 RuntimeVerifier 接口，供 8-step agent identity pipeline 使用。
兼容 Giskard CA 多 CA 认证架构。

接口定义（TypeScript 参考）：

  interface RuntimeVerifier {
    verify(agentDID: string, agentPublicKey: string): Promise<RuntimeVerification>
  }

  interface RuntimeVerification {
    verified: boolean
    trust_level: number         // 1-4
    trust_score: number         // 0.0 - 1.0
    permissions: string[]
    spending_limit: number
    did_resolution_status: "live" | "cached" | "failed"
    entity_verified: boolean
    execution_timestamp: string // ISO 8601 UTC
    pinned_public_key: string
    scope: string | null
  }

Trust Level 定义：
  L1: DID 可解析，无有效 cert
  L2: DID 可解析 + 至少 1 个有效 cert（任意 issuer）
  L3: DID 可解析 + 来自 trusted CA 的有效 cert（例如 Giskard CA）
  L4: DID 可解析 + trusted CA 的 entity_verified cert

多 CA 支持：
  trusted_cas = {
      "did:agent:giskard_ca": "<giskard_pubkey_hex>",
      "did:agentnexus:zSomeOtherCA": "<other_pubkey_hex>",
      ...
  }
  任意数量 CA，各自独立验证，最高级别 cert 决定 trust_level。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from nacl.exceptions import BadSignatureError

from agent_net.common.did import DIDResolver
from agent_net.common.profile import verify_certification


# ---------------------------------------------------------------------------
# 信任策略表（可在运行时替换）
# ---------------------------------------------------------------------------

#: 各信任级别允许的操作
TRUST_PERMISSIONS: dict[int, list[str]] = {
    1: ["discover", "read"],
    2: ["discover", "read", "message"],
    3: ["discover", "read", "message", "transact"],
    4: ["discover", "read", "message", "transact", "delegate"],
}

#: 各信任级别每日 USD 消费上限
TRUST_SPENDING_LIMITS: dict[int, int] = {
    1: 0,
    2: 10,
    3: 100,
    4: 1000,
}

#: 各级别基础信任分（加成前）
_BASE_SCORES: dict[int, float] = {
    1: 0.15,
    2: 0.40,
    3: 0.70,
    4: 0.95,
}

#: 表示 agent 在线的 resolution source 标识
_LIVE_SOURCES = {"local_db", "local_agent", "relay", "peer_directory"}


# ---------------------------------------------------------------------------
# 结果数据类
# ---------------------------------------------------------------------------

@dataclass
class RuntimeVerification:
    """
    RuntimeVerifier.verify() 的返回值。
    字段与 TypeScript 接口一一对应。
    """
    verified: bool                  # DID 解析成功 + 公钥匹配
    trust_level: int                # 1-4（L1 已注册 ~ L4 实体认证）
    trust_score: float              # 0.0 – 1.0
    permissions: list[str]          # 该信任级别允许的操作列表
    spending_limit: int             # 每日 USD 上限
    did_resolution_status: str      # "live" | "cached" | "failed"
    entity_verified: bool           # 法律实体绑定是否确认
    execution_timestamp: str        # ISO 8601 UTC
    pinned_public_key: str          # 解析时固定的公钥（hex）
    scope: Optional[str]            # 委托范围（暂未实现，返回 None）

    def to_dict(self) -> dict:
        return {
            "verified": self.verified,
            "trust_level": self.trust_level,
            "trust_score": round(self.trust_score, 4),
            "permissions": list(self.permissions),
            "spending_limit": self.spending_limit,
            "did_resolution_status": self.did_resolution_status,
            "entity_verified": self.entity_verified,
            "execution_timestamp": self.execution_timestamp,
            "pinned_public_key": self.pinned_public_key,
            "scope": self.scope,
        }


# ---------------------------------------------------------------------------
# CertFetcher 类型别名
# ---------------------------------------------------------------------------

#: async (did: str) -> list[cert_dict]
CertFetcher = Callable[[str], Awaitable[list[dict]]]


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------

class AgentNexusRuntimeVerifier:
    """
    AgentNexus 实现的 RuntimeVerifier。

    设计原则：
    - DIDResolver 负责身份解析（协议无关）
    - trusted_cas 负责 CA 信任锚（多 CA 并列，Giskard 是其中一个）
    - cert_fetcher 负责取回 certifications（注入，与存储层解耦）

    示例::

        resolver = DIDResolver()
        verifier = AgentNexusRuntimeVerifier(
            resolver=resolver,
            trusted_cas={"did:agent:giskard_ca": "<giskard_pubkey_hex>"},
            cert_fetcher=storage_cert_fetcher,
        )
        result = await verifier.verify(did, pubkey_hex)
        print(result.to_dict())
    """

    def __init__(
        self,
        resolver: DIDResolver,
        trusted_cas: dict[str, str] | None = None,
        cert_fetcher: CertFetcher | None = None,
    ) -> None:
        """
        Args:
            resolver:     DIDResolver 实例，支持 did:agentnexus / did:agent / did:key / did:web。
            trusted_cas:  可信 CA 注册表，{ca_did: ed25519_pubkey_hex}。
                          Giskard 集成示例：{"did:agent:giskard_ca": "<hex>"}
                          支持任意数量 CA，各自独立验证。
            cert_fetcher: async (did) -> list[cert_dict]。
                          不提供时 trust_level 固定为 L1（无 cert 检查）。
        """
        self.resolver = resolver
        # 统一小写，方便比较
        self.trusted_cas: dict[str, str] = {
            k: v.lower() for k, v in (trusted_cas or {}).items()
        }
        self.cert_fetcher = cert_fetcher

    # -----------------------------------------------------------------------
    # 公共接口
    # -----------------------------------------------------------------------

    async def verify(
        self,
        agent_did: str,
        agent_public_key: str,
    ) -> RuntimeVerification:
        """
        验证 agent 身份并计算信任级别。

        Args:
            agent_did:        Agent DID 字符串
            agent_public_key: 声明的 Ed25519 公钥（hex 或 multibase z...）

        Returns:
            RuntimeVerification 实例
        """
        ts = datetime.now(timezone.utc).isoformat()

        # ── 1. 解析 DID ──────────────────────────────────────────────────
        resolution_result = None
        resolution_status = "failed"
        try:
            resolution_result = await self.resolver.resolve(agent_did)
            if resolution_result and resolution_result.public_key:
                src = resolution_result.metadata.get("source", "")
                resolution_status = "live" if src in _LIVE_SOURCES else "cached"
        except Exception:
            pass

        if not resolution_result or not resolution_result.public_key:
            return self._failed_result(ts, agent_public_key)

        resolved_hex = resolution_result.public_key.hex()

        # ── 2. 比对声明公钥 ───────────────────────────────────────────────
        claimed_hex = self._normalize_pubkey(agent_public_key)
        key_verified = (resolved_hex == claimed_hex)

        # ── 3. 取回 certifications ────────────────────────────────────────
        certs: list[dict] = []
        if self.cert_fetcher is not None:
            try:
                certs = await self.cert_fetcher(agent_did) or []
            except Exception:
                certs = []

        # ── 4. 计算信任级别与各项指标 ─────────────────────────────────────
        trust_level = self._compute_trust_level(agent_did, certs)
        entity_verified = self._has_entity_verified(agent_did, certs)
        trust_score = self._compute_trust_score(trust_level, resolution_status)

        return RuntimeVerification(
            verified=key_verified,
            trust_level=trust_level,
            trust_score=trust_score,
            permissions=list(TRUST_PERMISSIONS.get(trust_level, [])),
            spending_limit=TRUST_SPENDING_LIMITS.get(trust_level, 0),
            did_resolution_status=resolution_status,
            entity_verified=entity_verified,
            execution_timestamp=ts,
            pinned_public_key=resolved_hex,
            scope=None,
        )

    # -----------------------------------------------------------------------
    # 内部辅助
    # -----------------------------------------------------------------------

    def _failed_result(self, ts: str, pubkey: str) -> RuntimeVerification:
        """DID 解析彻底失败时的零信任结果。"""
        return RuntimeVerification(
            verified=False,
            trust_level=1,
            trust_score=0.0,
            permissions=[],
            spending_limit=0,
            did_resolution_status="failed",
            entity_verified=False,
            execution_timestamp=ts,
            pinned_public_key=pubkey,
            scope=None,
        )

    def _normalize_pubkey(self, pubkey: str) -> str:
        """将 multibase（z...）或原始 hex 统一转为小写 hex。"""
        if pubkey.startswith("z"):
            try:
                from agent_net.common.crypto import decode_multikey_ed25519
                return decode_multikey_ed25519(pubkey).hex()
            except Exception:
                pass
        return pubkey.lower()

    def _is_trusted_ca(self, ca_did: str, ca_pubkey_hex: str) -> bool:
        """
        检查 (ca_did, ca_pubkey_hex) 是否在 trusted_cas 注册表中。
        双重验证：DID 匹配 + 公钥匹配，防止 DID 碰撞攻击。
        """
        expected = self.trusted_cas.get(ca_did)
        if expected is None:
            return False
        return ca_pubkey_hex.lower() == expected

    def _compute_trust_level(self, did: str, certs: list[dict]) -> int:
        """
        遍历 certifications，按以下规则计算信任级别：
          L1: 无有效 cert
          L2: ≥1 个有效 cert（任意 issuer）
          L3: ≥1 个来自 trusted CA 的有效 cert
          L4: trusted CA 的 cert 中含 claim="entity_verified"

        无效签名的 cert 静默跳过（不降级，不抛异常）。
        """
        has_any = False
        has_trusted = False
        has_entity = False

        for cert in certs:
            try:
                if not verify_certification(cert, did):
                    continue
            except (BadSignatureError, KeyError, ValueError, Exception):
                continue  # 篡改或格式错误，跳过

            has_any = True
            issuer = cert.get("issuer", "")
            issuer_pk = cert.get("issuer_pubkey", "")

            if self._is_trusted_ca(issuer, issuer_pk):
                has_trusted = True
                if cert.get("claim") == "entity_verified":
                    has_entity = True

        if has_entity and has_trusted:
            return 4
        if has_trusted:
            return 3
        if has_any:
            return 2
        return 1

    def _has_entity_verified(self, did: str, certs: list[dict]) -> bool:
        """检查是否存在来自 trusted CA 的有效 entity_verified cert。"""
        for cert in certs:
            try:
                if (
                    cert.get("claim") == "entity_verified"
                    and self._is_trusted_ca(
                        cert.get("issuer", ""),
                        cert.get("issuer_pubkey", ""),
                    )
                    and verify_certification(cert, did)
                ):
                    return True
            except Exception:
                continue
        return False

    def _compute_trust_score(self, trust_level: int, resolution_status: str) -> float:
        """
        0.0 – 1.0 归一化信任分。
        - 基础分由 trust_level 决定
        - live resolution 额外 +0.05（活跃性证明）
        - failed → 0.0
        """
        if resolution_status == "failed":
            return 0.0
        base = _BASE_SCORES.get(trust_level, 0.0)
        bonus = 0.05 if resolution_status == "live" else 0.0
        return min(1.0, base + bonus)


# ---------------------------------------------------------------------------
# 工厂函数：与 daemon storage 集成
# ---------------------------------------------------------------------------

def make_storage_cert_fetcher(db_path=None) -> CertFetcher:
    """
    创建从 AgentNexus SQLite 存储读取 certifications 的 CertFetcher。

    Args:
        db_path: 可选，覆盖默认 DB_PATH（测试时用 tmp_path）

    Returns:
        async (did: str) -> list[dict]
    """
    async def fetcher(did: str) -> list[dict]:
        import agent_net.storage as st
        if db_path is not None:
            from pathlib import Path
            original = st.DB_PATH
            st.DB_PATH = Path(db_path)
            try:
                return await st.get_certifications(did)
            finally:
                st.DB_PATH = original
        return await st.get_certifications(did)

    return fetcher


def make_runtime_verifier(
    trusted_cas: dict[str, str] | None = None,
    db_path=None,
) -> AgentNexusRuntimeVerifier:
    """
    便捷工厂：创建与本地 daemon storage 集成的 RuntimeVerifier。

    Args:
        trusted_cas: {ca_did: pubkey_hex}，例如 Giskard CA 配置
        db_path:     覆盖默认 DB_PATH（测试隔离用）
    """
    return AgentNexusRuntimeVerifier(
        resolver=DIDResolver(),
        trusted_cas=trusted_cas,
        cert_fetcher=make_storage_cert_fetcher(db_path=db_path),
    )
