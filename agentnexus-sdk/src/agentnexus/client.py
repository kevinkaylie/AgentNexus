"""AgentNexus asynchronous client compatibility facade."""
from typing import Optional

from .client_base import AgentInfo, PushRegistration, ClientLifecycleMixin
from .client_actions import ClientActionsMixin
from .client_polling import ClientPollingMixin


class AgentNexusClient(
    ClientLifecycleMixin,
    ClientActionsMixin,
    ClientPollingMixin,
):
    """Connect, communicate, and coordinate through an AgentNexus node."""
# Convenience function for module-level import
async def connect(
    name: Optional[str] = None,
    caps: Optional[list[str]] = None,
    did: Optional[str] = None,
    daemon_url: Optional[str] = None,
    token: Optional[str] = None,
) -> AgentNexusClient:
    """
    Connect to AgentNexus network.

    Usage:
        # Register new identity
        nexus = await agentnexus.connect("MyAgent", caps=["Chat"])

        # Or use existing identity
        nexus = await agentnexus.connect(did="did:agentnexus:z6Mk...")
    """
    return await AgentNexusClient.connect(
        name=name,
        caps=caps,
        did=did,
        daemon_url=daemon_url,
        token=token,
    )
