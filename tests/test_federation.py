"""
tests/test_federation.py
联邦 Relay + NexusProfile 测试用例 (tf01–tf07)
"""
import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, patch

from nacl.signing import SigningKey
from nacl.exceptions import BadSignatureError
from fastapi.testclient import TestClient

from agent_net.common.did import DIDGenerator
from agent_net.common.profile import NexusProfile


# ═══════════════════════════════════════════════════════════════
# NexusProfile 测试 (tf01–tf03)
# ═══════════════════════════════════════════════════════════════

def test_tf01_nexus_profile_create_and_sign():
    """NexusProfile 创建、签名、to_dict/from_dict 往返"""
    agent = DIDGenerator.create_new("TestBot")
    profile = NexusProfile.create(
        did=agent.did,
        signing_key=agent.private_key,
        name="TestBot",
        description="单元测试 Agent",
        tags=["test", "unit"],
        relay="http://localhost:9000",
        direct="http://1.2.3.4:8765",
    )

    # 基本属性
    assert profile.did == agent.did
    assert profile.name == "TestBot"
    assert profile.tags == ["test", "unit"]
    assert profile.relay_endpoint == "http://localhost:9000"
    assert profile.direct_endpoint == "http://1.2.3.4:8765"
    assert profile.signature != ""

    # header 包含正确字段
    assert profile.header["version"] == "1.0"
    assert "pubkey" in profile.header

    # to_dict / from_dict 往返
    d = profile.to_dict()
    assert d["signature"] == profile.signature
    restored = NexusProfile.from_dict(d)
    assert restored.did == profile.did
    assert restored.content == profile.content
    assert restored.signature == profile.signature


def test_tf02_nexus_profile_verify_success():
    """正确签名验证通过"""
    agent = DIDGenerator.create_new("VerifyBot")
    profile = NexusProfile.create(
        did=agent.did,
        signing_key=agent.private_key,
        name="VerifyBot",
        tags=["verify"],
        relay="http://localhost:9000",
    )

    # 验签成功
    assert profile.verify() is True

    # 序列化后依然可验签
    restored = NexusProfile.from_dict(profile.to_dict())
    assert restored.verify() is True


def test_tf03_nexus_profile_tamper_detected():
    """修改 content 后验签失败（BadSignatureError）"""
    agent = DIDGenerator.create_new("TamperBot")
    profile = NexusProfile.create(
        did=agent.did,
        signing_key=agent.private_key,
        name="TamperBot",
        description="原始描述",
        tags=["original"],
        relay="http://localhost:9000",
    )

    # 正常验签
    assert profile.verify() is True

    # 篡改 content
    profile.content["description"] = "篡改后的描述"

    # 验签应抛 BadSignatureError
    with pytest.raises(BadSignatureError):
        profile.verify()


def test_tf03b_nexus_profile_no_signature_raises():
    """未签名的 NexusProfile.verify() 抛 ValueError"""
    agent = DIDGenerator.create_new("NoSigBot")
    profile = NexusProfile(
        header={"did": agent.did, "pubkey": "aa", "version": "1.0"},
        content={"name": "test", "description": "", "tags": [], "endpoints": {}},
        signature="",
    )
    with pytest.raises(ValueError, match="no signature"):
        profile.verify()


# ═══════════════════════════════════════════════════════════════
# Relay 联邦功能测试 (tf04–tf07)  ── 使用 TestClient（同步）
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def relay_client(monkeypatch):
    """每次测试用全新的 relay app 实例（注入 fakeredis，隔离状态）"""
    import importlib
    import agent_net.relay.server as srv
    importlib.reload(srv)

    import fakeredis.aioredis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(srv, "_create_redis", lambda: fake)

    with TestClient(srv.app) as client:
        yield client, srv


