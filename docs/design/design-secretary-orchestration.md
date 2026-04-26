# AgentNexus 设计专题 — 常驻秘书与 Agent 团队协作编排

> 状态：活跃
> 目标：收敛“社交媒体/外部入口 -> 常驻秘书 Agent -> 本地/局域网 Worker 团队协作 -> 结果回传”的专项设计。
> 关联文档：
> - [design-v1.0.md](design-v1.0.md) — Owner DID、消息中心、意图路由、鉴权矩阵
> - [design-v0.x.md](design-v0.x.md) — SDK、Action Layer、适配器、Enclave/Playbook
> - [roadmap.md](../roadmap.md) — 版本路线图
> - [scenarios.md](../scenarios.md) — 跨平台协作场景

---

## 1. 问题定义

我们要支持的目标链路：

```text
社交媒体 / Webhook / OpenClaw 入口
  -> 常驻秘书 Agent 接单
  -> 选择团队成员（设计 / 开发 / 测试 / 评审）
  -> 唤醒或通知本地 / 局域网 Worker
  -> Enclave + Playbook 自动推进
  -> 汇总交付物
  -> 回传给主人
```

本专题聚焦“协作编排层”，不重复定义 DID、Relay、基础消息协议。

### 1.1 定位收敛

AgentNexus 仍然是 Agent 原生通信基础设施，但单独表达“Agent 能互相通信”过于抽象，当前更清晰的产品形态是：

> 基于 DID、Relay、加密消息和访问控制的 Agent 团队协作与流程编排底座。

因此，本专题不是把 AgentNexus 收窄为“开发团队工具”，而是把原有通信基础设施具象到企业流程化协作场景：

- 开发团队只是首个高频模板：需求 -> 设计 -> 评审 -> 开发 -> 测试 -> 交付
- 同一套机制也适用于客服升级、采购审批、合同审查、风控复核、运营工单等流程
- OpenClaw / CLI / Webhook / SDK Agent 都应视为入口或 Worker Adapter，而不是系统核心边界
- AgentNexus 的核心边界是身份、授权、消息、流程状态、共享产物、失败接管和可信交付

---

## 2. 运行形态模型

### 2.1 Agent 类型

| 类型 | 说明 | 在线模型 | 适合角色 |
|------|------|---------|---------|
| `resident` | 常驻进程，持续监听消息/任务 | 长连接或常驻轮询 | 秘书、项目经理、守护进程型 Reviewer |
| `interactive_cli` | 由本地命令拉起的 CLI Worker | 启动后上线，退出后离线 | Claude Code、Kiro、OpenAI CLI 等执行岗 |
| `service_worker` | Webhook / SDK / 平台适配器驱动 | 依赖平台回调或本地服务 | OpenClaw、Dify、Coze 等 |

### 2.2 基本判断

- 秘书 / 项目经理默认要求 `resident`
- 设计 / 开发 / 测试 / 评审允许 `resident` 或 `interactive_cli`
- `interactive_cli` 是否可纳入自动编排，取决于是否具备“可被本地命令拉起”的 Worker Launcher

### 2.3 需要补充的设计点

- `resident` 的在线判定、心跳、故障恢复
- `interactive_cli` 的启动命令、工作目录、环境变量、上下文注入
- 各类型 Agent 的统一元数据模型

### 2.4 秘书身份决策

本专题在最终版中做如下收敛：

- 秘书不是独立于 Owner 的匿名系统角色
- 秘书应定义为 **Owner DID 之下的专用子 Agent**
- 建议 `profile.type = "secretary"`，并通过现有 owner-agent 绑定关系挂到对应 `owner_did`
- 一个 Owner 可绑定一个或多个秘书子 Agent，但 Phase A 默认只启用一个主秘书
- Phase A 的 `actor_did` 应为该秘书子 Agent DID；其代表权限由 `owner_did + actor_did + 鉴权接口` 共同约束

---

## 3. 目标链路分层

### 3.1 入口层

- OpenClaw Skill
- 通用 Webhook
- 社交媒体适配器（飞书 / Slack / 企业微信 / Discord 等）

### 3.2 编排层

- 常驻秘书 Agent
- 任务分类 / 意图识别
- 团队成员选择
- Enclave 创建
- Playbook 启动与推进

### 3.3 执行层

- 常驻 Worker 直接接单
- CLI Worker 被本地命令拉起后接单
- 局域网 Worker 通过 Relay / P2P 收件

### 3.4 交付层

- 产物写入 Vault
- 状态汇总
- 最终结果包生成
- 回传给主人 / 原始入口

---

## 4. 三阶段目标

### 4.1 Phase A — 能演示

**目标**

- 社交入口先用通用 Webhook 或 OpenClaw
- 秘书 Agent 常驻
- Worker 可以是预先启动的 CLI 或常驻 Agent
- 协作范围先限制在同一 Daemon 或同一 `local Relay` 域内
- 用 Enclave + Playbook 跑通“设计 -> 评审 -> 开发 -> 评审 -> 完成”

**验收标准**

- [ ] 外部请求可进入秘书 Agent，且入口可解析或映射到明确的 `owner_did`
- [ ] 秘书只能代表已绑定的 `owner_did` 发起建单；未绑定 owner 的请求必须拒绝或转人工确认
- [ ] 建 Enclave、写入需求、启动 Playbook Run 的写操作必须走已鉴权接口，并显式携带 `actor_did`
- [ ] 至少 3 个角色可协作完成一次链路，并能在 Vault 中读取阶段交付物
- [ ] 最终回传必须附带 `run_id`、结构化 `summary`、最终状态
- [ ] 失败、阻塞、拒绝路径在状态上可观测，而不是静默丢失

**Phase A 授权边界**

- Phase A 接受“受信秘书进程代表 owner 发起”的部署前提，不要求先完成 v1.5 per-agent token 强绑定
- 但 Phase A 不接受“任意入口默认替任意 owner 自动开工”
- 入口若为 `owner_pre_authorized` 模式，应预绑定 `owner_did`，秘书才可直接建单
- 入口若为 `owner_confirm_required` 模式，应先生成 intake 记录，待 owner 确认后再创建 Enclave / Run
- 如果部署侧已有 capability token，可在 Phase A 复用；如果没有，至少也要满足 `owner_did + actor_did + 鉴权接口` 三件套
- 创建 Enclave 时，`owner_did` 表示资源归属主体，`actor_did` 表示实际调用主体；秘书建单必须使用秘书 DID 作为 `actor_did`

**明确不做**

- 不要求 CLI 按需自动拉起
- 不要求失败自动重试
- 不要求企业级审计和强担保

### 4.2 Phase B — 能顺手（Operational Teamwork）

**目标**

- 任意入口进入的任务，都能稳定转成 Enclave + Playbook
- 秘书可根据在线状态 / 平台偏好 / 负载自动选人
- 本地或局域网 Worker 的状态、产物、失败原因可追踪
- 用结构化状态、产物引用和阶段快照控制 PM Agent 上下文膨胀
- 常见失败可自动回退、切换备用 Worker 或升级人工
- CLI Launcher 作为可选 Worker Adapter 接入，而不是 Phase B 的唯一主线

**前置条件**

- `D-SEC-01 Worker Registry` 从 Phase A 最小版升级为正式版
- `D-SEC-05 交付包与结果汇总` 已完成，Delivery Manifest 结构稳定
- `D-SEC-10 Context Budget & Handoff` 已完成，阶段交接不依赖完整聊天历史
- `D-SEC-08 Adapter Contract` 已完成，OpenClaw / Webhook / SDK Agent / CLI Worker 使用统一入口和回传语义
- `D-SEC-09 Message Envelope v1` 已完成，消息统一携带 `message_id / session_id / run_id / actor_did / message_type`
- 如启用 CLI 自动拉起，`D-SEC-03 本地 CLI Launcher` 和 `D-SEC-07 安全边界` 必须先完成
- Launcher 必须是独立 sidecar，不能由秘书主进程直接拼接并执行本地命令
- Worker 启动命令必须来自固定 `worker profile`，不能由任务文本、聊天内容或模型输出直接拼接生成

**验收标准**

- [ ] Worker Registry 可返回 `available / busy / offline / blocked / needs_human` 等 presence 状态
- [ ] 角色选择策略可配置，并能按 capability / 在线状态 / 负载 / 平台偏好排序
- [ ] OpenClaw、Webhook、SDK Agent 至少两类 Adapter 走统一 intake 契约
- [ ] 所有 Playbook 相关消息都能用 `run_id` 串回流程状态
- [ ] 阶段交接默认使用 Context Snapshot + Artifact Ref，不传完整聊天历史
- [ ] 每个 Playbook stage 可声明 `max_context_tokens` 和 context include/exclude 策略
- [ ] PM / 秘书汇总时优先读取 Delivery Manifest 和 checkpoint，而不是完整对话日志
- [ ] 失败后可自动 fallback
- [ ] 结果包结构稳定，阶段和最终交付都使用 Delivery Manifest
- [ ] 如启用 Launcher，只允许执行白名单命令、固定工作目录、固定环境变量模板
- [ ] 如启用 Launcher，Worker 凭据和目录访问边界可配置，任务文本不能直接影响命令模板

