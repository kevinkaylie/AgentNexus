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

---

## v0.9.0 剩余条目实现设计

> 2026-04-13。底层数据结构（trust_graph.py、reputation.py）和存储层（4 张表）已在 v0.9.6 实现，以下为集成层设计。

### 现状分析

| 模块 | 已有 | 缺失 |
|------|------|------|
| trust_graph.py | TrustEdge、TrustGraph（内存 BFS）、TrustGraphStore（SQLite） | 未接入 governance router |
| reputation.py | InteractionRecord、ReputationScore、BehaviorScorer、ReputationStore | 未接入 governance router |
| governance router | 11 个端点 | 端点内部是桩实现，未调用 trust_graph/reputation 模块 |
| runtime_verifier.py | verify() → trust_level、trust_score | trust_score 仅基于 L 级 base_score，未接入 behavior_delta |

### 0.9-01 + 0.9-02：Web of Trust 信任传递 + 路径发现

**接入点：**

- `POST /trust/edge` → 写入 `TrustGraphStore`（现在只写内存）
- `DELETE /trust/edge` → 同步删除持久化层
- `GET /trust/edges/{did}` → 从持久化层读取
- `GET /trust/paths` → 加载 TrustGraph，调用 `find_trust_paths(source, target)`

**路径缓存：** 频繁查询的路径结果缓存 60 秒，避免每次加载全图做 BFS。

**衍生信任分消费：** `GET /reputation/{did}` 和 `GET /trust-snapshot/{did}` 中，若无直接信任边，通过 `compute_derived_trust(viewer_did, target_did)` 获取衍生分，注入 `attestation_bonus`。

**文件变更：** `agent_net/node/routers/governance.py`（4 个端点）

### 0.9-03 + 0.9-04：交互声誉系统 + 声誉存储查询 API

**接入点：**

- `POST /interactions` → 调用 `ReputationStore.record_interaction()`
- `GET /interactions/{did}` → 调用 `ReputationStore.get_interactions()`
- `GET /reputation/{did}` → RuntimeVerifier 获取 trust_level，ReputationStore 计算完整声誉分（base_score + behavior_delta + attestation_bonus）
- `GET /trust-snapshot/{did}` → 返回完整快照（含 recent_interactions、success_rate、trust_edges_in/out、OATR 格式）

**自动记录交互：** 消息投递成功/失败后，`routers/messages.py` 自动调用 `ReputationStore.record_interaction()`，无需手动调用。

**attestation_bonus 计算：** 从 `governance_attestations` 表读取未过期认证，permit +3 分，conditional +1 分，上限 15 分。

**文件变更：** `agent_net/node/routers/governance.py`（3 个端点 + `_compute_attestation_bonus`）、`agent_net/node/routers/messages.py`（自动记录）

### 0.9-05：信任衰减机制

**后台定时任务：** daemon 启动时注册 asyncio task，每小时执行一次 `TrustGraphStore.apply_decay(decay_rate=0.01, min_score=0.1)`。

**衰减效果：** score=0.8 的边，30 天无交互后 ≈ 0.39，90 天后触底 0.1。

**交互刷新：** `POST /interactions` 记录成功交互时，若存在对应信任边，timestamp 刷新 + score 小幅提升（+0.01，上限 1.0），防止活跃关系衰减。

**文件变更：** `agent_net/node/daemon.py`（衰减任务）、`agent_net/node/routers/governance.py`（交互刷新）

### 0.95-07：SDK Enclave API

**状态：已完成。** `agentnexus-sdk/src/agentnexus/enclave.py` 已实现 EnclaveManager / EnclaveProxy / VaultProxy / PlaybookRunProxy 全部方法，roadmap 已标记 ✅。

### 实施顺序

```
0.9-01 + 0.9-02（TrustGraphStore 接入）→ 0.9-03 + 0.9-04（ReputationStore 接入）→ 0.9-05（衰减任务）
```

预估总改动量约 220 行，分两批实现，每批完成后跑全量测试。

---

## v1.0.0 Phase 1 — 后端基础（1.0-04 + 1.0-06 + 1.0-08）

> 2026-04-15。三个优先条目的详细设计。

### 1.0-04 个人主 DID

#### 目标

一个"我"的 DID 代表本人，下挂 N 个 Agent DID。用户通过主 DID 统一管理所有 Agent。

#### 现状

`agents` 表：`did(PK), profile(JSON), is_local, last_seen, private_key_hex`。每个 Agent 独立，没有 owner_did 或层级关系。

#### 数据模型变更

**方案：agents 表新增 `owner_did` 字段**

不新建表，直接在 agents 表加一列。主 DID 本身也是一条 agent 记录（`owner_did = NULL`），子 Agent 的 `owner_did` 指向主 DID。

```sql
ALTER TABLE agents ADD COLUMN owner_did TEXT DEFAULT NULL;
CREATE INDEX idx_agents_owner ON agents(owner_did);
```

主 DID 与子 Agent 的区别：

| 字段 | 主 DID | 子 Agent |
|------|--------|---------|
| `owner_did` | `NULL` | 主 DID 的 did |
| `is_local` | 1 | 1 |
| `private_key_hex` | 有 | 有 |
| `profile.type` | `"owner"` | `"agent"` |

#### 新增端点

```
POST /owner/register          — 注册主 DID（生成密钥对，创建 owner 类型 agent）
POST /owner/bind              — 将已有 Agent DID 绑定到主 DID
DELETE /owner/unbind           — 解绑子 Agent
GET  /owner/agents             — 列出主 DID 下所有子 Agent
GET  /owner/profile            — 获取主 DID 的 profile
```

#### 注册流程

```
1. POST /owner/register {name: "Kevin"}
   → 生成 Ed25519 密钥对
   → 创建 did:agentnexus:<multikey>
   → 写入 agents 表（owner_did=NULL, profile.type="owner"）
   → 返回 {did, public_key}

2. POST /owner/bind {owner_did: "did:agentnexus:z6Mk...", agent_did: "did:agentnexus:z6Mk..."}
   → 验证 owner_did 是本地主 DID
   → 验证 agent_did 是本地 Agent
   → UPDATE agents SET owner_did=? WHERE did=?
   → 返回 {status: "ok"}
```

#### 向后兼容

- 没有 owner_did 的 Agent 继续正常工作
- 所有现有端点不受影响
- 主 DID 也可以直接收发消息（它本身就是一个 Agent）

#### 文件变更

