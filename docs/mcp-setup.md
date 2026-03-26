# MCP Setup Guide | MCP 配置指南

**[中文](#-中文) | [English](#-english)**

---

## 🇨🇳 中文

### MCP 工具列表（15 个）

| 工具名 | 说明 | 绑定后可省略的参数 |
|--------|------|-------------------|
| `whoami` | 返回当前绑定的 DID 和完整名片 | — |
| `register_agent` | 注册 Agent，自动生成 DID + 私钥 + 签名名片 | — |
| `list_local_agents` | 列出本节点所有 Agent | — |
| `send_message` | 向目标 DID 发消息（自动路由，含联邦查询） | `from_did` |
| `fetch_inbox` | 获取离线消息收件箱 | `did` |
| `search_agents` | 按能力关键词搜索 Agent | — |
| `add_contact` | 添加远程 Agent 到通讯录 | — |
| `get_stun_endpoint` | 获取本节点公网 IP:Port | — |
| `get_pending_requests` | 查看待审批的连接请求 | — |
| `resolve_request` | 审批连接请求（allow/deny） | — |
| `get_card` | 获取 Agent 的签名名片（可验签），省略 `did` 则返回自身名片 | `did` |
| `update_card` | 更新名片字段（签名在 Daemon 内完成） | `did` |
| `get_session` | 按 session_id 查询完整会话历史（含已读消息） | — |
| `certify_agent` | 为目标 Agent 签发认证（issuer 用私钥签名） | `issuer_did` |
| `get_certifications` | 获取 Agent 的所有认证（每条独立签名） | `did` |

### 前置条件

在使用 MCP 之前，确保 Daemon 已启动：

```bash
python main.py node start    # 必须先启动
```

### Claude Desktop 配置

编辑 Claude Desktop 配置文件（通常在 `~/Library/Application Support/Claude/claude_desktop_config.json` 或 `%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "nexus-planner": {
      "command": "python",
      "args": ["/absolute/path/to/main.py", "node", "mcp",
               "--name", "Planner", "--caps", "Planning,Schedule"]
    }
  }
}
```

### Cursor 配置

在项目根目录创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "nexus-coder": {
      "command": "python",
      "args": ["/absolute/path/to/main.py", "node", "mcp",
               "--name", "Coder", "--caps", "Code,Debug"]
    }
  }
}
```

### Claude Code 配置

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "nexus-coder": {
      "command": "python",
      "args": ["/absolute/path/to/main.py", "node", "mcp",
               "--name", "Coder", "--caps", "Code,Debug"]
    }
  }
}
```

### 绑定后的使用体验

绑定身份后（通过 `--name` 或 `--did`），Claude 不需要记忆 DID，参数自动填充：

```
whoami()
→ { did: "...", profile: { name: "Coder" } }

send_message(to_did="...", content="Done")
← from_did 自动填充

fetch_inbox()
← did 自动填充

update_card(description="v2")
← did 自动填充
```

### 启动模式

```bash
# 推荐：--name 自动注册+绑定（幂等，重启不重复注册）
python main.py node mcp --name "MyBot" --caps "Chat,Search"
python main.py node mcp --name "MyBot"   # 再次启动：复用已有 Agent

# 绑定到已有 DID
python main.py node mcp --did did:agent:abc123...

# 无绑定（旧方式，兼容保留）
python main.py node mcp
```

---

## 🇬🇧 English

### MCP Tools (15)

| Tool | Description | Auto-filled when bound |
|------|-------------|------------------------|
| `whoami` | Return bound DID and full NexusProfile card | — |
| `register_agent` | Register Agent with auto DID, private key, signed card | — |
| `list_local_agents` | List all Agents on this node | — |
| `send_message` | Send message to DID (auto-routed with federation lookup) | `from_did` |
| `fetch_inbox` | Retrieve offline messages | `did` |
| `search_agents` | Search Agents by capability keyword | — |
| `add_contact` | Add remote Agent to contacts | — |
| `get_stun_endpoint` | Get this node's public IP:Port | — |
| `get_pending_requests` | List connection requests awaiting approval | — |
| `resolve_request` | Approve or deny a connection request (allow/deny) | — |
| `get_card` | Get signed NexusProfile card; omit `did` to get own card | `did` |
| `update_card` | Update card fields (re-signed in Daemon, key stays put) | `did` |
| `get_session` | Retrieve full conversation history for a session ID (all messages) | — |
| `certify_agent` | Issue a certification for a target Agent (issuer signs with private key) | `issuer_did` |
| `get_certifications` | Get all certifications for an Agent (each independently signed) | `did` |

### Prerequisites

Start the Daemon before using MCP:

```bash
python main.py node start    # must start first
```

### Claude Desktop Configuration

Edit Claude Desktop config (typically `~/Library/Application Support/Claude/claude_desktop_config.json` or `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "nexus-planner": {
      "command": "python",
      "args": ["/absolute/path/to/main.py", "node", "mcp",
               "--name", "Planner", "--caps", "Planning,Schedule"]
    }
  }
}
```

### Cursor Configuration

Create `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "nexus-coder": {
      "command": "python",
      "args": ["/absolute/path/to/main.py", "node", "mcp",
               "--name", "Coder", "--caps", "Code,Debug"]
    }
  }
}
```

### Claude Code Configuration

Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "nexus-coder": {
      "command": "python",
      "args": ["/absolute/path/to/main.py", "node", "mcp",
               "--name", "Coder", "--caps", "Code,Debug"]
    }
  }
}
```

### Usage After Binding

Once bound (via `--name` or `--did`), Claude skips DID management — parameters auto-fill:

```
whoami()
→ { did: "...", profile: { name: "Coder" } }

send_message(to_did="...", content="Done")
← from_did auto-filled

fetch_inbox()
← did auto-filled

update_card(description="v2")
← did auto-filled
```

### Startup Modes

```bash
# Recommended: --name auto-registers and binds (idempotent)
python main.py node mcp --name "MyBot" --caps "Chat,Search"
python main.py node mcp --name "MyBot"   # restart: reuses existing Agent

# Bind to existing DID
python main.py node mcp --did did:agent:abc123...

# No binding (legacy, kept for compatibility)
python main.py node mcp
```

> Start `python main.py node start` before using MCP tools.
