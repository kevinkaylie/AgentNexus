"""
DID Resolution 测试套件

测试 did:agentnexus DID Method 的实现，符合 WG DID Resolution v1.0 规范

运行方式: python -m pytest tests/test_did_resolution.py -v
"""
import asyncio
import hashlib
import importlib
import json
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, ".")

from agent_net.common import crypto
from agent_net.common.did import (
    DIDGenerator,
    DIDResolver,
    DIDResolutionResult,
    create_agentnexus_did,
    resolve_did_sync,
    DIDNotFoundError,
    DIDKeyTypeUnsupportedError,
    DIDKeyExtractionError,
    DIDMethodUnsupportedError,
)


# ── WG 测试向量（来自 did-resolution.json）───────────────

WG_TEST_VECTORS = {
    "did_key_ed25519": {
        "did": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        "expected_method": "key",
        "expected_public_key_hex": "2e6fcce36701dc791488e0d0b1745cc1e33a4c1c9fcc41c63bd343dbbe0970e6",
        "expected_sender_id": "c446d9bcf84d5e3ee966bac5c1f634c1",
    },
    "sender_id_derivation": {
        "public_key_hex": "2e6fcce36701dc791488e0d0b1745cc1e33a4c1c9fcc41c63bd343dbbe0970e6",
        "expected_sender_id_hex": "c446d9bcf84d5e3ee966bac5c1f634c1",
    },
}


# ── 测试夹具 ──────────────────────────────────────────────

@pytest.fixture
def resolver():
    """创建 DIDResolver 实例"""
    return DIDResolver()


@pytest.fixture
def sample_ed25519_key():
    """样本 Ed25519 公钥（来自 WG 测试向量）"""
    return bytes.fromhex("2e6fcce36701dc791488e0d0b1745cc1e33a4c1c9fcc41c63bd343dbbe0970e6")


# ── 密码学测试 ─────────────────────────────────────────────