def test_tf04_relay_federation_join(relay_client):
    """POST /federation/join 注册后 /federation/peers 可见"""
    client, srv = relay_client
    peer_url = "http://192.168.1.200:9000"

    resp = client.post("/federation/join", json={"relay_url": peer_url})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["relay_url"] == peer_url

    # /federation/peers 应包含该 URL
    resp2 = client.get("/federation/peers")
    assert resp2.status_code == 200
    assert peer_url in resp2.json()["peers"]


def test_tf05_federation_announce_and_lookup(relay_client):
    """
    /federation/announce 写入 peer_directory，
    /lookup miss 后通过 _proxy_lookup 代理返回结果
    """
    client, srv = relay_client

    did = "did:agent:fedtest0000000001"
    peer_relay = "http://192.168.1.200:9000"

    # 公告一个公开 Agent 到 peer_directory
    resp = client.post("/federation/announce", json={
        "did": did,
        "relay_url": peer_relay,
        "profile": {"header": {"did": did}, "content": {"name": "RemoteBot"}},
    })
    assert resp.status_code == 200

    # peer_directory 已有记录
    resp2 = client.get("/federation/directory")
    assert any(e["did"] == did for e in resp2.json()["entries"])

    # /lookup miss 本地，代理查 peer relay（mock _proxy_lookup 避免 aiohttp 复杂性）
    fake_response_data = {
        "did": did,
        "endpoint": "http://192.168.1.20:8765",
        "relay": peer_relay,
        "public_ip": "192.168.1.20",
        "public_port": 8765,
        "updated_at": time.time(),
        "online": True,
    }

    async def mock_proxy(peer_relay_url, lookup_did):
        assert lookup_did == did
        assert peer_relay_url == peer_relay
        return fake_response_data

    with patch("agent_net.relay.server._proxy_lookup", side_effect=mock_proxy):
        resp3 = client.get(f"/lookup/{did}")

    assert resp3.status_code == 200
    body = resp3.json()
    assert body["did"] == did
    assert body["endpoint"] == "http://192.168.1.20:8765"
    assert body.get("_via_relay") == peer_relay


def test_tf06_lookup_not_in_directory_returns_404(relay_client):
    """DID 既不在本地也不在 peer_directory → 404"""
    client, srv = relay_client
    resp = client.get("/lookup/did:agent:nonexistent0000001")
    assert resp.status_code == 404


def test_tf07_health_shows_federation_counters(relay_client):
    """health 接口包含 peers 和 peer_directory 计数"""
    client, srv = relay_client

    # 加入一个 peer
    client.post("/federation/join", json={"relay_url": "http://seed.example.com:9000"})
    # 公告一个 Agent
    client.post("/federation/announce", json={
        "did": "did:agent:healthtest000001",
        "relay_url": "http://seed.example.com:9000",
    })

    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["peers"] >= 1
    assert data["peer_directory"] >= 1


# ═══════════════════════════════════════════════════════════════
# 私钥持久化测试 (tf08)
# ═══════════════════════════════════════════════════════════════

def test_tf08_private_key_persistence(tmp_path, monkeypatch):
    """store_private_key / get_private_key 往返"""
    import agent_net.storage as s
    monkeypatch.setattr(s, "DB_PATH", tmp_path / "test.db")

    async def _run():
        await s.init_db()
        agent = DIDGenerator.create_new("KeyBot")
        from agent_net.common.did import AgentProfile
        profile = AgentProfile(id=agent.did, name="KeyBot")
        from nacl.encoding import HexEncoder
        pk_hex = agent.private_key.encode(HexEncoder).decode()
        await s.register_agent(agent.did, profile.to_dict(), private_key_hex=pk_hex)

        retrieved = await s.get_private_key(agent.did)
        assert retrieved == pk_hex

        # 用取回的私钥重建 SigningKey 并签名验证
        restored_key = SigningKey(bytes.fromhex(retrieved))
        profile2 = NexusProfile.create(
            did=agent.did,
            signing_key=restored_key,
            name="KeyBot",
            tags=["key-test"],
            relay="http://localhost:9000",
        )
        assert profile2.verify() is True

    asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════
