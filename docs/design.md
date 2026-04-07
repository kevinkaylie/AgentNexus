# AgentNexus 设计文档

> 本文件按版本组织技术设计方案。随开发推进逐步细化。
> 已实现的架构参考 [architecture.md](architecture.md)，关键决策参考 [ADR](adr/)。

---

## v0.7.x — 基础设施层 ✅

> 已实现。详细设计参考：
> - [架构文档](architecture.md) — 整体架构、联邦网络、智能路由、Gatekeeper、握手协议
> - [API 参考](api-reference.md) — Relay API、Daemon API、密码学实现、数据库 Schema
> - [DID 方法规范](did-method-spec.md) — did:agentnexus 规范
> - [ADR-001 ~ ADR-005](adr/) — 五个核心架构决策

---

## v0.8.0 — SDK 基础 + 协作协议（Action Layer）

### 整体架构

```
外部 Agent（Python 代码 / OpenClaw / Dify）
  └── agentnexus-sdk（pip install）
        └── AgentNexusClient
              ├── 基础 API（connect/send/on_message/verify/certify）
              └── Action Layer（task_propose/task_claim/resource_sync/state_notify）
                    └── localhost:8765（Node Daemon）
                          └── 注册 DID → 收发消息 → 信任查询 → 协作动作
```

SDK 是 Daemon HTTP API 的轻量封装 + 协作协议的客户端实现。遵循 Sidecar 架构原则（[ADR-003](adr/003-sidecar-architecture.md)）：
- SDK 不持有私钥（主权隔离）
- SDK 不触碰外部平台 API Key
- 所有安全敏感操作委托给 Daemon

### SDK 包结构

```
agentnexus-sdk/
├── pyproject.toml
├── src/
│   └── agentnexus/
│       ├── __init__.py          # 导出 connect()
│       ├── client.py            # AgentNexusClient 核心类
│       ├── actions.py           # Action Layer（四种协作动作）
│       ├── models.py            # 数据模型（Message, Action, Verification 等）
│       ├── discovery.py         # Daemon 自动发现（零配置）
│       ├── exceptions.py        # 异常定义
│       └── sync.py              # 同步包装器
├── examples/
│   ├── echo_bot.py              # 回声机器人
│   └── team_collab.py           # 团队协作 demo（Action Layer）
└── tests/
```

### 核心 API 设计

```python
import agentnexus

# 一行接入（零配置）
nexus = agentnexus.connect("MyAgent", caps=["Chat", "Search"])

# ── 基础消息 ──
await nexus.send(to_did="did:agentnexus:z6Mk...", content="Hello!")

@nexus.on_message
async def handle(msg):
    print(f"From {msg.from_did}: {msg.content}")

# ── 信任查询 ──
result = await nexus.verify("did:agentnexus:z6Mk...")

# ── 协作动作（Action Layer）──
# 发布任务
await nexus.propose_task(
    to_did="did:agentnexus:z6Mk...",
    task={"title": "实现登录模块", "deadline": "2026-04-10", "required_caps": ["Code"]},
)

# 认领任务
await nexus.claim_task(task_id="task_abc123", eta="2026-04-08")

# 同步状态（Key-Value）
await nexus.sync_resource(key="design_v2", value={"status": "approved", "url": "..."})

# 汇报进度
await nexus.notify_state(task_id="task_abc123", status="in_progress", progress=0.6)
```

### Action Layer 消息格式（信封模式）

在现有 `send_message` 基础上扩展，不是独立协议层：

```json
{
  "from_did": "did:agentnexus:z6Mk...",
  "to_did": "did:agentnexus:z6Mk...",
  "content": {
    "title": "实现登录模块",
    "deadline": "2026-04-10",
    "required_caps": ["Code"]
  },
  "message_type": "task_propose",
  "protocol": "nexus_v1",
  "session_id": "sess_abc123"
}
```

四种动作类型的 content 结构：

| message_type | content 字段 | 说明 |
|-------------|-------------|------|
| `task_propose` | `{title, description?, deadline?, required_caps?, priority?}` | 发布/委派任务 |
| `task_claim` | `{task_id, eta?, message?}` | 认领/响应任务 |
| `resource_sync` | `{key, value, version?}` | 共享 K-V 数据更新 |
| `state_notify` | `{task_id?, status, progress?, error?}` | 心跳/完成/报错 |

`status` 枚举：`pending` / `in_progress` / `completed` / `failed` / `blocked`

SDK 接收端逻辑：
- `message_type` 为空或非 `nexus_v1` 协议 → 自由文本，直接交给 `on_message` 回调
- `message_type` 为四种动作之一 → 进入 SDK 任务状态机，触发对应的 `on_task_propose` / `on_task_claim` 等回调

### 多层递归路由

