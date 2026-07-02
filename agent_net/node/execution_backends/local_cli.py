"""LocalCLIBackend — execute stages via local CLI commands (argv list, no shell).

Design ref: docs/design/design-objective-loop-v1.1.md Sections 4.3, 6.1-6.3

Security: argv list only (no shell), command allowlist, output limits, timeout kill.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid

from agent_net.node.execution_backends.base import (
    ExecutionHandle,
    ExecutionResult,
)


# Patterns to detect obviously destructive commands in argv
_DESTRUCTIVE_PATTERNS = [
    re.compile(r"(?<![-\w])rm(?![-\w])"),       # Unix remove
    re.compile(r"(?<![-\w])del(?![-\w])"),      # Windows delete
    re.compile(r"(?<![-\w])rmdir(?![-\w])"),
    re.compile(r"(?<![-\w])format(?![-\w])"),
    re.compile(r"(?<![-\w])dd(?![-\w])"),
    re.compile(r">/dev/"),       # redirect to device
]

# Max bytes to scan for JSON extraction
_JSON_SCAN_LIMIT = 500_000
_CONTRACT = "agentnexus_json_v1"


def _short_summary(text: str, limit: int = 200) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:limit]
    return text.strip()[:limit]


def _is_destructive(argv: list[str]) -> bool:
    cmd_str = " ".join(argv).lower()
    for pat in _DESTRUCTIVE_PATTERNS:
        if pat.search(cmd_str):
            return True
    return False


def _extract_json(text: str) -> dict | None:
    """Extract the last JSON object from mixed text output. Returns None on failure."""
    candidates = []
    depth = 0
    start = -1
    limit = min(len(text), _JSON_SCAN_LIMIT)
    for i, ch in enumerate(text[:limit]):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidates.append(text[start:i + 1])
                start = -1

    for cand in reversed(candidates):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    return None


def _get_path(data: object, path: str) -> object:
    """Read a simple dotted path with optional [index] selectors from JSON data."""
    current = data
    for part in path.split("."):
        if current is None:
            return None
        while part:
            if "[" in part:
                key, rest = part.split("[", 1)
                if key:
                    if not isinstance(current, dict):
                        return None
                    current = current.get(key)
                idx_text, part = rest.split("]", 1)
                if not isinstance(current, list):
                    return None
                try:
                    current = current[int(idx_text)]
                except (ValueError, IndexError):
                    return None
                if part.startswith("."):
                    part = part[1:]
            else:
                if not isinstance(current, dict):
                    return None
                current = current.get(part)
                part = ""
    return current


def _extract_text_candidates(parsed: dict, paths: list[str]) -> list[str]:
    candidates: list[str] = []
    for path in paths:
        value = _get_path(parsed, path)
        if isinstance(value, str) and value.strip():
            candidates.append(value)

    payloads = parsed.get("payloads")
    if isinstance(payloads, list):
        for payload in payloads:
            if isinstance(payload, dict):
                text = payload.get("text")
                if isinstance(text, str) and text.strip():
                    candidates.append(text)
    return candidates


def _wrap_text_result(text: str, artifact_type: str = "TextArtifact") -> dict:
    return {
        "contract": _CONTRACT,
        "status": "completed",
        "artifact_type": artifact_type,
        "artifact_body": text,
        "summary": _short_summary(text) or "Text output captured",
        "evidence_refs": [],
    }


def _normalize_output(
    stdout: str,
    *,
    output_adapter: str = _CONTRACT,
    output_text_paths: list[str] | None = None,
    default_artifact_type: str = "TextArtifact",
) -> dict | None:
    """Normalize CLI-specific stdout into the AgentNexus result contract.

    Supported adapters:
    - agentnexus_json_v1: stdout already contains an AgentNexus JSON result.
    - openclaw_json: stdout is OpenClaw's JSON wrapper; unwrap assistant text.
    - json_text: stdout is a generic JSON wrapper; extract text paths.
    - text_artifact: wrap plain stdout as an artifact.
    """
    adapter = output_adapter or _CONTRACT

    if adapter == "text_artifact":
        return _wrap_text_result(stdout, default_artifact_type)

    parsed = _extract_json(stdout)
    if parsed is None:
        return None

    if adapter == _CONTRACT:
        return parsed

    paths = output_text_paths or []
    if adapter == "openclaw_json":
        paths = paths or [
            "meta.finalAssistantRawText",
            "meta.finalAssistantVisibleText",
            "payloads[0].text",
        ]
    elif adapter != "json_text":
        return parsed

    for candidate in _extract_text_candidates(parsed, paths):
        nested = _extract_json(candidate)
        if nested:
            return nested
        if candidate.strip():
            return _wrap_text_result(candidate, default_artifact_type)

    return None


class LocalCLIBackend:
    """Execute stages via local CLI subprocess (argv list, no shell)."""

    kind = "local_cli"

    def __init__(
        self,
        allowed_commands: set[str],
        default_timeout_sec: int = 1800,
        max_output_bytes: int = 1_048_576,
    ):
        self.allowed_commands = allowed_commands
        self.default_timeout_sec = default_timeout_sec
        self.max_output_bytes = max_output_bytes
        self._handles: dict[str, ExecutionHandle] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._retry_count: dict[str, int] = {}
        self._outputs: dict[str, tuple[str, str]] = {}

    # ── ExecutionBackend protocol ──────────────────────────────────────

    async def can_execute(self, worker: dict, stage: dict, objective: dict) -> bool:
        return worker.get("adapter", "") == "local_cli" or self.kind == "local_cli"

    async def start_execution(
        self,
        *,
        coordination_session_id: str,
        run_id: str,
        stage: str,
        worker_did: str,
        input_refs: list[dict],
        constraints: dict,
        command: list[str] | None = None,
    ) -> ExecutionHandle:
        """Validate and launch a CLI command as a subprocess.

        Supports constraints: timeout_sec, workdir, env
        """
        execution_id = f"exec_{uuid.uuid4().hex[:16]}"

        if command is None:
            h = ExecutionHandle(
                execution_id=execution_id, backend_kind=self.kind,
                worker_did=worker_did, stage=stage, status="blocked",
                metadata={"reason": "no command provided to start_execution"},
            )
            self._handles[execution_id] = h
            return h

        # Validate command
        exe = command[0]
        exe_name = os.path.basename(exe)
        allowed = {str(cmd).lower() for cmd in self.allowed_commands}
        allowed.update(os.path.basename(str(cmd)).lower() for cmd in self.allowed_commands)
        if exe_name.lower() not in allowed and exe.lower() not in allowed:
            h = ExecutionHandle(
                execution_id=execution_id, backend_kind=self.kind,
                worker_did=worker_did, stage=stage, status="blocked",
                metadata={
                    "reason": f"command '{exe_name}' not in allowed_commands",
                    "allowed": list(self.allowed_commands),
                },
            )
            self._handles[execution_id] = h
            return h

        # Check destructive command patterns
        if _is_destructive(command):
            h = ExecutionHandle(
                execution_id=execution_id, backend_kind=self.kind,
                worker_did=worker_did, stage=stage, status="blocked",
                metadata={
                    "reason": "destructive command pattern detected",
                    "gate": "destructive_command",
                },
            )
            self._handles[execution_id] = h
            return h

        timeout = constraints.get("timeout_sec", self.default_timeout_sec)
        workdir = constraints.get("workdir", None)
        env = constraints.get("env", None)

        try:
            kwargs = {}
            if workdir and os.path.isdir(workdir):
                kwargs["cwd"] = workdir
            if env and isinstance(env, dict):
                import os as _os
                merged = dict(_os.environ)
                merged.update(env)
                kwargs["env"] = merged
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **kwargs,
            )
        except FileNotFoundError:
            h = ExecutionHandle(
                execution_id=execution_id, backend_kind=self.kind,
                worker_did=worker_did, stage=stage, status="failed",
                metadata={"reason": f"executable not found: {exe}"},
            )
            self._handles[execution_id] = h
            return h
        except PermissionError:
            h = ExecutionHandle(
                execution_id=execution_id, backend_kind=self.kind,
                worker_did=worker_did, stage=stage, status="failed",
                metadata={"reason": f"permission denied: {exe}"},
            )
            self._handles[execution_id] = h
            return h

        handle_meta = {"command": command, "timeout_sec": timeout, "pid": proc.pid}
        if kwargs.get("cwd"):
            handle_meta["cwd"] = kwargs["cwd"]
        if kwargs.get("env"):
            handle_meta["env"] = kwargs["env"]
        for key in ("output_adapter", "output_text_paths", "artifact_type"):
            if key in constraints:
                handle_meta[key] = constraints[key]

        handle = ExecutionHandle(
            execution_id=execution_id, backend_kind=self.kind,
            worker_did=worker_did, stage=stage, status="running",
            metadata=handle_meta,
        )
        self._handles[execution_id] = handle
        self._processes[execution_id] = proc

        # Launch background task to wait for process
        task = asyncio.ensure_future(
            self._run_process(execution_id, proc, timeout)
        )
        self._tasks[execution_id] = task
        return handle

    async def poll_execution(self, handle: ExecutionHandle) -> ExecutionHandle:
        """Return current handle state. Background task updates status automatically."""
        current = self._handles.get(handle.execution_id)
        if current:
            return current
        return handle

    async def collect_result(self, handle: ExecutionHandle) -> ExecutionResult:
        """Wait for background task to finish, then parse output."""
        eid = handle.execution_id
        current = self._handles.get(eid, handle)

        # If already blocked/failed at start, return early
        if current.status in ("blocked", "failed", "cancelled"):
            meta = current.metadata or {}
            return ExecutionResult(
                execution_id=eid,
                status=current.status if current.status != "cancelled" else "blocked",
                artifact_type="",
                artifact_body="",
                summary=meta.get("reason", current.status),
                evidence_refs=[],
                human_decision_request=(
                    {"gate": meta.get("gate", "low_confidence"),
                     "question": meta.get("reason", "")}
                    if meta.get("reason") else None
                ),
            )

        # Wait for the background task to complete
        task = self._tasks.get(eid)
        if task and not task.done():
            try:
                await asyncio.wait_for(task, timeout=current.metadata.get("timeout_sec", 30) + 10)
            except asyncio.TimeoutError:
                pass

        # Re-read handle after task completion
        current = self._handles.get(eid, handle)
        meta = current.metadata or {}

        if current.status == "timed_out":
            return ExecutionResult(
                execution_id=eid, status="blocked",
                artifact_type="", artifact_body="",
                summary="Execution timed out",
                evidence_refs=[],
                human_decision_request={
                    "gate": "max_retry_exceeded",
                    "question": "Execution timed out. Retry or abort?",
                },
                raw_output_ref=meta.get("stdout", ""),
            )

        if current.status == "failed":
            return ExecutionResult(
                execution_id=eid, status="failed",
                artifact_type="", artifact_body="",
                summary=f"Process exited with code {meta.get('returncode', '?')}",
                evidence_refs=[],
                raw_output_ref=meta.get("stdout", ""),
            )

        # Parse worker output
        stdout = meta.get("stdout", "")
        parsed = _normalize_output(
            stdout,
            output_adapter=meta.get("output_adapter", _CONTRACT),
            output_text_paths=meta.get("output_text_paths"),
            default_artifact_type=meta.get("artifact_type", "TextArtifact"),
        )

        if parsed:
            contract = parsed.get("contract", "")
            if contract != _CONTRACT:
                import logging
                logging.getLogger("agentnexus").warning(
                    f"Worker {current.worker_did} output missing {_CONTRACT} "
                    f"contract (got: {contract or 'none'}). This is required for L0-Ready."
                )
            return ExecutionResult(
                execution_id=eid,
                status=parsed.get("status", "completed"),
                artifact_type=parsed.get("artifact_type", ""),
                artifact_body=parsed.get("artifact_body", ""),
                summary=parsed.get("summary", ""),
                evidence_refs=parsed.get("evidence_refs", []),
                human_decision_request=parsed.get("human_decision_request"),
                raw_output_ref=stdout,
            )

        # Parse failed — retry once: re-execute the same command to get fresh output
        if self._retry_count.get(eid, 0) == 0:
            self._retry_count[eid] = 1
            retry_proc = None
            try:
                cmd = (current.metadata or {}).get("command", [])
                if cmd:
                    # Inherit cwd and timeout from the first execution
                    retry_meta = current.metadata or {}
                    retry_timeout = retry_meta.get("timeout_sec", self.default_timeout_sec)
                    retry_kwargs: dict = {"stdout": asyncio.subprocess.PIPE,
                                          "stderr": asyncio.subprocess.PIPE}
                    if retry_meta.get("cwd"):
                        retry_kwargs["cwd"] = retry_meta["cwd"]
                    if retry_meta.get("env"):
                        import os as _os
                        merged = dict(_os.environ)
                        merged.update(retry_meta["env"])
                        retry_kwargs["env"] = merged

                    retry_proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        **retry_kwargs,
                    )
                    retry_stdout, retry_stderr = await asyncio.wait_for(
                        retry_proc.communicate(), timeout=retry_timeout
                    )
                    retry_stdout_str = retry_stdout.decode("utf-8", errors="replace")[:self.max_output_bytes]
                    # Try parsing the fresh output
                    self._outputs[eid] = (retry_stdout_str, retry_stderr.decode("utf-8", errors="replace")[:self.max_output_bytes])
                    parsed = _normalize_output(
                        retry_stdout_str,
                        output_adapter=retry_meta.get("output_adapter", _CONTRACT),
                        output_text_paths=retry_meta.get("output_text_paths"),
                        default_artifact_type=retry_meta.get("artifact_type", "TextArtifact"),
                    )
                    if parsed:
                        contract = parsed.get("contract", "")
                        if contract != _CONTRACT:
                            import logging
                            logging.getLogger("agentnexus").warning(
                                f"Worker {current.worker_did} output missing {_CONTRACT} "
                                f"contract (got: {contract or 'none'}). This is required for L0-Ready."
                            )
                        return ExecutionResult(
                            execution_id=eid,
                            status=parsed.get("status", "completed"),
                            artifact_type=parsed.get("artifact_type", ""),
                            artifact_body=parsed.get("artifact_body", ""),
                            summary=parsed.get("summary", ""),
                            evidence_refs=parsed.get("evidence_refs", []),
                            human_decision_request=parsed.get("human_decision_request"),
                            raw_output_ref=retry_stdout_str,
                        )
            except Exception as _retry_err:
                import logging
                logging.getLogger("agentnexus").warning(f"JSON retry failed: {_retry_err}")
            finally:
                if retry_proc is not None and retry_proc.returncode is None:
                    await self._kill_process(retry_proc)
                    try:
                        await retry_proc.communicate()
                    except Exception:
                        pass

        # Parse failed after retry → blocked
        return ExecutionResult(
            execution_id=eid, status="blocked",
            artifact_type="", artifact_body="",
            summary="Worker output could not be parsed as valid JSON after retry",
            evidence_refs=[],
            human_decision_request={
                "gate": "low_confidence",
                "question": "Worker output could not be parsed as valid JSON.",
            },
            raw_output_ref=stdout,
        )

    async def cancel_execution(self, handle: ExecutionHandle, reason: str) -> None:
        """Cancel the running task and kill its subprocess."""
        eid = handle.execution_id

        task = self._tasks.get(eid)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        proc = self._processes.get(eid)
        if proc is not None and proc.returncode is None:
            await self._kill_process(proc)
            try:
                await proc.communicate()
            except Exception:
                pass
        self._processes.pop(eid, None)

        current = self._handles.get(eid, handle)
        current.status = "cancelled"
        current.metadata = (current.metadata or {}) | {"reason": reason}
        self._handles[eid] = current

    # ── Internal helpers ──────────────────────────────────────────────

    async def _run_process(
        self,
        execution_id: str,
        proc: asyncio.subprocess.Process,
        timeout_sec: float,
    ) -> None:
        """Background task: wait for process, handle timeout, store output."""
        try:
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_sec
                )
            except asyncio.CancelledError:
                await self._kill_process(proc)
                try:
                    await proc.communicate()
                except Exception:
                    pass
                raise
            except asyncio.TimeoutError:
                await self._kill_process(proc)
                try:
                    stdout, stderr = await proc.communicate()
                except Exception:
                    stdout, stderr = b"", b""
                handle = self._handles.get(execution_id)
                if handle:
                    stdout_str = stdout.decode("utf-8", errors="replace")[:self.max_output_bytes]
                    stderr_str = stderr.decode("utf-8", errors="replace")[:self.max_output_bytes]
                    handle.status = "timed_out"
                    handle.metadata = (handle.metadata or {}) | {
                        "stdout": stdout_str, "stderr": stderr_str,
                        "reason": "timeout exceeded",
                    }
                    self._handles[execution_id] = handle
                return

            handle = self._handles.get(execution_id)
            if handle is None:
                return

            stdout_str = stdout.decode("utf-8", errors="replace")[:self.max_output_bytes]
            stderr_str = stderr.decode("utf-8", errors="replace")[:self.max_output_bytes]

            handle.status = "completed" if proc.returncode == 0 else "failed"
            handle.metadata = (handle.metadata or {}) | {
                "stdout": stdout_str,
                "stderr": stderr_str,
                "returncode": proc.returncode,
            }
            self._handles[execution_id] = handle
        finally:
            self._processes.pop(execution_id, None)

    @staticmethod
    async def _kill_process(proc: asyncio.subprocess.Process) -> None:
        """Kill process tree."""
        if proc.returncode is not None:
            return
        if os.name == "nt":
            try:
                kill_proc = await asyncio.create_subprocess_exec(
                    "taskkill", "/PID", str(proc.pid), "/T", "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await kill_proc.wait()
            except Exception:
                pass
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
