"""
tests/test_v05.py
v0.5 新特性测试：会话管理 (session_id / reply_to) + 多方认证体系 (certifications)
编号前缀: tv（v0.5）
"""
import asyncio
import importlib
import json
import pytest
from pathlib import Path


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def daemon_client(tmp_path, monkeypatch):
    """独立 DB + Token 的 daemon TestClient"""
    import agent_net.storage as s
    import agent_net.node.daemon as d
    monkeypatch.setattr(s, "DB_PATH", tmp_path / "test.db")
    importlib.reload(d)
    token_file = str(tmp_path / "daemon_token.txt")
    import agent_net.node._auth as _auth; monkeypatch.setattr(_auth, "USER_TOKEN_FILE", Path(token_file))
    from fastapi.testclient import TestClient
    with TestClient(d.app) as client:
        yield client, d, token_file


def _token(token_file):
    with open(token_file) as f:
        return f.read().strip()


def _register(client, token_file, name="TestAgent", **kw):
    """注册 Agent 并返回 DID"""
    resp = client.post(
        "/agents/register",
        json={"name": name, **kw},
        headers={"Authorization": f"Bearer {_token(token_file)}"},
    )
    assert resp.status_code == 200
    return resp.json()["did"]


def _headers(token_file):
    return {"Authorization": f"Bearer {_token(token_file)}"}


def _send(client, token_file, payload):
    return client.post("/messages/send", json=payload, headers=_headers(token_file))


def _inbox(client, token_file, did, actor_did=None):
    actor = actor_did or did
    return client.get(f"/messages/inbox/{did}?actor_did={actor}", headers=_headers(token_file))


def _session(client, token_file, session_id, actor_did):
    return client.get(
        f"/messages/session/{session_id}?actor_did={actor_did}",
        headers=_headers(token_file),
    )


# ── 会话管理测试 ──────────────────────────────────────────────

def test_tv01_send_auto_generates_session_id(daemon_client):
    """不传 session_id 时，daemon 自动生成 sess_ 前缀的会话 ID"""
    client, d, tf = daemon_client
    did_a = _register(client, tf, "AgentA")
    did_b = _register(client, tf, "AgentB")
    resp = _send(client, tf, {
        "from_did": did_a, "to_did": did_b, "content": "hello",
    })
    data = resp.json()
    assert resp.status_code == 200
    assert data["session_id"].startswith("sess_")
    assert len(data["session_id"]) == 21  # "sess_" + 16 hex chars


def test_tv02_send_with_explicit_session_id(daemon_client):
    """传入 session_id 时，原样使用"""
    client, d, tf = daemon_client
    did_a = _register(client, tf, "AgentA")
    did_b = _register(client, tf, "AgentB")
    resp = _send(client, tf, {
        "from_did": did_a, "to_did": did_b, "content": "hello",
        "session_id": "sess_custom123",
    })
    data = resp.json()
    assert data["session_id"] == "sess_custom123"


def test_tv03_reply_to_in_inbox(daemon_client):
    """reply_to 在 inbox 中可见"""
    client, d, tf = daemon_client
    did_a = _register(client, tf, "AgentA")
    did_b = _register(client, tf, "AgentB")
    # 第一条消息
    r1 = _send(client, tf, {
        "from_did": did_a, "to_did": did_b, "content": "hello",
        "session_id": "sess_test",
    })
    # 查询 inbox 拿到 msg_id（离线存储）
    inbox = _inbox(client, tf, did_b).json()
    msg_id = inbox["messages"][0]["id"]
    # 回复
    _send(client, tf, {
        "from_did": did_b, "to_did": did_a, "content": "hi back",
        "session_id": "sess_test", "reply_to": msg_id,
    })
    inbox2 = _inbox(client, tf, did_a).json()
    assert inbox2["messages"][0]["reply_to"] == msg_id
    assert inbox2["messages"][0]["session_id"] == "sess_test"


def test_tv04_fetch_session(daemon_client):
    """按 session_id 查询完整会话历史"""
    client, d, tf = daemon_client
    did_a = _register(client, tf, "AgentA")
    did_b = _register(client, tf, "AgentB")
    sid = "sess_history"
    _send(client, tf, {
        "from_did": did_a, "to_did": did_b, "content": "msg1", "session_id": sid,
    })
    _send(client, tf, {
        "from_did": did_b, "to_did": did_a, "content": "msg2", "session_id": sid,
    })
    _send(client, tf, {
        "from_did": did_a, "to_did": did_b, "content": "msg3", "session_id": sid,
    })
    resp = _session(client, tf, sid, did_a)
    data = resp.json()
    assert data["session_id"] == sid
    assert data["count"] == 3
    contents = [m["content"] for m in data["messages"]]
    assert contents == ["msg1", "msg2", "msg3"]


def test_tv05_session_across_reply_chain(daemon_client):
    """A→B→A 回复链在同一 session 内"""
    client, d, tf = daemon_client
    did_a = _register(client, tf, "AgentA")
    did_b = _register(client, tf, "AgentB")
    # A sends to B
    r1 = _send(client, tf, {
        "from_did": did_a, "to_did": did_b, "content": "请翻译",
    }).json()
    sid = r1["session_id"]
    # B reads inbox
    inbox = _inbox(client, tf, did_b).json()
    msg_id = inbox["messages"][0]["id"]
    # B replies to A with same session
    _send(client, tf, {
        "from_did": did_b, "to_did": did_a, "content": "翻译完成",
        "session_id": sid, "reply_to": msg_id,
    })
    # Full session should have 2 messages
    session = _session(client, tf, sid, did_a).json()
    assert session["count"] == 2
    assert session["messages"][0]["from"] == did_a
    assert session["messages"][1]["from"] == did_b


