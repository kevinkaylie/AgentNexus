"""
AgentNexus SDK Sync Wrapper

Provides synchronous API for non-async contexts.
"""
import asyncio
from typing import Optional

from .client import AgentNexusClient


class SyncClient:
    """
    Synchronous wrapper for AgentNexusClient.

    Usage:
        nexus = agentnexus.sync.connect("MyAgent")
        nexus.send(to_did="...", content="Hello!")
        nexus.close()
    """

    def __init__(self, client: AgentNexusClient, loop: asyncio.AbstractEventLoop):
        self._client = client
        self._loop = loop

    @property
    def did(self) -> str:
        return self._client.agent_info.did

    @property
    def name(self) -> str:
        return self._client.agent_info.name

    @property
    def capabilities(self) -> list[str]:
        return self._client.agent_info.capabilities

    def send(self, to_did: str, content: str | dict, **kwargs) -> dict:
        """Send a message (synchronous)."""
        return self._run(self._client.send(to_did, content, **kwargs))

    def verify(self, did: str, trusted_cas: Optional[dict] = None):
        """Verify an Agent's trust level (synchronous)."""
        return self._run(self._client.verify(did, trusted_cas))

    def certify(self, target_did: str, claim: str, evidence: str):
        """Issue a certification (synchronous)."""
        return self._run(self._client.certify(target_did, claim, evidence))

    def propose_task(self, to_did: str, title: str, **kwargs) -> str:
        """Propose a task (synchronous)."""
        return self._run(self._client.propose_task(to_did, title, **kwargs))

    def claim_task(self, to_did: str, task_id: str, **kwargs) -> None:
        """Claim a task (synchronous)."""
        return self._run(self._client.claim_task(to_did, task_id, **kwargs))

    def sync_resource(self, to_did: str, key: str, value, **kwargs) -> None:
        """Sync a resource (synchronous)."""
        return self._run(self._client.sync_resource(to_did, key, value, **kwargs))

    def notify_state(self, to_did: str, status: str, **kwargs) -> None:
        """Notify state (synchronous)."""
        return self._run(self._client.notify_state(to_did, status, **kwargs))

    def on_message(self, callback):
        """Register message callback (works in sync context)."""
        return self._client.on_message(callback)

    def on_task_propose(self, callback):
        """Register task_propose callback."""
        return self._client.on_task_propose(callback)

    def on_task_claim(self, callback):
        """Register task_claim callback."""
        return self._client.on_task_claim(callback)

    def on_resource_sync(self, callback):
        """Register resource_sync callback."""
        return self._client.on_resource_sync(callback)

    def on_state_notify(self, callback):
        """Register state_notify callback."""
        return self._client.on_state_notify(callback)

    def close(self) -> None:
        """Close the connection (synchronous)."""
        return self._run(self._client.close())

    def _run(self, coro):
        """
        Run a coroutine in the event loop.

        Note: We use asyncio.run_coroutine_threadsafe() when the loop is running
        (e.g., in a callback context). This requires the loop to be running in
        another thread. For simpler usage, the loop should not be running yet.

        For typical sync usage, just create a fresh loop per call to avoid
        cross-loop session issues.
        """
        if self._loop.is_running():
            # Loop is running (e.g., in a callback). Use threadsafe approach.
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result()
        return self._loop.run_until_complete(coro)

    def __enter__(self) -> "SyncClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()


def connect(
    name: Optional[str] = None,
    caps: Optional[list[str]] = None,
    did: Optional[str] = None,
    daemon_url: Optional[str] = None,
    token: Optional[str] = None,
) -> SyncClient:
    """
    Connect to AgentNexus network (synchronous).

    Usage:
        # Register new identity
        nexus = agentnexus.sync.connect("MyAgent", caps=["Chat"])

        # Or use existing identity
        nexus = agentnexus.sync.connect(did="did:agentnexus:z6Mk...")

        nexus.send(to_did="...", content="Hello!")
        nexus.close()
    """
    loop = asyncio.new_event_loop()
    client = loop.run_until_complete(
        AgentNexusClient.connect(
            name=name,
            caps=caps,
            did=did,
            daemon_url=daemon_url,
            token=token,
        )
    )
    return SyncClient(client, loop)