class TestCryptoOperations:
    """密码学操作测试"""

    def test_multikey_encode_decode_roundtrip(self, sample_ed25519_key):
        """Multikey 编码/解码往返测试"""
        multikey = crypto.encode_multikey_ed25519(sample_ed25519_key)
        assert multikey.startswith("z"), "Multikey must start with 'z'"

        decoded = crypto.decode_multikey_ed25519(multikey)
        assert decoded == sample_ed25519_key, "Decoded key must match original"

    def test_multikey_encode_length(self, sample_ed25519_key):
        """Multikey 编码长度验证"""
        multikey = crypto.encode_multikey_ed25519(sample_ed25519_key)
        # base58btc(34 bytes) ≈ 46 characters + 'z' prefix
        assert len(multikey) > 40, "Multikey should be at least 40 characters"
        assert len(multikey) < 60, "Multikey should be less than 60 characters"

    def test_ed25519_x25519_derivation(self, sample_ed25519_key):
        """Ed25519 → X25519 推导测试"""
        x25519_bytes = crypto.ed25519_pub_to_x25519(sample_ed25519_key)

        # X25519 公钥也是 32 字节
        assert len(x25519_bytes) == 32, "X25519 public key must be 32 bytes"

        # 推导结果应该与原始 Ed25519 公钥不同（除非恰好是同一曲线点）
        # 但关键是推导结果本身应该是有效的 X25519 公钥
        assert x25519_bytes != sample_ed25519_key, "X25519 should differ from Ed25519 (different curve)"

    def test_ed25519_x25519_x25519_pubkey_encoding(self, sample_ed25519_key):
        """X25519 multikey 编码/解码测试"""
        x25519_bytes = crypto.ed25519_pub_to_x25519(sample_ed25519_key)

        # 编码 X25519 multikey
        x_multikey = crypto.encode_multikey_x25519(x25519_bytes)
        assert x_multikey.startswith("z"), "X25519 multikey must start with 'z'"

        # 解码回来
        decoded_x = crypto.decode_multikey_x25519(x_multikey)
        assert decoded_x == x25519_bytes, "Decoded X25519 key must match"

    def test_x25519_multicodec_prefix(self):
        """X25519 multicodec 前缀验证"""
        # 生成一个测试密钥
        from nacl.signing import SigningKey
        sk = SigningKey.generate()
        ed_pk = sk.verify_key.encode()
        x_pk = crypto.ed25519_pub_to_x25519(ed_pk)

        # 编码
        x_multikey = crypto.encode_multikey_x25519(x_pk)

        # 解码后验证 multicodec 前缀为 0xec02
        multicodec_data = crypto._base58_decode(x_multikey[1:])
        prefix = int.from_bytes(multicodec_data[:2], "big")
        assert prefix == 0xEC02, f"X25519 multicodec prefix should be 0xEC02, got 0x{prefix:04X}"

    def test_ed25519_multicodec_prefix(self, sample_ed25519_key):
        """Ed25519 multicodec 前缀验证"""
        multikey = crypto.encode_multikey_ed25519(sample_ed25519_key)
        multicodec_data = crypto._base58_decode(multikey[1:])
        prefix = int.from_bytes(multicodec_data[:2], "big")
        assert prefix == 0xED01, f"Ed25519 multicodec prefix should be 0xED01, got 0x{prefix:04X}"

    def test_derive_sender_id_wg_vector(self, sample_ed25519_key):
        """sender_id 推导 - WG 测试向量"""
        expected_sender_id = WG_TEST_VECTORS["sender_id_derivation"]["expected_sender_id_hex"]

        sender_id = crypto.derive_sender_id(sample_ed25519_key)
        assert sender_id == expected_sender_id, (
            f"sender_id mismatch: expected {expected_sender_id}, got {sender_id}"
        )

    def test_derive_sender_id_length(self):
        """sender_id 长度验证（16字节/32字符 hex）"""
        from nacl.signing import SigningKey
        sk = SigningKey.generate()
        pk = sk.verify_key.encode()

        sender_id = crypto.derive_sender_id(pk)
        assert len(sender_id) == 32, f"sender_id should be 32 hex characters, got {len(sender_id)}"
        assert sender_id == sender_id.lower(), "sender_id should be lowercase hex"

    def test_base58btc_roundtrip(self):
        """Base58BTC 往返编码测试"""
        original = b"\x00\x01\x02\xff\xfe\xfd" + bytes(range(256))
        encoded = crypto.encode_base58btc(original)
        decoded = crypto.decode_base58btc(encoded)
        assert decoded == original, "Base58BTC roundtrip failed"

    def test_invalid_multikey_prefix_raises(self):
        """无效 multicodec 前缀应抛出错误"""
        # 构造一个 secp256k1 前缀 (0xe701) 的 multikey
        from nacl.signing import SigningKey
        sk = SigningKey.generate()
        pk = sk.verify_key.encode()

        # 手动构造错误前缀的 multicodec 数据
        wrong_prefix = 0xE701.to_bytes(2, "big")
        bad_data = wrong_prefix + pk
        bad_multikey = "z" + crypto._base58_encode(bad_data)

        with pytest.raises(ValueError, match="Unsupported multicodec prefix"):
            crypto.decode_multikey_ed25519(bad_multikey)


# ── DID Generator 测试 ────────────────────────────────────

