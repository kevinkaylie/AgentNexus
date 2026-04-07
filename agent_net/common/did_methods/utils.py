"""
DID Method Handler 共用工具方法

包含：
- build_did_document：构建 W3C DID Document
- extract_ed25519_key_from_doc：从 DID Document 提取 Ed25519 公钥
- compute_x402_score：计算 MEEET x402 评分
- fetch_did_web_document：获取 did:web 的 DID Document
"""
import json
from typing import Optional

import httpx

from agent_net.common import crypto


def compute_x402_score(reputation: int) -> int:
    """
    计算 MEEET Agent 的 x402 评分

    映射公式: min(100, 10 + (reputation / 850) * 82)
    参考: ADR-008 Q5 答疑

    Args:
        reputation: MEEET 平台的 reputation 值

    Returns:
        x402 评分 (0-100)
    """
    score = 10 + int((reputation / 850) * 82)
    return min(100, score)


def build_did_document(did: str, pubkey_bytes: bytes,
                       services: list[dict] | None = None) -> dict:
    """
    构建符合 W3C DID Core 和 did:agentnexus 规范的 DID Document

    包含:
    - Ed25519VerificationKey2018 (authentication, assertion)
    - X25519KeyAgreementKey2019 (keyAgreement，用于 ECDH)
    - service 数组（可选，由调用者传入）

    Args:
        did: DID 字符串
        pubkey_bytes: 32 字节 Ed25519 公钥
        services: 可选的 service 列表

    Returns:
        W3C DID Document 字典
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


def extract_ed25519_key_from_doc(doc: dict) -> Optional[bytes]:
    """
    从 DID Document 提取 Ed25519 公钥

    按优先级检查:
    1. publicKeyMultibase (Ed25519VerificationKey2020/2018) - 去掉 'z' 前缀和 multicodec 前缀
    2. publicKeyBase58 (Ed25519VerificationKey2018) - base58 解码
    3. publicKeyJwk (OKP, crv: Ed25519) - base64url 解码 x 字段

    参考: WG DID Resolution v1.0 §3.1.1

    Args:
        doc: DID Document 字典

    Returns:
        32 字节 Ed25519 公钥，或 None 如果未找到
    """
    verification_methods = doc.get("verificationMethod", [])

    for vm in verification_methods:
        vm_type = vm.get("type", "")

        # 优先级 1: publicKeyMultibase (支持 2020 和 2018 类型)
        if "publicKeyMultibase" in vm and "Ed25519" in vm_type:
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


async def fetch_did_web_document(domain: str) -> tuple[dict, str]:
    """
    从 HTTPS 端点获取 did:web 的 DID Document

    Args:
        domain: did:web:<domain> 中的域名部分

    Returns:
        (did_document, resolved_url) 元组

    Raises:
        DIDNotFoundError: 网络错误或 HTTP 错误
        DIDKeyExtractionError: JSON 解析失败
    """
    from agent_net.common.did import DIDNotFoundError, DIDKeyExtractionError

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

    return did_doc, doc_url
