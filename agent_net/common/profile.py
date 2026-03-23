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

from agent_net.common.constants import NEXUS_VERSION, NEXUS_CONTENT_SCHEMA_VERSION


# ── 工具函数 ─────────────────────────────────────────────────

def _canonical(content: dict) -> bytes:
    """对 content 做规范化 JSON 序列化（确定性字节流，用于签名）"""
    return json.dumps(content, sort_keys=True, separators=(',', ':')).encode('utf-8')


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
        return {
            "header": dict(self.header),
            "content": dict(self.content),
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NexusProfile":
        return cls(
            header=data["header"],
            content=data["content"],
            signature=data.get("signature", ""),
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

    def __repr__(self) -> str:
        return (
            f"NexusProfile(did={self.did!r}, name={self.name!r}, "
            f"tags={self.tags}, signed={bool(self.signature)})"
        )
