# Agent Adapter Contract

> Status: Active for v1.1 L0 local Objective Loop.

AgentNexus does not require every worker to run inside the same agent framework. A worker can be Claude Code, Codex, OpenClaw, pytest, a shell script, an SDK service, or a custom CLI. The integration boundary is the Agent Adapter Contract.

## Contract Layers

| Layer | Purpose | Owner |
|------|---------|-------|
| Identity | Worker has a stable `worker_did`, `worker_type`, owner binding, roles and capabilities | AgentNexus daemon + Worker Registry |
| Invocation | Runner starts the worker through a bounded adapter such as `local_cli` | local-runner sidecar |
| Output normalization | Worker output is normalized into `agentnexus_json_v1` | output adapter |

This keeps AgentNexus protocol-native while allowing framework-specific agents to keep their own runtime, memory, tools and auth.

## Required Worker Fields

Each local-runner worker should declare:

```yaml
worker_did: did:agentnexus:z6Mk...
agent_name: MyWorker
worker_type: interactive_cli
adapter: local_cli
command: my-agent-cli
args: ["run", "--prompt", "{prompt}"]
roles: ["developer"]
capabilities: ["Code"]
output_contract: agentnexus_json_v1
output_adapter: agentnexus_json_v1
```

`worker_did` is the protocol identity. `agent_name` is display metadata only. `roles` and `capabilities` are routing hints used by the Objective Loop.

## Output Contract

The native AgentNexus result shape is:

```json
{
  "contract": "agentnexus_json_v1",
  "status": "completed",
  "artifact_type": "ImplementationArtifact",
  "artifact_body": "result body",
  "summary": "short result summary",
  "evidence_refs": [],
  "human_decision_request": null
}
```

`status` must be one of `completed`, `changes_requested`, `failed`, or `blocked`.

## Output Adapters

The local CLI backend supports these `output_adapter` values:

| Adapter | Use case |
|---------|----------|
| `agentnexus_json_v1` | Worker prints an AgentNexus JSON result directly |
| `openclaw_json` | OpenClaw `--json` wrapper; extracts assistant text from `payloads[].text` or `meta.finalAssistantRawText` |
| `json_text` | Generic JSON wrapper; extracts text from configured `output_text_paths` |
| `text_artifact` | Plain text stdout becomes an AgentNexus artifact |

For wrapper adapters, if extracted text contains an AgentNexus JSON object, that object is used. Otherwise the text is wrapped as a completed artifact with `artifact_type`.

## Examples

### Claude Code

```yaml
claude_developer:
  worker_did: did:agentnexus:z6MkClaudeDeveloper...
  agent_name: ClaudeDeveloper
  worker_type: interactive_cli
  adapter: local_cli
  command: claude
  args: ["-p", "{prompt}", "--output-format", "text", "--max-turns", "1"]
  roles: ["developer", "implement"]
  capabilities: ["Code", "Debug", "Implement"]
  output_contract: agentnexus_json_v1
  output_adapter: agentnexus_json_v1
```

### OpenClaw

OpenClaw needs a session selector such as `--session-key`, `--session-id`, `--to`, or `--agent`.

```yaml
openclaw_worker:
  worker_did: did:agentnexus:z6MkOpenClawWorker...
  agent_name: OpenClawWorker
  worker_type: interactive_cli
  adapter: local_cli
  command: openclaw
  args: ["agent", "--local", "--json", "--session-key", "agent:agentnexus:{stage}", "--message", "{prompt}"]
  roles: ["developer", "reviewer", "tester", "implement", "code_review", "test"]
  capabilities: ["Code", "Review", "Test"]
  output_contract: agentnexus_json_v1
  output_adapter: openclaw_json
  artifact_type: OpenClawArtifact
```

### Generic JSON Wrapper

```yaml
generic_json_agent:
  worker_did: did:agentnexus:z6MkGenericAgent...
  agent_name: GenericJsonAgent
  worker_type: interactive_cli
  adapter: local_cli
  command: my-agent-cli
  args: ["run", "--json", "--prompt", "{prompt}"]
  allowed_commands: ["my-agent-cli"]
  roles: ["developer"]
  capabilities: ["Code"]
  output_contract: agentnexus_json_v1
  output_adapter: json_text
  output_text_paths: ["result.text", "message.content"]
  artifact_type: GenericAgentArtifact
```

### Plain Script

```yaml
script_worker:
  worker_did: did:agentnexus:z6MkScriptWorker...
  agent_name: ScriptWorker
  worker_type: interactive_cli
  adapter: local_cli
  command: python
  args: ["scripts/run_task.py", "{prompt}"]
  roles: ["tester"]
  capabilities: ["Test"]
  output_contract: agentnexus_json_v1
  output_adapter: text_artifact
  artifact_type: ScriptOutput
```

## Windows Command Shims

On Windows, npm/pnpm-installed tools often expose `.cmd` shims. Use `claude.cmd`, `codex.cmd`, `openclaw.cmd`, or a wrapper script when direct `.exe` launch is blocked by WindowsApps permissions. Add any custom shim basename to `allowed_commands`.

## Security Boundary

`local_cli` still runs commands as a local sidecar, not inside the daemon. The backend uses argv execution without a shell, command allowlists, timeout killing, output limits, and destructive command detection. Production hardening will add per-worker tokens and stronger policy enforcement in later versions.
