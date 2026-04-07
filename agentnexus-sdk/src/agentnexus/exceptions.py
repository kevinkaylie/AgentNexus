"""
AgentNexus SDK Exceptions
"""


class AgentNexusError(Exception):
    """Base exception for all AgentNexus SDK errors."""
    pass


class DaemonNotFoundError(AgentNexusError):
    """Daemon is not running or unreachable.

    Resolution: Run `python main.py node start` to start the Daemon.
    """
    def __init__(self, message: str = "Daemon not found"):
        super().__init__(message)
        self.resolution = "Run 'python main.py node start' to start the Daemon"


class AuthenticationError(AgentNexusError):
    """Token is invalid or missing."""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)
        self.resolution = "Check daemon_token.txt or set AGENTNEXUS_TOKEN environment variable"


class AgentNotFoundError(AgentNexusError):
    """DID does not exist."""
    def __init__(self, did: str):
        super().__init__(f"Agent not found: {did}")
        self.did = did


class DIDNotFoundError(AgentNexusError):
    """DID not found in Daemon (for connect(did=...) with unregistered DID)."""
    def __init__(self, did: str):
        super().__init__(f"DID not registered in Daemon: {did}")
        self.did = did


class MessageDeliveryError(AgentNexusError):
    """Message delivery failed."""
    def __init__(self, reason: str, method: str | None = None):
        super().__init__(f"Message delivery failed: {reason}")
        self.reason = reason
        self.method = method


class InvalidActionError(AgentNexusError):
    """Action Layer message format is invalid."""
    def __init__(self, message_type: str, errors: dict):
        super().__init__(f"Invalid action '{message_type}': {errors}")
        self.message_type = message_type
        self.errors = errors


class TokenPermissionWarning(Warning):
    """Token file has insecure permissions."""
    def __init__(self, path: str, current_mode: int):
        super().__init__(f"Token file {path} has permissions {oct(current_mode)}, recommend 0o600")
        self.path = path
        self.current_mode = current_mode
