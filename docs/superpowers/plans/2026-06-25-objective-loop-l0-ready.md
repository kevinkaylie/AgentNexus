# Objective Loop L0-Ready Hardening Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing Objective Loop V1.1 implementation to meet all L0-Ready acceptance criteria defined in `docs/design/design-objective-loop-v1.1.md` Section 14.1.

**Architecture:** Fix the 4 identified gaps in order: (1) identity — use real `worker_did` instead of `agent_name`, (2) contract — validate `agentnexus_json_v1`, (3) safety — loop budget, lease recovery, Worker Registry reconciliation, (4) resilience — fallback worker chain, DecisionGate abort/reject terminal paths. Each fix is a focused change to existing files; no new architectural components.

**Tech Stack:** Python 3.10+, aiosqlite, FastAPI, asyncio, YAML

---

### Task 1: Fix `worker_did` to use real DID instead of `agent_name`

**Files:**
- Modify: `agent_net/node/runner_loop.py:202-203`
- Modify: `agent_net/node/runner_loop.py:227-228`
- Modify: `agent_net/node/runner_loop.py:251-252`

**Design ref:** B1 from review — `worker_did` must be a real DID, not display name.

- [ ] **Step 1: Update runner_tick to use worker_did from config**

In `runner_tick()`, the `create_execution` call at line ~198-209 and the `execute_stage` calls at lines ~223-232 and ~247-256 all pass `worker.get("agent_name", "unknown")` as `worker_did`. Change all three to use the config's `worker_did` field, falling back to `agent_name` only if `worker_did` is absent.

```python
# In runner_tick(), replace all occurrences of:
#   worker_did=worker.get("agent_name", "unknown"),
# with:
#   worker_did=worker.get("worker_did") or worker.get("agent_name", "unknown"),
```

Three locations to fix:
1. `create_execution` call (~line 202): `worker_did=worker.get("agent_name", "unknown")`
2. First `execute_stage` call (~line 227): `worker_did=worker.get("agent_name", "unknown")`
3. Retry `execute_stage` call (~line 251): `worker_did=worker.get("agent_name", "unknown")`

- [ ] **Step 2: Run existing tests to verify no regression**

```bash
pytest tests/test_runner_loop.py tests/test_local_runner.py -v
```

- [ ] **Step 3: Commit**

```bash
git add agent_net/node/runner_loop.py
git commit -m "fix: use real worker_did from YAML config instead of agent_name

L0-Ready requires execution.worker_did to be a real DID, not a display
name. The YAML config already defines worker_did per worker profile; the
runner was incorrectly passing agent_name instead.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Add `agentnexus_json_v1` contract validation

**Files:**
- Modify: `agent_net/node/execution_backends/local_cli.py:265-275`
- Modify: `agent_net/node/local_runner.py:124-178` (add warning path)

**Design ref:** B3 from review — contract field must be validated, missing contract must emit warning.

- [ ] **Step 1: Add contract validation in LocalCLIBackend.collect_result**

After successful JSON parsing in `collect_result()` (around line 265), add a contract check. When `contract` is missing or not `agentnexus_json_v1`, emit a warning log but don't reject the result.

In `agent_net/node/execution_backends/local_cli.py`, modify the successful parse path:

```python
# After line 265 (if parsed:), add contract validation:
if parsed:
    contract = parsed.get("contract", "")
    if contract != "agentnexus_json_v1":
        import logging
        logging.getLogger("agentnexus").warning(
            f"Worker {worker_did} output missing agentnexus_json_v1 contract "
            f"(got: {contract or 'none'}). Accepting result but this is "
            f"required for L0-Ready."
        )
    return ExecutionResult(
        execution_id=eid,
        status=parsed.get("status", "completed"),
        ...
    )
```

Need to capture `worker_did` variable — it's available from `current.metadata` or the handle. Actually, `worker_did` isn't directly available in `collect_result`. We need to pass it through the handle metadata or add it to the handle. 

Simpler approach: add `worker_did` to the `ExecutionHandle.metadata` dict in `start_execution()` so it's available in `collect_result()`:

In `start_execution()`, the handle already includes `worker_did=worker_did` as a field. The `current` handle in `collect_result()` has `current.worker_did`. Use that.

```python
if parsed:
    contract = parsed.get("contract", "")
    if contract != "agentnexus_json_v1":
        import logging
        logging.getLogger("agentnexus").warning(
            f"Worker {current.worker_did} output missing agentnexus_json_v1 "
            f"contract (got: {contract or 'none'})"
        )
    return ExecutionResult(...)
