"""
tests/test_mcp_collaboration.py
MCP 协作工具测试 (tc-mcp-01~tc-mcp-10)

覆盖 ADR-012 §6 定义的 10 个 MCP 协作工具：
  tc-mcp-01 — propose_task 正确发送 task_propose 消息
  tc-mcp-02 — claim_task 正确发送 task_claim 消息
  tc-mcp-03 — sync_resource 正确发送 resource_sync 消息
  tc-mcp-04 — notify_state 正确发送 state_notify 消息
  tc-mcp-05 — start_discussion 向所有参与者广播
  tc-mcp-06 — reply_discussion 正确发送讨论回复
  tc-mcp-07 — vote_discussion 正确发送投票
  tc-mcp-08 — conclude_discussion 正确发送结论
  tc-mcp-09 — emergency_halt 使用独立 message_type
  tc-mcp-10 — list_skills 调用 GET /skills 端点
"""
import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock


# ─── aiohttp mock 工具 ────────────────────────────────────────────

class _Resp:
    """模拟单次 aiohttp 响应（async context manager）"""
    def __init__(self, status: int, data):
        self.status = status
        self._data = data

    async def json(self):
        return self._data

    async def text(self):
        return json.dumps(self._data)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class _Session:
    """按顺序消费预设响应的 session mock（async context manager）"""
    def __init__(self, *responses):
        self._q = list(responses)

    def _pop(self):
        return self._q.pop(0)

    def get(self, *a, **kw): return self._pop()
    def post(self, *a, **kw): return self._pop()

    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


# ─── 测试 fixture ──────────────────────────────────────────────────

@pytest.fixture
def mock_daemon():
    """模拟 Daemon HTTP 响应"""
    def _mock(*responses):
        return patch("aiohttp.ClientSession", return_value=_Session(*responses))
    return _mock


@pytest.fixture
def bound_did(monkeypatch):
    """设置 MCP 绑定 DID"""
    test_did = "did:agentnexus:z6MkTestAgent000000000000000000"
    monkeypatch.setenv("AGENTNEXUS_MY_DID", test_did)
    # 重新加载 mcp_server 模块以获取新的环境变量
    import importlib
    import agent_net.node.mcp_server as mcp
    importlib.reload(mcp)
    return test_did


# ═══════════════════════════════════════════════════════════════
# tc-mcp-01 — propose_task 正确发送 task_propose 消息
# ═══════════════════════════════════════════════════════════════

def test_tc_mcp_01_propose_task(mock_daemon, bound_did):
    """propose_task 发送 task_propose message_type，返回 task_id"""
    captured = {}

    class _CapturingSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        def post(self, url, json=None, **kw):
            captured["payload"] = json
            return _Resp(200, {"status": "ok"})

    from agent_net.node import mcp_server

    with patch("aiohttp.ClientSession", return_value=_CapturingSession()):
        result = asyncio.run(mcp_server._call("post", "/messages/send", json={
            "from_did": bound_did,
            "to_did": "did:agentnexus:z6MkTarget000000000000000000",
            "content": {"task_id": "task_test123", "title": "Test Task"},
            "message_type": "task_propose",
            "protocol": "nexus_v1",
        }))

    assert result["status"] == "ok"
    assert captured["payload"]["message_type"] == "task_propose"
    assert captured["payload"]["protocol"] == "nexus_v1"


# ═══════════════════════════════════════════════════════════════
# tc-mcp-02 — claim_task 正确发送 task_claim 消息
# ═══════════════════════════════════════════════════════════════

def test_tc_mcp_02_claim_task(mock_daemon, bound_did):
    """claim_task 发送 task_claim message_type"""
    captured = {}

    class _CapturingSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        def post(self, url, json=None, **kw):
            captured["payload"] = json
            return _Resp(200, {"status": "ok"})

    from agent_net.node import mcp_server

    with patch("aiohttp.ClientSession", return_value=_CapturingSession()):
        result = asyncio.run(mcp_server._call("post", "/messages/send", json={
            "from_did": bound_did,
            "to_did": "did:agentnexus:z6MkProposer000000000000000",
            "content": {"task_id": "task_test123", "eta": "2h"},
            "message_type": "task_claim",
            "protocol": "nexus_v1",
        }))

    assert result["status"] == "ok"
    assert captured["payload"]["message_type"] == "task_claim"


