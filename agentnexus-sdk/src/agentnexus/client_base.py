"""
AgentNexus SDK Client

Core client implementation for connecting to AgentNexus network.
"""
import asyncio
from typing import Optional, Callable, TYPE_CHECKING
from dataclasses import dataclass

import aiohttp

from .discovery import (
    discover_daemon_url,
    discover_token,
    require_daemon,
)
from .exceptions import (
    AuthenticationError,
    AgentNotFoundError,
    DIDNotFoundError,
    AgentNexusError,
)
from .actions import (
    ActionType,
)
from .discussion import (
    DiscussionMessageType,
    DiscussionManager,
)
from .emergency import EmergencyController, EmergencyConfig
from .enclave import EnclaveManager
from .owner import OwnerClient
from .team import TeamClient
from .secretary import SecretaryClient
from .runs import RunClient
from .worker import WorkerRuntime
from .orchestration import OrchestrationClient
from .coordination import CoordinationClient
from .constants import DEFAULT_PUSH_CALLBACK_URL

if TYPE_CHECKING:
    from .client import AgentNexusClient


@dataclass
class AgentInfo:
    """Information about the connected Agent."""
    did: str
    name: str
    capabilities: list[str]
    owner_did: str = ""       # D-SEC-08: 身份映射，SDK Agent/CLI Worker 查找 owner
    worker_type: str = ""     # resident / interactive_cli / service_worker


@dataclass
class PushRegistration:
    """Push registration info."""
    registration_id: str
    callback_secret: str
    expires_at: float


