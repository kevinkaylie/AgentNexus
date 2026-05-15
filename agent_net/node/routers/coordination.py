"""Coordination endpoints -- Coding Coordination V1 Phase 1"""
import asyncio
import hashlib
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from agent_net.node._auth import (
    _require_token,
    _verify_actor,
    _verify_actor_is_owner,
    _verify_actor_is_secretary,
)
from agent_net.node._models import (
    CreateCoordinationSessionRequest,
    ForkSessionRequest,
    CreateDelegationRequest,
    AcceptDelegationRequest,
    RejectDelegationRequest,
    SubmitArtifactRequest,
    SubmitReceiptRequest,
    CreateRuntimeEventRequest,
    CodingIntakeRequest,
    CodingClarifyRequest,
    CodingAdvanceRequest,
)
from agent_net.storage import (
    create_coordination_session, get_coordination_session, update_coordination_session,
    list_coordination_sessions,
    create_session_link, get_session_links, get_session_link_by_child,
    create_delegation, get_delegation, update_delegation, list_delegations,
    emit_event, get_runtime_events,
    create_artifact, get_artifact, list_artifacts,
    create_receipt, get_receipt, list_receipts,
    create_closure_record, list_closure_records,
    get_playbook_run, get_stage_executions_for_run,
    get_intake, update_intake, create_intake,
    get_owner, is_secretary, save_capability_token, get_private_key, get_agent,
)

router = APIRouter()

# ── coding.v1 workflow template ────────────────────────────────

CODING_V1_TEMPLATE = {
    "workflow_id": "coding.v1",
    "stages": [
        {"name": "clarify", "role": "clarifier", "next": "design"},
        {"name": "design", "role": "designer", "next": "design_review"},
        {"name": "design_review", "role": "reviewer", "next": "implement", "on_reject": "design"},
        {"name": "implement", "role": "developer", "next": "code_review"},
        {"name": "code_review", "role": "reviewer", "next": "test", "on_reject": "implement"},
        {"name": "test", "role": "tester", "next": "final", "on_reject": "implement"},
        {"name": "final", "role": "coordinator", "next": None},
    ],
}


def _get_stage_def(workflow: dict, stage_name: str) -> dict | None:
    for s in workflow.get("stages", []):
        if s["name"] == stage_name:
            return s
    return None


async def _verify_actor_can_access_session(sess: dict, actor_did: str) -> dict:
    """Allow session owner, controller, owner's child agent, or session delegate."""
    if not actor_did:
        raise HTTPException(400, "Missing actor_did")

    actor = await _verify_actor(actor_did)
    owner_did = sess["owner_did"]
    if actor_did in {owner_did, sess["controller_did"]}:
        return actor
    if actor.get("owner_did") == owner_did:
        return actor

    delegations = await list_delegations(sess["coordination_session_id"])
    for delegation in delegations:
        if actor_did == delegation["delegator_did"]:
            return actor
        if actor_did == delegation["delegatee_did"] and delegation["status"] == "accepted":
            return actor

    raise HTTPException(403, "Actor is not authorized for this coordination session")


async def _verify_actor_can_control_session(sess: dict, actor_did: str) -> dict:
    """Allow only owner, controller, or owner's child agent to mutate workflow control."""
    actor = await _verify_actor_can_access_session(sess, actor_did)
    if actor_did in {sess["owner_did"], sess["controller_did"]} or actor.get("owner_did") == sess["owner_did"]:
        return actor
    raise HTTPException(403, "Actor cannot control this coordination session")


async def _verify_owner_bound_actor(owner_did: str, actor_did: str) -> dict:
    owner = await get_owner(owner_did)
    if not owner:
        raise HTTPException(404, "Owner not found")
    actor = await _verify_actor(actor_did)
    if actor_did == owner_did or actor.get("owner_did") == owner_did:
        return actor
    raise HTTPException(403, "Actor is not bound to this owner")


def _sse_frame(event: dict) -> str:
    data = json.dumps(event, ensure_ascii=False)
    return f"id: {event['event_id']}\nevent: {event['event_type']}\ndata: {data}\n\n"