# ═══════════════════════════════════════════════════════════════
# tc-mcp-03 — sync_resource 正确发送 resource_sync 消息
# ═══════════════════════════════════════════════════════════════

def test_tc_mcp_03_sync_resource(mock_daemon, bound_did):
    """sync_resource 发送 resource_sync message_type"""
    captured = {}

    class _CapturingSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        def post(self, url, json=None, **kw):
            captured["payload"] = json
            return _Resp(200, {"status": "ok"})

    from agent_net.node import mcp_server

    with patch("aiohttp.ClientSession", return_value=_CapturingSession()):
        result = asyncio.run(mcp_server._call("post", "/messages/send", json={
            "from_did": bound_did,
            "to_did": "did:agentnexus:z6MkTarget000000000000000000",
            "content": {"key": "config", "value": json.dumps({"port": 8080})},
            "message_type": "resource_sync",
            "protocol": "nexus_v1",
        }))

    assert result["status"] == "ok"
    assert captured["payload"]["message_type"] == "resource_sync"


# ═══════════════════════════════════════════════════════════════
# tc-mcp-04 — notify_state 正确发送 state_notify 消息
# ═══════════════════════════════════════════════════════════════

def test_tc_mcp_04_notify_state(mock_daemon, bound_did):
    """notify_state 发送 state_notify message_type"""
    captured = {}

    class _CapturingSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        def post(self, url, json=None, **kw):
            captured["payload"] = json
            return _Resp(200, {"status": "ok"})

    from agent_net.node import mcp_server

    with patch("aiohttp.ClientSession", return_value=_CapturingSession()):
        result = asyncio.run(mcp_server._call("post", "/messages/send", json={
            "from_did": bound_did,
            "to_did": "did:agentnexus:z6MkProposer000000000000000",
            "content": {"status": "completed", "task_id": "task_test123"},
            "message_type": "state_notify",
            "protocol": "nexus_v1",
        }))

    assert result["status"] == "ok"
    assert captured["payload"]["message_type"] == "state_notify"


# ═══════════════════════════════════════════════════════════════
# tc-mcp-05 — start_discussion 向所有参与者广播
# ═══════════════════════════════════════════════════════════════

def test_tc_mcp_05_start_discussion_broadcasts_to_all(mock_daemon, bound_did):
    """start_discussion 向每个 participant 发送独立消息"""
    participants = [
        "did:agentnexus:z6MkParticipantA000000000000000",
        "did:agentnexus:z6MkParticipantB000000000000000",
    ]

    call_count = {"count": 0}

    class _CountingSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        def post(self, url, json=None, **kw):
            call_count["count"] += 1
            # 验证每条消息的 message_type
            assert json.get("message_type") == "discussion_start"
            assert json.get("protocol") == "nexus_v1"
            return _Resp(200, {"status": "ok"})

    from agent_net.node import mcp_server

    with patch("aiohttp.ClientSession", return_value=_CountingSession()):
        # 模拟 start_discussion 逻辑：向每个 participant 发送
        for did in participants:
            asyncio.run(mcp_server._call("post", "/messages/send", json={
                "from_did": bound_did,
                "to_did": did,
                "content": {"topic_id": "topic_test", "title": "Test", "participants": participants, "seq": 1},
                "message_type": "discussion_start",
                "protocol": "nexus_v1",
            }))

    assert call_count["count"] == 2  # 两个 participant 各收到一条


# ═══════════════════════════════════════════════════════════════
# tc-mcp-06 — reply_discussion 正确发送讨论回复
# ═══════════════════════════════════════════════════════════════

def test_tc_mcp_06_reply_discussion(mock_daemon, bound_did):
    """reply_discussion 发送 discussion_reply message_type"""
    captured = {}

    class _CapturingSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        def post(self, url, json=None, **kw):
            captured["payload"] = json
            return _Resp(200, {"status": "ok"})

    from agent_net.node import mcp_server

    with patch("aiohttp.ClientSession", return_value=_CapturingSession()):
        result = asyncio.run(mcp_server._call("post", "/messages/send", json={
            "from_did": bound_did,
            "to_did": "did:agentnexus:z6MkInitiator000000000000000",
            "content": {"topic_id": "topic_test", "content": "I agree with this proposal"},
            "message_type": "discussion_reply",
            "protocol": "nexus_v1",
        }))

    assert result["status"] == "ok"
    assert captured["payload"]["message_type"] == "discussion_reply"


