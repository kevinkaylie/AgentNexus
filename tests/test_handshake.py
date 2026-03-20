"""
加密握手模块测试套件
覆盖：完整握手、身份伪造检测、会话密钥加解密、过期 Challenge、重放攻击
"""
import time
import pytest

from agent_net.auth.handshake import HandshakeManager, SessionKey
from agent_net.identity.did_generator import DIDGenerator


# ── tc-h01: 完整握手，双方 session key 一致 ───────────────

def test_full_handshake_success():
    alice = DIDGenerator.create_new(name="Alice")
    bob = DIDGenerator.create_new(name="Bob")

    manager_a = HandshakeManager(alice.private_key)
    manager_b = HandshakeManager(bob.private_key)

    # A -> B: INIT
    init_packet = manager_a.create_init_packet()

    # B -> A: CHALLENGE
    challenge_packet = manager_b.process_init(init_packet)
    assert "challenge_token" in challenge_packet

    # A -> B: VERIFY
    verify_packet = manager_a.process_challenge(challenge_packet)

    # B 验证并派生 key
    session_key_b = manager_b.verify_response(verify_packet)

    # A 派生 key
    session_key_a = manager_a.get_session_key()

    assert session_key_a == session_key_b
    assert len(session_key_a) == 32  # AES-256


# ── tc-h02: 身份伪造，签名与声明 DID 不匹配 ──────────────

def test_identity_theft_fails():
    alice = DIDGenerator.create_new(name="Alice")
    hacker = DIDGenerator.create_new(name="Hacker")
    bob = DIDGenerator.create_new(name="Bob")

    manager_hacker = HandshakeManager(hacker.private_key)
    manager_b = HandshakeManager(bob.private_key)

    # 黑客发 INIT，然后篡改 sender_did 冒充 Alice
    fake_init = manager_hacker.create_init_packet()
    fake_init["sender_did"] = alice.did  # 篡改 DID 声明，但 verify_key 仍是 hacker 的

    challenge = manager_b.process_init(fake_init)
    verify = manager_hacker.process_challenge(challenge)

    # B 用 INIT 包里的 verify_key（hacker 的）验签，签名本身能过
    # 但 sender_did 与 verify_key 不对应 —— 此处测试签名验证逻辑
    # 实际上 hacker 用自己的私钥签，verify_key 也是自己的，签名能过
    # 真正的 identity theft 检测需要 DID -> verify_key 的可信映射
    # 这里验证：若 verify_key 被替换为 Alice 的，签名必然失败
    fake_init["verify_key"] = __import__('base64').b64encode(
        bytes(alice.verify_key)
    ).decode()
    manager_b2 = HandshakeManager(bob.private_key)
    manager_b2.process_init(fake_init)
    challenge2 = manager_b2._pending_challenge
    # 重新构造 challenge packet 供 hacker 签名
    challenge_packet2 = {"challenge_token": challenge2, "x25519_pub": challenge["x25519_pub"]}
    verify2 = manager_hacker.process_challenge(challenge_packet2)

    with pytest.raises(PermissionError):
        manager_b2.verify_response(verify2)


# ── tc-h03: session key 可用于 AES-256-GCM 加解密 ────────

def test_session_key_encrypt_decrypt():
    alice = DIDGenerator.create_new(name="Alice")
    bob = DIDGenerator.create_new(name="Bob")

    ma = HandshakeManager(alice.private_key)
    mb = HandshakeManager(bob.private_key)

    sk_b = mb.verify_response(ma.process_challenge(mb.process_init(ma.create_init_packet())))
    sk_a = ma.get_session_key()

    plaintext = b"Hello, AgentNexus!"
    ciphertext = sk_a.encrypt(plaintext)
    assert sk_b.decrypt(ciphertext) == plaintext


# ── tc-h04: 不同握手产生不同 session key ─────────────────

def test_different_handshakes_produce_different_keys():
    alice = DIDGenerator.create_new(name="Alice")
    bob = DIDGenerator.create_new(name="Bob")

    def do_handshake():
        ma = HandshakeManager(alice.private_key)
        mb = HandshakeManager(bob.private_key)
        mb.verify_response(ma.process_challenge(mb.process_init(ma.create_init_packet())))
        return ma.get_session_key().key

    key1 = do_handshake()
    key2 = do_handshake()
    assert key1 != key2  # 每次握手 X25519 临时密钥不同


# ── tc-h05: Challenge 过期后拒绝 ─────────────────────────

def test_expired_challenge_rejected(monkeypatch):
    alice = DIDGenerator.create_new(name="Alice")
    bob = DIDGenerator.create_new(name="Bob")

    ma = HandshakeManager(alice.private_key)
    mb = HandshakeManager(bob.private_key)

    init_packet = ma.create_init_packet()
    challenge_packet = mb.process_init(init_packet)

    # 篡改 challenge timestamp 使其过期
    challenge_packet["challenge_token"]["timestamp"] -= 60

    with pytest.raises(ValueError, match="expired"):
        ma.process_challenge(challenge_packet)
        # process_challenge 本身不校验过期，由 verify_response 校验
        # 直接让 mb 的 pending_challenge 过期
        mb._pending_challenge["timestamp"] -= 60
        verify = ma.process_challenge(challenge_packet)
        mb.verify_response(verify)


# ── tc-h06: verify_response 在无 challenge 时抛出 ────────

def test_verify_without_challenge_raises():
    bob = DIDGenerator.create_new(name="Bob")
    mb = HandshakeManager(bob.private_key)
    with pytest.raises(RuntimeError):
        mb.verify_response({"signature": "", "x25519_pub": ""})


# ── tc-h07: get_session_key 在握手未完成时抛出 ───────────

def test_get_session_key_before_handshake_raises():
    alice = DIDGenerator.create_new(name="Alice")
    ma = HandshakeManager(alice.private_key)
    with pytest.raises(RuntimeError):
        ma.get_session_key()
