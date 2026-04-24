"""
鉴权矩阵 v3 API 回归测试。
"""
import asyncio
import importlib
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, ".")


@pytest.fixture()
def client_env(tmp_path, monkeypatch):
    import agent_net.storage as st
    monkeypatch.setattr(st, "DB_PATH", tmp_path / "agent_net.db")

    import agent_net.node._auth as _auth
    monkeypatch.setattr(_auth, "USER_TOKEN_FILE", tmp_path / "daemon_token.txt")

    import agent_net.node.daemon as d
    importlib.reload(d)

    import agent_net.storage as st_reload
    importlib.reload(st_reload)
    asyncio.run(st_reload.init_db())

    from agent_net.node._auth import init_daemon_token
    from agent_net.node.daemon import app

    token = init_daemon_token()
    return TestClient(app), token


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register_owner_and_agent(client: TestClient, token: str):
    owner = client.post("/owner/register", json={"name": "Owner"}, headers=_headers(token)).json()["did"]
    agent = client.post("/agents/register", json={"name": "Agent"}, headers=_headers(token)).json()["did"]
    return owner, agent


def test_messages_send_requires_token_and_local_actor(client_env):
    client, token = client_env
    owner, agent = _register_owner_and_agent(client, token)

    payload = {"from_did": owner, "to_did": agent, "content": "hello"}
    assert client.post("/messages/send", json=payload).status_code == 401

    ok = client.post("/messages/send", json=payload, headers=_headers(token))
    assert ok.status_code == 200

    bad_actor = client.post(
        "/messages/send",
        json={"from_did": "did:agentnexus:zMissing", "to_did": agent, "content": "nope"},
        headers=_headers(token),
    )
    assert bad_actor.status_code == 403


def test_agent_private_reads_and_owner_access(client_env):
    client, token = client_env
    owner, agent = _register_owner_and_agent(client, token)
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent}, headers=_headers(token))

    no_token = client.get(f"/messages/inbox/{agent}?actor_did={owner}")
    assert no_token.status_code == 401

    owner_read = client.get(f"/messages/inbox/{agent}?actor_did={owner}", headers=_headers(token))
    assert owner_read.status_code == 200

    other = client.post("/agents/register", json={"name": "Other"}, headers=_headers(token)).json()["did"]
    forbidden = client.get(f"/messages/inbox/{agent}?actor_did={other}", headers=_headers(token))
    assert forbidden.status_code == 403


def test_enclave_reads_require_member_actor(client_env):
    client, token = client_env
    owner, member = _register_owner_and_agent(client, token)
    outsider = client.post("/agents/register", json={"name": "Outsider"}, headers=_headers(token)).json()["did"]

    create = client.post(
        "/enclaves",
        json={
            "name": "Project",
            "owner_did": owner,
            "members": {"developer": {"did": member, "permissions": "rw"}},
        },
        headers=_headers(token),
    )
    assert create.status_code == 200
    enclave_id = create.json()["enclave_id"]

    assert client.get(f"/enclaves/{enclave_id}?actor_did={owner}").status_code == 401

    owner_read = client.get(f"/enclaves/{enclave_id}?actor_did={owner}", headers=_headers(token))
    assert owner_read.status_code == 200

    outsider_read = client.get(f"/enclaves/{enclave_id}?actor_did={outsider}", headers=_headers(token))
    assert outsider_read.status_code == 403


def test_enclave_vault_read_requires_member_actor(client_env):
    client, token = client_env
    owner, member = _register_owner_and_agent(client, token)
    create = client.post(
        "/enclaves",
        json={
            "name": "Project",
            "owner_did": owner,
            "members": {"developer": {"did": member, "permissions": "rw"}},
        },
        headers=_headers(token),
    )
    enclave_id = create.json()["enclave_id"]

    put = client.put(
        f"/enclaves/{enclave_id}/vault/spec",
        json={"value": "draft", "author_did": member},
        headers=_headers(token),
    )
    assert put.status_code == 200

    assert client.get(f"/enclaves/{enclave_id}/vault/spec?actor_did={member}").status_code == 401
    got = client.get(f"/enclaves/{enclave_id}/vault/spec?actor_did={member}", headers=_headers(token))
    assert got.status_code == 200
    assert got.json()["value"] == "draft"


def test_capability_token_private_reads_require_token(client_env):
    client, token = client_env
    issuer, subject = _register_owner_and_agent(client, token)

    issue = client.post(
        "/capability-tokens/issue",
        json={"issuer_did": issuer, "subject_did": subject, "scope": {"permissions": ["vault:read"]}},
        headers=_headers(token),
    )
    token_id = issue.json()["token"]["token_id"]

    assert client.get(f"/capability-tokens/{token_id}").status_code == 401
    assert client.get(f"/capability-tokens/{token_id}", headers=_headers(token)).status_code == 200
    assert client.get(f"/capability-tokens/by-did/{subject}").status_code == 401
    assert client.get(f"/capability-tokens/by-did/{subject}", headers=_headers(token)).status_code == 200
