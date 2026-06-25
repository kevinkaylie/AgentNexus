"""Compatibility facade for AgentNexus persistence APIs.

Implementations are grouped by domain under ``agent_net.persistence``. The
legacy import surface and mutable ``DB_PATH`` remain available for callers and
tests.
"""
from agent_net.persistence.context import DEFAULT_DB_PATH

DB_PATH = DEFAULT_DB_PATH

from agent_net.persistence.core import *  # noqa: E402,F401,F403
from agent_net.persistence.schemas import *  # noqa: E402,F401,F403
from agent_net.persistence.governance import *  # noqa: E402,F401,F403
from agent_net.persistence.enclave import *  # noqa: E402,F401,F403
from agent_net.persistence.coordination import *  # noqa: E402,F401,F403