"""
密码学操作模块 - Ed25519/X25519 密钥推导与多编码格式
用于 did:agentnexus DID Method
"""
import hashlib
from nacl.signing import SigningKey, VerifyKey
import nacl.bindings


# ── 多编码格式常量 ────────────────────────────────────────

# Multibase base58btc 前缀
MULTIBASE_B58BTC_PREFIX = 0x7A  # ASCII 'z'

# Multicodec 前缀
MULTICODEC_ED25519_PUBKEY = 0xED01  # Ed25519 public key
MULTICODEC_X25519_PUBKEY = 0xEC02  # X25519 public key (key agreement)

# 编码后的长度（包含 multicodec 前缀）
# multicodec 2 bytes + raw key 32 bytes = 34 bytes for Ed25519/X25519
_ED25519_MULTICODEC_LEN = 34
_X25519_MULTICODEC_LEN = 34


# ── Base58BTC ─────────────────────────────────────────────

def _base58_chars() -> str:
    """Base58 character set (Bitcoin alphabet)"""
    return "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


_BASE58_TABLE = {c: i for i, c in enumerate(_base58_chars())}
_BASE58_ALPHABET = _base58_chars()


def _base58_encode(data: bytes) -> str:
    """Encode bytes to base58btc string"""
    if not data:
        return ""

    # Count leading zero bytes
    leading_zeros = 0
    for b in data:
        if b == 0:
            leading_zeros += 1
        else:
            break

    result = ["1"] * leading_zeros

    # Strip leading zeros and convert remaining to integer
    remaining = data[leading_zeros:]
    if not remaining:
        return "".join(result)

    num = int.from_bytes(remaining, "big")
    while num > 0:
        num, rem = divmod(num, 58)
        result.append(_BASE58_ALPHABET[rem])

    # divmod gives LSB-first, reverse to MSB-first
    # leading "1"s are already correct (MSB position of the original data)
    result = result[:leading_zeros] + list(reversed(result[leading_zeros:]))
    return "".join(result)


