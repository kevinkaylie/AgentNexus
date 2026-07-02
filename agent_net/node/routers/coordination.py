"""Coordination API router aggregator.

Endpoint implementations are split by workflow domain while retaining the
original module and router import contract.
"""
from .coordination_common import router
from . import coordination_sessions as _sessions  # noqa: F401
from . import coordination_delegations as _delegations  # noqa: F401
from . import coordination_records as _records  # noqa: F401
from . import coordination_coding as _coding  # noqa: F401
from . import coordination_executions as _executions  # noqa: F401

__all__ = ["router"]