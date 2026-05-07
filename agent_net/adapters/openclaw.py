"""
OpenClaw Platform Adapter

Adapter for OpenClaw platform integration via Skill mechanism.
"""
from typing import Dict, Any, Optional
import json

from .base import PlatformAdapter, SkillManifest


class OpenClawAdapter(PlatformAdapter):
    """
    OpenClaw platform adapter.

    Bridges OpenClaw Skill calls to AgentNexus operations.

    Usage:
        adapter = OpenClawAdapter(agent_did, router, storage)
        await adapter.inbound({"action": "invoke_skill", ...})
    """

    platform = "openclaw"

    def __init__(
        self,
        agent_did: str,
        router,  # agent_net.router.Router
        storage,  # agent_net.storage module
        owner_did: str = "",
    ):
        """
        Initialize OpenClaw adapter.

        Args:
            agent_did: The Agent DID this adapter is bound to
            router: Daemon's router module for message sending
            storage: Daemon's storage module for agent info
            owner_did: D-SEC-08: Skill 注册时绑定的 owner_did
        """
        self.agent_did = agent_did
        self.router = router
        self.storage = storage
        self.owner_did = owner_did
        self._action_handlers: Dict[str, callable] = {}

        # Register default action handlers
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register default action handlers."""
        self._action_handlers["invoke_skill"] = self._handle_invoke_skill
        self._action_handlers["query_status"] = self._handle_query_status
        self._action_handlers["send_message"] = self._handle_send_message
        self._action_handlers["get_profile"] = self._handle_get_profile
        self._action_handlers["dispatch_intake"] = self._handle_dispatch_intake

    async def inbound(self, request: dict) -> dict:
        """
        Handle OpenClaw Skill call → AgentNexus operation.

        Args:
            request: {
                "action": "invoke_skill" | "query_status" | "send_message" | "get_profile",
                ...action-specific params
            }

        Returns:
            Response dict
        """
        action = request.get("action")
        if not action:
            return {"error": "Missing action field", "status": 400}

        handler = self._action_handlers.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}", "status": 400}

        try:
            result = await handler(request)
            return {"status": "ok", "result": result}
        except Exception as e:
            return {"error": str(e), "status": 500}

    async def outbound(self, message: dict) -> dict:
        """
        Handle AgentNexus message → OpenClaw callback.

        Args:
            message: AgentNexus message dict

        Returns:
            Callback response
        """
        # OpenClaw expects a specific callback format
        return {
            "skill_id": message.get("skill_id", "agentnexus-comm"),
            "result": message.get("content"),
            "status": "completed",
        }

    def skill_manifest(self) -> dict:
        """Return skill manifest for this adapter."""
        manifest = SkillManifest(
            name=f"agentnexus-openclaw",
            version="0.1.0",
            platform="openclaw",
            description="AgentNexus communication skill for OpenClaw",
            capabilities=["Communication", "Messaging"],
            actions=["invoke_skill", "query_status", "send_message", "get_profile"],
            install={
                "type": "openclaw_skill",
                "url": "https://github.com/anthropics/agentnexus-skills/openclaw",
            },
        )
        return manifest.to_dict()

    # ── Action Handlers ─────────────────────────────────────────────

    async def _handle_invoke_skill(self, request: dict) -> dict:
        """Invoke a skill on another Agent."""
        target_did = request.get("target_did")
        payload = request.get("payload", {})
        message_type = request.get("message_type", "skill_invoke")

        if not target_did:
            raise ValueError("Missing target_did")

        result = await self.router.route_message(
            from_did=self.agent_did,
            to_did=target_did,
            content=json.dumps(payload) if isinstance(payload, dict) else payload,
            message_type=message_type,
            protocol="nexus_v1",
        )
        return result

    async def _handle_query_status(self, request: dict) -> dict:
        """Query Agent status."""
        target_did = request.get("target_did")
        if not target_did:
            raise ValueError("Missing target_did")

        agent_info = await self.storage.get_agent(target_did)
        if not agent_info:
            return {"found": False}

        return {
            "found": True,
            "did": agent_info["did"],
            "profile": agent_info["profile"],
            "last_seen": agent_info["last_seen"],
        }

    async def _handle_send_message(self, request: dict) -> dict:
        """Send a direct message to another Agent."""
        target_did = request.get("target_did")
        content = request.get("content")

        if not target_did or content is None:
            raise ValueError("Missing target_did or content")

        result = await self.router.route_message(
            from_did=self.agent_did,
            to_did=target_did,
            content=content,
        )
        return result

    async def _handle_get_profile(self, request: dict) -> dict:
        """Get the bound Agent's profile."""
        agent_info = await self.storage.get_agent(self.agent_did)
        if not agent_info:
            return {"found": False}
        return {
            "found": True,
            "did": agent_info["did"],
            "profile": agent_info["profile"],
        }

    async def _handle_dispatch_intake(self, request: dict) -> dict:
        """
        D-SEC-08: OpenClaw Skill 触发 intake→dispatch 流程。
        请求: {action: "dispatch_intake", objective, required_roles, session_id?, preferred_playbook?}
        """
        objective = request.get("objective")
        required_roles = request.get("required_roles")
        if not objective or not required_roles:
            raise ValueError("Missing objective or required_roles for dispatch")

        if not self.owner_did:
            raise ValueError("OpenClaw adapter not bound to an owner_did")

        import time
        return await self._intake_and_dispatch(
            session_id=request.get("session_id", f"openclaw_{int(time.time())}"),
            owner_did=self.owner_did,
            actor_did=self.agent_did,
            objective=objective,
            required_roles=required_roles,
            source_channel="openclaw",
            adapter_id=f"openclaw_{self.agent_did[-12:]}",
            message_ref=request.get("message_ref", ""),
            preferred_playbook=request.get("preferred_playbook", ""),
            entry_mode=request.get("entry_mode", "owner_pre_authorized"),
        )
