"""Secretary orchestration API for AgentNexus SDK."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import AgentNexusClient


@dataclass
class SecretaryInfo:
    did: str
    name: str
    capabilities: list[str] = field(default_factory=list)


@dataclass
class IntakeInfo:
    session_id: str
    owner_did: str
    actor_did: str
    status: str
    objective: str
    required_roles: list[str] = field(default_factory=list)
    preferred_playbook: str | None = None
    selected_workers: dict[str, str] = field(default_factory=dict)
    run_id: str | None = None
    source_channel: str | None = None
    source_message_ref: str | None = None
    constraints: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "IntakeInfo":
        data = data.get("intake", data)
        return cls(
            session_id=data.get("session_id", ""),
            owner_did=data.get("owner_did", ""),
            actor_did=data.get("actor_did", ""),
            status=data.get("status", ""),
            objective=data.get("objective", ""),
            required_roles=data.get("required_roles", []) or [],
            preferred_playbook=data.get("preferred_playbook"),
            selected_workers=data.get("selected_workers", {}) or {},
            run_id=data.get("run_id"),
            source_channel=data.get("source_channel"),
            source_message_ref=data.get("source_message_ref"),
            constraints=data.get("constraints", {}) or {},
        )


@dataclass
class DispatchResult:
    status: str
    session_id: str
    run_id: str | None = None
    enclave_id: str | None = None
    playbook_name: str | None = None
    current_stage: str | None = None
    selected_workers: dict[str, str] = field(default_factory=dict)
    missing_roles: list[str] = field(default_factory=list)
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict, session_id: str = "") -> "DispatchResult":
        return cls(
            status=data.get("status", ""),
            session_id=data.get("session_id", session_id),
            run_id=data.get("run_id"),
            enclave_id=data.get("enclave_id"),
            playbook_name=data.get("playbook_name"),
            current_stage=data.get("current_stage"),
            selected_workers=data.get("selected_workers", {}) or {},
            missing_roles=data.get("missing_roles", []) or [],
            reason=data.get("reason"),
        )


class SecretaryClient:
    """High-level Secretary intake and dispatch APIs."""

    def __init__(self, client: "AgentNexusClient"):
        self._client = client

    async def register(self, owner_did: str, name: str = "Secretary") -> SecretaryInfo:
        data = await self._client._request(
            "POST",
            "/agents/register",
            json={
                "name": name,
                "type": "secretary",
                "capabilities": ["orchestrate", "intake", "dispatch"],
                "worker_type": "resident",
            },
        )
        did = data["did"]
        try:
            await self._client.owner.bind(owner_did, did)
        except Exception:
            try:
                await self._client._request(
                    "DELETE",
                    f"/agents/{did}",
                    params={"actor_did": did},
                )
            except Exception:
                pass
            raise
        profile = data.get("profile", {})
        return SecretaryInfo(
            did=did,
            name=profile.get("name", name),
            capabilities=profile.get("capabilities", ["orchestrate", "intake", "dispatch"]),
        )

    async def create_intake(
        self,
        *,
        session_id: str,
        owner_did: str,
        actor_did: str,
        objective: str,
        required_roles: list[str],
        preferred_playbook: str | None = None,
        source: dict | None = None,
        constraints: dict | None = None,
    ) -> IntakeInfo:
        data = await self._client._request(
            "POST",
            "/secretary/intake",
            json={
                "session_id": session_id,
                "owner_did": owner_did,
                "actor_did": actor_did,
                "objective": objective,
                "required_roles": required_roles,
                "preferred_playbook": preferred_playbook,
                "source": source or {},
                "constraints": constraints or {},
            },
        )
        return IntakeInfo.from_dict(data)

    async def get_intake(self, session_id: str, *, actor_did: str) -> IntakeInfo:
        data = await self._client._request(
            "GET",
            f"/secretary/intake/{session_id}",
            params={"actor_did": actor_did},
        )
        return IntakeInfo.from_dict(data)

    async def list_intakes(
        self,
        owner_did: str,
        *,
        actor_did: str,
        status: str | None = None,
    ) -> list[IntakeInfo]:
        params = {"actor_did": actor_did}
        if status:
            params["status"] = status
        data = await self._client._request(
            "GET",
            f"/secretary/intakes/{owner_did}",
            params=params,
        )
        return [IntakeInfo.from_dict(item) for item in data.get("intakes", [])]

    async def dispatch(
        self,
        *,
        session_id: str,
        owner_did: str,
        actor_did: str,
        objective: str,
        required_roles: list[str],
        preferred_playbook: str | None = None,
        entry_mode: str = "owner_pre_authorized",
        source: dict | None = None,
        constraints: dict | None = None,
    ) -> DispatchResult:
        data = await self._client._request(
            "POST",
            "/secretary/dispatch",
            json={
                "session_id": session_id,
                "owner_did": owner_did,
                "actor_did": actor_did,
                "objective": objective,
                "required_roles": required_roles,
                "preferred_playbook": preferred_playbook,
                "entry_mode": entry_mode,
                "source": source or {},
                "constraints": constraints or {},
            },
        )
        return DispatchResult.from_dict(data, session_id=session_id)

    async def confirm(self, session_id: str, *, owner_did: str, actor_did: str) -> dict:
        return await self._client._request(
            "POST",
            f"/secretary/intake/{session_id}/confirm",
            json={"owner_did": owner_did, "actor_did": actor_did},
        )

    async def abort(self, session_id: str, *, actor_did: str, reason: str = "") -> dict:
        return await self._client._request(
            "POST",
            f"/secretary/intake/{session_id}/abort",
            json={"actor_did": actor_did, "reason": reason},
        )
