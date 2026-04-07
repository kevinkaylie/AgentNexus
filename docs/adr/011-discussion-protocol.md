# ADR-011: Discussion Protocol 讨论协议设计

## 状态

已采纳

## 日期

2026-04-05

## 背景

ADR-007 定义了四种基础协作动作（task_propose / task_claim / resource_sync / state_notify），有意将讨论、投票、审批留给后续版本。

当前 AgentNexus 的多 Agent 研发团队（设计 Agent、开发 Agent、评审 Agent、测试 Agent）通过文档进行异步协作——写文档、读文档、再写文档。这种模式有效但存在局限：

1. **无实时反馈循环**：设计 Agent 不知道开发 Agent 遇到了什么困难，要等下一轮文档更新才能感知
2. **讨论过程不可追溯**：决策的"为什么"散落在各处，没有结构化记录
3. **多方协商低效**：三方以上的讨论需要反复修改同一份文档，容易冲突

AgentNexus 已有 DID 通信、E2E 加密、信封模式（ADR-007），具备支撑实时讨论的基础设施。需要设计一套讨论协议，让 Agent 之间能发起讨论、回复引用、投票表决、结论落盘。

## 决策

### 1. 在 ADR-007 信封模式上平行扩展四种讨论动作

与 Action Layer 同层，共用信封格式，新增四种 `message_type`：

| message_type | 语义 | content 结构 |
|-------------|------|-------------|
| `discussion_start` | 发起讨论 | `{topic_id, title, participants[], context?, consensus?, related_task_id?}` |
| `discussion_reply` | 回复/引用/@提及 | `{topic_id, reply_to?, mentions[]?, content, request_escalate?}` |
| `discussion_vote` | 投票表决 | `{topic_id, vote: "approve"\|"reject"\|"abstain", reason?}` |
| `discussion_conclude` | 宣布结论并关闭 | `{topic_id, conclusion, conclusion_type?, action_items[]?}` |

所有消息携带 `protocol: "nexus_v1"`，复用现有 DID 通信和 E2E 加密，Relay 和 Daemon 无需任何改动。

### 2. topic_id 串联讨论生命周期

类似 Action Layer 的 `task_id`，讨论协议用 `topic_id` 串联一次讨论的所有消息：

格式：`disc_{uuid4}`

示例：`disc_a1b2c3d4-e5f6-7890-abcd-ef1234567890`

由发起方 SDK 生成，Daemon 不感知语义。

### 3. 多方消息分发：点对点扇出（v0.8）

讨论天然是多方的，与 task 的双方模式不同。分发策略分阶段实现：

- **v0.8（本版本）**：发起方向每个 participant 分别 `send`，每个人的回复也分别发给所有 participants。纯点对点扇出，不需要改 Relay，完全在 SDK 层实现。消息量 O(N²)，但早期讨论参与者少（3-5 个 Agent），可接受。
- **v0.9+（未来）**：引入 Topic 路由，Relay 做消息扇出。发起方发一条，Relay 转给所有订阅者。

投递保证：SDK 采用"尽力投递 + 失败重试 + 最终一致"策略：
- 逐个发送，记录每个 participant 的投递状态（`delivered` / `pending` / `failed`）
- 发送失败的走离线存储（现有智能路由的第四级降级）
- 每条讨论消息自带 `seq`（topic 内递增序号），接收方可检测缺失并请求重发
- 不要求事务性的全有全无——不能因为 D 离线就阻止 B 和 C 收到消息

`reply_to` 防伪：SDK 维护每个 topic 的已知消息 ID 列表（基于 `seq`）。收到 `discussion_reply` 时，如果 `reply_to` 引用的消息 ID 不在已知列表中，SDK 标记为 `unverified_ref` 并交给应用层决定是否接受。这是客户端侧校验，不需要协议层改动。

### 4. 共识规则声明与计票

发起方在 `discussion_start` 中通过 `consensus` 对象声明共识规则：

```json
{
  "consensus": {
    "mode": "majority | unanimous | leader_decides",
    "leader_did": "did:agentnexus:z6Mk...（mode 为 leader_decides 时必填）",
    "timeout_seconds": 300,
    "timeout_action": "auto_approve | auto_reject | escalate"
  }
}
```