async def _record_final_closure(
    sess: dict,
    actor_did: str,
    workflow_id: str,
    artifacts: list[dict] | None = None,
    receipts: list[dict] | None = None,
) -> dict:
    """Create the V1 terminal audit objects once: FinalResultReceipt + closure/SLA record."""
    coordination_session_id = sess["coordination_session_id"]
    artifacts = artifacts if artifacts is not None else await list_artifacts(coordination_session_id)
    receipts = receipts if receipts is not None else await list_receipts(coordination_session_id)

    final_receipt = next(
        (r for r in receipts if r["stage"] == "final" and r["receipt_type"] == "FinalResultReceipt"),
        None,
    )
    if not final_receipt:
        final_receipt_id = f"rcpt_{uuid.uuid4().hex[:16]}"
        final_receipt = await create_receipt(
            receipt_id=final_receipt_id,
            coordination_session_id=coordination_session_id,
            stage="final",
            receipt_type="FinalResultReceipt",
            issuer_did=actor_did,
            decision="passed",
            evidence_refs=[f"coordination://sessions/{coordination_session_id}/timeline"],
        )
        await emit_event(
            coordination_session_id=coordination_session_id,
            event_type="receipt.issued",
            stage="final",
            actor_did=actor_did,
            receipt_id=final_receipt_id,
            payload={"receipt_type": "FinalResultReceipt", "decision": "passed", "workflow_id": workflow_id},
        )

    closures = await list_closure_records(coordination_session_id)
    closure = next((s for s in closures if s["status"] == "recorded"), None)
    if not closure:
        closure_id = f"clo_{uuid.uuid4().hex[:16]}"
        final_receipt_id = final_receipt["receipt_id"]
        closure = await create_closure_record(
            closure_id=closure_id,
            coordination_session_id=coordination_session_id,
            actor_did=actor_did,
            status="recorded",
            sla_status="met",
            sla_metrics={
                "workflow_id": workflow_id,
                "artifact_count": len(artifacts),
                "receipt_count": len(receipts) + (0 if any(r["receipt_id"] == final_receipt_id for r in receipts) else 1),
            },
            receipt_id=final_receipt_id,
            evidence_refs=[f"coordination://sessions/{coordination_session_id}/receipts/{final_receipt_id}"],
        )
        await emit_event(
            coordination_session_id=coordination_session_id,
            event_type="closure.recorded",
            stage="final",
            actor_did=actor_did,
            receipt_id=final_receipt_id,
            payload={"closure_id": closure_id, "status": "recorded", "sla_status": "met"},
        )

    return {"final_receipt": final_receipt, "closure": closure}


# ═══════════════════════════════════════════════════════════════
# Coordination Session API
# ═══════════════════════════════════════════════════════════════

@router.post("/coordination/sessions")
async def api_create_session(req: dict, _=Depends(_require_token)):
    """Create a coordination session and emit session.created event."""
    await _verify_owner_bound_actor(req["owner_did"], req["controller_did"])
    _id = req.get("coordination_session_id") or f"cs_{uuid.uuid4().hex[:16]}"
    sess = await create_coordination_session(
        coordination_session_id=_id,
        owner_did=req["owner_did"],
        controller_did=req["controller_did"],
        objective=req["objective"],
        workflow_id=req.get("workflow_id", "coding.v1"),
        intake_session_id=req.get("intake_session_id"),
        parent_session_id=req.get("parent_session_id"),
        policy=req.get("policy"),
        context_snapshot=req.get("context_snapshot"),
    )
    await emit_event(
        coordination_session_id=_id,
        event_type="session.created",
        actor_did=req.get("controller_did", ""),
        session_id=_id,
        payload={"objective": req["objective"], "workflow_id": req.get("workflow_id", "coding.v1")},
    )
    return {"status": "created", "session": sess}


