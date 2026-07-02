"""Coordination API for AgentNexus SDK -- Coding Workflow V1."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import AgentNexusClient


class CoordinationClient:
    """High-level Coordination APIs for coding workflow management.

    Usage:
        session = await nexus.coordination.coding_intake(
            owner_did=nexus.agent_info.owner_did,
            actor_did=nexus.agent_info.did,
            objective="Implement login module",
            complexity="medium",
        )
    """

    def __init__(self, client: "AgentNexusClient"):
        self._client = client

    # ── Coding Intake ────────────────────────────────────────────

    async def coding_intake(
        self,
        *,
        owner_did: str,
        actor_did: str,
        objective: str,
        enclave_id: str | None = None,
        complexity: str = "medium",
        risk_level: str = "normal",
        cost_policy: str = "balanced",
        data_sensitivity: str = "internal",
        requires_human_approval: bool = False,
        session_id: str | None = None,
        preferred_playbook: str | None = None,
        source: dict | None = None,
    ) -> dict:
        """Create a coding coordination session via intake."""
        data = await self._client._request(
            "POST",
            "/coordination/coding/intake",
            json={
                "owner_did": owner_did,
                "actor_did": actor_did,
                "objective": objective,
                "enclave_id": enclave_id,
                "complexity": complexity,
                "risk_level": risk_level,
                "cost_policy": cost_policy,
                "data_sensitivity": data_sensitivity,
                "requires_human_approval": requires_human_approval,
                "session_id": session_id,
                "preferred_playbook": preferred_playbook,
                "source": source or {},
            },
        )
        return data["session"]

    # ── Session CRUD ─────────────────────────────────────────────

    async def get_session(self, coordination_session_id: str, *, actor_did: str) -> dict:
        """Get a coordination session by ID."""
        data = await self._client._request(
            "GET",
            f"/coordination/sessions/{coordination_session_id}",
            params={"actor_did": actor_did},
        )
        return data["session"]

    async def list_sessions(
        self,
        *,
        owner_did: str,
        actor_did: str,
        status: str | None = None,
        playbook_id: str | None = None,
    ) -> list[dict]:
        """List coordination sessions for an owner."""
        params: dict = {"owner_did": owner_did, "actor_did": actor_did}
        if status:
            params["status"] = status
        if playbook_id:
            params["playbook_id"] = playbook_id
        data = await self._client._request(
            "GET",
            "/coordination/sessions",
            params=params,
        )
        return data.get("sessions", [])

    async def fork_session(
        self,
        *,
        coordination_session_id: str,
        actor_did: str,
        link_type: str = "review_fork",
        reason: str = "",
    ) -> dict:
        """Fork a child coordination session."""
        data = await self._client._request(
            "POST",
            "/coordination/sessions/fork",
            json={
                "coordination_session_id": coordination_session_id,
                "actor_did": actor_did,
                "link_type": link_type,
                "reason": reason,
            },
        )
        return data["session"]

    # ── Artifacts ─────────────────────────────────────────────────

    async def submit_artifact(
        self,
        *,
        coordination_session_id: str,
        stage: str,
        artifact_type: str,
        producer_did: str,
        content_ref: str,
        run_id: str | None = None,
        artifact_id: str | None = None,
        schema_version: str = "1",
    ) -> dict:
        """Submit an artifact to a coordination session."""
        json_body: dict = {
            "coordination_session_id": coordination_session_id,
            "stage": stage,
            "artifact_type": artifact_type,
            "producer_did": producer_did,
            "content_ref": content_ref,
            "schema_version": schema_version,
        }
        if run_id:
            json_body["run_id"] = run_id
        if artifact_id:
            json_body["artifact_id"] = artifact_id
        data = await self._client._request(
            "POST",
            "/coordination/artifacts",
            json=json_body,
        )
        return data["artifact"]

    async def list_artifacts(
        self,
        coordination_session_id: str,
        *,
        actor_did: str,
        stage: str | None = None,
        run_id: str | None = None,
    ) -> list[dict]:
        """List artifacts for a coordination session."""
        params: dict = {"actor_did": actor_did}
        if stage:
            params["stage"] = stage
        if run_id:
            params["run_id"] = run_id
        data = await self._client._request(
            "GET",
            f"/coordination/sessions/{coordination_session_id}/artifacts",
            params=params,
        )
        return data.get("artifacts", [])

    # ── Receipts ──────────────────────────────────────────────────

    async def submit_receipt(
        self,
        *,
        coordination_session_id: str,
        stage: str,
        receipt_type: str,
        issuer_did: str,
        decision: str,
        run_id: str | None = None,
        subject_artifact_id: str = "",
        evidence_refs: list[str] | None = None,
        signature: str = "",
        receipt_id: str | None = None,
    ) -> dict:
        """Submit a receipt (review decision) for a stage."""
        json_body: dict = {
            "coordination_session_id": coordination_session_id,
            "stage": stage,
            "receipt_type": receipt_type,
            "issuer_did": issuer_did,
            "decision": decision,
            "subject_artifact_id": subject_artifact_id,
            "evidence_refs": evidence_refs or [],
            "signature": signature,
        }
        if run_id:
            json_body["run_id"] = run_id
        if receipt_id:
            json_body["receipt_id"] = receipt_id
        data = await self._client._request(
            "POST",
            "/coordination/receipts",
            json=json_body,
        )
        return data["receipt"]

    async def list_receipts(
        self,
        coordination_session_id: str,
        *,
        actor_did: str,
        stage: str | None = None,
        run_id: str | None = None,
    ) -> list[dict]:
        """List receipts for a coordination session."""
        params: dict = {"actor_did": actor_did}
        if stage:
            params["stage"] = stage
        if run_id:
            params["run_id"] = run_id
        data = await self._client._request(
            "GET",
            f"/coordination/sessions/{coordination_session_id}/receipts",
            params=params,
        )
        return data.get("receipts", [])

    # ── Workflow Advance ──────────────────────────────────────────

    async def advance(
        self,
        coordination_session_id: str,
        run_id: str,
        *,
        actor_did: str,
    ) -> dict:
        """Advance one PlaybookRun to the next stage."""
        return await self._client._request(
            "POST",
            f"/coordination/coding/{coordination_session_id}/runs/{run_id}/advance",
            json={"actor_did": actor_did},
        )

    # ── Timeline & Closures ───────────────────────────────────────

    async def timeline(
        self,
        coordination_session_id: str,
        *,
        actor_did: str,
    ) -> dict:
        """Get the merged timeline for a coordination session."""
        return await self._client._request(
            "GET",
            f"/coordination/sessions/{coordination_session_id}/timeline",
            params={"actor_did": actor_did},
        )

    async def closures(
        self,
        coordination_session_id: str,
        *,
        actor_did: str,
        status: str | None = None,
    ) -> dict:
        """List closure/SLA records for a coordination session."""
        params: dict = {"actor_did": actor_did}
        if status:
            params["status"] = status
        return await self._client._request(
            "GET",
            f"/coordination/sessions/{coordination_session_id}/closures",
            params=params,
        )

    # ── Owner Decision Gate ───────────────────────────────────────

    async def create_decision(
        self,
        *,
        coordination_session_id: str,
        requested_by_did: str,
        question: str,
        owner_did: str | None = None,
        run_id: str = "",
        stage: str = "",
        options: list[dict] | None = None,
        recommended_option: str = "",
        risk_level: str = "normal",
        evidence_refs: list[str] | None = None,
    ) -> dict:
        """Create a pending Owner/Decision Principal request."""
        data = await self._client._request(
            "POST",
            "/coordination/decisions",
            json={
                "coordination_session_id": coordination_session_id,
                "owner_did": owner_did,
                "requested_by_did": requested_by_did,
                "run_id": run_id,
                "stage": stage,
                "question": question,
                "options": options or [],
                "recommended_option": recommended_option,
                "risk_level": risk_level,
                "evidence_refs": evidence_refs or [],
            },
        )
        return data["decision"]

    async def list_decisions(
        self,
        *,
        owner_did: str,
        actor_did: str,
        status: str | None = "pending",
    ) -> list[dict]:
        """List decisions addressed to an Owner/Decision Principal."""
        params: dict = {"owner_did": owner_did, "actor_did": actor_did}
        if status is not None:
            params["status"] = status
        data = await self._client._request(
            "GET",
            "/owner/decisions",
            params=params,
        )
        return data.get("decisions", [])

    async def respond_decision(
        self,
        decision_id: str,
        *,
        actor_did: str,
        decision: str,
        comment: str = "",
        channel_ref: str = "",
        evidence_refs: list[str] | None = None,
    ) -> dict:
        """Respond to a pending Owner decision request and create a receipt."""
        return await self._client._request(
            "POST",
            f"/owner/decisions/{decision_id}/respond",
            json={
                "actor_did": actor_did,
                "decision": decision,
                "comment": comment,
                "channel_ref": channel_ref,
                "evidence_refs": evidence_refs or [],
            },
        )

    # ── Events ────────────────────────────────────────────────────

    async def emit_event(
        self,
        coordination_session_id: str,
        event_type: str,
        *,
        actor_did: str,
        stage: str = "",
        run_id: str = "",
        session_id: str = "",
        delegation_id: str = "",
        artifact_id: str = "",
        receipt_id: str = "",
        payload: dict | None = None,
    ) -> dict:
        """Append a runtime event to a coordination session."""
        data = await self._client._request(
            "POST",
            "/coordination/events",
            json={
                "coordination_session_id": coordination_session_id,
                "event_type": event_type,
                "stage": stage,
                "actor_did": actor_did,
                "run_id": run_id,
                "session_id": session_id,
                "delegation_id": delegation_id,
                "artifact_id": artifact_id,
                "receipt_id": receipt_id,
                "payload": payload or {},
            },
        )
        return data["event"]

    async def list_events(
        self,
        coordination_session_id: str,
        *,
        actor_did: str,
        stage: str | None = None,
        event_type: str | None = None,
    ) -> list[dict]:
        """List runtime events for a coordination session."""
        params: dict = {"actor_did": actor_did}
        if stage:
            params["stage"] = stage
        if event_type:
            params["event_type"] = event_type
        data = await self._client._request(
            "GET",
            f"/coordination/sessions/{coordination_session_id}/events",
            params=params,
        )
        return data.get("events", [])

    async def stream_events(
        self,
        coordination_session_id: str,
        *,
        actor_did: str,
        last_event_id: str = "",
        limit: int = 0,
        timeout_seconds: float = 0,
    ):
        """Stream runtime events via SSE. Returns an async generator of event dicts."""
        import json as _json

        params: dict = {"actor_did": actor_did}
        if last_event_id:
            params["last_event_id"] = last_event_id
        if limit > 0:
            params["limit"] = str(limit)
        if timeout_seconds > 0:
            params["timeout_seconds"] = str(timeout_seconds)

        if not self._client._session:
            raise RuntimeError("Client not connected")

        headers = {}
        if self._client.token:
            headers["Authorization"] = f"Bearer {self._client.token}"

        url = f"{self._client.daemon_url}/coordination/sessions/{coordination_session_id}/events/stream"
        async with self._client._session.get(url, headers=headers, params=params) as resp:
            if resp.status != 200:
                raise RuntimeError(f"SSE stream failed: {resp.status}")
            async for line in resp.content:
                line = line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    try:
                        yield _json.loads(data_str)
                    except _json.JSONDecodeError:
                        continue

    # ── Delegation ────────────────────────────────────────────────

    async def delegate_stage(
        self,
        *,
        coordination_session_id: str,
        stage: str,
        delegator_did: str,
        delegatee_did: str,
        run_id: str | None = None,
        role: str = "",
        runtime_kind: str = "native_worker",
        protocol: str = "agentnexus-native",
        session_id: str = "",
    ) -> dict:
        """Delegate a stage to a worker."""
        json_body = {
            "delegator_did": delegator_did,
            "delegatee_did": delegatee_did,
            "role": role or stage,
            "runtime_kind": runtime_kind,
            "protocol": protocol,
            "session_id": session_id,
        }
        if run_id:
            json_body["run_id"] = run_id
        return await self._client._request(
            "POST",
            f"/coordination/sessions/{coordination_session_id}/stages/{stage}/delegate",
            json=json_body,
        )

    async def accept_delegation(
        self,
        delegation_id: str,
        *,
        actor_did: str,
    ) -> dict:
        """Accept a pending delegation."""
        return await self._client._request(
            "POST",
            f"/coordination/delegations/{delegation_id}/accept",
            json={"actor_did": actor_did},
        )

    async def reject_delegation(
        self,
        delegation_id: str,
        *,
        actor_did: str,
        reason: str = "",
    ) -> dict:
        """Reject a pending delegation."""
        return await self._client._request(
            "POST",
            f"/coordination/delegations/{delegation_id}/reject",
            json={"actor_did": actor_did, "reason": reason},
        )

    # ── Objective Loop V1.1 ────────────────────────────────────────

    async def next_action(
        self,
        coordination_session_id: str,
        *,
        actor_did: str,
    ) -> dict:
        """Get the next action from the Loop Engine for a session.

        Returns an action dict with action_type, stage, reason, role, etc.
        """
        return await self._client._request(
            "GET",
            f"/coordination/sessions/{coordination_session_id}/next-action",
            params={"actor_did": actor_did},
        )

    async def list_executions(
        self,
        coordination_session_id: str,
        *,
        actor_did: str,
        run_id: str = "",
        stage: str = "",
    ) -> dict:
        """List objective_executions for a coordination session."""
        params = {"actor_did": actor_did}
        if run_id:
            params["run_id"] = run_id
        if stage:
            params["stage"] = stage
        return await self._client._request(
            "GET",
            f"/coordination/sessions/{coordination_session_id}/executions",
            params=params,
        )

    async def create_execution(
        self,
        *,
        coordination_session_id: str,
        run_id: str,
        stage: str,
        worker_did: str,
        backend_kind: str,
        actor_did: str,
        lease_ttl_sec: int = 1800,
        metadata: dict | None = None,
    ) -> dict:
        """Create a new objective_execution (execution lease)."""
        return await self._client._request(
            "POST",
            "/coordination/executions",
            json={
                "coordination_session_id": coordination_session_id,
                "run_id": run_id,
                "stage": stage,
                "worker_did": worker_did,
                "backend_kind": backend_kind,
                "actor_did": actor_did,
                "lease_ttl_sec": lease_ttl_sec,
                "metadata": metadata,
            },
        )

    async def update_execution(
        self,
        execution_id: str,
        *,
        actor_did: str,
        status: str | None = None,
        lease_ttl_sec: int | None = None,
        external_session_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Update an execution's status, lease, or metadata."""
        body = {"actor_did": actor_did}
        if status is not None:
            body["status"] = status
        if lease_ttl_sec is not None:
            body["lease_ttl_sec"] = lease_ttl_sec
        if external_session_id is not None:
            body["external_session_id"] = external_session_id
        if metadata is not None:
            body["metadata"] = metadata
        return await self._client._request(
            "PATCH",
            f"/coordination/executions/{execution_id}",
            json=body,
        )

    async def submit_execution_result(
        self,
        execution_id: str,
        *,
        actor_did: str,
        status: str,
        artifact_type: str,
        artifact_body: str,
        summary: str,
        evidence_refs: list[str] | None = None,
        human_decision_request: dict | None = None,
    ) -> dict:
        """Submit the result of an execution. Idempotent."""
        return await self._client._request(
            "POST",
            f"/coordination/executions/{execution_id}/result",
            json={
                "actor_did": actor_did,
                "result": {
                    "status": status,
                    "artifact_type": artifact_type,
                    "artifact_body": artifact_body,
                    "summary": summary,
                    "evidence_refs": evidence_refs or [],
                    "human_decision_request": human_decision_request,
                },
            },
        )
