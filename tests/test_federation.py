"""
tests/test_federation.py
联邦 Relay + NexusProfile 测试用例 (tf01–tf22, tr01–tr02)
"""
import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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

    # 3. patch daemon 模块级名称，使 token、配置均写入 tmp_path（完全隔离）
    token_file = str(tmp_path / "daemon_token.txt")
    monkeypatch.setattr(d, "DAEMON_TOKEN_FILE", token_file)
    monkeypatch.setattr(d, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(d, "NODE_CONFIG_FILE", str(tmp_path / "node_config.json"))

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


# ═══════════════════════════════════════════════════════════════
# 新增测试 tf13–tf22：Relay 容错 / 签名同步 / Token / 联邦边界
# ═══════════════════════════════════════════════════════════════

def test_tf13_local_relay_unreachable_register_succeeds(daemon_client, monkeypatch):
    """本地 Relay 不可达时，register 仍返回 200，agent 写入本地 DB（announce 静默失败）"""
    client, d, token_file = daemon_client
    with open(token_file) as f:
        token = f.read().strip()

    # 替换 aiohttp.ClientSession，使所有 POST 立即抛 ConnectionRefusedError
    class _FailSession:
        def post(self, *args, **kwargs):
            raise ConnectionRefusedError("simulated relay down")
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    monkeypatch.setattr(d.aiohttp, "ClientSession", _FailSession)

    resp = client.post(
        "/agents/register",
        json={"name": "RelayDownAgent", "capabilities": ["ping"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "did" in data

    # agent 已写入本地 DB
    local = client.get("/agents/local")
    assert any(a["did"] == data["did"] for a in local.json()["agents"])


def test_tf14_seed_relay_unreachable_announce_silent(daemon_client, monkeypatch):
    """is_public=True 时 federation announce 向不可达种子站发送，注册不受影响"""
    client, d, token_file = daemon_client
    with open(token_file) as f:
        token = f.read().strip()

    # 写入含不可达种子站的节点配置
    with open(d.NODE_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "local_relay": "http://localhost:9000",
            "seed_relays": ["http://unreachable-seed.invalid:9999"],
        }, f)

    # aiohttp 全部失败
    class _FailSession:
        def post(self, *args, **kwargs):
            raise ConnectionRefusedError("no route to host")
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    monkeypatch.setattr(d.aiohttp, "ClientSession", _FailSession)

    resp = client.post(
        "/agents/register",
        json={"name": "PublicBot", "is_public": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_public"] is True
    assert "did" in resp.json()


def test_tf15_patch_card_old_sig_invalid_on_new_content(daemon_client):
    """PATCH card 后，旧签名无法验证新内容（签名严格绑定内容）"""
    client, d, token_file = daemon_client
    with open(token_file) as f:
        token = f.read().strip()
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/agents/register",
        json={"name": "SigBoundBot", "description": "original"},
        headers=headers,
    )
    did = resp.json()["did"]
    old_np = NexusProfile.from_dict(resp.json()["nexus_profile"])
    old_sig = old_np.signature

    resp2 = client.patch(
        f"/agents/{did}/card",
        json={"description": "modified after patch"},
        headers=headers,
    )
    assert resp2.status_code == 200
    new_np = NexusProfile.from_dict(resp2.json())

    # 新签名与旧签名不同
    assert new_np.signature != old_sig
    # 新签名可验证新内容
    assert new_np.verify() is True

    # 用旧签名 + 新内容拼成混合 profile → 验签应失败
    from nacl.exceptions import BadSignatureError
    franken = NexusProfile(
        header=new_np.header,
        content=new_np.content,
        signature=old_sig,
    )
    with pytest.raises(BadSignatureError):
        franken.verify()


def test_tf16_patch_card_updated_at_advances(daemon_client):
    """PATCH card 后 updated_at 不小于注册时的值，且新签名仍有效"""
    client, d, token_file = daemon_client
    with open(token_file) as f:
        token = f.read().strip()
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/agents/register",
        json={"name": "TimeBot"},
        headers=headers,
    )
    did = resp.json()["did"]
    old_at = resp.json()["nexus_profile"]["content"]["updated_at"]

    time.sleep(0.05)  # 确保时钟推进

    resp2 = client.patch(
        f"/agents/{did}/card",
        json={"description": "updated description"},
        headers=headers,
    )
    assert resp2.status_code == 200
    new_np = NexusProfile.from_dict(resp2.json())
    assert new_np.content["updated_at"] >= old_at
    assert new_np.verify() is True


def test_tf17_duplicate_announce_updates_endpoint(relay_client):
    """同一 DID 两次 /announce 不产生重复条目，lookup 返回最新 endpoint"""
    client, srv = relay_client
    did = "did:agent:duptest0000000001"

    client.post("/announce", json={"did": did, "endpoint": "http://1.2.3.4:8765"})
    client.post("/announce", json={"did": did, "endpoint": "http://5.6.7.8:9000"})

    health = client.get("/health").json()
    assert health["registered"] == 1

    lookup = client.get(f"/lookup/{did}").json()
    assert lookup["endpoint"] == "http://5.6.7.8:9000"


def test_tf18_federation_proxy_peer_returns_404(relay_client):
    """peer relay 代理查询返回 None（peer 无此 DID）→ /lookup 最终返回 404"""
    client, srv = relay_client
    did = "did:agent:proxytest000000001"
    peer_relay = "http://peer-relay.example.com:9000"

    client.post("/federation/announce", json={"did": did, "relay_url": peer_relay})

    async def mock_proxy(peer_relay_url, lookup_did):
        return None  # peer 报告未找到

    with patch("agent_net.relay.server._proxy_lookup", side_effect=mock_proxy):
        resp = client.get(f"/lookup/{did}")

    assert resp.status_code == 404


def test_tf19_proxy_lookup_exception_returns_none():
    """_proxy_lookup 内部 aiohttp 超时/异常时返回 None，不向外抛出"""
    import importlib
    import agent_net.relay.server as srv
    importlib.reload(srv)

    async def _run():
        with patch("agent_net.relay.server.aiohttp.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            # 模拟 GET 请求超时
            mock_get = MagicMock()
            mock_get.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_get.__aexit__ = AsyncMock(return_value=None)
            mock_session.get = MagicMock(return_value=mock_get)

            result = await srv._proxy_lookup("http://fake-relay:9000", "did:agent:test")
            assert result is None

    asyncio.run(_run())


def test_tf20_malformed_token_returns_401(daemon_client):
    """Authorization 头格式错误或 token 值错误时，写接口返回 401"""
    client, d, token_file = daemon_client
    with open(token_file) as f:
        valid_token = f.read().strip()

    bad_headers = [
        {},                                                   # 无头
        {"Authorization": "Token " + valid_token},           # 错误 scheme
        {"Authorization": "Bearer"},                         # 缺少 token 值
        {"Authorization": "Bearer "},                        # 空 token
        {"Authorization": "Bearer wrong-token-deadbeef"},    # 错误 token
    ]
    for hdrs in bad_headers:
        resp = client.post("/agents/register", json={"name": "X"}, headers=hdrs)
        assert resp.status_code == 401, \
            f"Expected 401 for {hdrs!r}, got {resp.status_code}"


def test_tf21_relay_add_triggers_federation_join(daemon_client, monkeypatch):
    """POST /node/config/relay/add 向新种子站发送 /federation/join 请求"""
    client, d, token_file = daemon_client
    with open(token_file) as f:
        token = f.read().strip()

    posted_urls = []

    class _SpySession:
        def post(self, url, **kwargs):
            posted_urls.append(url)
            async def _ok():
                class _R:
                    status = 200
                return _R()
            return _ok()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    monkeypatch.setattr(d.aiohttp, "ClientSession", _SpySession)

    resp = client.post(
        "/node/config/relay/add",
        json={"url": "http://new-seed.example.com:9000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert any("/federation/join" in url for url in posted_urls), \
        f"Expected /federation/join call, posted to: {posted_urls}"


def test_tf22_tamper_header_pubkey_fails_verify():
    """header.pubkey 替换为另一个公钥 → verify() 抛 BadSignatureError"""
    from nacl.encoding import HexEncoder
    from nacl.exceptions import BadSignatureError

    agent = DIDGenerator.create_new("PubkeyBot")
    other = DIDGenerator.create_new("OtherBot")

    profile = NexusProfile.create(
        did=agent.did,
        signing_key=agent.private_key,
        name="PubkeyBot",
        relay="http://localhost:9000",
    )
    assert profile.verify() is True

    # 换成另一个 agent 的公钥
    other_pubkey_hex = other.verify_key.encode(HexEncoder).decode()
    profile.header["pubkey"] = other_pubkey_hex

    with pytest.raises(BadSignatureError):
        profile.verify()


# ═══════════════════════════════════════════════════════════════
# Relay 边界行为测试 (tr01–tr02)
# ═══════════════════════════════════════════════════════════════

def test_tr01_duplicate_federation_join_idempotent(relay_client):
    """同一 relay URL 多次 /federation/join → peers 集合中只有 1 条"""
    client, srv = relay_client
    peer = "http://peer.example.com:9000"

    for _ in range(3):
        r = client.post("/federation/join", json={"relay_url": peer})
        assert r.status_code == 200

    resp = client.get("/federation/peers")
    peers = resp.json()["peers"]
    assert peers.count(peer) == 1
    assert resp.json()["count"] == 1


def test_tr02_duplicate_announce_directory_updated(relay_client):
    """同一 DID 两次 /federation/announce → directory 只有 1 条，内容为最新"""
    client, srv = relay_client
    did = "did:agent:dirtest0000000001"

    client.post("/federation/announce", json={
        "did": did, "relay_url": "http://old-relay.example.com:9000",
    })
    client.post("/federation/announce", json={
        "did": did, "relay_url": "http://new-relay.example.com:9000",
    })

    resp = client.get("/federation/directory")
    data = resp.json()
    assert data["count"] == 1
    assert data["entries"][0]["relay_url"] == "http://new-relay.example.com:9000"
