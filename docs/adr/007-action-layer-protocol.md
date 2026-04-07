# ADR-007: Action Layer 协作协议设计

## 状态

提议

## 日期

2026-04-04

## 背景

v0.7.x 的消息系统是自由文本模式——Agent 之间发送任意字符串，语义由双方自行约定。这对简单对话足够，但无法支撑结构化协作场景（任务委派、进度汇报、资源同步）。

v0.8.0 需要引入协作协议（Action Layer），让 Agent 不仅能"聊天"，还能"协作"。核心设计问题：

1. **协议层级**：独立协议层 vs 在现有消息系统上扩展？
2. **动作类型**：需要哪些基础动作？如何保持最小化又足够实用？
3. **状态管理**：任务状态机在哪里维护？SDK 侧还是 Daemon 侧？
4. **向后兼容**：新协议如何与现有自由文本消息共存？

## 决策

### 1. 信封模式：在现有消息上扩展，不引入独立协议层

在 `send_message` 的 payload 中新增 `message_type` 和 `protocol` 字段：

```json
{
  "from_did": "did:agentnexus:z6Mk...",
  "to_did": "did:agentnexus:z6Mk...",
  "content": { ... },
  "message_type": "task_propose",
  "protocol": "nexus_v1",
  "session_id": "sess_abc123"
}
```

规则：
- `message_type` 为空或 `protocol` 非 `nexus_v1` → 自由文本消息，直接交给 `on_message` 回调
- `message_type` 为四种动作之一且 `protocol` 为 `nexus_v1` → 结构化动作，进入 Action Layer 处理

这样现有 Relay 和 Daemon 的消息路由逻辑完全不需要改动——它们只负责送达"信封"，不关心信封里装的是自由文本还是结构化动作。

### 2. 四种基础动作类型

| message_type | 语义 | content 结构 |
|-------------|------|-------------|
| `task_propose` | 发布/委派任务 | `{title, description?, deadline?, required_caps?, priority?}` |
| `task_claim` | 认领/响应任务 | `{task_id, eta?, message?}` |
| `resource_sync` | 共享 K-V 数据 | `{key, value, version?}` |
| `state_notify` | 进度/状态汇报 | `{task_id?, status, progress?, error?}` |

`status` 枚举值：`pending` | `in_progress` | `completed` | `failed` | `blocked`

为什么是这四种：
- `task_propose` + `task_claim` = 任务的发布-认领闭环
- `resource_sync` = 共享状态（设计稿 URL、配置变更、数据集版本）
- `state_notify` = 心跳 + 完成 + 报错的统一通道

这四种覆盖了 80% 的多 Agent 协作场景。更复杂的模式（竞拍、投票、审批链）可以在 v0.9+ 通过组合这四种基础动作实现。

### 3. 状态管理：SDK 侧轻量状态机

任务状态机在 SDK 内存中维护，不持久化到 Daemon：

```
task_propose → pending
  ├── task_claim → in_progress
  │     ├── state_notify(completed) → completed
  │     ├── state_notify(failed) → failed
  │     └── state_notify(blocked) → blocked → in_progress（恢复）
  └── 超时未认领 → expired（SDK 本地判断）
```

理由：
- Daemon 是通信基础设施，不应承担业务状态管理
- 不同 Agent 对任务状态的理解可能不同（有的需要审批环节，有的不需要）
- SDK 侧状态机可以被开发者覆盖或扩展
- 持久化需求由开发者自行决定（SQLite/Redis/内存）

### 4. SDK 回调接口

```python
@nexus.on_message
async def handle_text(msg):
    """自由文本消息"""
    print(f"{msg.from_did}: {msg.content}")

@nexus.on_task_propose
async def handle_task(task):
    """收到任务提议"""
    if "Code" in task.required_caps:
        await nexus.claim_task(task.task_id, eta="2h")

@nexus.on_state_notify
async def handle_state(state):
    """收到状态更新"""
    if state.status == "completed":
        print(f"任务 {state.task_id} 完成")
```

SDK 根据 `message_type` 自动分发到对应回调。未注册回调的动作类型回退到 `on_message`。

### 5. task_id 生成

`task_id` 由发起方 SDK 生成，格式：`task_{uuid4}`

示例：`task_a1b2c3d4-e5f6-7890-abcd-ef1234567890`

不使用 Daemon 生成，因为任务是 SDK 层概念，Daemon 不感知任务语义。使用完整 UUID4 避免大规模场景下的 ID 碰撞。

### 6. Daemon 侧改动（最小化）

Daemon 的 `/messages/send` 端点当前接受 `content` 为字符串。需要扩展为同时接受字符串和 JSON 对象：

```python
# 现有：content: str
# 扩展：content: Union[str, dict]
```