```

- [ ] **Step 2: Add contract field to the prompt template**

In `agent_net/node/runner_loop.py:build_worker_prompt()`, add `"contract": "agentnexus_json_v1"` to the JSON structure instructions:

```python
# In the prompt string (~line 75), add contract field:
Return a JSON block with:
- contract: "agentnexus_json_v1"
- summary
- status: completed | changes_requested | failed | blocked
- artifact_type
- artifact_body
- evidence_refs
- human_decision_request, optional
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_local_cli_backend.py -v
```

- [ ] **Step 4: Commit**

```bash
git add agent_net/node/execution_backends/local_cli.py agent_net/node/runner_loop.py
git commit -m "feat: validate agentnexus_json_v1 contract in worker output

Adds contract field validation in LocalCLIBackend.collect_result() with
warning on missing/mismatched contract. Updates prompt template to
include contract field in output instructions.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Worker Registry reconciliation on runner start

**Files:**
- Modify: `agent_net/node/local_runner.py` (add `reconcile_workers()` function)
- Modify: `agent_net/cli/runner.py` (call reconciliation in start/run commands)

**Design ref:** B2 from review — Section 9.1 requires YAML ↔ Registry reconciliation.

- [ ] **Step 1: Add reconcile_workers function**

In `agent_net/node/local_runner.py`, add a new async function:

```python
async def reconcile_workers(
    cfg: dict[str, Any],
    daemon_url: str,
    auth_headers: dict[str, str],
) -> list[str]:
    """Reconcile YAML worker profiles with Worker Registry.
    
    Returns a list of warning messages. Raises ValueError if a 
    hard-blocking issue is found (e.g., worker_did not registered).
    
    Design ref: docs/design/design-objective-loop-v1.1.md Section 9.1
    """
    import httpx
    
    workers = cfg.get("workers", {})
    if not workers:
        return []
    
    owner_did = cfg.get("owner_did", "")
    warnings: list[str] = []
    
    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch registered agents for this owner
        try:
            r = await client.get(
                f"{daemon_url}/agents",
                params={"owner_did": owner_did},
                headers=auth_headers,
            )
            if r.status_code != 200:
                warnings.append(
                    f"Could not fetch Worker Registry from daemon "
                    f"(HTTP {r.status_code}). Skipping reconciliation."
                )
                return warnings
            registry_agents = r.json().get("agents", [])
        except Exception as e:
            warnings.append(
                f"Could not reach daemon for Worker Registry: {e}. "
                f"Skipping reconciliation."
            )
            return warnings
        
        registry_by_did = {a["did"]: a for a in registry_agents}
        
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
                    f"not registered in the Worker Registry. Register it first: "
                    f"python main.py node agent register --did {worker_did} ..."
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
```

- [ ] **Step 2: Call reconciliation in CLI runner**

In `agent_net/cli/runner.py`, add reconciliation calls in both `node_local_runner_cmd` branches (`run` and `start`), after config loading and before the main loop:

```python
# After load_runner_config() succeeds, add:
from agent_net.node.local_runner import reconcile_workers
try:
    token = _read_token()
    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}
    reconcile_warnings = await reconcile_workers(
        cfg, cfg["daemon_url"], auth_headers
    )
    for w in reconcile_warnings:
        print(f"  [WARNING] {w}")
except ValueError as e:
    print(f"Error: {e}")
    return
```

This should be added in both the `run` and `start` branches, after config loading.

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_local_runner.py -v
```

- [ ] **Step 4: Commit**

```bash
git add agent_net/node/local_runner.py agent_net/cli/runner.py
git commit -m "feat: add Worker Registry reconciliation on runner start

Validates YAML worker profiles against the daemon's Worker Registry:
- worker_did must be registered
- owner_did must match
- worker_type must be valid
- output_contract must be agentnexus_json_v1
- presence warnings for non-available workers

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Lease expiry auto-handling in runner_tick

**Files:**
- Modify: `agent_net/node/runner_loop.py:308-314` (poll_execution handler)
- Modify: `agent_net/node/loop_engine.py:180-198` (lease expiry → mark timed_out)

**Design ref:** D3 from review — expired lease must be auto-handled (mark timed_out, retry or DecisionGate).

- [ ] **Step 1: Handle lease_expired in runner_tick's poll_execution branch**

