"""Runner Poll Loop — session discovery + next-action polling + execution.

Design ref: docs/design/design-objective-loop-v1.1.md Sections 4.2, 6, 11

The runner loop is the heartbeat of the Objective Loop:
1. Poll daemon for running sessions
2. For each session, query the Loop Engine for next_action
3. Handle ALL action types: start_execution, advance, poll, decision_gate, closed
4. Build structured prompt from template with objective/artifacts/constraints
"""
from __future__ import annotations

import re
from typing import Any, Callable, Awaitable

from agent_net.node.execution_backends.base import ExecutionResult
from agent_net.node.local_runner import (
    find_worker_for_role,
    find_worker_for_capability,
    find_fallback_worker,
    execute_stage,
)


def _build_constraints(config: dict[str, Any], worker: dict[str, Any]) -> dict[str, Any]:
    """Build execution constraints from config defaults merged with worker overrides.

    Worker-level fields take precedence over defaults. Propagates:
    timeout_sec, workdir, max_output_bytes, network_access, output adapter,
    allowed_commands, env.
    Design ref: docs/design/design-objective-loop-v1.1.md Sections 6.1-6.2
    """
    defaults = config.get("defaults", {})
    constraints = {
        "timeout_sec": worker.get("timeout_sec", defaults.get("timeout_sec", 1800)),
        "workdir": worker.get("workdir", defaults.get("workdir", "")),
        "max_output_bytes": worker.get("max_output_bytes",
                                        defaults.get("max_output_bytes", 1_048_576)),
        "network_access": worker.get("network_access",
                                      defaults.get("network_access", "deny_by_default")),
        "output_adapter": worker.get("output_adapter",
                                      defaults.get("output_adapter", "agentnexus_json_v1")),
        "artifact_type": worker.get("artifact_type",
                                    defaults.get("artifact_type", "TextArtifact")),
        "allowed_commands": worker.get("allowed_commands",
                                       defaults.get("allowed_commands", [])),
    }
    output_text_paths = worker.get("output_text_paths", defaults.get("output_text_paths"))
    if output_text_paths:
        constraints["output_text_paths"] = output_text_paths
    # env: only from worker; defaults.env would be too broad
    worker_env = worker.get("env")
    if worker_env and isinstance(worker_env, dict):
        constraints["env"] = worker_env
    return constraints


def build_worker_prompt(
    *,
    worker: dict[str, Any],
    coordination_session_id: str,
    run_id: str,
    stage: str,
    role: str,
    objective: str,
    input_refs: list[dict] | None = None,
    constraints: dict[str, Any] | None = None,
    acceptance_criteria: list[str] | None = None,
) -> str:
    """Build a structured prompt for a CLI worker from template args.

    The worker's args may contain {prompt} which is replaced with the structured message.
    Other template variables like {stage}, {role}, {objective} are also supported.
    """
    refs_text = ""
    if input_refs:
        refs_lines = []
        for r in input_refs:
            refs_lines.append(f"- {r.get('kind', 'ref')}: {r.get('ref', '')}")
        refs_text = "\n".join(refs_lines)

    constraints_text = ""
    if constraints:
        for k, v in constraints.items():
            constraints_text += f"- {k}: {v}\n"

    criteria_text = ""
    if acceptance_criteria:
        for c in acceptance_criteria:
            criteria_text += f"- {c}\n"

    prompt = f"""You are an AgentNexus worker.

CoordinationSession: {coordination_session_id}
Run: {run_id}
Stage: {stage}
Role: {role}
Objective: {objective}

Input refs:
{refs_text or '(none)'}

Constraints:
{constraints_text or '(none)'}

Acceptance criteria:
{criteria_text or '(none)'}

Return a JSON block with:
- contract: "agentnexus_json_v1"
- summary
- status: completed | changes_requested | failed | blocked
- artifact_type
- artifact_body
- evidence_refs
- human_decision_request, optional
"""
    return prompt


