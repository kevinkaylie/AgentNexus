"""ExecutionBackend base types — ExecutionHandle, ExecutionResult, Protocol."""
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ExecutionHandle:
    """Handle returned by start_execution, used for poll/collect/cancel."""
    execution_id: str
    backend_kind: str
    worker_did: str
    stage: str
    status: str  # pending | running | completed | failed | blocked | timed_out | cancelled
    external_session_id: str = ""
    lease_expires_at: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class ExecutionResult:
    """Structured result collected from a completed/cancelled execution."""
    execution_id: str
    status: str  # completed | changes_requested | failed | blocked
    artifact_type: str
    artifact_body: str
    summary: str
    evidence_refs: list[str] = field(default_factory=list)
    human_decision_request: dict[str, Any] | None = None
    raw_output_ref: str = ""


class ExecutionBackend(Protocol):
    """Protocol for execution backends.

    An ExecutionBackend handles "how to execute" a stage on a specific runtime.
    It does NOT decide what stage to run or whether the objective is complete.
    """
    kind: str

    async def can_execute(self, worker: dict, stage: dict, objective: dict) -> bool: ...

    async def start_execution(
        self,
        *,
        coordination_session_id: str,
        run_id: str,
        stage: str,
        worker_did: str,
        input_refs: list[dict],
        constraints: dict,
    ) -> ExecutionHandle: ...

    async def poll_execution(self, handle: ExecutionHandle) -> ExecutionHandle: ...

    async def collect_result(self, handle: ExecutionHandle) -> ExecutionResult: ...

    async def cancel_execution(self, handle: ExecutionHandle, reason: str) -> None: ...
