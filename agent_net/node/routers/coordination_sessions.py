from .coordination_common import (
    CODING_V1_PLAYBOOK_ID,
    Depends,
    HTTPException,
    _create_playbook_run_for_session,
    _ensure_coordination_enclave,
    _first_stage_name,
    _get_session_run,
    _playbook_fingerprint,
    _require_token,
    _resolve_playbook,
    _run_stage_snapshots,
    _verify_actor,
    _verify_actor_can_access_session,
    _verify_actor_can_control_session,
    _verify_owner_bound_actor,
    create_coordination_session,
    create_session_link,
    emit_event,
    get_coordination_session,
    get_playbook,
    get_runtime_events,
    get_stage_executions_for_run,
    is_secretary,
    list_coordination_sessions,
    list_playbook_runs_for_coordination_session,
    router,
    uuid,
)

# ═══════════════════════════════════════════════════════════════
# Coordination Session API
# ═══════════════════════════════════════════════════════════════

@router.post("/coordination/sessions")
async def api_create_session(req: dict, _=Depends(_require_token)):
    """Create a coordination session and emit session.created event."""
    await _verify_owner_bound_actor(req["owner_did"], req["controller_did"])
    _id = req.get("coordination_session_id") or f"cs_{uuid.uuid4().hex[:16]}"
    playbook = await _resolve_playbook(req.get("playbook_id", CODING_V1_PLAYBOOK_ID), req["controller_did"])
    stage_snapshots = playbook.get("stages", [])
    first_stage = _first_stage_name(stage_snapshots)
    enclave_id = await _ensure_coordination_enclave(
        enclave_id=req.get("enclave_id"),
        owner_did=req["owner_did"],
        controller_did=req["controller_did"],
        coordination_session_id=_id,
    )
    run_id = await _create_playbook_run_for_session(
        enclave_id=enclave_id,
        playbook=playbook,
        objective=req["objective"],
        coordination_session_id=_id,
        session_id=req.get("intake_session_id") or _id,
        first_stage=first_stage,
    )
    sess = await create_coordination_session(
        coordination_session_id=_id,
        owner_did=req["owner_did"],
        controller_did=req["controller_did"],
        objective=req["objective"],
        enclave_id=enclave_id,
        playbook_id=playbook["playbook_id"],
        playbook_version=playbook.get("version", "1"),
        playbook_fingerprint=playbook.get("fingerprint") or _playbook_fingerprint(stage_snapshots),
        playbook_run_id=run_id,
        current_stage=first_stage,
        stage_snapshots=stage_snapshots,
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
        run_id=run_id,
        payload={
            "objective": req["objective"],
            "playbook_id": playbook["playbook_id"],
            "playbook_version": playbook.get("version", "1"),
            "playbook_fingerprint": playbook.get("fingerprint"),
            "enclave_id": enclave_id,
        },
    )
    await emit_event(
        coordination_session_id=_id,
        event_type="stage.started",
        stage=first_stage,
        actor_did=req.get("controller_did", ""),
        session_id=_id,
        run_id=run_id,
        payload={"source": "coordination.create"},
    )
    return {"status": "created", "session": sess}


@router.get("/coordination/sessions")
async def api_list_sessions(
    owner_did: str = "",
    actor_did: str = "",
    status: str = "",
    playbook_id: str = "",
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
            sec = await is_secretary(actor_did)
            if not sec or sec.get("owner_did") != owner_did:
                raise HTTPException(403, "Actor is not authorized to list sessions for this owner")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(403, "Actor is not authorized to list sessions for this owner")

    sessions = await list_coordination_sessions(
        owner_did=owner_did,
        status=status or None,
        playbook_id=playbook_id or None,
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
    parent_run = await _get_session_run(parent_id, parent["playbook_run_id"])
    stage_snapshots = await _run_stage_snapshots(parent_run)
    parent_current_stage = parent_run.get("current_stage") or _first_stage_name(stage_snapshots)
    playbook = await get_playbook(parent_run["playbook_id"])
    if not playbook:
        raise HTTPException(400, f"Playbook not found for parent run: {parent_run['playbook_id']}")

    child_id = f"cs_{uuid.uuid4().hex[:16]}"
    child_run_id = await _create_playbook_run_for_session(
        enclave_id=parent["enclave_id"],
        playbook={**playbook, "stages": stage_snapshots},
        objective=parent["objective"],
        coordination_session_id=child_id,
        session_id=child_id,
        first_stage=parent_current_stage,
    )
    child = await create_coordination_session(
        coordination_session_id=child_id,
        owner_did=parent["owner_did"],
        controller_did=parent["controller_did"],
        objective=parent["objective"],
        enclave_id=parent["enclave_id"],
        playbook_id=parent["playbook_id"],
        playbook_version=parent["playbook_version"],
        playbook_fingerprint=parent["playbook_fingerprint"],
        playbook_run_id=child_run_id,
        current_stage=parent_current_stage,
        stage_snapshots=stage_snapshots,
        parent_session_id=parent_id,
        status=parent_run["status"],
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
        run_id=parent_run["run_id"],
        payload={
            "parent_session_id": parent_id,
            "child_session_id": child_id,
            "link_type": link_type,
            "parent_run_id": parent_run["run_id"],
            "child_run_id": child_run_id,
        },
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

    stage_entries = []
    for run in await list_playbook_runs_for_coordination_session(coordination_session_id):
        stage_entries.extend(await get_stage_executions_for_run(run["run_id"]))

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
