"""
agent_net.common.profile
NexusProfile —— Agent 签名名片

结构：
  {
    "header":  { "did", "pubkey"(hex), "version" },
    "content": {
        "schema_version": "1.0",   ← content 格式版本（已签名，防篡改）
        "name", "description", "tags",
        "endpoints": {"relay", "direct"},
        "updated_at": <unix_timestamp>
    },
    "signature": "<Ed25519 sig over canonical JSON(content)，hex>"
  }

签名规范：
  canonical(content) = json.dumps(content, sort_keys=True, separators=(',',':')).encode('utf-8')
  signature = SigningKey.sign(canonical, encoder=RawEncoder).signature  →  hex string
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

from nacl.encoding import HexEncoder, RawEncoder
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from agent_net.common.constants import NEXUS_VERSION, NEXUS_CONTENT_SCHEMA_VERSION, NEXUS_CERTIFICATION_VERSION


# ── 工具函数 ─────────────────────────────────────────────────

def _canonical(content: dict) -> bytes:
    """对 content 做规范化 JSON 序列化（确定性字节流，用于签名）"""
    return json.dumps(content, sort_keys=True, separators=(',', ':')).encode('utf-8')


def canonical_announce(
    did: str,
    endpoint: str,
    timestamp: float,
    public_ip: str | None = None,
    public_port: int | None = None,
) -> bytes:
    """生成 /announce 签名载荷的 canonical JSON bytes"""
    obj: dict = {"did": did, "endpoint": endpoint, "timestamp": timestamp}
    if public_ip is not None:
        obj["public_ip"] = public_ip
    if public_port is not None:
        obj["public_port"] = public_port
    return json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')


def verify_signed_payload(payload: bytes, signature_hex: str, pubkey_hex: str) -> bool:
    """
    通用 Ed25519 签名验证。
    成功返回 True，签名无效抛 nacl.exceptions.BadSignatureError。
    """
    vk = VerifyKey(bytes.fromhex(pubkey_hex))
    sig_bytes = bytes.fromhex(signature_hex)
    vk.verify(payload, sig_bytes)
    return True


def _canonical_certification(did: str, claim: str, evidence: str, issued_at: float) -> bytes:
    """生成 certification 签名载荷的 canonical JSON bytes"""
    obj = {"claim": claim, "did": did, "evidence": evidence, "issued_at": issued_at}
    return json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')


def create_certification(
    target_did: str,
    issuer_did: str,
    issuer_signing_key: SigningKey,
    claim: str,
    evidence: str = "",
) -> dict:
    """
    签发一条认证：issuer 用自己的私钥为 target_did 签名。
    返回完整的 certification dict。
    """
    issued_at = time.time()
    canonical = _canonical_certification(target_did, claim, evidence, issued_at)
    raw_sig = issuer_signing_key.sign(canonical, encoder=RawEncoder).signature
    issuer_pubkey = issuer_signing_key.verify_key.encode(HexEncoder).decode()
    return {
        "version": NEXUS_CERTIFICATION_VERSION,
        "issuer": issuer_did,
        "issuer_pubkey": issuer_pubkey,
        "claim": claim,
        "evidence": evidence,
        "issued_at": issued_at,
        "signature": raw_sig.hex(),
    }


def verify_certification(cert: dict, target_did: str) -> bool:
    """
    验证一条认证的签名。成功返回 True，失败抛 BadSignatureError。
    """
    canonical = _canonical_certification(
        target_did, cert["claim"], cert.get("evidence", ""), cert["issued_at"],
    )
    vk = VerifyKey(bytes.fromhex(cert["issuer_pubkey"]))
    sig_bytes = bytes.fromhex(cert["signature"])
    vk.verify(canonical, sig_bytes)
    return True


# ── 主类 ─────────────────────────────────────────────────────

@dataclass
class NexusProfile:
    """
    Agent 名片：可独立传播、可验签的身份凭证。
    - header: 身份标识（DID + 公钥 + 版本）
    - content: 可读信息（名称、描述、标签、联系端点）
    - signature: 对 content 的 Ed25519 签名（hex），未签名时为空串
    """
    header: dict
    content: dict
    signature: str = ""
    certifications: list[dict] | None = None

    # ── 构造 ─────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        did: str,
        signing_key: SigningKey,
        name: str,
        description: str = "",
        tags: list[str] | None = None,
        relay: str = "",
        direct: Optional[str] = None,
    ) -> "NexusProfile":
        """创建并签名名片（需要私钥）"""
        verify_key_hex = signing_key.verify_key.encode(HexEncoder).decode()
        header = {
            "did": did,
            "pubkey": verify_key_hex,
            "version": NEXUS_VERSION,
        }
        content = {
            "schema_version": NEXUS_CONTENT_SCHEMA_VERSION,
            "name": name,
            "description": description,
            "tags": tags or [],
            "endpoints": {
                "relay": relay,
                "direct": direct,
            },
            "updated_at": time.time(),
        }
        profile = cls(header=header, content=content)
        profile.sign(signing_key)
        return profile

    # ── 签名 / 验签 ───────────────────────────────────────────

    def sign(self, signing_key: SigningKey) -> "NexusProfile":
        """用私钥对 content 签名，更新 signature 字段"""
        raw_sig = signing_key.sign(_canonical(self.content), encoder=RawEncoder).signature
        self.signature = raw_sig.hex()
        return self

    def verify(self) -> bool:
        """
        用 header.pubkey 验证 signature 是否与 content 一致。
        验证通过返回 True；签名无效抛 nacl.exceptions.BadSignatureError。
        """
        if not self.signature:
            raise ValueError("NexusProfile has no signature")
        pubkey_bytes = bytes.fromhex(self.header["pubkey"])
        vk = VerifyKey(pubkey_bytes)
        sig_bytes = bytes.fromhex(self.signature)
        vk.verify(_canonical(self.content), sig_bytes)  # 失败抛 BadSignatureError
        return True

    # ── 序列化 ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "header": dict(self.header),
            "content": dict(self.content),
            "signature": self.signature,
        }
        if self.certifications:
            d["certifications"] = list(self.certifications)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "NexusProfile":
        return cls(
            header=data["header"],
            content=data["content"],
            signature=data.get("signature", ""),
            certifications=data.get("certifications"),
        )

    # ── 便捷属性 ──────────────────────────────────────────────

    @property
    def did(self) -> str:
        return self.header["did"]

    @property
    def name(self) -> str:
        return self.content.get("name", "")

    @property
    def tags(self) -> list[str]:
        return self.content.get("tags", [])

    @property
    def relay_endpoint(self) -> str:
        return self.content.get("endpoints", {}).get("relay", "")

    @property
    def direct_endpoint(self) -> Optional[str]:
        return self.content.get("endpoints", {}).get("direct")

    @property
    def schema_version(self) -> str:
        return self.content.get("schema_version", "")

    @property
    def updated_at(self) -> float:
        return self.content.get("updated_at", 0.0)

    def add_certification(self, cert: dict) -> "NexusProfile":
        """追加一条认证（不影响 content 签名）"""
        if self.certifications is None:
            self.certifications = []
        self.certifications.append(cert)
        return self

    def __repr__(self) -> str:
        return (
            f"NexusProfile(did={self.did!r}, name={self.name!r}, "
            f"tags={self.tags}, signed={bool(self.signature)})"
        )
