"""
Platform Adapter Base Class

Abstract base class for platform adapters that bridge external platforms
to AgentNexus SDK calls.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


@dataclass
class SkillManifest:
    """
    Standardized Skill description for discovery and installation.

    Attributes:
        name: Skill identifier (e.g., "translate", "agentnexus-comm")
        version: Semantic version string
        platform: Platform type ("openclaw", "webhook", "native")
        description: Human-readable description
        capabilities: High-level capability tags for discovery
        actions: Specific callable operations for execution
        install: Installation specification
        auth: Authentication requirements (optional)
    """
    name: str
    version: str
    platform: str
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    install: Optional[Dict[str, Any]] = None
    auth: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "name": self.name,
            "version": self.version,
            "platform": self.platform,
            "description": self.description,
            "capabilities": self.capabilities,
            "actions": self.actions,
        }
        if self.install:
            result["install"] = self.install
        if self.auth:
            result["auth"] = self.auth
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "SkillManifest":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            version=data["version"],
            platform=data["platform"],
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            actions=data.get("actions", []),
            install=data.get("install"),
            auth=data.get("auth"),
        )


class PlatformAdapter(ABC):
    """
    Abstract base class for platform adapters.

    Platform adapters convert external platform protocols to AgentNexus SDK calls
    and vice versa. Each adapter handles a specific platform (OpenClaw, Webhook, etc.)

    Usage:
        class MyAdapter(PlatformAdapter):
            platform = "myplatform"

            async def inbound(self, request: dict) -> dict:
                # Convert platform request to SDK operation
                ...

            async def outbound(self, message: dict) -> dict:
                # Push SDK event to platform
                ...

            def skill_manifest(self) -> dict:
                # Return skill description
                ...
    """

    platform: str  # Override in subclass

    @abstractmethod
    async def inbound(self, request: dict) -> dict:
        """
        Handle external platform → AgentNexus conversion.

        Args:
            request: Platform-specific request payload

        Returns:
            Response to send back to platform
        """
        ...

    @abstractmethod
    async def outbound(self, message: dict) -> dict:
        """
        Handle AgentNexus → external platform push.

        Args:
            message: AgentNexus message/event

        Returns:
            Platform response or confirmation
        """
        ...

    @abstractmethod
    def skill_manifest(self) -> dict:
        """
        Return the skill manifest for this adapter.

        Returns:
            SkillManifest as dictionary
        """
        ...

    def close(self) -> None:
        """
        Clean up resources (optional override).

        Called when the adapter is being shut down.
        """
        pass

    async def _intake_and_dispatch(
        self,
        session_id: str,
        owner_did: str,
        actor_did: str,
        objective: str,
        required_roles: list[str],
        source_channel: str,
        adapter_id: str,
        message_ref: str = "",
        preferred_playbook: str = "",
        entry_mode: str = "owner_pre_authorized",
        daemon_url: str = "http://localhost:8765",
        token: str = "",
    ) -> dict:
        """
        D-SEC-08: 统一 Intake 请求格式，交给秘书的 /secretary/dispatch。

        所有适配器通过此方法将外部入口消息转换为统一的 intake 格式，
        然后转发到 /secretary/dispatch 启动团队协作流程。
        """
        import aiohttp
        import os

        # 自动读取 daemon token（调用方未显式传入时）
        if not token:
            from agent_net.common.constants import DAEMON_TOKEN_FILE
            if os.path.exists(DAEMON_TOKEN_FILE):
                with open(DAEMON_TOKEN_FILE) as f:
                    token = f.read().strip()
            # 备用路径 ~/.agentnexus/daemon_token.txt
            if not token:
                alt = os.path.expanduser("~/.agentnexus/daemon_token.txt")
                if os.path.exists(alt):
                    with open(alt) as f:
                        token = f.read().strip()

        intake_payload = {
            "session_id": session_id,
            "owner_did": owner_did,
            "actor_did": actor_did,
            "objective": objective,
            "required_roles": required_roles,
            "preferred_playbook": preferred_playbook,
            "source": {
                "channel": source_channel,
                "adapter_id": adapter_id,
                "message_ref": message_ref,
            },
            "entry_mode": entry_mode,
        }

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{daemon_url}/secretary/dispatch",
                json=intake_payload,
                headers=headers,
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return {
                        "status": "accepted",
                        "run_id": result.get("run_id", ""),
                        "session_id": session_id,
                        "enclave_id": result.get("enclave_id", ""),
                    }
                else:
                    text = await resp.text()
                    return {
                        "status": "dispatch_failed",
                        "error": text,
                        "session_id": session_id,
                    }