| 字段 | 说明 |
|------|------|
| `mode` | `majority`：简单多数通过；`unanimous`：全票通过（一票否决）；`leader_decides`：leader 最终裁决 |
| `leader_did` | leader_decides 模式下的裁决者 DID |
| `timeout_seconds` | 投票超时时间，超时后触发 `timeout_action` |
| `timeout_action` | `auto_approve`：视为默认通过；`auto_reject`：视为默认否决；`escalate`：升级到人类代理（见决策 8） |

`consensus` 为 `null` 时表示纯讨论、无需投票，发起方可随时 conclude。

计票由发起方本地执行，不需要 Relay 参与，保持去中心化。

计票状态持久化：SDK 在 Daemon SQLite 中存储计票快照，复用 messages 表：

```json
{
  "message_type": "discussion_vote_state",
  "protocol": "nexus_v1_internal",
  "content": {
    "topic_id": "disc_...",
    "votes": {"did:...design": "approve", "did:...dev": "reject"},
    "status": "voting",
    "start_time": 1743825600.0
  }
}
```

`protocol: "nexus_v1_internal"` 标记为内部状态，路由器不转发给其他 Agent。发起方重启后从 Daemon 恢复计票状态，重新计算 timeout 剩余时间（`timeout_seconds - (now - start_time)`）。

### 5. 讨论状态机

```
discussion_start → open
  ├── discussion_reply（可多次）→ open
  ├── discussion_vote（可多次）→ voting
  │     └── 计票满足 consensus.mode → concluded（自动）
  └── discussion_conclude → concluded（手动）
```

状态机在 SDK 内存中维护，计票快照持久化到 Daemon（见决策 4）。发起方重启后从 Daemon 恢复状态。

conclude 权限规则：
- **自动 conclude**：`consensus.mode` 为 `majority` 或 `unanimous` 时，发起方 SDK 计票满足条件后自动发送 `discussion_conclude`
- **手动 conclude**：`consensus` 为 `null`（纯讨论）或 `leader_decides` 时，需发起方显式调用 `await nexus.conclude_discussion(topic_id, conclusion)`
- 只有发起方（`discussion_start` 的 `from_did`）可以 conclude
- `leader_decides` 模式下，leader 的 `discussion_vote` 等同于 conclude 指令，发起方 SDK 收到后自动执行
- 其他参与者不能 conclude，但可以 `request_escalate`

### 6. 结论落盘：协议层与应用层分离

`discussion_conclude` 只负责"宣布结论 + 关闭讨论"，是协议层行为。文档落盘是应用层行为，由消费者决定：

```
discussion_conclude（协议层）
    ↓ 触发 on_discussion_conclude 回调
应用层（Scribe Agent / hook）
    ↓ 写入
ADR / WIP / devlog（文件系统）
```

`action_items` 字段提供结构化的后续动作建议，但不强制执行：

```json
{
  "topic_id": "disc_...",
  "conclusion": "required_caps 改为可选，留空时 Relay 做模糊匹配",
  "action_items": [
    {"type": "update_document", "ref": "adr-007", "description": "补充 required_caps 可选说明"},
    {"type": "create_task", "description": "实现模糊匹配逻辑"}
  ]
}
```

`action_items` 使用逻辑标识符（`ref`），不耦合文件路径。应用层负责将 `ref` 映射到具体文件。

### 7. SDK 回调接口

```python
@nexus.on_discussion_start
async def handle_discussion(disc):
    """收到讨论邀请"""
    print(f"新讨论: {disc.title}, 参与者: {disc.participants}")

@nexus.on_discussion_reply
async def handle_reply(reply):
    """收到讨论回复"""
    print(f"{reply.from_did}: {reply.content}")

@nexus.on_discussion_conclude
async def handle_conclude(conclusion):
    """讨论结束，可在此触发文档落盘"""
    await write_to_doc(conclusion.target, conclusion.conclusion)
```

未注册回调的讨论消息回退到 `on_message`，与 ADR-007 行为一致。

### 8. Human-via-Agent：人类通过秘书 Agent 参与

人类不直接持有 DID，而是通过一个"秘书 Agent"代理参与讨论和决策：

```
人类（微信 / Telegram / OpenClaw）
    ↑↓ 现有人类通信渠道（Skill 适配）
秘书 Agent (did:agentnexus:z6Mk...secretary)
    ↑↓ AgentNexus 协议（标准 DID 通信）
其他 AI Agent
```