In `runner_tick()`, the `poll_execution` handler currently just logs. When `lease_expired: True`, the runner should update the execution status to `timed_out` via the PATCH endpoint, which will cause `next_action` to return the appropriate retry/DecisionGate action on the next tick.

```python
# In runner_tick(), replace the poll_execution handler (~line 308-314):
elif atype == "poll_execution":
    eid = action.get("execution_id", "")
    if action.get("lease_expired"):
        # Mark execution as timed_out so Loop Engine handles it next tick
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                token = _read_token_from_config(config)
                auth = {"Authorization": f"Bearer {token}"} if token else {}
                await client.patch(
                    f"{config['daemon_url']}/coordination/executions/{eid}",
                    json={
                        "actor_did": actor_did,
                        "status": "timed_out",
                    },
                    headers=auth,
                )
            actions.append({
                "action": "lease_expired", "session_id": sid,
                "stage": action.get("stage", ""),
                "execution_id": eid,
                "reason": "Marked timed_out due to lease expiry",
            })
        except Exception as e:
            actions.append({
                "action": "error", "session_id": sid,
                "reason": f"Failed to mark lease expired: {e}",
            })
    else:
        actions.append({
            "action": "poll_execution", "session_id": sid,
            "stage": action.get("stage", ""),
            "execution_id": eid,
            "reason": action.get("reason", ""),
        })
```

But wait — `runner_tick` doesn't have access to an HTTP client directly. The design uses callbacks. The `create_execution` callback already handles the POST. But there's no `update_execution` callback.

Better approach: add an `update_execution` callback to `runner_tick()`. Or, simpler: since the Loop Engine's `next_action()` already detects expired leases, we just need the runner to call PATCH when it sees `lease_expired: True`. 

Let me add an optional `update_execution` callback parameter to `runner_tick()`:

```python
async def runner_tick(
    *,
    config: dict[str, Any],
    list_sessions: Callable[..., Awaitable[list[dict]]],
    get_next_action: Callable[..., Awaitable[dict]],
    get_session_detail: Callable[..., Awaitable[dict]] | None = None,
    create_execution: Callable[..., Awaitable[dict]],
    submit_result: Callable[..., Awaitable[dict]],
    call_advance: Callable[..., Awaitable[dict]] | None = None,
    create_decision: Callable[..., Awaitable[dict]] | None = None,
    update_execution: Callable[..., Awaitable[dict]] | None = None,  # NEW
    actor_did: str = "",
    owner_did: str = "",
) -> list[dict]:
```

Then in the poll_execution handler, when `lease_expired` is true and `update_execution` is available:

```python
elif atype == "poll_execution":
    if action.get("lease_expired") and update_execution:
        eid = action.get("execution_id", "")
        try:
            await update_execution(eid, {
                "actor_did": actor_did,
                "status": "timed_out",
            })
            actions.append({
                "action": "lease_expired", "session_id": sid,
                "stage": action.get("stage", ""),
                "execution_id": eid,
                "reason": "Marked timed_out",
            })
        except Exception as e:
            actions.append({
                "action": "error", "session_id": sid,
                "reason": f"Failed to mark lease expired: {e}",
            })
    else:
        actions.append({
            "action": "poll_execution", "session_id": sid,
            "stage": action.get("stage", ""),
            "execution_id": action.get("execution_id", ""),
            "reason": action.get("reason", ""),
        })
```

- [ ] **Step 2: Add update_execution callback in CLI runner**

In `agent_net/cli/runner.py`, both the `run` and `start` branches, add the `update_execution` callback after `create_execution`:

```python
async def _ue(eid, body):
    r = await client.patch(
        f"{daemon_url}/coordination/executions/{eid}",
        json=body,
        headers=auth_headers,
    )
    if r.status_code == 200:
        return r.json()
    raise Exception(f"update_execution: {r.status_code}")
```

And pass it to `runner_tick()`:

```python
actions = await runner_tick(
    ...
    update_execution=_ue,
    ...
)
```

- [ ] **Step 3: Ensure next_action handles timed_out correctly**

Verify that `next_action()` already handles `timed_out` status (it does — line 163: `if latest["status"] in ("timed_out", "failed", "cancelled")`). No code change needed here.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_objective_loop_engine.py tests/test_runner_loop.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agent_net/node/runner_loop.py agent_net/cli/runner.py
git commit -m "feat: auto-handle lease expiry in runner poll loop

