"""Objective Loop Engine — TDD Unit Tests (P0-4)

Design ref: docs/design/design-objective-loop-v1.1.md Sections 4.2, 7, 8, 9
"""
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
    from agent_net.node._auth import _TOKEN_DID_BINDINGS
    _TOKEN_DID_BINDINGS.clear()
    yield
    _s.DB_PATH = _orig


async def _create_session(
    cs_id: str = "cs_loop_1",
    objective: str = "Implement login module",
    playbook_id: str = "coding.v1",
    status: str = "running",
    owner_did: str = "did:agentnexus:owner1",
    controller_did: str = "did:agentnexus:secretary1",
) -> dict:
    """Helper: create playbook, run, and coordination session."""
    from agent_net.storage import (
        create_coordination_session, create_playbook, create_playbook_run,
        get_playbook,
    )

    pb = await get_playbook(playbook_id)
    if pb is None:
        await create_playbook(
            playbook_id=playbook_id,
            name="Coding V1",
            stages=[
                {"name": "clarify", "role": "clarifier", "next": "design", "on_reject": ""},
                {"name": "design", "role": "designer", "next": "design_review", "on_reject": ""},
                {"name": "design_review", "role": "reviewer", "next": "implement", "on_reject": "design"},
                {"name": "implement", "role": "developer", "next": "code_review", "on_reject": ""},
                {"name": "code_review", "role": "reviewer", "next": "test", "on_reject": "implement"},
                {"name": "test", "role": "tester", "next": "final", "on_reject": "implement"},
                {"name": "final", "role": "coordinator", "next": "", "on_reject": ""},
            ],
        )

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    await create_playbook_run(
        run_id=run_id,
        playbook_id=playbook_id,
        enclave_id="enc_loop",
        playbook_name="Coding V1",
        coordination_session_id=cs_id,
    )

    sess = await create_coordination_session(
        coordination_session_id=cs_id,
        owner_did=owner_did,
        controller_did=controller_did,
        objective=objective,
        playbook_id=playbook_id,
        playbook_run_id=run_id,
        status=status,
        current_stage="clarify",
    )

    # Sync initial stage to the playbook_run
    from agent_net.storage import update_playbook_run
    await update_playbook_run(
        run_id,
        current_stage="clarify",
        status=status,
    )

    return sess


async def _create_execution(**kwargs) -> dict:
    """Helper: create an objective_execution record."""
    from agent_net.storage import create_objective_execution
    defaults = {
        "execution_id": f"exec_{uuid.uuid4().hex[:16]}",
        "coordination_session_id": "cs_loop_1",
        "run_id": "run_test",
        "stage": "implement",
        "worker_did": "did:agentnexus:w1",
        "backend_kind": "local_cli",
    }
    defaults.update(kwargs)
    return await create_objective_execution(**defaults)


# ═══════════════════════════════════════════════════════════════
# next_action() state machine tests
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_obj_engine_next_action_start_execution():
    """No execution for current stage → start_execution."""
    from agent_net.node.loop_engine import next_action

    sess = await _create_session(cs_id="cs_start_1")
    action = await next_action(
        coordination_session_id=sess["coordination_session_id"],
        controller_did=sess["controller_did"],
    )
    assert action["action_type"] == "start_execution"
    assert action["stage"] == "clarify"
    assert action["role"] == "clarifier"


@pytest.mark.asyncio
async def test_obj_engine_next_action_poll_execution():
    """Running execution for current stage → poll_execution."""
    from agent_net.node.loop_engine import next_action

    sess = await _create_session(cs_id="cs_poll_1")
    await _create_execution(
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="clarify",
        status="running",
    )
    action = await next_action(
        coordination_session_id=sess["coordination_session_id"],
        controller_did=sess["controller_did"],
    )
    assert action["action_type"] == "poll_execution"


@pytest.mark.asyncio
async def test_obj_engine_next_action_start_execution_when_timed_out():
    """Timed-out execution → start_execution (retry)."""
    from agent_net.node.loop_engine import next_action

    sess = await _create_session(cs_id="cs_reto_1")
    await _create_execution(
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="clarify",
        status="timed_out",
        attempt=1,
    )
    action = await next_action(
        coordination_session_id=sess["coordination_session_id"],
        controller_did=sess["controller_did"],
    )
    assert action["action_type"] == "start_execution"
    assert action["stage"] == "clarify"


@pytest.mark.asyncio
async def test_obj_engine_next_action_decision_gate_on_max_retry():
    """Retry count exceeded → create_decision_gate."""
    from agent_net.node.loop_engine import next_action

    sess = await _create_session(cs_id="cs_retmax_1")
    await _create_execution(
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="clarify",
        status="timed_out",
        attempt=5,
    )
    action = await next_action(
        coordination_session_id=sess["coordination_session_id"],
        controller_did=sess["controller_did"],
    )
    assert action["action_type"] == "create_decision_gate"