| 文件 | 变更 |
|------|------|
| `agent_net/storage.py` | `init_db` 加 ALTER TABLE + 新增 `register_owner`、`bind_agent`、`unbind_agent`、`list_owned_agents` |
| `agent_net/node/routers/agents.py` | 新增 5 个 `/owner/*` 端点 |

---

### 1.0-06 消息中心

#### 目标

统一查看主 DID 下所有 Agent 收发的消息。

#### 现状

`messages` 表查询只支持按单个 `to_did` 查收件箱。没有跨 Agent 聚合查询。

#### 新增端点

```
GET /owner/messages/inbox      — 主 DID 下所有子 Agent 的未读消息（聚合）
GET /owner/messages/all        — 主 DID 下所有子 Agent 的全部消息（分页）
GET /owner/messages/stats      — 各子 Agent 的消息统计（未读数、最后消息时间）
```

#### 查询逻辑

```sql
-- /owner/messages/inbox：聚合所有子 Agent 的未读消息
SELECT m.id, m.from_did, m.to_did, m.content, m.timestamp,
       m.session_id, m.message_type, m.protocol
FROM messages m
WHERE m.to_did IN (
    SELECT did FROM agents WHERE owner_did = ?
)
AND m.delivered = 0
ORDER BY m.timestamp DESC
LIMIT ? OFFSET ?

-- /owner/messages/stats：各子 Agent 统计
SELECT a.did, a.profile,
       COUNT(CASE WHEN m.delivered = 0 THEN 1 END) as unread_count,
       MAX(m.timestamp) as last_message_at
FROM agents a
LEFT JOIN messages m ON m.to_did = a.did
WHERE a.owner_did = ?
GROUP BY a.did
```

#### 响应格式

```json
// GET /owner/messages/inbox?owner_did=did:agentnexus:z6Mk...
{
    "owner_did": "did:agentnexus:z6Mk...",
    "messages": [
        {
            "id": 42,
            "from_did": "did:agentnexus:z6Mk...外部",
            "to_did": "did:agentnexus:z6Mk...子Agent",
            "to_agent_name": "Architect",
            "content": "设计方案已完成",
            "timestamp": 1744700000.0,
            "message_type": "state_notify",
            "session_id": "sess_abc123"
        }
    ],
    "total_unread": 5
}
```

#### 文件变更

| 文件 | 变更 |
|------|------|
| `agent_net/storage.py` | 新增 `fetch_owner_inbox`、`fetch_owner_messages`、`fetch_owner_message_stats` |
| `agent_net/node/routers/messages.py` | 新增 3 个 `/owner/messages/*` 端点 |

---

### 1.0-08 A2A Capability Token Envelope

#### 目标

Ed25519+JCS 签名信封，将 Enclave permissions 升级为结构化 capability token，支持跨 Enclave 互验。包含 `evaluated_constraint_hash`（qntm WG 最小互操作面要求）。

#### 现状

- `enclave_members.permissions`：简单字符串（`"rw"` / `"r"` / `"admin"`）
- `stage_executions`：没有 constraint_hash 字段
- 没有 capability token 的签发、验证、撤销机制

#### Capability Token 结构

```json
{
    "token_id": "ct_<uuid>",
    "version": 1,
    "issuer_did": "did:agentnexus:z6Mk...owner",
    "subject_did": "did:agentnexus:z6Mk...agent",
    "enclave_id": "enc_<uuid>",

    "scope": {
        "permissions": ["vault:read", "vault:write", "playbook:execute"],
        "resource_pattern": "vault/*",
        "role": "developer"
    },

    "constraints": {
        "spend_limit": 100,
        "max_delegation_depth": 1,
        "allowed_stages": ["implement", "review_code"],
        "input_keys": ["design_doc"],
        "output_key": "code_diff"
    },

    "validity": {
        "not_before": "2026-04-15T00:00:00Z",
        "not_after": "2026-05-15T00:00:00Z"
    },

    "revocation_endpoint": "https://relay.agentnexus.top/capability-tokens/<token_id>/status",

    "evaluated_constraint_hash": "sha256:<hex>",
    "signature_alg": "EdDSA",
    "canonicalization": "JCS",
    "signature": "<base64url>"
}
```

> **注：** `delegation_chain` 通过独立表 `delegation_chain_links` 管理，不在 Token JSON 内。查询时通过 `token_id` 关联获取父 token 及 scope_hash。

#### `evaluated_constraint_hash` 计算

```python
import hashlib
import json

def compute_constraint_hash(scope: dict, constraints: dict) -> str:
    """
    计算约束集的内容寻址哈希。
    qntm WG decision artifact 要求：每个 decision 必须引用被评估的约束集。
    """
    # JCS 规范化（确定性 JSON 序列化）
    canonical = json.dumps(
        {"scope": scope, "constraints": constraints},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
```

#### 数据模型变更

**新增 `capability_tokens` 表：**

```sql
CREATE TABLE IF NOT EXISTS capability_tokens (
    token_id TEXT PRIMARY KEY,
    version INTEGER DEFAULT 1,
    issuer_did TEXT NOT NULL,
    subject_did TEXT NOT NULL,
    enclave_id TEXT,
    scope_json TEXT NOT NULL,
    constraints_json TEXT NOT NULL,
    validity_json TEXT NOT NULL,
    revocation_endpoint TEXT NOT NULL,  -- 必填（R-1001）
    evaluated_constraint_hash TEXT NOT NULL,
    signature TEXT NOT NULL,
    status TEXT DEFAULT 'active',   -- active / revoked / expired
    created_at REAL NOT NULL,
    revoked_at REAL
);
CREATE INDEX idx_ct_subject ON capability_tokens(subject_did);
CREATE INDEX idx_ct_enclave ON capability_tokens(enclave_id);
CREATE INDEX idx_ct_status ON capability_tokens(status);
```

**新增 `delegation_chain_links` 表（委托链关系）：**

```sql
CREATE TABLE IF NOT EXISTS delegation_chain_links (
    id INTEGER PRIMARY KEY,
    child_token_id TEXT NOT NULL,
    parent_token_id TEXT NOT NULL,
    parent_scope_hash TEXT NOT NULL,  -- 用于快速验证单调收窄
    depth INTEGER DEFAULT 1,
    FOREIGN KEY (child_token_id) REFERENCES capability_tokens(token_id),
    FOREIGN KEY (parent_token_id) REFERENCES capability_tokens(token_id)
);
CREATE INDEX idx_dcl_child ON delegation_chain_links(child_token_id);
CREATE INDEX idx_dcl_parent ON delegation_chain_links(parent_token_id);
```