class TestDIDGenerator:
    """DIDGenerator 测试"""

    def test_create_new_legacy_format(self):
        """生成 did:agent:<hex> 格式（向后兼容）"""
        agent_did = DIDGenerator.create_new("test-agent")

        assert agent_did.did.startswith("did:agent:"), "DID should start with did:agent:"
        assert len(agent_did.did) == 10 + 16, "DID should be did:agent: + 16 hex chars"
        assert agent_did.private_key is not None
        assert agent_did.verify_key is not None

    def test_create_agentnexus_format(self):
        """生成 did:agentnexus:<multikey> 格式"""
        agent_did, multikey = DIDGenerator.create_agentnexus("test-agent")

        assert agent_did.did.startswith("did:agentnexus:"), "DID should start with did:agentnexus:"
        assert agent_did.did.endswith(":" + multikey), "DID should end with multikey"
        assert multikey.startswith("z"), "Multikey should start with 'z'"
        assert agent_did.private_key is not None
        assert agent_did.verify_key is not None

    def test_create_agentnexus_multikey_is_valid(self):
        """生成的 did:agentnexus 的 multikey 可以被正确解码"""
        agent_did, multikey = DIDGenerator.create_agentnexus("test-agent")

        # 应该能够成功解码
        decoded_key = crypto.decode_multikey_ed25519(multikey)
        assert len(decoded_key) == 32, "Decoded key should be 32 bytes"

        # 解码后的公钥应该与 verify_key 匹配
        assert decoded_key == agent_did.verify_key.encode()

    def test_create_new_uniqueness(self):
        """每次生成应该产生不同的 DID"""
        dids = set()
        for _ in range(10):
            agent_did = DIDGenerator.create_new("test")
            dids.add(agent_did.did)

        assert len(dids) == 10, "Each generated DID should be unique"


# ── DID Resolver 测试 ──────────────────────────────────────

class TestDIDResolver:
    """DIDResolver 测试"""

    def test_resolve_did_key_wg_vector(self, resolver):
        """解析 did:key - WG 测试向量"""
        did = WG_TEST_VECTORS["did_key_ed25519"]["did"]
        expected_pk_hex = WG_TEST_VECTORS["did_key_ed25519"]["expected_public_key_hex"]
        expected_sender_id = WG_TEST_VECTORS["did_key_ed25519"]["expected_sender_id"]

        result = asyncio.run(resolver.resolve(did))

        assert result.method == "key", f"Expected method 'key', got '{result.method}'"
        assert result.public_key.hex() == expected_pk_hex, "Public key mismatch"
        assert resolver.derive_sender_id(result.public_key) == expected_sender_id

    def test_resolve_agentnexus_new(self, resolver):
        """解析新生成的 did:agentnexus"""
        agent_did, multikey = DIDGenerator.create_agentnexus("test-agent")

        result = asyncio.run(resolver.resolve(agent_did.did))

        assert result.method == "agentnexus", f"Expected method 'agentnexus', got '{result.method}'"
        assert result.did == agent_did.did
        assert result.public_key == agent_did.verify_key.encode()

    def test_resolve_agentnexus_did_document_format(self, resolver):
        """验证 did:agentnexus DID Document 格式"""
        agent_did, _ = DIDGenerator.create_agentnexus("test-agent")
        result = asyncio.run(resolver.resolve(agent_did.did))

        doc = result.did_document
        assert doc is not None, "DID Document should not be None"

        # 验证必需字段
        assert "@context" in doc
        assert "https://www.w3.org/ns/did/v1" in doc["@context"]
        assert doc["id"] == agent_did.did

        # 验证 verificationMethod
        assert "verificationMethod" in doc
        assert len(doc["verificationMethod"]) > 0
        vm = doc["verificationMethod"][0]
        assert vm["type"] == "Ed25519VerificationKey2018"
        assert vm["controller"] == agent_did.did
        assert vm["publicKeyMultibase"].startswith("z")

        # 验证 authentication
        assert "authentication" in doc
        assert f"{agent_did.did}#agent-1" in doc["authentication"]

        # 验证 keyAgreement (X25519)
        assert "keyAgreement" in doc
        ka = doc["keyAgreement"][0]
        assert ka["type"] == "X25519KeyAgreementKey2019"
        assert ka["publicKeyMultibase"].startswith("z")

    def test_resolve_wg_interface(self, resolver):
        """测试 WG 规范接口 resolve_did()"""
        did = WG_TEST_VECTORS["did_key_ed25519"]["did"]
        expected_pk_hex = WG_TEST_VECTORS["did_key_ed25519"]["expected_public_key_hex"]

        wg_result = asyncio.run(resolver.resolve_did(did))

        # WG 格式: { public_key: bytes, method: string, metadata: map }
        assert "public_key" in wg_result
        assert "method" in wg_result
        assert "metadata" in wg_result
        assert isinstance(wg_result["public_key"], bytes)
        assert len(wg_result["public_key"]) == 32
        assert wg_result["public_key"].hex() == expected_pk_hex

    def test_resolve_unsupported_method(self, resolver):
        """不支持的 DID 方法应抛出 DIDMethodUnsupportedError"""
        with pytest.raises(DIDMethodUnsupportedError):
            asyncio.run(resolver.resolve("did:unknown:abc123"))

    def test_resolve_invalid_did_format(self, resolver):
        """无效 DID 格式应抛出错误"""
        with pytest.raises(DIDMethodUnsupportedError, match="must start with 'did:'"):
            asyncio.run(resolver.resolve("notadid:web:example.com"))

    def test_resolve_invalid_multikey(self, resolver):
        """无效 multikey 应抛出 DIDKeyTypeUnsupportedError"""
        # did:key with wrong multicodec prefix (secp256k1)
        with pytest.raises(DIDKeyTypeUnsupportedError):
            asyncio.run(resolver.resolve("did:key:zQ3shwNhBehPxCvMWKX4b3TLQ8WFjz5bYPuWdRhPDAStbNTN"))

    def test_resolve_agentnexus_roundtrip(self, resolver):
        """生成 → 解析 → 验证 往返测试"""
        # 生成
        agent_did, multikey = DIDGenerator.create_agentnexus("roundtrip-test")

        # 解析
        result = asyncio.run(resolver.resolve(agent_did.did))

        # 验证
        assert result.public_key == agent_did.verify_key.encode()

        # 验证 multikey 一致性
        decoded_multikey = crypto.decode_multikey_ed25519(multikey)
        assert decoded_multikey == result.public_key

    def test_resolve_multiple_did_methods(self, resolver):
        """测试解析多种 DID 方法"""
        # did:agentnexus
        agent_did, _ = DIDGenerator.create_agentnexus("multi-test")
        result1 = asyncio.run(resolver.resolve(agent_did.did))
        assert result1.method == "agentnexus"

        # did:key
        did_key = WG_TEST_VECTORS["did_key_ed25519"]["did"]
        result2 = asyncio.run(resolver.resolve(did_key))
        assert result2.method == "key"

        # 两者公钥应该不同（除非恰好相同）
        assert result1.did != result2.did