秘书 Agent 的职责：
- 将讨论消息推送给人类（v0.8 只做格式转换和简单拼接，不做智能摘要；智能摘要是 v0.9+ 优化）
- 将人类的自然语言回复翻译成结构化协议消息（如"同意" → `discussion_vote(vote: "approve")`）
- 作为 `consensus.leader_did` 或 `escalate` 的目标

实现路径：利用 OpenClaw 等已有人类通信渠道的平台，写一个 Skill 适配器即可，几乎零开发成本。

协议层不需要区分"人类代理 Agent"和"AI Agent"——它们都是普通的 DID 节点。人类的特权来自于被指定为 leader 或 emergency 授权者，而不是因为它是人类。

### 9. EMERGENCY_OVERRIDE：紧急熔断

当 Agent 失控（如死循环消耗 API Token）时，授权 DID 可通过现有 `state_notify` 发送紧急停止指令：

```json
{
  "message_type": "state_notify",
  "protocol": "nexus_v1",
  "content": {
    "status": "emergency_halt",
    "scope": "all | task_{id} | did:agentnexus:z6Mk...target",
    "reason": "token budget exceeded"
  }
}
```

设计约束：

**a) 权限控制**：只有在 `nexus.config.emergency_authorized_dids` 列表中的 DID 可以发起。SDK 收到非授权 DID 的 emergency_halt 时静默忽略。权限控制靠本地配置，不靠消息内字段——消息里声明优先级没有意义，恶意 Agent 也可以声明。

**b) 复用 state_notify**：emergency_halt 本质是一种状态通知，不新增 message_type，符合 ADR-007 最小化原则。`emergency_halt` 作为特殊的 `status` 值即可标识紧急性，不需要额外的优先级字段。

**c) SDK 内置强制执行**：收到 `status: "emergency_halt"` 且 `from_did` 在授权列表中时，SDK 内置行为直接执行，不走用户回调：
- 取消所有进行中的任务
- 停止所有待发送的消息
- 回复 `state_notify(status: "halted")` 确认
- 触发可选的 `on_emergency` 回调供开发者做清理

停止动作本身不可被开发者覆盖。

**d) 典型场景**：秘书 Agent 作为人类代理，被配置为 emergency 授权者。人类在手机上点一下，秘书 Agent 广播 emergency_halt，所有相关 Agent 立即停止。

### 10. 讨论与任务的关联

`discussion_start` 包含可选的 `related_task_id` 字段，将讨论关联到某个任务：

```json
{
  "topic_id": "disc_...",
  "title": "翻译任务的术语表用哪个版本",
  "related_task_id": "task_a1b2...",
  "participants": [...]
}
```

理由：实际场景中大部分讨论围绕某个任务展开。有了关联，SDK 可以提供 `nexus.get_discussion_history(task_id=...)` 查询某个任务的所有讨论，方便追溯。不关联任务时留空即可。

### 11. 结论冲突处理

投票未达成一致且非 `leader_decides` 模式时，发起方**不能**强制 conclude。可选路径：

1. **升级**：触发 `escalate`，升级到秘书 Agent / 人类裁决
2. **重新发起**：发起新的 `discussion_start`，`consensus.mode` 切换为 `leader_decides`，`context` 引用原 topic_id
3. **记录分歧**：发起方发送 `discussion_conclude`，标记 `conclusion_type: "no_consensus"`，记录各方立场，不做决策

```json
{
  "topic_id": "disc_...",
  "conclusion": "各方立场记录：设计 Agent 认为应改为可选，开发 Agent 认为应保持必填",
  "conclusion_type": "no_consensus"
}
```

`conclusion_type` 枚举值：`"consensus"`（默认，达成一致）| `"no_consensus"`（记录分歧）| `"escalated"`（已升级裁决）

理由：允许强制 conclude 会使投票机制形同虚设，但也不能让讨论永远挂着，所以需要"记录分歧、暂不决策"的出口。

### 12. 讨论历史查询

v0.8 依赖 Daemon 的 `fetch_inbox` 查询，SDK 按 `topic_id` 过滤还原完整消息流，不做独立缓存：

