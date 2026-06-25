from .coordination_common import (
    Depends,
    HTTPException,
    StreamingResponse,
    _get_session_run,
    _get_stage_def,
    _require_token,
    _run_stage_snapshots,
    _sse_frame,
    _verify_actor_can_access_session,
    _verify_actor_can_control_session,
    _verify_actor_can_represent_owner,
    asyncio,
    create_artifact,
    create_closure_record,
    create_decision_request,
    create_receipt,
    emit_event,
    get_coordination_session,
    get_decision_request,
    get_runtime_events,
    hashlib,
    list_artifacts,
    list_closure_records,
    list_decision_requests,
    list_receipts,
    resolve_decision_request,
    router,
    time,
    update_playbook_run,
    uuid,
)

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
    run_id = req.get("run_id") or sess.get("playbook_run_id", "")
    run = await _get_session_run(coord_id, run_id)
    if not _get_stage_def(await _run_stage_snapshots(run), stage):
        raise HTTPException(400, f"Unknown stage for session playbook: {stage}")

    # Compute content_hash from Vault content
    from agent_net.storage import vault_get
    if not content_ref.startswith("vault://"):
        raise HTTPException(400, "Artifact content_ref must be a vault:// reference")
    ref = content_ref[len("vault://"):]
    parts = ref.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(400, "Invalid vault artifact reference")
    if parts[0] != sess.get("enclave_id"):
        raise HTTPException(400, "Artifact content_ref enclave does not match coordination session")
    vault_entry = await vault_get(parts[0], parts[1])
    if not vault_entry or vault_entry.get("value") is None:
        raise HTTPException(400, "Artifact content_ref cannot be resolved from Vault")
    content_hash = "sha256:" + hashlib.sha256(vault_entry["value"].encode()).hexdigest()

    artifact_id = req.get("artifact_id") or f"art_{uuid.uuid4().hex[:16]}"
    artifact = await create_artifact(
        artifact_id=artifact_id,
        coordination_session_id=coord_id,
        run_id=run_id,
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
        run_id=run_id,
        artifact_id=artifact_id,
        payload={"artifact_type": req["artifact_type"], "content_hash": content_hash},
    )
    return {"status": "submitted", "artifact": artifact}


@router.get("/coordination/sessions/{coordination_session_id}/artifacts")
async def api_list_artifacts(coordination_session_id: str, stage: str = None, run_id: str = "", actor_did: str = "", _=Depends(_require_token)):
    """List artifacts for a session."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, actor_did)
    artifacts = await list_artifacts(coordination_session_id, stage=stage, run_id=run_id or None)
    return {"status": "ok", "artifacts": artifacts, "count": len(artifacts)}


@router.post("/coordination/receipts")
async def api_submit_receipt(req: dict, _=Depends(_require_token)):
    """Submit a receipt."""
    coord_id = req["coordination_session_id"]
    sess = await get_coordination_session(coord_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, req["issuer_did"])
    run_id = req.get("run_id") or sess.get("playbook_run_id", "")
    run = await _get_session_run(coord_id, run_id)
    if not _get_stage_def(await _run_stage_snapshots(run), req["stage"]):
        raise HTTPException(400, f"Unknown stage for session playbook: {req['stage']}")
    receipt_id = req.get("receipt_id") or f"rcpt_{uuid.uuid4().hex[:16]}"
    receipt = await create_receipt(
        receipt_id=receipt_id,
        coordination_session_id=coord_id,
        run_id=run_id,
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
        run_id=run_id,
        receipt_id=receipt_id,
        payload={"receipt_type": req["receipt_type"], "decision": req["decision"]},
    )
    return {"status": "issued", "receipt": receipt}


@router.get("/coordination/sessions/{coordination_session_id}/receipts")
async def api_list_receipts(coordination_session_id: str, stage: str = None, run_id: str = "", actor_did: str = "", _=Depends(_require_token)):
    """List receipts for a session."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, actor_did)
    receipts = await list_receipts(coordination_session_id, stage=stage, run_id=run_id or None)
    return {"status": "ok", "receipts": receipts, "count": len(receipts)}


