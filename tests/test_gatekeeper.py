"""
tests/test_gatekeeper.py
访问控制模块测试套件

覆盖:
  tg01 - public 模式全部放行
  tg02 - private 模式拦截未知 DID
  tg03 - private 模式白名单放行
  tg04 - 黑名单优先拒绝（无论模式）
  tg05 - ask 模式未知 DID 进入 pending 队列
  tg06 - resolve allow 唤醒等待中的握手协程
  tg07 - resolve deny 返回 deny，握手中断
  tg08 - 重复 resolve 返回 False
  tg09 - list_pending 只返回 status=pending 的记录
  tg10 - 白/黑名单持久化到文件，跨实例可读
"""
import asyncio
import json
import pytest
from pathlib import Path

import agent_net.storage as _storage
from agent_net.storage import (
    init_db, add_pending, list_pending, get_pending, resolve_pending,
)
from agent_net.node.gatekeeper import (
    Gatekeeper, GateDecision,
    WHITELIST_PATH, BLACKLIST_PATH, MODE_PATH,
    _save_list, _load_list, save_mode, load_mode,
)

FAKE_INIT = {"type": "INIT", "sender_did": "", "verify_key": "abc", "x25519_pub": "xyz"}


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """每个测试独立 DB + 独立配置文件路径"""
    db = tmp_path / "test.db"
    monkeypatch.setattr(_storage, "DB_PATH", db)
    asyncio.run(_storage.init_db())

    # 重定向配置文件到 tmp_path
    import agent_net.node.gatekeeper as gk
    monkeypatch.setattr(gk, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(gk, "WHITELIST_PATH", tmp_path / "whitelist.json")
    monkeypatch.setattr(gk, "BLACKLIST_PATH", tmp_path / "blacklist.json")
    monkeypatch.setattr(gk, "MODE_PATH", tmp_path / "mode.json")


def make_gate() -> Gatekeeper:
    """每个测试用新实例，避免全局 _pending_futures 污染"""
    return Gatekeeper()


def init_packet(did: str) -> dict:
    return {**FAKE_INIT, "sender_did": did}


# ── tg01: public 模式全部放行 ─────────────────────────────

def test_tg01_public_allows_all():
    async def _run():
        import agent_net.node.gatekeeper as gk
        save_mode("public")
        gate = make_gate()
        result = await gate.check("did:agent:stranger", init_packet("did:agent:stranger"))
        assert result == GateDecision.ALLOW
    asyncio.run(_run())


# ── tg02: private 模式拦截未知 DID ───────────────────────

def test_tg02_private_blocks_unknown():
    async def _run():
        save_mode("private")
        gate = make_gate()
        result = await gate.check("did:agent:unknown", init_packet("did:agent:unknown"))
        assert result == GateDecision.DENY
    asyncio.run(_run())


# ── tg03: private 模式白名单放行 ─────────────────────────

def test_tg03_private_allows_whitelist():
    async def _run():
        save_mode("private")
        gate = make_gate()
        gate.whitelist_add("did:agent:trusted")
        result = await gate.check("did:agent:trusted", init_packet("did:agent:trusted"))
        assert result == GateDecision.ALLOW
    asyncio.run(_run())


# ── tg04: 黑名单优先拒绝（public 模式下也拒绝）────────────

def test_tg04_blacklist_overrides_public():
    async def _run():
        save_mode("public")
        gate = make_gate()
        gate.blacklist_add("did:agent:evil")
        result = await gate.check("did:agent:evil", init_packet("did:agent:evil"))
        assert result == GateDecision.DENY
    asyncio.run(_run())


# ── tg05: ask 模式未知 DID 进入 pending ──────────────────

def test_tg05_ask_queues_unknown():
    async def _run():
        save_mode("ask")
        gate = make_gate()
        did = "did:agent:newcomer"
        result = await gate.check(did, init_packet(did))
        assert result == GateDecision.PENDING

        # 确认写入 pending_requests
        items = await list_pending()
        assert len(items) == 1
        assert items[0]["did"] == did
        assert items[0]["status"] == "pending"
    asyncio.run(_run())


# ── tg06: resolve allow 唤醒握手协程 ─────────────────────

def test_tg06_resolve_allow_resumes_handshake():
    async def _run():
        save_mode("ask")
        gate = make_gate()
        did = "did:agent:waiting"

        # 模拟握手协程等待
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        gate.register_pending_future(did, fut)

        # 先写入 pending 记录
        await add_pending(did, init_packet(did))

        # 另一协程 resolve
        async def _resolver():
            await asyncio.sleep(0)   # 让出控制权
            await gate.resolve(did, "allow")

        action, _ = await asyncio.gather(
            asyncio.wait_for(fut, timeout=2),
            _resolver(),
        )
        assert action == "allow"

        # DB 状态已更新
        rec = await get_pending(did)
        assert rec["status"] == "allow"
    asyncio.run(_run())


# ── tg07: resolve deny 握手中断 ──────────────────────────

def test_tg07_resolve_deny_blocks_handshake():
    async def _run():
        save_mode("ask")
        gate = make_gate()
        did = "did:agent:denied"

        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        gate.register_pending_future(did, fut)
        await add_pending(did, init_packet(did))

        async def _resolver():
            await asyncio.sleep(0)
            await gate.resolve(did, "deny")

        action, _ = await asyncio.gather(
            asyncio.wait_for(fut, timeout=2),
            _resolver(),
        )
        assert action == "deny"

        rec = await get_pending(did)
        assert rec["status"] == "deny"
    asyncio.run(_run())


# ── tg08: 重复 resolve 返回 False ────────────────────────

def test_tg08_duplicate_resolve_returns_false():
    async def _run():
        gate = make_gate()
        did = "did:agent:once"
        await add_pending(did, init_packet(did))
        ok1 = await gate.resolve(did, "allow")
        ok2 = await gate.resolve(did, "allow")   # 已不是 pending
        assert ok1 is True
        assert ok2 is False
    asyncio.run(_run())


# ── tg09: list_pending 只返回 status=pending ─────────────

def test_tg09_list_pending_filters_resolved():
    async def _run():
        gate = make_gate()
        await add_pending("did:agent:a", init_packet("did:agent:a"))
        await add_pending("did:agent:b", init_packet("did:agent:b"))
        await gate.resolve("did:agent:a", "allow")

        items = await list_pending()
        assert len(items) == 1
        assert items[0]["did"] == "did:agent:b"
    asyncio.run(_run())


# ── tg10: 白/黑名单文件持久化 ────────────────────────────

def test_tg10_list_files_persist():
    gate = make_gate()
    gate.whitelist_add("did:agent:p1")
    gate.whitelist_add("did:agent:p2")
    gate.blacklist_add("did:agent:evil")

    # 新实例重新读取
    gate2 = make_gate()
    assert "did:agent:p1" in gate2.whitelist_all()
    assert "did:agent:p2" in gate2.whitelist_all()
    assert "did:agent:evil" in gate2.blacklist_all()

    gate2.whitelist_remove("did:agent:p1")
    assert "did:agent:p1" not in gate2.whitelist_all()
    assert "did:agent:p2" in gate2.whitelist_all()