### 4.3 Phase C — 能放心托付（Trustworthy Enterprise Collaboration）

**目标**

- 鉴权和主体授权从“声明 + 校验”升级到强绑定
- 有审计、可观察性、超时重试、人工接管、撤销和恢复
- 对外口径和内部状态一致，可长期运行
- 交付物具备可验证来源、版本、校验值和签名

**验收标准**

- [ ] 关键链路有审计记录
- [ ] 失败恢复和人工接管流程明确
- [ ] Worker 身份、命令、权限边界可核验，支持 per-agent token
- [ ] Capability Token 强制接入 Enclave / Vault / Run / StageExecution
- [ ] `/deliver` 从 soft-enforce 过渡到 hard-enforce 签名验证和防重放
- [ ] 签名 canonicalization 升级到严格 JCS/RFC 8785
- [ ] Delivery Manifest 可签名，包含 artifact version、checksum、producer DID
- [ ] 结果包具备交付可信度，可被外部系统验证

---

## 5. 正式数据模型（第一版）

本节定义“秘书编排”在 V1.0/V1.5 应使用的最小对象模型，目标是解决 4 个问题：

1. 任务如何隔离，不让不同项目串上下文
2. Agent 之间交接时传什么，不传什么
3. 流程状态落在哪个对象上
4. 这套设计如何与现有 `session_id` / `run_id` / `CL0-CL3` 共存

### 5.1 设计原则

- 不用完整聊天记录交接任务；默认只传 `Context Snapshot` 和 `Artifact Ref`
- 不新增第四套主键；复用现有 `session_id`、`run_id`、`message_id`
- 过程记忆优先放结构化状态；长文本政策、知识库检索留给外挂 RAG
- `CL0-CL3` 继续只负责“决策/验证时间语义”，不承载业务编排状态

### 5.2 三层追踪键模型

| 层级 | 现有主键 | 语义 | 用途 |
|------|---------|------|------|
| 消息层 | `message_id` | 单条消息唯一标识 | 防重放、引用、审计 |
| 会话层 | `session_id` | 一段对话 / 一次交互入口 | 社交入口、秘书与 Worker 之间的消息串联 |
| 流程层 | `run_id` | 一次 SOP / Playbook 实例 | 任务编排、阶段推进、最终交付 |

补充约定：

- 本专题中的 **`thread_id` 先作为逻辑概念，不新增数据库列**
- 对“需要跨多条消息、跨多个阶段保持同一任务身份”的场景，`thread_id := run_id`
- `session_id` 仍保留“会话”语义，不和 `run_id` 混用
- 如果后续确实需要显式 `thread_id` 字段，应默认等于 `run_id`，不能再引入独立第四套 ID 体系

**Intake 阶段绑定规则**

- 外部入口消息进入系统时，先以 `session_id` 作为 intake 关联键
- 在 `run_id` 创建前，秘书维护临时 intake 记录：`{session_id -> owner_did, intake_status, proposed_playbook}`
- 一旦创建 `playbook_runs`，立即建立绑定：`session_id -> run_id`
- 后续 Worker 消息、阶段通知、最终回传统一带上该 `run_id`；必要时同时保留原始 `session_id`
- 对外回传至少返回：`run_id`、`session_id`、`final_status`

### 5.3 Context Snapshot

`Context Snapshot` 是阶段交接时传递的最小上下文包。它的目标不是保存全部讨论，而是告诉下一个 Agent：

- 这是什么任务
- 当前做到哪一步
- 你现在需要处理什么
- 你必须继承哪些约束
- 你应该读取哪些产物

建议结构：

```json
{
  "thread_id": "run_123",
  "session_id": "sess_abc",
  "objective": "完成 AgentNexus 秘书编排设计并形成可评审文档",
  "current_stage": "design_review",
  "assigned_role": "reviewer",
  "inputs": {
    "requirement_ref": {
      "enclave_id": "enclave_123",
      "key": "requirements/prd.md"
    },
    "design_doc_ref": {
      "enclave_id": "enclave_123",
      "key": "design/secretary-orchestration.md"
    }
  },
  "constraints": {
    "must_review_against": [
      "docs/design/design-v1.0.md",
      "docs/adr/013-enclave-collaboration-architecture.md"
    ],
    "required_consistency_level": "L0"
  },
  "handoff_summary": "已完成第一版数据模型设计，待确认 thread_id 映射与交付包边界。",
  "updated_at": 1777056000
}
```

约束：

- Snapshot 默认是**浓缩摘要**，不是聊天转储
- Snapshot 可内联到 `playbook_runs.context`，也可只保留 `snapshot_ref`
- Snapshot 允许挂业务 JSON，但不负责存长文正文
- Snapshot 更新应发生在阶段边界，而不是每条消息都改

### 5.4 Artifact

`Artifact` 是阶段输出的持久化产物，应该优先写入 Vault 或可验证外部引用，而不是只留在聊天消息里。

建议最小元数据：

```json
{
  "artifact_id": "artifact_design_doc_v1",
  "thread_id": "run_123",
  "stage_name": "design",
  "kind": "design_doc",
  "ref": {
    "enclave_id": "enclave_123",
    "key": "design/secretary-orchestration.md"
  },
  "produced_by": "did:agentnexus:architect-01",
  "summary": "补充了 thread_id、Context Snapshot、Artifact、Routing Slip 数据模型",
  "created_at": 1777056000
}
```

约束：

- `Artifact` 应可独立引用，不依赖整段对话才能理解
- `stage_executions.output_ref` 应优先指向本阶段的 `delivery manifest`，而不是假定只有一个正文文件
- 对结构化结果，允许在 `playbook_runs.context` 保存摘要，但正文仍应落 Vault / Git / 外部对象存储

### 5.4.1 Delivery Manifest

交付层不是单文件输出，而是一组有来源关系的产物。因此：

- `stage_executions.output_ref` 默认指向一个 `delivery manifest`
- `delivery manifest` 再列出多产物、版本、校验值、来源和必选项完成情况

建议结构：

```json
{
  "manifest_id": "manifest_review_stage_v1",
  "thread_id": "run_123",
  "stage_name": "review",
  "status": "completed",
  "artifacts": [
    {
      "kind": "review_report",
      "ref": {
        "enclave_id": "enclave_123",
        "key": "review/report.md"
      },
      "version": "git:abc123",
      "checksum": "sha256:...",
      "produced_by": "did:agentnexus:reviewer-01"
    },
    {
      "kind": "annotated_design_doc",
      "ref": {
        "enclave_id": "enclave_123",
        "key": "design/secretary-orchestration.md"
      },
      "version": "git:def456",
      "checksum": "sha256:...",
      "produced_by": "did:agentnexus:reviewer-01"
    }
  ],
  "required_outputs": ["review_report"],
  "created_at": 1777056000
}
```

最终交付也应使用同样模式，至少覆盖：

- `summary`
- `design_doc`
- `code_diff`
- `test_report`
- `review_report`
- `final_status`

`checksum` 字段在 Phase A 为可选；如果当前 VaultBackend 不产出校验值，可先省略。Phase B 起建议改为必填。

### 5.4.2 Artifact Ref 的可解析范围

Phase A 不引入新的 `vault://` 协议解析器；正文示例中的 Vault 引用统一使用 `{enclave_id, key}` 二元组。

Phase A 明确限制：

- 只保证同一 Daemon 或同一 `local Relay` 域内可解析
- 不经公网 seed Relay 同步 Vault 正文
- 跨机器读取仍必须满足 Enclave 成员校验或显式 capability 授权

后续如果要扩展为跨机器可解析引用，引用中至少应包含：

- `enclave_id`
- `key`
- `version`
- `backend`
- `access_capability_ref`

### 5.4.3 Context Budget & Handoff

OpenClaw 或本机 PM Agent 模式的一类常见问题是：PM 为了维持全局理解，会不断把需求、历史讨论、代码片段、执行日志、评审意见塞回上下文，导致 token 成本和错误率随任务长度增长。

AgentNexus 的 Phase B 应把“上下文可控协作”作为核心能力之一：不依赖 PM 的长聊天记忆，而依赖结构化流程状态、产物引用和角色化交接快照。

设计目标：

- 不把完整聊天历史作为默认阶段交接输入
- 不把大文档、代码 diff、测试日志直接塞进 PM prompt
- 每个阶段只拿该角色完成当前任务所需的最小上下文
- 大正文留在 Vault / Git / 外部对象存储，消息里只传引用和摘要
- 阶段结束时生成 checkpoint，供后续阶段和 PM 汇总使用

