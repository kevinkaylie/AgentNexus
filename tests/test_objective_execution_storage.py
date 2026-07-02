"""Objective Execution Storage — TDD Unit Tests (P0-1)

Tests for the new objective_executions table and CRUD functions.
Design ref: docs/design/design-objective-loop-v1.1.md Section 12
"""
import json
import time
import pytest
import pytest_asyncio
import uuid


@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    """Isolated database — writes to temp dir, never touches real data/agent_net.db."""
    import agent_net.storage as _s
    _db = tmp_path / 'agent_net.db'
    _orig = _s.DB_PATH
    _s.DB_PATH = _db
    _db.parent.mkdir(exist_ok=True)
    await _s.init_db()
    yield
    _s.DB_PATH = _orig


# ═══════════════════════════════════════════════════════════════
# objective_executions CRUD
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_obj_create_execution_minimal():
    """Create an objective execution with minimal fields, verify all defaults."""
    from agent_net.storage import create_objective_execution, get_objective_execution

    eid = f"exec_{uuid.uuid4().hex[:16]}"
    result = await create_objective_execution(
        execution_id=eid,
        coordination_session_id="cs_test_1",
        run_id="run_test_1",
        stage="implement",
        worker_did="did:agentnexus:test_worker",
        backend_kind="local_cli",
    )

    assert result["execution_id"] == eid
    assert result["status"] == "pending"
    assert result["attempt"] == 1
    assert result["lease_expires_at"] is None
    assert result["external_session_id"] == ""
    assert result["artifact_id"] == ""
    assert result["receipt_id"] == ""
    assert result["error"] == ""
    assert result["metadata"] == {}
    assert result["created_at"] > 0
    assert result["updated_at"] > 0

    # Verify retrieval
    loaded = await get_objective_execution(eid)
    assert loaded is not None
    assert loaded["coordination_session_id"] == "cs_test_1"
    assert loaded["backend_kind"] == "local_cli"


@pytest.mark.asyncio
async def test_obj_create_execution_full():
    """Create an objective execution with all optional fields."""
    from agent_net.storage import create_objective_execution, get_objective_execution

    eid = f"exec_{uuid.uuid4().hex[:16]}"
    ts = time.time() + 1800  # lease expires in 30min
    result = await create_objective_execution(
        execution_id=eid,
        coordination_session_id="cs_test_1",
        run_id="run_test_1",
        stage="code_review",
        worker_did="did:agentnexus:reviewer",
        backend_kind="local_cli",
        status="running",
        lease_expires_at=ts,
        attempt=2,
        external_session_id="cli-session-abc",
        metadata={"pid": 12345, "workdir": "/tmp/test"},
    )

    assert result["status"] == "running"
    assert result["attempt"] == 2
    assert result["lease_expires_at"] == ts
    assert result["external_session_id"] == "cli-session-abc"
    assert result["metadata"] == {"pid": 12345, "workdir": "/tmp/test"}

    loaded = await get_objective_execution(eid)
    assert loaded["status"] == "running"
    assert loaded["metadata"] == {"pid": 12345, "workdir": "/tmp/test"}


