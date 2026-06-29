"""Runner Poll Loop — TDD Unit Tests

Design ref: docs/design/design-objective-loop-v1.1.md Sections 4.2, 6, 11
"""
import pytest
import pytest_asyncio
import uuid
from unittest.mock import AsyncMock, patch, MagicMock


def test_obj_runner_build_constraints_passes_agent_adapter_options():
    """Worker-level adapter settings are passed into backend constraints."""
    from agent_net.node.runner_loop import _build_constraints

    config = {
        "defaults": {
            "timeout_sec": 30,
            "allowed_commands": ["python", "openclaw.cmd"],
            "output_adapter": "agentnexus_json_v1",
            "artifact_type": "TextArtifact",
        },
    }
    worker = {
        "timeout_sec": 10,
        "output_adapter": "openclaw_json",
        "output_text_paths": ["meta.finalAssistantRawText"],
        "artifact_type": "OpenClawArtifact",
    }

    constraints = _build_constraints(config, worker)

    assert constraints["timeout_sec"] == 10
    assert constraints["allowed_commands"] == ["python", "openclaw.cmd"]
    assert constraints["output_adapter"] == "openclaw_json"
    assert constraints["output_text_paths"] == ["meta.finalAssistantRawText"]
    assert constraints["artifact_type"] == "OpenClawArtifact"


def test_obj_runner_substitute_template_args_supports_stage_variables():
    """Command templates can include prompt and runtime identifiers."""
    from agent_net.node.runner_loop import _substitute_template_args

    args = _substitute_template_args(
        ["agent:agentnexus:{stage}", "{role}", "{run_id}", "{prompt}"],
        "hello",
        stage="implement",
        role="developer",
        run_id="run_123",
    )

    assert args == ["agent:agentnexus:implement", "developer", "run_123", "hello"]


# ═══════════════════════════════════════════════════════════════
# Runner tick() — single iteration of the poll loop
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_obj_runner_tick_processes_start_execution():
    """Runner tick finds a running session, gets start_execution, runs worker, submits result."""
    from agent_net.node.runner_loop import runner_tick

    fake_config = {
        "daemon_url": "http://localhost:8765",
        "defaults": {"timeout_sec": 30, "max_retries_per_stage": 2},
        "workers": {
            "fake_dev": {
                "agent_name": "FakeDev",
                "adapter": "local_cli",
                "command": "python",
                "args": ["-c", "print('{}')"],
                "roles": ["developer"],
                "capabilities": ["Code"],
            }
        },
    }
    session_id = f"cs_{uuid.uuid4().hex[:12]}"
    run_id = f"run_{uuid.uuid4().hex[:12]}"

    # Fake API responses
    async def fake_list_sessions(**kwargs):
        return [{"coordination_session_id": session_id, "playbook_run_id": run_id, "objective": "Test"}]

    async def fake_next_action(sid, actor):
        return {
            "action_type": "start_execution",
            "stage": "implement",
            "role": "developer",
            "reason": "No artifact",
        }

    fake_result_handle = None

    async def fake_create_execution(**body):
        nonlocal fake_result_handle
        eid = f"exec_{uuid.uuid4().hex[:12]}"
        fake_result_handle = eid
        return {"status": "created", "execution": {"execution_id": eid, "stage": "implement"}}

    async def fake_submit_result(eid, result_body):
        return {"status": "accepted", "artifact_id": "art_1", "receipt_id": "rcpt_1"}

    actions = await runner_tick(
        config=fake_config,
        list_sessions=fake_list_sessions,
        get_next_action=fake_next_action,
        create_execution=fake_create_execution,
        submit_result=fake_submit_result,
    )

    assert len(actions) >= 1
    assert actions[0]["action"] == "start_execution"
    assert actions[0]["session_id"] == session_id


@pytest.mark.asyncio
async def test_obj_runner_tick_no_sessions():
    """Runner tick with no running sessions returns empty list."""
    from agent_net.node.runner_loop import runner_tick

    fake_config = {"daemon_url": "http://localhost:8765", "defaults": {}, "workers": {}}

    async def fake_list_sessions(**kwargs):
        return []

    actions = await runner_tick(
        config=fake_config,
        list_sessions=fake_list_sessions,
        get_next_action=AsyncMock(),
        create_execution=AsyncMock(),
        submit_result=AsyncMock(),
    )

    assert actions == []


