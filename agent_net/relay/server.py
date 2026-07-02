"""Relay server compatibility aggregator."""
from . import server_common as _common
from .server_common import *  # noqa: F401,F403
from .relay_registry import *  # noqa: F401,F403
from .relay_federation import *  # noqa: F401,F403
from .relay_identity import *  # noqa: F401,F403
from .relay_anpn import *  # noqa: F401,F403
from .relay_meeet import *  # noqa: F401,F403
from agent_net.common import constants as _constants

# Public module attributes retained for tests and embedders.
app = _common.app
RELAY_HOST = _constants.RELAY_HOST
RELAY_IDENTITY_FILE = _constants.RELAY_IDENTITY_FILE


def init_relay_identity():
    """Initialize identity while preserving the legacy patch surface."""
    for name in ("RELAY_HOST", "RELAY_IDENTITY_FILE"):
        if name in globals():
            setattr(_common, name, globals()[name])
    _common.init_relay_identity()
    for name in (
        "_relay_signing_key",
        "_relay_did",
        "_relay_did_document",
        "_relay_host",
    ):
        globals()[name] = getattr(_common, name)