@pytest.mark.asyncio
async def test_obj_engine_next_action_advance_after_receipt():
    """Approved receipt for current stage → advance to next stage."""
    from agent_net.node.loop_engine import next_action
    from agent_net.storage import create_artifact, create_receipt

    sess = await _create_session(cs_id="cs_adv_1")

    art_id = f"art_{uuid.uuid4().hex[:12]}"
    await create_artifact(
        artifact_id=art_id,
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="clarify",
        artifact_type="RequirementSpec",
        producer_did=sess["controller_did"],
        content_ref="vault://enc_loop/clarify.md",
    )
    await create_receipt(
        receipt_id=f"rcpt_{uuid.uuid4().hex[:12]}",
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="clarify",
        receipt_type="DesignReceipt",
        issuer_did=sess["controller_did"],
        decision="approved",
        subject_artifact_id=art_id,
    )

    action = await next_action(
        coordination_session_id=sess["coordination_session_id"],
        controller_did=sess["controller_did"],
    )
    assert action["action_type"] == "advance"


@pytest.mark.asyncio
async def test_obj_engine_next_action_on_reject_back():
    """changes_requested receipt → start_execution for on_reject stage."""
    from agent_net.node.loop_engine import next_action
    from agent_net.storage import create_artifact, create_receipt
    from agent_net.storage import update_playbook_run, get_playbook_run

    sess = await _create_session(cs_id="cs_reject_1")

    run = await get_playbook_run(sess["playbook_run_id"])
    await update_playbook_run(
        sess["playbook_run_id"],
        current_stage="design_review",
        status="running",
        context=run.get("context", {}),
    )

    art_id = f"art_{uuid.uuid4().hex[:12]}"
    await create_artifact(
        artifact_id=art_id,
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="design_review",
        artifact_type="DesignReviewArtifact",
        producer_did=sess["controller_did"],
        content_ref="vault://enc_loop/design_review.md",
    )
    await create_receipt(
        receipt_id=f"rcpt_{uuid.uuid4().hex[:12]}",
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="design_review",
        receipt_type="ReviewReceipt",
        issuer_did=sess["controller_did"],
        decision="changes_requested",
        subject_artifact_id=art_id,
    )

    action = await next_action(
        coordination_session_id=sess["coordination_session_id"],
        controller_did=sess["controller_did"],
    )
    assert action["action_type"] == "start_execution"
    assert action["stage"] == "design"


@pytest.mark.asyncio
async def test_obj_engine_next_action_closed():
    """Final stage completed → closed."""
    from agent_net.node.loop_engine import next_action
    from agent_net.storage import create_artifact, create_receipt
    from agent_net.storage import update_playbook_run, get_playbook_run

    sess = await _create_session(cs_id="cs_closed_1")

    run = await get_playbook_run(sess["playbook_run_id"])
    await update_playbook_run(
        sess["playbook_run_id"],
        current_stage="final",
        status="running",
        context=run.get("context", {}),
    )

    art_id = f"art_{uuid.uuid4().hex[:12]}"
    await create_artifact(
        artifact_id=art_id,
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="final",
        artifact_type="DeliveryManifest",
        producer_did=sess["controller_did"],
        content_ref="vault://enc_loop/final.md",
    )
    await create_receipt(
        receipt_id=f"rcpt_{uuid.uuid4().hex[:12]}",
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="final",
        receipt_type="FinalResultReceipt",
        issuer_did=sess["controller_did"],
        decision="approved",
        subject_artifact_id=art_id,
    )

    action = await next_action(
        coordination_session_id=sess["coordination_session_id"],
        controller_did=sess["controller_did"],
    )
    assert action["action_type"] == "closed"


@pytest.mark.asyncio
async def test_obj_engine_next_action_blocked_execution():
    """Blocked execution → create_decision_gate."""
    from agent_net.node.loop_engine import next_action

    sess = await _create_session(cs_id="cs_blocked_1")
    await _create_execution(
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="clarify",
        status="blocked",
        metadata={"gate": "destructive_command", "reason": "rm detected"},
    )

    action = await next_action(
        coordination_session_id=sess["coordination_session_id"],
        controller_did=sess["controller_did"],
    )
    assert action["action_type"] == "create_decision_gate"


@pytest.mark.asyncio
async def test_obj_engine_next_action_wait_pending_decision():
    """Pending unresolved decision → wait."""
    from agent_net.node.loop_engine import next_action
    from agent_net.storage import create_decision_request

    sess = await _create_session(cs_id="cs_wait_1")
    await create_decision_request(
        decision_id=f"dec_{uuid.uuid4().hex[:12]}",
        owner_did=sess["owner_did"],
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="clarify",
        requested_by_did=sess["controller_did"],
        question="Allow network access?",
    )

    action = await next_action(
        coordination_session_id=sess["coordination_session_id"],
        controller_did=sess["controller_did"],
    )
    assert action["action_type"] == "wait"


@pytest.mark.asyncio
async def test_obj_engine_next_action_ignores_pending_decision_from_other_stage():
    """A stale pending decision from another stage must not deadlock the active stage."""
    from agent_net.node.loop_engine import next_action
    from agent_net.storage import create_decision_request, update_playbook_run

    sess = await _create_session(cs_id="cs_wait_other_stage")
    await update_playbook_run(
        sess["playbook_run_id"],
        current_stage="implement",
        status="running",
    )
    await create_decision_request(
        decision_id=f"dec_{uuid.uuid4().hex[:12]}",
        owner_did=sess["owner_did"],
        coordination_session_id=sess["coordination_session_id"],
        run_id=sess["playbook_run_id"],
        stage="design",
        requested_by_did=sess["controller_did"],
        question="Stale design decision",
    )

    action = await next_action(
        coordination_session_id=sess["coordination_session_id"],
        controller_did=sess["controller_did"],
    )
    assert action["action_type"] == "start_execution"
    assert action["stage"] == "implement"
