"""Owner DID API for AgentNexus SDK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import AgentNexusClient


@dataclass
class OwnerInfo:
    did: str
    public_key_hex: str
    profile: dict

    @classmethod
    def from_dict(cls, data: dict) -> "OwnerInfo":
        return cls(
            did=data.get("did", ""),
            public_key_hex=data.get("public_key_hex", ""),
            profile=data.get("profile", {}),
        )


@dataclass
class OwnedAgent:
    did: str
    profile: dict
    last_seen: float

    @classmethod
    def from_dict(cls, data: dict) -> "OwnedAgent":
        return cls(
            did=data.get("did", ""),
            profile=data.get("profile", {}),
            last_seen=data.get("last_seen", 0.0),
        )


class OwnerClient:
    """High-level wrapper for Owner DID and owner-agent binding APIs."""

    def __init__(self, client: "AgentNexusClient"):
        self._client = client

    async def register(self, name: str = "Owner") -> OwnerInfo:
        data = await self._client._request(
            "POST",
            "/owner/register",
            json={"name": name},
        )
        return OwnerInfo.from_dict(data)

    async def bind(self, owner_did: str, agent_did: str) -> dict:
        return await self._client._request(
            "POST",
            "/owner/bind",
            json={"owner_did": owner_did, "agent_did": agent_did},
        )

    async def unbind(self, owner_did: str, agent_did: str) -> dict:
        return await self._client._request(
            "DELETE",
            "/owner/unbind",
            json={"owner_did": owner_did, "agent_did": agent_did},
        )

    async def list_agents(self, owner_did: str, actor_did: str | None = None) -> list[OwnedAgent]:
        data = await self._client._request(
            "GET",
            f"/owner/agents/{owner_did}",
            params={"actor_did": actor_did or owner_did},
        )
        return [OwnedAgent.from_dict(item) for item in data.get("agents", [])]

    async def get_profile(self, owner_did: str) -> dict:
        return await self._client._request(
            "GET",
            f"/owner/profile/{owner_did}",
            auth=False,
        )
