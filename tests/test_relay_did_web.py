"""
测试 Relay did:web 支持

测试范围:
- 本地 Relay 暴露 /.well-known/did.json 端点
- DID Document 格式正确
- 身份持久化到 data/relay_identity.json
- 重启后身份保持一致
- 线上公网 Relay (relay.agentnexus.top) 测试
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import fakeredis
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def tmp_data_dir():
    """创建临时 data 目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_constants(tmp_data_dir):
    """Mock constants 中的路径"""
    with patch("agent_net.common.constants.DATA_DIR", tmp_data_dir), \
         patch("agent_net.common.constants.RELAY_IDENTITY_FILE", os.path.join(tmp_data_dir, "relay_identity.json")):
        yield tmp_data_dir


@pytest.fixture
def relay_client(mock_constants):
    """创建 Relay TestClient，注入 fakeredis"""
    # 重新导入模块以应用 mock
    import importlib
    from agent_net.relay import server
    importlib.reload(server)

    # 注入 fakeredis（异步版本）
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    with patch.object(server, "_create_redis", return_value=fake_redis):
        # 初始化身份
        server.init_relay_identity()

        with TestClient(server.app) as client:
            yield client, server


# ── 本地测试 ───────────────────────────────────────────────────

def test_relay_did_json_endpoint(relay_client):
    """Relay 暴露 /.well-known/did.json 端点"""
    client, server = relay_client
    resp = client.get("/.well-known/did.json")
    assert resp.status_code == 200
    doc = resp.json()

    # 验证 DID Document 基本结构
    assert "id" in doc
    assert doc["id"].startswith("did:web:")
    assert "verificationMethod" in doc
    assert len(doc["verificationMethod"]) == 1
    assert doc["verificationMethod"][0]["type"] == "Ed25519VerificationKey2018"


def test_relay_did_document_format(relay_client):
    """DID Document 格式正确"""
    client, server = relay_client
    resp = client.get("/.well-known/did.json")
    doc = resp.json()

    did = doc["id"]

    # 验证 @context
    assert "@context" in doc
    assert "https://www.w3.org/ns/did/v1" in doc["@context"]

    # 验证 verificationMethod
    vm = doc["verificationMethod"][0]
    assert vm["id"] == f"{did}#relay-key-1"
    assert vm["controller"] == did
    assert "publicKeyMultibase" in vm
    assert vm["publicKeyMultibase"].startswith("z")

    # 验证 authentication 和 assertionMethod
    assert doc["authentication"] == [f"{did}#relay-key-1"]
    assert doc["assertionMethod"] == [f"{did}#relay-key-1"]

    # 验证 service
    assert "service" in doc
    assert len(doc["service"]) == 1
    service = doc["service"][0]
    assert service["type"] == "AgentRelayService"
    assert "serviceEndpoint" in service
    assert service["serviceEndpoint"].startswith("https://")


def test_relay_did_document_key_agreement(relay_client):
    """DID Document 包含 X25519 keyAgreement"""
    client, server = relay_client
    resp = client.get("/.well-known/did.json")
    doc = resp.json()

    # keyAgreement 应该存在（Ed25519→X25519 推导成功）
    assert "keyAgreement" in doc
    ka = doc["keyAgreement"][0]
    assert ka["type"] == "X25519KeyAgreementKey2019"
    assert ka["publicKeyMultibase"].startswith("z")


def test_relay_identity_persisted(mock_constants):
    """身份持久化到 data/relay_identity.json"""
    from agent_net.relay import server
    import importlib
    importlib.reload(server)

    # 初始化身份
    server.init_relay_identity()

    identity_file = Path(mock_constants) / "relay_identity.json"
    assert identity_file.exists()

    # 验证文件内容
    data = json.loads(identity_file.read_text(encoding="utf-8"))
    assert "private_key_hex" in data
    assert "public_key_hex" in data
    assert "did" in data
    assert "created_at" in data
    assert data["did"].startswith("did:web:")


def test_relay_identity_consistent_after_reload(mock_constants):
    """重启后身份保持一致"""
    from agent_net.relay import server
    import importlib

    # 第一次初始化
    importlib.reload(server)
    server.init_relay_identity()
    did_1 = server._relay_did
    pubkey_1 = server._relay_signing_key.verify_key.encode().hex()

    # 重新加载模块（模拟重启）
    importlib.reload(server)
    server.init_relay_identity()
    did_2 = server._relay_did
    pubkey_2 = server._relay_signing_key.verify_key.encode().hex()

    # DID 和公钥应该一致
    assert did_1 == did_2
    assert pubkey_1 == pubkey_2


def test_relay_health_includes_did(relay_client):
    """health 端点包含 relay_did 信息"""
    client, server = relay_client
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "relay_did" in data
    assert data["relay_did"].startswith("did:web:")
    assert "relay_host" in data


def test_relay_did_matches_host_env(tmp_data_dir):
    """RELAY_HOST 环境变量影响 DID"""
    import os

    # 设置环境变量
    with patch.dict(os.environ, {"RELAY_HOST": "custom.relay.example.com"}):
        # 重新加载 constants（读取新环境变量）
        from agent_net.common import constants
        import importlib
        importlib.reload(constants)

        # 重新加载 server（使用新的 constants）
        from agent_net.relay import server
        importlib.reload(server)

        # 使用临时文件路径
        identity_file = Path(tmp_data_dir) / "relay_identity.json"
        with patch.object(server, "RELAY_IDENTITY_FILE", str(identity_file)):
            server.init_relay_identity()
            did = server._relay_did
            assert did == "did:web:custom.relay.example.com"


# ── 公网 Relay 测试 ───────────────────────────────────────────

@pytest.mark.skipif(
    os.environ.get("SKIP_ONLINE_TESTS", "1") == "1",
    reason="跳过线上测试，设置 SKIP_ONLINE_TESTS=0 启用"
)
def test_public_relay_did_json():
    """线上公网 Relay (relay.agentnexus.top) 暴露 DID Document"""
    import httpx

    resp = httpx.get(
        "https://relay.agentnexus.top/.well-known/did.json",
        timeout=10.0
    )
    assert resp.status_code == 200
    doc = resp.json()

    # 验证基本结构
    assert doc["id"] == "did:web:relay.agentnexus.top"
    assert "verificationMethod" in doc
    assert len(doc["verificationMethod"]) == 1
    assert doc["verificationMethod"][0]["type"] == "Ed25519VerificationKey2018"


@pytest.mark.skipif(
    os.environ.get("SKIP_ONLINE_TESTS", "1") == "1",
    reason="跳过线上测试，设置 SKIP_ONLINE_TESTS=0 启用"
)
def test_public_relay_did_resolvable():
    """线上 Relay 的 did:web 可被 DIDResolver 解析"""
    import asyncio
    from agent_net.common.did import DIDResolver

    async def resolve():
        resolver = DIDResolver()
        result = await resolver.resolve("did:web:relay.agentnexus.top")
        assert result.method == "web"
        assert len(result.public_key) == 32
        assert result.did_document is not None
        assert result.did_document["id"] == "did:web:relay.agentnexus.top"

    asyncio.run(resolve())


@pytest.mark.skipif(
    os.environ.get("SKIP_ONLINE_TESTS", "1") == "1",
    reason="跳过线上测试，设置 SKIP_ONLINE_TESTS=0 启用"
)
def test_public_relay_health_has_did():
    """线上 Relay 的 health 端点包含 relay_did"""
    import httpx

    resp = httpx.get(
        "https://relay.agentnexus.top/health",
        timeout=10.0
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "relay_did" in data
    assert data["relay_did"] == "did:web:relay.agentnexus.top"