#### Context Policy

Playbook stage 可声明上下文预算和装配策略：

```json
{
  "stage_name": "review_design",
  "role": "reviewer",
  "max_context_tokens": 12000,
  "context_policy": {
    "include": [
      "context_snapshot",
      "required_artifacts",
      "latest_rejection",
      "stage_checklist"
    ],
    "exclude": [
      "full_chat_history",
      "raw_debug_logs",
      "unrelated_artifacts"
    ],
    "artifact_mode": "summary_plus_ref"
  }
}
```

字段语义：

- `max_context_tokens`：该阶段交接包的目标上限，不含 Agent 自己按需读取的 Vault 正文。实现时使用字符数近似（1 token ≈ 4 字符英文 / 2 字符中文），Phase C 可引入 tiktoken 精确计数
- `include`：上下文装配时必须包含的摘要或引用
- `exclude`：默认禁止塞入 prompt 的内容
- `artifact_mode`：
  - `ref_only`：只传 Artifact Ref
  - `summary_plus_ref`：传摘要 + 引用
  - `inline_if_small`：小于阈值时内联，否则转引用
  - `full_inline`：仅限高优先级、小体积或明确要求全文的阶段

#### Role-scoped Context

不同角色默认看到不同上下文：

| 角色 | 默认上下文 | 默认不传 |
|------|-----------|----------|
| 秘书 / PM | run 状态、stage manifest、checkpoint、阻塞原因 | 全量 Worker 对话、完整 debug log |
| 设计 Agent | 需求摘要、约束、相关 artifact ref、上一轮评审意见 | 开发执行日志、无关讨论 |
| 开发 Agent | 已批准设计、任务边界、代码位置、输出要求 | 设计阶段完整争论过程 |
| 测试 Agent | 实现摘要、测试目标、接口契约、变更 ref | PM 全局聊天历史 |
| 评审 Agent | 待评审产物、checklist、相关约束、上一轮修复说明 | 无关角色的完整消息流 |

#### Handoff Checkpoint

每个阶段完成时，应生成一个轻量 checkpoint，写入 `playbook_runs.context.checkpoints` 或作为 manifest 的 companion artifact。

建议结构：

```json
{
  "run_id": "run_123",
  "stage_name": "design",
  "status": "completed",
  "summary": "完成登录功能技术设计，采用 REST + JWT session。",
  "artifacts": [
    {"kind": "design_doc", "ref": {"enclave_id": "enc_123", "key": "design_doc"}}
  ],
  "decisions": [
    "采用 REST API",
    "不在 Phase A 引入 OAuth provider"
  ],
  "open_questions": [
    "是否需要 refresh token 轮换策略"
  ],
  "next_stage_hints": "开发阶段重点实现 /login、/logout、session middleware。",
  "created_at": 1777056000
}
```

约束：

- checkpoint 是阶段交接摘要，不是审计日志
- checkpoint 可被 PM 和后续 Worker 放入 prompt
- 审计、追责、完整消息回放应走 Phase C 的 Audit Log，不应挤进 checkpoint
- 如果 checkpoint 超过阶段 token 预算，应再次压缩或拆成摘要 + artifact ref

#### Token Budget Metrics

Phase B 起建议记录以下指标，用于证明上下文控制效果：

- `estimated_context_tokens_planned`：按 policy 估算的上下文 token 数
- `estimated_context_tokens_actual`：实际发送给 Worker 的上下文 token 数
- `artifact_bytes_referenced`：通过引用而非 prompt 传递的正文大小
- `chat_history_tokens_avoided`：未注入完整聊天历史而节省的估算 token
- `stage_retry_context_tokens`：重试阶段额外消耗的上下文 token

这些指标可先放在 `playbook_runs.context.context_budget`，Phase C 若需要计费或审计，再拆到独立表。

### 5.5 Routing Slip

本项目的 `Routing Slip` 不需要新建一套平行引擎，直接映射到现有对象：

| Routing Slip 概念 | AgentNexus 现有对象 |
|------------------|-------------------|
| SOP 模板 | `playbooks` |
| 流转单实例 | `playbook_runs` |
| 当前指针 | `playbook_runs.current_stage` |
| 节点执行记录 | `stage_executions` |
| 节点 manifest 引用 | `stage_executions.output_ref` |
| 运行时上下文 | `playbook_runs.context` |

换句话说：

- `Playbook` 是模板
- `PlaybookRun` 就是流转单
- `StageExecution` 是每个节点的执行凭据

这意味着秘书 / PM Agent 不需要发明新协议，只需要围绕现有 `run_id` 驱动：

1. 选择 Playbook 模板
2. 创建 `playbook_runs`
3. 初始化 `context snapshot`
4. 按 `current_stage` 分配 Worker
5. 收集 `delivery manifest`
6. 产出最终结果包

### 5.6 过程记忆与领域记忆

采用双层架构，但尽量落在现有模型上：

| 层级 | 落点 | 内容 |
|------|------|------|
| 过程记忆 | `playbook_runs.context`、`stage_executions`、消息索引 | `thread_id`、`current_stage`、状态、输入输出引用、更新时间 |
| 领域记忆 | Snapshot/Artifact 挂载的 JSON | 业务字段、外部返回码、表单摘要、风控中间结果 |

落地原则：

- 过程记忆要求**结构化、可精确读取**
- 领域记忆允许无模式 JSON，但必须挂在明确的 `thread_id/run_id` 下
- 企业长文本知识不塞进 Snapshot，走外挂 RAG 或知识库检索

### 5.7 与现有 CL0-CL3 的关系

这套编排模型不替代现有 `consistency_level` 设计，两者分层如下：

| 层 | 负责内容 | 当前方案 |
|----|---------|---------|
| 编排层 | `thread_id`、Snapshot、Artifact、Routing Slip | 本专题 |
| 验证层 | `evaluated_constraint_hash` + `consistency_level` | `design-v1.0.md` / `a2a-consistency-level-proposal.md` |

明确边界：

- `Context Snapshot` 不定义新的时间一致性协议
- 秘书 / PM Agent 只声明某一步要求 `CL0/CL1/CL2/CL3`
- 真正的时间语义仍由验证器和策略引擎处理
- `vector clock / causal snapshot` 若后续要加，只能作为高敏业务扩展，**不能替代当前默认的 L2=HLC**

### 5.8 V1.0 Demo 的最小落地

为了避免过度抽象，V1.0 demo 先只做以下约定：

1. `thread_id := run_id`
2. `Context Snapshot` 内联存入 `playbook_runs.context`
3. `stage_executions.output_ref` 指向 `delivery manifest`，manifest 再列出正文产物
4. 消息仍使用现有 `session_id + reply_to + message_id`
5. 默认只声明 `CL0`，不把 L2/L3 拉进主路径
6. Vault/Artifact 解析范围只承诺同一 Daemon 或同一 `local Relay`

这样可以先把“秘书建单 -> Worker 接单 -> 交付产物 -> 汇总结果”跑通，再看是否需要抽出更通用的数据层。

### 5.9 Phase A 最小失败语义

即使是 demo，也必须把失败显式化。

最小要求：

- 单个阶段允许出现 `blocked`、`rejected`、`timeout`
- `rejected` 回退循环必须有上限；默认建议同一阶段最多回退 2 次
- 超过回退上限、关键角色缺席、或超时未推进时，`playbook_runs.status` 必须进入 `failed` 或 `paused`
- 进入 `failed`/`paused` 时，秘书必须给 owner 一个明确的人工接管信号
- Phase A 不要求自动恢复，但要求“失败原因可见、当前停在哪一步可见、谁需要接管可见”

**计数落点**

- Phase A 约定在 `stage_executions` 上增加 `retry_count INTEGER DEFAULT 0`
- `create_stage_execution` 的语义调整为 **create-or-reassign**：
  - 若 `(run_id, stage_name)` 不存在，则创建记录，`retry_count = 0`
  - 若 `(run_id, stage_name)` 已存在，则不返回失败，而是把该记录重新置为 `active`，更新 `assigned_did / task_id / started_at`，清空或覆盖 `output_ref`
- 同一阶段因 rejected/timeout 再次被分配时，沿用同一 `(run_id, stage_name)` 记录并递增 `retry_count`
- `task_id`、`assigned_did`、`output_ref` 保留最近一次尝试的值；历史尝试明细可放入 `playbook_runs.context.retry_history`
- `update_stage_execution` 必须允许更新 `status / output_ref / completed_at / assigned_did / task_id / started_at / retry_count`
- `playbook.py#on_stage_rejected` 进入回退前，必须先读取被回退目标阶段的 `retry_count` 并检查是否已达上限
- 若 `retry_count >= max_retries`，不得再次启动回退阶段，必须将 `playbook_runs.status` 置为 `failed` 或 `paused`