# ── 便捷函数测试 ───────────────────────────────────────────

class TestConvenienceFunctions:
    """便捷函数测试"""

    def test_create_agentnexus_did(self):
        """create_agentnexus_did() 便捷函数"""
        did, priv_hex, pub_hex = create_agentnexus_did("convenience-test")

        assert did.startswith("did:agentnexus:")
        assert len(priv_hex) == 64  # Ed25519 私钥 32 字节 hex
        assert len(pub_hex) == 64   # Ed25519 公钥 32 字节 hex

    def test_resolve_did_sync(self):
        """同步版本 DID 解析"""
        agent_did, _ = DIDGenerator.create_agentnexus("sync-test")
        result = resolve_did_sync(agent_did.did)

        assert isinstance(result, DIDResolutionResult)
        assert result.did == agent_did.did


# ── DIDResolutionResult 测试 ───────────────────────────────

class TestDIDResolutionResult:
    """DIDResolutionResult 测试"""

    def test_to_wg_format(self):
        """转换为 WG 格式"""
        result = DIDResolutionResult(
            did="did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
            method="key",
            public_key=bytes.fromhex("2e6fcce36701dc791488e0d0b1745cc1e33a4c1c9fcc41c63bd343dbbe0970e6"),
            metadata={"version": "1.0"},
        )

        wg_format = result.to_wg_format()

        assert "public_key" in wg_format
        assert "method" in wg_format
        assert "metadata" in wg_format
        assert len(wg_format["public_key"]) == 32
        assert wg_format["method"] == "key"

    def test_did_document_in_result(self):
        """DID Document 包含在结果中"""
        result = DIDResolutionResult(
            did="did:agentnexus:z6Mktest",
            method="agentnexus",
            public_key=bytes(32),
            did_document={"@context": "https://www.w3.org/ns/did/v1", "id": "did:agentnexus:z6Mktest"},
            metadata={},
        )

        assert result.did_document is not None
        assert result.did_document["id"] == result.did


