"""Tests for CoordinationClient SDK facade."""
from types import SimpleNamespace

import pytest


class FakeClient:
    """Fake AgentNexusClient for unit-testing CoordinationClient."""

    def __init__(self, *, actor_did: str = "did:agentnexus:actor",
                 actor_owner_did: str = "did:agentnexus:owner"):
        self.agent_info = SimpleNamespace(
            did=actor_did,
            owner_did=actor_owner_did,
            worker_type="resident",
        )
        self.requests: list[dict] = []

    async def _request(self, method, path, *, json=None, params=None, auth=True):
        self.requests.append({
            "method": method,
            "path": path,
            "json": json,
            "params": params,
            "auth": auth,
        })

        # coding_intake
        if path == "/coordination/coding/intake":
            return {
                "status": "intake",
                "session": {
                    "coordination_session_id": "cs_test001",
                    "playbook_run_id": "run_test001",
                    "owner_did": json["owner_did"],
                    "controller_did": json["actor_did"],
                    "objective": json["objective"],
                    "playbook_id": "coding.v1",
                    "status": "intake",
                },
            }
        # get_session
        if path.startswith("/coordination/sessions/") and "events" not in path and "timeline" not in path and "artifacts" not in path and "receipts" not in path and "closures" not in path and "fork" not in path and "stages" not in path:
            cs_id = path.split("/")[-1]
            return {
                "status": "ok",
                "session": {
                    "coordination_session_id": cs_id,
                    "owner_did": "did:agentnexus:owner",
                    "controller_did": "did:agentnexus:secretary",
                    "objective": "Test session",
                    "playbook_id": "coding.v1",
                    "status": "intake",
                },
            }
        # list_sessions
        if path == "/coordination/sessions":
            return {
                "status": "ok",
                "sessions": [],
                "count": 0,
            }
        # fork_session
        if path == "/coordination/sessions/fork":
            return {
                "status": "forked",
                "session": {
                    "coordination_session_id": "cs_child001",
                    "parent_session_id": json["coordination_session_id"],
                },
                "link_id": "sl_001",
            }
        # submit_artifact
        if path == "/coordination/artifacts":
            return {
                "status": "submitted",
                "artifact": {
                    "artifact_id": "art_001",
                    "coordination_session_id": json["coordination_session_id"],
                    "run_id": json.get("run_id", ""),
                    "stage": json["stage"],
                    "artifact_type": json["artifact_type"],
                    "producer_did": json["producer_did"],
                    "content_ref": json["content_ref"],
                    "content_hash": "sha256:test",
                },
            }
        # submit_receipt
        if path == "/coordination/receipts":
            return {
                "status": "issued",
                "receipt": {
                    "receipt_id": "rcpt_001",
                    "coordination_session_id": json["coordination_session_id"],
                    "run_id": json.get("run_id", ""),
                    "stage": json["stage"],
                    "receipt_type": json["receipt_type"],
                    "issuer_did": json["issuer_did"],
                    "decision": json["decision"],
                },
            }
        # delegate_stage
        if "/stages/" in path and "/delegate" in path:
            return {
                "status": "delegated",
                "delegation": {
                    "delegation_id": "del_001",
                    "stage": path.split("/stages/")[1].split("/delegate")[0],
                    "status": "pending",
                },
            }
        # accept_delegation
        if "/accept" in path and "/delegations/" in path:
            return {"status": "accepted"}
        # reject_delegation
        if "/reject" in path and "/delegations/" in path:
            return {"status": "rejected"}
        # advance
        if "/advance" in path:
            return {"status": "advanced", "run_id": path.split("/runs/")[1].split("/")[0], "current_stage": "design", "previous_stage": "clarify"}
        # timeline
        if "/timeline" in path:
            return {"status": "ok", "coordination_session_id": "cs_test001", "timeline": []}
        # events
        if "/events/stream" in path:
            return {"status": "ok"}
        if "/events" in path:
            return {"status": "ok", "events": []}
        # artifacts
        if "/artifacts" in path:
            return {"status": "ok", "artifacts": []}
        # receipts
        if "/receipts" in path:
            return {"status": "ok", "receipts": []}
        # closures
        if "/closures" in path:
            return {"status": "ok", "closures": []}

        return {"status": "ok"}


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def coord_client(client):
    from agentnexus.coordination import CoordinationClient
    return CoordinationClient(client)


# ═══════════════════════════════════════════════════════════════
# coding_intake
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_coordination_client_coding_intake(coord_client, client):
    """coding_intake sends POST to /coordination/coding/intake."""
    session = await coord_client.coding_intake(
        owner_did="did:agentnexus:owner",
        actor_did="did:agentnexus:secretary",
        objective="Implement login module",
        complexity="medium",
    )
    assert session["coordination_session_id"] == "cs_test001"
    assert client.requests[-1]["path"] == "/coordination/coding/intake"
    body = client.requests[-1]["json"]
    assert body["objective"] == "Implement login module"
    assert body["complexity"] == "medium"


