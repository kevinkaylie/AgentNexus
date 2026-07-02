"""Shared database configuration for persistence modules."""
from __future__ import annotations

from pathlib import Path

import aiosqlite


DEFAULT_DB_PATH = Path(__file__).parents[2] / "data" / "agent_net.db"


def get_db_path() -> Path:
    """Return the compatibility facade's current database path."""
    from agent_net import storage

    return Path(storage.DB_PATH)


def connect() -> aiosqlite.Connection:
    """Create a connection against the currently configured database path."""
    return aiosqlite.connect(get_db_path())