def _substitute_template_args(args: list[str], prompt: str, **variables: str) -> list[str]:
    """Replace {prompt} and other template variables in command args."""
    result = []
    replacements = {"prompt": prompt, **variables}
    for arg in args:
        for key, value in replacements.items():
            arg = arg.replace("{" + key + "}", str(value))
        result.append(arg)
    return result


async def runner_tick(
    *,
    config: dict[str, Any],
    list_sessions: Callable[..., Awaitable[list[dict]]],
    get_next_action: Callable[..., Awaitable[dict]],
    get_session_detail: Callable[..., Awaitable[dict]] | None = None,
    create_execution: Callable[..., Awaitable[dict]],
    submit_result: Callable[..., Awaitable[dict]],
    call_advance: Callable[..., Awaitable[dict]] | None = None,
    create_decision: Callable[..., Awaitable[dict]] | None = None,
    update_execution: Callable[..., Awaitable[dict]] | None = None,
    actor_did: str = "",
    owner_did: str = "",
) -> list[dict]:
    """Execute one tick of the runner poll loop.

    Handles ALL action types:
    - start_execution: find worker, build prompt, execute, submit result
    - advance: call advance API to move to next stage
    - poll_execution: wait for running execution
    - create_decision_gate: create decision request
    - closed/wait/blocked: log and skip

    Returns a list of action summaries for what was done this tick.
    """
    actions: list[dict] = []

    try:
        sessions = await list_sessions(owner_did=owner_did, actor_did=actor_did, status="running")
    except Exception as e:
        return [{"action": "error", "reason": f"list_sessions failed: {e}"}]

    if not sessions:
        return actions

    for sess in sessions:
        sid = sess.get("coordination_session_id", "")
        rid = sess.get("playbook_run_id", "")
        objective = sess.get("objective", "")

        try:
            action = await get_next_action(sid, actor_did)
        except Exception as e:
            actions.append({"action": "error", "session_id": sid, "reason": str(e)})
            continue

        atype = action.get("action_type", "")

        # ── start_execution ──────────────────────────────────────
        if atype == "start_execution":
            stage = action.get("stage", "")
            role = action.get("role", "")
            retry_attempt = action.get("retry_attempt", 1)

            # Find matching worker (try role first, then fallback to capability)
            worker = find_worker_for_role(config, role)
            if worker is None:
                worker = find_worker_for_capability(config, role)

            # For retries beyond first retry, try fallback worker
            # Design: retry same worker once (retry_attempt=2), then fallback (>=3)
            if retry_attempt >= 3 and worker is not None:
                worker_key = worker.get("worker_did") or worker.get("agent_name", "")
                fallback = find_fallback_worker(config, role, exclude_workers={worker_key})
                if fallback is not None:
                    worker = fallback

            if worker is None:
                actions.append({
                    "action": "skip", "session_id": sid, "stage": stage,
                    "reason": f"No worker for role '{role}'",
                })
                continue

            # Get session detail for context (objective, artifacts, constraints)
            session_detail = {}
            if get_session_detail:
                try:
                    session_detail = await get_session_detail(sid, actor_did)
                except Exception:
                    pass

            # Collect input refs from previous stage artifacts
            input_refs = []
            if session_detail:
                for art in session_detail.get("artifacts", []):
                    input_refs.append({
                        "kind": art.get("artifact_type", ""),
                        "ref": art.get("content_ref", ""),
                    })

            # Build structured prompt
            prompt = build_worker_prompt(
                worker=worker,
                coordination_session_id=sid,
                run_id=rid,
                stage=stage,
                role=role,
                objective=objective,
                input_refs=input_refs,
                constraints=action.get("constraints", config.get("defaults", {})),
                acceptance_criteria=session_detail.get("acceptance_criteria"),
            )

            # Substitute template args with actual prompt
            command = [worker["command"]] + _substitute_template_args(
                worker.get("args", []), prompt,
                stage=stage, role=role, objective=objective,
                coordination_session_id=sid, run_id=rid,
            )

            # Create execution record
            try:
                exec_resp = await create_execution(
                    coordination_session_id=sid,
                    run_id=rid,
                    stage=stage,
                    worker_did=worker.get("worker_did") or worker.get("agent_name", "unknown"),
                    backend_kind=worker.get("adapter", "local_cli"),
                    actor_did=actor_did,
                    lease_ttl_sec=config.get("defaults", {}).get("timeout_sec", 1800),
                    metadata={
                        "retry_attempt": retry_attempt,
                        "worker_name": worker.get("agent_name", ""),
                    },
                )
            except Exception as e:
                actions.append({
                    "action": "error", "session_id": sid, "stage": stage,
                    "reason": f"create_execution failed: {e}",
                })
                continue

            eid = exec_resp.get("execution", {}).get("execution_id", "")

            # Execute via backend (handles JSON retry internally)
            constraints = _build_constraints(config, worker)
            try:
                result = await execute_stage(
                    coordination_session_id=sid,
                    run_id=rid,
                    stage=stage,
                    worker_did=worker.get("worker_did") or worker.get("agent_name", "unknown"),
                    backend_kind=worker.get("adapter", "local_cli"),
                    command=command,
                    constraints=constraints,
                    allowed_commands=set(constraints.get("allowed_commands") or []),
                    timeout_sec=constraints.get("timeout_sec", 1800),
                    max_output_bytes=constraints.get("max_output_bytes", 1_048_576),
                )
            except Exception as e:
                actions.append({
                    "action": "error", "session_id": sid, "stage": stage,
                    "execution_id": eid, "reason": f"execute_stage failed: {e}",
                })
                continue

            # If backend signals retry (changes_requested), re-execute once
            if result.status == "changes_requested":
                retry_prompt = "Your previous response could not be parsed as valid JSON. Please reformat your result as the specified JSON structure only."
                retry_command = [worker["command"]] + _substitute_template_args(
                    worker.get("args", []), retry_prompt,
                    stage=stage, role=role, objective=objective,
                    coordination_session_id=sid, run_id=rid,
                )
                try:
                    result = await execute_stage(
                        coordination_session_id=sid,
                        run_id=rid,
                        stage=stage,
                        worker_did=worker.get("worker_did") or worker.get("agent_name", "unknown"),
                        backend_kind=worker.get("adapter", "local_cli"),
                        command=retry_command,
                        constraints=constraints,
                        allowed_commands=set(constraints.get("allowed_commands") or []),
                        timeout_sec=constraints.get("timeout_sec", 1800),
                        max_output_bytes=constraints.get("max_output_bytes", 1_048_576),
                    )
                except Exception:
                    pass  # result stays as changes_requested → will be submitted as blocked

            # Submit result
            try:
                await submit_result(eid, {
                    "actor_did": actor_did,
                    "result": {
                        "status": result.status,
                        "artifact_type": result.artifact_type,
                        "artifact_body": result.artifact_body,
                        "summary": result.summary,
                        "evidence_refs": result.evidence_refs,
                        "human_decision_request": result.human_decision_request,
                    },
                })
            except Exception as e:
                actions.append({
                    "action": "error", "session_id": sid, "stage": stage,
                    "execution_id": eid, "reason": f"submit_result failed: {e}",
                })
                continue

            actions.append({
                "action": "start_execution", "session_id": sid, "stage": stage,
                "execution_id": eid, "result_status": result.status,
            })

        # ── advance ──────────────────────────────────────────────
        elif atype == "advance":
            if call_advance:
                try:
                    await call_advance(sid, rid, actor_did)
                    actions.append({
                        "action": "advance", "session_id": sid,
                        "from_stage": action.get("stage", ""),
                        "to_stage": action.get("next_stage", ""),
                    })
                except Exception as e:
                    actions.append({
                        "action": "error", "session_id": sid,
                        "reason": f"advance failed: {e}",
                    })
            else:
                actions.append({
                    "action": "advance", "session_id": sid,
                    "stage": action.get("stage", ""),
                    "reason": "advance API not available (no call_advance callback)",
                })

        # ── poll_execution ───────────────────────────────────────
        elif atype == "poll_execution":
            if action.get("lease_expired") and update_execution:
                eid = action.get("execution_id", "")
                try:
                    await update_execution(eid, {
                        "actor_did": actor_did,
                        "status": "timed_out",
                    })
                    actions.append({
                        "action": "lease_expired", "session_id": sid,
                        "stage": action.get("stage", ""),
                        "execution_id": eid,
                        "reason": "Marked timed_out due to lease expiry",
                    })
                except Exception as e:
                    actions.append({
                        "action": "error", "session_id": sid,
                        "reason": f"Failed to mark lease expired: {e}",
                    })
            else:
                actions.append({
                    "action": "poll_execution", "session_id": sid,
                    "stage": action.get("stage", ""),
                    "execution_id": action.get("execution_id", ""),
                    "reason": action.get("reason", ""),
                })

        # ── create_decision_gate ─────────────────────────────────
        elif atype == "create_decision_gate":
            if create_decision:
                try:
                    await create_decision(
                        coordination_session_id=sid,
                        run_id=rid,
                        owner_did=owner_did,
                        controller_did=actor_did,
                        action=action,
                    )
                    actions.append({
                        "action": "create_decision_gate", "session_id": sid,
                        "stage": action.get("stage", ""),
                        "gate": action.get("gate", ""),
                    })
                except Exception as e:
                    actions.append({
                        "action": "error", "session_id": sid,
                        "reason": f"create_decision failed: {e}",
                    })
            else:
                actions.append({
                    "action": "create_decision_gate", "session_id": sid,
                    "stage": action.get("stage", ""),
                    "gate": action.get("gate", ""),
                    "reason": "decision API not available",
                })

        # ── closed / wait / blocked ──────────────────────────────
        elif atype in ("closed", "wait", "blocked", "submit_receipt"):
            actions.append({
                "action": atype, "session_id": sid,
                "stage": action.get("stage", ""),
                "reason": action.get("reason", ""),
            })

        else:
            actions.append({
                "action": atype, "session_id": sid,
                "stage": action.get("stage", ""),
                "reason": action.get("reason", ""),
            })

    return actions


