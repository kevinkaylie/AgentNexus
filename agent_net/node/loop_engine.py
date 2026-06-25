"""Objective Loop Engine — state machine for next-action computation.

Design ref: docs/design/design-objective-loop-v1.1.md Sections 4.2, 7, 8, 9

The Loop Engine is a pure state machine: it reads session/run/execution/receipt/decision
state and returns the next action. It does NOT execute actions — that's the caller's job.
"""
from __future__ import annotations

import time

from agent_net.storage import (
    get_coordination_session,
    get_playbook_run,
    get_playbook,
    list_objective_executions,
    list_artifacts,
    list_receipts,
    list_decision_requests,
)

# Default max retries per stage (overrideable via objective constraints)
DEFAULT_MAX_RETRIES = 2


async def next_action(
    coordination_session_id: str,
    controller_did: str,
) -> dict:
    """Compute the next action for a coordination session.

    Returns a dict with at minimum: action_type, stage, reason.
    See design doc section 11.3 for action_type enum.
    """
    sess = await get_coordination_session(coordination_session_id)
    if sess is None:
        return {
            "action_type": "blocked",
            "stage": "",
            "reason": f"Session {coordination_session_id} not found",
        }

    # Check session status
    if sess["status"] in ("completed", "closed", "aborted", "failed"):
        return {
            "action_type": "closed",
            "stage": sess.get("current_stage", ""),
            "reason": f"Session status is {sess['status']}",
        }

    run_id = sess.get("playbook_run_id", "")
    if not run_id:
        return {
            "action_type": "blocked",
            "stage": "",
            "reason": "No playbook_run_id on session",
        }

    run = await get_playbook_run(run_id)
    if run is None:
        return {
            "action_type": "blocked",
            "stage": "",
            "reason": f"PlaybookRun {run_id} not found",
        }

    run_status = run.get("status", "running")
    if run_status in ("completed", "closed", "aborted", "failed"):
        return {
            "action_type": "closed",
            "stage": run.get("current_stage", ""),
            "reason": f"Run status is {run_status}",
        }

    current_stage = run.get("current_stage", "") or sess.get("current_stage", "")
    if not current_stage:
        return {
            "action_type": "blocked",
            "stage": "",
            "reason": "No current_stage on run",
        }

    # Get playbook for stage definitions
    playbook_id = sess.get("playbook_id", "coding.v1")
    playbook = await get_playbook(playbook_id)
    stages_list = playbook.get("stages", []) if playbook else []
    stage_map = {s["name"]: s for s in stages_list}
    current_stage_def = stage_map.get(current_stage, {})
    next_stage_name = current_stage_def.get("next", "")
    on_reject_stage = current_stage_def.get("on_reject", "")

    # ── Check pending decisions ──────────────────────────────────────
    pending_decisions = await list_decision_requests(
        coordination_session_id=coordination_session_id,
        run_id=run_id,
        stage=current_stage,
        status="pending",
    )
    if pending_decisions:
        return {
            "action_type": "wait",
            "stage": current_stage,
            "reason": f"{len(pending_decisions)} pending decision(s) for stage {current_stage}",
            "pending_decision_ids": [d["decision_id"] for d in pending_decisions],
        }

    # ── Check existing executions for current stage ──────────────────
    executions = await list_objective_executions(
        coordination_session_id=coordination_session_id,
        run_id=run_id,
        stage=current_stage,
    )

    # Get policy for retry limits
    policy = sess.get("policy_json", {})
    if isinstance(policy, str):
        import json
        policy = json.loads(policy) if policy else {}
    max_retries = policy.get("max_retries_per_stage", DEFAULT_MAX_RETRIES)

    # ── Budget checks ──────────────────────────────────────────────
    max_total = policy.get("max_total_executions", 30)
    max_wall_clock = policy.get("max_wall_clock_sec", 14400)

    all_execs = await list_objective_executions(
        coordination_session_id=coordination_session_id,
    )
    if len(all_execs) >= max_total:
        return {
            "action_type": "create_decision_gate",
            "stage": current_stage,
            "reason": (
                f"Total executions ({len(all_execs)}) exceeded "
                f"budget ({max_total})"
            ),
            "gate": "max_retry_exceeded",
        }

    session_created = sess.get("created_at", 0)
    if session_created and (time.time() - session_created) > max_wall_clock:
        return {
            "action_type": "create_decision_gate",
            "stage": current_stage,
            "reason": (
                f"Wall clock ({time.time() - session_created:.0f}s) "
                f"exceeded budget ({max_wall_clock}s)"
            ),
            "gate": "max_retry_exceeded",
        }

    if executions:
        latest = executions[0]  # ordered by created_at DESC

        # Blocked execution → check for resolved decision first
        if latest["status"] == "blocked":
            # Check if there's already a resolved decision for this stage
            decisions = await list_decision_requests(
                coordination_session_id=coordination_session_id,
                run_id=run_id,
                stage=current_stage,
            )
            resolved_decisions = [d for d in decisions if d.get("status") in ("resolved", "approved", "denied")]
            if resolved_decisions:
                latest_decision = resolved_decisions[0]  # newest first
                response = latest_decision.get("response", {})
                if isinstance(response, str):
                    import json as _json
                    response = _json.loads(response) if response else {}
                decision_value = response.get("decision", "")
                if decision_value == "approved":
                    # Human approved retry — skip blocked execution, start new
                    return {
                        "action_type": "start_execution",
                        "stage": current_stage,
                        "role": current_stage_def.get("role", ""),
                        "reason": f"Blocked execution resolved: retry approved by human",
                        "retry_attempt": latest["attempt"] + 1,
                    }
                elif decision_value in ("rejected", "aborted"):
                    return {
                        "action_type": "closed",
                        "stage": current_stage,
                        "reason": (
                            f"Stage {current_stage} {decision_value} by human. "
                            f"Session cannot continue."
                        ),
                    }

            meta = latest.get("metadata", {})
            if isinstance(meta, str):
                import json
                meta = json.loads(meta) if meta else {}
            return {
                "action_type": "create_decision_gate",
                "stage": current_stage,
                "reason": f"Execution {latest['execution_id']} is blocked: {meta.get('reason', 'unknown')}",
                "execution_id": latest["execution_id"],
                "gate": meta.get("gate", "low_confidence"),
            }

        # Timed out or failed → retry or decision gate
        if latest["status"] in ("timed_out", "failed", "cancelled"):
            if latest["attempt"] >= max_retries:
                return {
                    "action_type": "create_decision_gate",
                    "stage": current_stage,
                    "reason": f"Stage {current_stage} exceeded max retries ({max_retries})",
                    "execution_id": latest["execution_id"],
                    "gate": "max_retry_exceeded",
                }
            return {
                "action_type": "start_execution",
                "stage": current_stage,
                "role": current_stage_def.get("role", ""),
                "reason": f"Retry stage {current_stage} (attempt {latest['attempt'] + 1})",
                "retry_attempt": latest["attempt"] + 1,
            }

        # Running → poll
        if latest["status"] in ("pending", "running"):
            # Check lease expiry
            lease = latest.get("lease_expires_at")
            if lease and lease < time.time():
                # Lease expired → mark as timed_out (caller should update storage)
                return {
                    "action_type": "poll_execution",
                    "stage": current_stage,
                    "reason": "Lease expired, caller should verify and handle",
                    "execution_id": latest["execution_id"],
                    "lease_expired": True,
                }
            return {
                "action_type": "poll_execution",
                "stage": current_stage,
                "reason": f"Execution {latest['execution_id']} is {latest['status']}",
                "execution_id": latest["execution_id"],
            }

        # Completed → check for artifact + receipt
        if latest["status"] == "completed":
            return await _check_artifact_receipt(
                coordination_session_id, run_id, current_stage,
                current_stage_def, next_stage_name, on_reject_stage,
            )

    # ── Check for artifact + receipt (even without execution record) ──
    return await _check_artifact_receipt(
        coordination_session_id, run_id, current_stage,
        current_stage_def, next_stage_name, on_reject_stage,
    )


