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
        workflow_id: str | None = None,
    ) -> list[dict]:
        """List coordination sessions for an owner."""
        params: dict = {"owner_did": owner_did, "actor_did": actor_did}
        if status:
            params["status"] = status
        if workflow_id:
            params["workflow_id"] = workflow_id
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
    ) -> list[dict]:
        """List artifacts for a coordination session."""
        params: dict = {"actor_did": actor_did}
        if stage:
            params["stage"] = stage
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
    ) -> list[dict]:
        """List receipts for a coordination session."""
        params: dict = {"actor_did": actor_did}
        if stage:
            params["stage"] = stage
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
        *,
        actor_did: str,
    ) -> dict:
        """Advance coding workflow to the next stage."""
        return await self._client._request(
            "POST",
            f"/coordination/coding/{coordination_session_id}/advance",
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

    # ── Events ────────────────────────────────────────────────────

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
        role: str = "",
        runtime_kind: str = "native_worker",
        protocol: str = "agentnexus-native",
        session_id: str = "",
    ) -> dict:
        """Delegate a stage to a worker."""
        return await self._client._request(
            "POST",
            f"/coordination/sessions/{coordination_session_id}/stages/{stage}/delegate",
            json={
                "delegator_did": delegator_did,
                "delegatee_did": delegatee_did,
                "role": role or stage,
                "runtime_kind": runtime_kind,
                "protocol": protocol,
                "session_id": session_id,
            },
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