async def process_action(
    *,
    config: dict[str, Any],
    session_id: str,
    run_id: str,
    action: dict,
    worker_did: str = "did:agentnexus:local-runner",
    objective: str = "",
) -> ExecutionResult | None:
    """Process a single next_action (start_execution) using a matching worker."""
    stage = action.get("stage", "")
    role = action.get("role", "")

    worker = find_worker_for_role(config, role)
    if worker is None:
        worker = find_worker_for_capability(config, role)
    if worker is None:
        return None

    # Build prompt
    prompt = build_worker_prompt(
        worker=worker,
        coordination_session_id=session_id,
        run_id=run_id,
        stage=stage,
        role=role,
        objective=objective,
    )
    command = [worker["command"]] + _substitute_template_args(
        worker.get("args", []), prompt,
        stage=stage, role=role, objective=objective,
        coordination_session_id=session_id, run_id=run_id,
    )

    constraints = _build_constraints(config, worker)

    return await execute_stage(
        coordination_session_id=session_id,
        run_id=run_id,
        stage=stage,
        worker_did=worker_did,
        backend_kind=worker.get("adapter", "local_cli"),
        command=command,
        constraints=constraints,
        allowed_commands=set(constraints.get("allowed_commands") or []),
        timeout_sec=constraints.get("timeout_sec", 1800),
        max_output_bytes=constraints.get("max_output_bytes", 1_048_576),
    )
