"""
MEEET DID Method Handler

解析 did:meeet:agent_<uuid> 格式的 DID。

通过 MEEET Solana API 获取 Ed25519 公钥，并缓存到 Redis。
"""
import json
import time
import os
import logging

import aiohttp

from agent_net.common.did import DIDResolutionResult, DIDNotFoundError
from agent_net.common import crypto
from .base import DIDMethodHandler
from .utils import build_did_document, compute_x402_score

logger = logging.getLogger(__name__)


# Mock Solana RPC URL (ADR-008 Q7 答疑：先用 Mock 实现)
MEEET_SOLANA_RPC_URL = os.environ.get("MEEET_SOLANA_RPC_URL", "http://localhost:9999/mock-solana")

_MEEET_MAPPING_PREFIX = "meeet:mapping:"
_MEEET_TTL = 86400  # 24 hours


class MeeetHandler(DIDMethodHandler):
    """
    did:meeet 方法处理器。

    格式: did:meeet:agent_<uuid>

    需要 Redis 客户端来缓存映射数据。
    解析流程：
    1. 先查 Redis 缓存
    2. 未命中则查询 Solana API
    3. 写入缓存并返回
    """

    method = "meeet"

    def __init__(self, redis_client):
        """
        初始化处理器。

        Args:
            redis_client: Redis 异步客户端实例
        """
        self.redis = redis_client

    async def resolve(self, did: str, method_specific_id: str) -> DIDResolutionResult:
        """
        解析 did:meeet:agent_<uuid>

        Args:
            did: 完整的 DID 字符串
            method_specific_id: agent_<uuid> 部分

        Returns:
            DIDResolutionResult

        Raises:
            DIDNotFoundError: 无法解析（API 不可达或 Agent 不存在）
        """
        # 验证格式
        if not method_specific_id.startswith("agent_"):
            raise DIDNotFoundError(f"Invalid did:meeet format: {did}")

        # 先查缓存
        mapping = await self._get_cached_mapping(did)
        if mapping:
            return self._build_result(did, mapping)

        # 查询 Solana API
        agent_uuid = method_specific_id.replace("agent_", "")
        mapping = await self._resolve_via_solana(agent_uuid)
        if mapping:
            # 缓存结果
            await self._cache_mapping(did, mapping)
            return self._build_result(did, mapping)

        raise DIDNotFoundError(f"Cannot resolve MEEET DID: {did}")

    async def _get_cached_mapping(self, did: str) -> dict | None:
        """从 Redis 获取缓存的映射数据"""
        mapping_key = f"{_MEEET_MAPPING_PREFIX}{did}"
        cached = await self.redis.get(mapping_key)
        if cached:
            return json.loads(cached)
        return None

    async def _cache_mapping(self, did: str, mapping: dict) -> None:
        """缓存映射数据到 Redis"""
        mapping_key = f"{_MEEET_MAPPING_PREFIX}{did}"
        await self.redis.set(
            mapping_key,
            json.dumps(mapping),
            ex=_MEEET_TTL
        )

    async def _resolve_via_solana(self, agent_uuid: str) -> dict | None:
        """
        通过 Solana API 解析 MEEET Agent。

        Args:
            agent_uuid: Agent UUID

        Returns:
            映射数据字典，或 None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{MEEET_SOLANA_RPC_URL}/agent/{agent_uuid}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return None
                    solana_data = await resp.json()
        except Exception as e:
            logger.warning(f"Solana API 调用失败: {type(e).__name__} — {e}")
            return None

        pubkey_hex = solana_data.get("pubkey")
        reputation = solana_data.get("reputation", 0)

        if not pubkey_hex:
            return None

        # 推导 did:agentnexus
        agentnexus_did = self._pubkey_to_agentnexus_did(pubkey_hex)
        x402_score = compute_x402_score(reputation)

        return {
            "agentnexus_did": agentnexus_did,
            "pubkey_hex": pubkey_hex,
            "meeet_reputation": reputation,
            "x402_score": x402_score,
            "registered_at": time.time(),
            "last_verified": time.time(),
            "source": "solana",
        }

    def _pubkey_to_agentnexus_did(self, pubkey_hex: str) -> str:
        """从 Ed25519 公钥推导 did:agentnexus"""
        pubkey_bytes = bytes.fromhex(pubkey_hex)
        multikey = crypto.encode_multikey_ed25519(pubkey_bytes)
        return f"did:agentnexus:{multikey}"

    def _build_result(self, did: str, mapping: dict) -> DIDResolutionResult:
        """构建解析结果"""
        pubkey_bytes = bytes.fromhex(mapping["pubkey_hex"])
        agentnexus_did = mapping["agentnexus_did"]

        # 构建 DID Document（W3C DID Core 规范）
        # @context 顺序：DID Core 在前，security vocabulary 在后
        did_document = {
            "@context": [
                "https://www.w3.org/ns/did/v1",
                "https://w3id.org/security/multikey/v1"
            ],
            "id": agentnexus_did,
            "alsoKnownAs": [did],
            "verificationMethod": [{
                "id": f"{agentnexus_did}#key-1",
                "type": "Multikey",
                "controller": agentnexus_did,
                "publicKeyMultibase": agentnexus_did.replace("did:agentnexus:", ""),
            }],
            "authentication": [f"{agentnexus_did}#key-1"],
            "assertionMethod": [f"{agentnexus_did}#key-1"],
        }

        return DIDResolutionResult(
            did=did,
            method="meeet",
            public_key=pubkey_bytes,
            did_document=did_document,
            metadata={
                "source": mapping.get("source", "meeet_solana"),
                "meeet_reputation_score": mapping["meeet_reputation"],
                "x402_score": mapping["x402_score"],
                "agentnexus_did": agentnexus_did,
            },
        )