def _base58_decode(s: str) -> bytes:
    """Decode base58btc string to bytes"""
    if not s:
        return b""

    # Count leading '1's (each represents a leading zero byte)
    leading_zeros = 0
    for c in s:
        if c == "1":
            leading_zeros += 1
        else:
            break

    result = [b"\x00"] * leading_zeros

    # Skip leading '1's and decode the rest
    remaining = s[leading_zeros:]
    if not remaining:
        return b"".join(result)

    num = 0
    for c in remaining:
        num = num * 58 + _BASE58_TABLE[c]

    if num > 0:
        result.append(num.to_bytes((num.bit_length() + 7) // 8, "big"))

    return b"".join(result)


# ── Ed25519 ↔ X25519 推导 ─────────────────────────────────

def ed25519_pub_to_x25519(ed25519_pub_bytes: bytes) -> bytes:
    """
    Ed25519 公钥 → X25519 公钥（用于 ECDH key agreement）

    Ed25519 公钥直接是 Curve25519 公钥的曲线点，
    使用 nacl.bindings.crypto_sign_ed25519_pk_to_curve25519 转换。
    """
    if len(ed25519_pub_bytes) != 32:
        raise ValueError(f"Ed25519 public key must be 32 bytes, got {len(ed25519_pub_bytes)}")
    return nacl.bindings.crypto_sign_ed25519_pk_to_curve25519(ed25519_pub_bytes)


def ed25519_priv_to_x25519(ed25519_priv_bytes: bytes) -> bytes:
    """
    Ed25519 私钥 → X25519 私钥（用于 ECDH key agreement）

    使用 nacl.bindings.crypto_sign_ed25519_sk_to_curve25519 转换。
    """
    if len(ed25519_priv_bytes) != 32:
        raise ValueError(f"Ed25519 private key must be 32 bytes, got {len(ed25519_priv_bytes)}")
    return nacl.bindings.crypto_sign_ed25519_sk_to_curve25519(ed25519_priv_bytes)


# ── Multibase/Multicodec 编码 ─────────────────────────────

def encode_multikey_ed25519(pubkey_bytes: bytes) -> str:
    """
    将 Ed25519 公钥编码为 multicodec multibase 格式 (z-prefix base58btc)

    格式: z + base58(multicodec_prefix || pubkey)
    multicodec_prefix = 0xed01 (2 bytes big-endian)

    参考: did:key spec, WG DID Resolution v1.0 §3.2
    """
    if len(pubkey_bytes) != 32:
        raise ValueError(f"Public key must be 32 bytes, got {len(pubkey_bytes)}")

    # Multicodec prefix (2 bytes) + 32-byte Ed25519 pubkey
    prefix = MULTICODEC_ED25519_PUBKEY.to_bytes(2, "big")
    multicodec_data = prefix + pubkey_bytes

    # Multibase encode: 'z' prefix + base58btc of multicodec data
    return "z" + _base58_encode(multicodec_data)


def decode_multikey_ed25519(multikey: str) -> bytes:
    """
    解码 multicodec multikey 为 Ed25519 公钥（32字节）

    验证 multicodec 前缀为 0xed01
    """
    if not multikey.startswith("z"):
        raise ValueError(f"Invalid multikey: must start with 'z', got {multikey[0]}")

    # Strip 'z' prefix and decode base58btc
    multicodec_data = _base58_decode(multikey[1:])

    if len(multicodec_data) < 2:
        raise ValueError("Multikey data too short after base58 decoding")

    # Extract and verify multicodec prefix
    prefix = int.from_bytes(multicodec_data[:2], "big")
    if prefix != MULTICODEC_ED25519_PUBKEY:
        raise ValueError(
            f"Unsupported multicodec prefix: 0x{prefix:04x}, expected 0x{MULTICODEC_ED25519_PUBKEY:04x}"
        )

    # Return the 32-byte public key
    return multicodec_data[2:]


def encode_multikey_x25519(pubkey_bytes: bytes) -> str:
    """
    将 X25519 公钥编码为 multicodec multikey 格式 (z-prefix base58btc)

    格式: z + base58(multicodec_prefix || pubkey)
    multicodec_prefix = 0xec02 (2 bytes big-endian)
    """
    if len(pubkey_bytes) != 32:
        raise ValueError(f"X25519 public key must be 32 bytes, got {len(pubkey_bytes)}")

    prefix = MULTICODEC_X25519_PUBKEY.to_bytes(2, "big")
    multicodec_data = prefix + pubkey_bytes

    return "z" + _base58_encode(multicodec_data)


def decode_multikey_x25519(multikey: str) -> bytes:
    """
    解码 multicodec multikey 为 X25519 公钥（32字节）
    """
    if not multikey.startswith("z"):
        raise ValueError(f"Invalid multikey: must start with 'z', got {multikey[0]}")

    multicodec_data = _base58_decode(multikey[1:])

    if len(multicodec_data) < 2:
        raise ValueError("Multikey data too short after base58 decoding")

    prefix = int.from_bytes(multicodec_data[:2], "big")
    if prefix != MULTICODEC_X25519_PUBKEY:
        raise ValueError(
            f"Unsupported multicodec prefix: 0x{prefix:04x}, expected 0x{MULTICODEC_X25519_PUBKEY:04x}"
        )

    return multicodec_data[2:]


# ── Sender ID 推导 ───────────────────────────────────────

def derive_sender_id(public_key: bytes) -> str:
    """
    从 Ed25519 公钥推导 sender_id

    算法: sender_id = SHA-256(public_key)[0:16]
    返回: 16字节的 lowercase hex 字符串 (32字符)

    参考: WG DID Resolution v1.0 §4
    """
    if len(public_key) != 32:
        raise ValueError(f"Public key must be 32 bytes, got {len(public_key)}")

    digest = hashlib.sha256(public_key).digest()
    sender_id_bytes = digest[:16]
    return sender_id_bytes.hex()


# ── DID Generation ────────────────────────────────────────

def create_new_did(name: str = "") -> tuple[str, str, str]:
    """
    生成新的 did:agentnexus DID

    返回: (did_string, private_key_hex, public_key_hex)
    """
    sk = SigningKey.generate()
    pk_bytes = sk.verify_key.encode()

    # Encode public key as multikey
    multikey = encode_multikey_ed25519(pk_bytes)
    did = f"did:agentnexus:{multikey}"

    return did, sk.encode().hex(), pk_bytes.hex()


# ── Base58 for did:agent legacy format ───────────────────

def encode_base58btc(data: bytes) -> str:
    """Encode bytes to base58btc (alias for multikey encoding without multicodec)"""
    return _base58_encode(data)


def decode_base58btc(s: str) -> bytes:
    """Decode base58btc string to bytes"""
    return _base58_decode(s)
