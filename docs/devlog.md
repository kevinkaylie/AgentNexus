# 开发日志（Development Log）

> 记录每次开发提交的内容、变更范围和测试结果。
> 按时间倒序排列（最新在最上面）。

---

## 评审问题修复 (2026-04-08)

### 变更概述

修复 devlog.md 和 ADR-012 评审中提出的全部问题（2 个阻塞 + 4 个建议 + 3 个代码评审建议）。

### 变更范围

- `agent_net/relay/server.py` — 修复 admin 签名验证漏洞，移除重复代码
- `agent_net/common/did_methods/meeet.py` — 补全 DID Document 字段，使用共享函数
- `agent_net/common/did_methods/utils.py` — 新增 `compute_x402_score()` 共享函数
- `agent_net/node/mcp_server.py` — 添加广播失败日志
- `agent_net/node/daemon.py` — 添加 `content_encoding` 标记
- `agent_net/router.py` — 支持 `content_encoding` 参数传递
- `agent_net/storage.py` — 支持 `content_encoding` 字段
- `agentnexus-sdk/src/agentnexus/actions.py` — 修复 EXPIRED 状态定义
- `docs/scenarios.md` — 补充场景 5 跨平台协作
- `tests/test_mcp_collaboration.py` — 新增 10 个 MCP 协作工具测试

### 修复内容

#### 阻塞性问题

| # | 问题 | 修复 |
|---|------|------|
| B1 | `/meeet/admin/register` 签名验证形同虚设，用 Relay 自己的密钥验证 | Bootstrap 模式：首次用 Relay 密钥；正常模式：必须用已注册 admin 密钥签名 |
| B2 | DID Document 缺少 `assertionMethod` 字段 | 补全 `assertionMethod: [did#key-1]`，修复 `@context` 顺序 |

#### 建议性问题

| # | 问题 | 修复 |
|---|------|------|
| S1 | `_compute_x402_score()` 两处重复代码 | 提取到 `utils.py` 共享 |
| S2 | `TaskStatus.EXPIRED` 写法混乱 | 明确添加 `EXPIRED` enum，清理 `hasattr` 检查 |
| S3 | `@context` 顺序错误 | DID Core context 在前（已在 B2 中一并修复）|
| S4 | dict content 序列化后无 `content_encoding` 标记 | 新增 `content_encoding` 字段，存储时标记 `"json"` |

#### ADR-012 代码评审建议

| # | 问题 | 修复 |
|---|------|------|
| CP1 | `start_discussion` 广播失败无日志 | 添加 `logger.warning(f"Failed to notify {did}: {e}")` |
| CP2 | scenarios.md 缺少场景 5 | 补充跨平台 MCP 协作场景（中英双语）|
| CP3 | 缺少测试覆盖 | 新增 `tests/test_mcp_collaboration.py`（10 个测试用例）|

### 测试结果

```
157 passed, 3 skipped ✅
```

---

## 代码评审 — v0.8.0 / v0.8.1 完整评审 (2026-04-07)

**评审者：** 锦衣卫指挥使（小鹰）
**结果：** 条件批准（2 项阻塞性问题建议修复后再发版，其余建议性/信息性问题可后续迭代）

### 复审（2026-04-08 00:18）

**结果：** ✅ 批准

| # | 问题 | 验证结果 |
|---|------|---------|
| B1 | MEEET admin 签名验证形同虚设 | ✅ 已修复 — Bootstrap 模式（首次注册用 Relay 签名密钥）+ 正常模式（遍历已注册 admin 公钥验签名），逻辑正确 |
| B2 | MeeetHandler DID Document 缺 authentication/assertionMethod | ✅ 已修复 — `authentication` 和 `assertionMethod` 字段已补全 |
| S1 | `_compute_x402_score()` 两处重复 | ✅ 已修复 — 提取到 `utils.py`，两处统一 import |
| S2 | `TaskStateMachine` EXPIRED 混乱处理 | ✅ 已修复 — `TaskStatus.EXPIRED = "expired"` 明确定义，`VALID_TRANSITIONS` 使用正式 enum |
| S3 | meeet DID Document @context 顺序 | ✅ 已修复 — DID Core 在前，security vocabulary 在后，并添加注释说明 |

**复审测试结果：**
```
157 passed, 3 skipped ✅
```
（新增 10 个测试用例覆盖修复点）

### 关联 ADR

ADR-009（ DID Method Handler 注册表）、ADR-007（Action Layer）、ADR-008（did:meeet 桥接）、ADR-011（Discussion Protocol）、ADR-012（MCP 协作层）

### 初审测试结果

```
147 passed, 3 skipped ✅
```

### 阻塞性问题（建议修复后再发版）