When next_action returns lease_expired=True, the runner now calls
PATCH /coordination/executions/{id} to mark the execution as timed_out.
On the next tick, the Loop Engine will see timed_out status and return
the appropriate retry or DecisionGate action.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Loop budget enforcement

**Files:**
- Modify: `agent_net/node/loop_engine.py` (add budget checks)
- Modify: `agent_net/node/local_runner.py` (add budget defaults)
- Modify: `agent_net/node/runner_loop.py` (read budget from session)

**Design ref:** D1 from review — Section 6.4.3 requires `max_total_executions` and `max_wall_clock_sec` enforcement.

- [ ] **Step 1: Add budget check in next_action()**

In `agent_net/node/loop_engine.py`, after loading the session and before computing the next action, add budget checks:

```python
# After loading session policy (~line 118), add budget checks:
max_total = policy.get("max_total_executions", 30)
max_wall_clock = policy.get("max_wall_clock_sec", 14400)

# Check total execution count
all_execs = await list_objective_executions(
    coordination_session_id=coordination_session_id,
)
if len(all_execs) >= max_total:
    return {
        "action_type": "create_decision_gate",
        "stage": current_stage,
        "reason": (
            f"Total executions ({len(all_execs)}) exceeded "
            f"budget ({max_total})"
        ),
        "gate": "max_retry_exceeded",
    }

# Check wall clock
session_created = sess.get("created_at", 0)
if session_created and (time.time() - session_created) > max_wall_clock:
    return {
        "action_type": "create_decision_gate",
        "stage": current_stage,
        "reason": (
            f"Wall clock ({time.time() - session_created:.0f}s) "
            f"exceeded budget ({max_wall_clock}s)"
        ),
        "gate": "max_retry_exceeded",
    }
```

Note: `list_objective_executions` without stage filter returns all executions for the session. Need to verify the function supports this (it does — `stage` is optional).

- [ ] **Step 2: Add budget defaults to runner config**

In `agent_net/node/local_runner.py`, add budget fields to `DEFAULT_CONFIG`:

```python
DEFAULT_CONFIG: dict[str, Any] = {
    ...
    "defaults": {
        "workdir": str(pathlib.Path.cwd()),
        "timeout_sec": 1800,
        "max_retries_per_stage": 2,
        "max_total_executions": 30,       # NEW
        "max_wall_clock_sec": 14400,      # NEW
        "require_final_acceptance": False, # NEW
    },
    ...
}
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_objective_loop_engine.py -v
```

- [ ] **Step 4: Commit**

```bash
git add agent_net/node/loop_engine.py agent_net/node/local_runner.py
git commit -m "feat: enforce loop budget (max_total_executions, max_wall_clock)

Adds budget checks to Loop Engine's next_action():
- max_total_executions: total execution attempts across all stages
- max_wall_clock_sec: total wall clock time since session creation

When either is exceeded, returns create_decision_gate with
max_retry_exceeded gate instead of continuing auto-execution.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Fallback worker chain

**Files:**
- Modify: `agent_net/node/local_runner.py` (add fallback worker finder)
- Modify: `agent_net/node/runner_loop.py` (implement fallback logic in runner_tick)

**Design ref:** D4 from review — Section 9.2 requires: retry same worker once → switch to same-role different worker → all candidates fail → DecisionGate.

- [ ] **Step 1: Add find_fallback_worker function**

In `agent_net/node/local_runner.py`:

```python
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
```

- [ ] **Step 2: Add fallback tracking in runner_tick**

In `agent_net/node/runner_loop.py`, modify the `start_execution` handler to track tried workers and use fallback when a worker fails:

After the initial `start_execution` handler gets the action and finds a worker, add fallback logic for retries:

```python
if atype == "start_execution":
    stage = action.get("stage", "")
    role = action.get("role", "")
    retry_attempt = action.get("retry_attempt", 1)
    
    # Find matching worker
    worker = find_worker_for_role(config, role)
    if worker is None:
        worker = find_worker_for_capability(config, role)
    
    # For retries, try fallback workers
    if worker is None or retry_attempt > 1:
        # Build exclude set from previous executions for this stage
        # (simplified: exclude the first-choice worker if retrying)
        from agent_net.node.local_runner import find_fallback_worker
        fallback = find_fallback_worker(
            config, role,
            exclude_workers={worker.get("worker_did") or worker.get("agent_name", "")} if worker else set(),
        )
        if fallback:
            worker = fallback
    
    if worker is None:
        actions.append({
            "action": "skip", "session_id": sid, "stage": stage,
            "reason": f"No worker for role '{role}' (retry {retry_attempt})",
        })
        continue
    
    # ... rest of execution logic
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_local_runner.py tests/test_runner_loop.py -v
```

- [ ] **Step 4: Commit**

```bash
git add agent_net/node/local_runner.py agent_net/node/runner_loop.py
git commit -m "feat: add fallback worker chain for stage retries

