"""
Key DID Method Handler

解析 did:key:<multikey> 格式的 DID。
"""
from agent_net.common.did import DIDResolutionResult, DIDKeyTypeUnsupportedError
from agent_net.common import crypto
from .base import DIDMethodHandler
from .utils import build_did_document


class KeyHandler(DIDMethodHandler):
    """
    did:key 方法处理器。

    格式: did:key:z<base58btc(multicodec || pubkey)>

    纯密码学解析，无需网络或数据库。
    """

    method = "key"

    async def resolve(self, did: str, method_specific_id: str) -> DIDResolutionResult:
        """
        解析 did:key:<multikey>

        Args:
            did: 完整的 DID 字符串
            method_specific_id: multikey 部分（z 开头）

        Returns:
            DIDResolutionResult

        Raises:
            DIDKeyTypeUnsupportedError: multikey 解码失败
        """
        try:
            pubkey_bytes = crypto.decode_multikey_ed25519(method_specific_id)
        except ValueError as e:
            raise DIDKeyTypeUnsupportedError(f"Failed to decode did:key: {e}")

        did_document = build_did_document(did, pubkey_bytes)

        return DIDResolutionResult(
            did=did,
            method="key",
            public_key=pubkey_bytes,
            did_document=did_document,
            metadata={"version": "1.0"},
        )
