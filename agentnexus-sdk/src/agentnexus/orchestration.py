"""Convenience aggregation for orchestration SDK clients."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import AgentNexusClient


class OrchestrationClient:
    """A grouped facade for users who prefer nexus.orchestration.*."""

    def __init__(self, client: "AgentNexusClient"):
        self.owner = client.owner
        self.team = client.team
        self.secretary = client.secretary
        self.runs = client.runs
        self.worker = client.worker
