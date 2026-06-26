from .coordination_common import (
    CreateExecutionRequest,
    Depends,
    HTTPException,
    SubmitExecutionResultRequest,
    UpdateExecutionRequest,
    _require_token,
    _verify_session_access,
    create_artifact,
    create_decision_request,
    create_objective_execution,
    create_receipt,
    emit_event,
    get_coordination_session,
    get_objective_execution,
    json,
    list_objective_executions,
    mark_execution_result,
    next_action,
    router,
    time,
    update_objective_execution,
    uuid,
)

# ═══════════════════════════════════════════════════════════════════
# Objective Loop V1.1 — Execution API
# ═══════════════════════════════════════════════════════════════════

@router.get("/coordination/sessions/{coordination_session_id}/executions")
async def list_executions(
    coordination_session_id: str,
    actor_did: str = "",
    run_id: str = "",
    stage: str = "",
    _token_ok: bool = Depends(_require_token),
):
    """List objective_executions for a coordination session."""
    if not actor_did:
        raise HTTPException(400, "actor_did query parameter is required")
    await _verify_session_access(coordination_session_id, actor_did)
    executions = await list_objective_executions(
        coordination_session_id=coordination_session_id,
        run_id=run_id or None,
        stage=stage or None,
    )
    return {"status": "ok", "executions": executions, "count": len(executions)}


@router.get("/coordination/sessions/{coordination_session_id}/next-action")
async def get_next_action(
    coordination_session_id: str,
    actor_did: str = "",
    _token_ok: bool = Depends(_require_token),
):
    """Return the next action for a coordination session's current state."""
    if not actor_did:
        raise HTTPException(400, "actor_did query parameter is required")

    await _verify_session_access(coordination_session_id, actor_did)
    action = await next_action(coordination_session_id, actor_did)
    return {"status": "ok", "action": action}


@router.post("/coordination/executions")
async def create_execution(req: CreateExecutionRequest, _token_ok: bool = Depends(_require_token)):
    """Create a new objective_execution (execution lease).

    Idempotency: rejects if a pending/running execution already exists for
    the same coordination_session_id + run_id + stage.
    """
    await _verify_session_access(req.coordination_session_id, req.actor_did)

    # Guard: prevent duplicate active executions for the same stage
    active_execs = await list_objective_executions(
        coordination_session_id=req.coordination_session_id,
        run_id=req.run_id,
        stage=req.stage,
        status=None,
    )
    for ex in active_execs:
        if ex["status"] in ("pending", "running"):
            raise HTTPException(
                409,
                f"Stage '{req.stage}' already has an active execution "
                f"({ex['execution_id']} is {ex['status']}). "
                f"Wait for it to complete or time out before creating a new one."
            )

    eid = f"exec_{uuid.uuid4().hex[:16]}"
    lease = time.time() + req.lease_ttl_sec if req.lease_ttl_sec > 0 else None
    meta = req.metadata or {}
    retry_attempt = meta.pop("retry_attempt", 1)
    try:
        exec_record = await create_objective_execution(
            execution_id=eid,
            coordination_session_id=req.coordination_session_id,
            run_id=req.run_id,
            stage=req.stage,
            worker_did=req.worker_did,
            backend_kind=req.backend_kind,
            status="pending",
            lease_expires_at=lease,
            attempt=retry_attempt,
            metadata=meta if meta else None,
        )
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(
                409,
                f"Stage '{req.stage}' already has an active execution "
                f"for run {req.run_id}. "
                f"Wait for it to complete or time out before creating a new one."
            ) from e
        raise
    await emit_event(
        coordination_session_id=req.coordination_session_id,
        event_type="stage.started",
        stage=req.stage,
        actor_did=req.actor_did,
        run_id=req.run_id,
        payload={"execution_id": eid, "backend_kind": req.backend_kind},
    )
    return {"status": "created", "execution": exec_record}


@router.patch("/coordination/executions/{execution_id}")
async def patch_execution(
    execution_id: str,
    req: UpdateExecutionRequest,
    _token_ok: bool = Depends(_require_token),
):
    """Update an execution's status, lease, or metadata."""
    # Verify session access
    existing = await get_objective_execution(execution_id)
    if existing is None:
        raise HTTPException(404, f"Execution {execution_id} not found")
    await _verify_session_access(existing["coordination_session_id"], req.actor_did)
    updates = {}
    if req.status is not None:
        updates["status"] = req.status
    if req.lease_ttl_sec is not None:
        updates["lease_expires_at"] = time.time() + req.lease_ttl_sec
    if req.external_session_id is not None:
        updates["external_session_id"] = req.external_session_id
    if req.metadata is not None:
        updates["metadata"] = req.metadata
    ok = await update_objective_execution(execution_id, **updates)
    if not ok:
        raise HTTPException(404, f"Execution {execution_id} not found")
    return {"status": "updated", "execution_id": execution_id}


