"""Worker runtime helpers for stage-based AgentNexus orchestration."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

from .actions import ActionMessage
from .enclave import VaultProxy

if TYPE_CHECKING:
    from .client import AgentNexusClient


@dataclass
class StageContext:
    task_id: str
    run_id: str
    enclave_id: str
    stage_name: str
    role: str
    from_did: str
    assigned_did: str
    context_snapshot: dict = field(default_factory=dict)
    vault: VaultProxy | None = None
    _client: "AgentNexusClient | None" = None

    async def deliver(
        self,
        *,
        kind: str,
        key: str,
        value: str | None = None,
        summary: str = "",
        status: str = "completed",
    ) -> None:
        if not self._client:
            raise RuntimeError("StageContext is not bound to a client")
        if value is not None:
            if not self.vault:
                raise RuntimeError("StageContext has no vault proxy")
            await self.vault.put(key, value, message=summary)
        artifact_ref = {"enclave_id": self.enclave_id, "key": key, "kind": kind, "summary": summary}
        await self._client.notify_state(
            to_did=self.from_did,
            task_id=self.task_id,
            status=status,
            output_ref=artifact_ref,
        )

    async def reject(self, reason: str) -> None:
        if not self._client:
            raise RuntimeError("StageContext is not bound to a client")
        await self._client.notify_state(
            to_did=self.from_did,
            task_id=self.task_id,
            status="rejected",
            reason=reason,
        )


class WorkerRuntime:
    """Dispatch task_propose messages with run/stage metadata into StageContext callbacks."""

    def __init__(self, client: "AgentNexusClient"):
        self._client = client
        self._stage_callbacks: dict[str, list[Callable]] = {}

    def on_stage(self, role: str | None = None):
        """Register a stage callback. Use role=None or "*" to receive all stages."""
        key = role or "*"

        def decorator(callback: Callable) -> Callable:
            self._stage_callbacks.setdefault(key, []).append(callback)
            return callback

        return decorator

    async def handle_task_propose(self, action: ActionMessage) -> bool:
        content = action.content or {}
        required = ("task_id", "run_id", "enclave_id", "stage_name")
        if not all(content.get(k) for k in required):
            return False

        role = content.get("role") or content.get("stage_role") or content.get("stage_name", "")
        callbacks = list(self._stage_callbacks.get(role, [])) + list(self._stage_callbacks.get("*", []))
        if not callbacks:
            return False

        ctx = StageContext(
            task_id=content["task_id"],
            run_id=content["run_id"],
            enclave_id=content["enclave_id"],
            stage_name=content["stage_name"],
            role=role,
            from_did=action.from_did,
            assigned_did=self._client.agent_info.did,
            context_snapshot=content.get("context_snapshot", content.get("context", {})) or {},
            vault=VaultProxy(self._client, content["enclave_id"]),
            _client=self._client,
        )

        for cb in callbacks:
            result = cb(ctx)
            if asyncio.iscoroutine(result):
                await result
        return True