@router.get("/coordination/sessions")
async def api_list_sessions(
    owner_did: str = "",
    actor_did: str = "",
    status: str = "",
    workflow_id: str = "",
    _=Depends(_require_token),
):
    """List coordination sessions for an owner. Dashboard/CLI前置API."""
    if not owner_did:
        raise HTTPException(400, "Missing owner_did")
    if not actor_did:
        raise HTTPException(400, "Missing actor_did")

    actor = await _verify_actor(actor_did)
    agent_owner_did = actor.get("owner_did", "")

    # owner can see all their sessions; bound child agents can too
    if actor_did != owner_did and agent_owner_did != owner_did:
        # Non-owner actor: check if they are secretary for this owner
        try:
            sec = await is_secretary(owner_did, actor_did)
            if not sec:
                raise HTTPException(403, "Actor is not authorized to list sessions for this owner")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(403, "Actor is not authorized to list sessions for this owner")

    sessions = await list_coordination_sessions(
        owner_did=owner_did,
        status=status or None,
        workflow_id=workflow_id or None,
    )

    # For non-owner actors, filter to only sessions they can access
    if actor_did != owner_did:
        accessible = []
        for sess in sessions:
            try:
                await _verify_actor_can_access_session(sess, actor_did)
            except HTTPException:
                continue
            accessible.append(sess)
        sessions = accessible

    return {"status": "ok", "sessions": sessions, "count": len(sessions)}


@router.get("/coordination/sessions/{coordination_session_id}")
async def api_get_session(coordination_session_id: str, actor_did: str = "", _=Depends(_require_token)):
    """Get coordination session by ID."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, actor_did)
    return {"status": "ok", "session": sess}


@router.post("/coordination/sessions/fork")
async def api_fork_session(req: dict, _=Depends(_require_token)):
    """Fork a child coordination session."""
    parent_id = req["coordination_session_id"]
    actor_did = req.get("actor_did", "")
    link_type = req.get("link_type", "review_fork")

    parent = await get_coordination_session(parent_id)
    if not parent:
        raise HTTPException(404, "Parent session not found")
    await _verify_actor_can_control_session(parent, actor_did)

    child_id = f"cs_{uuid.uuid4().hex[:16]}"
    child = await create_coordination_session(
        coordination_session_id=child_id,
        owner_did=parent["owner_did"],
        controller_did=parent["controller_did"],
        objective=parent["objective"],
        workflow_id=parent["workflow_id"],
        parent_session_id=parent_id,
    )
    # Update root_session_id to match parent's root
    from agent_net.storage import DB_PATH
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE coordination_sessions SET root_session_id=? WHERE coordination_session_id=?",
            (parent.get("root_session_id", parent_id), child_id),
        )
        await db.commit()

    link_id = f"sl_{uuid.uuid4().hex[:16]}"
    await create_session_link(
        link_id=link_id,
        coordination_session_id=parent_id,
        from_session_id=parent_id,
        to_session_id=child_id,
        link_type=link_type,
        reason=req.get("reason", ""),
    )
    await emit_event(
        coordination_session_id=parent_id,
        event_type="session.forked",
        actor_did=actor_did,
        session_id=child_id,
        payload={"parent_session_id": parent_id, "child_session_id": child_id, "link_type": link_type},
    )
    return {"status": "forked", "session": child, "link_id": link_id}


@router.get("/coordination/sessions/{coordination_session_id}/timeline")
async def api_timeline(coordination_session_id: str, actor_did: str = "", _=Depends(_require_token)):
    """Timeline API: merge runtime_events + stage_executions from all linked playbook_runs."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, actor_did)

    # Gather runtime events
    events = await get_runtime_events(coordination_session_id)

    # Find all playbook_runs with this coordination_session_id
    from agent_net.storage import DB_PATH
    import aiosqlite
    stage_entries = []
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT run_id FROM playbook_runs WHERE coordination_session_id=?",
            (coordination_session_id,),
        ) as cur:
            run_rows = await cur.fetchall()

        for run_row in run_rows:
            run_id = run_row[0]
            async with db.execute(
                "SELECT * FROM stage_executions WHERE run_id=? ORDER BY started_at",
                (run_id,),
            ) as cur:
                exec_rows = await cur.fetchall()
            for er in exec_rows:
                stage_entries.append({
                    "run_id": er[0],
                    "stage_name": er[1],
                    "assigned_did": er[2] or "",
                    "status": er[3],
                    "task_id": er[4] or "",
                    "output_ref": er[5] or "",
                    "retry_count": er[6] or 0,
                    "started_at": er[7],
                    "completed_at": er[8],
                })

    # Normalize to unified timeline format
    timeline = []
    for evt in events:
        timeline.append({
            "timestamp": evt["created_at"],
            "source": "coordination",
            "event_type": evt["event_type"],
            "stage": evt["stage"],
            "actor_did": evt["actor_did"],
            "session_id": evt["session_id"],
            "run_id": evt["run_id"],
            "detail": evt["payload"],
        })
    for se in stage_entries:
        timeline.append({
            "timestamp": se["started_at"] or 0,
            "source": "stage_execution",
            "event_type": f"stage.{se['status']}",
            "stage": se["stage_name"],
            "actor_did": se["assigned_did"],
            "session_id": "",
            "run_id": se["run_id"],
            "detail": {
                "task_id": se["task_id"],
                "output_ref": se["output_ref"],
                "retry_count": se["retry_count"],
                "completed_at": se["completed_at"],
            },
        })

    timeline.sort(key=lambda x: x["timestamp"])
    return {"status": "ok", "coordination_session_id": coordination_session_id, "timeline": timeline}