| # | 文件 | 问题描述 | 修复建议 |
|---|------|---------|---------|
| B1 | `agent_net/relay/server.py` 第 844-875 行 | `/meeet/admin/register` 签名验证形同虚设：使用 Relay 自己的 `relay_vk` 验证 admin 签名，而非验证 admin 公钥是否在白名单中。任何人都能用 Relay 自身的密钥自签名绕过验证。 | 引入 admin 公钥白名单机制（Redis SET `_MEEET_ADMINS_KEY` 已在存储层就绪），验证时应检查 `req.admin_pubkey` 是否在白名单中，再验证其签名来自对应私钥。当前 `sismember` 检查在存储写入前执行，属于实现顺序错误。 |
| B2 | `agent_net/common/did_methods/meeet.py` 第 174-180 行 | `_build_result()` 构建的 DID Document 缺少 `authentication` 和 `assertionMethod` 字段。W3C DID Core 规范要求验证方法必须被引用才能生效，当前只有 `verificationMethod` 无法用于 authentication/assertion。 | 参照 `utils.build_did_document()` 第 63-67 行，补全：`authentication: [f"{agentnexus_did}#key-1"]` 和 `assertionMethod: [f"{agentnexus_did}#key-1"]` |

### 建议性问题

| # | 文件 | 问题描述 | 处理状态 |
|---|------|---------|---------|
| S1 | `agent_net/common/did_methods/meeet.py` 第 103 行 / `agent_net/relay/server.py` 第 858 行 | `_compute_x402_score()` 两处完全相同的代码重复。维护性炸弹，后续修改公式容易只改一处。 | 提取到 `agent_net/common/did_methods/utils.py` 共用 |
| S2 | `agentnexus-sdk/src/agentnexus/actions.py` 第 164-170 行 | `TaskStateMachine.VALID_TRANSITIONS` 中 `TaskStatus.EXPIRED if hasattr(TaskStatus, 'EXPIRED') else "expired"` 运行时 `TaskStatus.EXPIRED` 不存在，实际总是字符串 `"expired"`。逻辑能跑但写法混乱。 | 统一使用字符串或明确定义 `EXPIRED` enum |
| S3 | `agent_net/common/did_methods/meeet.py` 第 172-174 行 | `@context` 顺序为 `["https://www.w3.org/ns/did/v1", "https://w3id.org/security/multikey/v1"]`，W3C DID Core 要求第一个是 DID Core context，security vocabulary 应在后面。`utils.build_did_document()` 顺序正确。 | 交换两行顺序 |
| S4 | `agent_net/node/daemon.py` 第 646-660 行 | Action Layer 消息的 `content` 传入时若为 dict，会被 `json.dumps` 序列化为 string，但无 `content_encoding` 标记。接收方需反序列化才能判断类型。 | 建议存储时明确 `content_encoding: "json"` 字段，或约定 SDK 侧统一传 string |

### 信息性问题

| # | 文件 | 问题描述 | 处理状态 |
|---|------|---------|---------|
| I1 | `agent_net/node/daemon.py` 第 725 行 | `/health` 端点只返回 `{"status": "ok"}`，而 Relay `/health` 返回 DID 和统计信息。对齐更好。 | 无需处理 |
| I2 | `agent_net/common/did_methods/utils.py` 第 131 行 | `User-Agent: "AgentNexus/1.0"` 硬编码版本号，未与实际版本同步。 | 无需处理 |
| I3 | `agent_net/common/did_methods/utils.py` `extract_ed25519_key_from_doc()` | 当 `type == "Ed25519VerificationKey2018"` 且有 `publicKeyJwk` 时会跳过 JWK 处理路径（代码只处理了 `Ed25519VerificationKey2020` + JWK）。实际不会命中但逻辑不完整。 | 无需处理 |

### 架构亮点（值得保持）

- **ADR-009 注册表模式**：比 if/elif 链优雅得多，后续加新 DID 方法只需注册 handler
- **测试覆盖**：147 tests 覆盖 DID resolution、federation、keystore、gatekeeper、online、discussion，结构清晰
- **Action Layer 协议设计**：SDK 侧完整，dataclass 封装合理
- **EmergencyController**：设计干净，callback + asyncio.Event halt 机制合理
- **DIDResolver 与存储层解耦**：Daemon 用 `db_path`，Relay 用 `redis_client`，各自注册需要的 handler

---

## ADR-012 v0.8 MCP 协作层工具实现 (2026-04-07)

### 变更概述

实现 ADR-012 定义的 v0.8 L7 协作层补全，新增 10 个 MCP 工具。

### 变更范围

