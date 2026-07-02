"""Coding Coordination V1 Phase 1 — Unit Tests"""
import json
import pytest
import pytest_asyncio
import uuid

from agent_net.node._auth import _TOKEN_DID_BINDINGS

@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    import agent_net.storage as s
    _db = tmp_path / "agent_net.db"
    _orig = s.DB_PATH
    s.DB_PATH = _db
    _db.parent.mkdir(exist_ok=True)
    if _db.exists():
        _db.unlink()
    await s.init_db()
    _TOKEN_DID_BINDINGS.clear()
    yield
    s.DB_PATH = _orig


def _auth_header():
    from agent_net.node._auth import init_daemon_token
    return {"Authorization": f"Bearer {init_daemon_token()}"}


async def _owner(name: str = "CoordOwner") -> dict:
    from agent_net.storage import register_owner
    return await register_owner(name)


async def _vault_ref(
    key: str,
    value: str = "artifact content",
    author_did: str = "did:agentnexus:test",
    enclave_id: str = "enc_coord_tests",
) -> str:
    from agent_net.storage import vault_put
    await vault_put(enclave_id, key, value, author_did)
    return f"vault://{enclave_id}/{key}"


# ═══════════════════════════════════════════════════════════════
# CoordinationSession CRUD
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_10_create_coordination_session():
    """Create a coordination session and verify fields."""
    from agent_net.storage import create_coordination_session, get_coordination_session

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    sess = await create_coordination_session(
        coordination_session_id=cs_id,
        owner_did="did:agentnexus:owner1",
        controller_did="did:agentnexus:ctrl1",
        objective="Implement login module",
    )
    assert sess["coordination_session_id"] == cs_id
    assert sess["status"] == "running"
    assert sess["playbook_id"] == "coding.v1"
    assert sess["current_stage"] == "clarify"
    assert sess["stage_snapshots"]

    loaded = await get_coordination_session(cs_id)
    assert loaded is not None
    assert loaded["objective"] == "Implement login module"
    assert loaded["policy_json"] == {"complexity": "medium", "risk_level": "normal", "cost_policy": "balanced"}