同时新增可选字段 `message_type` 和 `protocol` 到消息存储 schema。

`/messages/inbox/{did}` 返回值同步扩展，每条消息新增 `message_type` 和 `protocol` 字段（可为 NULL），SDK 据此分发到对应回调。（Q6 答疑触发补充）

这是 v0.8 对 Daemon 的唯一改动。

## 理由

### 为什么信封模式而不是独立协议层

| 维度 | 信封模式 | 独立协议层 |
|------|---------|-----------|
| Relay 改动 | 零 | 需新增动作路由逻辑 |
| Daemon 改动 | content 类型扩展（1 处） | 新增 Action API 端点 |
| 向后兼容 | 完全兼容 | 需版本协商 |
| 加密 | 复用现有 AES-256-GCM | 需独立加密通道 |
| 复杂度 | 低 | 高 |

信封模式的核心优势：**通信层和协作层解耦**。Relay 和 Daemon 只管送信，SDK 负责拆信和理解语义。

### 考虑的替代方案

1. **独立 Action API（Daemon 新增 `/actions/*` 端点）** — 语义更清晰，但增加 Daemon 复杂度，违反"Daemon 是通信基础设施"的定位。任务管理是业务逻辑，不应下沉到基础设施层。
2. **基于 Topic 的 Pub/Sub** — 适合广播场景，但点对点任务委派用 Pub/Sub 过度设计。Pub/Sub 规划在 v2.0。
3. **JSON-RPC over 消息** — 标准化程度高，但引入 RPC 语义（method/params/result）与 Agent 协作的异步本质不匹配。

## 影响范围

- `agent_net/node/daemon.py`：`/messages/send` 的 `content` 字段类型扩展为 `Union[str, dict]`，新增可选 `message_type`、`protocol` 字段
- `agent_net/storage.py`：messages 表新增 `message_type` 和 `protocol` 列（可选，默认 NULL）
- `agentnexus-sdk/src/agentnexus/actions.py`：Action Layer 客户端实现
- `agentnexus-sdk/src/agentnexus/models.py`：TaskPropose、TaskClaim、ResourceSync、StateNotify 数据模型
- 现有 MCP 工具 `anpn_send` 不受影响（继续发送自由文本）

## 测试要求

| 测试场景 | 类型 | 说明 |
|---------|------|------|
| 自由文本消息走 `on_message` 回调 | 单元 | `message_type` 为空时不进入 Action Layer |
| 结构化动作走对应回调 | 单元 | 四种 `message_type` 各触发正确回调 |
| 未注册回调的动作回退到 `on_message` | 单元 | 兜底行为验证 |
| 状态机合法转换 | 单元 | pending→in_progress→completed 等 |
| 状态机非法转换 | 单元 | completed→in_progress 应拒绝 |
| content 为 dict 时 Daemon 正确存储和返回 | 集成 | 验证 Daemon 侧 `Union[str, dict]` 扩展 |

## 相关 ADR

- ADR-003: Sidecar 架构（Action Layer 在 SDK 侧实现，不下沉到 Daemon）
- ADR-006: SDK 架构与 Daemon 通信协议（Action Layer 基于 SDK 的 HTTP 通信层）

## 评审记录

| 日期 | 评审者 | 结果 | 备注 |
|------|--------|------|------|
| 2026-04-04 | 评审 Agent | 批准 | 无阻塞性问题 |

## 答疑记录

| 日期 | 提问者 | 问题 | 回复 | 是否触发设计变更 |
|------|--------|------|------|----------------|
| 2026-04-04 | 开发 Agent | Q4: messages 表新增 `message_type` 和 `protocol` 列，数据迁移策略是 ALTER TABLE 添加可为空列，还是新表 + 迁移脚本？ | ALTER TABLE 添加可为空列。`ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT NULL` + `ALTER TABLE messages ADD COLUMN protocol TEXT DEFAULT NULL`。v0.8 早期版本用户量极小，不需要迁移脚本，SQLite 支持此操作且不锁表。 | 否 |
| 2026-04-04 | 开发 Agent | Q5: `session_id` 生成规则未明确，是 `sess_{uuid4}` 格式吗？ | 是，`sess_{uuid4}`，由发起方 SDK 生成。示例：`sess_a1b2c3d4-e5f6-7890-abcd-ef1234567890`。与 `task_id` 同理，Daemon 不感知语义。 | 否 |
| 2026-04-04 | 开发 Agent | Q6: `store_message()` 新增参数后，`fetch_inbox()` 返回值是否也需要同步修改以包含新字段？ | 是，`fetch_inbox()` 返回的消息对象需包含 `message_type` 和 `protocol` 字段（可为 NULL），SDK 据此分发到对应回调。 | **是** — 需在 Daemon 侧改动章节补充 `fetch_inbox` 返回值变更 |