```python
# SDK 便捷方法，底层是 inbox 过滤
messages = await nexus.get_discussion_history(topic_id="disc_...")

# 也支持按关联任务查询
discussions = await nexus.get_discussion_history(task_id="task_...")
```

理由：Daemon 的 `fetch_inbox` 已返回所有消息（含 message_type），SDK 过滤即可。v0.8 参与者少、消息量小，额外做本地缓存增加复杂度，没必要。

### 13. 僵局检测：参与者主动请求升级

v0.8 不做自动僵局检测，只依赖 timeout 和参与者主动请求。

任何参与者可以在 `discussion_reply` 中带 `request_escalate: true`，主动请求升级：

```json
{
  "message_type": "discussion_reply",
  "content": {
    "topic_id": "disc_...",
    "content": "我们已经讨论了 3 轮，立场没有变化，建议升级",
    "request_escalate": true
  }
}
```

发起方收到后触发 escalate 流程（按 `consensus.timeout_action` 处理）。

理由：自动检测"循环反驳"需要语义理解（判断是重复观点还是新论据），这是 NLP 问题，不应放在协议层。参与讨论的 Agent 本身有 LLM 能力，由它们自行判断是否僵局更合理。

### 14. emergency_halt 广播范围

`scope: "all"` 只广播给与发送方有活跃会话（已完成握手）的 Agent，不广播给 Relay 上所有 Agent。

实现方式：SDK 自行维护已握手 DID 列表，不需要 Daemon 新增端点（保持"Daemon 不感知业务语义"原则）：
- 新握手：`on_handshake_complete` 时加入列表
- 过期：24h 无通信自动移除，或依赖心跳
- 远程握手：通过 Relay 转发的握手同样记录，SDK 不区分本地/远程
- 广播时逐个发送 `state_notify`

理由：
- 广播给整个 Relay 太危险——一个被盗的授权 DID 可以瘫痪整个 Relay
- 限制在"已握手"范围内，影响面可控，符合 AgentNexus 的信任模型
- 没握手的 Agent 之间本来就不能通信，广播给它们没有意义

## 理由

### 为什么平行扩展而不是嵌套在 Action Layer 之上

| 维度 | 平行扩展（采用） | 嵌套在 Action Layer 上 |
|------|----------------|---------------------|
| Relay/Daemon 改动 | 零 | 零 |
| 概念复杂度 | 低——讨论和任务是平级概念 | 高——讨论变成任务的子流程 |
| 独立使用 | 可以只讨论不派任务 | 必须先有 task 才能讨论 |
| 组合使用 | 讨论结论可触发 task_propose | 同 |

讨论和任务是两种独立的协作模式，不应有从属关系。

### 考虑的替代方案

1. **基于 resource_sync 实现讨论** — 把讨论内容作为 K-V 数据同步。技术上可行，但语义不匹配：讨论是有序的消息流，不是 K-V 状态。强行用 resource_sync 会导致 key 命名混乱、排序困难。
2. **引入独立的 Group Chat 协议层** — 语义最清晰，但引入新的协议层违反 ADR-007 "信封模式，不引入独立协议层"的决策。且 v0.8 阶段参与者少，不需要完整的群聊基础设施。
3. **直接用自由文本消息 + 约定格式** — 零协议改动，但没有结构化保证，投票和结论落盘无法自动化。

## 影响范围

- `agentnexus-sdk/src/agentnexus/discussion.py`：Discussion Protocol 客户端实现（新增）
- `agentnexus-sdk/src/agentnexus/models.py`：DiscussionStart、DiscussionReply、DiscussionVote、DiscussionConclude、Consensus 数据模型（新增）
- `agentnexus-sdk/src/agentnexus/emergency.py`：EMERGENCY_OVERRIDE 内置处理逻辑（新增）
- `agentnexus-sdk/src/agentnexus/config.py`：`emergency_authorized_dids` 配置项（新增）
- Daemon 和 Relay：**无改动**（复用现有信封传输）
- `agent_net/storage.py`：messages 表已有 `message_type` 列（ADR-007），无需额外改动
- OpenClaw Skill 适配器：秘书 Agent 的人类通信桥接（新增，独立模块）

## 测试要求

