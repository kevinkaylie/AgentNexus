"""
AgentNexus SDK Discovery Module

Handles automatic discovery of Daemon URL and Token.
"""
import os
import warnings
from pathlib import Path
from typing import Optional

from .exceptions import DaemonNotFoundError, TokenPermissionWarning

# Default Daemon URL
DEFAULT_DAEMON_URL = "http://localhost:8765"

# Token file paths
USER_TOKEN_DIR = Path.home() / ".agentnexus"
USER_TOKEN_FILE = USER_TOKEN_DIR / "daemon_token.txt"
PROJECT_TOKEN_FILE = Path(__file__).parent.parent.parent / "data" / "daemon_token.txt"


def discover_daemon_url(
    daemon_url: Optional[str] = None,
) -> str:
    """
    Discover Daemon URL with priority:
    1. Explicit parameter
    2. Environment variable AGENTNEXUS_DAEMON_URL
    3. Default http://localhost:8765

    Returns:
        Daemon URL string

    Raises:
        DaemonNotFoundError: If Daemon is not reachable
    """
    # Priority 1: Explicit parameter
    if daemon_url:
        return daemon_url

    # Priority 2: Environment variable
    env_url = os.environ.get("AGENTNEXUS_DAEMON_URL")
    if env_url:
        return env_url

    # Priority 3: Default
    return DEFAULT_DAEMON_URL


def discover_token(
    token: Optional[str] = None,
    check_permissions: bool = True,
) -> Optional[str]:
    """
    Discover authentication token with priority:
    1. Explicit parameter
    2. Environment variable AGENTNEXUS_TOKEN
    3. User directory ~/.agentnexus/daemon_token.txt
    4. Project directory data/daemon_token.txt

    Args:
        token: Explicit token parameter
        check_permissions: If True, warn if token file permissions are not 0o600

    Returns:
        Token string, or None if not found
    """
    # Priority 1: Explicit parameter
    if token:
        return token

    # Priority 2: Environment variable
    env_token = os.environ.get("AGENTNEXUS_TOKEN")
    if env_token:
        return env_token

    # Priority 3: User directory
    if USER_TOKEN_FILE.exists():
        _check_file_permissions(USER_TOKEN_FILE, check_permissions)
        return USER_TOKEN_FILE.read_text().strip()

    # Priority 4: Project directory
    if PROJECT_TOKEN_FILE.exists():
        _check_file_permissions(PROJECT_TOKEN_FILE, check_permissions)
        return PROJECT_TOKEN_FILE.read_text().strip()

    return None


def _check_file_permissions(path: Path, check: bool) -> None:
    """Check if file permissions are secure (0o600)."""
    if not check:
        return

    try:
        mode = path.stat().st_mode & 0o777
        if mode != 0o600:
            warnings.warn(
                f"Token file {path} has permissions {oct(mode)}, recommend chmod 600",
                TokenPermissionWarning,
                stacklevel=3,
            )
    except OSError:
        pass  # Can't check permissions on this platform


async def check_daemon_health(daemon_url: str) -> bool:
    """
    Check if Daemon is healthy and reachable.

    Returns:
        True if Daemon is healthy, False otherwise
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{daemon_url}/health",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


async def require_daemon(daemon_url: str) -> None:
    """
    Require Daemon to be reachable.

    Raises:
        DaemonNotFoundError: If Daemon is not reachable
    """
    if not await check_daemon_health(daemon_url):
        raise DaemonNotFoundError(
            f"Daemon not reachable at {daemon_url}. "
            "Run 'python main.py node start' to start the Daemon."
        )