# ── WG 接口合规测试 ────────────────────────────────────────

class TestWGCompliance:
    """WG DID Resolution v1.0 接口合规测试"""

    def test_wg_did_resolution_interface(self, resolver):
        """WG 规范要求的 resolve_did() 接口"""
        did = WG_TEST_VECTORS["did_key_ed25519"]["did"]
        result = asyncio.run(resolver.resolve_did(did))

        assert "public_key" in result
        assert "method" in result
        assert "metadata" in result
        assert isinstance(result["public_key"], bytes)
        assert len(result["public_key"]) == 32

    def test_wg_sender_id_derivation(self, resolver):
        """WG §4 sender_id 推导算法"""
        pk_bytes = bytes.fromhex(WG_TEST_VECTORS["sender_id_derivation"]["public_key_hex"])
        expected = WG_TEST_VECTORS["sender_id_derivation"]["expected_sender_id_hex"]

        digest = hashlib.sha256(pk_bytes).digest()
        sender_id = digest[:16].hex()

        assert sender_id == expected

    def test_error_codes(self, resolver):
        """WG §2.3 错误码合规"""
        with pytest.raises(DIDMethodUnsupportedError):
            asyncio.run(resolver.resolve_did("did:foo:bar"))

    def test_key_type_unsupported_error(self, resolver):
        """WG §2.3 key_type_unsupported 错误码"""
        secp256k1_did = "did:key:zQ3shwNhBehPxCvMWKX4b3TLQ8WFjz5bYPuWdRhPDAStbNTN"

        with pytest.raises(DIDKeyTypeUnsupportedError):
            asyncio.run(resolver.resolve(secp256k1_did))


# ── DID Document 验证 ──────────────────────────────────────

class TestDIDDocumentVerification:
    """DID Document 格式验证"""

    def test_did_document_has_required_context(self, resolver):
        """DID Document 必须包含 @context"""
        agent_did, _ = DIDGenerator.create_agentnexus("context-test")
        result = asyncio.run(resolver.resolve(agent_did.did))

        assert "@context" in result.did_document
        assert "https://www.w3.org/ns/did/v1" in result.did_document["@context"]

    def test_verification_method_format(self, resolver):
        """verificationMethod 格式验证"""
        agent_did, _ = DIDGenerator.create_agentnexus("vm-test")
        result = asyncio.run(resolver.resolve(agent_did.did))

        vm = result.did_document["verificationMethod"][0]

        assert "id" in vm
        assert "type" in vm
        assert "controller" in vm
        assert "publicKeyMultibase" in vm
        assert vm["type"] == "Ed25519VerificationKey2018"
        assert vm["id"].endswith("#agent-1")

    def test_key_agreement_derivation(self, resolver):
        """keyAgreement X25519 密钥推导验证"""
        agent_did, _ = DIDGenerator.create_agentnexus("ka-test")
        result = asyncio.run(resolver.resolve(agent_did.did))

        ka = result.did_document.get("keyAgreement", [])
        assert len(ka) > 0, "keyAgreement should be present"

        ka_key_multikey = ka[0]["publicKeyMultibase"]
        ka_key = crypto.decode_multikey_x25519(ka_key_multikey)

        # 验证 X25519 密钥是 32 字节
        assert len(ka_key) == 32

        # 验证 X25519 密钥与 Ed25519→X25519 推导结果一致
        expected_x = crypto.ed25519_pub_to_x25519(result.public_key)
        assert ka_key == expected_x

    def test_td06_did_document_has_services(self):
        """td06: DID Document 含 service 数组"""
        from agent_net.common.did import build_services_from_profile
        from nacl.signing import SigningKey as _SK
        sk = _SK.generate()
        pubkey = sk.verify_key.encode()
        did = "did:agentnexus:testdid123"
        profile = {"endpoints": {"p2p": "http://localhost:8765", "relay": "http://relay.example.com"}}
        services = build_services_from_profile(profile)
        doc = DIDResolver()._build_did_document(did, pubkey, services)
        assert "service" in doc
        types = [s["type"] for s in doc["service"]]
        assert "AgentRelay" in types
        assert "AgentEndpoint" in types