# ── 认证体系测试 ──────────────────────────────────────────────

def test_tv06_certification_create_and_verify():
    """创建认证并验证签名"""
    from nacl.signing import SigningKey
    from agent_net.common.profile import create_certification, verify_certification
    issuer_sk = SigningKey.generate()
    cert = create_certification(
        target_did="did:agent:target001",
        issuer_did="did:agent:issuer001",
        issuer_signing_key=issuer_sk,
        claim="payment_verified",
        evidence="tx:0xabc123",
    )
    assert cert["claim"] == "payment_verified"
    assert cert["issuer"] == "did:agent:issuer001"
    assert verify_certification(cert, "did:agent:target001") is True


def test_tv07_certification_invalid_signature():
    """篡改的认证应验证失败"""
    from nacl.signing import SigningKey
    from nacl.exceptions import BadSignatureError
    from agent_net.common.profile import create_certification, verify_certification
    issuer_sk = SigningKey.generate()
    cert = create_certification(
        target_did="did:agent:target001",
        issuer_did="did:agent:issuer001",
        issuer_signing_key=issuer_sk,
        claim="payment_verified",
        evidence="tx:0xabc123",
    )
    # 篡改 claim
    cert["claim"] = "tampered_claim"
    with pytest.raises(BadSignatureError):
        verify_certification(cert, "did:agent:target001")


def test_tv08_certification_wrong_target_did():
    """用错误的 target_did 验证应失败"""
    from nacl.signing import SigningKey
    from nacl.exceptions import BadSignatureError
    from agent_net.common.profile import create_certification, verify_certification
    issuer_sk = SigningKey.generate()
    cert = create_certification(
        target_did="did:agent:target001",
        issuer_did="did:agent:issuer001",
        issuer_signing_key=issuer_sk,
        claim="service_quality_A",
    )
    with pytest.raises(BadSignatureError):
        verify_certification(cert, "did:agent:wrong_target")


def test_tv09_certify_via_daemon(daemon_client):
    """通过 daemon HTTP 端点签发认证"""
    client, d, tf = daemon_client
    token = _token(tf)
    # 注册 issuer 和 target
    issuer_did = _register(client, tf, "Issuer")
    target_did = _register(client, tf, "Target")
    # 签发认证
    resp = client.post(
        f"/agents/{target_did}/certify",
        json={"issuer_did": issuer_did, "claim": "verified_service", "evidence": "manual_review"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    cert = resp.json()["certification"]
    assert cert["claim"] == "verified_service"
    assert cert["issuer"] == issuer_did
    # 验证认证签名
    from agent_net.common.profile import verify_certification
    assert verify_certification(cert, target_did) is True


def test_tv10_certifications_in_profile(daemon_client):
    """认证出现在 NexusProfile 返回值中"""
    client, d, tf = daemon_client
    token = _token(tf)
    issuer_did = _register(client, tf, "CA_Agent")
    target_did = _register(client, tf, "ServiceBot")
    # 签发两条认证
    client.post(
        f"/agents/{target_did}/certify",
        json={"issuer_did": issuer_did, "claim": "payment_verified", "evidence": "tx:0x1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        f"/agents/{target_did}/certify",
        json={"issuer_did": issuer_did, "claim": "quality_A", "evidence": "reviews:50"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # 获取 profile
    profile = client.get(f"/agents/{target_did}/profile").json()
    assert "certifications" in profile
    assert len(profile["certifications"]) == 2
    claims = {c["claim"] for c in profile["certifications"]}
    assert claims == {"payment_verified", "quality_A"}


def test_tv11_get_certifications_endpoint(daemon_client):
    """专用端点获取认证列表"""
    client, d, tf = daemon_client
    token = _token(tf)
    issuer_did = _register(client, tf, "Issuer")
    target_did = _register(client, tf, "Target")
    client.post(
        f"/agents/{target_did}/certify",
        json={"issuer_did": issuer_did, "claim": "trusted"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.get(f"/agents/{target_did}/certifications")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["certifications"][0]["claim"] == "trusted"


def test_tv12_nexus_profile_certifications_not_in_content_signature():
    """certifications 不影响 content 签名——添加认证后 verify() 仍通过"""
    from nacl.signing import SigningKey
    from agent_net.common.profile import NexusProfile, create_certification
    sk = SigningKey.generate()
    profile = NexusProfile.create(
        did="did:agent:test001", signing_key=sk,
        name="TestBot", description="test",
    )
    # 验签通过
    assert profile.verify() is True
    # 追加认证
    issuer_sk = SigningKey.generate()
    cert = create_certification(
        target_did="did:agent:test001",
        issuer_did="did:agent:issuer001",
        issuer_signing_key=issuer_sk,
        claim="verified",
    )
    profile.add_certification(cert)
    # content 签名仍然有效
    assert profile.verify() is True
    # to_dict 包含 certifications
    d = profile.to_dict()
    assert len(d["certifications"]) == 1