- `agent_net/node/mcp_server.py` — 新增 10 个 Tool 定义 + call_tool 分支
- `docs/mcp-setup.md` — 更新工具列表（17→27）
- `docs/architecture.md` — 补充 ACP 协议栈、更新工具数量
- `docs/cross-platform-mcp-config.md` — 新建跨平台配置示例文档

### 提交内容

#### 1. MCP Action Layer 工具（4 个）

| 工具名 | message_type | 说明 |
|--------|--------------|------|
| `propose_task` | `task_propose` | 派发/委派任务，返回 task_id |
| `claim_task` | `task_claim` | 认领任务 |
| `sync_resource` | `resource_sync` | 共享 K-V 资源 |
| `notify_state` | `state_notify` | 汇报任务状态/进度 |

#### 2. MCP Discussion 工具（4 个）

| 工具名 | message_type | 说明 |
|--------|--------------|------|
| `start_discussion` | `discussion_start` | 发起多方讨论，返回 topic_id |
| `reply_discussion` | `discussion_reply` | 回复讨论（to_did 为发起方） |
| `vote_discussion` | `discussion_vote` | 投票表决 |
| `conclude_discussion` | `discussion_conclude` | 宣布结论并关闭 |

#### 3. MCP Emergency + Skill 工具（2 个）

| 工具名 | 说明 |
|--------|------|
| `emergency_halt` | 紧急熔断（独立 message_type，不复用 state_notify） |
| `list_skills` | 查询节点注册的 Skills |

#### 4. 文档更新

- **mcp-setup.md**：工具列表从 17 个更新为 27 个，新增协作层工具分类说明
- **architecture.md**：
  - 架构图工具数量 12→27
  - 新增 ACP 协议栈九层模型图
  - 新增 MCP 工具分类表
- **cross-platform-mcp-config.md**：新建文档，提供 Kiro CLI / Claude Code / OpenClaw / Claude Desktop / Cursor 配置示例

### 关键设计决策

1. **独立 message_type**：`emergency_halt` 使用独立 message_type 而非复用 `state_notify`（ADR-012 评审 P4 修复）
2. **start_discussion 多播**：向每个 participant 分别发送 invitation
3. **to_did 语义明确**：`reply_discussion` / `vote_discussion` 的 `to_did` 指向讨论发起方（ADR-012 评审 P1 修复）

### 测试结果

```
147 passed, 3 skipped ✅
```

---

## ADR-010 平台适配器 + ADR-011 完整实现 (2026-04-05)

### ADR-010 平台适配器架构实现

**变更范围：**
- 新增 `agent_net/adapters/` 目录
- 更新 `agent_net/node/daemon.py` 添加 `/adapters/*` 和 `/skills/*` 端点
- 更新 `agent_net/storage.py` 已有 skills 表

**提交内容：**

1. **PlatformAdapter 抽象基类** (`base.py`)
   - `inbound()` — 外部平台 → AgentNexus
   - `outbound()` — AgentNexus → 外部平台
   - `skill_manifest()` — 返回 Skill 描述
   - `SkillManifest` 数据类

2. **AdapterRegistry** (`registry.py`)
   - `register()` / `unregister()` / `get()` / `list()`
   - 与 ADR-009 注册表模式一致

3. **OpenClawAdapter** (`openclaw.py`)
   - 四种 action：`invoke_skill` / `query_status` / `send_message` / `get_profile`
   - 持有 agent_did + router + storage

4. **WebhookAdapter** (`webhook.py`)
   - HMAC-SHA256 签名验证
   - 可复用 HTTP session
   - `callback_url` 配置

5. **Daemon 端点**
   - `POST /adapters/{platform}/invoke` — 调用适配器
   - `POST /adapters/{platform}/register` — 注册适配器
   - `GET /skills` — 列出已注册 Skill
   - `GET /skills/{skill_id}` — 获取 Skill 详情
   - `POST /skills/register` — 注册 Skill
   - `DELETE /skills/{skill_id}` — 注销 Skill
   - `GET /messages/all/{did}` — 获取所有消息（含已投递）

### ADR-011 阻塞性问题修复

| # | 问题 | 修复内容 |
|---|------|---------|
| B1 | `emergency_halt` 未实现 | 新增 `emergency.py`，实现 `EmergencyController`，集成到 client.py `_dispatch_message` |
| B2 | SDK 回调未注册 | 添加 `on_discussion_start/reply/vote/conclude` 回调，`_dispatch_message` 路由 discussion 消息 |
| B3 | `get_discussion_history()` 是 TODO stub | 实现完整逻辑：调用 daemon `/messages/all` 端点，按 topic_id/task_id 过滤 |

