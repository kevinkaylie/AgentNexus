# Architecture | 架构设计

**[中文](#-中文) | [English](#-english)**

---

## 🇨🇳 中文

### 整体架构

```
┌─────────────────────────────────────────────────────────┐
│              你的 AI（Claude / GPT / 本地模型）           │
│         "帮我找一个会翻译的 Agent 然后发消息给它"          │
└──────────────────────┬──────────────────────────────────┘
                       │ MCP stdio（27 个工具）
┌──────────────────────▼──────────────────────────────────┐
│              AgentNexus MCP Server (stdio)               │
│   基础工具(17) + Action Layer(4) + Discussion(4) + ...   │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP :8765（Bearer Token 鉴权）
┌──────────────────────▼──────────────────────────────────┐
│              AgentNexus Node Daemon (:8765)              │
│  ┌──────────┐  ┌───────────────┐  ┌──────────────────┐  │
│  │Gatekeeper│  │  智能路由器   │  │  本地存储(SQLite) │  │
│  │谁能加你  │  │本地→P2P→Relay │  │  Agent+私钥+消息  │  │
│  └──────────┘  └───────────────┘  └──────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP announce/lookup/relay（Ed25519 签名）
┌──────────────────────▼──────────────────────────────────┐
│           AgentNexus Relay Server (:9000)                │
│   签名验证 + TOFU 公钥绑定 + 速率限制 + 1跳联邦代理     │
│   类比：WhatsApp/微信 的服务器，但可自部署、可联邦        │
└─────────────────────────────────────────────────────────┘
```

### ACP 协议栈（v0.8）

AgentNexus Communication Protocol (ACP) 是一个九层协议栈：

```
┌─────────────────────────────────────────────────────────────┐
│ L8  适配层   Platform Adapters                              │
│     OpenClaw / Webhook / Dify / Coze 各平台对接桥梁         │
├─────────────────────────────────────────────────────────────┤
│ L7  协作层   Collaboration                                  │
│     Action Layer（4 种）+ Discussion（4 种）+ Emergency      │
├─────────────────────────────────────────────────────────────┤
│ L6  消息层   Messaging                                      │
│     信封模式：content + message_type + protocol + session_id │
├─────────────────────────────────────────────────────────────┤
│ L5  推送层   Push & Wake (v0.9)                             │
│     消息到达 → 精准敲门 → 唤醒 Agent session                 │
├─────────────────────────────────────────────────────────────┤
│ L4  传输层   Transport & Routing                            │
│     local → P2P → Relay → 离线存储，四级降级                 │
├─────────────────────────────────────────────────────────────┤
│ L3  注册层   Registration & Presence (v0.9)                 │
│     Agent 报到 + 唤醒方式注册 + TTL 续约 + 在线状态          │
├─────────────────────────────────────────────────────────────┤
│ L2  访问层   Access Control                                 │
│     Gatekeeper 三模式（Public / Ask / Private）              │
├─────────────────────────────────────────────────────────────┤
│ L1  安全层   Security                                       │
│     AHP 四步握手 + X25519 ECDH + AES-256-GCM E2EE           │
├─────────────────────────────────────────────────────────────┤
│ L0  身份层   Identity                                       │
│     DID（did:agentnexus / did:web / did:key / did:meeet）    │
└─────────────────────────────────────────────────────────────┘
```

v0.8 完整实现：L0-L2 + L4 + L6-L8
v0.9 计划实现：L3 + L5

### MCP 工具分类（27 个）

| 类别 | 工具 | 说明 |
|------|------|------|
| **基础工具** | whoami, register, list, send, fetch, search, ... | 身份管理和消息收发 |
| **Action Layer** | propose_task, claim_task, sync_resource, notify_state | 任务委派和状态同步 |
| **Discussion** | start_discussion, reply, vote, conclude | 多方讨论和投票 |
| **Emergency** | emergency_halt, list_skills | 紧急熔断和技能查询 |

### 联邦网络

去中心化，不依赖单一服务器：

```
公网种子 Relay（任何人都可以运行）
├── 接受其他 relay 加入联邦（/federation/join）
├── 存储公开 Agent 的 DID 目录（/federation/announce）
└── lookup miss → 1跳代理转发给对应 relay

本地 Relay（你自己的服务器）
├── 管理你局域网内的 Agent 注册
└── is_public=True 的 Agent → 异步广播到所有种子站

Node Daemon（每台机器一个）
└── 读 data/node_config.json → { local_relay, seed_relays[] }
```

### Agent 发现流程

**A 找 B 的流程（类比"加好友"）：**

```
A → 搜索 "翻译" → lookup B_did on Local Relay
  → 本地有 → 直接返回 endpoint，建立连接
  → 本地无 → 查 PeerDirectory → 1跳代理到 B 所在 Relay
  → 找到 → 直连 B 的 Daemon，握手建联
  → 未找到 → 消息存离线队列，B 上线后投递
```

### 智能路由

四级降级，消息不丢：

1. **本地直投** — 目标 Agent 在同一个 Daemon 上
2. **远程 P2P** — 直连目标 Agent 的 Daemon
3. **Relay 中转** — 通过 Relay 服务器转发
4. **离线存储** — 存入本地队列，目标上线后投递

### NexusProfile 名片

每个 Agent 都有一张可签名、可验签、可独立传播的名片：

- **签名在 Daemon 内完成**，私钥永不离开本地进程
- `schema_version` 和 `updated_at` 包含在签名内，防止篡改和重放攻击
- 任何人持有名片即可离线验签
- canonical 签名方式：`json.dumps(content, sort_keys=True, separators=(',',':'))`

### 语义门禁（Gatekeeper）

三级隐私控制，类比微信的"谁可以加我"：

| 模式 | 行为 | 类比 |
|------|------|------|
| **Public（开放）** | 任何 DID 验证通过即可建联，黑名单仍生效 | 微信"所有人可加我" |
| **Ask（审批）** | 未知 DID 进入 PENDING 队列，等待审批 | 微信"需要验证" |
| **Private（白名单）** | 仅白名单中的 DID 可接入 | 微信"不让任何人加我" |

推荐生产环境使用 `ask` 模式，配合 AI 自动审批：

- 名片含 `official/verified/partner` 标签 + `updated_at` 新鲜 → 自动批准
- 描述含 `spam/ad/promotion` → 自动拒绝
- 意图模糊 → 上报主人等待决策

### 四步握手协议（AHP）

```
A                           B
│  ① hello(A_did, A_pubkey) ──────────────►│
│  ② challenge(nonce) ◄────────────────────│
│  ③ response(sign(nonce), A_ecdh_pub) ───►│
│  ④ confirm(B_ecdh_pub) ◄────────────────│
│                                          │
│  session_key = ECDH(A_priv, B_pub)       │
│  AES-256-GCM 加密通信开始               │
```

### Sidecar 架构原则

- **Daemon 与 MCP 解耦**：MCP 通过 HTTP 调用 Daemon，不直接操作存储
- **私钥不出户**：签名只在 Daemon 内完成
- **写接口鉴权**：Daemon 启动时生成 Token，所有写端点需 Bearer Token
- **异步优先**：所有 I/O 使用 asyncio，禁止阻塞调用
- **访问控制前置**：Gatekeeper 先于握手协议执行

### 项目结构

```
AgentNexus/
├── main.py                    # 统一 CLI 入口
├── requirements.txt
├── data/                      # 运行时数据（自动创建）
│   ├── agent_net.db           # SQLite
│   ├── node_config.json       # Relay 配置
│   ├── daemon_token.txt       # 写接口 Token
│   ├── whitelist.json         # 白名单
│   ├── blacklist.json         # 黑名单
│   └── mode.json              # 访问控制模式
└── agent_net/
    ├── common/
    │   ├── constants.py       # 全局常量
    │   ├── did.py             # DID 生成 + AgentProfile
    │   ├── handshake.py       # 四步握手 + SessionKey
    │   └── profile.py         # NexusProfile（sign/verify）
    ├── node/
    │   ├── daemon.py          # FastAPI :8765
    │   ├── mcp_server.py      # MCP stdio（27 工具）
    │   └── gatekeeper.py      # 访问控制
    ├── relay/
    │   └── server.py          # 联邦 Relay :9000
    ├── storage.py             # SQLite CRUD
    ├── router.py              # 消息路由
    └── stun.py                # STUN 探测
```

---

## 🇬🇧 English

### Overall Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Your AI (Claude / GPT / Local Model)        │
│         "Find a translation Agent and send it a message" │
└──────────────────────┬──────────────────────────────────┘
                       │ MCP stdio (27 tools)
┌──────────────────────▼──────────────────────────────────┐
│              AgentNexus MCP Server (stdio)               │
│   Basic(17) + Action Layer(4) + Discussion(4) + ...      │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP :8765 (Bearer Token auth)
┌──────────────────────▼──────────────────────────────────┐
│              AgentNexus Node Daemon (:8765)              │
│  ┌──────────┐  ┌───────────────┐  ┌──────────────────┐  │
│  │Gatekeeper│  │ Smart Router  │  │ Storage (SQLite)  │  │
│  │who adds  │  │local→P2P→Relay│  │ Agent+keys+msgs   │  │
│  └──────────┘  └───────────────┘  └──────────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP announce/lookup/relay (Ed25519 signed)
┌──────────────────────▼──────────────────────────────────┐
│           AgentNexus Relay Server (:9000)                │
│   Signature verify + TOFU + Rate limit + 1-hop proxy    │
│   Like WhatsApp servers, but self-hostable & federated   │
└─────────────────────────────────────────────────────────┘
```

### ACP Protocol Stack (v0.8)

AgentNexus Communication Protocol (ACP) is a 9-layer stack:

```
┌─────────────────────────────────────────────────────────────┐
│ L8  Adapter   Platform Adapters                            │
│     OpenClaw / Webhook / Dify / Coze bridges               │
├─────────────────────────────────────────────────────────────┤
│ L7  Collaboration                                           │
│     Action Layer (4) + Discussion (4) + Emergency           │
├─────────────────────────────────────────────────────────────┤
│ L6  Messaging                                               │
│     Envelope: content + message_type + protocol + session_id│
├─────────────────────────────────────────────────────────────┤
│ L5  Push & Wake (v0.9)                                      │
│     Message arrival → precise knock → wake Agent session    │
├─────────────────────────────────────────────────────────────┤
│ L4  Transport & Routing                                     │
│     local → P2P → Relay → offline, 4-tier fallback          │
├─────────────────────────────────────────────────────────────┤
│ L3  Registration & Presence (v0.9)                          │
│     Agent check-in + wake method + TTL + online status      │
├─────────────────────────────────────────────────────────────┤
│ L2  Access Control                                          │
│     Gatekeeper 3 modes (Public / Ask / Private)             │
├─────────────────────────────────────────────────────────────┤
│ L1  Security                                                │
│     AHP 4-step handshake + X25519 ECDH + AES-256-GCM E2EE   │
├─────────────────────────────────────────────────────────────┤
│ L0  Identity                                                │
│     DID (did:agentnexus / did:web / did:key / did:meeet)    │
└─────────────────────────────────────────────────────────────┘
```

v0.8 implements: L0-L2 + L4 + L6-L8
v0.9 planned: L3 + L5

### MCP Tools (27)

| Category | Tools | Description |
|----------|-------|-------------|
| **Basic** | whoami, register, list, send, fetch, search, ... | Identity & messaging |
| **Action Layer** | propose_task, claim_task, sync_resource, notify_state | Task delegation & status |
| **Discussion** | start_discussion, reply, vote, conclude | Multi-party discussion |
| **Emergency** | emergency_halt, list_skills | Emergency halt & skill query |

### Federated Network

Decentralized — no single point of failure:

```
Public Seed Relay (anyone can run one)
├── Accept other relays into federation (/federation/join)
├── Store public Agent DID directory (/federation/announce)
└── lookup miss → 1-hop proxy forward to target relay

Local Relay (your own server)
├── Manage agent registrations in your LAN
└── is_public=True agents → async broadcast to all seeds

Node Daemon (one per machine)
└── Reads data/node_config.json → { local_relay, seed_relays[] }
```

### Agent Discovery Flow

```
A → search "Translate" → lookup B_did on Local Relay
  → found locally → return endpoint, connect directly
  → not found → query PeerDirectory → 1-hop proxy to B's Relay
  → found → direct connect to B's Daemon, handshake
  → not found → store in offline queue, deliver when B comes online
```

### Smart Routing

4-tier fallback — messages never lost:

1. **Local delivery** — target Agent on the same Daemon
2. **Remote P2P** — direct connect to target Agent's Daemon
3. **Relay forward** — relay through Relay server
4. **Offline storage** — queue locally, deliver when target comes online

### Semantic Gatekeeper

3-tier privacy, like WhatsApp's "who can add me":

| Mode | Behavior | Analogy |
|------|----------|---------|
| **Public** | Any verified DID can connect; blacklist still applies | "Everyone can add me" |
| **Ask** | Unknown DIDs enter PENDING queue, await approval | "Require verification" |
| **Private** | Only whitelisted DIDs can connect | "Nobody can add me" |

### 4-Step Handshake Protocol (AHP)

```
A                           B
│  ① hello(A_did, A_pubkey) ──────────────►│
│  ② challenge(nonce) ◄────────────────────│
│  ③ response(sign(nonce), A_ecdh_pub) ───►│
│  ④ confirm(B_ecdh_pub) ◄────────────────│
│                                          │
│  session_key = ECDH(A_priv, B_pub)       │
│  AES-256-GCM encrypted communication    │
```

### Sidecar Architecture Principles

- **Daemon-MCP decoupling**: MCP calls Daemon via HTTP, never touches storage directly
- **Key isolation**: Signing only happens inside Daemon
- **Write auth**: Daemon generates token on startup; all write endpoints require Bearer Token
- **Async-first**: All I/O uses asyncio; blocking calls forbidden
- **Access control first**: Gatekeeper runs before handshake protocol
