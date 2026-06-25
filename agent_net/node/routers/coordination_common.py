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
    CreateExecutionRequest,
    UpdateExecutionRequest,
    SubmitExecutionResultRequest,
)
from agent_net.storage import (
    create_coordination_session, get_coordination_session,
    list_coordination_sessions,
    create_session_link, get_session_links, get_session_link_by_child,
    create_delegation, get_delegation, update_delegation, list_delegations,
    emit_event, get_runtime_events,
    create_artifact, get_artifact, list_artifacts,
    create_receipt, get_receipt, list_receipts,
    create_decision_request, get_decision_request, list_decision_requests, resolve_decision_request,
    create_closure_record, list_closure_records,
    get_playbook_run, get_stage_executions_for_run, list_playbook_runs_for_coordination_session,
    get_intake, update_intake, create_intake,
    get_owner, is_secretary, save_capability_token, get_private_key, get_agent,
    create_enclave, add_enclave_member, create_playbook, get_playbook, create_playbook_run,
    update_playbook_run,
    store_stage_manifest, store_final_manifest,
    create_objective_execution, get_objective_execution,
    list_objective_executions,
    update_objective_execution, mark_execution_result,
)
from agent_net.node.loop_engine import next_action

router = APIRouter()


async def _verify_session_access(coordination_session_id: str, actor_did: str) -> dict:
    """Verify actor_did has access to the coordination session.

    Returns the session dict on success, raises HTTPException on failure.
    """
    sess = await get_coordination_session(coordination_session_id)
    if sess is None:
        raise HTTPException(404, f"Session {coordination_session_id} not found")
    await _verify_actor_can_access_session(sess, actor_did)
    return sess

# ── builtin Playbook definitions ────────────────────────────────

CODING_V1_PLAYBOOK_ID = "coding.v1"
CODING_V1_STAGES = [
    {
        "name": "clarify",
        "role": "clarifier",
        "description": "Clarify and freeze the requirement",
        "input_keys": [],
        "output_key": "clarify.md",
        "next": "design",
        "on_reject": "",
    },
    {
        "name": "design",
        "role": "designer",
        "description": "Produce design artifact",
        "input_keys": ["clarify.md"],
        "output_key": "design.md",
        "next": "design_review",
        "on_reject": "",
    },
    {
        "name": "design_review",
        "role": "reviewer",
        "description": "Review design artifact",
        "input_keys": ["design.md"],
        "output_key": "design_review.md",
        "next": "implement",
        "on_reject": "design",
    },
    {
        "name": "implement",
        "role": "developer",
        "description": "Implement the approved design",
        "input_keys": ["design.md", "design_review.md"],
        "output_key": "implement.patch",
        "next": "code_review",
        "on_reject": "",
    },
    {
        "name": "code_review",
        "role": "reviewer",
        "description": "Review implementation artifact",
        "input_keys": ["implement.patch"],
        "output_key": "code_review.md",
        "next": "test",
        "on_reject": "implement",
    },
    {
        "name": "test",
        "role": "tester",
        "description": "Run verification and produce test receipt",
        "input_keys": ["implement.patch", "code_review.md"],
        "output_key": "test_report.md",
        "next": "final",
        "on_reject": "implement",
    },
    {
        "name": "final",
        "role": "coordinator",
        "description": "Summarize final delivery",
        "input_keys": ["test_report.md"],
        "output_key": "final.md",
        "next": "",
        "on_reject": "",
    },
]


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _playbook_fingerprint(stages: list[dict]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(stages).encode("utf-8")).hexdigest()


async def _resolve_playbook(playbook_id: str, actor_did: str = "") -> dict:
    """Resolve a Playbook definition. Builtins are seeded into the Playbook store."""
    playbook_id = playbook_id or CODING_V1_PLAYBOOK_ID
    playbook = await get_playbook(playbook_id)
    if playbook:
        if not playbook.get("fingerprint"):
            playbook["fingerprint"] = _playbook_fingerprint(playbook.get("stages", []))
        if not playbook.get("version"):
            playbook["version"] = "1"
        return playbook

    if playbook_id != CODING_V1_PLAYBOOK_ID:
        raise HTTPException(404, f"Playbook not found: {playbook_id}")

    fingerprint = _playbook_fingerprint(CODING_V1_STAGES)
    await create_playbook(
        playbook_id=CODING_V1_PLAYBOOK_ID,
        name="Coding Coordination V1",
        stages=CODING_V1_STAGES,
        description="Builtin coding coordination workflow",
        created_by=actor_did or "system",
        version="1",
        fingerprint=fingerprint,
    )
    return await get_playbook(CODING_V1_PLAYBOOK_ID)


def _get_stage_def(workflow: dict, stage_name: str) -> dict | None:
    stages = workflow.get("stages", []) if isinstance(workflow, dict) else workflow
    for s in stages:
        if s.get("name") == stage_name:
            return s
    return None