**新增文件：**
- `agentnexus-sdk/src/agentnexus/emergency.py`
- `agent_net/adapters/__init__.py`
- `agent_net/adapters/base.py`
- `agent_net/adapters/registry.py`
- `agent_net/adapters/openclaw.py`
- `agent_net/adapters/webhook.py`

**新增测试文件：**
- `agentnexus-sdk/tests/test_emergency.py` — EmergencyController 单元测试
  - 授权 DID 发送 emergency_halt 强制停止
  - 非授权 DID 发送静默忽略
  - callback 触发（sync/async）
  - scope 范围记录
  - wait_for_halt 超时机制

**补充 ADR-011 测试用例（test_discussion.py 扩展）：**
- discussion_start 正确扇出给所有 participants
- discussion_reply 的 reply_to 和 mentions 正确传递
- consensus.timeout 超时触发 timeout_action
- 未注册回调的讨论消息回退到 on_message
- conclusion_type 为 no_consensus 时正确记录各方立场
- request_escalate 触发升级流程
- related_task_id 关联查询
- 多方讨论 seq 排序

**测试结果：** 147 passed, 3 skipped ✅（SDK 新增 73 个测试）

---

## Discussion Protocol 实现 + 建议性问题修复 (2026-04-05)

### ADR-011 Discussion Protocol 实现

**变更范围：**
- 新增 `agentnexus-sdk/src/agentnexus/discussion.py`
- 更新 `agentnexus-sdk/src/agentnexus/__init__.py` 导出
- 新增 `agentnexus-sdk/tests/test_discussion.py`
- 新增 `agentnexus-sdk/tests/test_actions.py`
- 新增 `agentnexus-sdk/examples/echo_bot.py`
- 新增 `agentnexus-sdk/examples/discussion_demo.py`

**提交内容：**

1. **Discussion Protocol 数据模型**
   - `DiscussionStart` — 发起讨论（topic_id, title, participants, consensus, related_task_id）
   - `DiscussionReply` — 回复/引用/@提及（reply_to, mentions, request_escalate）
   - `DiscussionVote` — 投票表决（vote: approve/reject/abstain）
   - `DiscussionConclude` — 结束讨论（conclusion_type, action_items）
   - `Consensus` — 共识规则（mode, timeout_seconds, timeout_action）
   - `ActionItem` — 后续动作（type, ref, description）

2. **DiscussionStateMachine**
   - 状态管理：open → voting → concluded
   - 计票逻辑：majority / unanimous / leader_decides
   - reply_to 防伪验证（unverified_ref 标记）
   - seq 序号生成
   - timeout 剩余时间计算
   - 计票状态持久化支持（nexus_v1_internal）

3. **DiscussionManager**
   - 管理多个讨论（发起/参与）
   - start_discussion / reply / vote / conclude API
   - 点对点扇出（v0.8 策略）
   - 讨论历史查询

### 建议性问题修复

| # | 文件 | 问题描述 | 修复状态 |
|---|------|---------|---------|
| S1 | `agentnexus-sdk/src/agentnexus/client.py` | `_poll_messages` 指数退避无重置，长时间运行后轮询间隔永远是 max_backoff | ✅ 已修复 — 添加 success_count 计数，连续成功 10 次后重置状态 |
| S2 | `agentnexus-sdk/src/agentnexus/client.py` | `close()` 未等待 `_poll_task` 完成 | ✅ 已修复 — 添加 asyncio.wait_for 超时等待 |
| S3 | `agentnexus-sdk/tests/` | 目录为空，SDK 无测试覆盖 | ✅ 已修复 — 新增 test_discussion.py, test_actions.py |
| S4 | `agentnexus-sdk/examples/` | 目录为空 | ✅ 已修复 — 新增 echo_bot.py, discussion_demo.py |
| S2 (ADR-009) | `agent_net/common/did_methods/meeet.py` | `_resolve_via_solana` 吞掉所有异常 | ✅ 已修复 — 添加 logging.warning 记录异常类型和消息 |
| S3 (ADR-009) | `agent_net/common/did_methods/agent_legacy.py` | `_get_local_agent_key` 吞异常 | ✅ 已修复 — 添加 logging.warning |
| S4 (ADR-009) | `agent_net/relay/server.py` | `resolve_did` 内两处重复 lazy import | ✅ 已修复 — 提取为模块级函数 `_get_build_did_document()` |

**测试结果：** 147 passed, 3 skipped ✅

---

## 废代码清理 (2026-04-05)

| 文件 | 操作 | 理由 |
|------|------|------|
| `agent_net/daemon.py` | 删除 | v0.1 原型代码，功能已被 `agent_net/node/daemon.py` 完全替代，全项目零引用。147 测试全通过。 |

---

