"""Coding Coordination V1 Phase 1 — End-to-End Flow Tests"""
import json
import pytest
import pytest_asyncio
import uuid

from agent_net.node._auth import _TOKEN_DID_BINDINGS

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    from agent_net.storage import DB_PATH
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    from agent_net.storage import init_db
    await init_db()
    _TOKEN_DID_BINDINGS.clear()
    yield


def _auth_header():
    from agent_net.node._auth import init_daemon_token
    return {"Authorization": f"Bearer {init_daemon_token()}"}


async def _vault_ref(key: str, value: str, author_did: str) -> str:
    from agent_net.storage import vault_put
    enclave_id = "enc_coord_flow"
    await vault_put(enclave_id, key, value, author_did)
    return f"vault://{enclave_id}/{key}"


async def _bound_agent(owner_did: str, name: str, capabilities: list[str]) -> str:
    from agent_net.common.did import DIDGenerator, AgentProfile
    from nacl.encoding import HexEncoder
    from agent_net.storage import register_agent, bind_agent
    obj, _ = DIDGenerator.create_agentnexus(name)
    pk_hex = obj.private_key.encode(HexEncoder).decode()
    await register_agent(
        obj.did,
        AgentProfile(id=obj.did, name=name, type="agent", capabilities=capabilities).to_dict(),
        is_local=True,
        private_key_hex=pk_hex,
    )
    await bind_agent(owner_did, obj.did)
    return obj.did


