"""Objective Loop V1.1 — Execution API Integration Tests

Design ref: docs/design/design-objective-loop-v1.1.md Section 11.2-11.3
"""
import json
import tempfile
import pytest
import pytest_asyncio
import uuid


@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    """Isolated database — writes to temp dir, never touches real data/agent_net.db."""
    import agent_net.storage as s
    db = tmp_path / "agent_net.db"
    orig = s.DB_PATH
    s.DB_PATH = db
    db.parent.mkdir(exist_ok=True)
    if db.exists():
        db.unlink()
    await s.init_db()
    from agent_net.node._auth import _TOKEN_DID_BINDINGS
    _TOKEN_DID_BINDINGS.clear()
    yield
    s.DB_PATH = orig


def _auth_header():
    from agent_net.node._auth import init_daemon_token
    return {"Authorization": f"Bearer {init_daemon_token()}"}


async def _owner(name: str = "ExecOwner") -> dict:
    from agent_net.storage import register_owner
    return await register_owner(name)


async def _session(owner: dict, objective: str = "Test objective") -> dict:
    """Create a coordination session with coding.v1 playbook, returning session dict."""
    from agent_net.storage import create_coordination_session, create_playbook_run
    from agent_net.storage import get_playbook, create_playbook, update_playbook_run

    pb = await get_playbook("coding.v1")
    if pb is None:
        await create_playbook("coding.v1", "Coding V1", [
            {"name": "clarify", "role": "clarifier", "next": "design", "on_reject": ""},
            {"name": "design", "role": "designer", "next": "design_review", "on_reject": ""},
            {"name": "design_review", "role": "reviewer", "next": "implement", "on_reject": "design"},
            {"name": "implement", "role": "developer", "next": "code_review", "on_reject": ""},
            {"name": "code_review", "role": "reviewer", "next": "test", "on_reject": "implement"},
            {"name": "test", "role": "tester", "next": "final", "on_reject": "implement"},
            {"name": "final", "role": "coordinator", "next": "", "on_reject": ""},
        ])

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    await create_playbook_run(run_id, enclave_id="enc_api", playbook_id="coding.v1",
                              playbook_name="Coding V1", coordination_session_id=cs_id)
    sess = await create_coordination_session(
        coordination_session_id=cs_id,
        owner_did=owner["did"],
        controller_did=owner["did"],
        objective=objective,
        playbook_run_id=run_id,
        current_stage="clarify",
    )
    await update_playbook_run(run_id, current_stage="clarify", status="running")
    return sess


# ═══════════════════════════════════════════════════════════════
# GET /coordination/sessions/{id}/next-action
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_obj_api_next_action_start_execution():
    """GET next-action for a fresh session returns start_execution."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("NextActionOwner")
    sess = await _session(owner)
    client = TestClient(app, headers=_auth_header())

    resp = client.get(
        f"/coordination/sessions/{sess['coordination_session_id']}/next-action",
        params={"actor_did": owner["did"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["action"]["action_type"] == "start_execution"
    assert data["action"]["stage"] == "clarify"


@pytest.mark.asyncio
async def test_obj_api_next_action_unauthorized():
    """GET next-action without auth returns 401."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/coordination/sessions/cs_nonexistent/next-action")
    assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════
# POST /coordination/executions
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_obj_api_create_execution():
    """POST /coordination/executions creates an execution record."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("CreateExecOwner")
    sess = await _session(owner)
    client = TestClient(app, headers=_auth_header())

    resp = client.post("/coordination/executions", json={
        "coordination_session_id": sess["coordination_session_id"],
        "run_id": sess["playbook_run_id"],
        "stage": "clarify",
        "worker_did": owner["did"],
        "backend_kind": "local_cli",
        "actor_did": owner["did"],
        "lease_ttl_sec": 1800,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"
    assert data["execution"]["stage"] == "clarify"
    assert data["execution"]["backend_kind"] == "local_cli"
    assert data["execution"]["status"] == "pending"
    assert "execution_id" in data["execution"]


@pytest.mark.asyncio
async def test_obj_api_create_execution_missing_fields():
    """POST /coordination/executions with missing required fields returns 422."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    client = TestClient(app, headers=_auth_header())
    resp = client.post("/coordination/executions", json={
        "coordination_session_id": "cs_test",
        # missing run_id, stage, worker_did, etc.
    })
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# PATCH /coordination/executions/{id}
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_obj_api_update_execution():
    """PATCH /coordination/executions/{id} updates execution status."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("UpdateExecOwner")
    sess = await _session(owner)
    client = TestClient(app, headers=_auth_header())

    # Create first
    create_resp = client.post("/coordination/executions", json={
        "coordination_session_id": sess["coordination_session_id"],
        "run_id": sess["playbook_run_id"],
        "stage": "clarify",
        "worker_did": owner["did"],
        "backend_kind": "local_cli",
        "actor_did": owner["did"],
        "lease_ttl_sec": 1800,
    })
    eid = create_resp.json()["execution"]["execution_id"]

    # Update to running
    resp = client.patch(f"/coordination/executions/{eid}", json={
        "actor_did": owner["did"],
        "status": "running",
        "external_session_id": "ext-session-1",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"


# ═══════════════════════════════════════════════════════════════
# POST /coordination/executions/{id}/result
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_obj_api_submit_execution_result():
    """POST /coordination/executions/{id}/result submits result + creates artifact/receipt."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("ResultExecOwner")
    sess = await _session(owner)
    client = TestClient(app, headers=_auth_header())

    # Create execution
    create_resp = client.post("/coordination/executions", json={
        "coordination_session_id": sess["coordination_session_id"],
        "run_id": sess["playbook_run_id"],
        "stage": "clarify",
        "worker_did": owner["did"],
        "backend_kind": "local_cli",
        "actor_did": owner["did"],
        "lease_ttl_sec": 1800,
    })
    eid = create_resp.json()["execution"]["execution_id"]

    # Submit result
    resp = client.post(f"/coordination/executions/{eid}/result", json={
        "actor_did": owner["did"],
        "result": {
            "status": "completed",
            "artifact_type": "RequirementSpec",
            "artifact_body": "# Requirements\n- Login flow",
            "summary": "Requirements clarified",
            "evidence_refs": [],
            "human_decision_request": None,
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert "artifact_id" in data
    assert "receipt_id" in data


@pytest.mark.asyncio
async def test_obj_api_submit_result_idempotent():
    """Submitting same result twice to same execution is idempotent."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("IdemExecOwner")
    sess = await _session(owner)
    client = TestClient(app, headers=_auth_header())

    create_resp = client.post("/coordination/executions", json={
        "coordination_session_id": sess["coordination_session_id"],
        "run_id": sess["playbook_run_id"],
        "stage": "clarify",
        "worker_did": owner["did"],
        "backend_kind": "local_cli",
        "actor_did": owner["did"],
        "lease_ttl_sec": 1800,
    })
    eid = create_resp.json()["execution"]["execution_id"]

    result_payload = {
        "actor_did": owner["did"],
        "result": {
            "status": "completed",
            "artifact_type": "RequirementSpec",
            "artifact_body": "dup",
            "summary": "done",
            "evidence_refs": [],
            "human_decision_request": None,
        },
    }
    r1 = client.post(f"/coordination/executions/{eid}/result", json=result_payload)
    r2 = client.post(f"/coordination/executions/{eid}/result", json=result_payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["artifact_id"] == r2.json()["artifact_id"]
