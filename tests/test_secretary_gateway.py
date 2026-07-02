"""Secretary Human Gateway — TDD Unit Tests (P0-5)

Design ref: docs/design/design-objective-loop-v1.1.md Sections 8, 4.4
"""
import pytest
import pytest_asyncio
import uuid


@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    """Isolated database — writes to temp dir."""
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
async def test_obj_gateway_handle_decision_gate_creates_request():
    """handle_decision_gate creates a decision_request from Loop Engine output."""
    from agent_net.node.secretary_gateway import handle_decision_gate
    from agent_net.storage import list_decision_requests

    action = {
        "action_type": "create_decision_gate",
        "stage": "implement",
        "reason": "Execution blocked: rm detected",
        "execution_id": "exec_test_1",
        "gate": "destructive_command",
    }

    result = await handle_decision_gate(
        coordination_session_id="cs_test",
        run_id="run_test",
        owner_did="did:agentnexus:owner1",
        controller_did="did:agentnexus:secretary1",
        action=action,
    )

    assert result is not None
    assert result["status"] == "pending"
    assert result["stage"] == "implement"
    assert "destructive" in result.get("question", "").lower()

    # Verify it's persisted
    decisions = await list_decision_requests(
        coordination_session_id="cs_test",
    )
    assert len(decisions) == 1
    assert decisions[0]["stage"] == "implement"


@pytest.mark.asyncio
async def test_obj_gateway_handle_decision_gate_max_retry():
    """handle_decision_gate for max_retry_exceeded gate."""
    from agent_net.node.secretary_gateway import handle_decision_gate

    action = {
        "action_type": "create_decision_gate",
        "stage": "clarify",
        "reason": "Stage clarify exceeded max retries (2)",
        "gate": "max_retry_exceeded",
    }

    result = await handle_decision_gate(
        coordination_session_id="cs_test2",
        run_id="run_test",
        owner_did="did:agentnexus:owner1",
        controller_did="did:agentnexus:secretary1",
        action=action,
    )

    assert result["status"] == "pending"
    assert "retry" in result.get("question", "").lower()


@pytest.mark.asyncio
async def test_obj_gateway_handle_decision_gate_low_confidence():
    """handle_decision_gate for low_confidence gate."""
    from agent_net.node.secretary_gateway import handle_decision_gate

    action = {
        "action_type": "create_decision_gate",
        "stage": "code_review",
        "reason": "Worker output could not be parsed",
        "gate": "low_confidence",
    }

    result = await handle_decision_gate(
        coordination_session_id="cs_test3",
        run_id="run_test",
        owner_did="did:agentnexus:owner1",
        controller_did="did:agentnexus:secretary1",
        action=action,
    )

    assert result["status"] == "pending"
    assert result["stage"] == "code_review"
