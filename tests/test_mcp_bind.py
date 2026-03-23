"""
tests/test_mcp_bind.py
MCP --name/--did 身份绑定启动流程测试 (tm01–tm07)

覆盖 main._mcp_bind_agent() 及 node_mcp() 的所有分支：
  tm01 — --name 注册新 Agent（本地无同名）
  tm02 — --name 复用已有同名 Agent（幂等）
  tm03 — --did 绑定已有 DID
  tm04 — --did 不存在时 sys.exit(1)
  tm05 — 注册 payload 包含 caps/tags/desc/is_public；Token 头附加
  tm06 — daemon 未运行（ClientConnectorError）→ sys.exit(1)
  tm07 — node_mcp 绑定后注入 AGENTNEXUS_MY_DID 环境变量
"""
import asyncio
import json
import os
import pytest
import aiohttp
from unittest.mock import patch, MagicMock

import agent_net.common.constants as _const
from main import _mcp_bind_agent


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

    def get(self, *a, **kw):  return self._pop()
    def post(self, *a, **kw): return self._pop()

    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


def _patch_aiohttp(*responses):
    """patch aiohttp.ClientSession，按顺序返回预设响应"""
    return patch("aiohttp.ClientSession", return_value=_Session(*responses))


# ═══════════════════════════════════════════════════════════════
# tm01 — --name 注册新 Agent
# ═══════════════════════════════════════════════════════════════

def test_tm01_bind_name_registers_new_agent(tmp_path, monkeypatch):
    """--name 给定且无同名 Agent 时，调用 /agents/register 并返回新 DID"""
    monkeypatch.setattr(_const, "DAEMON_TOKEN_FILE", str(tmp_path / "no_token.txt"))
    new_did = "did:agent:newbot0000000001"

    with _patch_aiohttp(
        _Resp(200, {"agents": []}),          # GET /agents/local → 空列表
        _Resp(200, {"did": new_did}),         # POST /agents/register → 新 DID
    ):
        result = asyncio.run(
            _mcp_bind_agent("NewBot", None, ["coding"], "desc", ["tag1"], False)
        )

    assert result == new_did


# ═══════════════════════════════════════════════════════════════
# tm02 — --name 复用已有同名 Agent（幂等）
# ═══════════════════════════════════════════════════════════════

def test_tm02_bind_name_reuses_existing_agent(tmp_path, monkeypatch):
    """--name 给定且本地已有同名 Agent 时，直接返回其 DID，不调用 register"""
    monkeypatch.setattr(_const, "DAEMON_TOKEN_FILE", str(tmp_path / "no_token.txt"))
    existing_did = "did:agent:coderbot000000001"

    with _patch_aiohttp(
        _Resp(200, {"agents": [
            {"did": existing_did, "profile": {"name": "CoderBot"}},
            {"did": "did:agent:other00000000001", "profile": {"name": "OtherBot"}},
        ]}),
        # 不应消费第二个响应（不调用 register）
    ):
        result = asyncio.run(
            _mcp_bind_agent("CoderBot", None, [], "", [], False)
        )

    assert result == existing_did


# ═══════════════════════════════════════════════════════════════
# tm03 — --did 绑定已有 DID
# ═══════════════════════════════════════════════════════════════

def test_tm03_bind_did_valid(tmp_path, monkeypatch):
    """--did 给定且 profile 存在（200）时，直接返回该 DID"""
    monkeypatch.setattr(_const, "DAEMON_TOKEN_FILE", str(tmp_path / "no_token.txt"))
    target_did = "did:agent:targetdid0000001"

    with _patch_aiohttp(
        _Resp(200, {"header": {"did": target_did}}),   # GET /agents/{did}/profile
    ):
        result = asyncio.run(
            _mcp_bind_agent(None, target_did, [], "", [], False)
        )

    assert result == target_did


# ═══════════════════════════════════════════════════════════════
# tm04 — --did 不存在时 sys.exit(1)
# ═══════════════════════════════════════════════════════════════