async def _run_stage_snapshots(run: dict) -> list[dict]:
    context = run.get("context") or {}
    snapshots = context.get("stage_snapshots") or context.get("stages")
    if snapshots:
        return snapshots
    playbook = await get_playbook(run["playbook_id"])
    if not playbook:
        raise HTTPException(400, f"Playbook not found for run: {run['playbook_id']}")
    return playbook.get("stages", [])


async def _get_session_run(coordination_session_id: str, run_id: str) -> dict:
    run = await get_playbook_run(run_id)
    if not run:
        raise HTTPException(404, "Playbook run not found")
    if run.get("coordination_session_id") != coordination_session_id:
        raise HTTPException(404, "Playbook run is not attached to this coordination session")
    return run


def _first_stage_name(stages: list[dict]) -> str:
    if not stages:
        raise HTTPException(400, "Playbook has no stages")
    return stages[0]["name"]


async def _ensure_coordination_enclave(
    *,
    enclave_id: str | None,
    owner_did: str,
    controller_did: str,
    coordination_session_id: str,
) -> str:
    if enclave_id:
        return enclave_id
    from agent_net.enclave.models import Enclave

    new_enclave_id = Enclave.gen_id()
    await create_enclave(
        enclave_id=new_enclave_id,
        name=f"coord-{coordination_session_id[:8]}",
        owner_did=owner_did,
        vault_backend="local",
    )
    await add_enclave_member(
        enclave_id=new_enclave_id,
        did=owner_did,
        role="owner",
        permissions="admin",
        handbook="Coordination session owner",
    )
    if controller_did != owner_did:
        await add_enclave_member(
            enclave_id=new_enclave_id,
            did=controller_did,
            role="controller",
            permissions="rw",
            handbook="Coordination controller",
        )
    return new_enclave_id


async def _create_playbook_run_for_session(
    *,
    enclave_id: str,
    playbook: dict,
    objective: str,
    coordination_session_id: str,
    session_id: str,
    first_stage: str,
) -> str:
    from agent_net.enclave.models import PlaybookRun

    run_id = PlaybookRun.gen_id()
    await create_playbook_run(
        run_id=run_id,
        enclave_id=enclave_id,
        playbook_id=playbook["playbook_id"],
        playbook_name=playbook.get("name", playbook["playbook_id"]),
        coordination_session_id=coordination_session_id,
    )
    await update_playbook_run(
        run_id,
        current_stage=first_stage,
        context={
            "thread_id": run_id,
            "coordination_session_id": coordination_session_id,
            "session_id": session_id,
            "objective": objective,
            "current_stage": first_stage,
            "playbook_version": playbook.get("version", "1"),
            "playbook_fingerprint": playbook.get("fingerprint") or _playbook_fingerprint(playbook.get("stages", [])),
            "stage_snapshots": playbook.get("stages", []),
        },
    )
    return run_id


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


async def _verify_actor_can_represent_owner(owner_did: str, actor_did: str) -> dict:
    """Allow an Owner DID or one of its bound agents to answer for the Owner principal."""
    if not owner_did:
        raise HTTPException(400, "Missing owner_did")
    if not actor_did:
        raise HTTPException(400, "Missing actor_did")
    owner = await get_owner(owner_did)
    if not owner:
        raise HTTPException(404, "Owner not found")
    actor = await _verify_actor(actor_did)
    if actor_did == owner_did or actor.get("owner_did") == owner_did:
        return actor
    raise HTTPException(403, "Actor cannot represent this owner")


def _sse_frame(event: dict) -> str:
    data = json.dumps(event, ensure_ascii=False)
    return f"id: {event['event_id']}\nevent: {event['event_type']}\ndata: {data}\n\n"


def _vault_ref_payload(content_ref: str) -> dict:
    if not content_ref.startswith("vault://"):
        return {"uri": content_ref}
    ref = content_ref[len("vault://"):]
    enclave_id, _, key = ref.partition("/")
    return {"uri": content_ref, "enclave_id": enclave_id, "key": key}


def _manifest_artifact_item(artifact: dict, stage_def: dict | None = None) -> dict:
    output_key = (stage_def or {}).get("output_key") or artifact.get("artifact_type", "")
    return {
        "kind": output_key,
        "artifact_type": artifact.get("artifact_type", ""),
        "artifact_id": artifact.get("artifact_id", ""),
        "ref": _vault_ref_payload(artifact.get("content_ref", "")),
        "produced_by": artifact.get("producer_did", ""),
        "summary": artifact.get("artifact_type", ""),
        "checksum": artifact.get("content_hash", ""),
    }