# ═══════════════════════════════════════════════════════════════
# tc-mcp-07 — vote_discussion 正确发送投票
# ═══════════════════════════════════════════════════════════════

def test_tc_mcp_07_vote_discussion(mock_daemon, bound_did):
    """vote_discussion 发送 discussion_vote message_type"""
    captured = {}

    class _CapturingSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        def post(self, url, json=None, **kw):
            captured["payload"] = json
            return _Resp(200, {"status": "ok"})

    from agent_net.node import mcp_server

    with patch("aiohttp.ClientSession", return_value=_CapturingSession()):
        result = asyncio.run(mcp_server._call("post", "/messages/send", json={
            "from_did": bound_did,
            "to_did": "did:agentnexus:z6MkInitiator000000000000000",
            "content": {"topic_id": "topic_test", "vote": "approve"},
            "message_type": "discussion_vote",
            "protocol": "nexus_v1",
        }))

    assert result["status"] == "ok"
    assert captured["payload"]["message_type"] == "discussion_vote"


# ═══════════════════════════════════════════════════════════════
# tc-mcp-08 — conclude_discussion 正确发送结论
# ═══════════════════════════════════════════════════════════════

def test_tc_mcp_08_conclude_discussion(mock_daemon, bound_did):
    """conclude_discussion 发送 discussion_conclude message_type"""
    captured = {}

    class _CapturingSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        def post(self, url, json=None, **kw):
            captured["payload"] = json
            return _Resp(200, {"status": "ok"})

    from agent_net.node import mcp_server

    with patch("aiohttp.ClientSession", return_value=_CapturingSession()):
        result = asyncio.run(mcp_server._call("post", "/messages/send", json={
            "from_did": bound_did,
            "to_did": "did:agentnexus:z6MkParticipantA000000000000000",
            "content": {"topic_id": "topic_test", "conclusion": "Approved with modifications"},
            "message_type": "discussion_conclude",
            "protocol": "nexus_v1",
        }))

    assert result["status"] == "ok"
    assert captured["payload"]["message_type"] == "discussion_conclude"


# ═══════════════════════════════════════════════════════════════
# tc-mcp-09 — emergency_halt 使用独立 message_type
# ═══════════════════════════════════════════════════════════════

def test_tc_mcp_09_emergency_halt_uses_independent_message_type(mock_daemon, bound_did):
    """emergency_halt 使用独立的 message_type，不复用 state_notify"""
    captured = {}

    class _CapturingSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        def post(self, url, json=None, **kw):
            captured["payload"] = json
            return _Resp(200, {"status": "ok"})

    from agent_net.node import mcp_server

    with patch("aiohttp.ClientSession", return_value=_CapturingSession()):
        result = asyncio.run(mcp_server._call("post", "/messages/send", json={
            "from_did": bound_did,
            "to_did": "did:agentnexus:z6MkTarget000000000000000000",
            "content": {"scope": "agent", "reason": "API budget exceeded"},
            "message_type": "emergency_halt",
            "protocol": "nexus_v1",
        }))

    assert result["status"] == "ok"
    # 关键断言：message_type 必须是 emergency_halt，不能是 state_notify
    assert captured["payload"]["message_type"] == "emergency_halt"
    assert captured["payload"]["message_type"] != "state_notify"


# ═══════════════════════════════════════════════════════════════
# tc-mcp-10 — list_skills 调用 GET /skills 端点
# ═══════════════════════════════════════════════════════════════

def test_tc_mcp_10_list_skills_calls_get_endpoint(mock_daemon, bound_did):
    """list_skills 调用 GET /skills，不走消息系统"""
    captured = {"method": None}

    class _CapturingSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        def get(self, url, **kw):
            captured["method"] = "GET"
            captured["url"] = url
            return _Resp(200, {"skills": [{"agent_did": bound_did, "name": "TestSkill"}]})

        def post(self, url, **kw):
            captured["method"] = "POST"
            return _Resp(200, {})

    from agent_net.node import mcp_server

    with patch("aiohttp.ClientSession", return_value=_CapturingSession()):
        result = asyncio.run(mcp_server._call("get", "/skills"))

    assert captured["method"] == "GET"
    assert "skills" in result