def test_tm04_bind_did_not_found_exits(tmp_path, monkeypatch):
    """--did 给定但 daemon 返回 404 时，sys.exit(1)"""
    monkeypatch.setattr(_const, "DAEMON_TOKEN_FILE", str(tmp_path / "no_token.txt"))
    missing_did = "did:agent:missing0000000001"

    with _patch_aiohttp(
        _Resp(404, {"detail": "not found"}),   # GET /agents/{did}/profile → 404
    ):
        with pytest.raises(SystemExit) as exc:
            asyncio.run(_mcp_bind_agent(None, missing_did, [], "", [], False))

    assert exc.value.code == 1


# ═══════════════════════════════════════════════════════════════
# tm05 — 注册 payload 含 caps/tags/desc/is_public；Token 头附加
# ═══════════════════════════════════════════════════════════════

def test_tm05_register_payload_and_auth_header(tmp_path, monkeypatch):
    """注册新 Agent 时，payload 含完整字段；token 文件存在时 Authorization 头被附加"""
    token_file = tmp_path / "token.txt"
    token_file.write_text("test-secret-token")
    monkeypatch.setattr(_const, "DAEMON_TOKEN_FILE", str(token_file))

    new_did = "did:agent:capsbot0000000001"
    captured = {}

    class _CapturingSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        def get(self, url, **kw):
            return _Resp(200, {"agents": []})  # no existing agent

        def post(self, url, json=None, headers=None, **kw):
            captured["payload"] = json
            captured["headers"] = headers or {}
            return _Resp(200, {"did": new_did})

    with patch("aiohttp.ClientSession", return_value=_CapturingSession()):
        asyncio.run(_mcp_bind_agent(
            "CapsBot", None,
            caps=["Python", "Testing"],
            desc="A capable bot",
            tags=["bot", "test"],
            public=True,
        ))

    p = captured["payload"]
    assert p["name"] == "CapsBot"
    assert p["capabilities"] == ["Python", "Testing"]
    assert p["description"] == "A capable bot"
    assert p["tags"] == ["bot", "test"]
    assert p["is_public"] is True
    # Token 必须附加到 Authorization 头
    assert captured["headers"].get("Authorization") == "Bearer test-secret-token"


# ═══════════════════════════════════════════════════════════════
# tm06 — daemon 未运行时 sys.exit(1)
# ═══════════════════════════════════════════════════════════════

def test_tm06_no_daemon_exits(tmp_path, monkeypatch):
    """daemon 未运行（ClientConnectorError）时，输出提示并 sys.exit(1)"""
    monkeypatch.setattr(_const, "DAEMON_TOKEN_FILE", str(tmp_path / "no_token.txt"))

    conn_key = MagicMock()
    connector_error = aiohttp.ClientConnectorError(conn_key, OSError("connection refused"))

    class _FailSession:
        async def __aenter__(self):
            raise connector_error
        async def __aexit__(self, *_): pass

    with patch("aiohttp.ClientSession", return_value=_FailSession()):
        with pytest.raises(SystemExit) as exc:
            asyncio.run(_mcp_bind_agent("Bot", None, [], "", [], False))

    assert exc.value.code == 1


# ═══════════════════════════════════════════════════════════════
# tm07 — node_mcp 绑定后注入 AGENTNEXUS_MY_DID 环境变量
# ═══════════════════════════════════════════════════════════════

def test_tm07_node_mcp_sets_env_var(monkeypatch):
    """node_mcp --name 启动后，AGENTNEXUS_MY_DID 被写入 os.environ"""
    import main as m

    bound_did = "did:agent:envtest0000000001"

    # 绑定后注入后清除 env var，避免污染后续测试
    monkeypatch.delenv("AGENTNEXUS_MY_DID", raising=False)

    async def _mock_bind(*a, **kw):
        return bound_did

    async def _mock_mcp_main():
        pass  # 不实际启动 stdio 服务

    monkeypatch.setattr(m, "_mcp_bind_agent", _mock_bind)
    with patch("agent_net.node.mcp_server.main", _mock_mcp_main):
        m.node_mcp(name="EnvBot")

    assert os.environ.get("AGENTNEXUS_MY_DID") == bound_did
