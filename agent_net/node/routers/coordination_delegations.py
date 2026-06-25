from .coordination_common import (
    Depends,
    HTTPException,
    _get_session_run,
    _get_stage_def,
    _require_token,
    _run_stage_snapshots,
    _verify_actor,
    _verify_actor_can_control_session,
    create_delegation,
    emit_event,
    get_coordination_session,
    get_delegation,
    get_private_key,
    router,
    save_capability_token,
    update_delegation,
    uuid,
)

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

    run_id = req.get("run_id") or sess.get("playbook_run_id", "")
    run = await _get_session_run(coordination_session_id, run_id)
    stage_def = _get_stage_def(await _run_stage_snapshots(run), stage)
    if not stage_def:
        raise HTTPException(400, f"Unknown stage for session playbook: {stage}")

    role = req.get("role") or stage_def.get("role") or stage
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
            "input_keys": stage_def.get("input_keys", []),
            "output_key": stage_def.get("output_key", ""),
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
        run_id=run_id,
        delegation_id=delegation_id,
        payload={
            "role": role,
            "delegatee_did": delegatee_did,
            "capability_token_id": token_id,
            "input_keys": stage_def.get("input_keys", []),
            "output_key": stage_def.get("output_key", ""),
        },
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