@pytest.mark.asyncio
async def test_obj_runner_tick_no_matching_worker():
    """Runner tick with start_execution but no matching worker → logs and skips."""
    from agent_net.node.runner_loop import runner_tick

    fake_config = {
        "daemon_url": "http://localhost:8765",
        "defaults": {},
        "workers": {
            "tester_only": {
                "agent_name": "Tester",
                "command": "python",
                "args": [],
                "roles": ["tester"],
                "capabilities": ["Test"],
            }
        },
    }

    async def fake_list_sessions(**kwargs):
        return [{"coordination_session_id": "cs_1", "playbook_run_id": "r1"}]

    async def fake_next_action(sid, actor):
        return {
            "action_type": "start_execution",
            "stage": "implement",
            "role": "developer",  # no worker has this role
            "reason": "No artifact",
        }

    actions = await runner_tick(
        config=fake_config,
        list_sessions=fake_list_sessions,
        get_next_action=fake_next_action,
        create_execution=AsyncMock(),
        submit_result=AsyncMock(),
    )

    # Should return a skip action (no matching worker)
    assert len(actions) == 1
    assert actions[0]["action"] == "skip"
    assert "No worker for role" in actions[0]["reason"]


@pytest.mark.asyncio
async def test_obj_runner_tick_closed_session_skipped():
    """Runner tick with closed session → logged and skipped."""
    from agent_net.node.runner_loop import runner_tick

    fake_config = {"daemon_url": "http://localhost:8765", "defaults": {}, "workers": {}}

    async def fake_list_sessions(**kwargs):
        return [{"coordination_session_id": "cs_done", "playbook_run_id": "r_done"}]

    async def fake_next_action(sid, actor):
        return {"action_type": "closed", "stage": "final", "reason": "Done"}

    actions = await runner_tick(
        config=fake_config,
        list_sessions=fake_list_sessions,
        get_next_action=fake_next_action,
        create_execution=AsyncMock(),
        submit_result=AsyncMock(),
    )

    assert len(actions) == 1
    assert actions[0]["action"] == "closed"


# ═══════════════════════════════════════════════════════════════
# Runner loop integration (real execute_stage via backend)
# ═══════════════════════════════════════════════════════════════

@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    """Isolated database — writes to temp dir, never touches real data/agent_net.db."""
    import agent_net.storage as _s
    db = tmp_path / 'agent_net.db'
    _orig = _s.DB_PATH
    _s.DB_PATH = db
    db.parent.mkdir(exist_ok=True)
    await _s.init_db()
    from agent_net.node._auth import _TOKEN_DID_BINDINGS
    _TOKEN_DID_BINDINGS.clear()
    yield
    _s.DB_PATH = _orig


@pytest.mark.asyncio
async def test_obj_runner_process_action_executes_real_backend():
    """process_action with start_execution runs a real fake worker and gets result."""
    from agent_net.node.runner_loop import process_action
    from agent_net.node.local_runner import load_runner_config
    import tempfile, os

    # Write a minimal config file
    config_yaml = """
daemon_url: http://127.0.0.1:8765
defaults:
  timeout_sec: 10
  max_retries_per_stage: 2
workers:
  fake_dev:
    agent_name: FakeDev
    adapter: local_cli
    command: python
    args: ["-c", "import json; print(json.dumps({'summary':'ok','status':'completed','artifact_type':'Impl','artifact_body':'done','evidence_refs':[]}))"]
    roles: ["developer", "implement"]
    capabilities: ["Code"]
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_path = f.name

    cfg = load_runner_config(config_path)

    action = {
        "action_type": "start_execution",
        "stage": "implement",
        "role": "developer",
        "reason": "No artifact",
    }

    result = await process_action(
        config=cfg,
        session_id="cs_test",
        run_id="run_test",
        action=action,
        worker_did="did:agentnexus:w1",
    )

    assert result is not None
    assert result.status == "completed"
    assert result.artifact_type == "Impl"

    os.unlink(config_path)
