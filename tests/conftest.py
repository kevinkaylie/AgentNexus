"""
pytest configuration — shared fixtures and warning filters for AgentNexus tests.
"""
import gc
import os
import pathlib
import shutil
import tempfile
import uuid
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


def _pytest_tmpdir_usable() -> bool:
    """pytest 的 tmpdir 插件以 mode 0o700 创建基目录后**立即扫描**它。

    在受限文件沙箱（如 Windows 下的受限令牌/sandbox）中，`os.mkdir(path, 0o700)`
    建出的目录对该进程不可扫描，pytest 会在 ``tmp_path`` setup 阶段直接
    `PermissionError [WinError 5]`，导致**所有**使用 tmp_path 的测试报错。
    默认权限（0o777）与普通 mkdir 不受影响。

    这里做一次探针检测：只有确认本环境不可用时才覆盖 ``tmp_path``，
    因此在正常 CI（Linux/常规 Windows）上行为与 pytest 自带实现保持一致。
    """
    probe = os.path.join(tempfile.gettempdir(), f"_agentnexus_tmp_probe_{os.getpid()}")
    try:
        os.mkdir(probe, 0o700)
    except OSError:
        return False
    try:
        os.listdir(probe)
        return True
    except OSError:
        return False
    finally:
        shutil.rmtree(probe, ignore_errors=True)


if not _pytest_tmpdir_usable():

    @pytest.fixture
    def tmp_path(request):
        """沙箱兼容版 tmp_path：语义与 pytest 相同（每个用例一个全新空目录）。

        注意：**不能**用同样的方式兜底 ``tempfile``——子进程与工作区外临时目录
        在本沙箱下同样受限，而 pytest 的 tmpdir 是唯一影响面大、且可安全替换的点。
        """
        base = pathlib.Path(__file__).resolve().parents[1] / ".pytest_scratch"
        base.mkdir(exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in request.node.name)[:48]
        directory = base / f"{safe}_{uuid.uuid4().hex[:8]}"
        directory.mkdir(parents=True, exist_ok=True)
        yield directory
        shutil.rmtree(directory, ignore_errors=True)


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


# ── 环境能力探针：能力缺失时**跳过**而不是让测试失败 ────────────────────────
#
# 背景（2026-09-21 评审 S4）：此前把"受限沙箱下必然失败"的 25 个用例登记进
# `tests/full_suite_baseline.json` 当作环境性失败。评审在**不受限**环境跑全量得到
# 679 passed / 0 failed，证明这些用例本身是好的——登记成失败等于让基线长期带着
# 一批"实际上能过"的条目，也掩盖了真实回归。
#
# 正确做法：测试自己探测能力，能力不可用时显式 skip（带原因），于是
#   - 正常环境：全部执行 → 0 failed；
#   - 受限环境：显式 skip → 0 failed；
# 两种环境下基线都可以是**空**的，门禁只对"未登记失败"严格。

#: 需要真实子进程的测试文件（沙箱禁止 create_subprocess_exec 时跳过）
_SUBPROCESS_FILES = {
    "tests/test_local_cli_backend.py",
    "tests/test_local_runner.py",
    "tests/test_runner_loop.py",
    "tests/test_vault_git.py",
}

#: 需要在工作区外临时目录/家目录读写文件的测试文件
_OUTSIDE_TMPDIR_FILES = {
    "tests/test_relay_did_web.py",
}

_PROBE_CACHE: dict = {}


def _can_spawn_subprocess() -> bool:
    """探针必须用被测代码**实际使用**的 API。

    受限沙箱下 ``asyncio.create_subprocess_exec`` 抛 ``PermissionError [WinError 5]``，
    而同步 ``subprocess.run`` 可能仍然可用；只探后者会漏判（实测过一次）。
    """
    if "spawn" not in _PROBE_CACHE:
        import asyncio
        import sys

        async def _probe() -> bool:
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-c", "pass",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                return True
            except Exception:
                return False

        try:
            _PROBE_CACHE["spawn"] = asyncio.run(_probe())
        except Exception:
            _PROBE_CACHE["spawn"] = False
    return _PROBE_CACHE["spawn"]


def _can_use_outside_tmpdir() -> bool:
    if "outside" not in _PROBE_CACHE:
        directory = None
        try:
            directory = tempfile.mkdtemp(prefix="_agentnexus_outside_probe_")
            path = os.path.join(directory, "probe.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("ok")
            with open(path, "r", encoding="utf-8") as handle:
                handle.read()
            os.listdir(directory)
            _PROBE_CACHE["outside"] = True
        except OSError:
            _PROBE_CACHE["outside"] = False
        finally:
            if directory:
                shutil.rmtree(directory, ignore_errors=True)
    return _PROBE_CACHE["outside"]


def pytest_collection_modifyitems(config, items):
    """按环境能力跳过依赖外部能力的用例（原因写明，便于区分"未跑"与"通过"）。

    匹配用 ``item.nodeid`` 前缀（``tests/test_x.py::...``），而不是 ``module.__name__``：
    ``tests/`` 没有 ``__init__.py``，模块名可能被 pytest 改写，用 nodeid 才稳定。
    """
    if not _can_spawn_subprocess():
        reason = "受限环境：禁止创建子进程（asyncio.create_subprocess_exec → PermissionError）"
        for item in items:
            if item.nodeid.split("::", 1)[0] in _SUBPROCESS_FILES:
                item.add_marker(pytest.mark.skip(reason=reason))
    if not _can_use_outside_tmpdir():
        reason = "受限环境：工作区外临时目录/家目录不可读写（PermissionError）"
        for item in items:
            if item.nodeid.split("::", 1)[0] in _OUTSIDE_TMPDIR_FILES:
                item.add_marker(pytest.mark.skip(reason=reason))
