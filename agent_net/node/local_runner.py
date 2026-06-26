"""Local Runner — YAML config, worker matching, stage execution.

Design ref: docs/design/design-objective-loop-v1.1.md Sections 6, 11

The local runner is a sidecar that:
1. Loads YAML config with worker definitions
2. Polls the Loop Engine for next_action
3. Executes stages via LocalCLIBackend
4. Submits results back to the daemon
"""
from __future__ import annotations

import os
import pathlib
from copy import deepcopy
from typing import Any

import yaml

from agent_net.node.execution_backends.base import ExecutionResult
from agent_net.node.execution_backends.local_cli import LocalCLIBackend

# ── Defaults ─────────────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "daemon_url": "http://127.0.0.1:8765",
    "secretary_agent": "",
    "owner_did": "",
    "poll_interval_sec": 2,
    "defaults": {
        "workdir": str(pathlib.Path.cwd()),
        "timeout_sec": 1800,
        "max_retries_per_stage": 2,
        "max_total_executions": 30,       # NEW
        "max_wall_clock_sec": 14400,      # NEW
        "require_final_acceptance": False, # NEW
    },
    "workers": {},
}


# ── Config loading ───────────────────────────────────────────────────

def load_runner_config(path: str) -> dict[str, Any]:
    """Load and validate a local-runner YAML config file.

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if required fields are missing or invalid.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError("Config must be a YAML mapping")

    # Merge with defaults. Nested values must not share DEFAULT_CONFIG state.
    cfg = deepcopy(DEFAULT_CONFIG)
    if "daemon_url" in raw:
        cfg["daemon_url"] = raw["daemon_url"]
    else:
        raise ValueError("Config must include 'daemon_url'")

    if "secretary_agent" in raw:
        cfg["secretary_agent"] = raw["secretary_agent"]

    if "owner_did" in raw:
        cfg["owner_did"] = raw["owner_did"]

    if "poll_interval_sec" in raw:
        cfg["poll_interval_sec"] = int(raw["poll_interval_sec"])

    if "defaults" in raw and isinstance(raw["defaults"], dict):
        for k in ("workdir", "timeout_sec", "max_retries_per_stage",
                  "max_total_executions", "max_wall_clock_sec",
                  "require_final_acceptance",
                  "max_output_bytes", "network_access"):
            if k in raw["defaults"]:
                cfg["defaults"][k] = raw["defaults"][k]

    if "workers" in raw and isinstance(raw["workers"], dict):
        cfg["workers"] = raw["workers"]

    return cfg


# ── Worker matching ──────────────────────────────────────────────────

def _match_worker(
    cfg: dict[str, Any],
    match_field: str,
    match_value: str,
) -> dict[str, Any] | None:
    """Find a worker where match_value is in the worker's match_field list."""
    workers = cfg.get("workers", {})
    for name, w in workers.items():
        if not isinstance(w, dict):
            continue
        values = w.get(match_field, [])
        if not isinstance(values, list):
            values = [values]
        if match_value in values:
            return {"name": name, **w}
    return None


def find_worker_for_role(
    cfg: dict[str, Any], role: str
) -> dict[str, Any] | None:
    """Find a worker config that can fulfill the given role."""
    return _match_worker(cfg, "roles", role)


def find_worker_for_capability(
    cfg: dict[str, Any], capability: str
) -> dict[str, Any] | None:
    """Find a worker config that has the given capability."""
    return _match_worker(cfg, "capabilities", capability)


def find_fallback_worker(
    cfg: dict[str, Any],
    role: str,
    exclude_workers: set[str] | None = None,
) -> dict[str, Any] | None:
    """Find a fallback worker for a role, excluding already-tried workers.

    Design ref: docs/design/design-objective-loop-v1.1.md Section 9.2
    """
    exclude = exclude_workers or set()
    workers = cfg.get("workers", {})

    # Try role match first
    for name, w in workers.items():
        if not isinstance(w, dict):
            continue
        worker_key = w.get("worker_did") or w.get("agent_name", name)
        if worker_key in exclude:
            continue
        roles = w.get("roles", [])
        if not isinstance(roles, list):
            roles = [roles]
        if role in roles:
            return {"name": name, **w}

    # Fallback to capability match
    for name, w in workers.items():
        if not isinstance(w, dict):
            continue
        worker_key = w.get("worker_did") or w.get("agent_name", name)
        if worker_key in exclude:
            continue
        caps = w.get("capabilities", [])
        if not isinstance(caps, list):
            caps = [caps]
        if role in caps:
            return {"name": name, **w}

    return None


# ── Worker Registry reconciliation ──────────────────────────────────