---

## 6. 基础设施演进与 Phase 映射

本专题不替代 ADR-012 的 ACP 九层协议，而是明确：九层协议在团队协作场景下应优先补哪些基础设施能力。

核心原则：

- Phase A 只证明协作闭环，不追求企业级强安全
- Phase B 让团队协作稳定、顺手、跨入口可复用
- Phase C 让企业可以长期托付、审计、撤销和验证
- CLI Launcher 只是 Worker Adapter 的一种，不是通信基础设施的核心

### 6.1 Phase A — Demo Path

目标：跑通“外部入口 -> 秘书 -> Enclave -> Playbook -> Vault -> Manifest -> 回传”。

基础设施范围：

| ACP 层 | Phase A 约束 |
|--------|--------------|
| L0 身份 | 使用现有 DID；秘书是 Owner 绑定的子 Agent |
| L1 安全 | 复用现有签名/握手能力，不新增强制签名路径 |
| L2 访问 | 使用 daemon token + `owner_did / actor_did` 显式校验 |
| L3 Presence | 只认本地在线状态；不做正式负载模型 |
| L4 路由 | 同 Daemon 或同 local Relay 域内协作 |
| L5 Push | 可用现有 Push 通知，不要求唤醒离线 CLI |
| L6 消息 | 沿用 `session_id + reply_to + message_id`，业务上补 `run_id` |
| L7 协作 | 复用 Action Layer + Playbook 自动推进 |
| L8 适配 | OpenClaw / Webhook 可作为入口，SDK Agent 可作为 Worker |

Phase A 不做：

- per-agent token
- `/deliver` hard-enforce
- 跨公网 seed Relay 同步 Vault 正文
- 任意命令式 CLI 自动拉起
- 企业级审计和签名交付

### 6.2 Phase B — Operational Teamwork

目标：任意入口进来的任务，都能稳定转成团队协作流程，并在本地或局域网 Worker 中顺畅执行。

优先补齐：

| 能力 | 说明 | 对应设计 |
|------|------|----------|
| Worker Registry 正式版 | 统一记录 worker_type、capabilities、owner_did、profile_type、online、last_seen、load、wake_capability | D-SEC-01 |
| Presence 状态 | `available / busy / offline / blocked / needs_human`，用于选人和 fallback | D-SEC-01 / D-SEC-04 |
| Adapter Contract | OpenClaw、Webhook、SDK Agent、CLI Worker 使用统一 intake、身份映射、回传格式 | D-SEC-08 |
| Message Envelope v1 | 统一携带 `message_id / session_id / run_id / stage_name / actor_did / message_type / schema_version` | D-SEC-09 |
| Delivery Manifest 稳定版 | 阶段和最终交付都使用 manifest；Phase B 起建议 `checksum` 必填 | D-SEC-05 |
| Context Budget & Handoff | 用 Snapshot、Artifact Ref、角色化上下文和 checkpoint 控制 PM 长上下文膨胀 | D-SEC-10 |
| 失败与人工接管基础版 | claim 超时、blocked、rejected、fallback、manual handoff 可观测 | D-SEC-06 |
| CLI Launcher 可选适配器 | 只有在安全边界文档完成后，才允许自动拉起 CLI Worker | D-SEC-03 / D-SEC-07 |

Phase B 的边界：

- 可以继续使用 daemon token + actor DID 阶段性模型
- 不要求所有交付物签名
- 不要求 capability token 强制覆盖所有动作
- 但必须把所有关键流程状态落盘，并保证可查询、可回传、可接管

### 6.3 Phase C — Trustworthy Enterprise Collaboration

目标：企业可以把流程长期交给 Agent 团队运行，并能审计、追责、撤销、恢复和验证交付物。

优先补齐：

| 能力 | 说明 | 关联文档 |
|------|------|----------|
| Per-agent token | token 与 Agent DID 强绑定，替代共享 daemon token 的主体弱绑定 | design-v1.0.md 鉴权矩阵后续 |
| Capability enforcement | Enclave 创建、Vault 读写、Run 启动、Stage 执行均校验 capability scope | design-v1.0.md 1.0-08 |
| `/deliver` hard-enforce | 外部投递必须签名、防重放；无签名不再放行 | design-v1.0.md 鉴权矩阵 |
| Strict JCS | 签名 canonicalization 升级到 RFC 8785，支持跨语言互验 | docs/wip.md S5 |
| Audit Log | 记录谁在何时代表谁做了什么，输入输出和决策结果是什么 | v1.5 企业版 |
| Signed Delivery Manifest | 最终交付包包含 producer DID、version、checksum、signature | D-SEC-05 |
| Human Takeover Protocol | 暂停、转人工、恢复、重跑、撤销、归档 | D-SEC-06 |
| Adapter 权限边界 | 每个适配器声明身份映射、授权模式、回传能力和数据边界 | D-SEC-08 |

Phase C 的边界：

- 不再接受“仅自报 actor_did”作为强安全边界
- 不再接受无签名外部投递
- 不再接受无法追踪来源的最终交付
- 信任评分只能作为辅助信号，不能替代明确授权

### 6.4 实现顺序

建议按以下顺序推进：

1. Worker Registry + Presence 正式化
2. Adapter Contract
3. Message Envelope v1
4. Delivery Manifest 稳定版
5. Context Budget & Handoff
6. 失败恢复与人工接管基础版
7. CLI Launcher 可选适配器
--- Phase B / Phase C 分界线 ---
8. Per-agent token
9. Capability Token 强制接入
10. `/deliver` hard-enforce + Strict JCS
11. Audit Log + Signed Manifest + Human Takeover Protocol

这意味着 Phase B 应优先解决“团队协作能稳定运行”，Phase C 再解决“企业能长期可信托付”。

---

## 7. 建议补充的设计文档

### D-SEC-01 运行形态与 Worker Registry

**Phase A 最小版**（已实现）：见上方 Phase A 定义。

**Phase B 正式版**升级点：

Presence 状态扩展：

| 状态 | 含义 | 判定方式 |
|------|------|---------|
| `available` | 在线且空闲 | local 或 remote presence 为真，且无 active stage_execution |
| `busy` | 在线但正在执行任务 | local 或 remote presence 为真，且有 active stage_execution |
| `offline` | 不在线 | local 和 remote presence 均为假 |
| `blocked` | 在线但被标记为不可用 | 手动标记或连续失败超阈值 |
| `needs_human` | 需要人工介入 | 当前 stage 进入 paused/failed |

**Presence 判定分层**：

| 来源 | 判定方式 | 适用范围 | TTL |
|------|---------|---------|-----|
| `local_presence` | `router.is_local(did)` | 同 Daemon 本地 Agent | 实时 |
| `remote_presence` | Push registration 有效（`get_active_push_registrations(did)` 非空）或 `last_seen` 在 heartbeat_ttl 内 | 局域网 / 跨 Relay Agent | Push TTL 或 heartbeat_ttl（默认 300s） |

`get_worker_presence(did)` 返回结构：

```json
{
  "presence": "available",
  "presence_source": "local",
  "presence_ttl": null,
  "active_run_id": null,
  "active_stage": null,
  "load": 0
}
```

- `presence_source`：`"local"` | `"push"` | `"heartbeat"` | `"manual"`
- `presence_ttl`：remote presence 的剩余有效秒数；local 为 null（实时）

Worker Registry 正式版查询结果：

```json
{
  "did": "did:agentnexus:worker-01",
  "owner_did": "did:agentnexus:owner-01",
  "worker_type": "resident",
  "profile_type": "architect",
  "capabilities": ["design", "adr", "review"],
  "tags": ["python", "docs"],
  "presence": "available",
  "presence_source": "local",
  "last_seen": 1777056000,
  "active_run_id": null,
  "active_stage": null,
  "load": 0
}
```

新增存储函数：

- `get_worker_presence(did)` → `{presence, presence_source, presence_ttl, active_run_id, active_stage, load}`
- `list_workers_v2(owner_did, role=None, presence=None)` → 支持按角色和状态过滤
- `set_worker_blocked(did, blocked: bool, reason: str)` → 手动标记不可用

`load` 计算：当前该 Worker 的 active stage_execution 数量。Phase B 只做简单计数，Phase C 可引入加权负载。

### D-SEC-02 秘书 Agent 编排契约

Phase A 最小版定义如下。

接单输入最小格式：

```json
{
  "session_id": "sess_abc",
  "owner_did": "did:agentnexus:owner-01",
  "actor_did": "did:agentnexus:secretary-01",
  "objective": "补充秘书编排设计并完成评审",
  "required_roles": ["architect", "reviewer", "developer"],
  "preferred_playbook": "pb_design_review_impl",
  "source": {
    "channel": "webhook",
    "message_ref": "msg_123"
  }
}
```

