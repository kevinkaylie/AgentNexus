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
