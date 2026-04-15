"""
v1.0-04 个人主 DID 测试套件
测试 ID: v10_own_01 – v10_own_06

覆盖场景：
  - 注册主 DID
  - 绑定 Agent 到主 DID
  - 解绑 Agent
  - 列出子 Agent
  - 获取主 DID profile
"""
import asyncio
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, ".")


# ---------------------------------------------------------------------------
# 测试 Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    """创建隔离的测试环境"""
    import agent_net.storage as st
    monkeypatch.setattr(st, "DB_PATH", tmp_path / "agent_net.db")

    import agent_net.node._auth as _auth
    monkeypatch.setattr(_auth, "USER_TOKEN_FILE", tmp_path / "daemon_token.txt")

    import agent_net.node.daemon as d
    importlib.reload(d)

    import agent_net.storage as st_reload
    importlib.reload(st_reload)
    asyncio.run(st_reload.init_db())

    from agent_net.node.daemon import app
    yield TestClient(app)


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def test_v10_own_01_register_owner(isolated_env):
    """注册个人主 DID"""
    client = isolated_env

    # 获取 token
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册主 DID
    resp = client.post(
        "/owner/register",
        json={"name": "TestOwner"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "did" in data
    assert data["did"].startswith("did:agentnexus:")
    assert "public_key_hex" in data
    assert "profile" in data
    assert data["profile"]["type"] == "owner"
    assert data["profile"]["name"] == "TestOwner"

    # 验证写入数据库
    from agent_net.storage import get_agent
    agent = asyncio.run(get_agent(data["did"]))
    assert agent is not None
    assert agent["profile"]["type"] == "owner"
    assert agent["owner_did"] is None  # 主 DID 没有 owner


def test_v10_own_02_bind_agent(isolated_env):
    """绑定 Agent 到主 DID"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册主 DID
    owner_resp = client.post(
        "/owner/register",
        json={"name": "Owner"},
        headers={"Authorization": f"Bearer {token}"},
    )
    owner_did = owner_resp.json()["did"]

    # 注册普通 Agent
    agent_resp = client.post(
        "/agents/register",
        json={"name": "SubAgent", "capabilities": ["Chat"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    agent_did = agent_resp.json()["did"]

    # 绑定
    bind_resp = client.post(
        "/owner/bind",
        json={"owner_did": owner_did, "agent_did": agent_did},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bind_resp.status_code == 200
    assert bind_resp.json()["status"] == "ok"

    # 验证绑定关系
    from agent_net.storage import get_agent, list_owned_agents
    agent = asyncio.run(get_agent(agent_did))
    assert agent["owner_did"] == owner_did

    owned = asyncio.run(list_owned_agents(owner_did))
    assert len(owned) == 1
    assert owned[0]["did"] == agent_did


def test_v10_own_03_bind_already_bound(isolated_env):
    """绑定已被其他 owner 拥有的 Agent 应失败"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册两个主 DID
    owner1 = client.post("/owner/register", json={"name": "Owner1"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    owner2 = client.post("/owner/register", json={"name": "Owner2"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 注册 Agent
    agent = client.post("/agents/register", json={"name": "Agent"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 绑定到 owner1
    client.post("/owner/bind", json={"owner_did": owner1, "agent_did": agent}, headers={"Authorization": f"Bearer {token}"})

    # 尝试绑定到 owner2（应失败）
    resp = client.post("/owner/bind", json={"owner_did": owner2, "agent_did": agent}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 409  # Agent already bound


def test_v10_own_04_unbind_agent(isolated_env):
    """解绑 Agent"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册主 DID 和 Agent
    owner = client.post("/owner/register", json={"name": "Owner"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    agent = client.post("/agents/register", json={"name": "Agent"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 绑定
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent}, headers={"Authorization": f"Bearer {token}"})

    # 解绑
    resp = client.request(
        "DELETE", "/owner/unbind",
        json={"owner_did": owner, "agent_did": agent},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200

    # 验证解绑
    from agent_net.storage import get_agent
    agent_data = asyncio.run(get_agent(agent))
    assert agent_data["owner_did"] is None


def test_v10_own_05_list_owned_agents(isolated_env):
    """列出主 DID 下所有子 Agent"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册主 DID
    owner = client.post("/owner/register", json={"name": "Owner"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 注册多个 Agent
    agent1 = client.post("/agents/register", json={"name": "Agent1"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    agent2 = client.post("/agents/register", json={"name": "Agent2"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 绑定
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent1}, headers={"Authorization": f"Bearer {token}"})
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent2}, headers={"Authorization": f"Bearer {token}"})

    # 列出
    resp = client.get(f"/owner/agents/{owner}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["owner_did"] == owner
    assert data["count"] == 2
    dids = [a["did"] for a in data["agents"]]
    assert agent1 in dids
    assert agent2 in dids


def test_v10_own_06_get_owner_profile(isolated_env):
    """获取主 DID profile"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册主 DID
    owner = client.post("/owner/register", json={"name": "TestOwner"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 获取 profile
    resp = client.get(f"/owner/profile/{owner}")
    assert resp.status_code == 200
    profile = resp.json()
    assert profile["type"] == "owner"
    assert profile["name"] == "TestOwner"

    # 非主 DID 应返回 404
    agent = client.post("/agents/register", json={"name": "Agent"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    resp2 = client.get(f"/owner/profile/{agent}")
    assert resp2.status_code == 404