# ═══════════════════════════════════════════════════════════════
# Stage / Delegation API
# ═══════════════════════════════════════════════════════════════

@router.post("/coordination/sessions/{coordination_session_id}/stages/{stage}/delegate")
async def api_delegate_stage(coordination_session_id: str, stage: str, req: dict, _=Depends(_require_token)):
    """Delegate a stage to a worker. Auto-issues capability token."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_control_session(sess, req.get("delegator_did", ""))

    role = req.get("role", stage)
    delegator_did = req.get("delegator_did", "")
    delegatee_did = req.get("delegatee_did", "")
    if not delegatee_did:
        raise HTTPException(400, "Missing delegatee_did")
    await _verify_actor(delegatee_did)

    issuer_did = delegator_did or sess["controller_did"]
    issuer_private_key = await get_private_key(issuer_did)
    if not issuer_private_key:
        raise HTTPException(403, "Delegator has no signing key for capability token")

    from agent_net.common.capability_token import issue_token, sign_token
    token = await issue_token(
        issuer_did=issuer_did,
        subject_did=delegatee_did,
        scope={
            "permissions": ["execute_stage"],
            "resource_pattern": f"coordination:{coordination_session_id}:{stage}",
            "role": role,
        },
        constraints={
            "spend_limit": 0,
            "max_delegation_depth": 1,
            "allowed_stages": [stage],
            "input_keys": [],
            "output_key": "",
        },
        validity_days=1,
        max_delegation_depth=1,
    )
    signed_token = sign_token(token, issuer_private_key)
    token_id = signed_token.token_id
    await save_capability_token(signed_token.to_dict())

    delegation_id = f"del_{uuid.uuid4().hex[:16]}"
    delegation = await create_delegation(
        delegation_id=delegation_id,
        coordination_session_id=coordination_session_id,
        stage=stage,
        role=role,
        delegator_did=delegator_did or sess["controller_did"],
        delegatee_did=delegatee_did,
        capability_token_id=token_id,
        runtime_kind=req.get("runtime_kind", "native_worker"),
        protocol=req.get("protocol", "agentnexus-native"),
        session_id=req.get("session_id", ""),
    )
    await emit_event(
        coordination_session_id=coordination_session_id,
        event_type="delegation.created",
        stage=stage,
        actor_did=delegator_did or sess["controller_did"],
        delegation_id=delegation_id,
        payload={"role": role, "delegatee_did": delegatee_did, "capability_token_id": token_id},
    )
    return {"status": "delegated", "delegation": delegation}


@router.post("/coordination/delegations/{delegation_id}/accept")
async def api_accept_delegation(delegation_id: str, req: dict, _=Depends(_require_token)):
    """Accept a delegation."""
    delegation = await get_delegation(delegation_id)
    if not delegation:
        raise HTTPException(404, "Delegation not found")
    if delegation["status"] != "pending":
        raise HTTPException(400, f"Delegation is {delegation['status']}")
    if req.get("actor_did") != delegation["delegatee_did"]:
        raise HTTPException(403, "Only delegatee can accept delegation")
    await _verify_actor(req.get("actor_did", ""))

    await update_delegation(delegation_id, status="accepted")
    await emit_event(
        coordination_session_id=delegation["coordination_session_id"],
        event_type="delegation.accepted",
        stage=delegation["stage"],
        actor_did=req.get("actor_did", ""),
        delegation_id=delegation_id,
    )
    return {"status": "accepted", "delegation_id": delegation_id}


@router.post("/coordination/delegations/{delegation_id}/reject")
async def api_reject_delegation(delegation_id: str, req: dict, _=Depends(_require_token)):
    """Reject a delegation."""
    delegation = await get_delegation(delegation_id)
    if not delegation:
        raise HTTPException(404, "Delegation not found")
    if delegation["status"] != "pending":
        raise HTTPException(400, f"Delegation is {delegation['status']}")
    actor_did = req.get("actor_did", "")
    if actor_did not in {delegation["delegatee_did"], delegation["delegator_did"]}:
        raise HTTPException(403, "Only delegator or delegatee can reject delegation")
    await _verify_actor(actor_did)

    await update_delegation(delegation_id, status="rejected")
    reason = req.get("reason", "")
    await emit_event(
        coordination_session_id=delegation["coordination_session_id"],
        event_type="delegation.rejected",
        stage=delegation["stage"],
        actor_did=req.get("actor_did", ""),
        delegation_id=delegation_id,
        payload={"reason": reason},
    )
    return {"status": "rejected", "delegation_id": delegation_id, "reason": reason}


# ═══════════════════════════════════════════════════════════════
# Event / Artifact / Receipt API
# ═══════════════════════════════════════════════════════════════

@router.post("/coordination/events")
async def api_create_event(req: dict, _=Depends(_require_token)):
    """Manually write a runtime event."""
    event_id = req.get("event_id") or f"evt_{uuid.uuid4().hex[:16]}"
    # Verify coordination session exists
    sess = await get_coordination_session(req["coordination_session_id"])
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, req.get("actor_did", ""))

    from agent_net.storage import create_runtime_event as _create_evt
    result = await _create_evt(
        event_id=event_id,
        coordination_session_id=req["coordination_session_id"],
        event_type=req["event_type"],
        stage=req.get("stage", ""),
        actor_did=req.get("actor_did", ""),
        session_id=req.get("session_id", ""),
        run_id=req.get("run_id", ""),
        delegation_id=req.get("delegation_id", ""),
        artifact_id=req.get("artifact_id", ""),
        receipt_id=req.get("receipt_id", ""),
        payload=req.get("payload"),
    )
    return {"status": "recorded", "event": result}


@router.get("/coordination/sessions/{coordination_session_id}/events")
async def api_list_events(coordination_session_id: str, stage: str = None, event_type: str = None, actor_did: str = "", _=Depends(_require_token)):
    """List runtime events for a session."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, actor_did)
    events = await get_runtime_events(coordination_session_id, stage=stage, event_type=event_type)
    return {"status": "ok", "events": events, "count": len(events)}


