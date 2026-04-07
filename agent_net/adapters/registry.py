"""
Adapter Registry

Manages platform adapter registration and lookup.
"""
from typing import Dict, Optional, Type
from .base import PlatformAdapter


class AdapterRegistry:
    """
    Registry for platform adapters.

    Similar pattern to DID method handler registry (ADR-009).
    """

    _adapters: Dict[str, PlatformAdapter] = {}

    @classmethod
    def register(cls, adapter: PlatformAdapter) -> None:
        """
        Register a platform adapter.

        Args:
            adapter: PlatformAdapter instance
        """
        cls._adapters[adapter.platform] = adapter

    @classmethod
    def unregister(cls, platform: str) -> bool:
        """
        Unregister a platform adapter.

        Args:
            platform: Platform name

        Returns:
            True if adapter was removed, False if not found
        """
        if platform in cls._adapters:
            del cls._adapters[platform]
            return True
        return False

    @classmethod
    def get(cls, platform: str) -> Optional[PlatformAdapter]:
        """
        Get adapter by platform name.

        Args:
            platform: Platform name

        Returns:
            PlatformAdapter instance or None
        """
        return cls._adapters.get(platform)

    @classmethod
    def list(cls) -> Dict[str, PlatformAdapter]:
        """
        List all registered adapters.

        Returns:
            Dict of platform -> adapter
        """
        return dict(cls._adapters)

    @classmethod
    def reset(cls) -> None:
        """Clear all registered adapters (for testing)."""
        cls._adapters.clear()


# Convenience functions
def register_adapter(adapter: PlatformAdapter) -> None:
    """Register a platform adapter."""
    AdapterRegistry.register(adapter)


def get_adapter(platform: str) -> Optional[PlatformAdapter]:
    """Get adapter by platform name."""
    return AdapterRegistry.get(platform)


def list_adapters() -> Dict[str, PlatformAdapter]:
    """List all registered adapters."""
    return AdapterRegistry.list()