创建 Enclave 的 Phase A 接口契约：

```json
{
  "name": "secretary-run-sess_abc",
  "owner_did": "did:agentnexus:owner-01",
  "actor_did": "did:agentnexus:secretary-01",
  "vault_backend": "local",
  "members": {
    "architect": {"did": "did:agentnexus:architect-01", "permissions": "rw"},
    "reviewer": {"did": "did:agentnexus:reviewer-01", "permissions": "rw"}
  }
}
```

字段语义：

- `owner_did` 是 Enclave 的资源归属主体，写入 `enclaves.owner_did`
- `actor_did` 是实际调用主体，Phase A 可为 owner 本人，也可为绑定在该 owner 下的秘书子 Agent
- 服务端必须校验 `actor_did == owner_did`，或 `actor_did` 是 `owner_did` 绑定下且 `profile.type = "secretary"` 的本地 Agent
- `POST /enclaves` 的请求模型需要从仅 `owner_did` 扩展为 `owner_did + actor_did`；现有只传 `owner_did` 的调用可在兼容期默认 `actor_did := owner_did`
- 创建成功后，Owner 必须以 `admin` 成员加入 Enclave；秘书是否加入成员列表由部署策略决定，但若秘书需要继续写 Vault / 创建 Run，则必须作为成员加入并具备 `rw` 或 `admin` 权限

必填字段：

- `session_id`
- `owner_did`
- `actor_did`
- `objective`
- `required_roles`

选填字段：

- `preferred_playbook`
- `source`
- `constraints`
- `artifacts`

秘书处理顺序：

1. 校验 `actor_did` 是否为 `owner_did` 绑定下的 `profile.type = "secretary"` 子 Agent
2. 校验入口模式：`owner_pre_authorized` 可直接继续；`owner_confirm_required` 则先停在 intake
3. 生成 intake 记录，键为 `session_id`
4. 从 Worker Registry 中按 `required_roles` 选出候选成员
5. 若缺少关键角色，直接返回 `blocked`
6. 创建 Enclave，写入初始需求产物
7. 选择 `preferred_playbook`；若未提供则按 `required_roles` 匹配默认 Playbook
8. 创建 `run_id`，建立 `session_id -> run_id` 绑定
9. 将 intake 摘要复制到 `playbook_runs.context.intake`
10. 启动 Playbook，并将状态回传给主人或原始入口

Enclave / Run 调用主体规则：

- `POST /enclaves`：`owner_did` 是归属主体，`actor_did` 是秘书 DID 或 owner DID
- `PUT /enclaves/{id}/vault/{key}`：`author_did` 使用实际写入者 DID；秘书代写需求产物时使用秘书 DID
- `POST /enclaves/{id}/runs`：`actor_did` 使用启动 run 的秘书 DID，且该 DID 必须是 Enclave 成员并具备 `rw` 或以上权限
- 后续 Worker 阶段产物写入时，`author_did` 使用实际 Worker DID，不使用秘书 DID 代签

Intake 记录最小结构：

```json
{
  "session_id": "sess_abc",
  "owner_did": "did:agentnexus:owner-01",
  "actor_did": "did:agentnexus:secretary-01",
  "status": "intake",
  "objective": "补充秘书编排设计并完成评审",
  "required_roles": ["architect", "reviewer", "developer"],
  "preferred_playbook": "pb_design_review_impl",
  "selected_workers": {
    "architect": "did:agentnexus:architect-01",
    "reviewer": "did:agentnexus:reviewer-01"
  }
}
```

状态机最小集：

- `intake`
- `awaiting_owner_confirm`
- `ready_to_start`
- `running`
- `blocked`
- `completed`
- `failed`

对外响应最小集：

- `accepted`：已进入 intake
- `awaiting_owner_confirm`：等待 owner 确认
- `blocked`：缺少角色或资源
- `started`：已创建 `run_id`
- `completed`：附带 `run_id + final_status + summary`
- `failed`：附带 `run_id`（如果已有）和失败原因

### D-SEC-03 本地 CLI Launcher

需要定义：

- 本地命令拉起模型
- 独立 sidecar 执行边界
- 固定 `worker profile -> command/workdir/env` 映射
- 任务上下文如何注入 CLI
- 启动成功 / 失败的判定
- 幂等性、并发、重复拉起保护

### D-SEC-04 角色选择与回退策略

需要定义：

- 按 capability / 平台 / 在线状态 / trust score / 最近负载 选人
- 首选 Worker 不在线时的 fallback
- 评审 rejected 时的回退策略

### D-SEC-05 交付包与结果汇总

**目标**：定义阶段交付和最终交付的标准结构，确保产物可追踪、可引用、可验证。

**阶段 Delivery Manifest**（每个 stage 完成时生成）：

```json
{
  "manifest_id": "manifest_<stage>_<run_id>",
  "run_id": "run_123",
  "stage_name": "design",
  "status": "completed",
  "artifacts": [
    {
      "kind": "design_doc",
      "ref": {"enclave_id": "enc_123", "key": "design/spec.md"},
      "produced_by": "did:agentnexus:architect-01",
      "summary": "≤200字产物摘要",
      "checksum": "sha256:...",
      "version": "git:abc123"
    }
  ],
  "required_outputs": ["design_doc"],
  "missing_outputs": [],
  "created_at": 1777056000
}
```

`checksum` 和 `version`：Phase A/B 可选，Phase C 必填。

**最终 Delivery Manifest**（Playbook 完成时由秘书汇总）：

```json
{
  "manifest_id": "manifest_final_<run_id>",
  "run_id": "run_123",
  "status": "completed",
  "summary": "一段话最终结果摘要",
  "stage_manifests": ["manifest_design_run_123", "manifest_review_run_123", "manifest_impl_run_123"],
  "final_artifacts": [
    {"kind": "summary", "ref": {"enclave_id": "enc_123", "key": "final/summary.md"}},
    {"kind": "design_doc", "ref": {"enclave_id": "enc_123", "key": "design/spec.md"}},
    {"kind": "code_diff", "ref": {"enclave_id": "enc_123", "key": "impl/diff.patch"}},
    {"kind": "test_report", "ref": {"enclave_id": "enc_123", "key": "test/report.md"}},
    {"kind": "review_report", "ref": {"enclave_id": "enc_123", "key": "review/report.md"}}
  ],
  "final_status": "completed | partial | failed",
  "created_at": 1777056000
}
```

**标准 artifact kind**：

| kind | 说明 | 必选 |
|------|------|------|
| `summary` | 最终结果一句话摘要 | ✅ |
| `design_doc` | 技术设计文档 | 按 Playbook |
| `code_diff` | 代码变更 | 按 Playbook |
| `test_report` | 测试报告 | 按 Playbook |
| `review_report` | 评审报告 | 按 Playbook |

**落点**：`stage_executions.output_ref` 存可解析的 Artifact Ref（`{enclave_id}/manifests/{run_id}/{stage}`）；manifest 本身写入 Vault `manifests/{run_id}/{stage}` 或 `manifests/{run_id}/final`。Vault key 统一不带文件后缀，内容为 JSON。每个 run 的 manifest 路径唯一，不会跨 run 覆盖。

### D-SEC-06 失败恢复与人工接管

**目标**：定义协作链路中各类失败的检测、自动恢复和人工升级路径。

**失败类型与处理策略**：

| 失败类型 | 检测方式 | Phase B 自动处理 | 人工升级条件 |
|---------|---------|-----------------|-------------|
| 未 claim 超时 | stage_execution 创建后 N 分钟无 `task_claim` | 重新选人（fallback 到次优 Worker） | 连续 2 次无人 claim |
| Worker 执行超时 | stage_execution `active` 超过 `stage.timeout` | 标记 `timeout`，尝试 fallback | 连续 2 次超时 |
| Stage rejected | `on_stage_rejected` 回调 | 回退到 `on_reject` 阶段（受 `retry_count` 限制） | `retry_count >= max_retries` |
| Worker 离线 | Presence 变为 `offline` 且 stage 仍 `active` | 等待 `reconnect_window`（默认 5 分钟），超时后 fallback | 无可用 fallback Worker |
| 关键角色缺席 | dispatch 时 `missing_roles` 非空 | 返回 `blocked` | 立即通知 Owner |

**超时配置**：

```json
{
  "claim_timeout_seconds": 300,
  "stage_timeout_seconds": 3600,
  "reconnect_window_seconds": 300,
  "max_retries": 2
}
```

默认值可在 Playbook 级别或 Stage 级别覆盖。

**人工接管信号**：

当 `playbook_runs.status` 进入 `paused` 或 `failed` 时，秘书必须：

1. 向 Owner 发送 `human_confirm` 消息，包含：
   - `run_id`、`current_stage`、失败原因
   - 可选操作：`resume`（指定新 Worker）、`skip`（跳过当前阶段）、`abort`（终止 Run）