```
L1 (Local)  → 进程间通信，数据不出机器（现有 router.py local 路径）
L2 (LAN)    → 局域网 Relay 查询（现有 relay lookup 路径）
L3 (Global) → 种子 Relay 跨网穿透 + 异步邮局（现有 federation 路径）
```

这三层已在现有路由器中实现（local → p2p → relay → offline），v0.8 的工作是在 SDK 层面暴露路由层级信息，让开发者可以感知消息走了哪条路径。

### 异步模型

- 核心 API 使用 `async/await`（与 Daemon 的 asyncio 架构一致）
- 提供同步包装器 `agentnexus.sync.connect()` 供非异步场景使用
- `on_message` / `on_task_propose` 等回调在后台 asyncio 任务中运行

### Daemon 自动发现

```python
# 发现优先级：
# 1. 显式参数: connect(daemon_url="http://...")
# 2. 环境变量: AGENTNEXUS_DAEMON_URL
# 3. 默认值: http://localhost:8765

# 发现流程：
# 1. 尝试 GET /health
# 2. 成功 → 返回连接
# 3. 失败 → 抛出 DaemonNotFoundError
```

### 平台适配器设计

#### OpenClaw Skill

```
OpenClaw Agent
  └── AgentNexus Skill（Python 包）
        └── 内部使用 agentnexus-sdk
              └── 消息转发：OpenClaw 消息 ↔ AgentNexus 消息
```

#### Webhook 通用桥接

```
Dify/Coze Agent
  └── 配置 Webhook URL: http://localhost:8765/webhook/{did}
        └── Daemon 接收 Webhook → 转为 AgentNexus 消息
        └── AgentNexus 消息 → 回调 Webhook URL
```

Daemon 新增端点：
- `POST /webhook/{did}` — 接收外部平台 Webhook 消息
- `POST /webhook/{did}/config` — 配置回调 URL

### did:meeet 互操作（R-0809 + R-0811 + R-0812）

MEEET 平台有 1020 个 Agent 使用 `did:meeet:agent_{uuid}` 格式。采用映射模式（不生成新密钥，不托管私钥）。

解析流程：

```
GET /resolve/did:meeet:agent_xxx
  ↓
Relay DIDResolver._resolve_meeet()
  ↓
查询 MEEET Solana state API → 获取 Ed25519 公钥 + reputation score
  ↓
复用 MEEET Ed25519 公钥 → 生成对应 did:agentnexus
  ↓
构建 DID Document（含 AgentService + meeet_reputation_score + x402_score）
```

桥接映射（Redis 持久化）：

```
relay:meeet:{did:meeet:agent_xxx} → {
  "agentnexus_did": "did:agentnexus:z6Mk...",
  "pubkey_hex": "<ed25519_hex>",
  "meeet_reputation": 500,
  "x402_score": 72,
  "registered_at": 1711000000.0
}
```

批量注册流程：
1. MEEET agent 用 Ed25519 私钥签名 nonce → 证明 did:meeet 所有权
2. Relay 从 MEEET 公钥推导 did:agentnexus（`did:agentnexus:z` + base58btc(0xED01 || pubkey)）
3. 写入映射表 + 注册到 ANPN directory
4. x402 payer 通过 did:agentnexus 发现 Agent

Trust Grade 映射（v0.8 短期方案）：

| MEEET Reputation | x402 Score | 说明 |
|-----------------|------------|------|
| 0 (NEW)         | ~10        | 新注册，最低信任 |
| 200 (BEGINNER)  | ~45        | 有基础交互历史 |
| 500             | ~72        | 活跃用户 |
| 850+ (EXPERT)   | ~92+       | 专家级，高信任 |

映射公式（线性插值）：`x402_score = 10 + (meeet_reputation / 850) * 82`，上限 100。

v0.9 长期方案：reputation 映射到 `trust_score` 的 `behavior_delta` 分量，与 L 级信任体系解耦。

实现位置：
- `agent_net/common/did.py` — `DIDResolver` 新增 `_resolve_meeet()` 方法
- `agent_net/relay/server.py` — `/resolve/{did}` 新增 meeet 分支 + 批量注册端点
- metadata 字段：`{"source": "meeet_solana", "meeet_reputation_score": 500, "x402_score": 72}`

### AgentService 端点补全（R-0810）

当前 DID Document service 类型：
- `AgentRelayService` — Relay 自身（`/.well-known/did.json`）
- `AgentRelay` — Agent 关联的 Relay 地址
- `AgentEndpoint` — Agent 的 P2P 直连地址

新增：
- `AgentService` — Agent 的可调用服务端点（MCP stdio / ANPN 协议）