# ═══════════════════════════════════════════════════════════════
# Full workflow flow test
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_11_full_coding_workflow():
    """E2E: coding intake -> clarify -> design -> design_review -> implement -> code_review -> test -> final."""
    from agent_net.storage import register_owner
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient

    # Register owner so coding/intake passes get_owner check
    owner = await register_owner("E2EOwner")
    client = TestClient(app, headers=_auth_header())

    # 1. Coding intake
    intake_resp = client.post("/coordination/coding/intake", json={
        "owner_did": owner["did"],
        "actor_did": owner["did"],
        "objective": "Implement login module with OAuth2",
        "complexity": "medium",
        "risk_level": "normal",
        "cost_policy": "balanced",
    })
    assert intake_resp.status_code == 200
    intake_data = intake_resp.json()
    assert intake_data["status"] == "intake"
    cs_id = intake_data["session"]["coordination_session_id"]
    assert cs_id.startswith("cs_")

    # Helper: submit artifact + receipt for a stage, then advance
    async def submit_artifact(stage, artifact_type, producer, key, value):
        content_ref = await _vault_ref(key, value, producer)
        return client.post("/coordination/artifacts", json={
            "coordination_session_id": cs_id,
            "stage": stage,
            "artifact_type": artifact_type,
            "producer_did": producer,
            "content_ref": content_ref,
        })

    def submit_receipt(stage, receipt_type, issuer, decision, subject_artifact_id=""):
        return client.post("/coordination/receipts", json={
            "coordination_session_id": cs_id,
            "stage": stage,
            "receipt_type": receipt_type,
            "issuer_did": issuer,
            "decision": decision,
            "subject_artifact_id": subject_artifact_id,
        })

    def advance(actor):
        return client.post(f"/coordination/coding/{cs_id}/advance", json={"actor_did": actor})

    # 2. Clarify stage
    resp = await submit_artifact("clarify", "RequirementSpec", owner["did"], "clarify", "clarify")
    assert resp.status_code == 200
    resp = submit_receipt("clarify", "ReviewReceipt", owner["did"], "approved")
    assert resp.status_code == 200
    resp = advance(owner["did"])
    assert resp.status_code == 200
    assert resp.json()["current_stage"] == "design"

    # 3. Design stage
    resp = await submit_artifact("design", "DesignArtifact", owner["did"], "design", "design")
    assert resp.status_code == 200
    resp = submit_receipt("design", "DesignReceipt", owner["did"], "approved")
    assert resp.status_code == 200
    resp = advance(owner["did"])
    assert resp.status_code == 200
    assert resp.json()["current_stage"] == "design_review"

    # 4. Design review stage
    resp = await submit_artifact("design_review", "ReviewFinding", owner["did"], "design_review", "review")
    assert resp.status_code == 200
    resp = submit_receipt("design_review", "ReviewReceipt", owner["did"], "approved")
    assert resp.status_code == 200
    resp = advance(owner["did"])
    assert resp.status_code == 200
    assert resp.json()["current_stage"] == "implement"

    # 5. Implement stage
    resp = await submit_artifact("implement", "PatchArtifact", owner["did"], "patch", "patch")
    assert resp.status_code == 200
    resp = submit_receipt("implement", "ReviewReceipt", owner["did"], "approved")
    assert resp.status_code == 200
    resp = advance(owner["did"])
    assert resp.status_code == 200
    assert resp.json()["current_stage"] == "code_review"

    # 6. Code review stage
    resp = await submit_artifact("code_review", "ReviewFinding", owner["did"], "cr", "cr")
    assert resp.status_code == 200
    resp = submit_receipt("code_review", "ReviewReceipt", owner["did"], "approved")
    assert resp.status_code == 200
    resp = advance(owner["did"])
    assert resp.status_code == 200
    assert resp.json()["current_stage"] == "test"

    # 7. Test stage
    resp = await submit_artifact("test", "TestLog", owner["did"], "testlog", "test")
    assert resp.status_code == 200
    resp = submit_receipt("test", "TestReceipt", owner["did"], "passed")
    assert resp.status_code == 200
    resp = advance(owner["did"])
    assert resp.status_code == 200
    # final stage has no next, should be completed
    assert resp.json()["status"] == "completed"

    # 8. Verify timeline has all stages
    timeline_resp = client.get(f"/coordination/sessions/{cs_id}/timeline", params={"actor_did": owner["did"]})
    assert timeline_resp.status_code == 200
    timeline = timeline_resp.json()["timeline"]

    # Should have events for each stage
    stage_names = {e["stage"] for e in timeline if e["stage"]}
    assert "clarify" in stage_names
    assert "design" in stage_names
    assert "design_review" in stage_names
    assert "implement" in stage_names
    assert "code_review" in stage_names
    assert "test" in stage_names

    # Should have artifact.submitted events
    event_types = {e["event_type"] for e in timeline}
    assert "artifact.submitted" in event_types
    assert "receipt.issued" in event_types

    # 9. Verify artifacts
    art_resp = client.get(f"/coordination/sessions/{cs_id}/artifacts", params={"actor_did": owner["did"]})
    assert art_resp.status_code == 200
    artifacts = art_resp.json()["artifacts"]
    assert len(artifacts) >= 6  # clarify, design, design_review, implement, code_review, test

    # 10. Verify receipts
    rcpt_resp = client.get(f"/coordination/sessions/{cs_id}/receipts", params={"actor_did": owner["did"]})
    assert rcpt_resp.status_code == 200
    receipts = rcpt_resp.json()["receipts"]
    assert len(receipts) >= 6  # clarify, design, design_review, implement, code_review, test
    assert any(r["receipt_type"] == "FinalResultReceipt" and r["stage"] == "final" for r in receipts)

    # 11. Verify closure/SLA record
    closure_resp = client.get(f"/coordination/sessions/{cs_id}/closures", params={"actor_did": owner["did"]})
    assert closure_resp.status_code == 200
    closures = closure_resp.json()["closures"]
    assert len(closures) == 1
    assert closures[0]["status"] == "recorded"
    assert closures[0]["sla_status"] == "met"

    # 12. Verify terminal audit event
    events_resp = client.get(f"/coordination/sessions/{cs_id}/events", params={"actor_did": owner["did"]})
    event_types = {e["event_type"] for e in events_resp.json()["events"]}
    assert "closure.recorded" in event_types


