"""
密钥导出/导入测试 (tk01-tk05)

测试 keystore.py 的加密导出/解密导入功能。
"""
import asyncio
import importlib
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def daemon_client(tmp_path, monkeypatch):
    """独立 DB + Token 的 daemon TestClient"""
    import agent_net.storage as st
    import agent_net.node.daemon as d
    monkeypatch.setattr(st, "DB_PATH", tmp_path / "test.db")
    importlib.reload(d)
    import agent_net.node._auth as _auth; monkeypatch.setattr(_auth, "USER_TOKEN_FILE", tmp_path / "token.txt")
    with TestClient(d.app) as client:
        yield client, d


def _token(d):
    from agent_net.node._auth import get_token
    return get_token()


# ── tk01: 导出→导入往返完整 ──────────────────────────────────

def test_tk01_export_import_roundtrip():
    """tk01: 导出→导入身份完整"""
    from nacl.signing import SigningKey
    from agent_net.common.keystore import export_agent, import_agent

    sk = SigningKey.generate()
    did = "did:agentnexus:zTestRoundtrip"
    private_key_hex = sk.encode().hex()
    profile = {"id": did, "name": "TestAgent", "public_key_hex": sk.verify_key.encode().hex()}
    certs = [{"issuer": "did:agent:abc", "claim": "test_claim", "issued_at": 1234567890.0}]
    password = "super_secret_password_123"

    exported = export_agent(did, private_key_hex, profile, password, certifications=certs)
    assert isinstance(exported, bytes)
    assert len(exported) > 100

    payload = import_agent(exported, password)
    assert payload["did"] == did
    assert payload["private_key_hex"] == private_key_hex
    assert payload["profile"] == profile
    assert payload["certifications"] == certs


# ── tk02: 错误密码解密失败 ────────────────────────────────────

def test_tk02_wrong_password_fails():
    """tk02: 错误密码解密失败"""
    from nacl.signing import SigningKey
    from agent_net.common.keystore import export_agent, import_agent

    sk = SigningKey.generate()
    did = "did:agentnexus:zTestWrongPass"
    exported = export_agent(did, sk.encode().hex(), {}, "correct_password")

    with pytest.raises(ValueError, match="Decryption failed"):
        import_agent(exported, "wrong_password")


# ── tk03: Daemon HTTP 导出端点 ────────────────────────────────

def test_tk03_export_via_daemon(daemon_client):
    """tk03: Daemon HTTP 导出端点"""
    client, d = daemon_client
    token = _token(d)

    resp = client.post(
        "/agents/register",
        json={"name": "ExportTestAgent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    did = resp.json()["did"]

    resp2 = client.get(
        f"/agents/{did}/export",
        params={"password": "test_export_pass"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert "data" in data

    exported_json = json.loads(data["data"])
    assert exported_json["version"] == "1.0"
    assert "salt" in exported_json
    assert "encrypted" in exported_json


# ── tk04: Daemon HTTP 导入端点 ────────────────────────────────

def test_tk04_import_via_daemon(daemon_client):
    """tk04: Daemon HTTP 导入端点"""
    client, d = daemon_client
    token = _token(d)
    password = "import_test_pass_456"

    resp = client.post(
        "/agents/register",
        json={"name": "ImportTestAgent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    did = resp.json()["did"]

    resp2 = client.get(
        f"/agents/{did}/export",
        params={"password": password},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    bundle_data = resp2.json()["data"]

    resp3 = client.post(
        "/agents/import",
        json={"data": bundle_data, "password": password},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 200
    result = resp3.json()
    assert result["status"] == "ok"
    assert result["did"] == did

    resp4 = client.get(f"/agents/{did}")
    assert resp4.status_code == 200


# ── tk05: 导出保留认证 ────────────────────────────────────────

def test_tk05_export_preserves_certifications(daemon_client):
    """tk05: 认证一并导出"""
    client, d = daemon_client
    token = _token(d)
    password = "cert_export_pass_789"

    resp = client.post(
        "/agents/register",
        json={"name": "CertTarget"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    target_did = resp.json()["did"]

    resp2 = client.post(
        "/agents/register",
        json={"name": "CertIssuer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    issuer_did = resp2.json()["did"]

    resp3 = client.post(
        f"/agents/{target_did}/certify",
        json={"issuer_did": issuer_did, "claim": "payment_verified", "evidence": "tx:abc123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp3.status_code == 200

    resp4 = client.get(f"/agents/{target_did}/certifications")
    certs_before = resp4.json()["certifications"]
    assert len(certs_before) >= 1

    resp5 = client.get(
        f"/agents/{target_did}/export",
        params={"password": password},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp5.status_code == 200
    bundle_data = resp5.json()["data"]

    from agent_net.common.keystore import import_agent
    payload = import_agent(bundle_data.encode(), password)
    assert len(payload["certifications"]) >= 1
    assert any(c["claim"] == "payment_verified" for c in payload["certifications"])