async def reconcile_workers(
    cfg: dict[str, Any],
    daemon_url: str,
    auth_headers: dict[str, str],
    actor_did: str = "",
) -> list[str]:
    """Reconcile YAML worker profiles with Worker Registry.

    Returns a list of warning messages. Raises ValueError if a
    hard-blocking issue is found.

    Design ref: docs/design/design-objective-loop-v1.1.md Section 9.1
    """
    import httpx

    workers = cfg.get("workers", {})
    if not workers:
        return []

    owner_did = cfg.get("owner_did", "")
    if not owner_did:
        return ["No owner_did in config; skipping Worker Registry reconciliation."]
    warnings: list[str] = []

    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch registered workers via agents.py GET /owner/workers/v2/{owner_did}
        try:
            r = await client.get(
                f"{daemon_url}/owner/workers/v2/{owner_did}",
                params={"actor_did": owner_did},
                headers=auth_headers,
            )
            if r.status_code == 404:
                raise ValueError(
                    f"Owner '{owner_did}' not found in Worker Registry. "
                    f"Register the owner first: POST /owner/register"
                )
            if r.status_code == 401:
                raise ValueError(
                    f"Authentication failed when accessing Worker Registry "
                    f"(HTTP 401). Check your daemon token."
                )
            if r.status_code == 403:
                raise ValueError(
                    f"Access denied to Worker Registry (HTTP 403). "
                    f"Ensure actor_did is bound to owner_did={owner_did}."
                )
            if r.status_code >= 500:
                raise ValueError(
                    f"Worker Registry returned server error "
                    f"(HTTP {r.status_code}). Cannot verify worker identities."
                )
            if r.status_code != 200:
                warnings.append(
                    f"Could not fetch Worker Registry from daemon "
                    f"(HTTP {r.status_code}). Skipping reconciliation."
                )
                return warnings
            registry_workers = r.json().get("workers", [])
        except (httpx.HTTPError, httpx.NetworkError, httpx.TimeoutException,
                OSError) as e:
            warnings.append(
                f"Could not reach daemon for Worker Registry: {e}. "
                f"Skipping reconciliation."
            )
            return warnings

        registry_by_did = {w["did"]: w for w in registry_workers if "did" in w}

        for name, w in workers.items():
            if not isinstance(w, dict):
                continue

            worker_did = w.get("worker_did", "")

            # Check 1: worker_did is required
            if not worker_did:
                raise ValueError(
                    f"Worker '{name}' is missing required 'worker_did' field. "
                    f"All workers must have a registered DID."
                )

            # Check 2: worker_did must be in Registry
            if worker_did not in registry_by_did:
                raise ValueError(
                    f"Worker '{name}' has worker_did={worker_did} which is "
                    f"not registered in the Worker Registry. Register it first."
                )

            reg_agent = registry_by_did[worker_did]

            # Check 3: owner binding
            reg_owner = reg_agent.get("owner_did", "")
            if reg_owner and reg_owner != owner_did:
                raise ValueError(
                    f"Worker '{name}' (DID={worker_did}) is owned by "
                    f"{reg_owner}, not {owner_did}. Workers must be bound "
                    f"to the same owner."
                )

            # Check 4: worker_type
            worker_type = w.get("worker_type", "")
            if worker_type not in ("interactive_cli", "resident", "service_worker"):
                raise ValueError(
                    f"Worker '{name}' has invalid worker_type='{worker_type}'. "
                    f"Must be one of: interactive_cli, resident, service_worker."
                )

            # Check 5: output_contract
            if w.get("output_contract") != "agentnexus_json_v1":
                raise ValueError(
                    f"Worker '{name}' must have output_contract='agentnexus_json_v1'."
                )

            # Check 6: presence (warning, not error)
            presence = reg_agent.get("presence", "")
            if presence and presence != "available":
                warnings.append(
                    f"Worker '{name}' (DID={worker_did}) has presence="
                    f"'{presence}'. Only 'available' workers will be "
                    f"auto-dispatched."
                )

        return warnings


# ── Stage execution ─────────────────────────────────────────────────

# Built-in allowed commands for the local_cli backend
DEFAULT_ALLOWED_COMMANDS = {"python", "python3", "claude", "codex", "pytest"}


async def execute_stage(
    *,
    coordination_session_id: str,
    run_id: str,
    stage: str,
    worker_did: str,
    backend_kind: str,
    command: list[str],
    constraints: dict[str, Any],
    allowed_commands: set[str] | None = None,
    timeout_sec: int | None = None,
    max_output_bytes: int = 1_048_576,
) -> ExecutionResult:
    """Execute a single stage via LocalCLIBackend.

    This is the core of the local runner: it takes a next_action
    (start_execution) and runs it through the appropriate backend.

    Returns an ExecutionResult with the parsed worker output.
    """
    if backend_kind != "local_cli":
        raise ValueError(f"Unsupported backend_kind: {backend_kind}")

    cmds = allowed_commands or DEFAULT_ALLOWED_COMMANDS
    timeout = timeout_sec or constraints.get("timeout_sec", 1800)

    backend = LocalCLIBackend(
        allowed_commands=cmds,
        default_timeout_sec=timeout,
        max_output_bytes=max_output_bytes,
    )

    handle = await backend.start_execution(
        coordination_session_id=coordination_session_id,
        run_id=run_id,
        stage=stage,
        worker_did=worker_did,
        input_refs=constraints.get("input_refs", []),
        constraints=constraints,
        command=command,
    )

    # If blocked/failed immediately (e.g., disallowed command)
    if handle.status in ("blocked", "failed"):
        return await backend.collect_result(handle)

    # Wait for completion (in production, this would be a polling loop)
    import asyncio
    for _ in range(300):  # 30s max at 0.1s intervals
        await asyncio.sleep(0.1)
        handle = await backend.poll_execution(handle)
        if handle.status in ("completed", "failed", "blocked", "timed_out", "cancelled"):
            break

    return await backend.collect_result(handle)
