"""
v1.0-05 意图路由测试套件
测试 ID: v10_ir_01 – v10_ir_04

覆盖场景：
  - 关键词匹配转发
  - 无匹配留在主 DID 收件箱
  - 匹配阈值过滤
  - 主 DID 无子 Agent 时不转发
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

    # 重置 router 单例的本地 sessions
    from agent_net.router import router
    router._local_sessions.clear()

    from agent_net.node.daemon import app
    yield TestClient(app)


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def test_v10_ir_01_intent_route_match(isolated_env):
    """意图路由：关键词匹配转发"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    from agent_net.storage import get_agent, fetch_inbox
    from agent_net.router import router

    token = init_daemon_token()

    # 注册主 DID
    owner = client.post("/owner/register", json={"name": "Owner"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 注册子 Agent（带 capabilities）
    agent1 = client.post("/agents/register", json={"name": "CodeAgent", "capabilities": ["Code", "Python"]}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    agent2 = client.post("/agents/register", json={"name": "TranslateAgent", "capabilities": ["Translate", "English"]}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 绑定
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent1}, headers={"Authorization": f"Bearer {token}"})
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent2}, headers={"Authorization": f"Bearer {token}"})

    # 注册 agent1 为本地 session（模拟在线）
    router.register_local_session(agent1)
    router.register_local_session(agent2)

    # 发送消息给主 DID（包含 "python code" 关键词）
    result = asyncio.run(router.route_message(
        from_did="did:agentnexus:external",
        to_did=owner,
        content="帮我写一段 python code 实现登录功能",
    ))

    # 应转发到 CodeAgent（匹配 Code + Python）
    assert result["status"] == "delivered"
    assert result["method"] == "local"

    # 验证消息到达 CodeAgent
    msg = asyncio.run(router.receive(agent1, timeout=0.5))
    assert msg is not None
    assert "python" in msg["content"].lower()

    # 清理
    router.unregister_local_session(agent1)
    router.unregister_local_session(agent2)


def test_v10_ir_02_intent_route_no_match(isolated_env):
    """意图路由：无匹配留在主 DID 收件箱"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    from agent_net.storage import fetch_inbox
    from agent_net.router import router

    token = init_daemon_token()

    # 注册主 DID
    owner = client.post("/owner/register", json={"name": "Owner"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 注册子 Agent（不带相关 capabilities）
    agent = client.post("/agents/register", json={"name": "MathAgent", "capabilities": ["Math", "Calculator"]}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 绑定
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent}, headers={"Authorization": f"Bearer {token}"})

    # 发送消息给主 DID（无关内容）
    result = asyncio.run(router.route_message(
        from_did="did:agentnexus:external",
        to_did=owner,
        content="今天天气怎么样",
    ))

    # 无匹配，消息留在主 DID 收件箱（离线存储）
    assert result["status"] == "queued"
    assert result["method"] == "offline"

    # 验证消息存入主 DID 的 inbox
    inbox = asyncio.run(fetch_inbox(owner))
    assert len(inbox) == 1
    assert "天气" in inbox[0]["content"]


def test_v10_ir_03_intent_route_threshold(isolated_env):
    """意图路由：匹配阈值过滤"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    from agent_net.storage import fetch_inbox
    from agent_net.router import router, MIN_MATCH_SCORE

    token = init_daemon_token()

    # 注册主 DID
    owner = client.post("/owner/register", json={"name": "Owner"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 注册子 Agent（只有一个 capability）
    agent = client.post("/agents/register", json={"name": "ChatAgent", "capabilities": ["Chat"]}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 绑定
    client.post("/owner/bind", json={"owner_did": owner, "agent_did": agent}, headers={"Authorization": f"Bearer {token}"})

    # 注册本地 session
    router.register_local_session(agent)

    # 发送消息（只匹配一个关键词 "chat"，低于阈值 MIN_MATCH_SCORE=2）
    result = asyncio.run(router.route_message(
        from_did="did:agentnexus:external",
        to_did=owner,
        content="让我们 chat 吧",
    ))

    # 匹配分数 = 1 < 2，不转发
    assert result["status"] == "queued"
    assert result["method"] == "offline"

    # 清理
    router.unregister_local_session(agent)


def test_v10_ir_04_intent_route_no_agents(isolated_env):
    """意图路由：主 DID 无子 Agent 时不转发"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    from agent_net.storage import fetch_inbox
    from agent_net.router import router

    token = init_daemon_token()

    # 注册主 DID（不绑定子 Agent）
    owner = client.post("/owner/register", json={"name": "Owner"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 发送消息给主 DID
    result = asyncio.run(router.route_message(
        from_did="did:agentnexus:external",
        to_did=owner,
        content="帮我写代码",
    ))

    # 无子 Agent，消息留在主 DID 收件箱
    assert result["status"] == "queued"
    assert result["method"] == "offline"

    # 验证消息存入主 DID 的 inbox
    inbox = asyncio.run(fetch_inbox(owner))
    assert len(inbox) == 1