@router.post("/coordination/executions/{execution_id}/result")
async def submit_execution_result(
    execution_id: str,
    req: SubmitExecutionResultRequest,
    _token_ok: bool = Depends(_require_token),
):
    """Submit the result of an execution. Creates artifact + receipt. Idempotent."""
    import hashlib

    existing = await get_objective_execution(execution_id)
    if existing is None:
        raise HTTPException(404, f"Execution {execution_id} not found")
    await _verify_session_access(existing["coordination_session_id"], req.actor_did)

    r = req.result

    # Compute result hash
    hash_input = json.dumps({
        "execution_id": execution_id,
        "status": r.status,
        "artifact_type": r.artifact_type,
        "artifact_body": r.artifact_body,
        "summary": r.summary,
    }, sort_keys=True, ensure_ascii=False)
    result_hash = "sha256:" + hashlib.sha256(hash_input.encode()).hexdigest()

    existing = await get_objective_execution(execution_id)

    # Idempotency: same hash → return existing
    if existing.get("result_hash"):
        if existing["result_hash"] == result_hash:
            return {
                "status": "accepted",
                "execution_id": execution_id,
                "artifact_id": existing["artifact_id"],
                "receipt_id": existing["receipt_id"],
                "next_action_hint": "advance",
            }
        # Different hash → conflict
        raise HTTPException(409, "Execution already has a result with different hash")

    # Persist artifact body to vault
    import uuid as _uuid
    # Get enclave_id from the coordination session (not from execution record)
    sess_for_enclave = await get_coordination_session(existing["coordination_session_id"])
    enclave_id = sess_for_enclave.get("enclave_id", "") if sess_for_enclave else "default"
    vault_key = f"executions/{execution_id}/result.md"
    try:
        from agent_net.storage import vault_put
        await vault_put(
            enclave_id or "default",
            vault_key,
            r.artifact_body,
            req.actor_did,
        )
        content_ref = f"vault://{enclave_id or 'default'}/{vault_key}"
    except Exception:
        content_ref = r.artifact_body[:500]  # fallback

    # Create artifact
    art_id = f"art_{_uuid.uuid4().hex[:16]}"
    await create_artifact(
        artifact_id=art_id,
        coordination_session_id=existing["coordination_session_id"],
        run_id=existing["run_id"],
        stage=existing["stage"],
        artifact_type=r.artifact_type,
        producer_did=existing["worker_did"],
        content_ref=content_ref,
    )

    # Determine receipt decision
    if r.status == "completed":
        decision = "approved"
    elif r.status == "changes_requested":
        decision = "changes_requested"
    elif r.status == "failed":
        decision = "failed"
    else:
        decision = "blocked"

    # If blocked, create DecisionGate
    if r.status == "blocked" or decision == "blocked":
        if r.human_decision_request:
            question = r.human_decision_request.get("question", r.summary)
        else:
            question = r.summary or "Worker blocked"

        await create_decision_request(
            decision_id=f"dec_{_uuid.uuid4().hex[:16]}",
            owner_did=(await get_coordination_session(existing["coordination_session_id"])).get("owner_did", ""),
            coordination_session_id=existing["coordination_session_id"],
            run_id=existing["run_id"],
            stage=existing["stage"],
            requested_by_did=req.actor_did,
            question=question,
            options=["Retry", "Skip", "Abort"],
            recommended_option="Retry",
            risk_level="normal",
            evidence_refs=[execution_id],
        )

    # Create receipt
    rcpt_id = f"rcpt_{_uuid.uuid4().hex[:16]}"
    receipt_type = "FinalResultReceipt" if existing["stage"] == "final" else (
        "ReviewReceipt" if existing["stage"] in ("design_review", "code_review")
        else "DesignReceipt"
    )
    await create_receipt(
        receipt_id=rcpt_id,
        coordination_session_id=existing["coordination_session_id"],
        run_id=existing["run_id"],
        stage=existing["stage"],
        receipt_type=receipt_type,
        issuer_did=req.actor_did,
        decision=decision,
        subject_artifact_id=art_id,
        evidence_refs=r.evidence_refs,
    )

    # Mark execution result
    await mark_execution_result(
        execution_id,
        artifact_id=art_id,
        receipt_id=rcpt_id,
        result_hash=result_hash,
        status=r.status if r.status != "blocked" else "blocked",
    )

    # Emit event
    await emit_event(
        coordination_session_id=existing["coordination_session_id"],
        event_type="stage.completed",
        stage=existing["stage"],
        actor_did=req.actor_did,
        run_id=existing["run_id"],
        payload={
            "execution_id": execution_id,
            "artifact_id": art_id,
            "receipt_id": rcpt_id,
            "decision": decision,
            "status": r.status,
        },
    )

    return {
        "status": "accepted",
        "execution_id": execution_id,
        "artifact_id": art_id,
        "receipt_id": rcpt_id,
        "next_action_hint": "advance" if decision == "approved" else "retry",
    }
