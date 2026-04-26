"""Team / Worker Registry API for AgentNexus SDK."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import AgentNexusClient


@dataclass
class WorkerInfo:
    did: str
    owner_did: str = ""
    worker_type: str = "resident"
    profile_type: str = "agent"
    capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    last_seen: float = 0.0
    presence: str = "offline"
    presence_source: str = "local"
    presence_ttl: float | None = None
    active_run_id: str | None = None
    active_stage: str | None = None
    load: int = 0
    online: bool | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "WorkerInfo":
        return cls(
            did=data.get("did", ""),
            owner_did=data.get("owner_did", ""),
            worker_type=data.get("worker_type", "resident"),
            profile_type=data.get("profile_type", "agent"),
            capabilities=data.get("capabilities", []) or [],
            tags=data.get("tags", []) or [],
            last_seen=data.get("last_seen", 0.0) or 0.0,
            presence=data.get("presence", "available" if data.get("online") else "offline"),
            presence_source=data.get("presence_source", "local"),
            presence_ttl=data.get("presence_ttl"),
            active_run_id=data.get("active_run_id"),
            active_stage=data.get("active_stage"),
            load=data.get("load", 0) or 0,
            online=data.get("online"),
        )


class TeamClient:
    """Worker registry, presence, and worker metadata APIs."""

    def __init__(self, client: "AgentNexusClient"):
        self._client = client

    async def list_workers(
        self,
        owner_did: str,
        *,
        actor_did: str | None = None,
        role: str | None = None,
        presence: str | None = None,
        v2: bool = True,
    ) -> list[WorkerInfo]:
        path = f"/owner/workers/v2/{owner_did}" if v2 else f"/owner/workers/{owner_did}"
        params = {"actor_did": actor_did or owner_did}
        if role:
            params["role"] = role
        if presence:
            params["presence"] = presence
        data = await self._client._request("GET", path, params=params)
        return [WorkerInfo.from_dict(item) for item in data.get("workers", [])]

    async def get_presence(self, did: str, *, actor_did: str | None = None) -> dict:
        return await self._client._request(
            "GET",
            f"/workers/{did}/presence",
            params={"actor_did": actor_did or self._client.agent_info.did},
        )

    async def set_blocked(
        self,
        did: str,
        blocked: bool,
        *,
        actor_did: str,
        reason: str = "",
    ) -> dict:
        return await self._client._request(
            "PATCH",
            f"/workers/{did}/blocked",
            params={"blocked": blocked, "actor_did": actor_did, "reason": reason},
        )

    async def set_worker_type(self, did: str, worker_type: str, *, actor_did: str) -> dict:
        return await self._client._request(
            "PATCH",
            f"/agents/{did}/worker-type",
            params={"worker_type": worker_type, "actor_did": actor_did},
        )
