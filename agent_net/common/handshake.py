"""
agent_net.common.handshake
加密握手模块 —— node 和 relay 共用
（内容与 agent_net.auth.handshake 相同，统一从此处导入）
"""
import os
import json
import time
import base64
import hashlib
from dataclasses import dataclass

from nacl.signing import SigningKey, VerifyKey
from nacl.public import PrivateKey, PublicKey, Box
from nacl.encoding import RawEncoder
from nacl.exceptions import BadSignatureError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass
class SessionKey:
    key: bytes  # 32 bytes, AES-256

    def __eq__(self, other):
        if isinstance(other, SessionKey):
            return self.key == other.key
        if isinstance(other, bytes):
            return self.key == other
        return NotImplemented

    def __len__(self):
        return len(self.key)

    def encrypt(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        nonce = os.urandom(12)
        ct = AESGCM(self.key).encrypt(nonce, plaintext, aad or None)
        return nonce + ct

    def decrypt(self, data: bytes, aad: bytes = b"") -> bytes:
        nonce, ct = data[:12], data[12:]
        return AESGCM(self.key).decrypt(nonce, ct, aad or None)


class HandshakeManager:
    """
    Packet 驱动的四步握手管理器，每次握手创建新实例。

    发起方: create_init_packet() -> process_challenge() -> get_session_key()
    响应方: process_init()       -> verify_response()   -> (返回 SessionKey)
    """

    CHALLENGE_TTL = 30

    def __init__(self, private_key: SigningKey):
        self._signing_key = private_key
        self._verify_key: VerifyKey = private_key.verify_key
        self._x25519_priv = PrivateKey.generate()
        self._x25519_pub = self._x25519_priv.public_key
        self._sender_did: str | None = None
        self._pending_challenge: dict | None = None
        self._peer_x25519_pub: str | None = None
        self._session_key: SessionKey | None = None
        self._init_packet: dict | None = None

    def create_init_packet(self) -> dict:
        pub_b64 = base64.b64encode(bytes(self._verify_key)).decode()
        x25519_b64 = base64.b64encode(bytes(self._x25519_pub)).decode()
        did = self._sender_did or f"did:agent:{hashlib.sha256(bytes(self._verify_key)).hexdigest()[:16]}"
        self._sender_did = did
        return {
            "type": "INIT",
            "sender_did": did,
            "verify_key": pub_b64,
            "x25519_pub": x25519_b64,
            "timestamp": time.time(),
        }

    def process_challenge(self, challenge_packet: dict) -> dict:
        challenge_token = challenge_packet["challenge_token"]
        self._peer_x25519_pub = challenge_packet["x25519_pub"]
        token_bytes = json.dumps(challenge_token, sort_keys=True).encode()
        signed = self._signing_key.sign(token_bytes, encoder=RawEncoder)
        sig_b64 = base64.b64encode(signed.signature).decode()
        return {
            "type": "VERIFY",
            "sender_did": self._sender_did,
            "signature": sig_b64,
            "x25519_pub": base64.b64encode(bytes(self._x25519_pub)).decode(),
        }

    def get_session_key(self) -> SessionKey:
        if self._session_key:
            return self._session_key
        if not self._peer_x25519_pub:
            raise RuntimeError("Handshake not complete. Call process_challenge() first.")
        self._session_key = self._derive(self._peer_x25519_pub)
        return self._session_key

    def process_init(self, init_packet: dict) -> dict:
        self._init_packet = init_packet
        nonce = base64.b64encode(os.urandom(32)).decode()
        challenge_token = {
            "nonce": nonce,
            "timestamp": time.time(),
            "target_did": init_packet["sender_did"],
        }
        self._pending_challenge = challenge_token
        return {
            "type": "CHALLENGE",
            "challenge_token": challenge_token,
            "x25519_pub": base64.b64encode(bytes(self._x25519_pub)).decode(),
        }

    def verify_response(self, verify_packet: dict) -> SessionKey:
        if not self._pending_challenge:
            raise RuntimeError("No pending challenge.")
        age = time.time() - self._pending_challenge["timestamp"]
        if age > self.CHALLENGE_TTL:
            raise ValueError(f"Challenge expired ({age:.1f}s)")
        claimed_vk_b64 = self._init_packet.get("verify_key", "")
        try:
            vk = VerifyKey(base64.b64decode(claimed_vk_b64))
            token_bytes = json.dumps(self._pending_challenge, sort_keys=True).encode()
            sig = base64.b64decode(verify_packet["signature"])
            vk.verify(token_bytes, sig)
        except BadSignatureError:
            raise PermissionError("Signature verification failed: identity mismatch.")
        self._peer_x25519_pub = verify_packet["x25519_pub"]
        self._session_key = self._derive(self._peer_x25519_pub)
        return self._session_key

    def _derive(self, peer_x25519_pub_b64: str) -> SessionKey:
        peer_pub = PublicKey(base64.b64decode(peer_x25519_pub_b64))
        box = Box(self._x25519_priv, peer_pub)
        return SessionKey(key=bytes(box)[:32])