# schema_version + Token 鉴权 + PATCH 名片测试 (tf09–tf12)
# ═══════════════════════════════════════════════════════════════

def test_tf09_schema_version_in_signed_content():
    """schema_version 和 updated_at 包含在 content 中（已签名，防篡改）"""
    agent = DIDGenerator.create_new("SchemaBot")
    profile = NexusProfile.create(
        did=agent.did,
        signing_key=agent.private_key,
        name="SchemaBot",
        relay="http://localhost:9000",
    )
    # schema_version 必须在 content 中
    assert "schema_version" in profile.content
    assert profile.schema_version == "1.0"
    # updated_at 也在 content 中
    assert "updated_at" in profile.content
    assert profile.updated_at > 0
    # 签名覆盖了含 schema_version 的 content → 验签必须通过
    assert profile.verify() is True
    # 篡改 schema_version 应令签名失效
    from nacl.exceptions import BadSignatureError
    profile.content["schema_version"] = "9.9"
    with pytest.raises(BadSignatureError):
        profile.verify()


@pytest.fixture
def daemon_client(tmp_path, monkeypatch):
    """使用独立 DB 和 Token 文件的 daemon app TestClient"""
    import importlib
    import agent_net.storage as s
    import agent_net.node.daemon as d

    # 1. 先 patch storage DB 路径
    monkeypatch.setattr(s, "DB_PATH", tmp_path / "test.db")

    # 2. 重新加载 daemon，使其内部状态（全局变量）重置
    importlib.reload(d)

    # 3. patch daemon 模块级名称，使 token 写入 tmp_path
    token_file = str(tmp_path / "daemon_token.txt")
    monkeypatch.setattr(d, "DAEMON_TOKEN_FILE", token_file)
    monkeypatch.setattr(d, "DATA_DIR", str(tmp_path))

    # 4. 用 context manager 确保 lifespan（init_db + _init_daemon_token）运行
    from fastapi.testclient import TestClient
    with TestClient(d.app) as client:
        yield client, d, token_file


def test_tf10_write_endpoint_requires_token(daemon_client):
    """写接口无 Token 时返回 401"""
    client, d, token_file = daemon_client
    resp = client.post("/agents/register", json={"name": "UnAuthBot"})
    assert resp.status_code == 401


def test_tf11_write_endpoint_accepts_valid_token(daemon_client):
    """写接口携带有效 Token 时返回 200"""
    client, d, token_file = daemon_client
    # 读取 daemon 生成的 token
    with open(token_file, "r") as f:
        token = f.read().strip()
    resp = client.post(
        "/agents/register",
        json={"name": "AuthBot", "capabilities": ["test"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "did" in data
    assert data.get("nexus_profile") is not None
    # 验签 nexus_profile
    np_data = data["nexus_profile"]
    restored = NexusProfile.from_dict(np_data)
    assert restored.verify() is True


def test_tf12_patch_card_updates_and_resigns(daemon_client):
    """PATCH /agents/{did}/card 更新字段并重新签名"""
    client, d, token_file = daemon_client
    with open(token_file, "r") as f:
        token = f.read().strip()
    headers = {"Authorization": f"Bearer {token}"}

    # 先注册
    resp = client.post(
        "/agents/register",
        json={"name": "CardBot", "description": "原始描述", "tags": ["original"]},
        headers=headers,
    )
    assert resp.status_code == 200
    did = resp.json()["did"]
    old_sig = resp.json()["nexus_profile"]["signature"]

    # PATCH 更新名片
    resp2 = client.patch(
        f"/agents/{did}/card",
        json={"description": "更新后的描述", "tags": ["updated", "v2"]},
        headers=headers,
    )
    assert resp2.status_code == 200
    new_card = resp2.json()
    # 签名应已更新
    assert new_card["signature"] != old_sig
    # 新签名可验签
    restored = NexusProfile.from_dict(new_card)
    assert restored.verify() is True
    # content 字段已更新
    assert restored.content["description"] == "更新后的描述"
    assert restored.tags == ["updated", "v2"]