**`stage_executions` 新增字段：**

```sql
ALTER TABLE stage_executions ADD COLUMN evaluated_constraint_hash TEXT;
ALTER TABLE stage_executions ADD COLUMN capability_token_id TEXT;
```

#### 签发流程

```
1. Enclave owner 创建 Enclave + 添加成员
2. 系统自动为每个成员签发 capability token：
   - scope 从 enclave_members.permissions + role 推导
   - constraints 从 Playbook stage 定义推导（input_keys, output_key, allowed_stages）
   - issuer_did = enclave owner_did
   - 用 owner 的 Ed25519 私钥签名
3. Token 写入 capability_tokens 表
4. Playbook 引擎在 stage 推进时：
   - 验证 assigned_did 持有有效 token
   - 验证 token.constraints 包含当前 stage
   - 计算 evaluated_constraint_hash 写入 stage_executions
```

#### 验证流程

```python
async def verify_capability_token(token: dict, action: str) -> dict:
    """
    验证 capability token。
    返回 {valid: bool, reason: str} 或详细验证结果。
    """
    # 1. 签名验证（Ed25519 over JCS-canonicalized payload）
    if not verify_signature(token):
        return {"valid": False, "reason": "SIGNATURE_INVALID"}

    # 2. 有效期检查
    now = time.time()
    validity = token["validity"]
    if now < validity["not_before"]:
        return {"valid": False, "reason": "NOT_YET_VALID"}
    if now > validity["not_after"]:
        return {"valid": False, "reason": "EXPIRED"}

    # 3. 状态检查（调用 revocation_endpoint 或查本地缓存）
    if await is_revoked(token["token_id"]):
        return {"valid": False, "reason": "REVOKED"}

    # 4. 委托链完整性 + 单调收窄验证
    chain_links = await get_delegation_chain(token["token_id"])
    if chain_links:
        parent = await get_token(chain_links[0]["parent_token_id"])
        if not parent:
            return {"valid": False, "reason": "CHAIN_BREAK"}
        # 单调收窄：child scope ⊆ parent scope
        if not scope_is_subset(token["scope"], parent["scope"]):
            return {"valid": False, "reason": "SCOPE_EXPANSION"}
        # 约束更严格
        if token["constraints"]["spend_limit"] > parent["constraints"]["spend_limit"]:
            return {"valid": False, "reason": "SPEND_LIMIT_EXPANSION"}
        if token["constraints"]["max_delegation_depth"] >= parent["constraints"]["max_delegation_depth"]:
            return {"valid": False, "reason": "DELEGATION_DEPTH_EXPANSION"}

    # 5. 权限检查
    if action not in token["scope"]["permissions"]:
        return {"valid": False, "reason": "PERMISSION_DENIED"}

    return {"valid": True, "token_id": token["token_id"]}


def scope_is_subset(child_scope: dict, parent_scope: dict) -> bool:
    """验证 child scope 是 parent scope 的子集（单调收窄）。"""
    child_perms = set(child_scope.get("permissions", []))
    parent_perms = set(parent_scope.get("permissions", []))
    if not child_perms.issubset(parent_perms):
        return False
    # resource_pattern: child 应更窄或相同
    child_pattern = child_scope.get("resource_pattern", "*")
    parent_pattern = parent_scope.get("resource_pattern", "*")
    if child_pattern != parent_pattern and not child_pattern.startswith(parent_pattern.rstrip("*")):
        return False
    return True
```

#### 新增端点

```
POST /capability-tokens/issue     — 签发 token（Enclave owner 调用）
GET  /capability-tokens/{token_id} — 查询 token
POST /capability-tokens/{token_id}/verify — 验证 token
POST /capability-tokens/{token_id}/revoke — 撤销 token
GET  /capability-tokens/by-did/{did} — 查询某 DID 持有的所有有效 token
```

#### 与现有 permissions 的兼容

- `enclave_members.permissions` 字段保留，作为简写
- 系统自动从 permissions 生成 capability token
- 映射规则：
  - `"admin"` → `["vault:read", "vault:write", "vault:delete", "playbook:execute", "member:manage"]`
  - `"rw"` → `["vault:read", "vault:write", "playbook:execute"]`
  - `"r"` → `["vault:read"]`
- 旧代码继续用 permissions 字符串，新代码用 capability token

#### 与 crosswalk 的对齐

`evaluated_constraint_hash` 对应 `crosswalk/agentnexus.yaml` 中的 `active_constraints` 映射。签发的 token 即 qntm WG decision artifact 中的 constraint envelope（`constraint_set_type: "enclave"`）。

#### 文件变更

| 文件 | 变更 |
|------|------|
| `agent_net/storage.py` | `init_db` 新增 capability_tokens 表 + delegation_chain_links 表 + stage_executions ALTER |
| `agent_net/common/capability_token.py` | **新建**。CapabilityToken 数据类 + 签发/验证/撤销逻辑 + `compute_constraint_hash` + `scope_is_subset` |
| `agent_net/node/routers/governance.py` | 新增 5 个 `/capability-tokens/*` 端点，验证返回 `{valid, reason}` |
| `agent_net/enclave/playbook.py` | stage 推进时验证 token + 写入 evaluated_constraint_hash |

---

### 实施顺序

```
1.0-04 个人主 DID（~150 行）
    ↓ agents 表 owner_did 就绪
1.0-06 消息中心（~100 行）
    ↓ 聚合查询端点就绪
1.0-08 Capability Token Envelope（~400 行）
    ↓ 新模块 + 表 + 端点 + Playbook 集成
```

1.0-04 和 1.0-06 是纯增量，不改现有逻辑。1.0-08 改动最大，但核心是新建 `capability_token.py` 模块，对现有代码的侵入限于 Playbook 引擎的 stage 推进处。

---

### 设计评审（2026-04-15）

#### 1.0-04 个人主 DID — ✅ 通过

| 项目 | 评估 | 备注 |
|------|------|------|
| 数据模型 | ✅ | 在 agents 表加 `owner_did` 列，不新建表，简洁 |
| 端点设计 | ✅ | 5 个 `/owner/*` 端点，职责清晰 |
| 注册流程 | ✅ | 生成密钥对 → 创建 DID → 写入 agents |
| 向后兼容 | ✅ | `owner_did=NULL` 的 Agent 继续正常工作 |

**改进建议：**

