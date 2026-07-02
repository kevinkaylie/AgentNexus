"""
pytest configuration — shared fixtures and warning filters for AgentNexus tests.
"""
import gc
import warnings

import pytest

# ── Resource-leak guard: promote known leak categories to errors ─────────────
# These catch regressions that otherwise only show as silent warnings in CI.
#
#   aiosqlite worker thread callbacks after event-loop close
#   Proactor transport unclosed on Windows
#   Unclosed files / sockets
#
warnings.filterwarnings("error", category=ResourceWarning, message=r".*unclosed.*")
warnings.filterwarnings(
    "error",
    category=pytest.PytestUnhandledThreadExceptionWarning,
    message=r".*(_connection_worker_thread|Event loop is closed).*",
)


@pytest.fixture(scope="session", autouse=True)
def _gc_aiosqlite_before_loop_close():
    """Force garbage-collect aiosqlite connections before the event loop exits.

    aiosqlite worker threads use ``call_soon_threadsafe`` to dispatch their own
    cleanup.  On Windows ProactorEventLoop this callback can arrive *after* the
    loop has already stopped, producing a ``RuntimeError: Event loop is closed``
    inside the worker thread.  Running a full GC pass while the loop is still
    alive gives those callbacks a chance to land.
    """
    yield
    gc.collect()