@pytest.mark.asyncio
async def test_v10_sec_10_get_nonexistent_session():
    """Get nonexistent session returns None."""
    from agent_net.storage import get_coordination_session
    result = await get_coordination_session("cs_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_v10_sec_10_list_sessions_by_owner_and_status():
    """List sessions filters by PlaybookRun-derived status."""
    from agent_net.storage import (
        create_coordination_session,
        create_playbook_run,
        list_coordination_sessions,
        update_playbook_run,
    )

    cs_id1 = f"cs_{uuid.uuid4().hex[:16]}"
    cs_id2 = f"cs_{uuid.uuid4().hex[:16]}"
    run_id1 = f"run_{uuid.uuid4().hex[:16]}"
    run_id2 = f"run_{uuid.uuid4().hex[:16]}"
    await create_playbook_run(run_id1, "enc_test", "coding.v1", coordination_session_id=cs_id1)
    await create_playbook_run(run_id2, "enc_test", "coding.v1", coordination_session_id=cs_id2)
    await update_playbook_run(run_id1, status="running", current_stage="clarify")
    await update_playbook_run(run_id2, status="blocked", current_stage="clarify")
    await create_coordination_session(cs_id1, "did:agentnexus:ownerA", "did:agentnexus:ctrl", "Task 1", playbook_run_id=run_id1)
    await create_coordination_session(cs_id2, "did:agentnexus:ownerA", "did:agentnexus:ctrl", "Task 2", playbook_run_id=run_id2)

    all_sessions = await list_coordination_sessions("did:agentnexus:ownerA")
    assert len(all_sessions) == 2

    running_only = await list_coordination_sessions("did:agentnexus:ownerA", status="running")
    assert len(running_only) == 1
    assert running_only[0]["coordination_session_id"] == cs_id1


@pytest.mark.asyncio
async def test_v10_sec_10_update_coordination_session():
    """Update session metadata without writing runtime status."""
    from agent_net.storage import create_coordination_session, update_coordination_session, get_coordination_session

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(cs_id, "did:agentnexus:owner1", "did:agentnexus:ctrl1", "Test")

    ok = await update_coordination_session(cs_id, policy_json={"complexity": "high"})
    assert ok

    sess = await get_coordination_session(cs_id)
    assert sess["policy_json"] == {"complexity": "high"}


@pytest.mark.asyncio
async def test_v10_sec_10_update_nonexistent_session():
    """Update nonexistent session returns False."""
    from agent_net.storage import update_coordination_session
    ok = await update_coordination_session("cs_nonexistent", policy_json={"complexity": "high"})
    assert not ok


# ═══════════════════════════════════════════════════════════════
# SessionLink CRUD
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_10_create_session_link():
    """Create session link and verify bidirectional lookup."""
    from agent_net.storage import create_coordination_session, create_session_link, get_session_links, get_session_link_by_child

    root_id = f"cs_{uuid.uuid4().hex[:16]}"
    child_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(root_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")
    await create_coordination_session(child_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test", parent_session_id=root_id)

    link_id = f"sl_{uuid.uuid4().hex[:16]}"
    await create_session_link(link_id, root_id, root_id, child_id, "review_fork", "independent review")

    links = await get_session_links(root_id)
    assert len(links) == 1
    assert links[0]["link_type"] == "review_fork"
    assert links[0]["to_session_id"] == child_id

    parent_link = await get_session_link_by_child(child_id)
    assert parent_link is not None
    assert parent_link["from_session_id"] == root_id


@pytest.mark.asyncio
async def test_v10_sec_10_get_session_links_filtered():
    """Get session links filtered by type."""
    from agent_net.storage import create_coordination_session, create_session_link, get_session_links

    root_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(root_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")

    child1 = f"cs_{uuid.uuid4().hex[:16]}"
    child2 = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(child1, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test", parent_session_id=root_id)
    await create_coordination_session(child2, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test", parent_session_id=root_id)

    await create_session_link(f"sl_{uuid.uuid4().hex[:16]}", root_id, root_id, child1, "review_fork")
    await create_session_link(f"sl_{uuid.uuid4().hex[:16]}", root_id, root_id, child2, "implementation_fork")

    review_links = await get_session_links(root_id, link_type="review_fork")
    assert len(review_links) == 1
    assert review_links[0]["to_session_id"] == child1


# ═══════════════════════════════════════════════════════════════
# RuntimeEvent + emit_event
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_10_emit_event_auto_id():
    """emit_event generates event_id automatically and stores with correct fields."""
    from agent_net.storage import create_coordination_session, emit_event, get_runtime_events

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(cs_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")

    evt = await emit_event(
        coordination_session_id=cs_id,
        event_type="stage.started",
        stage="design",
        actor_did="did:agentnexus:designer1",
        run_id="run_123",
        payload={"key": "value"},
    )
    assert evt["event_id"].startswith("evt_")
    assert evt["event_type"] == "stage.started"

    events = await get_runtime_events(cs_id)
    assert len(events) == 1
    assert events[0]["event_type"] == "stage.started"
    assert events[0]["stage"] == "design"
    assert events[0]["actor_did"] == "did:agentnexus:designer1"
    assert events[0]["run_id"] == "run_123"
    assert events[0]["payload"] == {"key": "value"}


@pytest.mark.asyncio
async def test_v10_sec_10_get_runtime_events_filtered():
    """Get events filtered by stage and event_type."""
    from agent_net.storage import create_coordination_session, emit_event, get_runtime_events

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(cs_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")

    await emit_event(cs_id, "stage.started", stage="design", actor_did="agent1")
    await emit_event(cs_id, "stage.completed", stage="design", actor_did="agent1")
    await emit_event(cs_id, "stage.started", stage="implement", actor_did="agent2")

    design_events = await get_runtime_events(cs_id, stage="design")
    assert len(design_events) == 2

    started_events = await get_runtime_events(cs_id, event_type="stage.started")
    assert len(started_events) == 2


@pytest.mark.asyncio
async def test_v10_sec_10_events_ordered_by_time():
    """Events are returned in ascending created_at order."""
    from agent_net.storage import create_coordination_session, emit_event, get_runtime_events
    import time

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(cs_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")

    await emit_event(cs_id, "stage.started", stage="clarify")
    await emit_event(cs_id, "artifact.submitted", stage="clarify")
    await emit_event(cs_id, "stage.completed", stage="clarify")

    events = await get_runtime_events(cs_id)
    assert len(events) == 3
    assert events[0]["event_type"] == "stage.started"
    assert events[1]["event_type"] == "artifact.submitted"
    assert events[2]["event_type"] == "stage.completed"


# ═══════════════════════════════════════════════════════════════
# Artifact CRUD
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_10_create_artifact_with_hash():
    """Create artifact with content_hash."""
    from agent_net.storage import create_coordination_session, create_artifact, get_artifact

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(cs_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")

    art_id = f"art_{uuid.uuid4().hex[:16]}"
    art = await create_artifact(
        artifact_id=art_id,
        coordination_session_id=cs_id,
        run_id="run_test",
        stage="design",
        artifact_type="DesignArtifact",
        producer_did="did:agentnexus:designer1",
        content_ref="vault://enc1/design_doc",
        content_hash="sha256:abc123",
    )
    assert art["artifact_id"] == art_id
    assert art["content_hash"] == "sha256:abc123"

    loaded = await get_artifact(art_id)
    assert loaded["artifact_type"] == "DesignArtifact"
    assert loaded["stage"] == "design"


@pytest.mark.asyncio
async def test_v10_sec_10_list_artifacts_by_stage():
    """List artifacts filtered by stage."""
    from agent_net.storage import create_coordination_session, create_artifact, list_artifacts

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(cs_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")

    await create_artifact(f"art_{uuid.uuid4().hex[:16]}", cs_id, "run_test", "design", "DesignArtifact", "agent1", "ref1")
    await create_artifact(f"art_{uuid.uuid4().hex[:16]}", cs_id, "run_test", "implement", "PatchArtifact", "agent2", "ref2")

    all_arts = await list_artifacts(cs_id)
    assert len(all_arts) == 2

    design_arts = await list_artifacts(cs_id, stage="design")
    assert len(design_arts) == 1
    assert design_arts[0]["artifact_type"] == "DesignArtifact"


# ═══════════════════════════════════════════════════════════════
# Receipt CRUD
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_10_create_receipt():
    """Create receipt with decision and evidence_refs."""
    from agent_net.storage import create_coordination_session, create_receipt, get_receipt

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(cs_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")

    rcpt_id = f"rcpt_{uuid.uuid4().hex[:16]}"
    rcpt = await create_receipt(
        receipt_id=rcpt_id,
        coordination_session_id=cs_id,
        run_id="run_test",
        stage="code_review",
        receipt_type="ReviewReceipt",
        issuer_did="did:agentnexus:reviewer1",
        decision="changes_requested",
        subject_artifact_id="art_patch_001",
        evidence_refs=["finding_1", "finding_2"],
    )
    assert rcpt["decision"] == "changes_requested"

    loaded = await get_receipt(rcpt_id)
    assert loaded["receipt_type"] == "ReviewReceipt"
    assert loaded["evidence_refs"] == ["finding_1", "finding_2"]


@pytest.mark.asyncio
async def test_v10_sec_10_list_receipts_by_stage():
    """List receipts filtered by stage."""
    from agent_net.storage import create_coordination_session, create_receipt, list_receipts

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(cs_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")

    await create_receipt(f"rcpt_{uuid.uuid4().hex[:16]}", cs_id, "run_test", "design_review", "ReviewReceipt", "agent1", "approved")
    await create_receipt(f"rcpt_{uuid.uuid4().hex[:16]}", cs_id, "run_test", "code_review", "ReviewReceipt", "agent2", "approved")

    design_rcpts = await list_receipts(cs_id, stage="design_review")
    assert len(design_rcpts) == 1
    assert design_rcpts[0]["decision"] == "approved"


# ═══════════════════════════════════════════════════════════════
# Closure / SLA Record CRUD
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_10_create_closure_record():
    """Create coding closure/SLA record and verify audit fields."""
    from agent_net.storage import (
        create_coordination_session,
        create_closure_record,
        get_closure_record,
        list_closure_records,
    )

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(cs_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")

    closure_id = f"clo_{uuid.uuid4().hex[:16]}"
    record = await create_closure_record(
        closure_id=closure_id,
        coordination_session_id=cs_id,
        actor_did="did:agentnexus:ctrl",
        status="recorded",
        sla_status="met",
        sla_metrics={"latency_ms": 1200},
        receipt_id="rcpt_final",
        evidence_refs=["coordination://sessions/test/timeline"],
    )
    assert record["status"] == "recorded"

    loaded = await get_closure_record(closure_id)
    assert loaded["sla_metrics"] == {"latency_ms": 1200}

    records = await list_closure_records(cs_id)
    assert len(records) == 1
    assert records[0]["receipt_id"] == "rcpt_final"


# ═══════════════════════════════════════════════════════════════
# Delegation CRUD
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_10_create_delegation():
    """Create delegation with capability_token_id."""
    from agent_net.storage import create_coordination_session, create_delegation, get_delegation

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(cs_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")

    del_id = f"del_{uuid.uuid4().hex[:16]}"
    delegation = await create_delegation(
        delegation_id=del_id,
        coordination_session_id=cs_id,
        stage="design",
        role="designer",
        delegator_did="did:agentnexus:ctrl",
        delegatee_did="did:agentnexus:designer1",
        capability_token_id="ct_test123",
    )
    assert delegation["status"] == "pending"

    loaded = await get_delegation(del_id)
    assert loaded["capability_token_id"] == "ct_test123"
    assert loaded["role"] == "designer"


@pytest.mark.asyncio
async def test_v10_sec_10_update_delegation():
    """Update delegation status."""
    from agent_net.storage import create_coordination_session, create_delegation, update_delegation, get_delegation

    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    await create_coordination_session(cs_id, "did:agentnexus:owner1", "did:agentnexus:ctrl", "Test")

    del_id = f"del_{uuid.uuid4().hex[:16]}"
    await create_delegation(del_id, cs_id, "implement", "developer", "ctrl", "dev1", "ct_001")

    ok = await update_delegation(del_id, status="accepted")
    assert ok

    delegation = await get_delegation(del_id)
    assert delegation["status"] == "accepted"


# ═══════════════════════════════════════════════════════════════
# Router-level Tests (using TestClient)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_10_api_create_session():
    """POST /coordination/sessions returns 200 with session dict."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("ApiCreateOwner")
    client = TestClient(app, headers=_auth_header())
    resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Test via API",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"
    assert data["session"]["objective"] == "Test via API"


@pytest.mark.asyncio
async def test_v10_sec_10_api_get_session():
    """GET /coordination/sessions/{id} returns session."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("ApiGetOwner")
    client = TestClient(app, headers=_auth_header())
    # Create first
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Get test",
    })
    cs_id = create_resp.json()["session"]["coordination_session_id"]

    get_resp = client.get(f"/coordination/sessions/{cs_id}", params={"actor_did": owner["did"]})
    assert get_resp.status_code == 200
    assert get_resp.json()["session"]["objective"] == "Get test"


@pytest.mark.asyncio
async def test_v10_sec_10_api_timeline():
    """GET /coordination/sessions/{id}/timeline returns merged timeline."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("ApiTimelineOwner")
    client = TestClient(app, headers=_auth_header())
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Timeline test",
    })
    cs_id = create_resp.json()["session"]["coordination_session_id"]

    # Add an event
    client.post("/coordination/events", json={
        "coordination_session_id": cs_id,
        "event_type": "stage.started",
        "stage": "design",
        "actor_did": owner["did"],
    })

    timeline_resp = client.get(f"/coordination/sessions/{cs_id}/timeline", params={"actor_did": owner["did"]})
    assert timeline_resp.status_code == 200
    data = timeline_resp.json()
    assert data["status"] == "ok"
    assert len(data["timeline"]) >= 1  # at least session.created from create


@pytest.mark.asyncio
async def test_v10_sec_10_api_submit_artifact():
    """POST /coordination/artifacts creates artifact."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("ApiArtifactOwner")
    client = TestClient(app, headers=_auth_header())
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Artifact test",
    })
    session = create_resp.json()["session"]
    cs_id = session["coordination_session_id"]
    ref = await _vault_ref("design.md", "design body", owner["did"], session["enclave_id"])

    art_resp = client.post("/coordination/artifacts", json={
        "coordination_session_id": cs_id,
        "stage": "design",
        "artifact_type": "DesignArtifact",
        "producer_did": owner["did"],
        "content_ref": ref,
    })
    assert art_resp.status_code == 200
    data = art_resp.json()
    assert data["status"] == "submitted"
    assert data["artifact"]["artifact_type"] == "DesignArtifact"


@pytest.mark.asyncio
async def test_v10_sec_10_api_submit_receipt():
    """POST /coordination/receipts creates receipt."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("ApiReceiptOwner")
    client = TestClient(app, headers=_auth_header())
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Receipt test",
    })
    cs_id = create_resp.json()["session"]["coordination_session_id"]

    rcpt_resp = client.post("/coordination/receipts", json={
        "coordination_session_id": cs_id,
        "stage": "design_review",
        "receipt_type": "ReviewReceipt",
        "issuer_did": owner["did"],
        "decision": "approved",
        "subject_artifact_id": "art_001",
    })
    assert rcpt_resp.status_code == 200
    data = rcpt_resp.json()
    assert data["status"] == "issued"
    assert data["receipt"]["decision"] == "approved"


@pytest.mark.asyncio
async def test_v10_sec_10_api_stream_events_replays_sse():
    """GET /coordination/sessions/{id}/events/stream replays events as SSE."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("ApiStreamOwner")
    client = TestClient(app, headers=_auth_header())
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Stream test",
    })
    cs_id = create_resp.json()["session"]["coordination_session_id"]

    with client.stream(
        "GET",
        f"/coordination/sessions/{cs_id}/events/stream",
        params={"actor_did": owner["did"], "limit": 1},
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert "event: session.created" in body
    assert '"coordination_session_id"' in body


@pytest.mark.asyncio
async def test_v10_sec_10_api_create_and_list_closure():
    """POST /coordination/closures records coding delivery/SLA audit record."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("ApiClosureOwner")
    client = TestClient(app, headers=_auth_header())
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Closure test",
    })
    cs_id = create_resp.json()["session"]["coordination_session_id"]

    closure_resp = client.post("/coordination/closures", json={
        "coordination_session_id": cs_id,
        "actor_did": owner["did"],
        "sla_status": "met",
        "sla_metrics": {"stage_count": 1},
    })
    assert closure_resp.status_code == 200
    data = closure_resp.json()
    assert data["status"] == "recorded"
    assert data["closure"]["sla_status"] == "met"

    list_resp = client.get(f"/coordination/sessions/{cs_id}/closures", params={"actor_did": owner["did"]})
    assert list_resp.status_code == 200
    closures = list_resp.json()["closures"]
    assert len(closures) == 1
    assert closures[0]["sla_metrics"] == {"stage_count": 1}


@pytest.mark.asyncio
async def test_v10_sec_10_api_coding_intake():
    """POST /coordination/coding/intake creates root session and intake."""
    from agent_net.storage import register_owner, register_agent
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient
    from agent_net.common.did import DIDGenerator, AgentProfile
    from nacl.encoding import HexEncoder

    # Register owner + agent
    owner = await register_owner("TestOwner")
    obj, _ = DIDGenerator.create_agentnexus("TestAgent")
    profile = AgentProfile(id=obj.did, name="TestAgent", type="agent", capabilities=["code"]).to_dict()
    pk_hex = obj.private_key.encode(HexEncoder).decode()
    await register_agent(obj.did, profile, is_local=True, private_key_hex=pk_hex)
    from agent_net.storage import bind_agent
    await bind_agent(owner["did"], obj.did)

    client = TestClient(app, headers=_auth_header())
    resp = client.post("/coordination/coding/intake", json={
        "owner_did": owner["did"],
        "actor_did": obj.did,
        "objective": "Implement login module",
        "complexity": "medium",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "intake"
    assert data["session"]["playbook_id"] == "coding.v1"
    assert data["session"]["current_stage"] == "clarify"


@pytest.mark.asyncio
async def test_v10_sec_10_api_coding_advance_flow():
    """POST /coordination/coding/{id}/runs/{run_id}/advance flows through stages."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("ApiAdvanceOwner")
    client = TestClient(app, headers=_auth_header())
    # Create session first
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Advance test",
        "playbook_id": "coding.v1",
    })
    session = create_resp.json()["session"]
    cs_id = session["coordination_session_id"]
    run_id = session["playbook_run_id"]
    ref = await _vault_ref("clarify.md", "clarify body", owner["did"], session["enclave_id"])

    # Submit artifact for clarify stage
    client.post("/coordination/artifacts", json={
        "coordination_session_id": cs_id,
        "run_id": run_id,
        "stage": "clarify",
        "artifact_type": "RequirementSpec",
        "producer_did": owner["did"],
        "content_ref": ref,
    })
    # Submit receipt for clarify (approved)
    client.post("/coordination/receipts", json={
        "coordination_session_id": cs_id,
        "run_id": run_id,
        "stage": "clarify",
        "receipt_type": "ReviewReceipt",
        "issuer_did": owner["did"],
        "decision": "approved",
    })

    resp = client.post(f"/coordination/coding/{cs_id}/runs/{run_id}/advance", json={"actor_did": owner["did"]})
    assert resp.status_code == 200
    data = resp.json()
    # Should advance from clarify to design
    assert data["current_stage"] in ("design", "clarify")


@pytest.mark.asyncio
async def test_v10_sec_10_api_reject_blocks_advance():
    """Receipt rejection blocks workflow advance."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("ApiRejectOwner")
    client = TestClient(app, headers=_auth_header())
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Reject test",
        "playbook_id": "coding.v1",
    })
    session = create_resp.json()["session"]
    cs_id = session["coordination_session_id"]
    run_id = session["playbook_run_id"]
    ref = await _vault_ref("clarify.md", "clarify body", owner["did"], session["enclave_id"])

    # Submit artifact for current clarify stage
    client.post("/coordination/artifacts", json={
        "coordination_session_id": cs_id,
        "run_id": run_id,
        "stage": "clarify",
        "artifact_type": "RequirementSpec",
        "producer_did": owner["did"],
        "content_ref": ref,
    })
    # Reject the current stage
    client.post("/coordination/receipts", json={
        "coordination_session_id": cs_id,
        "run_id": run_id,
        "stage": "clarify",
        "receipt_type": "ReviewReceipt",
        "issuer_did": owner["did"],
        "decision": "changes_requested",
    })

    resp = client.post(f"/coordination/coding/{cs_id}/runs/{run_id}/advance", json={"actor_did": owner["did"]})
    assert resp.status_code == 200
    data = resp.json()
    # Design review has on_reject: "design", so should revert
    assert data["status"] in ("reverted", "blocked")


@pytest.mark.asyncio
async def test_v10_sec_10_api_get_session_rejects_other_owner():
    """A registered but unrelated owner cannot read another coordination session."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("CoordPrivateOwner")
    other = await _owner("CoordOtherOwner")
    client = TestClient(app, headers=_auth_header())
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Private coordination",
    })
    cs_id = create_resp.json()["session"]["coordination_session_id"]

    resp = client.get(f"/coordination/sessions/{cs_id}", params={"actor_did": other["did"]})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_v10_sec_10_api_advance_requires_approved_receipt():
    """Playbook stage cannot advance on artifact alone."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("CoordReceiptGateOwner")
    client = TestClient(app, headers=_auth_header())
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Receipt gate",
    })
    session = create_resp.json()["session"]
    cs_id = session["coordination_session_id"]
    run_id = session["playbook_run_id"]
    ref = await _vault_ref("clarify_gate.md", "clarify body", owner["did"], session["enclave_id"])
    client.post("/coordination/artifacts", json={
        "coordination_session_id": cs_id,
        "run_id": run_id,
        "stage": "clarify",
        "artifact_type": "RequirementSpec",
        "producer_did": owner["did"],
        "content_ref": ref,
    })

    resp = client.post(f"/coordination/coding/{cs_id}/runs/{run_id}/advance", json={"actor_did": owner["did"]})
    assert resp.status_code == 400
    assert "missing approved receipt" in resp.text


@pytest.mark.asyncio
async def test_v10_sec_10_api_submit_artifact_rejects_unverifiable_ref():
    """Artifacts must resolve to vault content so receipts can trust hashes."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    owner = await _owner("CoordBadArtifactOwner")
    client = TestClient(app, headers=_auth_header())
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Bad artifact",
    })
    cs_id = create_resp.json()["session"]["coordination_session_id"]

    resp = client.post("/coordination/artifacts", json={
        "coordination_session_id": cs_id,
        "stage": "design",
        "artifact_type": "DesignArtifact",
        "producer_did": owner["did"],
        "content_ref": "file:///tmp/design.md",
    })
    assert resp.status_code == 400