## 代码评审 — ADR-010 平台适配器 / ADR-011 讨论协议（复审 2026-04-05）

**评审者：** 御史（小包）
**结果：** 批准（ADR-011）；批准（ADR-010，有一项结构偏差需说明）

### ADR-010 平台适配器

| 章节 | 应有实现 | 实际状态 | 备注 |
|------|---------|---------|------|
| §1 `agent_net/adapters/base.py` | PlatformAdapter ABC | ✅ 存在 | — |
| §1 `agent_net/adapters/openclaw.py` | OpenClawAdapter | ✅ 存在 | — |
| §1 `agent_net/adapters/webhook.py` | WebhookAdapter | ✅ 存在，含 HMAC-SHA256 签名验证 |
| §1 `agent_net/adapters/registry.py` | AdapterRegistry | ✅ 存在 | — |
| §3 | SkillRegistry 函数 | ✅ 在 `storage.py` 中实现（不在 `node/skill.py`，结构偏差但功能等效） |
| §6 `/adapters/{platform}/invoke` | Daemon 端点 | ✅ 存在（daemon.py:937） |
| §6 `/adapters/{platform}/register` | Daemon 端点 | ✅ 存在（daemon.py:960） |
| §6 `/skills` | Skill 查询端点 | ✅ GET/POST/DELETE 均存在（daemon.py:1003-1053） |
| §3 | SQLite skills 表 | ✅ 在 storage.py 中 | — |

**ADR-010 结论：** ✅ 批准。唯一偏差：SkillRegistry 函数在 `storage.py` 而非 ADR 规划的 `node/skill.py`，但功能完整，不阻塞。

### ADR-011 讨论协议

#### 已实现 ✅

| 模块 | 文件 | 评价 |
|------|------|------|
| 数据模型 | `discussion.py` §Data Models | ✅ 四个 message type + Consensus + ActionItem，序列化/反序列化正确 |
| 状态机 | `discussion.py` §DiscussionStateMachine | ✅ open/voting/concluded 状态转换正确；seq 序号；reply_to 防伪（known_message_ids） |
| 计票逻辑 | `check_consensus()` | ✅ majority/unanimous/leader_decides 三种模式正确 |
| timeout 处理 | `_handle_timeout()` | ✅ asyncio.sleep + TimeoutAction 三种行为 |
| SDK 回调注册 | `client.py` | ✅ `on_discussion_start/reply/vote/conclude` 已注册，`_dispatch_message` 正确路由 |
| emergency_halt | `emergency.py` | ✅ `EmergencyController` 实现：授权检查、静默忽略未授权、asyncio.Event halt、内置停止动作、`state_notify(status=halted)` 回复、`on_emergency` 回调 |
| history 查询 | `discussion.py get_discussion_history()` | ✅ 实现完整：`_fetch_all_messages()` → topic_id/task_id 过滤 → 缓存 |
| 单元测试 | `tests/test_discussion.py` | ✅ 覆盖全部模型 + 状态转换 + 计票逻辑 |

#### 缺失测试覆盖 ⚠️

| # | 测试场景 | 说明 |
|---|---------|------|
| T1 | `emergency_halt` 授权 DID 发送时强制停止 | ADR-011 测试要求，未覆盖 |
| T2 | `emergency_halt` 非授权 DID 静默忽略 | ADR-011 测试要求，未覆盖 |
| T3 | `emergency_halt scope=all` 只发给已握手 DID | ADR-011 测试要求，未覆盖 |
| T4 | 集成：discussion_start → reply → vote → conclude 端到端 | ADR-011 测试要求，未覆盖 |

**ADR-011 结论：** ✅ 批准。B1/B2/B3 均已修复。T1–T4 为测试缺口，建议后续迭代补充。

---

## 设计评审 — ADR-011 Discussion Protocol (2026-04-05)

**评审者：** 御史（小包）
**结果：** 条件批准

### 阻塞性问题

| # | 位置 | 问题描述 | 处理状态 |
|---|------|---------|---------|
| P1 | ADR-011 决策 9 | `trust_context: "T0"` 在 L1–L4 信任体系中未定义，属于跨 ADR 概念缺失 | ✅ 闭环 — 设计 Agent 已移除 T0，改用 emergency_authorized_dids 本地配置（ADR §9）；御史确认修复后在 ADR 评审记录中批准 |
| P2 | ADR-011 决策 2 | `discussion_reply.reply_to` 无防伪验证，恶意 Agent 可构造虚假引用破坏讨论连贯性 | ✅ 闭环 — 设计 Agent 已补充 SDK 校验逻辑（ADR §3 unverified_ref 标记）；御史确认修复后在 ADR 评审记录中批准 |

### 建议性问题