# ── 端点集成测试 ────────────────────────────────────────────

def test_td07_relay_resolve_endpoint(monkeypatch):
    """td07: Relay /resolve/{did} 返回 DID Doc"""
    import fakeredis.aioredis
    import agent_net.relay.server as srv
    importlib.reload(srv)

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(srv, "_create_redis", lambda: fake_redis)

    agent_did, _ = DIDGenerator.create_agentnexus("RelayTestAgent")
    did = agent_did.did
    pubkey_hex = agent_did.verify_key.encode().hex()

    asyncio.run(fake_redis.set(
        f"{srv._REG_PREFIX}{did}",
        json.dumps({"did": did, "pubkey_hex": pubkey_hex, "endpoints": {}})
    ))

    with TestClient(srv.app) as client:
        resp = client.get(f"/resolve/{did}")
    assert resp.status_code == 200
    data = resp.json()
    assert "didDocument" in data
    assert data["didDocument"]["id"] == did
    assert data["source"] == "local_registry"


def test_td08_daemon_resolve_endpoint(tmp_path, monkeypatch):
    """td08: Daemon /resolve/{did} 返回 DID Doc"""
    import agent_net.node.daemon as d
    import agent_net.storage as st

    monkeypatch.setattr(st, "DB_PATH", tmp_path / "test.db")
    importlib.reload(d)
    monkeypatch.setattr(d, "DAEMON_TOKEN_FILE", str(tmp_path / "token.txt"))
    monkeypatch.setattr(d, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(d, "NODE_CONFIG_FILE", str(tmp_path / "node_config.json"))

    with TestClient(d.app) as client:
        token = d._daemon_token
        resp = client.post(
            "/agents/register",
            json={"name": "DaemonResolveTest"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        did = resp.json()["did"]
        assert did.startswith("did:agentnexus:")

        resp2 = client.get(f"/resolve/{did}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert "didDocument" in data
        assert data["didDocument"]["id"] == did


def test_td11_register_creates_agentnexus_did(tmp_path, monkeypatch):
    """td11: 新注册 Agent 使用 did:agentnexus 格式"""
    import agent_net.node.daemon as d
    import agent_net.storage as st

    monkeypatch.setattr(st, "DB_PATH", tmp_path / "test.db")
    importlib.reload(d)
    monkeypatch.setattr(d, "DAEMON_TOKEN_FILE", str(tmp_path / "token.txt"))
    monkeypatch.setattr(d, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(d, "NODE_CONFIG_FILE", str(tmp_path / "node_config.json"))

    with TestClient(d.app) as client:
        token = d._daemon_token
        resp = client.post(
            "/agents/register",
            json={"name": "NewFormatAgent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        did = resp.json()["did"]
        assert did.startswith("did:agentnexus:"), f"Expected did:agentnexus:..., got {did}"


def test_td12_legacy_did_agent_still_works(tmp_path, monkeypatch):
    """td12: 旧 did:agent Agent 仍正常工作"""
    import agent_net.node.daemon as d
    import agent_net.storage as st

    monkeypatch.setattr(st, "DB_PATH", tmp_path / "test.db")
    importlib.reload(d)
    monkeypatch.setattr(d, "DAEMON_TOKEN_FILE", str(tmp_path / "token.txt"))
    monkeypatch.setattr(d, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(d, "NODE_CONFIG_FILE", str(tmp_path / "node_config.json"))

    with TestClient(d.app) as client:
        token = d._daemon_token
        resp = client.post(
            "/agents/register",
            json={"name": "LegacyFmtAgent", "did_format": "agent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        did = resp.json()["did"]
        assert did.startswith("did:agent:"), f"Expected did:agent:..., got {did}"

        resp2 = client.get(f"/agents/{did}")
        assert resp2.status_code == 200


# ── 运行所有测试的快速方法 ─────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
