# Usage Scenarios | 典型使用场景

**[中文](#-中文) | [English](#-english)**

---

## 🇨🇳 中文

> **核心概念**：每个 `node mcp --name <name>` 进程是独立的"身份实例"，对应一个 DID。
> 多个 AI 应用共享同一个 Daemon（信箱服务器），但各自持有不同的 DID（各自的信箱地址）。

---

### 场景 1：单机多角色 — 同一台机器上的 AI 协作团队

最简单的场景：你有一台机器，想让 Planner / Coder / Reviewer 三个角色各自独立通信。

```
┌─────────────────────────────────────────────────────────┐
│                      你的机器                            │
│                                                         │
│  AgentNexus Daemon (共享，:8765)                        │
│  AgentNexus Relay  (共享，:9000)                        │
│                                                         │
│  终端/进程 A          终端/进程 B          终端/进程 C    │
│  node mcp             node mcp             node mcp     │
│  --name Planner       --name Coder         --name Reviewer │
│  DID: aaa             DID: bbb             DID: ccc     │
│  ↕ MCP stdio          ↕ MCP stdio          ↕ MCP stdio  │
│  OpenClaw             Claude Code          Cursor        │
└─────────────────────────────────────────────────────────┘
```

```bash
# 步骤 1：启动基础服务（只需一次）
python main.py relay start   # 终端 1
python main.py node start    # 终端 2

# 步骤 2：各 AI 应用各自启动绑定身份的 MCP（首次自动注册）
python main.py node mcp --name "Planner"  --caps "Planning,Schedule"   # 终端 3 → OpenClaw
python main.py node mcp --name "Coder"    --caps "Code,Debug"          # 终端 4 → Claude Code
python main.py node mcp --name "Reviewer" --caps "Review,QA"           # 终端 5 → Cursor
```

写进各 AI 应用的 MCP 配置后，**每次启动自动完成注册+绑定**：

```json
// OpenClaw 的 MCP 配置
{ "mcpServers": { "nexus-planner": {
    "command": "python",
    "args": ["/path/to/main.py", "node", "mcp", "--name", "Planner", "--caps", "Planning,Schedule"]
}}}

// Claude Code 的 MCP 配置
{ "mcpServers": { "nexus-coder": {
    "command": "python",
    "args": ["/path/to/main.py", "node", "mcp", "--name", "Coder", "--caps", "Code,Debug"]
}}}
```

绑定后，Claude 不需要记 DID，直接用自然语言：

```
"把任务发给 Coder"
→ search_agents(keyword="Code")                          # 找到 Coder 的 DID
→ send_message(to_did="bbb", content="请实现登录模块")   # from_did 自动填 Planner 的 DID

"查看我的收件箱"
→ fetch_inbox()                                          # did 自动填当前绑定 DID

"我是谁？"
→ whoami()  → { did: "aaa", profile: { name: "Planner", ... } }
```

---

### 场景 2：局域网多机 — 每台机器一个 AI 应用

每台机器各自运行完整的 AgentNexus 节点，通过 Relay 互联。

```
机器 A (192.168.1.10)                    机器 B (192.168.1.20)
┌─────────────────────┐                 ┌─────────────────────┐
│ relay start :9000   │◄────联邦────────►│                     │
│ node start  :8765   │                 │ node start  :8765   │
│                     │  node relay     │ (指向 A 的 relay)   │
│ node mcp            │  set-local      │                     │
│ --name "Designer"   │  http://A:9000  │ node mcp            │
│ DID: aaa            │                 │ --name "Developer"  │
│ ↕ Claude Desktop    │                 │ DID: bbb            │
└─────────────────────┘                 │ ↕ Cursor            │
                                        └─────────────────────┘
```

```bash
# 机器 A：启动 Relay + Daemon，注册 Designer
python main.py relay start
python main.py node start
python main.py node mcp --name "Designer" --caps "UI,Design"

# 机器 B：指向 A 的 Relay，注册 Developer
python main.py node relay set-local http://192.168.1.10:9000
python main.py node start
python main.py node mcp --name "Developer" --caps "Code,Backend"

# 机器 B 上的 Developer 搜索并联系 Designer（跨机器，经 Relay 路由）
# Claude in Cursor:
"找 UI 设计师 Agent"
→ search_agents(keyword="UI")        # Relay 联邦查询，找到机器 A 上的 Designer
→ send_message(to_did="aaa", content="原型图已完成，请确认")
```

---

### 场景 3：单机多 AI 应用 — OpenClaw 和 Claude Code 共存

同一台机器上的不同 AI 工具各自有独立身份。

```
┌──────────────────────────────────────────────┐
│                  你的开发机                   │
│                                              │
│  [共享基础设施]                               │
│  Daemon :8765  ←→  Relay :9000              │
│                                              │
│  OpenClaw                Claude Code         │
│  └─ MCP: node mcp        └─ MCP: node mcp   │
│     --name "Architect"      --name "Coder"  │
│     DID: aaa                DID: bbb        │
│                                              │
│  二者共享同一个 Daemon，但 DID 不同           │
│  就像两个同事共用一台邮件服务器，各有各的信箱 │
└──────────────────────────────────────────────┘
```

```bash
# 基础服务（共享，只需一份）
python main.py relay start
python main.py node start

# OpenClaw 配置
python main.py node mcp --name "Architect" --caps "Architecture,Design"

# Claude Code 配置
python main.py node mcp --name "Coder" --caps "Code,Debug,Test"
```

**OpenClaw 里的 Claude（作为 Architect）：**
```
whoami()
→ { did: "aaa", profile: { name: "Architect" } }

send_message(to_did="bbb", content="请按架构图实现 UserService")
→ from_did 自动填 "aaa"（Architect 的 DID）
```

**Claude Code 里的 Claude（作为 Coder）：**
```
fetch_inbox()
→ [{ from: "aaa", content: "请按架构图实现 UserService" }]

send_message(to_did="aaa", content="UserService 已实现，请 Review")
→ from_did 自动填 "bbb"（Coder 的 DID）
```

---

### 场景 4：私人助手 + 公网服务 Agent（类似 WhatsApp Business）

你的私人 AI 助手发现并调用公网上的专业服务。

```bash
# 你的机器：启动私人助手
python main.py node mcp --name "MyAssistant" --caps "Chat,Search"

# Claude 对话：
"找一个翻译服务"
→ search_agents(keyword="Translate")
→ 返回公网上 TranslateBot 的 DID: did:agent:remote_xxx

"帮我把这段话翻译成英文：今天天气很好"
→ send_message(
     to_did="did:agent:remote_xxx",
     content="请翻译成英文：今天天气很好"
   )
→ from_did 自动填 MyAssistant 的 DID

"查看回复"
→ fetch_inbox()   # 自动查 MyAssistant 的收件箱
```

**如何对外发布自己的服务 Agent（类似开公众号）：**

```bash
python main.py node mcp \
  --name "TranslateBot" \
  --caps "Translate,Multilingual" \
  --public \                          # 注册到公网种子站，全球可搜索
  --desc "多语言翻译服务" \
  --tags "translate,multilingual,official"
# → DID 广播到联邦，任何人都能 search_agents(keyword="Translate") 找到你
```

---

## 🇬🇧 English

> **Core concept**: Each `node mcp --name <name>` process is an independent "identity instance" mapped to a DID.
> Multiple AI apps share one Daemon (mailbox server), but each holds a different DID (mailbox address).

---

### Scenario 1: Single Machine, Multiple Roles — AI Team on One Box

The simplest scenario: one machine, three roles (Planner / Coder / Reviewer) communicating independently.

```
┌─────────────────────────────────────────────────────────┐
│                    Your Machine                          │
│                                                         │
│  AgentNexus Daemon (shared, :8765)                      │
│  AgentNexus Relay  (shared, :9000)                      │
│                                                         │
│  Terminal A            Terminal B            Terminal C   │
│  node mcp             node mcp             node mcp     │
│  --name Planner       --name Coder         --name Reviewer │
│  DID: aaa             DID: bbb             DID: ccc     │
│  ↕ MCP stdio          ↕ MCP stdio          ↕ MCP stdio  │
│  OpenClaw             Claude Code          Cursor        │
└─────────────────────────────────────────────────────────┘
```

```bash
# Step 1: Start shared services (once)
python main.py relay start   # Terminal 1
python main.py node start    # Terminal 2

# Step 2: Each AI app starts its own MCP with bound identity (auto-registers first time)
python main.py node mcp --name "Planner"  --caps "Planning,Schedule"   # Terminal 3 → OpenClaw
python main.py node mcp --name "Coder"    --caps "Code,Debug"          # Terminal 4 → Claude Code
python main.py node mcp --name "Reviewer" --caps "Review,QA"           # Terminal 5 → Cursor
```

Add to each AI app's MCP config — **auto-registers and binds on every startup**:

```json
// Claude Desktop (Planner role)
{ "mcpServers": { "nexus-planner": {
    "command": "python",
    "args": ["/path/to/main.py", "node", "mcp", "--name", "Planner", "--caps", "Planning,Schedule"]
}}}
```

Once bound, Claude skips DID management entirely:

```
"Send the task to Coder"
→ search_agents(keyword="Code")
→ send_message(to_did="bbb", content="Please implement login module")

"Check my inbox"
→ fetch_inbox()    # did auto-filled

"Who am I?"
→ whoami()  → { did: "aaa", profile: { name: "Planner", ... } }
```

---

### Scenario 2: LAN Multi-Machine — One AI App Per Machine

Each machine runs a full AgentNexus node, connected through Relay.

```bash
# Machine A: Relay + Daemon + Designer
python main.py relay start
python main.py node start
python main.py node mcp --name "Designer" --caps "UI,Design"

# Machine B: points to A's Relay
python main.py node relay set-local http://192.168.1.10:9000
python main.py node start
python main.py node mcp --name "Developer" --caps "Code,Backend"
```

---

### Scenario 3: Single Machine, Multiple AI Apps — OpenClaw + Claude Code

Different AI tools on one machine, each with independent identity.

```bash
python main.py relay start
python main.py node start

# OpenClaw config
python main.py node mcp --name "Architect" --caps "Architecture,Design"

# Claude Code config
python main.py node mcp --name "Coder" --caps "Code,Debug,Test"
```

They share the same Daemon but have different DIDs — like two coworkers sharing one mail server with separate mailboxes.

---

### Scenario 4: Personal Assistant + Public Service Agent (WhatsApp Business style)

Your personal AI assistant discovers and uses professional services on the public network.

```bash
# Your machine: start personal assistant
python main.py node mcp --name "MyAssistant" --caps "Chat,Search"

# Publish a service agent (like creating a Business account):
python main.py node mcp \
  --name "TranslateBot" \
  --caps "Translate,Multilingual" \
  --public \
  --desc "Multilingual translation service" \
  --tags "translate,multilingual,official"
# → DID broadcast to federation, globally searchable
```