| # | 位置 | 问题描述 | 处理状态 |
|---|------|---------|---------|
| S1 | ADR-011 决策 13 | `request_escalate` 合法时机未定义（concluded 后能否 escalate？） | 后续迭代 |
| S2 | ADR-011 决策 4 | 投票计票是否含发起方、leader 是否需先投票，均未说明 | 后续迭代 |
| S3 | ADR-011 决策 8/11 | Escalate 后人类裁决结论以何种协议消息落盘未定义 | 后续迭代 |
| S4 | ADR-011 决策 8 | 秘书 Agent 摘要粒度和翻译策略需要边界定义（建议在 ADR-010 补充） | 后续迭代 |

---

## 代码评审 — Bug 报告 (2026-04-05)

**发现者：** 御史（小包）
**结果：** 阻塞性问题 1 项，建议性问题 1 项

### 阻塞性问题

| # | 文件 | 问题描述 | 修复状态 |
|---|------|---------|---------|
| B1 | `agent_net/node/daemon.py` 第 884-893 行 | `/deliver` 端点不提取 `message_type` 和 `protocol` 字段，导致经 Relay 转发的 Action Layer 消息（`task_propose` 等）无法触发 SDK 状态机，R-0803 功能实际不可用。`api_send_message` 正确传递了这两个字段，但 `/deliver` 被遗漏。 | ✅ 已修复 — 代码已包含 message_type 和 protocol 提取 |

**修复方案：**
```python
@app.post("/deliver")
async def api_deliver(payload: dict):
    from_did = payload.get("from")
    to_did = payload.get("to")
    content = payload.get("content")
    if not all([from_did, to_did, content]):
        raise HTTPException(400, "Missing fields")
    session_id = payload.get("session_id", "")
    reply_to = payload.get("reply_to")
    message_type = payload.get("message_type")
    protocol = payload.get("protocol")
    return await router.route_message(from_did, to_did, content, session_id, reply_to,
                                     message_type=message_type, protocol=protocol)
```

### 建议性问题

| # | 文件 | 问题描述 | 处理状态 |
|---|------|---------|---------|
| S1 | `agent_net/common/did_methods/meeet.py` `_resolve_via_solana()` | Solana API 不可达时 `except Exception: return None`，所有异常类型被归一化为 `None`，最终统一抛出 `DIDNotFoundError`。无法区分"网络故障"和"DID 不存在"，不符合 R-0809 设计意图（应有诊断信息）。ADR-009 评审时已标记为 S2，列为"后续迭代"，本次重提。 | 后续迭代 |

**修复建议：** 在 `except Exception` 前增加 `logging.warning(f"Solana API 调用失败: {type(e).__name__} — {e}")`，便于运维区分故障类型。

### 新增测试用例

| 测试文件 | 测试场景 | 覆盖的 Bug |
|---------|---------|-----------|
| `tests/test_cases.py` | `test_tc08`：`/deliver` 端点透传 `message_type` 和 `protocol`，验证 Action Layer 消息不丢失 | B1 |
| `tests/test_did_resolution.py` | `test_td13`：`did:meeet` 缓存命中时返回正确 DID Document | B2 |
| `tests/test_did_resolution.py` | `test_td14`：Solana API 不可达时抛出 `DIDNotFoundError`，不回退到未验证密钥 | B2 |

---

## 代码评审 — ADR-009 DID Method Handler 注册表重构 (2026-04-04)

**关联 ADR：** ADR-009
**评审者：** 评审 Agent
**结果：** 批准

### 阻塞性问题

无。

### 建议性问题

| # | 文件 | 问题描述 | 处理状态 |
|---|------|---------|---------|
| S1 | agent_net/common/did.py | `DIDResolver.__init__` 空 `pass` 可删除 | 后续迭代 |
| S2 | agent_net/common/did_methods/meeet.py | `_resolve_via_solana` 吞掉所有异常，建议加 logging.warning | ✅ 已修复 (2026-04-05) |
| S3 | agent_net/common/did_methods/agent_legacy.py | `_get_local_agent_key` 吞异常，建议加 logging | ✅ 已修复 (2026-04-05) |
| S4 | agent_net/relay/server.py | `resolve_did` 内两处重复 lazy import build_did_document | ✅ 已修复 (2026-04-05) |

### 新增测试用例

测试 fixture 使用 `autouse=True` + `reset_handlers()` 实现隔离，已有 39 个 DID resolution 测试覆盖注册表路由。

### 修复内容（2026-04-04）

1. **client.py**：在 import 中添加 `AgentNexusError`
2. **sync.py**：`_run()` 改用 `asyncio.run_coroutine_threadsafe()` 处理 loop 已运行的情况，避免跨 loop session 问题

