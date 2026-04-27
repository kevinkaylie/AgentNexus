# AgentNexus Python SDK

3 lines to connect your AI Agent to the decentralized network.

## Install

```bash
pip install -e .
```

## Quick Start: Owner + Secretary + Dispatch

Register an Owner DID, create a Secretary Agent, bind Worker Agents, and dispatch a task.

```python
import agentnexus

# 1. Bootstrap: connect as admin
admin = await agentnexus.connect("Team Admin", caps=["Admin"])

# 2. Register personal main DID (Owner)
owner = await admin.owner.register("Kevin")

# 3. Register Secretary Agent (auto-bound to Owner)
secretary = await admin.secretary.register(owner.did, name="Secretary")

# 4. Create and bind Worker Agents
architect = await agentnexus.connect("Architect", caps=["architect", "design"])
developer = await agentnexus.connect("Developer", caps=["developer", "code"])
reviewer = await agentnexus.connect("Reviewer", caps=["reviewer", "review"])

await admin.owner.bind(owner.did, architect.agent_info.did)
await admin.owner.bind(owner.did, developer.agent_info.did)
await admin.owner.bind(owner.did, reviewer.agent_info.did)
```

### Dispatch a Session

```python
result = await admin.secretary.dispatch(
    session_id="sess_login_001",
    owner_did=owner.did,
    actor_did=secretary.did,
    objective="Complete login module design, implementation, testing and review",
    required_roles=["architect", "developer", "reviewer"],
    entry_mode="owner_pre_authorized",
)

print(f"Run: {result.run_id}, Enclave: {result.enclave_id}, Stage: {result.current_stage}")
```

### Worker: Handle Stage Tasks

Workers use `@nexus.worker.on_stage(role=...)` instead of parsing `task_propose` JSON manually.

```python
worker = await agentnexus.connect(did=developer.agent_info.did)

@worker.worker.on_stage(role="developer")
async def handle_stage(ctx):
    # Read requirements from Vault
    req = await ctx.vault.get("requirements/intake.json")

    # Read design spec
    spec = await ctx.vault.get("design/spec.md")
    patch = implement(spec.value)

    # Deliver artifact: writes to Vault + notifies completion
    await ctx.deliver(
        kind="code_diff",
        key="impl/diff.patch",
        value=patch,
        summary="Login module implementation",
    )

# Reject a stage if needed:
# await ctx.reject(reason="Tests failed, missing edge cases")
```

### Query Run / Intake Status

```python
intake = await admin.runs.get_intake("sess_login_001", actor_did=secretary.did)
status = await admin.runs.get_status(result.enclave_id, result.run_id)
```

### Owner Abort

```python
await admin.secretary.abort(
    session_id="sess_login_001",
    actor_did=owner.did,
    reason="Requirement changed, cancelling this run",
)
```

## Core Messaging (Lightweight)

For simple point-to-point communication without orchestration:

```python
nexus = await agentnexus.connect("MyAgent", caps=["Chat", "Search"])
await nexus.send(to_did="did:agentnexus:z6Mk...", content="Hello!")

@nexus.on_message
async def handle(msg):
    print(f"From {msg.from_did}: {msg.content}")

await nexus.close()
```

## Main Facades

| Facade | Purpose |
|--------|---------|
| `nexus.owner` | Owner DID registration and child Agent binding |
| `nexus.team` | Worker registry, presence and worker metadata |
| `nexus.secretary` | Intake, dispatch, confirm and abort |
| `nexus.runs` | Intake and Playbook run status |
| `nexus.worker` | Stage callback runtime and artifact delivery |
| `nexus.enclaves` | Enclave, Vault and Playbook APIs |
| `nexus.orchestration` | Aggregated facade (all of the above in one place) |

The legacy `send / propose_task / claim_task / notify_state` APIs remain supported for lightweight point-to-point collaboration.

## Synchronous API

For non-async contexts (scripts, REPL):

```python
import agentnexus.sync as sync

nexus = sync.connect("MyAgent", caps=["Chat"])
nexus.send(to_did="did:agentnexus:z6Mk...", content="Hello!")
nexus.close()
```
