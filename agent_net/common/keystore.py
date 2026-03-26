"""
Agent 密钥导出/导入模块

格式: JSON envelope
  {
    "version": "1.0",
    "salt": "<16字节 hex>",
    "encrypted": "<nacl SecretBox 密文 hex>"
  }

加密方案:
  key = argon2id.kdf(32, password, salt)
  encrypted = SecretBox(key).encrypt(payload_json)

payload (明文 JSON):
  { "did": "...", "private_key_hex": "...", "profile": {...}, "certifications": [...] }
"""
import json
from nacl.pwhash import argon2id
from nacl.secret import SecretBox
from nacl.utils import random as nacl_random


# argon2id 参数（适合交互式密码）
_KDF_OPS = argon2id.OPSLIMIT_INTERACTIVE
_KDF_MEM = argon2id.MEMLIMIT_INTERACTIVE
_SALT_LEN = 16


def export_agent(
    did: str,
    private_key_hex: str,
    profile: dict,
    password: str,
    certifications: list | None = None,
) -> bytes:
    """
    加密导出 Agent 身份包

    Args:
        did: Agent DID 字符串
        private_key_hex: Ed25519 私钥 (32字节 hex)
        profile: Agent profile dict
        password: 用户密码（明文）
        certifications: Agent 的认证列表（可选）

    Returns:
        JSON 格式的加密包（bytes）
    """
    salt = nacl_random(_SALT_LEN)
    key = argon2id.kdf(
        SecretBox.KEY_SIZE,
        password.encode("utf-8"),
        salt,
        opslimit=_KDF_OPS,
        memlimit=_KDF_MEM,
    )
    box = SecretBox(key)

    payload = {
        "did": did,
        "private_key_hex": private_key_hex,
        "profile": profile,
        "certifications": certifications or [],
    }
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encrypted = box.encrypt(payload_json)

    envelope = {
        "version": "1.0",
        "salt": salt.hex(),
        "encrypted": encrypted.hex(),
    }
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def import_agent(data: bytes, password: str) -> dict:
    """
    解密导入 Agent 身份包

    Args:
        data: export_agent() 返回的 bytes
        password: 用户密码（明文）

    Returns:
        { "did": str, "private_key_hex": str, "profile": dict, "certifications": list }

    Raises:
        ValueError: 格式错误或密码错误
    """
    try:
        envelope = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid keystore format: {e}") from e

    version = envelope.get("version")
    if version != "1.0":
        raise ValueError(f"Unsupported keystore version: {version!r}")

    try:
        salt = bytes.fromhex(envelope["salt"])
        encrypted = bytes.fromhex(envelope["encrypted"])
    except (KeyError, ValueError) as e:
        raise ValueError(f"Malformed keystore envelope: {e}") from e

    key = argon2id.kdf(
        SecretBox.KEY_SIZE,
        password.encode("utf-8"),
        salt,
        opslimit=_KDF_OPS,
        memlimit=_KDF_MEM,
    )
    box = SecretBox(key)

    try:
        payload_json = box.decrypt(encrypted)
    except Exception as e:
        raise ValueError("Decryption failed — wrong password or corrupted data") from e

    try:
        payload = json.loads(payload_json.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid payload JSON after decryption: {e}") from e

    # 基础校验
    if "did" not in payload or "private_key_hex" not in payload:
        raise ValueError("Keystore payload missing required fields (did, private_key_hex)")

    return payload