```json
{
  "service": [
    {"id": "#relay", "type": "AgentRelay", "serviceEndpoint": "https://relay.agentnexus.top"},
    {"id": "#agent", "type": "AgentEndpoint", "serviceEndpoint": "http://192.168.1.10:8765"},
    {"id": "#mcp", "type": "AgentService", "serviceEndpoint": "stdio://agentnexus-mcp", "protocol": "mcp/1.0"},
    {"id": "#anpn", "type": "AgentService", "serviceEndpoint": "https://relay.agentnexus.top/relay/anpn-lookup/{did}/anpn", "protocol": "anpn/1.0"}
  ]
}
```

实现位置：
- `agent_net/common/did.py` — `build_services_from_profile()` 新增 AgentService 生成逻辑
- `agent_net/relay/server.py` — `_build_relay_did_document()` 保持 `AgentRelayService` 不变

### 错误处理

| 异常 | 场景 | 处理 |
|------|------|------|
| `DaemonNotFoundError` | Daemon 未启动或不可达 | 提示启动命令 |
| `AuthenticationError` | Token 无效或缺失 | 提示检查 daemon_token.txt |
| `AgentNotFoundError` | DID 不存在 | 提示注册或检查 DID |
| `MessageDeliveryError` | 消息投递失败 | 返回路由方法和失败原因 |
| `InvalidActionError` | Action Layer 消息格式错误 | 返回字段校验详情 |

---

## v0.8.5 — Relay Vault + Enclave 群组

### Relay Vault 架构

```
Agent A ──┐
Agent B ──┼── Enclave "project-x" ── Vault (Redis DB 1, 持久化)
Agent C ──┘                           ├── key: "design_v2" → {status, url}
                                      ├── key: "task_board" → [{...}, {...}]
                                      └── ACL: {architect: rw, developer: r, reviewer: r}
```

- Vault 是 Enclave 级别的共享 Key-Value 存储
- MVP 使用 Redis 持久化模式（独立 DB 1，关闭自动过期）
- 使用 Redis Hashes 或 JSON 模块存储
- 长期迁移到 PostgreSQL (JSONB) 或 MongoDB（支持复杂 ACL 查询和版本回溯）

### Enclave 群组

- 创建 Enclave 时指定成员 DID 列表和角色分配
- Enclave 内成员共享同一个 Vault 命名空间
- 支持 Enclave 级别的消息广播（群发）
- 成员加入/退出需要管理者 DID 签名授权

### 基于 DID 的 RBAC

```python
enclave_config = {
    "name": "project-x",
    "roles": {
        "architect": {"permissions": ["vault:read", "vault:write", "task:propose"]},
        "developer": {"permissions": ["vault:read", "task:claim", "state:notify"]},
        "reviewer":  {"permissions": ["vault:read", "task:propose"]},
    },
    "members": {
        "did:agentnexus:z6Mk_architect": "architect",
        "did:agentnexus:z6Mk_developer": "developer",
    }
}
```

权限检查在 Relay 层执行，防止搬砖工 Agent 篡改架构师 Agent 的设计稿。

---

## v0.9.0 — 信任传递 & 声誉 + Output Provenance

### Output Provenance（输出溯源）

每条消息携带 `trust_context` 元数据：

```json
{
  "from_did": "...",
  "content": "翻译结果：...",
  "trust_context": {
    "source_tier": "T2",
    "evidence_chain": [
      {"type": "database", "source": "did:agentnexus:z6Mk_dict_service", "confidence": 0.95},
      {"type": "model_inference", "model": "gpt-4", "confidence": 0.7}
    ],
    "overall_confidence": 0.82
  }
}
```

来源分级：
- T1：原始事实（数据库查询、官方文件、链上数据）
- T2：经验证的二手信息（已验签的 Agent 转述）
- T3：聚合推理（多源综合，有部分推理）
- T4：单源推理（基于单一模型输出）
- T5：纯模型推理（无外部验证，幻觉风险最高）

统计层：Relay 记录 Agent 产生的 T1~T5 比例，沉淀为 Profile 中的"可靠性权重"。

### trust_score 计算重构

```
当前：trust_score = base_score(trust_level) + live_bonus
目标：trust_score = base_score(L级) + behavior_delta + attestation_bonus + provenance_weight
```

- `behavior_delta`：基于交互历史（成功率、响应速度）的动态加减分
- `attestation_bonus`：OATR JWT attestation 的评分加成
- `provenance_weight`：基于 T1~T5 比例的可靠性权重
- 兼容 OATR 0-100 连续评分体系

### JWT Attestation 验证

- 新增 `verify_jwt_attestation()` 函数
- 与现有 `verify_certification()` 并行
- 支持 EdDSA (Ed25519) 签名的 compact JWT
- trust_snapshot 导出为 OATR 标准格式
- Certification ↔ JWT 双向桥接
- 参考：[OATR 接口契约](contracts/oatr-jwt-attestation.md)

---

## v1.0.0+ — 桌面应用及后续

> 设计待定义。参考 [roadmap.md](roadmap.md)。