# ═══════════════════════════════════════════════════════════════
# Fork session flow test
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_11_fork_session_flow():
    """Fork a review session and verify via timeline."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient
    from agent_net.storage import register_owner

    owner = await register_owner("ForkOwner")
    client = TestClient(app, headers=_auth_header())

    # Create root session
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Fork test task",
    })
    cs_id = create_resp.json()["session"]["coordination_session_id"]

    # Fork a review session
    fork_resp = client.post("/coordination/sessions/fork", json={
        "coordination_session_id": cs_id,
        "actor_did": owner["did"],
        "link_type": "review_fork",
        "reason": "Independent code review",
    })
    assert fork_resp.status_code == 200
    fork_data = fork_resp.json()
    assert fork_data["status"] == "forked"
    child_id = fork_data["session"]["coordination_session_id"]
    assert child_id != cs_id

    # Verify child session has parent_session_id
    get_child = client.get(f"/coordination/sessions/{child_id}", params={"actor_did": owner["did"]})
    assert get_child.status_code == 200
    # parent_session_id should be root

    # Verify link exists in root's timeline
    timeline_resp = client.get(f"/coordination/sessions/{cs_id}/timeline", params={"actor_did": owner["did"]})
    assert timeline_resp.status_code == 200
    events = timeline_resp.json()["timeline"]
    fork_events = [e for e in events if e["event_type"] == "session.forked"]
    assert len(fork_events) >= 1


# ═══════════════════════════════════════════════════════════════
# Delegation flow test
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_11_delegation_flow():
    """Delegate a stage, accept it, verify delegation events."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient
    from agent_net.storage import register_owner

    owner = await register_owner("DelegationOwner")
    delegatee = await _bound_agent(owner["did"], "DesignerDelegate", ["designer"])
    client = TestClient(app, headers=_auth_header())

    # Create session
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Delegation test",
    })
    cs_id = create_resp.json()["session"]["coordination_session_id"]

    # Delegate design stage
    del_resp = client.post(f"/coordination/sessions/{cs_id}/stages/design/delegate", json={
        "role": "designer",
        "delegator_did": owner["did"],
        "delegatee_did": delegatee,
        "runtime_kind": "native_worker",
        "session_id": "sess_design_001",
    })
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["status"] == "delegated"
    delegation_id = del_data["delegation"]["delegation_id"]
    assert delegation_id.startswith("del_")

    # Accept delegation
    accept_resp = client.post(f"/coordination/delegations/{delegation_id}/accept", json={
        "actor_did": delegatee,
    })
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "accepted"

    # Verify delegation events in timeline
    timeline_resp = client.get(f"/coordination/sessions/{cs_id}/timeline", params={"actor_did": owner["did"]})
    assert timeline_resp.status_code == 200
    events = timeline_resp.json()["timeline"]
    delegation_events = [e for e in events if e["event_type"] in ("delegation.created", "delegation.accepted")]
    assert len(delegation_events) >= 2


# ═══════════════════════════════════════════════════════════════
# Rejection and revert flow test
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_11_rejection_flow():
    """Reject design_review, verify advance reverts to design stage."""
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient
    from agent_net.storage import register_owner

    owner = await register_owner("RejectFlowOwner")
    client = TestClient(app, headers=_auth_header())

    # Create session
    create_resp = client.post("/coordination/sessions", json={
        "owner_did": owner["did"],
        "controller_did": owner["did"],
        "objective": "Rejection flow test",
        "workflow_id": "coding.v1",
    })
    cs_id = create_resp.json()["session"]["coordination_session_id"]

    # Move through clarify → design → design_review
    # Clarify
    client.post("/coordination/artifacts", json={
        "coordination_session_id": cs_id, "stage": "clarify",
        "artifact_type": "RequirementSpec", "producer_did": owner["did"],
        "content_ref": await _vault_ref("rej_clarify", "clarify", owner["did"]),
    })
    client.post("/coordination/receipts", json={
        "coordination_session_id": cs_id, "stage": "clarify",
        "receipt_type": "ReviewReceipt", "issuer_did": owner["did"], "decision": "approved",
    })
    r1 = client.post(f"/coordination/coding/{cs_id}/advance", json={"actor_did": owner["did"]})
    assert r1.json()["current_stage"] == "design"

    # Design - approved
    client.post("/coordination/artifacts", json={
        "coordination_session_id": cs_id, "stage": "design",
        "artifact_type": "DesignArtifact", "producer_did": owner["did"],
        "content_ref": await _vault_ref("rej_design", "design", owner["did"]),
    })
    client.post("/coordination/receipts", json={
        "coordination_session_id": cs_id, "stage": "design",
        "receipt_type": "DesignReceipt", "issuer_did": owner["did"], "decision": "approved",
    })
    r2 = client.post(f"/coordination/coding/{cs_id}/advance", json={"actor_did": owner["did"]})
    assert r2.json()["current_stage"] == "design_review"

    # Submit design_review artifact
    client.post("/coordination/artifacts", json={
        "coordination_session_id": cs_id, "stage": "design_review",
        "artifact_type": "ReviewFinding", "producer_did": owner["did"],
        "content_ref": await _vault_ref("rej_review", "review", owner["did"]),
    })

    # Reject design_review
    client.post("/coordination/receipts", json={
        "coordination_session_id": cs_id, "stage": "design_review",
        "receipt_type": "ReviewReceipt", "issuer_did": owner["did"],
        "decision": "changes_requested",
    })

    # Advance: should revert to design (design_review.on_reject = "design")
    r3 = client.post(f"/coordination/coding/{cs_id}/advance", json={"actor_did": owner["did"]})
    data = r3.json()
    assert data["status"] == "reverted"
    assert data["revert_to"] == "design"

    # Verify blocked event in timeline
    timeline = client.get(f"/coordination/sessions/{cs_id}/timeline", params={"actor_did": owner["did"]}).json()["timeline"]
    blocked_events = [e for e in timeline if e["event_type"] == "stage.blocked"]
    assert len(blocked_events) >= 1