When a stage fails and needs retry, the runner now tries fallback
workers with the same role before giving up. Excludes already-tried
workers to avoid infinite loops with the same failing worker.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: DecisionGate abort/reject terminal paths

**Files:**
- Modify: `agent_net/node/loop_engine.py:126-160` (blocked execution handler)

**Design ref:** D2 from review — Section 8.1 requires full DecisionGate recovery: `rejected` → failed closure, `aborted` → aborted closure.

- [ ] **Step 1: Handle rejected and aborted decisions in next_action**

In `agent_net/node/loop_engine.py`, extend the blocked execution handler (~lines 125-160) to also check for `rejected` and `aborted` decisions on the current stage:

```python
if latest["status"] == "blocked":
    decisions = await list_decision_requests(
        coordination_session_id=coordination_session_id,
        run_id=run_id,
        stage=current_stage,
    )
    resolved_decisions = [d for d in decisions if d.get("status") in ("resolved", "approved", "denied")]
    if resolved_decisions:
        latest_decision = resolved_decisions[0]
        response = latest_decision.get("response", {})
        if isinstance(response, str):
            import json as _json
            response = _json.loads(response) if response else {}
        decision_value = response.get("decision", "")
        
        if decision_value == "approved":
            return {
                "action_type": "start_execution",
                "stage": current_stage,
                "role": current_stage_def.get("role", ""),
                "reason": "Blocked execution resolved: retry approved by human",
                "retry_attempt": latest["attempt"] + 1,
            }
        elif decision_value in ("rejected", "aborted"):
            # Terminal: mark session as aborted/failed
            return {
                "action_type": "closed",
                "stage": current_stage,
                "reason": (
                    f"Stage {current_stage} {decision_value} by human. "
                    f"Session cannot continue."
                ),
            }
```

This requires that the `resolve_decision_request` API updates the decision status and stores the human's response with `decision: "aborted"` or `decision: "rejected"`. We should also ensure the Secretary Gateway's `handle_decision_gate` properly maps human responses.

- [ ] **Step 2: Ensure Secretary Gateway maps abort/reject decisions correctly**

The existing `secretary_gateway.py` creates decision requests but doesn't handle responses. The resolution endpoint (`POST /owner/decisions/{id}/resolve`) already exists in the codebase. Verify it stores the response correctly. No code change needed if the existing `resolve_decision_request` stores `response` as JSON with `decision` field.

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_objective_loop_engine.py -v
```

- [ ] **Step 4: Commit**

```bash
git add agent_net/node/loop_engine.py
git commit -m "feat: handle rejected/aborted DecisionGate responses in Loop Engine

When a human rejects or aborts a DecisionGate, the Loop Engine now
returns action_type='closed' instead of getting stuck. This completes
the DecisionGate recovery matrix per Section 8.1 of the design doc.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: Create example config and documentation

**Files:**
- Create: `.agentnexus/local-runner.yaml.example`
- Modify: `docs/quickstart-objective-loop.md` (if needed)

- [ ] **Step 1: Create example YAML config**

Create `.agentnexus/local-runner.yaml.example`:

