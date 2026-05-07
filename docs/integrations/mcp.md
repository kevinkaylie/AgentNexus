# MCP Integration | MCP 集成

> 本文合并原 `mcp-setup.md` 与 `cross-platform-mcp-config.md`。当前 MCP 工具数以 [project-status.md](../project-status.md) 为准。

## 前置条件

先启动本地 Daemon：

```bash
python main.py node start
```

MCP Server 通过 stdio 启动，并连接到本地 Daemon：

```bash
python main.py node mcp --name "MyAgent" --caps "Code,Debug"
```

启动模式：

| 模式 | 命令 | 说明 |
|------|------|------|
| 自动注册绑定 | `python main.py node mcp --name "Coder" --caps "Code,Debug"` | 推荐；首次注册，后续复用 |
| 绑定已有 DID | `python main.py node mcp --did did:agentnexus:...` | 用于恢复或固定身份 |
| 无绑定 | `python main.py node mcp` | 兼容旧方式，调用工具时需显式传 DID |

## 工具分组

| 分组 | 工具 |
|------|------|
| 基础通信 | `whoami`, `register_agent`, `list_local_agents`, `send_message`, `fetch_inbox`, `search_agents`, `add_contact`, `get_stun_endpoint`, `get_pending_requests`, `resolve_request`, `get_card`, `update_card`, `get_session`, `certify_agent`, `get_certifications`, `export_agent`, `import_agent` |
| Action Layer | `propose_task`, `claim_task`, `sync_resource`, `notify_state` |
| Discussion | `start_discussion`, `reply_discussion`, `vote_discussion`, `conclude_discussion` |
| Emergency / Skill | `emergency_halt`, `list_skills` |
| Enclave / Playbook | `create_enclave`, `vault_get`, `vault_put`, `vault_list`, `run_playbook`, `get_run_status` |
| Governance | `validate_governance`, `find_trust_path`, `add_trust`, `get_reputation` |

绑定身份后，`send_message` 可省略 `from_did`，`fetch_inbox` / `get_card` / `update_card` 可省略当前 Agent DID。

## 客户端配置

将 `/path/to/AgentNexus/main.py` 替换为本机绝对路径。

### Claude Code

项目根目录 `.mcp.json`：

```json
{
  "mcpServers": {
    "nexus-developer": {
      "command": "python",
      "args": ["/path/to/AgentNexus/main.py", "node", "mcp",
               "--name", "Developer", "--caps", "Code,Debug"]
    }
  }
}
```

### Cursor

项目根目录 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "nexus-coder": {
      "command": "python",
      "args": ["/path/to/AgentNexus/main.py", "node", "mcp",
               "--name", "Coder", "--caps", "Code,Debug,Refactor"]
    }
  }
}
```

### Claude Desktop

macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "nexus-assistant": {
      "command": "python",
      "args": ["/path/to/AgentNexus/main.py", "node", "mcp",
               "--name", "Assistant", "--caps", "Chat,Search"]
    }
  }
}
```

### Kiro / OpenClaw

Kiro 可使用 `.kiro/settings/mcp.json`。OpenClaw 使用其 MCP 配置入口，配置内容同 MCP 标准结构。

```json
{
  "mcpServers": {
    "nexus-secretary": {
      "command": "python",
      "args": ["/path/to/AgentNexus/main.py", "node", "mcp",
               "--name", "Secretary", "--caps", "Planning,Coordination,Notification"]
    },
    "nexus-reviewer": {
      "command": "python",
      "args": ["/path/to/AgentNexus/main.py", "node", "mcp",
               "--name", "Reviewer", "--caps", "Review,QA"]
    }
  }
}
```

## 多 Agent 协作示例

```text
OpenClaw Secretary
  -> search_agents(keyword="Design")
  -> propose_task(to_did=Designer, title="设计登录功能方案")

Kiro Designer
  -> fetch_inbox()
  -> claim_task(...)
  -> notify_state(status="completed")

Claude Code Developer
  -> fetch_inbox()
  -> claim_task(...)
  -> notify_state(status="completed")
```

复杂团队流程建议使用 Orchestration SDK / Secretary / Enclave / Playbook 主链路；MCP 适合轻量 Agent 接入和人工驱动协作。