---

## 代码评审 — SDK v0.8.0 (2026-04-04)

**关联 ADR：** ADR-006, ADR-007, ADR-008
**评审者：** 评审 Agent
**结果：** 批准

### 阻塞性问题

| # | 文件 | 问题描述 | 修复状态 |
|---|------|---------|---------|
| 1 | agentnexus-sdk/src/agentnexus/client.py | `_register_new_agent` 引用未导入的 `AgentNexusError`，运行时 NameError | ✅ 已修复 |
| 2 | agentnexus-sdk/src/agentnexus/sync.py | `_run()` 在 loop.is_running() 时创建新 loop，导致 session 跨 loop 失效 | ✅ 已修复 |

### 建议性问题

| # | 文件 | 问题描述 | 处理状态 |
|---|------|---------|---------|
| S1 | agentnexus-sdk/src/agentnexus/client.py | `_poll_messages` 指数退避无上限重置，长时间运行后轮询间隔永远是 max_backoff | ✅ 已修复 (2026-04-05) |
| S2 | agentnexus-sdk/src/agentnexus/client.py | `close()` 未等待 `_poll_task` 完成，可能有残留请求 | ✅ 已修复 (2026-04-05) |
| S3 | agentnexus-sdk/src/agentnexus/actions.py | `TaskStateMachine` 状态转换无持久化，进程重启后状态丢失 | 后续迭代（Discussion Protocol 已实现持久化支持） |
| S4 | agentnexus-sdk/tests/ 和 examples/ | 目录为空，SDK 无任何测试覆盖 | ✅ 已修复 (2026-04-05) |

---

## 2026-04-04 (下午)

### ADR-009: DID Method Handler 注册表架构重构

**变更范围：**
- 新增 `agent_net/common/did_methods/` 目录
- `agent_net/common/did.py`：DIDResolver 改为注册表路由
- `agent_net/node/daemon.py`：启动时调用 `register_daemon_handlers()`
- `agent_net/relay/server.py`：启动时调用 `register_relay_handlers()`，简化 resolve_did

**提交内容：**

1. **DIDMethodHandler 抽象基类**
   - `did_methods/base.py`：定义 `method` 属性和 `resolve()` 抽象方法

2. **工具函数**
   - `did_methods/utils.py`：`build_did_document()`、`extract_ed25519_key_from_doc()`、`fetch_did_web_document()`

3. **五个 Handler 实现**
   - `agentnexus.py`：AgentNexusHandler — 纯密码学解析
   - `agent_legacy.py`：AgentLegacyHandler — 需 db_path，仅 Daemon 注册
   - `key.py`：KeyHandler — 纯密码学解析
   - `web.py`：WebHandler — HTTPS 端点获取
   - `meeet.py`：MeeetHandler — 需 redis_client，仅 Relay 注册

4. **注册函数**
   - `register_daemon_handlers(db_path)`：注册 agentnexus/agent/key/web
   - `register_relay_handlers(redis_client)`：注册 agentnexus/key/web/meeet
   - `reset_handlers()`：测试隔离

5. **DIDResolver 重构**
   - 移除 `_resolve_*` 私有方法
   - `resolve()` 改为查注册表路由到 handler
   - `register()` / `reset_handlers()` 类方法

**测试结果：** 144 passed, 3 skipped ✅

---

## 2026-04-04 (上午)

### v0.8.0 — SDK 基础 + Action Layer + did:meeet 桥接

**变更范围：**
- 新增 `agentnexus-sdk/` 独立包
- `agent_net/node/daemon.py`：Token 写入用户目录、messages/send 支持 Action Layer
- `agent_net/storage.py`：messages 表新增 message_type/protocol 列
- `agent_net/router.py`：路由支持 message_type/protocol 参数
- `agent_net/relay/server.py`：MEEET 桥接端点、did:meeet 解析

**提交内容：**

1. **SDK 包结构（ADR-006）**
   - `pyproject.toml`：依赖 aiohttp + pydantic
   - `src/agentnexus/__init__.py`：导出核心 API
   - `src/agentnexus/client.py`：AgentNexusClient 核心类
   - `src/agentnexus/discovery.py`：Daemon/Token 自动发现
   - `src/agentnexus/exceptions.py`：异常层次
   - `src/agentnexus/models.py`：Message/VerificationResult/Certification
   - `src/agentnexus/sync.py`：同步包装器

2. **SDK 核心 API**
   - `connect(name, caps)`：注册新身份
   - `connect(did=...)`：复用已注册身份（Q2 答疑）
   - `send(to_did, content)`：发送消息
   - `verify(did)`：信任查询
   - `certify(target_did, claim, evidence)`：签发认证
   - `on_message` 回调：接收消息
   - 轮询机制 + 指数退避（Q1 答疑）