@router.get("/coordination/sessions/{coordination_session_id}/events/stream")
async def api_stream_events(
    coordination_session_id: str,
    actor_did: str = "",
    last_event_id: str = "",
    limit: int = 0,
    poll_interval: float = 0.5,
    heartbeat_seconds: float = 15.0,
    timeout_seconds: float = 0,
    _=Depends(_require_token),
):
    """SSE stream for runtime events. Use limit>0 for finite replay/testing."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, actor_did)

    async def event_generator():
        emitted = set()
        replaying = not bool(last_event_id)
        emitted_count = 0
        started_at = time.time()
        last_heartbeat = started_at

        while True:
            events = await get_runtime_events(coordination_session_id)
            for evt in events:
                event_id = evt["event_id"]
                if not replaying:
                    if event_id == last_event_id:
                        replaying = True
                    continue
                if event_id in emitted:
                    continue
                emitted.add(event_id)
                emitted_count += 1
                yield _sse_frame(evt)
                if limit > 0 and emitted_count >= limit:
                    return

            now = time.time()
            if timeout_seconds > 0 and now - started_at >= timeout_seconds:
                return
            if heartbeat_seconds > 0 and now - last_heartbeat >= heartbeat_seconds:
                last_heartbeat = now
                yield ": heartbeat\n\n"
            await asyncio.sleep(max(poll_interval, 0.1))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/coordination/artifacts")
async def api_submit_artifact(req: dict, _=Depends(_require_token)):
    """Submit an artifact. Server computes content_hash from Vault."""
    coord_id = req["coordination_session_id"]
    stage = req["stage"]
    content_ref = req["content_ref"]
    sess = await get_coordination_session(coord_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, req["producer_did"])

    # Compute content_hash from Vault content
    from agent_net.storage import vault_get
    if not content_ref.startswith("vault://"):
        raise HTTPException(400, "Artifact content_ref must be a vault:// reference")
    ref = content_ref[len("vault://"):]
    parts = ref.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(400, "Invalid vault artifact reference")
    vault_entry = await vault_get(parts[0], parts[1])
    if not vault_entry or vault_entry.get("value") is None:
        raise HTTPException(400, "Artifact content_ref cannot be resolved from Vault")
    content_hash = "sha256:" + hashlib.sha256(vault_entry["value"].encode()).hexdigest()

    artifact_id = req.get("artifact_id") or f"art_{uuid.uuid4().hex[:16]}"
    artifact = await create_artifact(
        artifact_id=artifact_id,
        coordination_session_id=coord_id,
        stage=stage,
        artifact_type=req["artifact_type"],
        producer_did=req["producer_did"],
        content_ref=content_ref,
        content_hash=content_hash,
        schema_version=req.get("schema_version", "1"),
    )
    await emit_event(
        coordination_session_id=coord_id,
        event_type="artifact.submitted",
        stage=stage,
        actor_did=req["producer_did"],
        artifact_id=artifact_id,
        payload={"artifact_type": req["artifact_type"], "content_hash": content_hash},
    )
    return {"status": "submitted", "artifact": artifact}


@router.get("/coordination/sessions/{coordination_session_id}/artifacts")
async def api_list_artifacts(coordination_session_id: str, stage: str = None, actor_did: str = "", _=Depends(_require_token)):
    """List artifacts for a session."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, actor_did)
    artifacts = await list_artifacts(coordination_session_id, stage=stage)
    return {"status": "ok", "artifacts": artifacts, "count": len(artifacts)}


