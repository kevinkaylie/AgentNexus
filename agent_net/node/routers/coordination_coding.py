from .coordination_common import (
    CODING_V1_PLAYBOOK_ID,
    Depends,
    HTTPException,
    _create_playbook_run_for_session,
    _ensure_coordination_enclave,
    _first_stage_name,
    _get_session_run,
    _get_stage_def,
    _playbook_fingerprint,
    _record_final_closure,
    _require_token,
    _resolve_playbook,
    _run_stage_snapshots,
    _verify_actor_can_access_session,
    _verify_actor_can_control_session,
    _verify_owner_bound_actor,
    create_artifact,
    create_coordination_session,
    create_intake,
    emit_event,
    get_coordination_session,
    list_artifacts,
    list_decision_requests,
    list_receipts,
    router,
    time,
    update_intake,
    update_playbook_run,
    uuid,
)

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
    playbook_id = req.get("preferred_playbook") or CODING_V1_PLAYBOOK_ID
    playbook = await _resolve_playbook(playbook_id, actor_did)
    stage_snapshots = playbook.get("stages", [])
    first_stage = _first_stage_name(stage_snapshots)
    enclave_id = await _ensure_coordination_enclave(
        enclave_id=req.get("enclave_id"),
        owner_did=owner_did,
        controller_did=actor_did,
        coordination_session_id=cs_id,
    )
    session_id = req.get("session_id") or f"sess_{uuid.uuid4().hex[:16]}"
    run_id = await _create_playbook_run_for_session(
        enclave_id=enclave_id,
        playbook=playbook,
        objective=objective,
        coordination_session_id=cs_id,
        session_id=session_id,
        first_stage=first_stage,
    )
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
        enclave_id=enclave_id,
        playbook_id=playbook["playbook_id"],
        playbook_version=playbook.get("version", "1"),
        playbook_fingerprint=playbook.get("fingerprint") or _playbook_fingerprint(stage_snapshots),
        playbook_run_id=run_id,
        current_stage=first_stage,
        stage_snapshots=stage_snapshots,
        intake_session_id=session_id,
        policy=policy,
    )

    await emit_event(
        coordination_session_id=cs_id,
        event_type="session.created",
        actor_did=actor_did,
        session_id=session_id,
        run_id=run_id,
        payload={
            "objective": objective,
            "playbook_id": playbook["playbook_id"],
            "playbook_version": playbook.get("version", "1"),
            "playbook_fingerprint": playbook.get("fingerprint"),
            "enclave_id": enclave_id,
            "policy": policy,
        },
    )
    await emit_event(
        coordination_session_id=cs_id,
        event_type="stage.started",
        stage=first_stage,
        actor_did=actor_did,
        session_id=session_id,
        run_id=run_id,
        payload={"source": "coding_intake"},
    )

    # Optionally create intake record if this actor is associated with a secretary
    from agent_net.storage import get_agent
    actor = await get_agent(actor_did)
    intake_info = None
    if actor and actor.get("owner_did") == owner_did:
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
            await update_intake(
                session_id,
                status="running",
                coordination_session_id=cs_id,
                run_id=run_id,
            )
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
    run_id = req.get("run_id") or sess.get("playbook_run_id", "")
    await _get_session_run(coordination_session_id, run_id)

    artifact_id = f"art_{uuid.uuid4().hex[:16]}"
    artifact = await create_artifact(
        artifact_id=artifact_id,
        coordination_session_id=coordination_session_id,
        run_id=run_id,
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
        run_id=run_id,
        artifact_id=artifact_id,
        payload={"artifact_type": "RequirementSpec", "requirement_spec": req.get("requirement_spec", {})},
    )
    return {"status": "clarified", "artifact": artifact}