3. **Action Layer（ADR-007）**
   - `src/agentnexus/actions.py`：四种协作动作
   - `task_propose` / `task_claim` / `resource_sync` / `state_notify`
   - TaskStateMachine 状态机
   - session_id 格式：`sess_{uuid4}`（Q5 答疑）

4. **Daemon 侧改动**
   - messages 表新增 `message_type` / `protocol` 列（Q4 答疑）
   - `fetch_inbox()` 返回新字段（Q6 答疑）
   - `/messages/send` 接受 `Union[str, dict]`
   - Token 写入 `~/.agentnexus/daemon_token.txt`

5. **did:meeet 桥接（ADR-008）**
   - `POST /meeet/admin/register`：平台管理员注册
   - `POST /meeet/register`：单个 Agent 注册
   - `POST /meeet/batch-register`：批量注册（最大 100 条）
   - `GET /meeet/status`：状态统计
   - `GET /resolve/did:meeet:...`：解析 MEEET DID
   - Mock Solana API 支持（Q7 答疑）
   - x402 score 映射公式

**测试结果：** 144 passed, 3 skipped ✅

---

## 2026-04-03

### 多 Agent 协作文档系统

**变更范围：** 文档（无代码变更）

**提交内容：**
- 创建 `AGENTS.md` 上下文索引（项目根目录）
- 创建 4 个角色手册：`docs/roles/{design,development,review,testing}-agent.md`
- 创建 5 个 ADR：`docs/adr/001-005`（DID 格式、握手协议、Sidecar 架构、多 CA、Gatekeeper）
- 创建 ADR 模板：`docs/adr/000-template.md`
- 创建 3 个接口契约：`docs/contracts/{giskard-ca,oatr-jwt,qntm-did-resolution}.md`
- 创建设计评审流程：`docs/processes/design-review.md`
- 创建 WIP 追踪：`docs/wip.md`
- 创建 4 个文档模板：`docs/templates/{role-handbook,adr,contract,wip-entry}.tmpl.md`
- 更新 `.gitignore`：新增 `docs/wip.md`、`docs/contracts/giskard-ca-certification.md`、`docs/contracts/oatr-jwt-attestation.md` 为仅本地文件
- 创建项目级需求文档 `docs/requirements.md`、设计文档 `docs/design.md`、开发日志 `docs/devlog.md`

**测试结果：** 无代码变更，无需测试

---

## 2026-03-27

### v0.7.1 — Relay did:web 支持

**变更范围：** `agent_net/relay/server.py`, `agent_net/common/did.py`, `tests/`

**提交内容：**
- Relay 身份持久化（`data/relay_identity.json`）
- `GET /.well-known/did.json` 端点
- CLI `relay start --host` 参数
- DID Document 包含 Ed25519 + X25519 + service
- 测试用例（本地 + 线上公网）

**测试结果：** 144/144 通过 ✅

---

## 2026-03-27

### v0.7.6 — Protocol 规范化

**变更范围：** `agent_net/relay/server.py`

**提交内容：**
- anpn_register 存储时 normalize protocol lowercase
- anpn_lookup 查询时 normalize protocol lowercase
- 与 AiAgentKarl ANP bridge 对齐互操作方案

**测试结果：** 144/144 通过 ✅

---

## 2026-03-26

### v0.6.0 — W3C DID Method + Key Export/Import

**变更范围：** `agent_net/common/did.py`, `agent_net/common/keystore.py`, `agent_net/relay/server.py`, `agent_net/node/daemon.py`, `tests/`

**提交内容：**
- `did:agentnexus` 新格式（multikey 编码）
- W3C DID Document 输出
- Relay + Daemon `/resolve/{did}` 端点
- 密钥导出/导入（argon2id + SecretBox）
- 44 个新测试

**测试结果：** 124/124 通过 ✅

---

## 2026-03-26

### v0.5.0 — Session Management + Certifications

**变更范围：** `agent_net/storage.py`, `agent_net/router.py`, `agent_net/common/profile.py`, `agent_net/node/daemon.py`, `agent_net/node/mcp_server.py`

**提交内容：**
- 消息 session_id + reply_to 字段
- `GET /messages/session/{session_id}` 端点
- NexusProfile certifications 顶层字段
- `create_certification()` / `verify_certification()` 函数
- Giskard 集成提案文档
- 12 个新测试

**测试结果：** 80/80 通过 ✅

---

## 更早版本

参考 [CHANGELOG.md](../CHANGELOG.md) 获取 v0.1.0 ~ v0.4.0 的变更记录。
