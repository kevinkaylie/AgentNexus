# 跨平台 MCP 配置示例

本文档提供 Kiro CLI、Claude Code、OpenClaw 等平台的 AgentNexus MCP 配置示例。

## 前置条件

1. **启动 Daemon**：所有平台使用前必须先启动 Daemon
   ```bash
   python main.py node start
   ```

2. **获取绝对路径**：将配置中的 `/path/to/AgentNexus` 替换为实际项目路径
   ```bash
   pwd  # 在项目根目录执行，获取绝对路径
   ```

---

## Kiro CLI 配置

Kiro 是一个 AI 驱动的命令行工具，适合作为设计 Agent 或规划 Agent。

### 配置文件位置

`.kiro/settings/mcp.json`（项目根目录）

### 设计 Agent 配置示例

```json
{
  "mcpServers": {
    "nexus-designer": {
      "command": "python",
      "args": ["/path/to/AgentNexus/main.py", "node", "mcp",
               "--name", "Designer", "--caps", "Design,Architecture"]
    }
  }
}
```

### 规划 Agent 配置示例

```json
{
  "mcpServers": {
    "nexus-planner": {
      "command": "python",
      "args": ["/path/to/AgentNexus/main.py", "node", "mcp",
               "--name", "Planner", "--caps", "Planning,Coordination"]
    }
  }
}
```

---

## Claude Code 配置

Claude Code 是 Anthropic 官方的命令行 AI 助手，适合作为开发 Agent。

### 配置文件位置

`.mcp.json`（项目根目录）

### 开发 Agent 配置示例

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

### 测试 Agent 配置示例

```json
{
  "mcpServers": {
    "nexus-tester": {
      "command": "python",
      "args": ["/path/to/AgentNexus/main.py", "node", "mcp",
               "--name", "Tester", "--caps", "Test,QA"]
    }
  }
}
```

---

## OpenClaw 配置

OpenClaw 支持多 Agent 实例，可在同一配置中定义多个 Agent。

### 配置文件位置

参考 OpenClaw 文档中的 MCP 配置位置

### 多 Agent 配置示例

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

---

## Claude Desktop 配置

Claude Desktop 是 Anthropic 的桌面应用。

### 配置文件位置

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

### 配置示例

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

---

## Cursor 配置

Cursor 是 AI 驱动的代码编辑器。

### 配置文件位置

`.cursor/mcp.json`（项目根目录）

### 配置示例

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

---

## 多 Agent 协作流程示例

以下展示一个典型的跨平台协作场景：

```
┌─────────────────────────────────────────────────────────────┐
│ 人类在飞书 → "安排开发登录功能"                                │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ OpenClaw 秘书 Agent                                          │
│   search_agents(keyword="Design") → 找到 Designer           │
│   propose_task(to_did=Designer, title="设计登录功能方案")     │
│   → task_id: "task_a1b2c3d4"                                │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼ 人类切换到 Kiro CLI
┌─────────────────────────────────────────────────────────────┐
│ Kiro 设计 Agent                                              │
│   fetch_inbox() → [{ message_type: "task_propose", ... }]   │
│   claim_task(to_did=Secretary, task_id="task_a1b2c3d4")     │
│   ... 完成设计 ...                                           │
│   propose_task(to_did=Developer, title="实现登录功能")       │
│   notify_state(to_did=Secretary, status="completed")        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼ 人类切换到 Claude Code
┌─────────────────────────────────────────────────────────────┐
│ Claude Code 开发 Agent                                       │
│   fetch_inbox() → [{ message_type: "task_propose", ... }]   │
│   claim_task(...) → 写代码 → notify_state(status="completed")│
└─────────────────────────────────────────────────────────────┘
```

---

## 启动模式说明

### `--name` 模式（推荐）

自动注册并绑定身份，幂等操作（重启不重复注册）：

```bash
python main.py node mcp --name "MyAgent" --caps "Code,Debug"
```

### `--did` 模式

绑定到已存在的 DID：

```bash
python main.py node mcp --did did:agentnexus:z6Mk...
```

### 无绑定模式

兼容旧版本，需要在每次调用时手动指定 DID：

```bash
python main.py node mcp
```

---

## 常见问题

### Q: MCP 工具调用报错 "No DID bound"

**A**: 启动时使用 `--name` 或 `--did` 参数绑定身份。

### Q: 多个 MCP 实例可以共用同一个 Agent 吗？

**A**: 可以。使用相同的 `--name` 启动会复用已有 Agent。但同一时间只有一个实例能绑定该 Agent。

### Q: 如何查看已注册的 Agent？

**A**: 调用 `list_local_agents` 工具，或直接查询 Daemon：
```bash
curl http://localhost:8765/agents/local
```

### Q: 如何在团队中共享 Agent 身份？

**A**: 使用 `export_agent` 导出加密包，通过安全渠道传递后用 `import_agent` 导入。