@router.post("/coordination/coding/{coordination_session_id}/runs/{run_id}/advance")
async def api_coding_advance(coordination_session_id: str, run_id: str, req: dict, _=Depends(_require_token)):
    """Advance one PlaybookRun based on its stage snapshot and receipts."""
    sess = await get_coordination_session(coordination_session_id)
    if not sess:
        raise HTTPException(404, "Coordination session not found")
    await _verify_actor_can_control_session(sess, req.get("actor_did", ""))
    run = await _get_session_run(coordination_session_id, run_id)

    if run.get("status") == "completed":
        return {"status": "completed", "run_id": run_id, "current_stage": run.get("current_stage", "")}

    stage_snapshots = await _run_stage_snapshots(run)
    receipts = await list_receipts(coordination_session_id, run_id=run_id)
    artifacts = await list_artifacts(coordination_session_id, run_id=run_id)

    current_stage_name = run.get("current_stage") or _first_stage_name(stage_snapshots)

    stage_def = _get_stage_def(stage_snapshots, current_stage_name)
    if not stage_def:
        raise HTTPException(400, f"Unknown stage: {current_stage_name}")

    pending_decisions = await list_decision_requests(
        coordination_session_id=coordination_session_id,
        run_id=run_id,
        stage=current_stage_name,
        status="pending",
    )
    if pending_decisions:
        await emit_event(
            coordination_session_id=coordination_session_id,
            event_type="stage.blocked",
            stage=current_stage_name,
            actor_did=req.get("actor_did", ""),
            run_id=run_id,
            payload={
                "reason": "Awaiting owner decision",
                "decision_ids": [d["decision_id"] for d in pending_decisions],
            },
        )
        return {
            "status": "awaiting_owner_decision",
            "run_id": run_id,
            "current_stage": current_stage_name,
            "decisions": pending_decisions,
        }

    # Check receipt decisions for this stage
    stage_receipts = [r for r in receipts if r["stage"] == current_stage_name]
    has_approved = any(r["decision"] in ("approved", "passed") for r in stage_receipts)
    has_rejected = any(r["decision"] in ("changes_requested", "failed") for r in stage_receipts)

    if has_rejected:
        # Block or revert per Playbook snapshot's on_reject
        reject_target = stage_def.get("on_reject")
        if reject_target:
            await emit_event(
                coordination_session_id=coordination_session_id,
                event_type="stage.blocked",
                stage=current_stage_name,
                actor_did=req.get("actor_did", ""),
                run_id=run_id,
                payload={"reason": "Receipt rejected, reverting to " + reject_target},
            )
            await emit_event(
                coordination_session_id=coordination_session_id,
                event_type="stage.started",
                stage=reject_target,
                actor_did=req.get("actor_did", ""),
                run_id=run_id,
                payload={"previous_stage": current_stage_name, "reason": "on_reject"},
            )
            await update_playbook_run(run_id, current_stage=reject_target)
            return {
                "status": "reverted",
                "run_id": run_id,
                "current_stage": reject_target,
                "revert_to": reject_target,
                "previous_stage": current_stage_name,
            }
        else:
            await update_playbook_run(run_id, status="blocked")
            await emit_event(
                coordination_session_id=coordination_session_id,
                event_type="stage.blocked",
                stage=current_stage_name,
                actor_did=req.get("actor_did", ""),
                run_id=run_id,
                payload={"reason": "Receipt rejected, no on_reject target"},
            )
            return {"status": "blocked", "run_id": run_id, "current_stage": current_stage_name, "reason": "Receipt rejected"}

    stage_artifacts = [a for a in artifacts if a["stage"] == current_stage_name]
    if not stage_artifacts:
        raise HTTPException(400, f"Cannot advance {current_stage_name}: missing artifact")
    if not has_approved:
        raise HTTPException(400, f"Cannot advance {current_stage_name}: missing approved receipt")

    # Advance to next stage
    next_stage_name = stage_def.get("next")
    if not next_stage_name:
        # Final stage completed
        await update_playbook_run(
            run_id,
            status="completed",
            completed_at=time.time(),
        )
        closure = await _record_final_closure(
            sess,
            run_id,
            req.get("actor_did", ""),
            sess.get("playbook_id", ""),
            artifacts=artifacts,
            receipts=receipts,
        )
        return {"status": "completed", "run_id": run_id, "current_stage": current_stage_name, "closure": closure}

    next_def = _get_stage_def(stage_snapshots, next_stage_name)
    if not next_def:
        raise HTTPException(400, f"Unknown next stage: {next_stage_name}")

    if next_stage_name == "final" and not next_def.get("next"):
        await update_playbook_run(
            run_id,
            status="completed",
            current_stage=next_stage_name,
            completed_at=time.time(),
        )
        await emit_event(
            coordination_session_id=coordination_session_id,
            event_type="stage.started",
            stage=next_stage_name,
            actor_did=req.get("actor_did", ""),
            run_id=run_id,
            payload={"previous_stage": current_stage_name, "terminal": True},
        )
        closure = await _record_final_closure(
            {**sess, "current_stage": next_stage_name, "status": "completed"},
            run_id,
            req.get("actor_did", ""),
            sess.get("playbook_id", ""),
            artifacts=artifacts,
            receipts=receipts,
        )
        return {
            "status": "completed",
            "run_id": run_id,
            "current_stage": next_stage_name,
            "previous_stage": current_stage_name,
            "closure": closure,
        }

    await update_playbook_run(run_id, status="running", current_stage=next_stage_name)
    await emit_event(
        coordination_session_id=coordination_session_id,
        event_type="stage.started",
        stage=next_stage_name,
        actor_did=req.get("actor_did", ""),
        run_id=run_id,
        payload={"previous_stage": current_stage_name},
    )

    return {"status": "advanced", "run_id": run_id, "current_stage": next_stage_name, "previous_stage": current_stage_name}
