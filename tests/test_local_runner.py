"""Local Runner — TDD Unit Tests (P0-3)

Design ref: docs/design/design-objective-loop-v1.1.md Sections 6, 11
"""
import os
import tempfile
import yaml
import pytest
import pytest_asyncio
import uuid


# ═══════════════════════════════════════════════════════════════
# YAML Config Loading
# ═══════════════════════════════════════════════════════════════

VALID_CONFIG_YAML = """
daemon_url: http://127.0.0.1:8765
secretary_agent: OpenClawSecretary
poll_interval_sec: 2

defaults:
  workdir: /tmp/project
  timeout_sec: 1800
  max_retries_per_stage: 2

workers:
  claude_developer:
    agent_name: ClaudeDeveloper
    adapter: local_cli
    command: claude
    args: ["-p", "{prompt}"]
    roles: ["developer", "implement"]
    capabilities: ["Code", "Debug", "Implement"]

  pytest_runner:
    agent_name: LocalTestRunner
    adapter: local_cli
    command: python
    args: ["-m", "pytest"]
    roles: ["tester", "test"]
    capabilities: ["Test"]
"""


@pytest.fixture
def config_file():
    """Create a temporary YAML config file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(VALID_CONFIG_YAML)
        path = f.name
    yield path
    os.unlink(path)


def test_obj_runner_load_config_basic(config_file):
    """Load a valid YAML config and verify all fields."""
    from agent_net.node.local_runner import load_runner_config

    cfg = load_runner_config(config_file)
    assert cfg["daemon_url"] == "http://127.0.0.1:8765"
    assert cfg["poll_interval_sec"] == 2
    assert cfg["defaults"]["timeout_sec"] == 1800
    assert cfg["defaults"]["max_retries_per_stage"] == 2


def test_obj_runner_load_config_workers(config_file):
    """Workers section is parsed correctly."""
    from agent_net.node.local_runner import load_runner_config

    cfg = load_runner_config(config_file)
    assert "claude_developer" in cfg["workers"]
    assert "pytest_runner" in cfg["workers"]
    w = cfg["workers"]["claude_developer"]
    assert w["command"] == "claude"
    assert w["adapter"] == "local_cli"
    assert "developer" in w["roles"]
    assert "Code" in w["capabilities"]


def test_obj_runner_load_config_defaults():
    """Missing optional fields get sensible defaults."""
    from agent_net.node.local_runner import load_runner_config

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write("daemon_url: http://localhost:8765\n")
        path = f.name

    cfg = load_runner_config(path)
    assert cfg["poll_interval_sec"] == 2  # default
    assert cfg["defaults"]["timeout_sec"] == 1800
    assert cfg["defaults"]["max_retries_per_stage"] == 2
    assert cfg["workers"] == {}

    os.unlink(path)


def test_obj_runner_load_config_allowed_commands_default():
    """Default config includes common CLI agent command shims."""
    from agent_net.node.local_runner import load_runner_config

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write("daemon_url: http://localhost:8765\n")
        path = f.name

    try:
        cfg = load_runner_config(path)
        allowed = cfg["defaults"]["allowed_commands"]
        assert "claude.cmd" in allowed
        assert "codex.cmd" in allowed
        assert "openclaw.cmd" in allowed
    finally:
        os.unlink(path)


def test_obj_runner_load_config_does_not_mutate_defaults():
    """YAML defaults are merged without leaking into module-level DEFAULT_CONFIG."""
    from agent_net.node.local_runner import DEFAULT_CONFIG, load_runner_config

    original_timeout = DEFAULT_CONFIG["defaults"]["timeout_sec"]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write("daemon_url: http://localhost:8765\ndefaults:\n  timeout_sec: 7\n")
        path = f.name

    try:
        cfg = load_runner_config(path)
        assert cfg["defaults"]["timeout_sec"] == 7
        assert DEFAULT_CONFIG["defaults"]["timeout_sec"] == original_timeout
    finally:
        os.unlink(path)


def test_obj_runner_load_config_missing_daemon_url():
    """Config without daemon_url raises ValueError."""
    from agent_net.node.local_runner import load_runner_config

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write("poll_interval_sec: 5\nworkers: {}\n")
        path = f.name

    with pytest.raises(ValueError, match="daemon_url"):
        load_runner_config(path)

    os.unlink(path)


def test_obj_runner_config_nonexistent_file():
    """Nonexistent config file raises FileNotFoundError."""
    from agent_net.node.local_runner import load_runner_config

    with pytest.raises(FileNotFoundError):
        load_runner_config("/nonexistent/config.yaml")


# ═══════════════════════════════════════════════════════════════
# Worker matching
# ═══════════════════════════════════════════════════════════════

def test_obj_runner_find_worker_by_role():
    """Find a worker that matches a given role."""
    from agent_net.node.local_runner import load_runner_config, find_worker_for_role

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(VALID_CONFIG_YAML)
        path = f.name

    cfg = load_runner_config(path)
    w = find_worker_for_role(cfg, "developer")
    assert w is not None
    assert w["agent_name"] == "ClaudeDeveloper"

    w2 = find_worker_for_role(cfg, "tester")
    assert w2 is not None
    assert w2["agent_name"] == "LocalTestRunner"

    os.unlink(path)


def test_obj_runner_find_worker_by_capability():
    """Find a worker that matches a given capability."""
    from agent_net.node.local_runner import load_runner_config, find_worker_for_capability

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(VALID_CONFIG_YAML)
        path = f.name

    cfg = load_runner_config(path)
    w = find_worker_for_capability(cfg, "Test")
    assert w is not None
    assert w["agent_name"] == "LocalTestRunner"

    w2 = find_worker_for_capability(cfg, "Debug")
    assert w2 is not None
    assert w2["agent_name"] == "ClaudeDeveloper"

    os.unlink(path)


def test_obj_runner_find_worker_not_found():
    """No matching worker returns None."""
    from agent_net.node.local_runner import load_runner_config, find_worker_for_role

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(VALID_CONFIG_YAML)
        path = f.name

    cfg = load_runner_config(path)
    w = find_worker_for_role(cfg, "designer")
    assert w is None

    os.unlink(path)


# ═══════════════════════════════════════════════════════════════
# Runner loop (integration with real storage + fake backend)
# ═══════════════════════════════════════════════════════════════

@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    """Isolated database — writes to temp dir, never touches real data/agent_net.db."""
    import agent_net.storage as _s
    _db = tmp_path / 'agent_net.db'
    _orig = _s.DB_PATH
    _s.DB_PATH = _db
    _db.parent.mkdir(exist_ok=True)
    await _s.init_db()
    from agent_net.node._auth import _TOKEN_DID_BINDINGS
    _TOKEN_DID_BINDINGS.clear()
    yield
    _s.DB_PATH = _orig


@pytest.mark.asyncio
async def test_obj_runner_execute_single_stage():
    """Runner executes one stage via a fake backend and returns result."""
    from agent_net.node.local_runner import execute_stage

    result = await execute_stage(
        coordination_session_id="cs_test",
        run_id="run_test",
        stage="implement",
        worker_did="did:agentnexus:w1",
        backend_kind="local_cli",
        command=["python", "-c", "import json; print(json.dumps({'summary':'ok','status':'completed','artifact_type':'Test','artifact_body':'done','evidence_refs':[]}))"],
        constraints={"timeout_sec": 10},
    )
    assert result is not None
    assert result.status == "completed"
    assert result.artifact_type == "Test"


@pytest.mark.asyncio
async def test_obj_runner_execute_stage_blocked_command():
    """Runner blocks disallowed commands."""
    from agent_net.node.local_runner import execute_stage

    result = await execute_stage(
        coordination_session_id="cs_test",
        run_id="run_test",
        stage="implement",
        worker_did="did:agentnexus:w1",
        backend_kind="local_cli",
        command=["rm", "-rf", "/"],
        constraints={},
    )
    assert result.status == "blocked"


@pytest.mark.asyncio
async def test_obj_runner_execute_stage_rejects_unsupported_backend():
    """backend_kind is validated instead of being silently ignored."""
    from agent_net.node.local_runner import execute_stage

    with pytest.raises(ValueError, match="Unsupported backend_kind"):
        await execute_stage(
            coordination_session_id="cs_test",
            run_id="run_test",
            stage="implement",
            worker_did="did:agentnexus:w1",
            backend_kind="remote_cli",
            command=["python", "-c", "print('unused')"],
            constraints={},
        )