class ClientLifecycleMixin:
    """
    AgentNexus client for connecting to the decentralized Agent network.

    Usage:
        # Register new identity
        nexus = await AgentNexusClient.connect(name="MyAgent", caps=["Chat"])

        # Or use existing identity
        nexus = await AgentNexusClient.connect(did="did:agentnexus:z6Mk...")

        # Send message
        await nexus.send(to_did="...", content="Hello!")

        # Receive messages
        @nexus.on_message
        async def handle(msg):
            print(f"From {msg.from_did}: {msg.content}")

        # Close
        await nexus.close()
    """

    def __init__(
        self,
        daemon_url: str,
        token: Optional[str],
        agent_info: AgentInfo,
    ):
        self.daemon_url = daemon_url
        self.token = token
        self.agent_info = agent_info

        self._session: Optional[aiohttp.ClientSession] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._running = False

        # Push registration (v0.9)
        self._push_registration: Optional[PushRegistration] = None
        self._push_refresh_task: Optional[asyncio.Task] = None
        self._push_callback_url: Optional[str] = None
        self._push_expires: int = 3600  # Remember original TTL for refresh

        # Callbacks
        self._message_callbacks: list[Callable] = []
        self._action_callbacks: dict[str, list[Callable]] = {
            ActionType.TASK_PROPOSE: [],
            ActionType.TASK_CLAIM: [],
            ActionType.RESOURCE_SYNC: [],
            ActionType.STATE_NOTIFY: [],
        }
        self._discussion_callbacks: dict[str, list[Callable]] = {
            DiscussionMessageType.START: [],
            DiscussionMessageType.REPLY: [],
            DiscussionMessageType.VOTE: [],
            DiscussionMessageType.CONCLUDE: [],
        }

        # Discussion Manager
        self._discussion_manager: Optional[DiscussionManager] = None

        # Emergency Controller
        self._emergency_controller: Optional[EmergencyController] = None

        # Enclave Manager
        self._enclave_manager: Optional[EnclaveManager] = None

        # Orchestration SDK facades
        self.owner = OwnerClient(self)
        self.team = TeamClient(self)
        self.secretary = SecretaryClient(self)
        self.runs = RunClient(self)
        self.worker = WorkerRuntime(self)
        self.orchestration = OrchestrationClient(self)
        self.coordination = CoordinationClient(self)

        # Polling state
        self._poll_interval = 2.0  # seconds
        self._poll_backoff = 1.0   # multiplier
        self._max_backoff = 30.0   # max interval

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        auth: bool = True,
    ) -> dict:
        """Internal HTTP helper used by higher-level SDK facades."""
        if not self._session:
            raise RuntimeError("Client not connected")

        headers = {}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        url = f"{self.daemon_url}{path}"
        async with self._session.request(
            method.upper(),
            url,
            headers=headers,
            json=json,
            params=params,
        ) as resp:
            if resp.status == 401:
                raise AuthenticationError("Invalid or missing token")
            if resp.status == 403:
                raise PermissionError(await resp.text())
            if resp.status == 404:
                raise KeyError(await resp.text())
            if resp.status < 200 or resp.status >= 300:
                raise AgentNexusError(await resp.text())
            if resp.status == 204:
                return {}
            try:
                return await resp.json()
            except Exception:
                return {}

    def configure_emergency(
        self,
        authorized_dids: list[str],
        on_emergency: Optional[Callable] = None,
    ) -> None:
        """
        Configure emergency halt functionality.

        Args:
            authorized_dids: List of DIDs authorized to send emergency_halt
            on_emergency: Optional async callback for custom cleanup
        """
        self._emergency_controller = EmergencyController(
            EmergencyConfig(
                authorized_dids=set(authorized_dids),
                on_emergency=on_emergency,
            )
        )

    @property
    def emergency(self) -> Optional[EmergencyController]:
        """Access the Emergency Controller."""
        return self._emergency_controller

    @classmethod
    async def connect(
        cls,
        name: Optional[str] = None,
        caps: Optional[list[str]] = None,
        did: Optional[str] = None,
        daemon_url: Optional[str] = None,
        token: Optional[str] = None,
    ) -> "AgentNexusClient":
        """
        Connect to AgentNexus network.

        Args:
            name: Agent name (for new registration)
            caps: Capabilities list (for new registration)
            did: Existing DID to connect (skips registration)
            daemon_url: Daemon URL (auto-discovered if not provided)
            token: Authentication token (auto-discovered if not provided)

        Returns:
            Connected AgentNexusClient instance

        Raises:
            DaemonNotFoundError: If Daemon is not reachable
            DIDNotFoundError: If did is provided but not registered
            ValueError: If neither name nor did is provided
        """
        # Discover Daemon URL
        url = discover_daemon_url(daemon_url)
        await require_daemon(url)

        # Discover token
        tok = discover_token(token)

        # Either register new or use existing
        if did:
            agent_info = await cls._verify_existing_did(url, tok, did)
        elif name:
            agent_info = await cls._register_new_agent(url, tok, name, caps or [])
        else:
            raise ValueError("Either 'name' or 'did' must be provided")

        client = cls(url, tok, agent_info)
        await client._start()

        return client

    @staticmethod
    async def _verify_existing_did(
        daemon_url: str,
        token: Optional[str],
        did: str,
    ) -> AgentInfo:
        """Verify existing DID exists in Daemon."""
        async with aiohttp.ClientSession() as session:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            async with session.get(
                f"{daemon_url}/agents/{did}",
                headers=headers,
            ) as resp:
                if resp.status == 404:
                    raise DIDNotFoundError(did)
                if resp.status != 200:
                    raise AgentNotFoundError(did)

                data = await resp.json()
                profile = data.get("profile", {})
                return AgentInfo(
                    did=did,
                    name=profile.get("name", ""),
                    capabilities=profile.get("capabilities", []),
                    owner_did=data.get("owner_did", ""),
                    worker_type=data.get("worker_type", ""),
                )

    @staticmethod
    async def _register_new_agent(
        daemon_url: str,
        token: Optional[str],
        name: str,
        caps: list[str],
    ) -> AgentInfo:
        """Register a new Agent with Daemon."""
        async with aiohttp.ClientSession() as session:
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            async with session.post(
                f"{daemon_url}/agents/register",
                headers=headers,
                json={"name": name, "capabilities": caps},
            ) as resp:
                if resp.status == 401:
                    raise AuthenticationError("Invalid or missing token")
                if resp.status != 200:
                    raise AgentNexusError(f"Registration failed: {await resp.text()}")

                data = await resp.json()
                return AgentInfo(
                    did=data["did"],
                    name=name,
                    capabilities=caps,
                    owner_did=data.get("owner_did", ""),
                    worker_type=data.get("worker_type", ""),
                )

    async def _start(self) -> None:
        """Start the client (create session, start polling)."""
        self._session = aiohttp.ClientSession()
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        # Initialize discussion manager
        self._discussion_manager = DiscussionManager(self)

    async def register_push(
        self,
        callback_url: Optional[str] = None,
        callback_type: str = "webhook",
        expires: int = 3600,
    ) -> PushRegistration:
        """
        Register push notification callback (ADR-012 L3).

        Args:
            callback_url: Callback URL (default: local webhook server)
            callback_type: webhook / sse / platform
            expires: TTL in seconds

        Returns:
            PushRegistration with registration_id and callback_secret
        """
        if not self._session:
            raise RuntimeError("Client not connected")

        url = callback_url or DEFAULT_PUSH_CALLBACK_URL
        self._push_callback_url = url

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with self._session.post(
            f"{self.daemon_url}/push/register",
            headers=headers,
            json={
                "did": self.agent_info.did,
                "callback_url": url,
                "callback_type": callback_type,
                "expires": expires,
            },
        ) as resp:
            if resp.status != 200:
                raise AgentNexusError(f"Push registration failed: {await resp.text()}")

            data = await resp.json()
            self._push_registration = PushRegistration(
                registration_id=data["registration_id"],
                callback_secret=data["callback_secret"],
                expires_at=data["expires_at"],
            )
            self._push_expires = expires  # Remember for refresh

            # Start background refresh task (refresh at expires/2)
            if self._push_refresh_task:
                self._push_refresh_task.cancel()
            self._push_refresh_task = asyncio.create_task(
                self._push_refresh_loop(expires // 2)
            )

            return self._push_registration

    async def _push_refresh_loop(self, interval: int) -> None:
        """Background task to refresh push registration."""
        while self._running and self._push_callback_url:
            await asyncio.sleep(interval)
            try:
                await self._refresh_push_registration()
            except Exception as e:
                print(f"[SDK] Push refresh error: {e}")

    async def _refresh_push_registration(self) -> None:
        """Refresh push registration TTL."""
        if not self._session or not self._push_callback_url:
            return

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with self._session.post(
            f"{self.daemon_url}/push/refresh",
            headers=headers,
            json={
                "did": self.agent_info.did,
                "callback_url": self._push_callback_url,
                "callback_type": "webhook",
                "expires": self._push_expires,  # Use original TTL
            },
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if self._push_registration:
                    self._push_registration.expires_at = data["expires_at"]

    async def unregister_push(self) -> bool:
        """Unregister push notification."""
        if not self._session:
            return False

        if self._push_refresh_task:
            self._push_refresh_task.cancel()
            self._push_refresh_task = None

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with self._session.delete(
            f"{self.daemon_url}/push/{self.agent_info.did}",
            headers=headers,
        ) as resp:
            self._push_registration = None
            return resp.status == 200

    async def close(self) -> None:
        """Close the client connection."""
        self._running = False

        # Cancel push refresh task
        if self._push_refresh_task:
            self._push_refresh_task.cancel()
            try:
                await asyncio.wait_for(self._push_refresh_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            finally:
                self._push_refresh_task = None

        # Unregister push on close
        if self._push_registration:
            try:
                await self.unregister_push()
            except Exception:
                pass

        if self._poll_task:
            self._poll_task.cancel()
            try:
                # Wait for poll task to finish with timeout
                await asyncio.wait_for(self._poll_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        if self._session:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "AgentNexusClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    # ── Messaging API ────────────────────────────────────────────


__all__ = ["AgentInfo", "PushRegistration", "ClientLifecycleMixin"]