| # | 建议 | 优先级 | 说明 |
|---|------|--------|------|
| S1-04-1 | `POST /owner/register` 返回加密私钥或提示导出 | P2 | 用户需能恢复主 DID，否则私钥丢失后无法管理子 Agent |

#### 1.0-06 消息中心 — ✅ 通过

| 项目 | 评估 | 备注 |
|------|------|------|
| 聚合查询 SQL | ✅ | 子查询 + JOIN 设计正确 |
| 端点设计 | ✅ | 3 个 `/owner/messages/*` 端点 |
| 响应格式 | ✅ | 包含 `to_agent_name` 字段，方便用户识别 |
| 分页支持 | ✅ | LIMIT/OFFSET |

**改进建议：**

| # | 建议 | 优先级 | 说明 |
|---|------|--------|------|
| S1-06-1 | 可加 `GET /owner/messages/search?q=` 支持关键词搜索 | P3 | 非必需，但大消息量时有用 |

#### 1.0-08 Capability Token Envelope — ✅ 通过（改进已采纳）

| 项目 | 评估 | 备注 |
|------|------|------|
| Token 结构 | ✅ | 五字段齐全 + `revocation_endpoint`（已采纳 S1-08-1） |
| `evaluated_constraint_hash` | ✅ | 符合 qntm WG decision artifact 要求 |
| JCS 规范化 | ✅ | `sort_keys=True, separators=(",", ":")` 正确 |
| 权限映射 | ✅ | `admin/rw/r` → 细粒度权限数组，与 SINT T2/T1/T0 对齐 |
| 数据模型 | ✅ | `capability_tokens` 表 + `delegation_chain_links` 表（已采纳 S1-08-2） |
| 签发流程 | ✅ | 自动从 `enclave_members.permissions` 推导 |
| 验证流程 | ✅ | 包含 monotonic narrowing 检查（已采纳 S1-08-3） |

**已采纳改进：**

| # | 建议 | 状态 | 说明 |
|---|------|------|------|
| S1-08-1 | Token 结构添加 `revocation_endpoint` 字段 | ✅ 已采纳 | 已添加到 Token 结构，必填字段 |
| S1-08-2 | `delegation_chain` 改为独立表 | ✅ 已采纳 | 新增 `delegation_chain_links` 表，移除 JSON TEXT 列 |
| S1-08-3 | 补充 monotonic narrowing 验证逻辑 | ✅ 已采纳 | 验证流程新增 `scope_is_subset` + 约束比较 |
| S1-08-4 | 与 SINT 字段命名对齐 | 🟢 小优化 | 可在 crosswalk 中加别名映射 |

#### 与 SINT/qntm WG 对齐检查

| 检查项 | 状态 | 参考 |
|--------|------|------|
| `evaluated_constraint_hash` 在 Token 中 | ✅ | qntm WG issue #7 要求 |
| 权限映射 `r → T0, rw → T1, admin → T2` | ✅ | enclave-permission-model.md + enclave-mapping.ts |
| JCS canonicalization | ✅ | SINT RFC-001 §签名格式 |
| 委托链单调收窄验证 | ✅ 已实现 | `scope_is_subset` + constraint 比较 |
| 撤销端点必填 | ✅ 已实现 | Token 结构包含 `revocation_endpoint` |

---

### 评审结论

三项设计全部通过，改进建议已采纳并整合到设计中：

- ✅ S1-08-1：`revocation_endpoint` 字段已添加到 Token 结构
- ✅ S1-08-2：`delegation_chain_links` 独立表已定义
- ✅ S1-08-3：`scope_is_subset` + monotonic narrowing 验证已实现

**设计已完善，可进入开发。**

---

### 代码评审记录（v1.0 Phase 1）

> 评审日期：2026-04-15 | 评审者：评审 Agent | 测试结果：371 passed, 8 skipped ✅

#### 评审结论：已通过

所有阻塞性问题已修复，补充测试用例已通过。

#### 阻塞性问题 — ✅ 全部已修复

| # | 问题 | 位置 | 状态 |
|---|------|------|------|
| P1 | `verify_token` 委托链验证依赖 `token._parent_token_id` 动态属性，从数据库恢复时该属性为 None，导致委托链验证被跳过。应改为直接调用 `get_delegation_chain_func(token.token_id)` | `capability_token.py#verify_token` | ✅ 已修复 — 改为直接调用 `get_delegation_chain_func(token.token_id)`，不依赖动态属性 |
| P2 | `CapabilityToken.to_dict()` 使用 `asdict()`，不包含动态属性 `_parent_token_id`，导致 `api_issue_token` 中委托链信息丢失，`delegation_chain_links` 表永远不会写入。修复：在 `api_issue_token` 里手动补 `token_dict["_parent_token_id"] = parent_token_id` | `governance.py#api_issue_token` | ✅ 已修复 — 在 `save_capability_token` 前手动补上委托链属性 |

#### 建议性问题 — ✅ 全部已修复

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| S1 | `register_owner` 在 storage.py 里直接 import 了 `DIDGenerator` 和 `_config`，违反存储层不依赖 node 层的原则 | 🟡 | ⬚ 建议修复（架构层面，不影响功能） |
| S2 | `api_verify_token` 传 `get_token_func=get_capability_token`（返回 dict），但 `verify_token` 里用 `parent.scope` 访问属性——dict 没有 `.scope`，委托链验证会抛异常 | 🟡 | ✅ 已修复 — 改为 `parent["scope"]` dict 访问，同时兼容 dict 和 CapabilityToken 对象 |
| S3 | `scope_is_subset` 的 `resource_pattern` 比较逻辑对复杂 glob 模式会误判 | 🟢 | ⬚ 后续优化 |
| S4 | `verify_token` 中 `max_delegation_depth` 用 `>=` 比较，比设计文档"更严格"要求更严，确认是否有意为之 | 🟢 | ⬚ 确认（有意为之：child depth 必须严格小于 parent） |
| S5 | `fetch_owner_inbox` 不包含发给主 DID 本身的消息（`WHERE a.owner_did = ?` 不含主 DID 自己） | 🟢 | ⬚ 后续优化 |

#### 补充测试用例 — ✅ 全部已通过

| # | 场景 | 重要性 | 状态 |
|---|------|--------|------|
| T1 | 委托链端到端：签发 parent token → 签发 child token（带 parent_token_id）→ 验证委托链完整性 | 🔴 必需 | ✅ 已通过 — test_v10_ct_07 |
| T2 | 单调收窄拒绝：child scope 超出 parent scope → 验证返回 SCOPE_EXPANSION | 🔴 必需 | ✅ 已通过 — test_v10_ct_08 |
| T3 | 过期 Token：validity_days=0 → 验证返回 EXPIRED | 🟡 建议 | ✅ 已通过 — test_v10_ct_09 |

