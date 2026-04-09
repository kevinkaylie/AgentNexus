"""
AgentNexus SDK Client

Core client implementation for connecting to AgentNexus network.
"""
import asyncio
import json
import uuid
from typing import Optional, Callable, Any, Union
from dataclasses import dataclass

import aiohttp

from .discovery import (
    discover_daemon_url,
    discover_token,
    require_daemon,
    check_daemon_health,
)
from .exceptions import (
    DaemonNotFoundError,
    AuthenticationError,
    AgentNotFoundError,
    MessageDeliveryError,
    DIDNotFoundError,
    InvalidActionError,
    AgentNexusError,
)
from .models import Message, VerificationResult, Certification
from .actions import (
    ActionMessage,
    TaskPropose,
    TaskClaim,
    ResourceSync,
    StateNotify,
    ActionType,
    PROTOCOL_NEXUS_V1,
)
from .discussion import (
    DiscussionStart,
    DiscussionReply,
    DiscussionVote,
    DiscussionConclude,
    DiscussionMessageType,
    DiscussionManager,
)
from .emergency import EmergencyController, EmergencyConfig
from .enclave import EnclaveManager, EnclaveProxy, EnclaveInfo, VaultEntry


# Default Push callback URL for SDK (local webhook server)
DEFAULT_PUSH_CALLBACK_URL = "http://127.0.0.1:18765/push/callback"


@dataclass
class AgentInfo:
    """Information about the connected Agent."""
    did: str
    name: str
    capabilities: list[str]


@dataclass
class PushRegistration:
    """Push registration info."""
    registration_id: str
    callback_secret: str
    expires_at: float


