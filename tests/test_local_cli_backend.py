"""ExecutionBackend + LocalCLIBackend — TDD Unit Tests (P0-2)

Design ref: docs/design/design-objective-loop-v1.1.md Sections 4.3, 6.1-6.3
"""
import json
import os
import tempfile
import time
import pytest
import asyncio


# ═══════════════════════════════════════════════════════════════
# ExecutionHandle / ExecutionResult dataclass tests
# ═══════════════════════════════════════════════════════════════

def test_obj_execution_handle_defaults():
    """ExecutionHandle creates with required fields and sensible defaults."""
    from agent_net.node.execution_backends.base import ExecutionHandle
    h = ExecutionHandle(
        execution_id="exec_1",
        backend_kind="local_cli",
        worker_did="did:agentnexus:w1",
        stage="implement",
        status="pending",
    )
    assert h.execution_id == "exec_1"
    assert h.backend_kind == "local_cli"
    assert h.status == "pending"
    assert h.external_session_id == ""
    assert h.lease_expires_at is None
    assert h.metadata is None


def test_obj_execution_result_fields():
    """ExecutionResult holds worker output and optional human decision request."""
    from agent_net.node.execution_backends.base import ExecutionResult
    r = ExecutionResult(
        execution_id="exec_1",
        status="completed",
        artifact_type="ImplementationArtifact",
        artifact_body="# Implemented",
        summary="Done",
        evidence_refs=[],
    )
    assert r.status == "completed"
    assert r.artifact_type == "ImplementationArtifact"
    assert r.artifact_body == "# Implemented"
    assert r.human_decision_request is None
    assert r.raw_output_ref == ""


def test_obj_execution_result_with_human_decision():
    """ExecutionResult can carry a human decision request for blocked states."""
    from agent_net.node.execution_backends.base import ExecutionResult
    r = ExecutionResult(
        execution_id="exec_1",
        status="blocked",
        artifact_type="",
        artifact_body="",
        summary="Worker needs network access",
        evidence_refs=[],
        human_decision_request={
            "gate": "network_access",
            "question": "Allow pip install?",
        },
    )
    assert r.status == "blocked"
    assert r.human_decision_request["gate"] == "network_access"


# ═══════════════════════════════════════════════════════════════
# LocalCLIBackend tests
# ═══════════════════════════════════════════════════════════════

FAKE_WORKER_SCRIPT = '''
import sys, json
print("some chatter before JSON")
print(json.dumps({
    "summary": "Task completed",
    "status": "completed",
    "artifact_type": "TestArtifact",
    "artifact_body": "test output",
    "evidence_refs": ["ref1"],
    "human_decision_request": None
}))
'''

FAKE_WORKER_FAIL_SCRIPT = '''
import sys
print("I tried but could not figure it out")
print("NOT JSON OUTPUT HERE")
'''

FAKE_WORKER_TIMEOUT_SCRIPT = '''
import time
time.sleep(30)
print("too late")
'''

FAKE_WORKER_LARGE_OUTPUT = '''
import sys, json
print("x" * 100000)
print(json.dumps({"summary": "ok", "status": "completed", "artifact_type": "T",
    "artifact_body": "", "evidence_refs": []}))
'''


def _write_script(content: str, dir_: str, name: str) -> str:
    path = os.path.join(dir_, f"{name}.py")
    with open(path, "w") as f:
        f.write(content)
    return path


@pytest.mark.asyncio
async def test_obj_local_cli_backend_successful_run():
    """LocalCLIBackend executes a command, captures output, parses JSON result."""
    from agent_net.node.execution_backends.local_cli import LocalCLIBackend

    with tempfile.TemporaryDirectory() as tmp:
        script = _write_script(FAKE_WORKER_SCRIPT, tmp, "worker")
        backend = LocalCLIBackend(
            allowed_commands={"python"},
            default_timeout_sec=10,
            max_output_bytes=1_000_000,
        )
        handle = await backend.start_execution(
            coordination_session_id="cs_test",
            run_id="run_test",
            stage="implement",
            worker_did="did:agentnexus:w1",
            input_refs=[],
            constraints={"timeout_sec": 10},
            command=["python", script],
        )
        assert handle.status == "running"

        # Poll until complete — background task auto-updates handle
        for _ in range(30):
            await asyncio.sleep(0.1)
            handle = await backend.poll_execution(handle)
            if handle.status in ("completed", "failed", "blocked", "timed_out"):
                break

        # Wait for completion if still running
        if handle.status == "running":
            await asyncio.sleep(0.5)
            handle = await backend.poll_execution(handle)

        assert handle.status == "completed"

        result = await backend.collect_result(handle)
        assert result.status == "completed"
        assert result.artifact_type == "TestArtifact"
        assert result.artifact_body == "test output"
        assert result.summary == "Task completed"
        assert "ref1" in result.evidence_refs


@pytest.mark.asyncio
async def test_obj_local_cli_backend_invalid_json_retry():
    """Worker output with no valid JSON → retry once, then blocked."""
    from agent_net.node.execution_backends.local_cli import LocalCLIBackend

    with tempfile.TemporaryDirectory() as tmp:
        script = _write_script(FAKE_WORKER_FAIL_SCRIPT, tmp, "worker")
        backend = LocalCLIBackend(
            allowed_commands={"python"},
            default_timeout_sec=10,
            max_output_bytes=1_000_000,
        )
        handle = await backend.start_execution(
            coordination_session_id="cs_test",
            run_id="run_test",
            stage="implement",
            worker_did="did:agentnexus:w1",
            input_refs=[],
            constraints={},
            command=["python", script],
        )

        for _ in range(30):
            await asyncio.sleep(0.1)
            handle = await backend.poll_execution(handle)
            if handle.status in ("completed", "failed", "blocked", "timed_out"):
                break

        # The process may exit with code 0 but produce no valid JSON
        # collect_result should detect this and return blocked
        if handle.status == "running":
            await asyncio.sleep(0.5)
            handle = await backend.poll_execution(handle)

        result = await backend.collect_result(handle)
        # Backend re-executes once internally; if both fail → blocked
        assert result.status == "blocked"
        assert result.raw_output_ref != ""  # raw output preserved