@router.post("/coordination/receipts")
async def api_submit_receipt(req: dict, _=Depends(_require_token)):
    """Submit a receipt."""
    coord_id = req["coordination_session_id"]
    sess = await get_coordination_session(coord_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, req["issuer_did"])
    receipt_id = req.get("receipt_id") or f"rcpt_{uuid.uuid4().hex[:16]}"
    receipt = await create_receipt(
        receipt_id=receipt_id,
        coordination_session_id=coord_id,
        stage=req["stage"],
        receipt_type=req["receipt_type"],
        issuer_did=req["issuer_did"],
        decision=req["decision"],
        subject_artifact_id=req.get("subject_artifact_id", ""),
        evidence_refs=req.get("evidence_refs"),
        signature=req.get("signature", ""),
    )
    await emit_event(
        coordination_session_id=coord_id,
        event_type="receipt.issued",
        stage=req["stage"],
        actor_did=req["issuer_did"],
        receipt_id=receipt_id,
        payload={"receipt_type": req["receipt_type"], "decision": req["decision"]},
    )
    return {"status": "issued", "receipt": receipt}


@router.get("/coordination/sessions/{coordination_session_id}/receipts")
async def api_list_receipts(coordination_session_id: str, stage: str = None, actor_did: str = "", _=Depends(_require_token)):
    """List receipts for a session."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, actor_did)
    receipts = await list_receipts(coordination_session_id, stage=stage)
    return {"status": "ok", "receipts": receipts, "count": len(receipts)}


@router.post("/coordination/closures")
async def api_create_closure(req: dict, _=Depends(_require_token)):
    """Record V1 coding delivery closure and SLA audit evidence."""
    coord_id = req["coordination_session_id"]
    sess = await get_coordination_session(coord_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    actor_did = req.get("actor_did", "")
    await _verify_actor_can_control_session(sess, actor_did)

    closure_id = req.get("closure_id") or f"clo_{uuid.uuid4().hex[:16]}"
    closure = await create_closure_record(
        closure_id=closure_id,
        coordination_session_id=coord_id,
        actor_did=actor_did,
        status=req.get("status", "recorded"),
        sla_status=req.get("sla_status", "not_applicable"),
        sla_metrics=req.get("sla_metrics") or {},
        receipt_id=req.get("receipt_id", ""),
        evidence_refs=req.get("evidence_refs") or [],
    )
    await emit_event(
        coordination_session_id=coord_id,
        event_type="closure.recorded",
        stage=req.get("stage", "final"),
        actor_did=actor_did,
        receipt_id=req.get("receipt_id", ""),
        payload={
            "closure_id": closure_id,
            "status": closure["status"],
            "sla_status": closure["sla_status"],
        },
    )
    return {"status": "recorded", "closure": closure}


@router.get("/coordination/sessions/{coordination_session_id}/closures")
async def api_list_closures(coordination_session_id: str, status: str = None, actor_did: str = "", _=Depends(_require_token)):
    """List coding closure/SLA records for a session."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, actor_did)
    closures = await list_closure_records(coordination_session_id, status=status)
    return {"status": "ok", "closures": closures, "count": len(closures)}