class AgentNexusClient:
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

        # Polling state
        self._poll_interval = 2.0  # seconds
        self._poll_backoff = 1.0   # multiplier
        self._max_backoff = 30.0   # max interval

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

    async def send(
        self,
        to_did: str,
        content: Union[str, dict],
        message_type: Optional[str] = None,
        protocol: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        Send a message to another Agent.

        Args:
            to_did: Recipient's DID
            content: Message content (string or dict for Action Layer)
            message_type: Optional message type for Action Layer
            protocol: Optional protocol identifier (default: nexus_v1 if message_type set)
            session_id: Optional session ID for conversation threading

        Returns:
            Response from Daemon

        Raises:
            MessageDeliveryError: If message cannot be delivered
        """
        if not self._session:
            raise RuntimeError("Client not connected")

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        payload = {
            "from_did": self.agent_info.did,
            "to_did": to_did,
            "content": content,
        }

        if message_type:
            payload["message_type"] = message_type
            payload["protocol"] = protocol or PROTOCOL_NEXUS_V1

        if session_id:
            payload["session_id"] = session_id

        async with self._session.post(
            f"{self.daemon_url}/messages/send",
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status == 401:
                raise AuthenticationError()
            if resp.status != 200:
                text = await resp.text()
                raise MessageDeliveryError(text)

            return await resp.json()

    # ── Trust API ────────────────────────────────────────────────

    async def verify(self, did: str, trusted_cas: Optional[dict] = None) -> VerificationResult:
        """
        Verify the trust level of an Agent.

        Args:
            did: Agent's DID to verify
            trusted_cas: Optional dict of {ca_did: pubkey_hex}

        Returns:
            VerificationResult with trust level and permissions
        """
        if not self._session:
            raise RuntimeError("Client not connected")

        async with self._session.post(
            f"{self.daemon_url}/runtime/verify",
            json={
                "agent_did": did,
                "agent_public_key": "",  # Will be resolved by Daemon
                "trusted_cas": trusted_cas or {},
            },
        ) as resp:
            if resp.status != 200:
                raise AgentNotFoundError(did)

            data = await resp.json()
            return VerificationResult(
                did=did,
                trust_level=data.get("trust_level", 1),
                permissions=data.get("permissions", ["discover", "read"]),
                spending_limit=data.get("spending_limit", 0),
                certifications=data.get("certifications", []),
                metadata=data.get("metadata", {}),
            )

    async def certify(
        self,
        target_did: str,
        claim: str,
        evidence: str,
    ) -> Certification:
        """
        Issue a certification for another Agent.

        Note: This calls Daemon's /agents/{did}/certify endpoint,
        which performs the actual signing.

        Args:
            target_did: Agent to certify
            claim: Claim type (e.g., "payment_verified")
            evidence: Evidence URL or reference

        Returns:
            The issued Certification
        """
        if not self._session:
            raise RuntimeError("Client not connected")

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with self._session.post(
            f"{self.daemon_url}/agents/{target_did}/certify",
            headers=headers,
            json={
                "claim": claim,
                "evidence": evidence,
                "issuer_did": self.agent_info.did,
            },
        ) as resp:
            if resp.status == 401:
                raise AuthenticationError()
            if resp.status != 200:
                raise AgentNexusError(f"Certification failed: {await resp.text()}")

            data = await resp.json()
            return Certification(
                version=data.get("version", "1.0"),
                issuer=data.get("issuer", ""),
                issuer_pubkey=data.get("issuer_pubkey", ""),
                claim=claim,
                evidence=evidence,
                issued_at=data.get("issued_at", 0),
                signature=data.get("signature", ""),
            )

    # ── Action Layer API ────────────────────────────────────────

    async def propose_task(
        self,
        to_did: str,
        title: str,
        description: Optional[str] = None,
        deadline: Optional[str] = None,
        required_caps: Optional[list[str]] = None,
        priority: Optional[str] = None,
    ) -> str:
        """
        Propose a task to another Agent.

        Returns:
            Generated task_id
        """
        task_id = f"task_{uuid.uuid4().hex}"
        action = TaskPropose(
            task_id=task_id,
            title=title,
            description=description,
            deadline=deadline,
            required_caps=required_caps,
            priority=priority,
        )

        await self.send(
            to_did=to_did,
            content=action.to_content(),
            message_type=ActionType.TASK_PROPOSE,
        )

        return task_id

    async def claim_task(
        self,
        to_did: str,
        task_id: str,
        eta: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        """Claim a task."""
        action = TaskClaim(
            task_id=task_id,
            eta=eta,
            message=message,
        )

        await self.send(
            to_did=to_did,
            content=action.to_content(),
            message_type=ActionType.TASK_CLAIM,
        )

    async def sync_resource(
        self,
        to_did: str,
        key: str,
        value: Any,
        version: Optional[str] = None,
    ) -> None:
        """Sync a resource (key-value data)."""
        action = ResourceSync(
            key=key,
            value=value,
            version=version,
        )

        await self.send(
            to_did=to_did,
            content=action.to_content(),
            message_type=ActionType.RESOURCE_SYNC,
        )

    async def notify_state(
        self,
        to_did: str,
        status: str,
        task_id: Optional[str] = None,
        progress: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Notify state/progress."""
        action = StateNotify(
            task_id=task_id,
            status=status,
            progress=progress,
            error=error,
        )

        await self.send(
            to_did=to_did,
            content=action.to_content(),
            message_type=ActionType.STATE_NOTIFY,
        )

    # ── Callbacks ────────────────────────────────────────────────

    def on_message(self, callback: Callable) -> Callable:
        """
        Register a callback for free-text messages.

        Usage:
            @nexus.on_message
            async def handle(msg: Message):
                print(f"From {msg.from_did}: {msg.content}")
        """
        self._message_callbacks.append(callback)
        return callback

    def on_task_propose(self, callback: Callable) -> Callable:
        """Register callback for task_propose actions."""
        self._action_callbacks[ActionType.TASK_PROPOSE].append(callback)
        return callback

    def on_task_claim(self, callback: Callable) -> Callable:
        """Register callback for task_claim actions."""
        self._action_callbacks[ActionType.TASK_CLAIM].append(callback)
        return callback

    def on_resource_sync(self, callback: Callable) -> Callable:
        """Register callback for resource_sync actions."""
        self._action_callbacks[ActionType.RESOURCE_SYNC].append(callback)
        return callback

    def on_state_notify(self, callback: Callable) -> Callable:
        """Register callback for state_notify actions."""
        self._action_callbacks[ActionType.STATE_NOTIFY].append(callback)
        return callback

    # ── Discussion Callbacks ────────────────────────────────────────

    def on_discussion_start(self, callback: Callable) -> Callable:
        """Register callback for discussion_start messages."""
        self._discussion_callbacks[DiscussionMessageType.START].append(callback)
        return callback

    def on_discussion_reply(self, callback: Callable) -> Callable:
        """Register callback for discussion_reply messages."""
        self._discussion_callbacks[DiscussionMessageType.REPLY].append(callback)
        return callback

    def on_discussion_vote(self, callback: Callable) -> Callable:
        """Register callback for discussion_vote messages."""
        self._discussion_callbacks[DiscussionMessageType.VOTE].append(callback)
        return callback

    def on_discussion_conclude(self, callback: Callable) -> Callable:
        """Register callback for discussion_conclude messages."""
        self._discussion_callbacks[DiscussionMessageType.CONCLUDE].append(callback)
        return callback

    # ── Discussion API ─────────────────────────────────────────────

    @property
    def discussion(self) -> DiscussionManager:
        """Access the Discussion Manager for starting/managing discussions."""
        if not self._discussion_manager:
            self._discussion_manager = DiscussionManager(self)
        return self._discussion_manager

    # ── Enclave API ─────────────────────────────────────────────────

    @property
    def enclaves(self) -> EnclaveManager:
        """Access the Enclave Manager for creating/managing Enclaves."""
        if not self._enclave_manager:
            self._enclave_manager = EnclaveManager(self)
        return self._enclave_manager

    async def create_enclave(
        self,
        name: str,
        members: dict[str, dict],
        vault_backend: str = "local",
        vault_config: Optional[dict] = None,
    ) -> EnclaveProxy:
        """
        Create an Enclave (project team).

        Args:
            name: Enclave name
            members: Member mapping {"role": {"did": "...", "handbook": "..."}}
            vault_backend: Vault backend type (local / git)
            vault_config: Vault config (git needs repo_path)

        Returns:
            EnclaveProxy
        """
        return await self.enclaves.create(name, members, vault_backend, vault_config)

    async def vault_get(self, enclave_id: str, key: str) -> VaultEntry:
        """Direct access to read from a Vault."""
        from .enclave import VaultProxy
        proxy = VaultProxy(self, enclave_id)
        return await proxy.get(key)

    async def vault_put(
        self,
        enclave_id: str,
        key: str,
        value: str,
        message: str = "",
    ):
        """Direct access to write to a Vault."""
        from .enclave import VaultProxy
        proxy = VaultProxy(self, enclave_id)
        return await proxy.put(key, value, message)

    # ── Polling ──────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Background polling loop for incoming messages."""
        success_count = 0
        while self._running:
            try:
                await self._poll_messages()
                # Reset backoff on success
                self._poll_backoff = 1.0
                self._poll_interval = 2.0
                success_count += 1
                # After 10 consecutive successes, consider connection stable
                # and reset any accumulated backoff state
                if success_count >= 10:
                    success_count = 0
            except Exception as e:
                success_count = 0
                # Exponential backoff
                self._poll_interval = min(
                    self._poll_interval * 2,
                    self._max_backoff,
                )
                print(f"[SDK] Poll error, backing off to {self._poll_interval}s: {e}")

            await asyncio.sleep(self._poll_interval)

    async def _poll_messages(self) -> None:
        """Poll for new messages and dispatch to callbacks."""
        if not self._session:
            return

        async with self._session.get(
            f"{self.daemon_url}/messages/inbox/{self.agent_info.did}",
        ) as resp:
            if resp.status != 200:
                raise MessageDeliveryError(f"Poll failed: {resp.status}")

            messages = await resp.json()

            for msg_data in messages:
                msg = Message(
                    id=msg_data["id"],
                    from_did=msg_data["from"],
                    content=msg_data["content"],
                    timestamp=msg_data["timestamp"],
                    session_id=msg_data.get("session_id", ""),
                    reply_to=msg_data.get("reply_to"),
                    message_type=msg_data.get("message_type"),
                    protocol=msg_data.get("protocol"),
                )

                await self._dispatch_message(msg)

    async def _fetch_all_messages(self) -> list[Message]:
        """
        Fetch all messages for this Agent (including delivered ones).

        Used by DiscussionManager to query discussion history.
        """
        if not self._session:
            return []

        async with self._session.get(
            f"{self.daemon_url}/messages/all/{self.agent_info.did}",
            params={"limit": 1000},
        ) as resp:
            if resp.status != 200:
                return []

            data = await resp.json()
            messages = data.get("messages", [])
            return [
                Message(
                    id=msg_data["id"],
                    from_did=msg_data["from"],
                    content=msg_data["content"],
                    timestamp=msg_data["timestamp"],
                    session_id=msg_data.get("session_id", ""),
                    reply_to=msg_data.get("reply_to"),
                    message_type=msg_data.get("message_type"),
                    protocol=msg_data.get("protocol"),
                )
                for msg_data in messages
            ]

    async def _dispatch_message(self, msg: Message) -> None:
        """Dispatch message to appropriate callbacks."""
        # Check if this is a Discussion Protocol message
        if (
            msg.message_type
            and msg.protocol == PROTOCOL_NEXUS_V1
            and msg.message_type in self._discussion_callbacks
        ):
            callbacks = self._discussion_callbacks[msg.message_type]
            if callbacks:
                try:
                    content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content

                    # Handle discussion message via DiscussionManager
                    if self._discussion_manager:
                        if msg.message_type == DiscussionMessageType.START:
                            sm = self._discussion_manager.handle_discussion_start(
                                msg.from_did, content, msg.id
                            )
                            for cb in callbacks:
                                try:
                                    result = cb(sm)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception as e:
                                    print(f"[SDK] Discussion callback error: {e}")
                            return
                        elif msg.message_type == DiscussionMessageType.REPLY:
                            reply, sm, validation_status = self._discussion_manager.handle_discussion_reply(
                                msg.from_did, content, msg.id
                            )
                            for cb in callbacks:
                                try:
                                    result = cb(reply, sm, validation_status)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception as e:
                                    print(f"[SDK] Discussion callback error: {e}")
                            return
                        elif msg.message_type == DiscussionMessageType.VOTE:
                            vote, sm, consensus_result = self._discussion_manager.handle_discussion_vote(
                                msg.from_did, content, msg.id
                            )
                            for cb in callbacks:
                                try:
                                    result = cb(vote, sm, consensus_result)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception as e:
                                    print(f"[SDK] Discussion callback error: {e}")
                            # Auto-conclude if consensus reached and we're the initiator
                            if consensus_result and sm.topic_id in self._discussion_manager._initiated:
                                await self._discussion_manager._check_auto_conclude(sm.topic_id)
                            return
                        elif msg.message_type == DiscussionMessageType.CONCLUDE:
                            conclude_msg, sm = self._discussion_manager.handle_discussion_conclude(
                                msg.from_did, content, msg.id
                            )
                            for cb in callbacks:
                                try:
                                    result = cb(conclude_msg, sm)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception as e:
                                    print(f"[SDK] Discussion callback error: {e}")
                            return
                except json.JSONDecodeError:
                    pass  # Fall through to action handling

        # Check if this is an Action Layer message
        if (
            msg.message_type
            and msg.protocol == PROTOCOL_NEXUS_V1
            and msg.message_type in self._action_callbacks
        ):
            callbacks = self._action_callbacks[msg.message_type]
            # Check for emergency_halt (state_notify with status="emergency_halt")
            if msg.message_type == ActionType.STATE_NOTIFY:
                try:
                    content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                    if content.get("status") == "emergency_halt":
                        # Handle emergency halt with built-in enforcement
                        if self._emergency_controller:
                            result = await self._emergency_controller.handle_emergency_halt(
                                msg.from_did, content, self
                            )
                            if result.get("handled"):
                                # Emergency halt executed, don't call user callbacks
                                return
                        # Fall through if not handled (no controller or unauthorized)

                except (json.JSONDecodeError, TypeError):
                    pass

            if callbacks:
                # Parse content as action
                try:
                    content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                    action_msg = ActionMessage(
                        from_did=msg.from_did,
                        message_type=msg.message_type,
                        content=content,
                    )
                    for cb in callbacks:
                        try:
                            result = cb(action_msg)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            print(f"[SDK] Callback error: {e}")
                    return
                except json.JSONDecodeError:
                    pass  # Fall through to regular message handling

        # Regular message or no action callback registered
        for cb in self._message_callbacks:
            try:
                result = cb(msg)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                print(f"[SDK] Message callback error: {e}")


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
