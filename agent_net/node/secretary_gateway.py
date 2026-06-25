"""Secretary Human Gateway — DecisionGate creation and human interaction boundary.

Design ref: docs/design/design-objective-loop-v1.1.md Sections 8, 4.4

The Secretary Gateway translates Loop Engine create_decision_gate actions into
persisted decision_requests that the Secretary can present to human owners.
"""
from __future__ import annotations

import uuid

from agent_net.storage import create_decision_request


# Human-readable gate descriptions
_GATE_QUESTIONS: dict[str, str] = {
    "scope_change": "Worker detected scope change. Approve expanded scope?",
    "secret_access": "Worker needs access to credentials/private services. Grant access?",
    "destructive_command": "Worker attempted a destructive command. Allow execution?",
    "network_access": "Worker needs external network access. Allow?",
    "low_confidence": "Worker output could not be reliably parsed. How to proceed?",
    "review_conflict": "Multiple reviewers disagree. Please arbitrate.",
    "max_retry_exceeded": "Stage retry limit exceeded. Retry, skip, or abort?",
    "final_acceptance": "Objective complete. Accept delivery?",
}

_GATE_RISK: dict[str, str] = {
    "scope_change": "normal",
    "secret_access": "high",
    "destructive_command": "high",
    "network_access": "normal",
    "low_confidence": "normal",
    "review_conflict": "normal",
    "max_retry_exceeded": "normal",
    "final_acceptance": "low",
}

_GATE_OPTIONS: dict[str, list[str]] = {
    "scope_change": ["Approve expanded scope", "Keep original scope", "Abort"],
    "secret_access": ["Grant one-time access", "Deny", "Provide alternative"],
    "destructive_command": ["Allow (I understand the risk)", "Deny", "Abort"],
    "network_access": ["Allow", "Deny", "Abort"],
    "low_confidence": ["Retry", "Skip stage", "Abort"],
    "review_conflict": ["Prefer reviewer A", "Prefer reviewer B", "Request new review"],
    "max_retry_exceeded": ["Retry once more", "Skip stage", "Abort"],
    "final_acceptance": ["Accept delivery", "Request changes", "Abort"],
}


async def handle_decision_gate(
    coordination_session_id: str,
    run_id: str,
    owner_did: str,
    controller_did: str,
    action: dict,
) -> dict:
    """Create a persisted decision_request from a Loop Engine create_decision_gate action.

    Args:
        coordination_session_id: The coordination session.
        run_id: The playbook run.
        owner_did: The owner who will make the decision.
        controller_did: The Secretary/controller requesting the decision.
        action: The Loop Engine action dict with gate, stage, reason, execution_id.

    Returns:
        The created decision_request dict.
    """
    gate = action.get("gate", "low_confidence")
    stage = action.get("stage", "")
    reason = action.get("reason", "")
    execution_id = action.get("execution_id", "")

    question = _GATE_QUESTIONS.get(gate, f"Decision required for stage {stage}: {reason}")
    risk = _GATE_RISK.get(gate, "normal")
    options = _GATE_OPTIONS.get(gate, ["Approve", "Deny", "Abort"])
    recommended = options[0] if options else "Approve"

    decision_id = f"dec_{uuid.uuid4().hex[:16]}"

    result = await create_decision_request(
        decision_id=decision_id,
        owner_did=owner_did,
        coordination_session_id=coordination_session_id,
        run_id=run_id,
        stage=stage,
        requested_by_did=controller_did,
        question=question,
        options=options,
        recommended_option=recommended,
        risk_level=risk,
        evidence_refs=[execution_id] if execution_id else [],
    )

    return result
