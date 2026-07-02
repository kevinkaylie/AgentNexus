"""
AgentNexus SDK Client

Core client implementation for connecting to AgentNexus network.
"""
import uuid
from typing import Optional, Callable, Any, Union


from .exceptions import (
    AuthenticationError,
    AgentNotFoundError,
    MessageDeliveryError,
    AgentNexusError,
)
from .models import VerificationResult, Certification
from .actions import (
    TaskPropose,
    TaskClaim,
    ResourceSync,
    StateNotify,
    ActionType,
    PROTOCOL_NEXUS_V1,
)
from .discussion import (
    DiscussionMessageType,
    DiscussionManager,
)
from .enclave import EnclaveManager, EnclaveProxy, VaultEntry


class ClientActionsMixin:
    async def send(
        self,
        to_did: str,
        content: Union[str, dict],
        message_type: Optional[str] = None,
        protocol: Optional[str] = None,
        session_id: Optional[str] = None,
        message_id: Optional[str] = None,
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
        if message_id:
            payload["message_id"] = message_id

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
        output_ref: Optional[dict | str] = None,
        reason: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> None:
        """Notify state/progress."""
        action = StateNotify(
            task_id=task_id,
            status=status,
            progress=progress,
            error=error,
            output_ref=output_ref,
            reason=reason,
            context=context,
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
        *,
        owner_did: Optional[str] = None,
        actor_did: Optional[str] = None,
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
        return await self.enclaves.create(
            name,
            members,
            vault_backend,
            vault_config,
            owner_did=owner_did,
            actor_did=actor_did,
        )

    async def vault_get(
        self,
        enclave_id: str,
        key: str,
        *,
        actor_did: Optional[str] = None,
    ) -> VaultEntry:
        """Direct access to read from a Vault."""
        from .enclave import VaultProxy
        proxy = VaultProxy(self, enclave_id, actor_did=actor_did)
        return await proxy.get(key)

    async def vault_put(
        self,
        enclave_id: str,
        key: str,
        value: str,
        message: str = "",
        *,
        author_did: Optional[str] = None,
    ):
        """Direct access to write to a Vault."""
        from .enclave import VaultProxy
        proxy = VaultProxy(self, enclave_id, actor_did=author_did)
        return await proxy.put(key, value, message, author_did=author_did)

    # ── Polling ──────────────────────────────────────────────────


__all__ = ["ClientActionsMixin"]