| 测试场景 | 类型 | 说明 |
|---------|------|------|
| discussion_start 正确扇出给所有 participants | 单元 | 验证点对点扇出逻辑 |
| discussion_reply 的 reply_to 和 mentions 正确传递 | 单元 | 引用和 @提及 |
| discussion_vote 计票逻辑（majority / unanimous / leader_decides） | 单元 | 各种共识模式 |
| consensus.timeout 超时触发 timeout_action | 单元 | auto_approve / auto_reject / escalate |
| 未注册回调的讨论消息回退到 on_message | 单元 | 兜底行为 |
| emergency_halt 授权 DID 发送时强制停止 | 单元 | 验证内置强制执行 |
| emergency_halt 非授权 DID 发送时静默忽略 | 单元 | 权限校验 |
| 完整讨论流程：start → reply → vote → conclude | 集成 | 端到端验证 |
| escalate 流程：超时 → 秘书 Agent 收到 → 人类裁决 → conclude | 集成 | Human-via-Agent 端到端 |
| conclusion_type 为 no_consensus 时正确记录各方立场 | 单元 | 结论冲突处理 |
| request_escalate 触发升级流程 | 单元 | 参与者主动请求升级 |
| related_task_id 关联查询 | 单元 | get_discussion_history(task_id=...) |
| emergency_halt scope=all 只发给已握手 DID | 单元 | 广播范围限制 |
| 多方讨论并发回复，验证 seq 排序 | 集成 | 消息顺序一致性 |
| 秘书 Agent 收到 escalate 后转发格式验证 | 集成 | Human-via-Agent 格式转换 |

## 相关 ADR

- ADR-007: Action Layer 协作协议设计（共用信封模式，讨论协议是平行扩展）
- ADR-003: Sidecar 架构（Discussion Protocol 在 SDK 侧实现，不下沉到 Daemon）
- ADR-006: SDK 架构与 Daemon 通信协议（基于 SDK 的 HTTP 通信层）

## 待定事项

> 以下问题推迟到后续版本处理。

1. **v0.9 Topic 路由的具体设计**：Relay 侧 topic 订阅/退订 API、消息扇出策略、与现有路由的关系。v0.8 的点对点扇出已够用，等遇到 10+ Agent 讨论场景再设计。由未来 ADR 单独记录。
2. **秘书 Agent Skill 规范**：不同平台（OpenClaw / Dify / Coze）的 Skill 接口完全不同，在 ADR 里定义具体规范没有意义。ADR 只定义秘书 Agent 的协议层行为（决策 8），具体 Skill 适配器作为独立文档放在对应适配器目录下。

## 评审记录

| 日期 | 评审者 | 结果 | 备注 |
|------|--------|------|------|
| 2026-04-05 | 御史（小包） | 条件批准 | P1（trust_context T0 未定义）、P2（reply_to 无防伪机制）须在开发前修复；S1–S4 建议性问题后续迭代 |
| 2026-04-05 | 御史（小包） | **批准** | P1 ✅ 已修复（移除 T0，权限改由 emergency_authorized_dids 本地配置）；P2 ✅ 已修复（SDK 校验 reply_to 消息 ID 存在性，标记 unverified_ref） |
| 2026-04-05 | 评审 Agent | 条件批准 | 阻塞性：B1 消息顺序保证、B2 trust_context 未定义、B3 握手列表维护、B4 action_items 耦合文件路径；建议性：S1 查询性能、S2 秘书摘要边界、S3 测试覆盖、S4 与 ADR-010 集成 |
| 2026-04-05 | 设计 Agent | — | 回应评审：B1 已补充投递保证策略和 seq 序号（§3）；B2/P1 已移除 trust_context，权限靠本地配置（§9）；B3 已明确 SDK 自维护握手列表（§14）；B4 action_items 改用逻辑标识符 ref（§6）；P2 reply_to 防伪由 SDK 校验 topic 内消息 ID 存在性（§3 投递保证）；S2 已明确 v0.8 只做格式转换（§8）；S3 已补充 2 个测试场景 |
| 2026-04-05 | 开发 Agent | 条件批准 | 阻塞性：B1 授权配置位置、B2 计票持久化、B3 conclude 权限归属；建议性：S1 讨论历史缓存、S2 timeout 计时、S3 vote 撤回、S4 多轮投票 |
| 2026-04-05 | 设计 Agent | — | 回复开发评审：B1 SDK 配置为主；B2 持久化到 Daemon SQLite（§4 补充）；B3 majority/unanimous 自动 conclude，其他显式调用（§5 补充）；S1 内存缓存；S2 asyncio 计时；S3/S4 v0.8 不支持 |
| 2026-04-05 | 开发 Agent | **批准** | B1-B3 已澄清，S1-S4 已明确，无其他问题 |
| 2026-04-05 | 御史（小包） | **批准** | ADR-010 ✅ 实现完毕（skill 在 storage.py 而非 node/skill.py，功能等效）；ADR-011 ✅ B1/B2/B3 均已修复；⚠️ T1–T4 集成测试（emergency_halt、端到端流程）缺口，后续迭代补充 |
| 2026-04-05 | 开发 Agent | **批准** | B1 ✅ emergency.py 已实现 EmergencyController；B2 ✅ client.py 已添加 on_discussion_* 回调；B3 ✅ get_discussion_history 调用 /messages/all 端点；ADR-010 ✅ 平台适配器 + Skill 端点已实现 |

