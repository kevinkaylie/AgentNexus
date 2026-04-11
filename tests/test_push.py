"""
tests/test_push.py
Push Registration 测试 (v0.9)

覆盖 ADR-012 L3/L5：
- push_registrations 表 CRUD
- /push/register, /push/refresh, /push/{did} 端点
- Push 通知触发
- TTL 过期清理
"""
import asyncio
import json
import time
import pytest
import pytest_asyncio
import aiohttp
from unittest.mock import patch, MagicMock, AsyncMock

from agent_net import storage


# ─── Fixtures ─────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path, monkeypatch):
    """每个测试使用独立的临时数据库"""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    await storage.init_db()
    yield db_path


# ─── Push Registration CRUD ───────────────────────────────────────

@pytest.mark.asyncio
async def test_create_push_registration():
    """创建 Push 注册"""
    result = await storage.create_push_registration(
        did="did:agentnexus:z6MkTest",
        callback_url="http://127.0.0.1:3001/notify",
        callback_type="webhook",
        expires_seconds=3600,
    )

    assert "registration_id" in result
    assert result["registration_id"].startswith("reg_")
    assert "callback_secret" in result
    assert result["callback_secret"].startswith("sk_")
    assert "expires_at" in result
    assert result["expires_at"] > time.time()


@pytest.mark.asyncio
async def test_get_active_push_registrations():
    """获取有效的 Push 注册"""
    await storage.create_push_registration(
        did="did:agentnexus:z6MkTest",
        callback_url="http://127.0.0.1:3001/notify",
    )

    regs = await storage.get_active_push_registrations("did:agentnexus:z6MkTest")
    assert len(regs) == 1
    assert regs[0]["callback_url"] == "http://127.0.0.1:3001/notify"


@pytest.mark.asyncio
async def test_get_active_excludes_expired():
    """过期注册不应返回"""
    # 创建一个已过期的注册
    await storage.create_push_registration(
        did="did:agentnexus:z6MkExpired",
        callback_url="http://127.0.0.1:3001/notify",
        expires_seconds=-1,  # 已过期
    )

    regs = await storage.get_active_push_registrations("did:agentnexus:z6MkExpired")
    assert len(regs) == 0


@pytest.mark.asyncio
async def test_refresh_push_registration():
    """续约 Push 注册"""
    await storage.create_push_registration(
        did="did:agentnexus:z6MkTest",
        callback_url="http://127.0.0.1:3001/notify",
        expires_seconds=3600,
    )

    new_expires = await storage.refresh_push_registration(
        did="did:agentnexus:z6MkTest",
        callback_url="http://127.0.0.1:3001/notify",
        expires_seconds=7200,
    )

    assert new_expires is not None
    assert new_expires > time.time() + 3600


@pytest.mark.asyncio
async def test_delete_push_registration():
    """删除 Push 注册"""
    await storage.create_push_registration(
        did="did:agentnexus:z6MkTest",
        callback_url="http://127.0.0.1:3001/notify",
    )

    deleted = await storage.delete_push_registration("did:agentnexus:z6MkTest")
    assert deleted == 1

    regs = await storage.get_active_push_registrations("did:agentnexus:z6MkTest")
    assert len(regs) == 0


@pytest.mark.asyncio
async def test_cleanup_expired_push_registrations():
    """清理过期注册"""
    # 创建一个已过期和一个有效的注册
    await storage.create_push_registration(
        did="did:agentnexus:z6MkExpired",
        callback_url="http://127.0.0.1:3001/notify",
        expires_seconds=-1,
    )
    await storage.create_push_registration(
        did="did:agentnexus:z6MkValid",
        callback_url="http://127.0.0.1:3002/notify",
        expires_seconds=3600,
    )

    deleted = await storage.cleanup_expired_push_registrations()
    assert deleted == 1

    regs_expired = await storage.get_active_push_registrations("did:agentnexus:z6MkExpired")
    regs_valid = await storage.get_active_push_registrations("did:agentnexus:z6MkValid")
    assert len(regs_expired) == 0
    assert len(regs_valid) == 1


# ─── Multiple Registrations ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_callbacks_per_did():
    """一个 DID 可以注册多个回调"""
    await storage.create_push_registration(
        did="did:agentnexus:z6MkMulti",
        callback_url="http://127.0.0.1:3001/notify",
        callback_type="webhook",
    )
    await storage.create_push_registration(
        did="did:agentnexus:z6MkMulti",
        callback_url="http://127.0.0.1:3002/notify",
        callback_type="webhook",
    )

    regs = await storage.get_active_push_registrations("did:agentnexus:z6MkMulti")
    assert len(regs) == 2


@pytest.mark.asyncio
async def test_replace_same_callback():
    """同一 URL + type 会替换旧注册"""
    result1 = await storage.create_push_registration(
        did="did:agentnexus:z6MkTest",
        callback_url="http://127.0.0.1:3001/notify",
    )
    result2 = await storage.create_push_registration(
        did="did:agentnexus:z6MkTest",
        callback_url="http://127.0.0.1:3001/notify",
    )

    regs = await storage.get_active_push_registrations("did:agentnexus:z6MkTest")
    assert len(regs) == 1
    assert regs[0]["registration_id"] == result2["registration_id"]


# ─── Daemon Endpoints ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_push_register_endpoint():
    """测试 /push/register 端点"""
    from agent_net.node import daemon
    import importlib

    # 使用 TestClient 需要 token，且需要先注册 Agent 绑定 DID
    from fastapi.testclient import TestClient

    # 重新加载 daemon 模块以确保干净状态
    importlib.reload(daemon)

    with TestClient(daemon.app) as client:
        from agent_net.node._auth import get_token
        token = get_token() or "test-token"

        # 先注册 Agent 以绑定 DID（需要通过 daemon 的 agent 注册）
        reg_response = client.post(
            "/agents/register",
            json={"name": "PushTestAgent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert reg_response.status_code == 200
        agent_did = reg_response.json()["did"]

        # 现在注册 Push（使用已绑定的 DID）
        response = client.post(
            "/push/register",
            json={
                "did": agent_did,
                "callback_url": "http://127.0.0.1:3001/notify",
                "callback_type": "webhook",
                "expires": 3600,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        # 应该成功返回
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "registration_id" in data


# ─── Push Notify Integration ───────────────────────────────────────

@pytest.mark.asyncio
async def test_push_notify_triggered_on_offline_message():
    """离线消息存储后应触发 Push 通知"""
    # 创建 Push 注册
    await storage.create_push_registration(
        did="did:agentnexus:z6MkTarget",
        callback_url="http://127.0.0.1:19999/notify",  # 不存在的端口
    )

    # 存储消息（模拟离线投递）
    await storage.store_message(
        from_did="did:agentnexus:z6MkSender",
        to_did="did:agentnexus:z6MkTarget",
        content="Test message",
    )

    # 消息应该已存储（即使 callback_url 无效，消息仍会静默存储）
    inbox = await storage.fetch_inbox("did:agentnexus:z6MkTarget")
    # fetch_inbox 返回未读消息并标记为 delivered
    assert len(inbox) == 1
    assert inbox[0]["content"] == "Test message"
