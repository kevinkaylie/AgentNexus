"""
Web DID Method Handler

解析 did:web:<domain> 格式的 DID。
"""
from agent_net.common.did import DIDResolutionResult, DIDKeyExtractionError
from .base import DIDMethodHandler
from .utils import fetch_did_web_document, extract_ed25519_key_from_doc


class WebHandler(DIDMethodHandler):
    """
    did:web 方法处理器。

    格式: did:web:<domain>

    从 HTTPS 端点获取 DID Document：
    - did:web:example.com -> https://example.com/.well-known/did.json
    - did:web:example.com/path -> https://example.com/path/did.json
    """

    method = "web"

    async def resolve(self, did: str, method_specific_id: str) -> DIDResolutionResult:
        """
        解析 did:web:<domain>

        Args:
            did: 完整的 DID 字符串
            method_specific_id: 域名部分

        Returns:
            DIDResolutionResult

        Raises:
            DIDNotFoundError: 网络错误或 HTTP 错误
            DIDKeyExtractionError: JSON 解析失败或未找到 Ed25519 密钥
        """
        did_doc, doc_url = await fetch_did_web_document(method_specific_id)

        # 从 DID Document 提取 Ed25519 公钥
        pubkey_bytes = extract_ed25519_key_from_doc(did_doc)

        if not pubkey_bytes:
            raise DIDKeyExtractionError(f"No Ed25519 key found in did:web document from {doc_url}")

        return DIDResolutionResult(
            did=did,
            method="web",
            public_key=pubkey_bytes,
            did_document=did_doc,
            metadata={"resolved_url": doc_url, "version": "1.0"},
        )