# ═══════════════════════════════════════════════════════════════════
# SDK facade integration test (ASGI-backed)
# ═══════════════════════════════════════════════════════════════════


class _ASGILazyResponse:
    """Lazy async context manager: defers HTTP call to __aenter__, wraps result."""

    def __init__(self, coro_factory):
        self._coro_factory = coro_factory
        self.status = 0

    async def __aenter__(self):
        self._inner = await self._coro_factory()
        self.status = self._inner.status_code
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self._inner.json()

    async def text(self):
        return self._inner.text


class _ASGIBackedSession:
    """Minimal aiohttp.ClientSession replacement backed by httpx ASGI transport."""

    def __init__(self, app, base_url="http://testserver"):
        import httpx
        self._transport = httpx.ASGITransport(app=app)
        self._client = httpx.AsyncClient(transport=self._transport, base_url=base_url)
        self._is_closed = False

    def request(self, method, url, *, headers=None, json=None, params=None, **kwargs):
        async def _do():
            return await self._client.request(method, url, headers=headers, json=json, params=params or None)
        return _ASGILazyResponse(_do)

    def get(self, url, *, headers=None, params=None, **kwargs):
        async def _do():
            return await self._client.get(url, headers=headers, params=params or None)
        return _ASGILazyResponse(_do)

    def post(self, url, *, headers=None, json=None, params=None, **kwargs):
        async def _do():
            return await self._client.post(url, headers=headers, json=json, params=params or None)
        return _ASGILazyResponse(_do)

    async def close(self):
        if not self._is_closed:
            await self._client.aclose()
            self._is_closed = True