2. 通过 Push 通知（如已注册）或消息中心展示

**Owner 接管操作**：

所有接管端点必须 Bearer Token + `actor_did`，且 `actor_did` 必须是 Enclave owner。秘书不可代操作（Phase B）；Phase C 可通过 capability token 授权秘书代操作。

| 操作 | 说明 | 端点 | 请求体 |
|------|------|------|--------|
| `abort` | 终止整个 Run | `POST /secretary/intake/{session_id}/abort` | `{"actor_did": "<owner_did>"}` |
| `resume` | 指定新 Worker 重新执行当前阶段 | `POST /secretary/intake/{session_id}/resume` | `{"actor_did": "<owner_did>", "new_worker_did": "<did>"}` |
| `skip` | 跳过当前阶段，推进到下一阶段 | `POST /secretary/intake/{session_id}/skip` | `{"actor_did": "<owner_did>"}` |

鉴权校验流程：
1. `_require_token` — 验证 Bearer Token
2. `_verify_actor_is_owner(actor_did)` — 验证是本地 Owner
3. 验证 `actor_did` 是该 intake 对应 Enclave 的 `owner_did`

Phase B 先实现 `abort`；`resume` 和 `skip` 可在 Phase B 后期补充。

### D-SEC-07 安全边界

需要定义：

- 秘书可代表谁发起任务
- Launcher 可执行哪些命令
- 命令白名单、固定工作目录、环境变量模板
- CLI Worker 可访问哪些目录 / 凭据
- 最终结果如何附带来源和签名信息

### D-SEC-08 Adapter Contract

**目标**：所有外部入口（OpenClaw / Webhook / SDK Agent / CLI Worker）使用统一的 intake 请求格式、身份映射规则和回传语义。

**适配器类型与能力矩阵**：

| 适配器 | 双向交互 | 推送 | 人工确认 | 文件附件 | 身份来源 |
|--------|---------|------|---------|---------|---------|
| OpenClaw Skill | ✅ | ✅ | ✅ | ✅ | Skill 注册时绑定 owner_did |
| Webhook | ❌ 单向 | ❌ | ❌ | ✅ URL | 适配器预配置 + HMAC 校验 |
| SDK Agent | ✅ | ✅ | ✅ | ✅ Vault | `nexus.agent_info.did` → owner_did |
| CLI Worker | ✅ | ❌ | ❌ | ✅ 本地文件 | worker profile 预绑定 |

**统一 Intake 请求格式**：

所有适配器转换后必须产出以下结构，交给秘书的 `/secretary/dispatch`：

```json
{
  "session_id": "<adapter生成或透传>",
  "owner_did": "<从身份映射获取>",
  "actor_did": "<秘书DID>",
  "objective": "<从入口消息提取>",
  "required_roles": ["<从意图识别或显式指定>"],
  "source": {
    "channel": "openclaw | webhook | sdk | cli",
    "adapter_id": "<适配器实例ID>",
    "message_ref": "<原始消息引用>"
  },
  "entry_mode": "owner_pre_authorized | owner_confirm_required"
}
```

**身份映射规则**：

- OpenClaw：Skill 注册时绑定 `owner_did`，运行时从 Skill context 获取
- Webhook：`owner_did` 必须来自适配器预配置（注册 Webhook 时绑定），不信任请求头 `X-Owner-DID`。Webhook payload 必须通过 HMAC 签名校验（`X-Nexus-Signature`，与 Push 通知使用相同的 HMAC 机制）。请求头 `X-Owner-DID` 仅作为路由 hint，不作为授权来源
- SDK Agent：`connect()` 时的 DID 通过 `owner_did` 关系链查找
- CLI Worker：worker profile 中预配置 `owner_did`

**回传格式**：

适配器回传至少包含：

```json
{
  "run_id": "run_123",
  "session_id": "sess_abc",
  "status": "completed | failed | blocked",
  "summary": "一句话结果摘要",
  "manifest_ref": {"enclave_id": "enc_123", "key": "manifests/run_123/final"}
}
```

**数据边界**：适配器只能看到 intake 请求和最终回传结果，不能直接访问 Vault 正文或中间阶段消息。需要中间产物的适配器（如 OpenClaw）必须以绑定的 Agent DID 或 secretary DID 发起 Vault 读取，不允许 adapter service identity 直接绕过 Enclave 成员校验。

### D-SEC-09 Message Envelope v1

**目标**：所有协作消息携带统一外层字段，确保任何消息都能串回流程状态。

**稳定外层字段**：

```json
{
  "message_id": "msg_<uuid>",
  "session_id": "sess_<id>",
  "run_id": "run_<id>",
  "stage_name": "design",
  "actor_did": "did:agentnexus:...",
  "message_type": "task_propose",
  "schema_version": "1",
  "timestamp": 1777056000,
  "content": { ... }
}
```

**message_type 最小集**：

| type | 方向 | 说明 |
|------|------|------|
| `task_propose` | 秘书/引擎 → Worker | 分配任务 |
| `task_claim` | Worker → 秘书 | 认领任务 |
| `state_notify` | Worker → 秘书/引擎 | 状态/进度汇报 |
| `artifact_ready` | Worker → 秘书 | 产物已写入 Vault |
| `approval_request` | Worker → 评审 | 请求评审 |
| `handoff` | 引擎 → Worker | 阶段交接（携带 Context Snapshot） |
| `human_confirm` | 秘书 → Owner | 需要人工确认 |

**run_id 绑定规则**：

- Intake 阶段（run_id 未创建前）：消息只带 `session_id`，`run_id` 为 null
- Run 创建后：所有后续消息必须同时带 `session_id` 和 `run_id`
- Worker 回复消息时，必须从收到的 `task_propose` 中继承 `run_id` 和 `stage_name`

**幂等与防重放**：

- `message_id` 全局唯一（UUID）。客户端可传入自定义 `message_id`；未传时由服务端生成 `msg_<uuid>`，并持久化到 `messages.message_id`。接收方用于去重
- `timestamp` 用于 L1 时间窗口校验（如启用）
- Phase B 不要求签名；Phase C 纳入 Ed25519 签名

**Migration 策略**：

当前 `messages` 表缺少 `message_id / run_id / stage_name / actor_did / schema_version` 字段。Phase B 实现方案：

- `message_id`：已在鉴权矩阵 v3 的 `/deliver` 防重放中引入，需持久化到 `messages` 表（`ALTER TABLE messages ADD COLUMN message_id TEXT`）
- `run_id` / `stage_name`：存入 `messages.content` 的 JSON 结构中（不新增列），通过 `message_type` 区分协作消息
- `actor_did`：对于 `/messages/send`，`from_did` 即 actor；对于 `/deliver`，从签名中推导
- `schema_version`：存入 content JSON，默认 `"1"`

不新增 `run_id` / `stage_name` / `schema_version` 列，避免大规模 schema 变更。查询时通过 `message_type` 过滤协作消息，再从 content JSON 提取。

### D-SEC-10 Context Budget & Handoff

**目标**：控制阶段交接时的上下文大小，避免 PM/Worker 的 prompt 随任务长度无限膨胀。

**Context Snapshot 必填字段**：

| 字段 | 必填 | 说明 |
|------|------|------|
| `thread_id` | ✅ | 等于 `run_id` |
| `session_id` | ✅ | 原始入口会话 |
| `objective` | ✅ | 任务目标一句话 |
| `current_stage` | ✅ | 当前阶段名 |
| `assigned_role` | ✅ | 当前角色 |
| `inputs` | ✅ | Artifact Ref 列表（`{enclave_id, key}`） |
| `handoff_summary` | ✅ | 上一阶段交接摘要（≤500 字） |
| `constraints` | 选填 | 必须遵守的约束 |
| `updated_at` | ✅ | 最后更新时间 |

**更新时机**：仅在阶段边界更新（stage completed/rejected/handoff），不在每条消息时更新。

**Playbook Stage Context Policy**：

```json
{
  "max_context_tokens": 12000,
  "context_policy": {
    "include": ["context_snapshot", "required_artifacts", "latest_rejection", "stage_checklist"],
    "exclude": ["full_chat_history", "raw_debug_logs", "unrelated_artifacts"],
    "artifact_mode": "summary_plus_ref"
  }
}
```

`artifact_mode` 策略：

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `ref_only` | 只传 `{enclave_id, key}` | 大文件、代码仓库 |
| `summary_plus_ref` | 摘要（≤200 字）+ 引用 | **默认**，适用大多数阶段 |
| `inline_if_small` | < 2000 字符内联，否则转引用 | 短文档、配置文件 |
| `full_inline` | 全文内联 | 仅限明确要求全文的高优先级阶段 |

**Handoff Checkpoint schema**：