async def _check_artifact_receipt(
    coordination_session_id: str,
    run_id: str,
    current_stage: str,
    stage_def: dict,
    next_stage: str,
    on_reject: str,
) -> dict:
    """Check artifacts and receipts to determine advance/reject/start."""
    artifacts = await list_artifacts(
        coordination_session_id=coordination_session_id,
        stage=current_stage,
    )
    receipts = await list_receipts(
        coordination_session_id=coordination_session_id,
        stage=current_stage,
    )

    stage_artifacts = [a for a in artifacts if a.get("run_id") == run_id]
    stage_receipts = [r for r in receipts if r.get("run_id") == run_id]

    # No artifact → need to start execution
    if not stage_artifacts:
        return {
            "action_type": "start_execution",
            "stage": current_stage,
            "role": stage_def.get("role", ""),
            "reason": f"No artifact for stage {current_stage}",
        }

    # Artifact exists, check for receipt
    if not stage_receipts:
        # Final stage with artifact → can close
        if not next_stage:
            return {
                "action_type": "submit_receipt",
                "stage": current_stage,
                "reason": f"Final stage {current_stage} has artifact but no receipt",
            }
        return {
            "action_type": "submit_receipt",
            "stage": current_stage,
            "reason": f"Stage {current_stage} has artifact but no receipt",
        }

    latest_receipt = stage_receipts[0]  # ordered by created_at DESC
    decision = latest_receipt.get("decision", "")

    if decision in ("approved", "passed"):
        if not next_stage:
            return {
                "action_type": "closed",
                "stage": current_stage,
                "reason": f"Final stage {current_stage} approved",
            }
        return {
            "action_type": "advance",
            "stage": current_stage,
            "next_stage": next_stage,
            "reason": f"Stage {current_stage} approved, advance to {next_stage}",
        }

    if decision in ("changes_requested", "failed", "rejected"):
        if on_reject:
            # Look up the on_reject stage role from the playbook
            sess_for_pb = await get_coordination_session(coordination_session_id)
            if sess_for_pb:
                pb = await get_playbook(sess_for_pb.get("playbook_id", "coding.v1"))
                if pb:
                    stages = {s["name"]: s for s in pb.get("stages", [])}
                    on_reject_def = stages.get(on_reject, {})
                    return {
                        "action_type": "start_execution",
                        "stage": on_reject,
                        "role": on_reject_def.get("role", ""),
                        "reason": f"Stage {current_stage} rejected, fallback to {on_reject}",
                    }
            return {
                "action_type": "start_execution",
                "stage": on_reject,
                "role": "",
                "reason": f"Stage {current_stage} rejected, fallback to {on_reject}",
            }
        return {
            "action_type": "start_execution",
            "stage": current_stage,
            "role": stage_def.get("role", ""),
            "reason": f"Stage {current_stage} rejected, retry same stage",
        }

    # Unknown decision
    return {
        "action_type": "wait",
        "stage": current_stage,
        "reason": f"Unknown receipt decision: {decision}",
    }