# ═══════════════════════════════════════════════════════════════
# get_session / list_sessions
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_coordination_client_get_session(coord_client, client):
    """get_session sends GET /coordination/sessions/{id}."""
    session = await coord_client.get_session("cs_test001", actor_did="did:agentnexus:owner")
    assert session["coordination_session_id"] == "cs_test001"
    req = client.requests[-1]
    assert req["method"] == "GET"
    assert req["params"]["actor_did"] == "did:agentnexus:owner"


@pytest.mark.asyncio
async def test_coordination_client_list_sessions(coord_client, client):
    """list_sessions sends GET /coordination/sessions."""
    sessions = await coord_client.list_sessions(
        owner_did="did:agentnexus:owner",
        actor_did="did:agentnexus:owner",
    )
    assert isinstance(sessions, list)
    req = client.requests[-1]
    assert req["method"] == "GET"
    assert req["params"]["owner_did"] == "did:agentnexus:owner"


# ═══════════════════════════════════════════════════════════════
# fork_session
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_coordination_client_fork_session(coord_client, client):
    """fork_session sends POST /coordination/sessions/fork."""
    child = await coord_client.fork_session(
        coordination_session_id="cs_test001",
        actor_did="did:agentnexus:owner",
        link_type="review_fork",
        reason="independent review",
    )
    assert child["coordination_session_id"] == "cs_child001"
    body = client.requests[-1]["json"]
    assert body["link_type"] == "review_fork"
    assert body["reason"] == "independent review"


# ═══════════════════════════════════════════════════════════════
# submit_artifact / submit_receipt
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_coordination_client_submit_artifact(coord_client, client):
    """submit_artifact sends POST /coordination/artifacts."""
    artifact = await coord_client.submit_artifact(
        coordination_session_id="cs_test001",
        stage="design",
        artifact_type="DesignArtifact",
        producer_did="did:agentnexus:designer",
        content_ref="vault://enc/design.md",
    )
    assert artifact["artifact_id"] == "art_001"
    body = client.requests[-1]["json"]
    assert body["stage"] == "design"
    assert body["artifact_type"] == "DesignArtifact"


@pytest.mark.asyncio
async def test_coordination_client_submit_receipt(coord_client, client):
    """submit_receipt sends POST /coordination/receipts."""
    receipt = await coord_client.submit_receipt(
        coordination_session_id="cs_test001",
        stage="design",
        receipt_type="DesignReceipt",
        issuer_did="did:agentnexus:reviewer",
        decision="approved",
        subject_artifact_id="art_001",
    )
    assert receipt["receipt_id"] == "rcpt_001"
    body = client.requests[-1]["json"]
    assert body["decision"] == "approved"


# ═══════════════════════════════════════════════════════════════
# advance / timeline / closures
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_coordination_client_advance(coord_client, client):
    """advance sends POST /coordination/coding/{id}/runs/{run_id}/advance."""
    state = await coord_client.advance(
        coordination_session_id="cs_test001",
        run_id="run_test001",
        actor_did="did:agentnexus:secretary",
    )
    assert state["current_stage"] == "design"
    assert state["run_id"] == "run_test001"
    req = client.requests[-1]
    assert req["path"] == "/coordination/coding/cs_test001/runs/run_test001/advance"


@pytest.mark.asyncio
async def test_coordination_client_timeline(coord_client, client):
    """timeline sends GET /coordination/sessions/{id}/timeline."""
    timeline = await coord_client.timeline(
        coordination_session_id="cs_test001",
        actor_did="did:agentnexus:secretary",
    )
    assert isinstance(timeline["timeline"], list)
    req = client.requests[-1]
    assert req["method"] == "GET"


@pytest.mark.asyncio
async def test_coordination_client_closures(coord_client, client):
    """closures sends GET /coordination/sessions/{id}/closures."""
    closures = await coord_client.closures(
        coordination_session_id="cs_test001",
        actor_did="did:agentnexus:secretary",
    )
    assert isinstance(closures["closures"], list)
    req = client.requests[-1]
    assert req["method"] == "GET"


# ═══════════════════════════════════════════════════════════════
# delegation
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_coordination_client_delegate_stage(coord_client, client):
    """delegate_stage sends POST to delegate endpoint."""
    result = await coord_client.delegate_stage(
        coordination_session_id="cs_test001",
        stage="design",
        delegator_did="did:agentnexus:secretary",
        delegatee_did="did:agentnexus:designer",
        run_id="run_test001",
        role="designer",
    )
    assert result["delegation"]["status"] == "pending"
    body = client.requests[-1]["json"]
    assert body["delegatee_did"] == "did:agentnexus:designer"
    assert body["run_id"] == "run_test001"


@pytest.mark.asyncio
async def test_coordination_client_accept_delegation(coord_client, client):
    """accept_delegation sends POST to accept endpoint."""
    result = await coord_client.accept_delegation(
        delegation_id="del_001",
        actor_did="did:agentnexus:designer",
    )
    assert result["status"] == "accepted"


@pytest.mark.asyncio
async def test_coordination_client_reject_delegation(coord_client, client):
    """reject_delegation sends POST to reject endpoint."""
    result = await coord_client.reject_delegation(
        delegation_id="del_001",
        actor_did="did:agentnexus:designer",
        reason="not my expertise",
    )
    assert result["status"] == "rejected"