```json
{
  "run_id": "run_123",
  "stage_name": "design",
  "status": "completed",
  "summary": "≤200字阶段摘要",
  "artifacts": [{"kind": "design_doc", "ref": {"enclave_id": "...", "key": "..."}}],
  "decisions": ["采用 REST API"],
  "open_questions": ["是否需要 refresh token"],
  "next_stage_hints": "开发重点实现 /login、/logout",
  "created_at": 1777056000
}
```

落点：写入 `playbook_runs.context.checkpoints[stage_name]`。

**Token 估算**：Phase B 使用字符近似（1 token ≈ 4 字符英文 / 2 字符中文）。`estimated_context_tokens_planned` 和 `estimated_context_tokens_actual`（命名明确为估算值，非精确 billing） 记录在 `playbook_runs.context.context_budget` 中。

**与 Vault/RAG 的边界**：正文、知识库、长日志不进入 Snapshot。Worker 需要时通过 Vault API 按需读取。

---

## 8. 关键开放问题

- CLI Worker 是“先拉起再收消息”，还是“收消息后再拉起”？
- 本地命令拉起是由 Daemon 执行，还是由单独的 Launcher sidecar 执行？
- 结果回传是自由文本、结构化 summary，还是签名交付包？
- 测试 / 评审角色是否允许多人并行和投票裁决？

---

## 9. 与现有能力的边界

### 已有

- Action Layer / Discussion
- Push 注册与通知
- Enclave / Vault / Playbook 自动推进
- Owner DID / 消息中心 / 意图路由

### 未正式设计完成

- CLI Launcher
- Adapter Contract
- Message Envelope v1
- 失败恢复 / 人工接管
- 社交媒体入口适配器规范

---

## 10. 下一步建议

按顺序补文档：

1. D-SEC-01 Worker Registry 正式版
2. D-SEC-08 Adapter Contract
3. D-SEC-09 Message Envelope v1
4. D-SEC-10 Context Budget & Handoff
5. D-SEC-05 交付包与结果汇总
6. D-SEC-06 失败恢复与人工接管
7. D-SEC-07 安全边界
8. D-SEC-03 本地 CLI Launcher

其中 `D-SEC-03` 只有在需要自动拉起 CLI Worker 时才是 Phase B 前置；`D-SEC-07` 必须先于任何自动命令执行能力完成。

完成以上文档后，再将 Phase B 拆成可交付的实现批次：Registry/Presence、Adapter、Envelope、Context Budget、Manifest、Fallback、可选 Launcher。

---

## 11. 设计评审记录（2026-04-25）

> 评审者：评审 Agent

### 评审结论：初版有条件通过；以下问题已在最终版正文中闭环

整体质量高：问题定义清晰、分层合理、数据模型与现有系统映射准确、`thread_id := run_id` 避免了第四套 ID。Phase A 验收标准具体可测。

### 阻塞性问题（Phase A 前置）

| # | 问题 | 说明 | 状态 |
|---|------|------|------|
| P1 | D-SEC-02 秘书编排契约未定义 | 已在 `D-SEC-02` 补齐接单格式、状态机、选人流程、对外响应最小集 | ✅ 已闭环 |
| P2 | D-SEC-01 Worker Registry 未定义 | 已在 `D-SEC-01` 补齐 `worker_type`、在线判定、Phase A 选人优先级 | ✅ 已闭环 |

### 建议性问题

| # | 问题 | 严重性 | 建议 | 状态 |
|---|------|--------|------|------|
| S1 | §5.3 Context Snapshot 用 `vault://` 协议，但 Vault API 实际路径是 `/enclaves/{id}/vault/{key}`，无解析规则 | 🟡 | Phase A 先用 `enclave_id + key` 二元组，不引入新协议 | ✅ 已收敛到正文 |
| S2 | §5.4.1 Delivery Manifest 的 `checksum` 字段——当前 Vault 写入不计算 checksum | 🟢 | Phase A 可选，Phase B 必须 | ✅ 已在正文明确为 Phase A 可选 |
| S3 | §8 开放问题"秘书是 DID 还是子 Agent"未决 | 🟡 | 建议明确为子 Agent（`profile.type = "secretary"`），绑定到 Owner DID，与鉴权矩阵 v3 一致 | ✅ 已收敛到 §2.4 |
| S4 | §5.9 回退上限"同一阶段最多回退 2 次"——当前 `playbook.py` 的 `on_stage_rejected` 无计数器 | 🟡 | `stage_executions` 加 `retry_count`，Phase A 需要 | ✅ 已收敛到 §5.9 |

### 建议开发顺序

```
1. 按 D-SEC-01 实现最小 Worker Registry（agents 表加 worker_type + 在线查询函数）
2. 按 D-SEC-02 实现秘书接单与 intake 流程
3. 开发 Phase A：秘书常驻 → Intake → Enclave → Playbook → 交付 → 回传
4. 测试：端到端 3 角色协作
```

---

## 12. 最终复核（2026-04-25）

> 复核者：评审 Agent

### 复核结论：可开始开工

本轮文档已满足 Phase A 开发前置条件：

- D-SEC-01 最小 Worker Registry 已定义
- D-SEC-02 最小秘书编排契约已定义
- 秘书身份已收敛为 Owner 绑定的子 Agent
- Enclave 创建契约已明确为 `owner_did` 资源归属 + `actor_did` 实际调用主体
- Vault 引用已收敛为 `{enclave_id, key}` 二元组
- 回退计数的状态落点和 `stage_executions` create-or-reassign 语义已明确

剩余事项属于后续实现与扩展，不再阻塞 Phase A 开发。

---

## 13. 代码评审记录（2026-04-26）

> 评审者：评审 Agent | 测试结果：399 passed, 8 skipped ✅

### 评审结论：通过

实现与设计文档高度一致。D-SEC-01（Worker Registry）、D-SEC-02（秘书编排契约）、§5.9（retry_count + create-or-reassign）全部落地。

### 实现覆盖

| 设计项 | 实现文件 | 状态 |
|--------|---------|------|
| D-SEC-01 Worker Registry | `storage.py`（list_workers, set_worker_type, worker_type 字段） | ✅ |
| D-SEC-01 在线判定 | `storage.py#list_workers`（router.is_local） | ✅ |
| D-SEC-01 秘书排除 | `storage.py#list_workers`（profile.type != secretary） | ✅ |
| D-SEC-02 秘书注册 | `storage.py#register_secretary` | ✅ |
| D-SEC-02 秘书身份校验 | `_auth.py#_verify_actor_is_secretary` + `storage.py#is_secretary` | ✅ |
| D-SEC-02 Intake CRUD | `storage.py`（create/get/update/list_intakes） + `secretary_intakes` 表 | ✅ |
| D-SEC-02 Dispatch 链路 | `secretary.py#api_dispatch`（校验→选人→Enclave→Playbook→Run） | ✅ |
| D-SEC-02 入口模式 | `secretary.py#api_dispatch`（owner_pre_authorized / owner_confirm_required） | ✅ |
| D-SEC-02 Owner 确认 | `secretary.py#api_confirm_intake` | ✅ |
| §5.9 retry_count | `storage.py#create_stage_execution`（create-or-reassign + retry_count 递增） | ✅ |
| §5.9 回退上限 | `playbook.py#on_stage_rejected`（retry_count >= max_retries → failed） | ✅ |

### 建议性问题

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| S1 | `api_dispatch` 中 `stages` 变量在 `if not playbook` 分支内定义，走 `preferred_playbook` 分支时 `stages` 未定义，末尾 `stages[0]` 会抛 NameError | 🟡 | ✅ 已修复 — 在 `preferred_playbook` 分支后统一从 `playbook.get("stages", [])` 提取 |
| S2 | `playbook.py#_send_task_propose` 的 `from_did` 硬编码为 `"playbook_engine"`，鉴权矩阵 v3 的 `_verify_actor` 会拒绝非本地 DID，导致 403 | 🟡 | ✅ 已修复 — `_send_task_propose` 新增 `from_did` 参数，调用方使用 `enclave.owner_did` |
| S3 | `register_secretary` 在 storage.py 中 import `_config` 和 `DIDGenerator`，storage 层不应依赖 node 层 | 🟢 | ⬚ 后续重构 |
| S4 | 测试只覆盖 storage 层（11 个），缺少 HTTP 端点端到端测试（/secretary/intake、/secretary/dispatch） | 🟢 | ⬚ 待补充 |

---

## 14. Phase B 设计评审记录（2026-04-26）

> 评审者：评审 Agent

### 评审结论：通过

Phase B 设计质量高，从"能演示"到"能顺手"的升级路径清晰。核心新增（Context Budget、基础设施演进映射、D-SEC-08/09/10）均为正确的设计决策。CLI Launcher 降级为可选适配器是正确的风险控制。