# ═══════════════════════════════════════════════════════════════
# Coding Workflow API
# ═══════════════════════════════════════════════════════════════

@router.post("/coordination/coding/intake")
async def api_coding_intake(req: dict, _=Depends(_require_token)):
    """Coding-specific intake: creates coordination session and links to intake."""
    owner_did = req["owner_did"]
    actor_did = req["actor_did"]
    objective = req["objective"]

    await _verify_owner_bound_actor(owner_did, actor_did)

    # Create root coordination session
    cs_id = f"cs_{uuid.uuid4().hex[:16]}"
    policy = {
        "complexity": req.get("complexity", "medium"),
        "risk_level": req.get("risk_level", "normal"),
        "cost_policy": req.get("cost_policy", "balanced"),
        "data_sensitivity": req.get("data_sensitivity", "internal"),
        "requires_human_approval": req.get("requires_human_approval", False),
    }
    sess = await create_coordination_session(
        coordination_session_id=cs_id,
        owner_did=owner_did,
        controller_did=actor_did,
        objective=objective,
        workflow_id="coding.v1",
        policy=policy,
    )

    await emit_event(
        coordination_session_id=cs_id,
        event_type="session.created",
        actor_did=actor_did,
        session_id=cs_id,
        payload={"objective": objective, "workflow_id": "coding.v1", "policy": policy},
    )

    # Optionally create intake record if this actor is associated with a secretary
    from agent_net.storage import get_agent
    actor = await get_agent(actor_did)
    intake_info = None
    if actor and actor.get("owner_did") == owner_did:
        session_id = req.get("session_id") or f"sess_{uuid.uuid4().hex[:16]}"
        try:
            import time
            await create_intake(
                session_id=session_id,
                owner_did=owner_did,
                actor_did=actor_did,
                objective=objective,
                required_roles=["clarifier", "designer", "developer", "reviewer", "tester"],
                preferred_playbook=req.get("preferred_playbook"),
                source_channel=req.get("source", {}).get("channel"),
                source_message_ref=req.get("source", {}).get("message_ref"),
            )
            await update_intake(session_id, coordination_session_id=cs_id)
            intake_info = {"session_id": session_id, "status": "intake"}
        except Exception:
            pass  # intake creation is optional

    return {"status": "intake", "session": sess, "intake": intake_info}