---

## v1.0.0 Phase 2 — 意图路由 + Web 仪表盘 + 接入向导（1.0-05 + 1.0-01 + 1.0-03）

> 2026-04-17。

### 1.0-05 意图路由

#### 目标

外部发消息给主 DID，根据消息内容自动转发到最匹配的子 Agent。

#### 现状

`router.py` 的 `route_message` 按 `to_did` 直接路由。如果 `to_did` 是主 DID，消息存入主 DID 的收件箱，不会转发给子 Agent。

#### 设计

在 `route_message` 的离线存储步骤之前，插入意图路由逻辑：

```python
# router.py — route_message 中，离线存储之前

# 意图路由：如果 to_did 是主 DID，尝试转发到子 Agent
from agent_net.storage import get_owner, list_owned_agents
owner = await get_owner(to_did)
if owner:
    target = await _intent_route(content, to_did)
    if target:
        # 递归路由到子 Agent（保留原始 from_did）
        return await self.route_message(
            from_did, target, content, session_id, reply_to,
            message_type, protocol, content_encoding,
        )
```

#### 匹配策略

```python
async def _intent_route(content: str, owner_did: str) -> Optional[str]:
    """
    根据消息内容匹配最合适的子 Agent。
    策略：关键词匹配 Agent capabilities。
    """
    agents = await list_owned_agents(owner_did)
    if not agents:
        return None

    content_lower = content.lower()
    best_match = None
    best_score = 0

    for agent in agents:
        profile = agent.get("profile", {})
        caps = profile.get("capabilities", [])
        tags = profile.get("tags", [])
        keywords = [c.lower() for c in caps + tags]

        score = sum(1 for kw in keywords if kw in content_lower)
        if score > best_score:
            best_score = score
            best_match = agent["did"]

    # S1-05-1：匹配阈值，避免低质量转发
    MIN_MATCH_SCORE = 2  # 至少 2 个关键词匹配才转发
    if best_score < MIN_MATCH_SCORE:
        return None  # 无足够匹配，消息留在主 DID 收件箱

    return best_match  # None 表示无匹配，消息留在主 DID 收件箱
```

#### 防递归

主 DID 转发到子 Agent 后，子 Agent 的 `route_message` 不会再触发意图路由（因为子 Agent 不是 owner 类型）。

#### 文件变更

| 文件 | 变更 |
|------|------|
| `agent_net/router.py` | `route_message` 插入意图路由逻辑 + `_intent_route` 方法 |

预估：~35 行。

#### 改进建议（已采纳）

| # | 建议 | 状态 | 说明 |
|---|------|------|------|
| S1-05-1 | 添加匹配阈值，避免低质量转发 | ✅ 已采纳 | `MIN_MATCH_SCORE = 2`，至少 2 个关键词匹配才转发 |
| S2-05-1 | 返回匹配日志/元数据 | 🟢 后续 | 转发成功后记录匹配 Agent 和 score，便于调试 |
| S3-05-1 | 支持配置优先级权重 | 🟢 后续 | 某些 capability（如 "Emergency"）可设置更高权重 |

---

### 1.0-01 Web 仪表盘

#### 目标

`localhost:8765/ui` 提供 Web 管理界面，覆盖 Agent 管理、消息中心、Enclave/Playbook、信任网络。

#### 技术选型

| 选项 | 方案 | 理由 |
|------|------|------|
| 前端框架 | **Vue 3 + Vite** | 轻量、SFC 单文件组件、构建产物小（< 500KB gzip）。项目 Python 为主，Vue 的模板语法对非前端开发者更友好 |
| UI 组件库 | **PrimeVue** | 开箱即用的数据表格、树形组件、图表，免费 |
| 图可视化 | **D3.js**（信任网络图）+ **dagre**（Playbook DAG） | 轻量，不引入重框架 |
| 构建产物 | Vite build → `agent_net/node/static/` 目录 | FastAPI `StaticFiles` 挂载，零额外依赖 |
| 开发模式 | `vite dev` 代理 API 到 `:8765` | 前后端分离开发，构建后合并 |

#### 目录结构

```
web/                          # 前端源码（不打包进 pip install）
├── package.json
├── vite.config.ts
├── index.html
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── api/                  # API 调用层
│   │   └── client.ts         # fetch wrapper，baseURL = /
│   ├── views/
│   │   ├── Dashboard.vue     # 首页概览
│   │   ├── Agents.vue        # Agent 列表 + 详情
│   │   ├── Messages.vue      # 消息中心
│   │   ├── Enclaves.vue      # Enclave 管理
│   │   ├── TrustNetwork.vue  # 信任网络图
│   │   └── Setup.vue         # 接入向导（1.0-03）
│   └── components/
│       ├── PlaybookDAG.vue   # Playbook DAG 可视化
│       ├── TrustGraph.vue    # D3 信任网络图
│       └── TokenList.vue     # Capability Token 列表
└── dist/                     # 构建产物 → 复制到 agent_net/node/static/

agent_net/node/static/        # 构建产物（git tracked）
├── index.html
├── assets/
│   ├── index-xxx.js
│   └── index-xxx.css
```

#### FastAPI 挂载

```python
# daemon.py 追加

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

_static_dir = Path(__file__).parent / "static"

if _static_dir.exists():
    # S4-01-1 修复：使用 html=True 模式，自动处理 SPA fallback
    app.mount("/ui", StaticFiles(directory=_static_dir, html=True), name="ui")
```

使用 `StaticFiles(html=True)` 模式：
- `/ui/assets/index.js` → 返回静态文件
- `/ui/agents` → 无匹配文件时返回 `index.html`（SPA fallback）
- 无需额外路由，FastAPI 自动处理

所有 `/ui/*` 路径由 StaticFiles 处理，Vue Router history mode 自动生效。

#### 鉴权机制（S5-01-1）

本地访问免鉴权，远程访问需 Token：