### 建议性问题

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| S1 | §5.4.3 `max_context_tokens` 需要 token 计数机制（tiktoken 或字符近似），当前无实现 | 🟡 | ✅ 已补充字符近似说明 |
| S2 | D-SEC-08 列出 `public_intake` 模式但 Phase B 验收标准未提及，需明确是 Phase B 还是 Phase C | 🟢 | ✅ 已明确归 Phase C |
| S3 | §6.4 实现顺序 11 步未标注 Phase B/C 分界线 | 🟢 | ✅ 已加分界线 |
| S4 | D-SEC-05/06/07 仍只有标题，Phase B 前置条件要求"已完成"但文档为空 | 🟢 | ✅ 已细化 |

---

## 15. Phase B 设计复评记录（2026-04-26）

> 评审者：评审 Agent

### 复评结论：有条件通过 → 阻塞项已在正文中闭环

Phase B 的产品方向正确：从本机 PM 长上下文编排升级为“有 Presence、Adapter Contract、Message Envelope、Context Budget、Manifest、Fallback 的可运行团队协作”。但当前文档仍有 4 个实现前必须闭环的契约问题，否则会在局域网协作、安全边界和产物解析上产生歧义。

### 阻塞性问题

| # | 问题 | 严重性 | 建议 |
|---|------|--------|------|
| P1 | D-SEC-01 Presence 只覆盖本地 Agent | 🔴 | ✅ 已拆分 local_presence / remote_presence，补充 Push/heartbeat 判定和 presence_source/presence_ttl |
| P2 | D-SEC-08 Webhook 身份映射允许伪造 | 🔴 | ✅ 已收紧：owner_did 必须来自预配置，payload 必须 HMAC 校验，请求头仅作 hint |
| P3 | D-SEC-06 接管端点无鉴权契约 | 🔴 | ✅ 已补齐：Bearer Token + actor_did + Enclave owner 校验，含请求体定义 |
| P4 | D-SEC-05 Manifest 引用不可唯一解析 | 🔴 | ✅ 已改为 run-scoped Artifact Ref：`manifests/{run_id}/{stage}` |

### 建议性问题

| # | 问题 | 严重性 | 建议 |
|---|------|--------|------|
| S1 | D-SEC-09 Message Envelope 缺 migration 策略 | 🟡 | ✅ 已补充：message_id 新增列，run_id/stage_name/schema_version 存 content JSON |
| S2 | token 估算命名应明确为预算指标 | 🟢 | ✅ 已改为 estimated_context_tokens_* |
| S3 | Adapter Vault 访问缺少主体说明 | 🟡 | ✅ 已明确必须以绑定 Agent DID 或 secretary DID 发起 |

### 通过项

| 项目 | 评审结果 |
|------|----------|
| Phase B 将 CLI Launcher 降级为可选 Worker Adapter | ✅ 正确，避免把命令执行风险放进主路径 |
| Context Budget & Handoff 纳入 Phase B | ✅ 正确，是相对本机 PM 长上下文方案的核心差异化 |
| Delivery Manifest 作为阶段和最终交付标准结构 | ✅ 方向正确，需修正引用落点 |
| Phase C 才做 per-agent token、Capability enforcement、hard-enforce `/deliver`、Strict JCS | ✅ 分层合理 |

### 退出条件

Phase B 设计进入实现前，需要至少完成：

1. 修正 D-SEC-01 Presence 的 local/remote 判定模型。
2. 修正 D-SEC-08 Webhook owner 映射和认证规则。
3. 补齐 D-SEC-06 Owner 接管端点鉴权契约。
4. 修正 D-SEC-05 Manifest 引用为可解析、run-scoped 的 Artifact Ref。

以上 4 项闭环后，可重新评审并进入 Phase B 实现拆分。

---

## 16. Phase B 设计第二次评审（2026-04-26）

> 评审者：评审 Agent

### 评审结论：通过，可进入 Phase B 实现拆分

复评中 4 个阻塞性问题和 3 个建议性问题全部在正文中闭环，无残留矛盾。

| # | 问题 | 闭环确认 |
|---|------|---------|
| P1 | Presence local/remote 拆分 | ✅ 判定分层表 + presence_source/presence_ttl 完整 |
| P2 | Webhook 身份映射 | ✅ 正文和能力矩阵表均统一为"预配置 + HMAC" |
| P3 | 接管端点鉴权 | ✅ 请求体、校验流程、Phase 分期均已定义 |
| P4 | Manifest 引用 | ✅ 落点、回传示例、评审记录三处均为 run-scoped |
| S1 | Envelope migration | ✅ message_id 新增列，其余存 content JSON |
| S2 | token 命名 | ✅ 两处均统一为 estimated_* |
| S3 | Adapter Vault 主体 | ✅ 明确以 Agent DID 或 secretary DID 发起 |

自查修正：能力矩阵表 Webhook 身份来源列、回传示例 manifest 路径、§5.4.3 token 指标命名三处残留不一致已同步修正。

无新增问题。设计可进入 Phase B 实现拆分。

---

## 17. Phase B 设计最终复评（2026-04-26）

> 评审者：评审 Agent

### 评审结论：通过，可进入 Phase B 开发

上轮 4 个阻塞项均已在正文闭环：Presence 已拆分本地/远端判定，Webhook owner 映射已收紧为预配置 + HMAC，Owner 接管端点已补齐鉴权契约，Manifest 引用已改为 run-scoped Artifact Ref。

Phase B 可以进入实现拆分，建议按 `Registry/Presence → Adapter → Envelope → Context Budget → Manifest → Fallback → 可选 Launcher` 顺序推进。

### 非阻塞实现注意项

| # | 问题 | 严重性 | 建议 |
|---|------|--------|------|
| S1 | `D-SEC-09` 要求所有协作消息有 `message_id`，但当前 `SendMessageRequest` 尚未定义由客户端传入还是服务端生成。 | 🟡 | ✅ 已在 D-SEC-09 明确：客户端可传入，未传时服务端生成 `msg_<uuid>` 并持久化 |
| S2 | `D-SEC-05` 中 `output_ref`、`manifest_ref` 示例已是 run-scoped，但个别示例路径有 `.json` 后缀差异。 | 🟢 | ✅ 已统一：Vault key 不带文件后缀，所有示例已修正 |

### 可开发范围

Phase B 首批开发可直接开始以下内容：

1. `list_workers_v2` / `get_worker_presence` / remote presence TTL。
2. Adapter Contract 基础框架与 Webhook HMAC intake。
3. Message Envelope v1 的 `message_id` 持久化与 content JSON 兼容策略。
4. Context Snapshot / Handoff Checkpoint / estimated context budget。
5. Delivery Manifest 写入 Vault 并更新 `stage_executions.output_ref`。
6. D-SEC-06 Owner 接管端点（abort）。

### 开发状态（2026-04-26）

Phase B 以下项目已完成开发并通过测试：

| D-ID | 功能 | 状态 |
|------|------|------|
| D-SEC-01 | Worker Registry（Presence + load + 过滤） | ✅ 已完成 |
| D-SEC-02 | Intake 流程 + Secretary Dispatch | ✅ 已完成 |
| D-SEC-05 | Delivery Manifest（Stage + Final，Vault 写入） | ✅ 已完成 |
| D-SEC-06 | Owner 接管（abort 端点） | ✅ 已完成 |
| D-SEC-09 | Message Envelope v1（message_id 持久化） | ✅ 已完成 |

测试覆盖：`test_v10_sec_01~09` 共 21 个测试用例全部通过（415 passed, 8 skipped）。
6. Owner `abort` 接管链路。

---

## 18. Phase B 首批代码评审记录（2026-04-26）

> 评审者：评审 Agent | 测试结果：417 passed, 8 skipped ✅

### 评审结论：通过

Phase B 首批实现覆盖 D-SEC-01 Presence 正式版、D-SEC-05 Delivery Manifest、D-SEC-06 Owner abort、D-SEC-09 Message Envelope message_id 持久化。上轮 S1/S2/S3 全部修复确认。

### 上轮问题修复确认

| # | 问题 | 状态 |
|---|------|------|
| S1 | `stages` 变量未定义 | ✅ `stages = None` + fallback |
| S2 | playbook_engine `from_did` 硬编码 | ✅ 改为 `enclave["owner_did"]` |
| S3 | `/deliver` 无签名未记录 warning | ✅ `logger.warning` 已补 |

### 建议性问题

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| S1 | `store_stage_manifest` Vault 写入失败静默 pass，应记录 warning log | 🟡 | ⬚ 待修复 |
| S2 | `_WORKER_BLOCKED` 是内存 dict，进程重启后丢失 | 🟢 | ⬚ Phase C 持久化 |
| S3 | `api_dispatch` pre_authorized 模式下两次 DB 写入可能留孤儿 intake | 🟢 | ⬚ 后续优化 |