@router.post("/coordination/coding/{coordination_session_id}/clarify")
async def api_coding_clarify(coordination_session_id: str, req: dict, _=Depends(_require_token)):
    """Submit clarification artifact (RequirementSpec)."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, req.get("actor_did", ""))

    artifact_id = f"art_{uuid.uuid4().hex[:16]}"
    artifact = await create_artifact(
        artifact_id=artifact_id,
        coordination_session_id=coordination_session_id,
        stage="clarify",
        artifact_type="RequirementSpec",
        producer_did=req.get("actor_did", ""),
        content_ref=req.get("content_ref", f"vault://requirement/{artifact_id}"),
    )
    await emit_event(
        coordination_session_id=coordination_session_id,
        event_type="artifact.submitted",
        stage="clarify",
        actor_did=req.get("actor_did", ""),
        artifact_id=artifact_id,
        payload={"artifact_type": "RequirementSpec", "requirement_spec": req.get("requirement_spec", {})},
    )
    await update_coordination_session(coordination_session_id, status="clarified")
    return {"status": "clarified", "artifact": artifact}


@router.post("/coordination/coding/{coordination_session_id}/advance")
async def api_coding_advance(coordination_session_id: str, req: dict, _=Depends(_require_token)):
    """Advance coding workflow to next stage based on receipts and template."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_control_session(sess, req.get("actor_did", ""))

    workflow_id = sess.get("workflow_id", "coding.v1")
    workflow = CODING_V1_TEMPLATE if workflow_id == "coding.v1" else {"stages": []}

    # Determine current stage from events and artifacts
    events = await get_runtime_events(coordination_session_id)
    receipts = await list_receipts(coordination_session_id)
    artifacts = await list_artifacts(coordination_session_id)

    # Find current stage based on latest activity
    current_stage_name = "clarify"
    latest_time = 0
    for evt in events:
        if evt["stage"] and evt["created_at"] > latest_time:
            current_stage_name = evt["stage"]
            latest_time = evt["created_at"]

    stage_def = _get_stage_def(workflow, current_stage_name)
    if not stage_def:
        raise HTTPException(400, f"Unknown stage: {current_stage_name}")

    # Check receipt decisions for this stage
    stage_receipts = [r for r in receipts if r["stage"] == current_stage_name]
    has_approved = any(r["decision"] in ("approved", "passed") for r in stage_receipts)
    has_rejected = any(r["decision"] in ("changes_requested", "failed") for r in stage_receipts)

    if has_rejected:
        # Block or revert per template's on_reject
        reject_target = stage_def.get("on_reject")
        if reject_target:
            await update_coordination_session(coordination_session_id, status=f"reverted_to_{reject_target}")
            await emit_event(
                coordination_session_id=coordination_session_id,
                event_type="stage.blocked",
                stage=current_stage_name,
                actor_did=req.get("actor_did", ""),
                payload={"reason": "Receipt rejected, reverting to " + reject_target},
            )
            return {"status": "reverted", "current_stage": current_stage_name, "revert_to": reject_target}
        else:
            await emit_event(
                coordination_session_id=coordination_session_id,
                event_type="stage.blocked",
                stage=current_stage_name,
                actor_did=req.get("actor_did", ""),
                payload={"reason": "Receipt rejected, no on_reject target"},
            )
            return {"status": "blocked", "current_stage": current_stage_name, "reason": "Receipt rejected"}

    stage_artifacts = [a for a in artifacts if a["stage"] == current_stage_name]
    if not stage_artifacts:
        raise HTTPException(400, f"Cannot advance {current_stage_name}: missing artifact")
    if not has_approved:
        raise HTTPException(400, f"Cannot advance {current_stage_name}: missing approved receipt")

    # Advance to next stage
    next_stage_name = stage_def.get("next")
    if not next_stage_name:
        # Final stage completed
        await update_coordination_session(coordination_session_id, status="completed")
        closure = await _record_final_closure(
            sess,
            req.get("actor_did", ""),
            workflow_id,
            artifacts=artifacts,
            receipts=receipts,
        )
        return {"status": "completed", "current_stage": current_stage_name, "closure": closure}

    # Check if next stage is terminal (no further stages)
    next_def = _get_stage_def(workflow, next_stage_name)
    is_terminal = next_def and not next_def.get("next")

    await update_coordination_session(coordination_session_id, status=next_stage_name)
    await emit_event(
        coordination_session_id=coordination_session_id,
        event_type="stage.started",
        stage=next_stage_name,
        actor_did=req.get("actor_did", ""),
        payload={"previous_stage": current_stage_name},
    )
    if is_terminal:
        await update_coordination_session(coordination_session_id, status="completed")
        closure = await _record_final_closure(
            sess,
            req.get("actor_did", ""),
            workflow_id,
            artifacts=artifacts,
            receipts=receipts,
        )
        return {
            "status": "completed",
            "current_stage": next_stage_name,
            "previous_stage": current_stage_name,
            "closure": closure,
        }

    return {"status": "advanced", "current_stage": next_stage_name, "previous_stage": current_stage_name}