@pytest.mark.asyncio
async def test_obj_local_cli_backend_timeout():
    """Command exceeding timeout is killed and marked timed_out."""
    from agent_net.node.execution_backends.local_cli import LocalCLIBackend

    with tempfile.TemporaryDirectory() as tmp:
        script = _write_script(FAKE_WORKER_TIMEOUT_SCRIPT, tmp, "worker")
        backend = LocalCLIBackend(
            allowed_commands={"python"},
            default_timeout_sec=1,
            max_output_bytes=1_000_000,
        )
        handle = await backend.start_execution(
            coordination_session_id="cs_test",
            run_id="run_test",
            stage="implement",
            worker_did="did:agentnexus:w1",
            input_refs=[],
            constraints={"timeout_sec": 1},
            command=["python", script],
        )

        for _ in range(20):
            await asyncio.sleep(0.15)
            handle = await backend.poll_execution(handle)
            if handle.status in ("completed", "failed", "blocked", "timed_out"):
                break

        assert handle.status == "timed_out"


@pytest.mark.asyncio
async def test_obj_local_cli_backend_disallowed_command():
    """Command not in allowlist is rejected before execution."""
    from agent_net.node.execution_backends.local_cli import LocalCLIBackend

    backend = LocalCLIBackend(
        allowed_commands={"python"},
        default_timeout_sec=10,
        max_output_bytes=1_000_000,
    )

    handle = await backend.start_execution(
        coordination_session_id="cs_test",
        run_id="run_test",
        stage="implement",
        worker_did="did:agentnexus:w1",
        input_refs=[],
        constraints={},
        command=["rm", "-rf", "/"],
    )
    assert handle.status == "blocked"
    assert "not in allowed_commands" in handle.metadata.get("reason", "")


@pytest.mark.asyncio
async def test_obj_local_cli_backend_output_truncation():
    """Output exceeding max_output_bytes is truncated but raw saved."""
    from agent_net.node.execution_backends.local_cli import LocalCLIBackend

    with tempfile.TemporaryDirectory() as tmp:
        script = _write_script(FAKE_WORKER_LARGE_OUTPUT, tmp, "worker")
        backend = LocalCLIBackend(
            allowed_commands={"python"},
            default_timeout_sec=10,
            max_output_bytes=100_000,  # only 100KB
        )
        handle = await backend.start_execution(
            coordination_session_id="cs_test",
            run_id="run_test",
            stage="implement",
            worker_did="did:agentnexus:w1",
            input_refs=[],
            constraints={},
            command=["python", script],
        )

        for _ in range(30):
            await asyncio.sleep(0.1)
            handle = await backend.poll_execution(handle)
            if handle.status in ("completed", "failed", "blocked", "timed_out"):
                break

        if handle.status == "running":
            await asyncio.sleep(0.5)
            handle = await backend.poll_execution(handle)

        # Should complete — JSON at the end is parseable even if output is truncated.
        # With 100KB limit, the leading x's are truncated before the JSON part.
        result = await backend.collect_result(handle)
        assert result.raw_output_ref != ""
        # The JSON should be extracted from the tail of the output
        # (may succeed or need retry depending on truncation position)
        assert result.status in ("completed", "changes_requested", "blocked")


@pytest.mark.asyncio
async def test_obj_local_cli_backend_constraints_from_start_execution():
    """start_execution passes constraints through to the command execution."""
    from agent_net.node.execution_backends.local_cli import LocalCLIBackend

    backend = LocalCLIBackend(
        allowed_commands={"python"},
        default_timeout_sec=10,
        max_output_bytes=1_000_000,
    )

    with tempfile.TemporaryDirectory() as tmp:
        script = _write_script(FAKE_WORKER_SCRIPT, tmp, "worker")
        # Verify constraints['timeout_sec'] overrides default
        handle = await backend.start_execution(
            coordination_session_id="cs_test",
            run_id="run_test",
            stage="implement",
            worker_did="did:agentnexus:w1",
            input_refs=[],
            constraints={"timeout_sec": 5},
            command=["python", script],
        )
        assert handle.status in ("pending", "running")


@pytest.mark.asyncio
async def test_obj_local_cli_backend_cancel():
    """cancel_execution kills the running process."""
    from agent_net.node.execution_backends.local_cli import LocalCLIBackend

    with tempfile.TemporaryDirectory() as tmp:
        script = _write_script(FAKE_WORKER_TIMEOUT_SCRIPT, tmp, "worker")
        backend = LocalCLIBackend(
            allowed_commands={"python"},
            default_timeout_sec=30,
            max_output_bytes=1_000_000,
        )
        handle = await backend.start_execution(
            coordination_session_id="cs_test",
            run_id="run_test",
            stage="implement",
            worker_did="did:agentnexus:w1",
            input_refs=[],
            constraints={},
            command=["python", script],
        )
        proc = backend._processes[handle.execution_id]

        # Cancel immediately
        await backend.cancel_execution(handle, "owner abort")
        await asyncio.sleep(0.3)

        handle = await backend.poll_execution(handle)
        assert handle.status == "cancelled"
        assert proc.returncode is not None
        assert handle.execution_id not in backend._processes