@pytest.mark.asyncio
async def test_obj_get_nonexistent():
    """Get nonexistent execution returns None."""
    from agent_net.storage import get_objective_execution
    result = await get_objective_execution("exec_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_obj_list_by_session():
    """List executions filtered by coordination_session_id."""
    from agent_net.storage import create_objective_execution, list_objective_executions

    cs_id_1 = "cs_list_1"
    cs_id_2 = "cs_list_2"

    # Create 3 executions for cs_id_1, 2 for cs_id_2
    for i in range(3):
        await create_objective_execution(
            execution_id=f"exec_a_{i}_{uuid.uuid4().hex[:8]}",
            coordination_session_id=cs_id_1,
            run_id="run_1",
            stage=f"stage_{i}",
            worker_did="did:agentnexus:w1",
            backend_kind="local_cli",
        )
    for i in range(2):
        await create_objective_execution(
            execution_id=f"exec_b_{i}_{uuid.uuid4().hex[:8]}",
            coordination_session_id=cs_id_2,
            run_id="run_2",
            stage=f"stage_b_{i}",  # different stages to avoid unique constraint
            worker_did="did:agentnexus:w2",
            backend_kind="local_service",
        )

    r1 = await list_objective_executions(coordination_session_id=cs_id_1)
    assert len(r1) == 3
    for e in r1:
        assert e["coordination_session_id"] == cs_id_1

    r2 = await list_objective_executions(coordination_session_id=cs_id_2)
    assert len(r2) == 2
    assert r2[0]["backend_kind"] == "local_service"


@pytest.mark.asyncio
async def test_obj_list_by_run_and_stage():
    """List executions filtered by run_id and stage."""
    from agent_net.storage import create_objective_execution, list_objective_executions

    await create_objective_execution(
        execution_id=f"exec_s1_{uuid.uuid4().hex[:8]}",
        coordination_session_id="cs_filter",
        run_id="run_1",
        stage="implement",
        worker_did="did:agentnexus:w1",
        backend_kind="local_cli",
    )
    await create_objective_execution(
        execution_id=f"exec_s2_{uuid.uuid4().hex[:8]}",
        coordination_session_id="cs_filter",
        run_id="run_1",
        stage="code_review",
        worker_did="did:agentnexus:w2",
        backend_kind="local_cli",
    )

    # Filter by stage only
    r = await list_objective_executions(
        coordination_session_id="cs_filter", stage="implement"
    )
    assert len(r) == 1
    assert r[0]["stage"] == "implement"

    # Filter by run_id only
    r = await list_objective_executions(
        coordination_session_id="cs_filter", run_id="run_1"
    )
    assert len(r) == 2


@pytest.mark.asyncio
async def test_obj_list_by_status():
    """List executions filtered by status."""
    from agent_net.storage import create_objective_execution, list_objective_executions

    await create_objective_execution(
        execution_id=f"exec_st_{uuid.uuid4().hex[:8]}",
        coordination_session_id="cs_status",
        run_id="run_1",
        stage="implement",
        worker_did="did:agentnexus:w1",
        backend_kind="local_cli",
        status="running",
    )
    await create_objective_execution(
        execution_id=f"exec_st2_{uuid.uuid4().hex[:8]}",
        coordination_session_id="cs_status",
        run_id="run_1",
        stage="implement",
        worker_did="did:agentnexus:w2",
        backend_kind="local_cli",
        status="completed",
    )

    r = await list_objective_executions(
        coordination_session_id="cs_status", status="running"
    )
    assert len(r) == 1
    assert r[0]["status"] == "running"


@pytest.mark.asyncio
async def test_obj_list_empty():
    """List executions for a session with no executions returns empty list."""
    from agent_net.storage import list_objective_executions
    r = await list_objective_executions(coordination_session_id="cs_empty")
    assert r == []


@pytest.mark.asyncio
async def test_obj_update_execution():
    """Update execution status, lease, and metadata."""
    from agent_net.storage import (
        create_objective_execution,
        update_objective_execution,
        get_objective_execution,
    )

    eid = f"exec_{uuid.uuid4().hex[:16]}"
    await create_objective_execution(
        execution_id=eid,
        coordination_session_id="cs_upd",
        run_id="run_1",
        stage="implement",
        worker_did="did:agentnexus:w1",
        backend_kind="local_cli",
    )

    new_lease = time.time() + 3600
    ok = await update_objective_execution(
        eid,
        status="running",
        lease_expires_at=new_lease,
        external_session_id="pid-999",
        metadata={"pid": 999},
    )
    assert ok is True

    loaded = await get_objective_execution(eid)
    assert loaded["status"] == "running"
    assert loaded["lease_expires_at"] == new_lease
    assert loaded["external_session_id"] == "pid-999"
    assert loaded["metadata"] == {"pid": 999}
    # updated_at should be newer
    assert loaded["updated_at"] >= loaded["created_at"]


@pytest.mark.asyncio
async def test_obj_update_nonexistent():
    """Update nonexistent execution returns False."""
    from agent_net.storage import update_objective_execution
    ok = await update_objective_execution("exec_nonexistent", status="running")
    assert ok is False


# ═══════════════════════════════════════════════════════════════
# mark_execution_result — idempotent result submission
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_obj_mark_result_completed():
    """mark_execution_result creates artifact/receipt refs and updates status."""
    from agent_net.storage import (
        create_objective_execution,
        mark_execution_result,
        get_objective_execution,
    )

    eid = f"exec_{uuid.uuid4().hex[:16]}"
    await create_objective_execution(
        execution_id=eid,
        coordination_session_id="cs_mark",
        run_id="run_1",
        stage="implement",
        worker_did="did:agentnexus:w1",
        backend_kind="local_cli",
        status="running",
    )

    result = await mark_execution_result(
        eid,
        artifact_id="art_abc",
        receipt_id="rcpt_abc",
        result_hash="sha256:deadbeef",
        status="completed",
    )
    assert result["execution_id"] == eid
    assert result["status"] == "completed"
    assert result["artifact_id"] == "art_abc"
    assert result["receipt_id"] == "rcpt_abc"

    loaded = await get_objective_execution(eid)
    assert loaded["status"] == "completed"
    assert loaded["artifact_id"] == "art_abc"
    assert loaded["completed_at"] is not None


@pytest.mark.asyncio
async def test_obj_mark_result_idempotent_same_hash():
    """Submitting the same result twice with same hash returns existing record."""
    from agent_net.storage import (
        create_objective_execution,
        mark_execution_result,
    )

    eid = f"exec_{uuid.uuid4().hex[:16]}"
    await create_objective_execution(
        execution_id=eid,
        coordination_session_id="cs_idem",
        run_id="run_1",
        stage="implement",
        worker_did="did:agentnexus:w1",
        backend_kind="local_cli",
        status="running",
    )

    r1 = await mark_execution_result(
        eid,
        artifact_id="art_abc",
        receipt_id="rcpt_abc",
        result_hash="sha256:deadbeef",
        status="completed",
    )
    # Second submission with same hash — should be idempotent
    r2 = await mark_execution_result(
        eid,
        artifact_id="art_abc",
        receipt_id="rcpt_abc",
        result_hash="sha256:deadbeef",
        status="completed",
    )
    assert r1["artifact_id"] == r2["artifact_id"]
    assert r1["receipt_id"] == r2["receipt_id"]


@pytest.mark.asyncio
async def test_obj_mark_result_idempotent_nonexistent():
    """mark_execution_result on nonexistent execution raises ValueError."""
    from agent_net.storage import mark_execution_result
    import pytest as pyt

    with pyt.raises(ValueError, match="not found"):
        await mark_execution_result(
            "exec_nonexistent",
            artifact_id="art_x",
            receipt_id="rcpt_x",
            result_hash="sha256:abc",
            status="completed",
        )
