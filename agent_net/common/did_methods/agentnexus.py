"""
AgentNexus DID Method Handler

解析 did:agentnexus:<multikey> 格式的 DID。
"""
import time

from agent_net.common.did import DIDResolutionResult, DIDKeyExtractionError
from agent_net.common import crypto
from .base import DIDMethodHandler
from .utils import build_did_document


class AgentNexusHandler(DIDMethodHandler):
    """
    did:agentnexus 方法处理器。

    格式: did:agentnexus:z<base58btc(0xED01 || ed25519_pubkey)>

    纯密码学解析，无需网络或数据库。
    """

    method = "agentnexus"

    async def resolve(self, did: str, method_specific_id: str) -> DIDResolutionResult:
        """
        解析 did:agentnexus:<multikey>

        Args:
            did: 完整的 DID 字符串
            method_specific_id: multikey 部分（z 开头）

        Returns:
            DIDResolutionResult

        Raises:
            DIDKeyExtractionError: multikey 解码失败
        """
        try:
            pubkey_bytes = crypto.decode_multikey_ed25519(method_specific_id)
        except ValueError as e:
            raise DIDKeyExtractionError(f"Failed to decode did:agentnexus multikey: {e}")

        # 构建 DID Document
        did_document = build_did_document(did, pubkey_bytes)

        return DIDResolutionResult(
            did=did,
            method="agentnexus",
            public_key=pubkey_bytes,
            did_document=did_document,
            metadata={"version": "1.0", "created": time.strftime("%Y-%m-%dT%H:%M:%SZ")},
        )
