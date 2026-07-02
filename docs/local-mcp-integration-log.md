# 本地 MCP 接入记录

> 目的：记录本机 OpenClaw / Claude Code / Codex 接入 AgentNexus 的配置变更，避免后续排障时不知道哪些文件被改过。

## 2026-06-18

### 已完成的本地闭环验证

- 启动 AgentNexus Node Daemon：`python main.py node start`
- Daemon 监听：`http://127.0.0.1:8765`
- Daemon 进程：`63464`
- 执行内置闭环：`python main.py node coordination demo`
- 验证结果：
  - Session：`cs_2c6401e6ff38474d`
  - Run：`run_ddfe911cd78c`
  - Status：`completed`
  - Closure：`clo_4a062240205d4d2a`
  - Dashboard：`http://127.0.0.1:8765/ui/coordination/cs_2c6401e6ff38474d`

### 项目内 MCP 配置

新增 `.mcp.json`，供 Claude Code 使用：

- MCP server：`nexus-claude-dev`
- Agent name：`ClaudeDeveloper`
- Capabilities：`Code,Debug,Implement`
- 启动命令：`python D:\PycharmProjects\AgentNexus\main.py node mcp --name ClaudeDeveloper --caps Code,Debug,Implement`

新增 `.kiro/settings/mcp.json`，供 OpenClaw 或兼容 Kiro MCP 配置入口使用：

- MCP server：`nexus-secretary`
- Agent name：`OpenClawSecretary`
- Capabilities：`Planning,Coordination,Notification`
- 启动命令：`python D:\PycharmProjects\AgentNexus\main.py node mcp --name OpenClawSecretary --caps Planning,Coordination,Notification`

说明：本次未写入 OpenClaw 自身的全局配置文件。已检查本机 `C:\Users\zkx19\Documents\Codex\2026-06-02\openclaw-npm-ts`，未找到明确的 MCP 配置入口；因此先在 AgentNexus 项目内保留兼容配置模板，避免误写未知位置。

### Codex 全局配置

Codex MCP 配置位于：

- `C:\Users\zkx19\.codex\config.toml`

已新增 MCP server：

- MCP server：`nexus_codex_reviewer`
- Agent name：`CodexReviewer`
- Capabilities：`Review,Code,QA`
- 启动命令：`python D:\PycharmProjects\AgentNexus\main.py node mcp --name CodexReviewer --caps Review,Code,QA`

写入前已备份：

- `C:\Users\zkx19\.codex\config.toml.agentnexus-20260618-174905.bak`

### 已注册的本地 MCP 身份

- `ClaudeDeveloper`：`did:agentnexus:z6MksBK5nxeKzz1uRrVSKK1unfdMoE1R6XA3S7tUPncFQn5F`
- `OpenClawSecretary`：`did:agentnexus:z6MkwSthuXfNFHVw8pgvd52BXah6sp2mJmE5cuzQ3CH7iHmJ`
- `CodexReviewer`：`did:agentnexus:z6Mkfj5AKaFSPN6Lkg1AyAngB45bpaQP8hHE7kkMqRWCzWMM`

### 验证结果

- `.mcp.json` JSON 语法通过。
- `.kiro/settings/mcp.json` JSON 语法通过。
- `C:\Users\zkx19\.codex\config.toml` TOML 语法通过。
- Daemon 仍在监听 `0.0.0.0:8765`。
- `python main.py agent list` 可看到三个身份。

### 回滚方式

项目内回滚：

- 删除 `.mcp.json`
- 删除 `.kiro/settings/mcp.json`
- 删除本记录文件 `docs/local-mcp-integration-log.md`，如果不再需要

Codex 全局配置回滚：

- 使用备份文件还原 `C:\Users\zkx19\.codex\config.toml`
- 或删除 `[mcp_servers.nexus_codex_reviewer]` 段

### 注意事项

- AgentNexus MCP server 是 stdio 进程，客户端启动 MCP 时会自动拉起对应 `python main.py node mcp ...`。
- 所有 MCP 身份依赖 Node Daemon，因此使用 OpenClaw / Claude Code / Codex 前应先确认 `http://127.0.0.1:8765` 可用。
- `--name` 模式是幂等的；重复启动同名 Agent 会复用已有身份，不会反复注册新 DID。