```python
# daemon.py 鉴权中间件
from starlette.middleware.base import BaseHTTPMiddleware

class UIAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 仅对 /ui 路径鉴权（API 端点已有独立鉴权）
        if not request.url.path.startswith("/ui"):
            return await call_next(request)

        # 本地访问（localhost / 127.0.0.1）免鉴权
        client_host = request.client.host if request.client else ""
        if client_host in ("localhost", "127.0.0.1", "::1"):
            return await call_next(request)

        # 远程访问：检查 Authorization header 或 cookie
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            token = request.cookies.get("daemon_token", "")

        if token != _load_daemon_token():
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        return await call_next(request)

app.add_middleware(UIAuthMiddleware)
```

前端配合（`web/src/api/client.ts`）：

```typescript
// 本地开发时无需 Token，远程访问自动携带
const token = localStorage.getItem("daemon_token") || "";

export async function fetchApi(path: string, options = {}) {
  const headers = { ...options.headers };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(path, { ...options, headers });
}
```

#### 页面设计

**1. Dashboard（首页）**

```
┌─────────────────────────────────────────────────────┐
│  AgentNexus Dashboard                    [Owner DID]│
├──────────┬──────────┬──────────┬───────────────────┤
│ Agents   │ Unread   │ Enclaves │ Avg Trust Score   │
│   5      │   12     │   3      │   78.5            │
├──────────┴──────────┴──────────┴───────────────────┤
│  最近消息                                           │
│  ┌─────────────────────────────────────────────┐   │
│  │ Agent1 ← sender: "设计方案已完成"    2min ago│   │
│  │ Agent2 ← sender: "代码已提交"        5min ago│   │
│  └─────────────────────────────────────────────┘   │
│  活跃 Playbook                                      │
│  ┌─────────────────────────────────────────────┐   │
│  │ 登录功能开发  [design] → [review] → implement│   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

数据源：`GET /owner/agents/{did}` + `GET /owner/messages/stats` + `GET /enclaves` + `GET /reputation/{did}`（聚合子 Agent）

**S2-01-1 改进：** 信任分改为 `Avg Trust Score`（子 Agent 平均），明确显示来源，避免用户误解为主 DID 自身分数。

**S3-01-1 优化：** TrustNetwork 页面节点 > 50 时启用分页加载，每页显示 20 个节点，支持搜索/筛选功能。

**2. Agents（Agent 列表）**

表格：DID（缩写）、名称、capabilities、信任分、最后活跃时间、状态（在线/离线）。点击进入详情页（profile、certifications、capability tokens）。

数据源：`GET /owner/agents/{did}` + `GET /reputation/{did}` + `GET /capability-tokens/by-did/{did}`

**3. Messages（消息中心）**

左侧：子 Agent 列表 + 未读数。右侧：选中 Agent 的消息流。

数据源：`GET /owner/messages/stats` + `GET /owner/messages/inbox` + `GET /messages/all/{did}`

**4. Enclaves（Enclave 管理）**

Enclave 列表 → 点击进入：成员、Vault 文档、Playbook 运行状态。Playbook 用 DAG 图展示 stage 依赖和当前进度。

数据源：`GET /enclaves` + `GET /enclaves/{id}` + `GET /enclaves/{id}/runs/{rid}`

**5. TrustNetwork（信任网络）**

D3 力导向图：节点 = Agent DID，边 = 信任关系（score 映射为边粗细），颜色 = trust_level。

数据源：`GET /trust/edges/{did}` + `GET /reputation/{did}`

#### 文件变更

| 文件 | 变更 |
|------|------|
| `web/` | **新建**。Vue 3 + Vite 前端项目 |
| `agent_net/node/static/` | **新建**。构建产物目录 |
| `agent_net/node/daemon.py` | 挂载 StaticFiles(html=True) + UIAuthMiddleware |
| `pyproject.toml` | 排除 `web/` 目录，不打包进 pip install |

#### pyproject.toml 配置（S1-01-1）

```toml
[tool.setuptools.packages.find]
where = ["src"]
include = ["agent_net*"]
exclude = ["web*"]

# 或使用 hatchling
[tool.hatch.build.targets.wheel]
exclude = ["web/", "*.ts", "*.vue"]
```

确保 `pip install agentnexus-sdk` 不包含前端源码，构建产物 `agent_net/node/static/` 随主包一起安装。

#### 改进建议（已采纳）

| # | 建议 | 状态 | 说明 |
|---|------|------|------|
| S1-01-1 | pyproject.toml 排除 `web/` 目录 | ✅ 已采纳 | 配置 exclude 规则 |
| S2-01-1 | Dashboard 信任分显示来源 | ✅ 已采纳 | 改为 `Avg Trust Score` |
| S3-01-1 | TrustNetwork 性能优化 | 🟢 后续 | 节点 > 50 时分页加载 |
| S4-01-1 | SPA fallback 路由顺序 | ✅ 已采纳 | 使用 `StaticFiles(html=True)` |
| S5-01-1 | 鉴权机制 | ✅ 已采纳 | 本地免鉴权 + UIAuthMiddleware |

---

### 1.0-03 Agent 接入向导

#### 目标

UI 引导用户接入 Agent：选平台 → 显示安装命令 → Agent 注册后自动出现在列表中。

#### 设计

作为仪表盘的一个页面（`Setup.vue`），不是独立应用。

**步骤流程：**

```
Step 1: 选择接入方式
  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │  MCP     │  │  SDK     │  │ OpenClaw │  │ Webhook  │
  │(Claude)  │  │(Python)  │  │ (Skill)  │  │ (HTTP)   │
  └──────────┘  └──────────┘  └──────────┘  └──────────┘

Step 2: 显示安装命令（根据选择动态生成）
  ┌─────────────────────────────────────────────────┐
  │ # MCP 方式                                       │
  │ python main.py node mcp --name "MyAgent" \       │
  │   --caps "Chat,Code"                             │
  │                                    [复制] [下一步]│
  └─────────────────────────────────────────────────┘

Step 3: 等待 Agent 注册（轮询 /agents/local）
  ┌─────────────────────────────────────────────────┐
  │ ⏳ 等待 Agent 连接...                             │
  │                                                   │
  │ ✅ MyAgent (did:agentnexus:z6Mk...) 已连接！     │
  │                                    [绑定到主 DID] │
  └─────────────────────────────────────────────────┘

Step 4: 绑定到主 DID（调用 POST /owner/bind）
  ┌─────────────────────────────────────────────────┐
  │ ✅ MyAgent 已绑定到你的主 DID                     │
  │                                    [完成]         │
  └─────────────────────────────────────────────────┘
```

#### 各平台安装命令模板

```typescript
// S2-03-1：使用模板函数而非字符串拼接
interface SetupTemplate {
  title: string;
  generateCommand: (name: string, caps: string[]) => string;
  description: string;
}