@router.post("/coordination/decisions")
async def api_create_decision_request(req: dict, _=Depends(_require_token)):
    """Create an Owner/Decision Principal request and pause the stage until it is answered."""
    coord_id = req["coordination_session_id"]
    sess = await get_coordination_session(coord_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    requested_by = req.get("requested_by_did") or req.get("actor_did", "")
    await _verify_actor_can_control_session(sess, requested_by)

    owner_did = req.get("owner_did") or sess.get("owner_did", "")
    await _verify_actor_can_represent_owner(owner_did, owner_did)

    run_id = req.get("run_id") or sess.get("playbook_run_id", "")
    stage = req.get("stage") or ""
    if run_id:
        run = await _get_session_run(coord_id, run_id)
        if stage and not _get_stage_def(await _run_stage_snapshots(run), stage):
            raise HTTPException(400, f"Unknown stage for session playbook: {stage}")

    decision_id = req.get("decision_id") or f"dec_{uuid.uuid4().hex[:16]}"
    decision = await create_decision_request(
        decision_id=decision_id,
        owner_did=owner_did,
        coordination_session_id=coord_id,
        run_id=run_id,
        stage=stage,
        requested_by_did=requested_by,
        question=req["question"],
        options=req.get("options") or [],
        recommended_option=req.get("recommended_option", ""),
        risk_level=req.get("risk_level", "normal"),
        evidence_refs=req.get("evidence_refs") or [],
    )
    await emit_event(
        coordination_session_id=coord_id,
        event_type="decision.requested",
        stage=stage,
        actor_did=requested_by,
        run_id=run_id,
        payload={
            "decision_id": decision_id,
            "owner_did": owner_did,
            "question": req["question"],
            "risk_level": decision["risk_level"],
        },
    )
    return {"status": "pending", "decision": decision}


@router.get("/owner/decisions")
async def api_list_owner_decisions(owner_did: str, actor_did: str, status: str = "pending", _=Depends(_require_token)):
    """List decision requests addressed to an Owner/Decision Principal."""
    await _verify_actor_can_represent_owner(owner_did, actor_did)
    decisions = await list_decision_requests(owner_did=owner_did, status=status or None)
    return {"status": "ok", "decisions": decisions, "count": len(decisions)}


@router.post("/owner/decisions/{decision_id}/respond")
async def api_respond_owner_decision(decision_id: str, req: dict, _=Depends(_require_token)):
    """Resolve a DecisionRequest and turn it into an OwnerDecisionReceipt."""
    decision_req = await get_decision_request(decision_id)
    if not decision_req:
        raise HTTPException(404, "Decision request not found")
    if decision_req["status"] != "pending":
        raise HTTPException(400, f"Decision request is {decision_req['status']}")

    owner_did = decision_req["owner_did"]
    actor_did = req.get("actor_did", "")
    await _verify_actor_can_represent_owner(owner_did, actor_did)

    decision_value = req.get("decision", "")
    if decision_value not in {"approved", "passed", "changes_requested", "rejected", "failed", "aborted"}:
        raise HTTPException(400, "Unsupported decision")

    coord_id = decision_req["coordination_session_id"]
    sess = await get_coordination_session(coord_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_access_session(sess, actor_did)

    response = {
        "actor_did": actor_did,
        "decision": decision_value,
        "comment": req.get("comment", ""),
        "channel_ref": req.get("channel_ref", ""),
    }
    resolved = await resolve_decision_request(decision_id, status="resolved", response=response)

    receipt_id = req.get("receipt_id") or f"rcpt_{uuid.uuid4().hex[:16]}"
    evidence_refs = [
        f"coordination://decisions/{decision_id}",
        *decision_req.get("evidence_refs", []),
        *(req.get("evidence_refs") or []),
    ]
    receipt = await create_receipt(
        receipt_id=receipt_id,
        coordination_session_id=coord_id,
        run_id=decision_req.get("run_id", ""),
        stage=decision_req.get("stage", ""),
        receipt_type=req.get("receipt_type", "OwnerDecisionReceipt"),
        issuer_did=owner_did,
        decision=decision_value,
        subject_artifact_id=req.get("subject_artifact_id", ""),
        evidence_refs=evidence_refs,
        signature=req.get("signature", ""),
    )
    await emit_event(
        coordination_session_id=coord_id,
        event_type="decision.responded",
        stage=decision_req.get("stage", ""),
        actor_did=actor_did,
        run_id=decision_req.get("run_id", ""),
        receipt_id=receipt_id,
        payload={
            "decision_id": decision_id,
            "owner_did": owner_did,
            "decision": decision_value,
            "comment": response["comment"],
            "channel_ref": response["channel_ref"],
        },
    )
    await emit_event(
        coordination_session_id=coord_id,
        event_type="receipt.issued",
        stage=decision_req.get("stage", ""),
        actor_did=owner_did,
        run_id=decision_req.get("run_id", ""),
        receipt_id=receipt_id,
        payload={"receipt_type": receipt["receipt_type"], "decision": decision_value, "decision_id": decision_id},
    )
    if decision_value == "aborted" and decision_req.get("run_id"):
        await update_playbook_run(decision_req["run_id"], status="aborted", completed_at=time.time())

    return {"status": "resolved", "decision": resolved, "receipt": receipt}


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