### 开发评审阻塞性问题详情

| # | 章节 | 问题描述 |
|---|------|---------|
| B1 | §9 | `emergency_authorized_dids` 放在 SDK 配置里，每个 Agent 实例自己维护授权列表。是否应该由 Daemon 统一管理？ |
| B2 | §4/§5 | 计票状态在 SDK 内存中维护，发起方重启后状态丢失。建议持久化到本地文件或 Daemon SQLite |
| B3 | §5/§11 | conclude 的执行权限不明确：SDK 自动判断条件满足后 conclude，还是需要显式调用？ |

### 开发评审建议性问题详情

| # | 章节 | 问题描述 |
|---|------|---------|
| S1 | §12 | 大量讨论消息时 `fetch_inbox` 过滤效率低，建议 SDK 本地缓存 topic_id → messages 映射 |
| S2 | §4 | consensus.timeout 谁来计时？建议发起方 SDK 启动 asyncio 计时任务 |
| S3 | §4 | discussion_vote 是否支持撤回/修改？建议明确 |
| S4 | §11 | 投票不通过后是否支持同一 topic_id 内多轮投票？建议明确 |

## 答疑记录

| 日期 | 提问者 | 问题 | 回复 | 是否触发设计变更 |
|------|--------|------|------|----------------|
| 2026-04-05 | 开发 Agent | B1: `emergency_authorized_dids` 放 SDK 还是 Daemon？ | SDK 配置为主（Agent 级别决策），支持从 Daemon `/config` 继承默认值。同一 Daemon 上多个 Agent 的授权列表可能不同，不应由 Daemon 统一管理。 | 否（实现细节，不改协议） |
| 2026-04-05 | 开发 Agent | B2: 计票状态发起方重启后丢失 | 持久化到 Daemon SQLite，复用 messages 表存一条 `message_type: "discussion_vote_state"`, `protocol: "nexus_v1_internal"` 的内部记录，不路由给其他 Agent。重启后从 Daemon 恢复。 | **是** — §4 补充计票持久化策略，§5 状态机补充恢复逻辑 |
| 2026-04-05 | 开发 Agent | B3: conclude 的执行权限不明确 | 两种模式：majority/unanimous 时 SDK 自动 conclude；null/leader_decides 时需显式调用。只有发起方可 conclude，leader 的 vote 等同于 conclude，其他参与者不能 conclude。 | **是** — §5 补充 conclude 权限规则 |
| 2026-04-05 | 开发 Agent | S1: 讨论历史缓存 | SDK 内存维护 `topic_id → messages[]` 映射，优先查缓存，未命中查 Daemon inbox。不改协议。 | 否 |
| 2026-04-05 | 开发 Agent | S2: timeout 谁来计时 | 发起方 SDK 启动 asyncio 计时任务。重启后从 Daemon 恢复计票状态，重新计算剩余时间。 | 否 |
| 2026-04-05 | 开发 Agent | S3: vote 是否支持撤回 | v0.8 不支持。投票不可撤回，投错可 request_escalate。撤回引入状态回滚复杂度，MVP 不值得。 | 否 |
| 2026-04-05 | 开发 Agent | S4: 同一 topic 多轮投票 | 不支持。投票不通过走决策 11 三条路径，重新发起用新 topic_id + context 引用原 topic。 | 否 |