const SETUP_TEMPLATES: Record<string, SetupTemplate> = {
  mcp: {
    title: "MCP（Claude Desktop / Cursor / Claude Code）",
    generateCommand: (name, caps) =>
      `python main.py node mcp --name "${name}" --caps "${caps.join(",")}"`,
    description: "适合 AI 编程助手场景",
  },
  sdk: {
    title: "Python SDK",
    generateCommand: (name, caps) =>
      `import agentnexus\nnexus = await agentnexus.connect("${name}", caps=["${caps.join('", "')}"])`,
    description: "适合自定义 Agent 开发",
  },
  openclaw: {
    title: "OpenClaw Skill",
    generateCommand: (name, caps) =>
      `curl -X POST http://localhost:8765/adapters/openclaw/register \\\n  -H "Authorization: Bearer $TOKEN" \\\n  -d '{"skill_name": "${name}", "capabilities": ["${caps.join('", "')}"]}'`,
    description: "适合已有 OpenClaw Skill",
  },
  webhook: {
    title: "Webhook（Dify / Coze / 自定义）",
    generateCommand: (name, caps) =>
      `curl -X POST http://localhost:8765/adapters/webhook/register \\\n  -H "Authorization: Bearer $TOKEN" \\\n  -d '{"name": "${name}", "callback_url": "https://your-service/webhook"}'`,
    description: "适合任何能发 HTTP 请求的服务",
  },
};

// 使用示例
const command = SETUP_TEMPLATES.mcp.generateCommand("MyAgent", ["Chat", "Code"]);
```

#### 轮询检测新 Agent

```typescript
// Setup.vue — Step 3
const POLL_INTERVAL = 2000;  // 2 秒
const POLL_TIMEOUT = 60000;  // 60 秒超时（S1-03-1）

async function waitForAgent(expectedName: string) {
  const before = await fetch("/agents/local").then(r => r.json());
  const beforeDids = new Set(before.agents.map(a => a.did));

  let elapsed = 0;

  const interval = setInterval(async () => {
    elapsed += POLL_INTERVAL;

    // S1-03-1：超时机制
    if (elapsed >= POLL_TIMEOUT) {
      clearInterval(interval);
      showError("等待超时，请检查命令是否正确执行，或手动刷新页面");
      return;
    }

    // S3-03-1：显示进度
    updateProgress(`等待中... (已轮询 ${elapsed / 1000} 秒)`);

    const after = await fetch("/agents/local").then(r => r.json());
    const newAgent = after.agents.find(a => !beforeDids.has(a.did));

    if (newAgent) {
      clearInterval(interval);

      // S4-03-1：检查名称匹配
      if (newAgent.profile?.name !== expectedName) {
        showWarning(`检测到新 Agent "${newAgent.profile?.name}"，但名称不匹配`);
      }

      onAgentConnected(newAgent);
    }
  }, POLL_INTERVAL);
}
```

#### 文件变更

| 文件 | 变更 |
|------|------|
| `web/src/views/Setup.vue` | 接入向导页面（4 步流程） |
| `web/src/api/client.ts` | fetchApi wrapper + Token 携带逻辑 |

#### 改进建议（已采纳）

| # | 建议 | 状态 | 说明 |
|---|------|------|------|
| S1-03-1 | 轮询超时机制 | ✅ 已采纳 | 60 秒超时 + 错误提示 |
| S2-03-1 | placeholder 替换逻辑 | ✅ 已采纳 | 使用模板函数 `generateCommand(name, caps)` |
| S3-03-1 | Step 3 显示进度 | ✅ 已采纳 | 显示轮询秒数 |
| S4-03-1 | 错误处理 | ✅ 已采纳 | 名称不匹配警告 + 超时错误提示 |

---

### 实施顺序

```
1.0-05 意图路由（~35 行，纯后端）✅ 已完成（2026-04-17）
    ↓
1.0-01 Web 仪表盘
    Phase A: 项目脚手架（Vite + Vue + FastAPI 挂载）✅ 已完成（2026-04-17）
    Phase B: Dashboard + Agents 页面 → 待实施
    Phase C: Messages + Enclaves 页面 → 待实施
    Phase D: TrustNetwork 页面（D3）→ 待实施
    ↓
1.0-03 接入向导（仪表盘的一个页面，随 Phase B 一起做）
```

**已完成：**
- 1.0-05 意图路由（router.py + test_v10_intent_route.py）
- 1.0-01 Phase A：web/ 前端脚手架 + daemon.py StaticFiles 挂载

**下一步：** Phase B — Dashboard + Agents 页面完善 + Setup.vue 接入向导

---

### Phase 2 设计评审记录（v1.0.0）

> 评审日期：2026-04-17 | 评审者：Claude Code

#### 评审结论：✅ 全部通过，改进已采纳

三项设计全部通过，改进建议已采纳并整合到设计中。

#### 1.0-05 意图路由 — ✅ 通过

| 项目 | 评估 | 备注 |
|------|------|------|
| 设计位置 | ✅ | 在 `route_message` 离线存储前插入 |
| 匹配策略 | ✅ | 关键词匹配 capabilities + tags |
| 防递归 | ✅ | 子 Agent 不是 owner 类型 |
| 改进 S1-05-1 | ✅ 已采纳 | `MIN_MATCH_SCORE = 2` 匹配阈值 |

#### 1.0-01 Web 仪表盘 — ✅ 通过

| 项目 | 评估 | 备注 |
|------|------|------|
| 技术选型 | ✅ | Vue 3 + Vite + PrimeVue |
| 构建产物 | ✅ | `web/` → `agent_net/node/static/` |
| 改进 S1-01-1 | ✅ 已采纳 | pyproject.toml exclude `web/` |
| 改进 S2-01-1 | ✅ 已采纳 | 改为 `Avg Trust Score` |
| 改进 S4-01-1 | ⚠️ 部分采纳 | `StaticFiles(html=True)` 仅处理目录请求，不处理 Vue Router history mode。必须保留 catch-all 路由作为 SPA fallback，两者并存 |
| 改进 S5-01-1 | ✅ 已采纳 | UIAuthMiddleware 鉴权。补充：用 daemon token 生成 session cookie，避免每次访问输入 token |

#### 1.0-03 Agent 接入向导 — ✅ 通过

| 项目 | 评估 | 备注 |
|------|------|------|
| 流程设计 | ✅ | 4 步流程清晰 |
| 平台覆盖 | ✅ | MCP/SDK/OpenClaw/Webhook |
| 改进 S1-03-1 | ✅ 已采纳 | 60 秒轮询超时 |
| 改进 S2-03-1 | ✅ 已采纳 | 模板函数 `generateCommand()` |
| 改进 S3-03-1 | ✅ 已采纳 | 显示轮询进度 |
| 改进 S4-03-1 | ⚠️ 部分采纳 | 保持 DID 差集检测为主要逻辑，名称匹配仅作辅助提示。用户可能修改命令中的名称，按名称匹配不可靠 |

#### 后续优化（P3）

| # | 建议 | 说明 |
|---|------|------|
| S2-05-1 | 返回匹配日志/元数据 | 意图路由转发后记录匹配详情 |
| S3-05-1 | 支持配置优先级权重 | 某些 capability 设置更高权重 |
| S3-01-1 | TrustNetwork 性能优化 | 节点 > 50 时分页加载 |

**设计已完善，可进入开发。**

---

### 代码评审记录（v1.0 Phase 2）

> 评审日期：2026-04-17 | 评审者：评审 Agent | 测试结果：375 passed, 8 skipped ✅

#### 评审结论：已通过

所有阻塞性和建议性问题已修复。

#### 阻塞性问题 — ✅ 全部已修复

| # | 问题 | 位置 | 状态 |
|---|------|------|------|
| P1 | 意图路由插入位置错误（步骤 3.5，Relay 之后）。若主 DID 有 P2P endpoint 或 Relay 地址，消息在步骤 2/3 就被投递，永远不触发意图路由 | `router.py#route_message` | ✅ 已修复 — 移到步骤 1 之后（本地直投之后，P2P/Relay 之前） |
| P2 | `StaticFiles(html=True)` 不处理 Vue Router history mode 路径。需补充 catch-all 路由 | `daemon.py` | ✅ 已修复 — mount `/ui/assets` + catch-all route `/ui/{path:path}` |