async def _store_delivery_manifests_for_run(
    sess: dict,
    run_id: str,
    actor_did: str,
    playbook_id: str,
    artifacts: list[dict],
) -> dict:
    """Persist Delivery Manifest artifacts for a completed Coordination run."""
    stage_snapshots = await _run_stage_snapshots(await _get_session_run(sess["coordination_session_id"], run_id))
    stage_manifest_ids: list[str] = []
    stage_manifest_refs: list[str] = []
    final_artifacts: list[dict] = []

    for stage_def in stage_snapshots:
        stage_name = stage_def.get("name", "")
        if not stage_name:
            continue
        stage_artifacts = [a for a in artifacts if a.get("stage") == stage_name]
        if not stage_artifacts:
            continue
        manifest_artifacts = [_manifest_artifact_item(a, stage_def) for a in stage_artifacts]
        required_outputs = [stage_def["output_key"]] if stage_def.get("output_key") else []
        manifest = await store_stage_manifest(
            run_id=run_id,
            stage_name=stage_name,
            status="completed",
            artifacts=manifest_artifacts,
            required_outputs=required_outputs,
            produced_by=actor_did,
        )
        stage_manifest_ids.append(manifest["manifest_id"])
        stage_manifest_refs.append(f"vault://{sess.get('enclave_id', '')}/manifests/{run_id}/{stage_name}")
        final_artifacts.extend(manifest_artifacts)

    final_manifest = await store_final_manifest(
        run_id=run_id,
        status="completed",
        summary=f"Coordination session {sess['coordination_session_id']} completed with playbook {playbook_id}.",
        stage_manifest_ids=stage_manifest_ids,
        final_artifacts=final_artifacts,
        produced_by=actor_did,
    )
    final_manifest_ref = f"vault://{sess.get('enclave_id', '')}/manifests/{run_id}/final"
    return {
        "manifest_id": final_manifest["manifest_id"],
        "ref": final_manifest_ref,
        "stage_manifest_ids": stage_manifest_ids,
        "stage_manifest_refs": stage_manifest_refs,
        "artifact_count": len(final_artifacts),
    }


async def _record_final_closure(
    sess: dict,
    run_id: str,
    actor_did: str,
    playbook_id: str,
    artifacts: list[dict] | None = None,
    receipts: list[dict] | None = None,
) -> dict:
    """Create the V1 terminal audit objects once: FinalResultReceipt + closure/SLA record."""
    coordination_session_id = sess["coordination_session_id"]
    artifacts = artifacts if artifacts is not None else await list_artifacts(coordination_session_id, run_id=run_id)
    receipts = receipts if receipts is not None else await list_receipts(coordination_session_id, run_id=run_id)
    delivery_manifest = await _store_delivery_manifests_for_run(
        sess,
        run_id,
        actor_did,
        playbook_id,
        artifacts,
    )

    final_receipt = next(
        (r for r in receipts if r["stage"] == "final" and r["receipt_type"] == "FinalResultReceipt"),
        None,
    )
    if not final_receipt:
        final_receipt_id = f"rcpt_{uuid.uuid4().hex[:16]}"
        final_receipt = await create_receipt(
            receipt_id=final_receipt_id,
            coordination_session_id=coordination_session_id,
            run_id=run_id,
            stage="final",
            receipt_type="FinalResultReceipt",
            issuer_did=actor_did,
            decision="passed",
            evidence_refs=[
                f"coordination://sessions/{coordination_session_id}/timeline",
                delivery_manifest["ref"],
            ],
        )
        await emit_event(
            coordination_session_id=coordination_session_id,
            event_type="receipt.issued",
            stage="final",
            actor_did=actor_did,
            run_id=run_id,
            receipt_id=final_receipt_id,
            payload={"receipt_type": "FinalResultReceipt", "decision": "passed", "playbook_id": playbook_id},
        )

    closures = await list_closure_records(coordination_session_id)
    closure = next((s for s in closures if s["status"] == "recorded" and s.get("sla_metrics", {}).get("run_id") == run_id), None)
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
                "run_id": run_id,
                "playbook_id": playbook_id,
                "artifact_count": len(artifacts),
                "receipt_count": len(receipts) + (0 if any(r["receipt_id"] == final_receipt_id for r in receipts) else 1),
                "delivery_manifest": delivery_manifest,
            },
            receipt_id=final_receipt_id,
            evidence_refs=[
                f"coordination://sessions/{coordination_session_id}/receipts/{final_receipt_id}",
                delivery_manifest["ref"],
                *delivery_manifest["stage_manifest_refs"],
            ],
        )
        await emit_event(
            coordination_session_id=coordination_session_id,
            event_type="closure.recorded",
            stage="final",
            actor_did=actor_did,
            run_id=run_id,
            receipt_id=final_receipt_id,
            payload={
                "closure_id": closure_id,
                "status": "recorded",
                "sla_status": "met",
                "delivery_manifest_ref": delivery_manifest["ref"],
            },
        )

    return {"final_receipt": final_receipt, "closure": closure, "delivery_manifest": delivery_manifest}



__all__ = [name for name in globals() if not name.startswith("__")]
