# Coding Coordination Quickstart

Run a full coding coordination workflow on your local machine in under 10 minutes.

## Prerequisites

- Python 3.11+
- Redis 5+ (for Relay; optional for local-only demo)

## 1. Install

```bash
git clone <repo-url>
cd AgentNexus

# Install core package
pip install -e .

# Install SDK
pip install -e agentnexus-sdk
```

## 2. Start Services

**Terminal 1 — Relay** (skip if running local-only without federation):

```bash
python main.py relay start
```

Relay listens on `http://0.0.0.0:9000`.

**Terminal 2 — Node Daemon**:

```bash
python main.py node start
```

Daemon listens on `http://0.0.0.0:8765`.

## 3. Run the Demo

```bash
python main.py node coordination demo
```

This command:

1. Creates demo identities (owner, secretary, designer, developer, reviewer, tester)
2. Creates a demo enclave with vault content
3. Runs `coding_intake` to create a coordination session
4. Submits artifacts for each workflow stage
5. Submits receipts and advances the workflow
6. Displays a summary with the session ID and Dashboard URL

**Expected output:**

```text
Setting up demo identities...
  Owner: did:agentnexus:z...
  Secretary: did:agentnexus:z...
Creating demo enclave and vault content...
Running coding coordination workflow...
  Session: cs_abc123
  Artifact: art_... (clarify)
  Artifact: art_... (design)
  Status: advanced

Coding Coordination demo completed

Session: cs_abc123
Status : completed
Events : 12 timeline entries
Closure: clo_abc123

Open:  http://127.0.0.1:8765/ui/coordination/cs_abc123
```

## 4. Inspect the Session

### Via CLI

```bash
python main.py node coordination show cs_abc123 --actor <secretary_did>
```

### Via API

```bash
# Get session detail
curl http://localhost:8765/coordination/sessions/cs_abc123?actor_did=<secretary_did>

# Get timeline
curl "http://localhost:8765/coordination/sessions/cs_abc123/timeline?actor_did=<secretary_did>"

# Get artifacts
curl "http://localhost:8765/coordination/sessions/cs_abc123/artifacts?actor_did=<secretary_did>"

# Get receipts
curl "http://localhost:8765/coordination/sessions/cs_abc123/receipts?actor_did=<secretary_did>"

# Get closures
curl "http://localhost:8765/coordination/sessions/cs_abc123/closures?actor_did=<secretary_did>"

# List all sessions for an owner
curl "http://localhost:8765/coordination/sessions?owner_did=<owner_did>&actor_did=<owner_did>"
```

### Via SDK

```python
import asyncio
import agentnexus


async def inspect():
    nexus = await agentnexus.connect("Inspector", caps=["Admin"])

    sessions = await nexus.coordination.list_sessions(
        owner_did="<owner_did>",
        actor_did="<actor_did>",
    )
    for s in sessions:
        print(f"{s['coordination_session_id']}: {s['objective']} [{s['status']}]")

    # Get full detail
    session = await nexus.coordination.get_session(
        "cs_abc123", actor_did="<actor_did>"
    )
    timeline = await nexus.coordination.timeline(
        "cs_abc123", actor_did="<actor_did>"
    )
    closures = await nexus.coordination.closures(
        "cs_abc123", actor_did="<actor_did>"
    )

    print(f"Objective: {session['objective']}")
    print(f"Status: {session['status']}")
    print(f"Timeline events: {len(timeline.get('timeline', []))}")
    print(f"Closures: {len(closures.get('closures', []))}")

    await nexus.close()


asyncio.run(inspect())
```

## 5. View in Dashboard

Open the URL printed by the demo command:

```text
http://127.0.0.1:8765/ui/coordination
```

Or open the Dashboard at `http://127.0.0.1:8765/ui` and navigate to Coordination.

## 6. Run the SDK Example

See the full SDK example at `agentnexus-sdk/examples/coding_coordination_demo.py`:

```bash
python agentnexus-sdk/examples/coding_coordination_demo.py
```

## Troubleshooting

**"Cannot connect to Node Daemon"**
Ensure the daemon is running: `python main.py node start`

**"AgentNexus SDK is not installed"**
Run: `pip install -e agentnexus-sdk`

**ImportError when importing coordination module**
Verify the SDK package is installed in development mode:
```bash
pip install -e agentnexus-sdk
python -c "from agentnexus.coordination import CoordinationClient; print('OK')"
```

**Redis connection refused**
The Relay requires Redis. If you don't have Redis running, the coordination demo still works without the Relay (local-only mode).

**Demo identities already exist**
The demo reuses existing identities with the same name. To force fresh identities, delete `data/agent_net.db` and restart the daemon.

**Artifact content not visible in Dashboard**
Artifact content is stored in the local Vault (enclave). If `data/agent_net.db` or Vault entries are deleted, artifact metadata and hashes remain but content may not be retrievable.