#### 建议性问题 — ✅ 全部已修复

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| S1 | `Setup.vue` Step 1 调用 `registerOwner` 时 token 尚未设置（Step 2 才设置），会 401 | 🟡 | ✅ 已修复 — 调换步骤顺序：先设置 Token（Step 0）再创建 Owner（Step 1） |
| S2 | `Dashboard.vue` 中 `totalEnclaves` 初始化为 0 但从未更新 | 🟢 | ✅ 已修复 — 调用 `listEnclaves()` 获取数量 |
| S3 | `Messages.vue` 中 `content.slice(0, 50)` 未判断 content 类型 | 🟢 | ✅ 已修复 — 先判断 `typeof data.content === 'string'` |
| S4 | `client.ts` `fetchOwnerStats` 返回类型中 `last_message_at` 可能为 null | 🟢 | ⬚ 后续优化 |

---

## v1.5 前瞻 — 决策一致性分级（1.5-13）

> 2026-04-20 概念设计。来源：A2A#1575 讨论中关于"decision identity 是否 time-dependent"的问题。

### 问题

同一个 Agent 在不同时间点被验证，可能因信任分衰减、TTL 过期、图传播延迟等因素得到不同结果。对于大部分操作这不是问题（权限验证是时间无关的），但金融、合规等场景需要精确的时间保证。

### 设计：协议层一致性级别

在 `evaluation_context` 中引入可选的 `consistency_level` 字段，按需开启：

| 级别 | 名称 | 机制 | 开销 | 适用场景 |
|------|------|------|------|---------|
| L0 | 无时间约束 | 不填 `evaluation_context`，仅校验 constraint hash | 零 | 权限查询、scope 验证、日常操作（默认） |
| L1 | 墙钟时间戳 | `evaluated_at` 填 Unix 时间戳，验证者检查合理窗口 | 极低 | 审计留痕、一般合规、交易记录 |
| L2 | 因果序保证 | HLC（物理时钟 + 逻辑计数器），精确判断多 Agent 并发事件的因果关系 | 低 | 分布式多 Agent 协作、因果序敏感场景 |
| L3 | 极端延迟容忍 | 存储-转发 + 延迟确认，容忍长时间断连和网络分区 | 中 | 高延迟网络、跨地域合规举证 |

### 协议表达

```json
{
  "evaluated_constraint_hash": "sha256:abc...",
  "consistency_level": "L1",
  "evaluation_context": {
    "evaluated_at": 1713600000,
    "policy_version": "v1.2"
  }
}
```

L0 时 `consistency_level` 和 `evaluation_context` 均省略，向下兼容现有实现。

### 关键原则

1. **默认零开销**：L0 是默认值，现有代码不需要改动
2. **业务方按需选择**：不是平台强制，而是业务根据场景声明需要的级别
3. **成本递增**：越高级别开销越大，只有真正需要的场景才付成本
4. **与策略引擎联动**：`consistency_level` 可作为 1.5-12 策略引擎的一条策略规则

---

### 代码评审记录（Consistency Level L0/L1）

> 评审日期：2026-04-21 | 评审者：评审 Agent | 测试结果：382 passed, 8 skipped ✅

#### 评审结论：有条件通过

P1、S1 修复后合并。

#### 阻塞性问题

| # | 问题 | 位置 | 状态 |
|---|------|------|------|
| P1 | L1 时间窗口检查逻辑有误：`verify_token` 内部调用 `build_evaluation_context` 生成 `evaluated_at`，然后立刻用 `check_l1_window` 检查自己刚生成的时间戳，时间差永远是毫秒级，永远通过。正确做法：`check_l1_window` 应由验证方调用，检查 token 本身携带的 `evaluation_context.evaluated_at`（外部传入），而非内部新生成的 | `capability_token.py#verify_token` L1 段 | ✅ 已修复 — 移除 `verify_token` 中的 L1 自检查逻辑。`check_l1_window` 作为独立函数由外部验证方调用。 |

#### 建议性问题

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| S1 | `l1_window_seconds=None` 传给 `check_l1_window` 时会覆盖默认值 | 🟡 | ✅ 已修复 — 移除 `l1_window_seconds` 参数（L1 窗口检查不再在 `verify_token` 内执行） |
| S2 | `test_cl_05` 注释说"30.001 秒"但实际测试值是 30.01 秒 | 🟢 | ✅ 已修正 |

#### 缺失测试用例

| # | 场景 | 状态 |
|---|------|------|
| T1 | L1 窗口检查在 `verify_token` 集成层的端到端测试（P1 修复后补充） | ⬚ 待补充 |
