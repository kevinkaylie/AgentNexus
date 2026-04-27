"""Run and intake status API for AgentNexus SDK."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .secretary import IntakeInfo

if TYPE_CHECKING:
    from .client import AgentNexusClient


@dataclass
class RunStatus:
    run_id: str
    enclave_id: str
    playbook_name: str
    current_stage: str
    status: str
    stages: dict = field(default_factory=dict)
    started_at: float = 0.0
    completed_at: float | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "RunStatus":
        return cls(
            run_id=data.get("run_id", ""),
            enclave_id=data.get("enclave_id", ""),
            playbook_name=data.get("playbook_name", ""),
            current_stage=data.get("current_stage", ""),
            status=data.get("run_status", data.get("status", "")),
            stages=data.get("stages", {}) or {},
            started_at=data.get("started_at", 0.0) or 0.0,
            completed_at=data.get("completed_at"),
        )


class RunClient:
    """Playbook run and intake status facade."""

    def __init__(self, client: "AgentNexusClient"):
        self._client = client

    async def get_intake(self, session_id: str, *, actor_did: str) -> IntakeInfo:
        return await self._client.secretary.get_intake(session_id, actor_did=actor_did)

    async def get_status(
        self,
        enclave_id: str,
        run_id: str,
        *,
        actor_did: str | None = None,
    ) -> RunStatus:
        data = await self._client._request(
            "GET",
            f"/enclaves/{enclave_id}/runs/{run_id}",
            params={"actor_did": actor_did or self._client.agent_info.did},
        )
        return RunStatus.from_dict(data)

    async def abort(self, session_id: str, *, actor_did: str, reason: str = "") -> dict:
        return await self._client.secretary.abort(session_id, actor_did=actor_did, reason=reason)