```yaml
# AgentNexus Local Runner Configuration
# Copy to .agentnexus/local-runner.yaml and customize
#
# Design ref: docs/design/design-objective-loop-v1.1.md Section 6.2

daemon_url: http://127.0.0.1:8765
secretary_agent: did:agentnexus:z6MkSecretary...
owner_did: did:agentnexus:z6MkOwner...
poll_interval_sec: 2

defaults:
  workdir: /path/to/your/project
  timeout_sec: 1800
  max_retries_per_stage: 2
  max_total_executions: 30
  max_wall_clock_sec: 14400
  require_final_acceptance: false
  network_access: deny_by_default
  max_output_bytes: 1048576

workers:
  # ── Developer Worker ──────────────────────────────────────────
  claude_developer:
    # REQUIRED: Real DID registered in Worker Registry
    worker_did: did:agentnexus:z6MkClaudeDeveloper...
    # Display name (for logs only)
    agent_name: ClaudeDeveloper
    # Must be one of: interactive_cli, resident, service_worker
    worker_type: interactive_cli
    # v1.1 only supports local_cli
    adapter: local_cli
    # Command to execute (basename or full path)
    command: claude
    # Arguments: {prompt} is replaced with structured task
    args: ["-p", "{prompt}"]
    # Roles this worker can fulfill (must match playbook stage roles)
    roles: ["developer", "implement"]
    # Capabilities for fallback matching
    capabilities: ["Code", "Debug", "Implement"]
    # REQUIRED for L0-Ready
    output_contract: agentnexus_json_v1
    # Working directory (must be in daemon's workdir allowlist)
    workdir: /path/to/your/project

  # ── Reviewer Worker ───────────────────────────────────────────
  codex_reviewer:
    worker_did: did:agentnexus:z6MkCodexReviewer...
    agent_name: CodexReviewer
    worker_type: interactive_cli
    adapter: local_cli
    command: codex
    args: ["exec", "{prompt}"]
    roles: ["reviewer", "code_review"]
    capabilities: ["Review", "Code", "QA"]
    output_contract: agentnexus_json_v1

  # ── Tester Worker ─────────────────────────────────────────────
  pytest_runner:
    worker_did: did:agentnexus:z6MkLocalTestRunner...
    agent_name: LocalTestRunner
    worker_type: interactive_cli
    adapter: local_cli
    command: python
    args: ["-m", "pytest"]
    roles: ["tester", "test"]
    capabilities: ["Test"]
    output_contract: agentnexus_json_v1

  # ── Script Worker (fallback) ──────────────────────────────────
  script_worker:
    worker_did: did:agentnexus:z6MkScriptWorker...
    agent_name: ScriptWorker
    worker_type: interactive_cli
    adapter: local_cli
    command: python
    args: ["script.py", "--input", "{prompt}"]
    roles: ["developer", "reviewer", "tester"]
    capabilities: ["Code", "Review", "Test", "Script"]
    output_contract: agentnexus_json_v1
```

- [ ] **Step 2: Verify quickstart doc exists and is current**

The file `docs/quickstart-objective-loop.md` already exists. Verify it references the example config and reconciliation step.

- [ ] **Step 3: Commit**

```bash
git add .agentnexus/local-runner.yaml.example
git commit -m "docs: add local-runner.yaml.example with L0-Ready worker profiles

All worker profiles include required fields: worker_did, worker_type,
output_contract, and allowlisted workdir. Includes 4 worker profiles
(developer, reviewer, tester, script fallback) covering the full
coding.v1 playbook stages.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: End-to-end verification

**Files:**
- No code changes — run all tests and verify.

- [ ] **Step 1: Run full unit test suite**

```bash
cd D:\PycharmProjects\AgentNexus && pytest tests/test_objective_loop_engine.py tests/test_local_cli_backend.py tests/test_objective_execution_storage.py tests/test_local_runner.py tests/test_runner_loop.py -v
```

Expected: All 56+ tests pass.

- [ ] **Step 2: Run full project test suite**

```bash
cd D:\PycharmProjects\AgentNexus && pytest tests/ -v --timeout=60
```

Expected: 544+ passed, existing skips unchanged.

- [ ] **Step 3: Verify ruff lint**

```bash
cd D:\PycharmProjects\AgentNexus && ruff check agent_net/node/loop_engine.py agent_net/node/runner_loop.py agent_net/node/local_runner.py agent_net/node/execution_backends/local_cli.py agent_net/cli/runner.py agent_net/node/secretary_gateway.py
```

Expected: Zero errors.

- [ ] **Step 4: Update project-status.md**

Update `docs/project-status.md` to reflect L0-Ready hardening completion.

- [ ] **Step 5: Final commit**

```bash
git add docs/project-status.md
git commit -m "chore: mark Objective Loop L0-Ready hardening complete

All L0-Ready acceptance criteria from design-objective-loop-v1.1.md
Section 14.1 are now met:
- Real worker_did in execution records
- agentnexus_json_v1 contract validation
- Worker Registry reconciliation
- Lease expiry auto-handling
- Loop budget enforcement
- Fallback worker chain
- DecisionGate abort/reject terminal paths
- Example config with 4 worker profiles

Co-Authored-By: Claude <noreply@anthropic.com>"
```
