"""
AgentNexus SDK Sync Wrapper

Provides synchronous API for non-async contexts.
"""
import asyncio
import inspect
from typing import Optional

from .client import AgentNexusClient


class _SyncFacade:
    """Run coroutine-returning facade methods on SyncClient's event loop."""

    def __init__(self, target, runner):
        self._target = target
        self._runner = runner

    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        def wrapper(*args, **kwargs):
            result = attr(*args, **kwargs)
            if inspect.isawaitable(result):
                return self._runner(result)
            return result

        return wrapper


class _SyncVaultProxy:
    def __init__(self, target, runner):
        self._target = target
        self._runner = runner

    def get(self, key: str, **kwargs):
        return self._runner(self._target.get(key, **kwargs))

    def put(self, key: str, value: str, **kwargs):
        return self._runner(self._target.put(key, value, **kwargs))

    def list(self, **kwargs):
        return self._runner(self._target.list(**kwargs))

    def history(self, key: str, **kwargs):
        return self._runner(self._target.history(key, **kwargs))

    def delete(self, key: str, **kwargs):
        return self._runner(self._target.delete(key, **kwargs))


class _SyncPlaybookRunProxy:
    def __init__(self, target, runner):
        self._target = target
        self._runner = runner

    @property
    def run_id(self) -> str:
        return self._target.run_id

    def get_status(self, **kwargs):
        return self._runner(self._target.get_status(**kwargs))


class _SyncEnclaveProxy:
    def __init__(self, target, runner):
        self._target = target
        self._runner = runner
        self.vault = _SyncVaultProxy(target.vault, runner)

    @property
    def enclave_id(self) -> str:
        return self._target.enclave_id

    @property
    def info(self):
        return self._target.info

    def run_playbook(self, playbook: Optional[dict] = None, playbook_id: Optional[str] = None, **kwargs):
        proxy = self._runner(self._target.run_playbook(playbook, playbook_id, **kwargs))
        return _SyncPlaybookRunProxy(proxy, self._runner)

    def get_run(self, run_id: Optional[str] = None, **kwargs):
        return self._runner(self._target.get_run(run_id, **kwargs))

    def add_member(self, did: str, role: str, **kwargs):
        return self._runner(self._target.add_member(did, role, **kwargs))

    def remove_member(self, did: str, **kwargs):
        return self._runner(self._target.remove_member(did, **kwargs))


class _SyncEnclaveManager:
    def __init__(self, target, runner):
        self._target = target
        self._runner = runner

    def create(self, name: str, members: dict[str, dict], *args, **kwargs):
        proxy = self._runner(self._target.create(name, members, *args, **kwargs))
        return _SyncEnclaveProxy(proxy, self._runner)

    def get(self, enclave_id: str, **kwargs):
        proxy = self._runner(self._target.get(enclave_id, **kwargs))
        return _SyncEnclaveProxy(proxy, self._runner)

    def list(self, **kwargs):
        return self._runner(self._target.list(**kwargs))

    def archive(self, enclave_id: str, **kwargs):
        return self._runner(self._target.archive(enclave_id, **kwargs))


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
        self.owner = _SyncFacade(client.owner, self._run)
        self.team = _SyncFacade(client.team, self._run)
        self.secretary = _SyncFacade(client.secretary, self._run)
        self.runs = _SyncFacade(client.runs, self._run)
        self.worker = client.worker
        self.enclaves = _SyncEnclaveManager(client.enclaves, self._run)
        self.orchestration = type(
            "SyncOrchestration",
            (),
            {
                "owner": self.owner,
                "team": self.team,
                "secretary": self.secretary,
                "runs": self.runs,
                "worker": self.worker,
            },
        )()

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

    def create_enclave(self, name: str, members: dict[str, dict], *args, **kwargs):
        """Create an Enclave (synchronous)."""
        proxy = self._run(self._client.create_enclave(name, members, *args, **kwargs))
        return _SyncEnclaveProxy(proxy, self._run)

    def vault_get(self, enclave_id: str, key: str, **kwargs):
        """Read from a Vault (synchronous)."""
        return self._run(self._client.vault_get(enclave_id, key, **kwargs))

    def vault_put(self, enclave_id: str, key: str, value: str, **kwargs):
        """Write to a Vault (synchronous)."""
        return self._run(self._client.vault_put(enclave_id, key, value, **kwargs))

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