@pytest.mark.asyncio
async def test_v10_sec_11_sdk_facade_integration(monkeypatch, tmp_path):
    """Integration: SDK facade → ASGI transport → real daemon app.

    Verifies that the AgentNexusClient SDK's coordination methods
    (coding_intake, submit_artifact, submit_receipt, advance, timeline,
    closures) work end-to-end against the real FastAPI app via ASGI transport.
    """
    import aiohttp
    from agentnexus.client import AgentNexusClient, AgentInfo
    from agent_net.storage import register_owner, register_agent, bind_agent, vault_put
    from agent_net.node.daemon import app
    from agent_net.node._auth import init_daemon_token
    from agent_net.common.did import DIDGenerator, AgentProfile
    from nacl.encoding import HexEncoder

    # -- Setup: token file --
    token_file = tmp_path / "daemon_token.txt"
    token_file.write_text(init_daemon_token())
    monkeypatch.setattr("agent_net.common.constants.DAEMON_TOKEN_FILE", str(token_file))
    monkeypatch.setattr("agent_net.node._auth.DAEMON_TOKEN_FILE", str(token_file))

    # -- Setup: owner --
    owner = await register_owner("SDKIntegrationOwner")

    # -- Setup: agents --
    async def _make_agent(name, caps):
        obj, vk = DIDGenerator.create_agentnexus(name)
        pk_hex = obj.private_key.encode(HexEncoder).decode()
        await register_agent(
            obj.did,
            AgentProfile(id=obj.did, name=name, type="agent", capabilities=caps).to_dict(),
            is_local=True,
            private_key_hex=pk_hex,
        )
        await bind_agent(owner["did"], obj.did)
        return obj.did

    secretary_did = await _make_agent("SDK Secretary", ["orchestrate", "intake"])
    designer_did = await _make_agent("SDK Designer", ["design"])
    developer_did = await _make_agent("SDK Developer", ["coding"])
    reviewer_did = await _make_agent("SDK Reviewer", ["review"])
    tester_did = await _make_agent("SDK Tester", ["testing"])

    # -- Setup: vault content --
    enclave_id = "enc_sdk_integration"
    await vault_put(enclave_id, "clarify.md", "# Requirements\n\nSDK integration test requirements.", owner["did"])
    await vault_put(enclave_id, "design.md", "# Design\n\nSDK integration test design.", owner["did"])
    await vault_put(enclave_id, "implement.py", "# Code\n\ndef test(): pass", owner["did"])
    await vault_put(enclave_id, "code_review.md", "# Review\n\nLGTM.", owner["did"])
    await vault_put(enclave_id, "test_report.md", "# Test Report\n\nAll passed.", owner["did"])

    # -- Create SDK client backed by ASGI transport --
    asgi_session = _ASGIBackedSession(app)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: asgi_session)

    client = AgentNexusClient(
        daemon_url="http://testserver",
        token=init_daemon_token(),
        agent_info=AgentInfo(did=owner["did"], name="SDKIntegrationClient", capabilities=["Admin"], owner_did=owner["did"]),
    )
    client._session = asgi_session

    try:
        # 1. Coding intake
        session = await client.coordination.coding_intake(
            owner_did=owner["did"],
            actor_did=secretary_did,
            objective="SDK facade integration test",
            complexity="medium",
        )
        cs_id = session["coordination_session_id"]
        assert cs_id.startswith("cs_")

        # 2. Run all 7 stages via SDK facade
        workflow = [
            ("clarify", "RequirementSpec", designer_did, "ClarifyReceipt", reviewer_did, "clarify.md"),
            ("design", "DesignArtifact", designer_did, "DesignReceipt", reviewer_did, "design.md"),
            ("design_review", "ReviewFinding", reviewer_did, "ReviewReceipt", reviewer_did, None),
            ("implement", "PatchArtifact", developer_did, "ImplReceipt", reviewer_did, "implement.py"),
            ("code_review", "ReviewFinding", reviewer_did, "CodeReviewReceipt", reviewer_did, "code_review.md"),
            ("test", "TestLog", tester_did, "TestReceipt", reviewer_did, "test_report.md"),
        ]

        for stage, atype, producer, rtype, issuer, vkey in workflow:
            content_ref = f"vault://{enclave_id}/{vkey}" if vkey else f"vault://{enclave_id}/design.md"
            art = await client.coordination.submit_artifact(
                coordination_session_id=cs_id,
                stage=stage,
                artifact_type=atype,
                producer_did=producer,
                content_ref=content_ref,
            )
            assert art["artifact_id"].startswith("art_")

            rcpt = await client.coordination.submit_receipt(
                coordination_session_id=cs_id,
                stage=stage,
                receipt_type=rtype,
                issuer_did=issuer,
                decision="approved",
            )
            assert rcpt["receipt_id"].startswith("rcpt_")

            state = await client.coordination.advance(
                coordination_session_id=cs_id,
                actor_did=secretary_did,
            )
            # Final stage auto-completes on advance from test (next=final, final next=None)
            if state["status"] == "completed":
                break
            assert state["status"] == "advanced"

        # Advance from test should have auto-completed into final
        assert state["status"] == "completed"

        # 4. Verify timeline via SDK
        timeline_data = await client.coordination.timeline(cs_id, actor_did=secretary_did)
        timeline = timeline_data.get("timeline", [])
        stages_seen = {e["stage"] for e in timeline if e["stage"]}
        for s in ("clarify", "design", "design_review", "implement", "code_review", "test"):
            assert s in stages_seen, f"Stage {s} missing from timeline"

        # 5. Verify artifacts via SDK
        artifacts = await client.coordination.list_artifacts(cs_id, actor_did=secretary_did)
        assert len(artifacts) >= 6

        # 6. Verify receipts via SDK (including FinalResultReceipt)
        receipts = await client.coordination.list_receipts(cs_id, actor_did=secretary_did)
        assert len(receipts) >= 6
        assert any(r["receipt_type"] == "FinalResultReceipt" and r["stage"] == "final" for r in receipts)

        # 7. Verify closure via SDK
        closures_data = await client.coordination.closures(cs_id, actor_did=secretary_did)
        closures = closures_data.get("closures", [])
        assert len(closures) == 1
        assert closures[0]["status"] == "recorded"
        assert closures[0]["sla_status"] == "met"

        # 8. Verify list_sessions works
        sessions = await client.coordination.list_sessions(
            owner_did=owner["did"],
            actor_did=owner["did"],
        )
        assert len(sessions) >= 1
        assert any(s["coordination_session_id"] == cs_id for s in sessions)

    finally:
        await asgi_session.close()

