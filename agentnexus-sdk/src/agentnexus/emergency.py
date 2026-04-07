"""
AgentNexus SDK Emergency Override

Implements EMERGENCY_OVERRIDE functionality for emergency halt operations.

Based on ADR-011: Discussion Protocol Design, Decision 9
"""
import asyncio
from typing import Optional, Set, Callable, Any
from dataclasses import dataclass, field


@dataclass
class EmergencyConfig:
    """
    Configuration for emergency halt functionality.

    Attributes:
        authorized_dids: Set of DIDs authorized to send emergency_halt
        on_emergency: Optional callback for custom cleanup (called after halt)
    """
    authorized_dids: Set[str] = field(default_factory=set)
    on_emergency: Optional[Callable[[], Any]] = None


class EmergencyController:
    """
    Controller for emergency halt operations.

    Emergency halt is triggered by receiving a state_notify message with
    status="emergency_halt" from an authorized DID. The SDK performs
    built-in halt actions and optionally triggers a user callback.

    Usage:
        config = EmergencyConfig(
            authorized_dids={"did:agentnexus:z6Mk...secretary"},
            on_emergency=async_cleanup,
        )
        controller = EmergencyController(config)

        # In message dispatch:
        if msg.message_type == "state_notify":
            content = json.loads(msg.content)
            if content.get("status") == "emergency_halt":
                controller.handle_emergency_halt(msg.from_did, content)
    """

    def __init__(self, config: EmergencyConfig):
        """
        Initialize emergency controller.

        Args:
            config: Emergency configuration
        """
        self.config = config
        self._halted = False
        self._halt_event = asyncio.Event()

    @property
    def is_halted(self) -> bool:
        """Check if system is halted."""
        return self._halted

    def is_authorized(self, from_did: str) -> bool:
        """
        Check if a DID is authorized to send emergency halt.

        Args:
            from_did: Sender's DID

        Returns:
            True if authorized
        """
        return from_did in self.config.authorized_dids

    async def handle_emergency_halt(
        self,
        from_did: str,
        content: dict,
        client: Optional[Any] = None,
    ) -> dict:
        """
        Handle an emergency halt message.

        This performs built-in halt actions:
        1. Cancel all pending tasks
        2. Stop message polling
        3. Reply with state_notify(status="halted")
        4. Trigger optional on_emergency callback

        Args:
            from_did: Sender's DID
            content: Message content with "status", "scope", "reason"
            client: Optional AgentNexusClient for reply

        Returns:
            Result dict with halt status
        """
        # Check authorization
        if not self.is_authorized(from_did):
            # Silently ignore unauthorized emergency halt
            return {"handled": False, "reason": "unauthorized"}

        if self._halted:
            return {"handled": False, "reason": "already_halted"}

        # Mark as halted
        self._halted = True
        self._halt_event.set()

        scope = content.get("scope", "all")
        reason = content.get("reason", "No reason provided")

        # Built-in halt actions
        halt_result = {
            "handled": True,
            "scope": scope,
            "reason": reason,
        }

        # Cancel client tasks if provided
        if client:
            # Stop polling
            client._running = False

            # Send acknowledgment
            try:
                await client.send(
                    to_did=from_did,
                    content={"status": "halted", "reason": reason},
                    message_type="state_notify",
                )
            except Exception as e:
                halt_result["ack_error"] = str(e)

        # Trigger user callback
        if self.config.on_emergency:
            try:
                result = self.config.on_emergency()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                halt_result["callback_error"] = str(e)

        return halt_result

    async def wait_for_halt(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for emergency halt to occur.

        Args:
            timeout: Maximum time to wait (None = forever)

        Returns:
            True if halted, False if timeout
        """
        try:
            if timeout:
                await asyncio.wait_for(self._halt_event.wait(), timeout)
            else:
                await self._halt_event.wait()
            return True
        except asyncio.TimeoutError:
            return False

    def reset(self) -> None:
        """Reset halt state (for testing)."""
        self._halted = False
        self._halt_event.clear()


# ── Integration Helper ────────────────────────────────────────────────

def create_emergency_controller(
    authorized_dids: list[str],
    on_emergency: Optional[Callable] = None,
) -> EmergencyController:
    """
    Create an emergency controller with configuration.

    Args:
        authorized_dids: List of DIDs authorized to send emergency halt
        on_emergency: Optional async callback for cleanup

    Returns:
        Configured EmergencyController
    """
    config = EmergencyConfig(
        authorized_dids=set(authorized_dids),
        on_emergency=on_emergency,
    )
    return EmergencyController(config)
