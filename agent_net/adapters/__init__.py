"""
AgentNexus Platform Adapters

Provides adapters for external platforms (OpenClaw, Webhook, etc.) to integrate
with AgentNexus network.

Based on ADR-010: Platform Adapter & Skill Registry Architecture
"""
from .base import PlatformAdapter, SkillManifest
from .registry import AdapterRegistry, register_adapter, get_adapter, list_adapters

__all__ = [
    "PlatformAdapter",
    "SkillManifest",
    "AdapterRegistry",
    "register_adapter",
    "get_adapter",
    "list_adapters",
]
