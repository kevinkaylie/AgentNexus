"""Tests for coordination CLI commands (SDK facade refactored)."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────

def _make_resp(body):
    """Create a fake HTTP response that works as an async context manager."""
    resp = AsyncMock()
    resp.status = 200
    resp.json = AsyncMock(return_value=body)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _resolve_body(url, response_overrides, default=None):
    """Find the override body matching a URL path suffix.

    Matches against the URL path (not query string) using end-of-path matching
    to avoid substring collisions (e.g. /timeline incorrectly matching .../timeline/foo).
    """
    if not response_overrides:
        return default or {"status": "ok"}
    from urllib.parse import urlparse
    path = urlparse(url).path
    # Sort by key length descending so longer (more specific) paths match first
    for suffix, override in sorted(response_overrides.items(), key=lambda x: -len(x[0])):
        if path.endswith(suffix):
            return override
    return default or {"status": "ok"}


def _make_fake_session(response_overrides=None):
    """Create a fake aiohttp.ClientSession that records .request() calls.

    All methods return regular functions (not coroutines) that return an
    async context manager, matching aiohttp's real API contract.

    response_overrides: dict mapping URL substring -> response body dict.
    """
    session = AsyncMock()
    session._last_request = None

    def _request(method, url, *, headers=None, json=None, params=None, **kwargs):
        session._last_request = (method, url, json, params, headers)
        return _make_resp(_resolve_body(url, response_overrides))

    session.request = _request

    def _get(url, *, headers=None, params=None, **kwargs):
        session._last_request = ("GET", url, None, params, headers)
        return _make_resp(_resolve_body(url, response_overrides))

    def _post(url, *, json=None, headers=None, params=None, **kwargs):
        session._last_request = ("POST", url, json, params, headers)
        return _make_resp(_resolve_body(url, response_overrides))

    session.get = _get
    session.post = _post
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _patch_session(monkeypatch, session):
    """Replace aiohttp.ClientSession with a factory that returns `session`."""
    def _factory(*a, **kw):
        return session
    monkeypatch.setattr("aiohttp.ClientSession", _factory)


async def _run_cmd(monkeypatch, capsys, args, response_overrides=None):
    """Run a coordination CLI command with mocked HTTP.

    response_overrides: dict mapping URL substring -> response body dict.
    """
    session = _make_fake_session(response_overrides)
    _patch_session(monkeypatch, session)

    from main import node_coordination_cmd
    await node_coordination_cmd(args)

    return session


# ── Fixture ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _patch_token_file(tmp_path, monkeypatch):
    """Ensure daemon token exists for CLI commands."""
    token_file = tmp_path / "daemon_token.txt"
    token_file.write_text("test-token-123")
    monkeypatch.setattr("agent_net.common.constants.DAEMON_TOKEN_FILE", str(token_file))
    monkeypatch.setattr("agent_net.node._auth.DAEMON_TOKEN_FILE", str(token_file))


# ═══════════════════════════════════════════════════════════════════
# coding-intake
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_coding_intake(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "coding-intake",
        "did:agentnexus:owner1", "did:agentnexus:actor1",
        "Implement login module",
        "--complexity", "high",
        "--risk", "elevated",
    ], {
        "/coordination/coding/intake": {
            "status": "intake",
            "session": {"coordination_session_id": "cs_cli001", "objective": "Build CLI"},
        },
    })

    method, url, body, params, headers = session._last_request
    assert "/coordination/coding/intake" in url
    assert body["owner_did"] == "did:agentnexus:owner1"
    assert body["complexity"] == "high"
    assert body["risk_level"] == "elevated"

    captured = capsys.readouterr()
    assert "cs_cli001" in captured.out


# ═══════════════════════════════════════════════════════════════════
# get-session
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_get_session(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "get", "cs_test001",
        "--actor", "did:agentnexus:owner1",
    ], {
        "/coordination/sessions/cs_test001": {
            "status": "ok",
            "session": {"coordination_session_id": "cs_test001", "objective": "Test"},
        },
    })

    method, url, body, params, headers = session._last_request
    assert "/coordination/sessions/cs_test001" in url
    assert params["actor_did"] == "did:agentnexus:owner1"

    captured = capsys.readouterr()
    assert "cs_test001" in captured.out


# ═══════════════════════════════════════════════════════════════════
# list-sessions
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_list_sessions(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "list",
        "--owner", "did:agentnexus:owner1",
        "--actor", "did:agentnexus:actor1",
    ], {
        "/coordination/sessions": {
            "status": "ok",
            "sessions": [
                {"coordination_session_id": "cs_a", "objective": "Task A", "status": "intake"},
                {"coordination_session_id": "cs_b", "objective": "Task B", "status": "design"},
            ],
            "count": 2,
        },
    })

    method, url, body, params, headers = session._last_request
    assert "/coordination/sessions" in url
    assert params["owner_did"] == "did:agentnexus:owner1"

    captured = capsys.readouterr()
    assert "cs_a" in captured.out
    assert "cs_b" in captured.out


# ═══════════════════════════════════════════════════════════════════
# fork-session
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_fork_session(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "fork", "cs_test001",
        "--actor", "did:agentnexus:owner1",
        "--link-type", "review_fork",
        "--reason", "independent review",
    ], {
        "/coordination/sessions/fork": {
            "status": "forked",
            "session": {"coordination_session_id": "cs_child001"},
            "link_id": "sl_001",
        },
    })

    method, url, body, params, headers = session._last_request
    assert "/coordination/sessions/fork" in url
    assert body["coordination_session_id"] == "cs_test001"
    assert body["link_type"] == "review_fork"

    captured = capsys.readouterr()
    assert "cs_child001" in captured.out


# ═══════════════════════════════════════════════════════════════════
# submit-artifact
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_submit_artifact(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "artifact", "submit",
        "cs_test001", "design", "DesignArtifact",
        "did:agentnexus:designer",
        "vault://enc/design.md",
    ], {
        "/coordination/artifacts": {
            "status": "submitted",
            "artifact": {"artifact_id": "art_cli001", "stage": "design"},
        },
    })

    method, url, body, params, headers = session._last_request
    assert "/coordination/artifacts" in url
    assert body["stage"] == "design"
    assert body["artifact_type"] == "DesignArtifact"

    captured = capsys.readouterr()
    assert "art_cli001" in captured.out


# ═══════════════════════════════════════════════════════════════════
# submit-receipt
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_submit_receipt(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "receipt", "submit",
        "cs_test001", "design", "DesignReceipt",
        "did:agentnexus:reviewer", "approved",
        "--subject-artifact", "art_001",
    ], {
        "/coordination/receipts": {
            "status": "issued",
            "receipt": {"receipt_id": "rcpt_cli001", "decision": "approved"},
        },
    })

    method, url, body, params, headers = session._last_request
    assert "/coordination/receipts" in url
    assert body["decision"] == "approved"
    assert body["subject_artifact_id"] == "art_001"

    captured = capsys.readouterr()
    assert "rcpt_cli001" in captured.out


# ═══════════════════════════════════════════════════════════════════
# advance
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_advance(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "advance", "cs_test001",
        "--actor", "did:agentnexus:secretary",
    ], {
        "/advance": {
            "status": "advanced",
            "current_stage": "design",
            "previous_stage": "clarify",
        },
    })

    method, url, body, params, headers = session._last_request
    assert "/advance" in url
    assert body["actor_did"] == "did:agentnexus:secretary"

    captured = capsys.readouterr()
    assert "design" in captured.out


# ═══════════════════════════════════════════════════════════════════
# timeline
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_timeline(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "timeline", "cs_test001",
        "--actor", "did:agentnexus:secretary",
    ], {
        "/timeline": {
            "status": "ok",
            "timeline": [{"event_type": "session.created", "stage": "clarify"}],
        },
    })

    method, url, body, params, headers = session._last_request
    assert "/timeline" in url

    captured = capsys.readouterr()
    assert "session.created" in captured.out


# ═══════════════════════════════════════════════════════════════════
# closures
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_closures(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "closures", "cs_test001",
        "--actor", "did:agentnexus:secretary",
    ], {
        "/closures": {
            "status": "ok",
            "closures": [{"closure_id": "clo_001", "status": "recorded"}],
        },
    })

    method, url, body, params, headers = session._last_request
    assert "/closures" in url

    captured = capsys.readouterr()
    assert "clo_001" in captured.out


# ═══════════════════════════════════════════════════════════════════
# delegate
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_delegate(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "delegate", "cs_test001", "design",
        "did:agentnexus:designer",
        "--delegator", "did:agentnexus:secretary",
        "--role", "designer",
    ], {
        "/delegate": {
            "status": "delegated",
            "delegation": {"delegation_id": "del_001", "status": "pending"},
        },
    })

    method, url, body, params, headers = session._last_request
    assert "/delegate" in url
    assert body["delegatee_did"] == "did:agentnexus:designer"
    assert body["role"] == "designer"

    captured = capsys.readouterr()
    assert "del_001" in captured.out


# ═══════════════════════════════════════════════════════════════════
# accept-delegation
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_accept_delegation(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "accept", "del_001",
        "--actor", "did:agentnexus:designer",
    ], {
        "/accept": {"status": "accepted"},
    })

    method, url, body, params, headers = session._last_request
    assert "/accept" in url
    assert body["actor_did"] == "did:agentnexus:designer"

    captured = capsys.readouterr()
    assert "accepted" in captured.out


# ═══════════════════════════════════════════════════════════════════
# reject-delegation
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_reject_delegation(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "reject", "del_001",
        "--actor", "did:agentnexus:designer",
        "--reason", "not my expertise",
    ], {
        "/reject": {"status": "rejected"},
    })

    method, url, body, params, headers = session._last_request
    assert "/reject" in url
    assert body["reason"] == "not my expertise"

    captured = capsys.readouterr()
    assert "rejected" in captured.out


# ═══════════════════════════════════════════════════════════════════
# show (new SDK facade command)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_coordination_show(monkeypatch, capsys):
    """CLI show command displays session detail via SDK facade."""
    await _run_cmd(monkeypatch, capsys, [
        "show", "cs_test001",
        "--actor", "did:agentnexus:secretary",
    ], {
        # Use specific URL suffixes to avoid substring matching collisions
        "sessions/cs_test001/timeline": {
            "status": "ok",
            "timeline": [
                {"event_type": "session.created", "stage": "clarify"},
                {"event_type": "artifact.submitted", "stage": "design"},
            ],
        },
        "sessions/cs_test001/artifacts": {
            "status": "ok",
            "artifacts": [
                {"artifact_id": "art_001", "stage": "design", "artifact_type": "DesignArtifact"},
            ],
        },
        "sessions/cs_test001/receipts": {
            "status": "ok",
            "receipts": [
                {"receipt_id": "rcpt_001", "stage": "design", "decision": "approved"},
            ],
        },
        "sessions/cs_test001/closures": {
            "status": "ok",
            "closures": [{"closure_id": "clo_001", "sla_status": "met"}],
        },
        # Session detail last so it can still match /sessions/cs_test001 alone
        "/coordination/sessions/cs_test001": {
            "status": "ok",
            "session": {
                "coordination_session_id": "cs_test001",
                "objective": "Build demo login",
                "status": "completed",
                "workflow_id": "wf_demo",
                "owner_did": "did:agentnexus:owner1",
                "controller_did": "did:agentnexus:secretary",
            },
        },
    })

    captured = capsys.readouterr()
    assert "cs_test001" in captured.out
    assert "Build demo login" in captured.out
    assert "completed" in captured.out
    assert "session.created" in captured.out
    assert "art_001" in captured.out
    assert "rcpt_001" in captured.out
    assert "clo_001" in captured.out


# ═══════════════════════════════════════════════════════════════════
# demo (happy path)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_coordination_demo_happy_path(monkeypatch, capsys):
    """CLI demo command runs the full demo workflow via SDK facade."""
    await _run_cmd(monkeypatch, capsys, ["demo"], {
        "/health": {"status": "ok"},
        "/agents/local": {"agents": []},
        "/agents/register": {"did": "did:agentnexus:zDemoSecretary"},
        "/owner/register": {"did": "did:agentnexus:zDemoOwner", "public_key_hex": "ab" * 32, "profile": {"name": "Demo Owner"}},
        "/owner/bind": {"status": "bound"},
        "/enclaves": {"enclave_id": "demo_coordination_enclave"},
        "/coordination/coding/intake": {
            "status": "intake",
            "session": {"coordination_session_id": "cs_demo001"},
        },
        "/coordination/artifacts": {
            "status": "submitted",
            "artifact": {"artifact_id": "art_demo001"},
        },
        "/coordination/receipts": {
            "status": "issued",
            "receipt": {"receipt_id": "rcpt_demo001"},
        },
        "/advance": {
            "status": "advanced",
            "current_stage": "design",
        },
        "/timeline": {
            "status": "ok",
            "timeline": [{"event_type": "session.created"}],
        },
        "/closures": {
            "status": "ok",
            "closures": [{"closure_id": "clo_demo001", "status": "recorded"}],
        },
        "/coordination/sessions/cs_demo001": {
            "status": "ok",
            "session": {
                "coordination_session_id": "cs_demo001",
                "status": "completed",
            },
        },
    })

    captured = capsys.readouterr()
    assert "cs_demo001" in captured.out
    assert "Status : completed" in captured.out
    assert "Advance: ->" in captured.out
    assert "http://127.0.0.1:8765/ui/coordination/cs_demo001" in captured.out


# ═══════════════════════════════════════════════════════════════════
# demo — daemon unavailable
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_coordination_demo_daemon_unavailable(monkeypatch, capsys):
    """CLI demo fails gracefully when daemon is not running."""
    session = _make_fake_session({"*": {"status": "ok"}})
    # Override health check to raise on __aenter__ (simulating connection failure)
    def _health_get(url, *, headers=None, params=None, **kwargs):
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"status": "ok"})
        from aiohttp import ClientConnectorError
        resp.__aenter__ = AsyncMock(side_effect=ClientConnectorError(url, OSError("Connection refused")))
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp
    session.get = _health_get

    _patch_session(monkeypatch, session)

    from main import node_coordination_cmd
    await node_coordination_cmd(["demo"])

    captured = capsys.readouterr()
    assert "Cannot connect" in captured.out or "Error" in captured.out


# ═══════════════════════════════════════════════════════════════════
# timeline (dedicated command)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_coordination_timeline_dedicated(monkeypatch, capsys):
    """CLI timeline command displays timeline entries."""
    session = await _run_cmd(monkeypatch, capsys, [
        "timeline", "cs_test001",
        "--actor", "did:agentnexus:secretary",
    ], {
        "/timeline": {
            "status": "ok",
            "timeline": [
                {"event_type": "session.created", "stage": "clarify"},
                {"event_type": "artifact.submitted", "stage": "design"},
                {"event_type": "receipt.issued", "stage": "design"},
            ],
        },
    })

    captured = capsys.readouterr()
    assert "session.created" in captured.out
    assert "artifact.submitted" in captured.out
    assert "receipt.issued" in captured.out


# ═══════════════════════════════════════════════════════════════════
# list-sessions with workflow_id filter
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_list_sessions_with_workflow(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "list",
        "--owner", "did:agentnexus:owner1",
        "--actor", "did:agentnexus:actor1",
        "--workflow", "coding.v1",
    ], {
        "/coordination/sessions": {
            "status": "ok",
            "sessions": [],
            "count": 0,
        },
    })

    method, url, body, params, headers = session._last_request
    assert params["workflow_id"] == "coding.v1"


# ═══════════════════════════════════════════════════════════════════
# list-sessions with status filter
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cli_list_sessions_with_status(monkeypatch, capsys):
    session = await _run_cmd(monkeypatch, capsys, [
        "list",
        "--owner", "did:agentnexus:owner1",
        "--actor", "did:agentnexus:actor1",
        "--status", "completed",
    ], {
        "/coordination/sessions": {
            "status": "ok",
            "sessions": [],
            "count": 0,
        },
    })

    method, url, body, params, headers = session._last_request
    assert params["status"] == "completed"
