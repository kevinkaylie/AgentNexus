"""
v1.0-06 消息中心测试套件
测试 ID: v10_msg_01 – v10_msg_04

覆盖场景：
  - 聚合未读消息
  - 聚合全部消息（分页）
  - 各子 Agent 消息统计
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

def test_v10_msg_01_owner_inbox(isolated_env):
    """聚合主 DID 下所有子 Agent 的未读消息"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册主 DID
    owner = client.post("/owner/register", json={"name": "Owner"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 注册子 Agent
    agent1 = client.post("/agents/register", json={"name": "Agent1"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    agent2 = client.post("/agents/register", json={"name": "Agent2"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 绑定
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent1}, headers={"Authorization": f"Bearer {token}"})
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent2}, headers={"Authorization": f"Bearer {token}"})

    # 发送消息到子 Agent（使用 store_message 直接写入）
    from agent_net.storage import store_message
    asyncio.run(store_message("did:external:sender1", agent1, "Hello Agent1"))
    asyncio.run(store_message("did:external:sender2", agent2, "Hello Agent2"))
    asyncio.run(store_message("did:external:sender3", agent1, "Another message"))

    # 查询聚合未读
    resp = client.get(f"/owner/messages/inbox?owner_did={owner}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["owner_did"] == owner
    assert data["total_unread"] == 3
    assert len(data["messages"]) == 3

    # 验证消息包含 to_agent_name
    msgs = data["messages"]
    agent1_msgs = [m for m in msgs if m["to_did"] == agent1]
    assert len(agent1_msgs) == 2
    assert agent1_msgs[0]["to_agent_name"] == "Agent1"


def test_v10_msg_02_owner_messages_all(isolated_env):
    """聚合全部消息（分页）"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册主 DID 和子 Agent
    owner = client.post("/owner/register", json={"name": "Owner"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    agent = client.post("/agents/register", json={"name": "Agent"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent}, headers={"Authorization": f"Bearer {token}"})

    # 发送多条消息
    from agent_net.storage import store_message
    for i in range(5):
        asyncio.run(store_message("did:external:sender", agent, f"Message {i}"))

    # 部分标记已读
    from agent_net.storage import fetch_inbox
    asyncio.run(fetch_inbox(agent))  # fetch_inbox 会标记 delivered=1

    # 发送更多未读消息
    asyncio.run(store_message("did:external:sender", agent, "New unread"))

    # 查询全部消息
    resp = client.get(f"/owner/messages/all?owner_did={owner}&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 6

    # 验证 delivered 字段
    msgs = data["messages"]
    delivered_msgs = [m for m in msgs if m["delivered"]]
    assert len(delivered_msgs) == 5  # fetch_inbox 处理了前 5 条


def test_v10_msg_03_owner_stats(isolated_env):
    """各子 Agent 消息统计"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册主 DID
    owner = client.post("/owner/register", json={"name": "Owner"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 注册子 Agent
    agent1 = client.post("/agents/register", json={"name": "Agent1"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    agent2 = client.post("/agents/register", json={"name": "Agent2"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 绑定
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent1}, headers={"Authorization": f"Bearer {token}"})
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent2}, headers={"Authorization": f"Bearer {token}"})

    # 发送消息
    from agent_net.storage import store_message
    asyncio.run(store_message("did:external", agent1, "Msg1"))
    asyncio.run(store_message("did:external", agent1, "Msg2"))
    asyncio.run(store_message("did:external", agent2, "Msg3"))

    # 查询统计
    resp = client.get(f"/owner/messages/stats?owner_did={owner}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["stats"]) == 2

    # 验证统计
    stats = data["stats"]
    agent1_stat = next(s for s in stats if s["did"] == agent1)
    assert agent1_stat["name"] == "Agent1"
    assert agent1_stat["unread_count"] == 2

    agent2_stat = next(s for s in stats if s["did"] == agent2)
    assert agent2_stat["unread_count"] == 1


def test_v10_msg_04_owner_not_found(isolated_env):
    """非主 DID 查询应返回 404"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册普通 Agent（非 owner）
    agent = client.post("/agents/register", json={"name": "Agent"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 尝试查询
    resp = client.get(f"/owner/messages/inbox?owner_did={agent}")
    assert resp.status_code == 404

    resp2 = client.get(f"/owner/messages/stats?owner_did={agent}")
    assert resp2.status_code == 404