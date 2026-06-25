# AgentNexus 设计专题 — Coding Coordination V1

> 状态：设计/草稿实现未接入；当前后端不可运行，需先补 models、storage、router registration 和测试
> 目标：以 coding 场景作为 v1 核心闭环，验证 AgentNexus 作为跨协议、跨 runtime、跨 session 的可信协调层。
> 关联文档：
> - [design-v1.0.md](design-v1.0.md) — DID、消息中心、Capability Token、鉴权矩阵
> - [design-secretary-orchestration.md](design-secretary-orchestration.md) — Secretary / Enclave / Playbook 主链路
> - [design-sdk-orchestration.md](design-sdk-orchestration.md) — Owner / Secretary / Team / Run / Worker SDK
> - [docs/project-status.md](../project-status.md) — 当前版本状态唯一来源

---

## 1. 背景判断

> 实现状态说明（2026-05-12）：本文是目标设计，不是已实现说明。当前 `agent_net/node/routers/coordination.py` 仍是未接入 router 草稿，因缺少 `_models.py` request models 与 `storage.py` coordination functions 无法导入，daemon 也尚未注册 coordination router。真实进度以 [docs/project-status.md](../project-status.md) 为准。

AgentNexus 最初的判断仍然成立：未来个人、企业、组织内部都会拥有 Agent；完成真实任务需要 Agent 之间发现、联系、授权、交互和协作。

但生态正在变化：

- A2A / MCP / AP2 / AG-UI 等协议会持续演进，AgentNexus 不应赌单一底层协议。
- OpenAI Agents SDK、Claude Code、Google ADK、AutoGen、CrewAI、LangGraph 等会持续强化框架内编排，AgentNexus 不应重复造通用 Agent 框架。
- 企业级任务仍然需要跨模型、跨系统、跨私有云、跨权限边界的协调与治理。

因此 v1 的主线调整为：

> AgentNexus 不做 another agent protocol，也不做通用内部编排框架；AgentNexus 做 protocol-agnostic trusted coordination layer。

coding 场景是 v1 最适合的首个演示场景，因为它自然包含：

- 需求澄清
- 高级模型设计
- 设计评审
- 开发实现
- 代码评审
- 测试验证
- 多 session / 多 Agent / 多模型 / 多权限边界的动态组合
- 产物、过程和结果的审计

---

## 2. V1 定位

### 2.1 一句话

AgentNexus V1 是面向 AI coding team 的可信协调闭环：

```text
requirement intake
  -> clarify
  -> design
  -> design review
  -> implementation
  -> code review
  -> test
  -> final receipt
```

它不要求所有阶段都由 AgentNexus 自己执行。每个阶段可以委托给：

- AgentNexus native Worker
- A2A Agent
- MCP 工具链
- Webhook / OpenClaw / Dify / Coze
- OpenAI / Anthropic / Qwen / 本地模型 runtime
- 人类审批节点

AgentNexus 负责统一这些执行单元的身份、授权、session、事件、产物、验收和审计。

### 2.2 核心边界

AgentNexus 负责：

- 谁发起任务
- 谁能接任务
- 哪个 runtime / Agent / session 执行哪个阶段
- 哪些 context 可以给谁
- 任务授权范围是什么
- 过程事件如何记录
- 产物如何引用和校验
- 评审与测试结论如何沉淀
- 最终结果如何形成 receipt

AgentNexus 不负责：

- 替代 A2A/MCP 作为唯一通信协议
- 替代 OpenAI Agents SDK / ADK / CrewAI / AutoGen / LangGraph
- 自研完整代码生成模型
- 强行把所有任务都拆成多 Agent
- 在 v1 实现 payment gateway / payment settlement 或企业级争议处理

---

## 3. 核心原则

### 3.1 Agent != Role != Session != Instance

coding 任务中必须解耦四个概念：

| 概念 | 含义 | 示例 |
|------|------|------|
| Agent / Identity | 对外稳定身份和能力入口 | `did:agentnexus:...` |
| Role | 阶段职责和权限注入 | clarifier / designer / reviewer / developer / tester |
| Session | 上下文和审计边界 | root session / review fork / implementation fork |
| Instance | 一次实际执行单元 | GPT-5.5 session、Claude Code worker、Qwen local worker |

同一个 Agent 可在不同 session 中承担不同 role；同一个 role 也可由不同 instance 执行。

### 3.2 从单 Agent 启动，按需升级 topology

V1 不默认多 Agent。每个任务先按最低成本路径启动，再按复杂度、风险、数据敏感度升级。

| 条件 | 默认 topology |
|------|---------------|
| low complexity + low risk | 单 Agent，同 session |
| medium complexity | 同 Agent，fork review session |
| high complexity | 独立 designer / reviewer / developer / tester |
| sensitive data | 本地 runtime / 私有模型 / 人审 |
| cost sensitive | 高级模型设计/评审，低成本模型实现/测试 |

### 3.3 Session 是记忆和责任边界

V1 中 `CoordinationSession` 是一等模型。它不是普通聊天记录，而是一次任务从需求到交付的审计容器。

它需要支持：

- root session
- forked session
- session parent/child link
- context pack
- artifact link
- event timeline
- receipt chain

### 3.4 Secretary 是 Coordination Controller

现有 Secretary Agent 不再只被理解为拟人化助理，而是默认的 coordination controller。

它负责：

- intake
- clarify
- classify
- select topology
- dispatch stages
- monitor events
- request owner confirmation
- collect receipts
- summarize final delivery

Secretary 是默认实现，未来可替换为企业 workflow engine、A2A orchestrator、人工 PM 或第三方 runtime。

---

## 4. V1 功能闭环

### 4.1 主链路

```text
1. Intake requirement
2. Create root CoordinationSession
3. Clarify requirement with human
4. Classify complexity/risk/cost/sensitivity
5. Select workflow topology
6. Delegate design stage
7. Review design
8. Delegate implementation stage
9. Review code
10. Run test / verification
11. Produce FinalResultReceipt
12. Record ClosureRecord / SLA audit summary
```

### 4.2 阶段定义

| Stage | Role | 主要产物 | 可选 topology |
|-------|------|----------|---------------|
| `clarify` | clarifier | RequirementSpec | 同 session |
| `design` | designer | DesignArtifact | 高级模型 / 高信任 Agent |
| `design_review` | reviewer | ReviewReceipt | 同 session / fork session / 独立 Agent |
| `implement` | developer | PatchArtifact | 同 Agent / cheaper model / 多 worker |
| `code_review` | reviewer | ReviewReceipt | fork session / 独立 Agent |
| `test` | tester | TestReceipt | native worker / CI / local command adapter |
| `final` | coordinator | FinalResultReceipt | Secretary / owner agent |

### 4.3 最小验收标准

V1 demo 必须能跑通：

1. 用户提交一个 coding 需求。
2. Secretary 创建 root `CoordinationSession`。
3. Clarify 阶段可记录人类确认结果。
4. Design 阶段生成 `DesignArtifact`。
5. Design review 至少支持同 session review 和 fork session review 两种模式。
6. Implement 阶段生成 `PatchArtifact` 或 patch reference。
7. Code review 生成 `ReviewReceipt`。
8. Test 阶段生成 `TestReceipt`。
9. Final 阶段生成 `FinalResultReceipt`。
10. 所有阶段在 timeline 中可追踪，且能看到参与者 DID、role、session、artifact hash、结论。

---

## 5. 一等对象模型

### 5.1 CoordinationSession

一次任务级协调容器。

```json
{
  "coordination_session_id": "cs_123",
  "root_session_id": "sess_root",
  "intake_session_id": "sess_intake",
  "parent_session_id": null,
  "owner_did": "did:agentnexus:owner",
  "controller_did": "did:agentnexus:secretary",
  "objective": "实现登录模块重构",
  "enclave_id": "enc_123",
  "playbook_id": "coding.v1",
  "playbook_version": "1",
  "playbook_fingerprint": "sha256:...",
  "playbook_run_id": "run_123",
  "complexity": "medium",
  "risk_level": "normal",
  "cost_policy": "balanced",
  "policy_json": {
    "complexity": "medium",
    "risk_level": "normal",
    "data_sensitivity": "internal",
    "cost_policy": "balanced",
    "requires_human_approval": false
  },
  "created_at": 0,
  "updated_at": 0
}
```

建议存储：

- 新表 `coordination_sessions`
- `Playbook` 是唯一流程定义源，`PlaybookRun.context.stage_snapshots` 保存该 run 创建时的阶段快照
- `coordination_sessions` 是审计/权限/聚合容器；运行时游标（`current_stage` / `status`）以 `playbook_runs` 为准
- `coordination_sessions` V1 默认对应 1 个主 `playbook_run`，后续可扩展为 1:N
- 现有 `secretary_intakes.session_id` 作为入口兼容字段，并新增 `coordination_session_id`
- `playbook_runs.run_id` 作为 Vault / Manifest / Handoff 的内部执行 ID，并通过 `playbook_runs.coordination_session_id` 反向挂到容器；`coordination_sessions.playbook_run_id` 仅表示主 run
- `intake_session_id` 指向最初的人机澄清入口 session
- `policy_json` 保存 topology policy 输入，默认值由 Secretary 初步判断，用户或 owner 可覆盖
- `POST /enclaves/{enclave_id}/runs` 创建的是 `coordination_mode=standalone` 的底层 Enclave Run；需要 artifact/receipt/timeline/advance 审计链时应通过 Coordination 入口创建 run

### 5.2 SessionLink

记录 session fork / branch / review 隔离关系。

```json
{
  "link_id": "sl_123",
  "coordination_session_id": "cs_123",
  "from_session_id": "sess_root",
  "to_session_id": "sess_review_1",
  "link_type": "review_fork",
  "reason": "independent design review"
}
```

### 5.3 DelegationRecord

记录某个 stage 被委托给谁、以什么权限、使用什么 context。

```json
{
  "delegation_id": "del_123",
  "coordination_session_id": "cs_123",
  "stage": "design",
  "role": "designer",
  "delegator_did": "did:agentnexus:secretary",
  "delegatee_did": "did:agentnexus:designer",
  "runtime_kind": "native_worker",
  "protocol": "agentnexus-native",
  "session_id": "sess_design",
  "capability_token_id": "ct_123",
  "context_pack_id": "ctx_123",
  "status": "accepted"
}
```

Phase 1 规则：

- 每条 `DelegationRecord` 必须关联一个 `capability_token_id`
- 创建 delegation 时自动签发或绑定 Capability Token
- `stage_executions` 新增 `delegation_id`，用于从 stage 反查授权来源
- delegation 和 capability token 在 Phase 1 按 1:1 关系处理，后续可扩展为一个 token 覆盖多个 delegation

### 5.4 RuntimeEvent

统一消息、stage execution、adapter callback、review/test 状态。

```json
{
  "event_id": "evt_123",
  "coordination_session_id": "cs_123",
  "stage": "implement",
  "event_type": "artifact.submitted",
  "actor_did": "did:agentnexus:developer",
  "session_id": "sess_impl",
  "run_id": "run_123",
  "payload": {},
  "created_at": 0
}
```

V1 事件类型：

- `session.created`
- `session.forked`
- `stage.started`
- `stage.completed`
- `stage.blocked`
- `delegation.created`
- `delegation.accepted`
- `delegation.rejected`
- `context.attached`
- `artifact.submitted`
- `review.approved`
- `review.changes_requested`
- `test.passed`
- `test.failed`
- `receipt.issued`
- `closure.recorded`

实现约定：

- 新增 `runtime_events` 表作为统一事件日志
- `storage.py` 新增 `emit_event()` 辅助函数，所有关键路径必须通过该函数写事件
- Phase 1 至少覆盖：dispatch、stage start、stage complete、artifact submit、receipt submit、session fork
- timeline API 以 `runtime_events` 为主，再聚合现有 `stage_executions` 作为兼容信息
- SSE API 提供最小实时事件流：`GET /coordination/sessions/{coordination_session_id}/events/stream`

### 5.5 ContextPack

阶段交接的最小上下文包。

```json
{
  "context_pack_id": "ctx_123",
  "coordination_session_id": "cs_123",
  "stage": "implement",
  "summary": "Login module design approved with changes",
  "allowed_sources": ["requirements", "design_artifact", "review_receipt"],
  "excluded_sources": ["private_owner_notes"],
  "artifact_refs": ["artifact_design_123", "receipt_review_123"],
  "constraint_hash": "sha256:..."
}
```

Phase 1 约定：

- 不新建 `context_packs` 表，先复用现有 Playbook context snapshot
- `ContextPack` 作为逻辑模型进入 API 和事件 payload
- Phase 2 再升级为一等模型，并补齐 `constraint_hash`

### 5.6 Artifact

阶段输出。

V1 类型：

- `RequirementSpec`
- `DesignArtifact`
- `PatchArtifact`
- `ReviewFinding`
- `TestLog`

统一字段：

```json
{
  "artifact_id": "art_123",
  "coordination_session_id": "cs_123",
  "stage": "design",
  "artifact_type": "DesignArtifact",
  "producer_did": "did:agentnexus:designer",
  "content_ref": "vault://enclave/key",
  "content_hash": "sha256:...",
  "schema_version": "1"
}
```

实现约定：

- 客户端提交 artifact 时只传 `content_ref` 和类型信息
- 服务端读取 Vault 内容后计算 `content_hash`
- `content_hash` 使用 SHA-256，格式为 `sha256:<hex>`
- receipt 通过 `subject_artifact_id` 引用 artifact，并间接继承 hash 校验

### 5.7 Receipt

验收和责任记录。

V1 类型：

- `DesignReceipt`
- `ReviewReceipt`
- `TestReceipt`
- `FinalResultReceipt`

统一字段：

```json
{
  "receipt_id": "rcpt_123",
  "coordination_session_id": "cs_123",
  "stage": "code_review",
  "receipt_type": "ReviewReceipt",
  "issuer_did": "did:agentnexus:reviewer",
  "subject_artifact_id": "art_patch_123",
  "decision": "changes_requested",
  "evidence_refs": ["finding_1", "finding_2"],
  "signature": "",
  "created_at": 0
}
```

V1 可先支持 unsigned receipt；签名 receipt 后移到 v1.5 安全收紧，但数据结构必须预留。

### 5.8 ClosureRecord

coding 交付收口与 SLA 审计记录。

V1 中 `ClosureRecord` 只表达“本次 coding workflow 已完成、最终 receipt 是什么、SLA audit 指标是什么、证据链在哪里”。它不表达真实支付、资金清结算或网关调用。

统一字段：

```json
{
  "closure_id": "clo_123",
  "coordination_session_id": "cs_123",
  "actor_did": "did:agentnexus:coordinator",
  "status": "recorded",
  "sla_status": "met",
  "sla_metrics": {
    "playbook_id": "coding.v1",
    "artifact_count": 6,
    "receipt_count": 7
  },
  "receipt_id": "rcpt_final_123",
  "evidence_refs": ["coordination://sessions/cs_123/receipts/rcpt_final_123"],
  "created_at": 0
}
```

---

## 6. 与现有实现的映射

| V1 对象 / 能力 | 当前可复用实现 | 需要补齐 |
|----------------|----------------|----------|
| CoordinationSession | `secretary_intakes.session_id`、`playbook_runs.run_id` | 新表和统一 API；`secretary_intakes` / `playbook_runs` 增加 `coordination_session_id` |
| SessionLink | 暂无 | fork / branch 关系 |
| DelegationRecord | `capability_tokens`、`stage_executions` | 委托记录表；`stage_executions` 增加 `delegation_id` |
| RuntimeEvent | `messages`、`stage_executions`、`vault_history` | `runtime_events` 表 + `emit_event()` |
| ContextPack | Playbook context snapshot、context budget | Phase 1 复用 snapshot；Phase 2 一等模型和 hash |
| Artifact | `enclave_vault`、Delivery Manifest | artifact schema / 服务端 hash / refs |
| Receipt | stage/final manifest 雏形 | receipt schema 和 API |
| ClosureRecord | Delivery Manifest、stage/final manifest | coding 交付收口记录 + SLA audit API |
| TopologyPolicy | Secretary dispatch 选人逻辑 | complexity/risk/cost 策略 |
| AdapterGateway | OpenClaw/Webhook/SDK adapter | A2A adapter、统一 protocol 字段 |
| TrustSelection | trust/reputation/governance | 纳入 worker selection |

---

## 7. API 设计与目标端点

> 当前状态：以下端点是 V1 目标 API。router 草稿中已有部分路径定义，但由于 request models、storage functions 和 daemon registration 未补齐，当前不能视为可运行端点。

### 7.1 Coordination Session API

```text
POST /coordination/sessions
GET  /coordination/sessions/{coordination_session_id}
GET  /coordination/sessions/{coordination_session_id}/timeline
POST /coordination/sessions/fork
```

### 7.2 Stage / Delegation API

```text
POST /coordination/sessions/{coordination_session_id}/stages/{stage}/delegate
POST /coordination/delegations/{delegation_id}/accept
POST /coordination/delegations/{delegation_id}/reject
```

### 7.3 Event / Artifact / Receipt API

```text
POST /coordination/events
GET  /coordination/sessions/{coordination_session_id}/events
GET  /coordination/sessions/{coordination_session_id}/events/stream
POST /coordination/artifacts
POST /coordination/receipts
GET  /coordination/sessions/{coordination_session_id}/artifacts
GET  /coordination/sessions/{coordination_session_id}/receipts
POST /coordination/closures
GET  /coordination/sessions/{coordination_session_id}/closures
```

### 7.4 Coding Workflow API

V1 可提供高层便捷 API，内部仍使用上面的通用对象。

```text
POST /coordination/coding/intake
POST /coordination/coding/{coordination_session_id}/clarify
POST /coordination/coding/{coordination_session_id}/runs/{run_id}/advance
```

`advance` 由 Secretary / Coordination Controller 调用，根据指定 PlaybookRun 的当前 stage、policy 和 receipt 推进流程。

Phase 1 推进规则：

- 内置默认 `coding.v1` 是 Playbook Definition，阶段顺序为 `clarify -> design -> design_review -> implement -> code_review -> test -> final`
- `advance()` 读取 `playbook_runs.current_stage/status` 和 `PlaybookRun.context.stage_snapshots`，不从 `coordination_sessions` 读取运行时状态
- Artifact / Receipt 按 `coordination_session_id + run_id + stage` 归属，避免同一容器多 run 的同名 stage 串线
- receipt decision 为 `approved` / `passed` 时推进到下一阶段
- receipt decision 为 `changes_requested` / `failed` 时按 Playbook stage 的 `on_reject` 回退；没有 `on_reject` 时阻塞
- 动态 workflow editor、复杂 DAG、跨模板组合、自动重试和替换 worker 后移到 Phase 2+

---

## 8. SDK 设计草案

在现有 Orchestration SDK 之上新增 `coordination` facade。该 facade 是高层参数和对象封装，不重复实现通信或编排引擎。

内部关系：

- `create_session()` 只创建 `CoordinationSession`，不隐式触发 `secretary.dispatch`
- `coding_intake()` / `advance()` 可复用 `SecretaryClient.create_intake()`、`SecretaryClient.dispatch()` 和 `RunClient`
- `delegate_stage()` 复用现有 Run / Stage / Worker Runtime API，并写入 `DelegationRecord`
- SDK 层只负责把 coding coordination 对象映射到现有 Secretary / Enclave / Playbook 主链路

```python
session = await nexus.coordination.create_session(
    objective="实现登录模块重构",
    owner_did=owner.did,
    controller_did=secretary.did,
    workflow="coding.v1",
)

await nexus.coordination.submit_clarification(
    session.id,
    requirement_spec={...},
)

delegation = await nexus.coordination.delegate_stage(
    session.id,
    stage="design",
    role="designer",
    topology="same_agent",
)

await nexus.coordination.submit_artifact(
    session.id,
    stage="design",
    artifact_type="DesignArtifact",
    content_ref="vault://...",
)

await nexus.coordination.submit_receipt(
    session.id,
    stage="design_review",
    receipt_type="ReviewReceipt",
    decision="approved",
)

timeline = await nexus.coordination.get_timeline(session.id)
```

---

## 9. Topology Policy V1

### 9.1 输入信号

```json
{
  "complexity": "low | medium | high",
  "risk_level": "low | normal | high",
  "data_sensitivity": "public | internal | sensitive",
  "cost_policy": "quality_first | balanced | cost_sensitive",
  "requires_human_approval": false
}
```

### 9.2 默认规则

| 规则 | 行为 |
|------|------|
| `complexity=low` 且 `risk_level=low` | 单 Agent，同 session |
| `complexity=medium` | design review 使用 fork session |
| `complexity=high` | designer/reviewer/developer/tester 分离 |
| `data_sensitivity=sensitive` | 只选择 local/private runtime |
| `cost_policy=cost_sensitive` | design/review 用 high-tier，implement/test 可用 low-tier |
| `requires_human_approval=true` | 每个关键 receipt 后暂停等待 owner confirm |

### 9.3 V1 限制

- 策略先规则化，不引入复杂优化器。
- worker scoring 可复用现有 capability / presence，trust 和 cost 先作为附加排序因子。
- 并行多 worker implement 后移到 v1.1，V1 先支持串行和单阶段 fork。

---

## 10. 开发计划

### Phase 1 — Coordination Core

必做：

- 新增 coordination 数据表：sessions、session_links、delegations、events、artifacts、receipts、closure_records。
- `secretary_intakes` / `playbook_runs` 增加 `coordination_session_id`，`stage_executions` 增加 `delegation_id`。
- 新增 coordination router。
- 现有 secretary dispatch 创建或绑定 `coordination_session_id`。
- 新增 `emit_event()`，timeline API 聚合 coordination events + stage executions。

验收：

- coding intake 能创建 root coordination session。
- 能手动写入 event/artifact/receipt。
- timeline 可返回完整阶段轨迹。
- SSE event stream 可回放/订阅 runtime events。

### Phase 2 — Coding Workflow

必做：

- 注册内置 `coding.v1` Playbook。
- Secretary 根据 topology policy 推进 stage。
- 支持 design review fork session。
- ContextPack 生成和 constraint hash。

验收：

- 能跑通 clarify -> design -> design_review -> implement -> code_review -> test -> final。
- review fork 能被 timeline 正确串回 root session。

内置 template：

```json
{
  "playbook_id": "coding.v1",
  "stages": [
    {"name": "clarify", "role": "clarifier", "next": "design"},
    {"name": "design", "role": "designer", "next": "design_review"},
    {"name": "design_review", "role": "reviewer", "next": "implement", "on_reject": "design"},
    {"name": "implement", "role": "developer", "next": "code_review"},
    {"name": "code_review", "role": "reviewer", "next": "test", "on_reject": "implement"},
    {"name": "test", "role": "tester", "next": "final", "on_reject": "implement"},
    {"name": "final", "role": "coordinator", "next": null}
  ]
}
```

### Phase 3 — Enforcement and Adapter

必做：

- 每次 stage delegation 绑定 capability token。
- dispatch / deliver / adapter invoke 检查 delegation scope。
- 新增最小 A2A AgentCard import/export 或 task adapter。
- webhook/native adapter 统一写 RuntimeEvent。

验收：

- 未授权 worker 不能提交 stage artifact。
- A2A 或 webhook worker 的事件可进入同一 timeline。

### Phase 4 — Receipt and Release Demo

必做：

- Design / Review / Test / Final receipt schema 稳定。
- ClosureRecord / SLA audit schema 稳定。
- README / quickstart 增加 coding coordination demo。
- Dashboard 至少能展示 session timeline、stage、artifact、receipt、closure。

验收：

- 一条 coding 需求能形成最终 FinalResultReceipt。
- 最终完成时自动形成 ClosureRecord / SLA audit record。
- 用户能看到每个阶段由谁执行、用哪个 session、提交了什么、评审/测试结论是什么。
- 用户能通过 timeline 或 SSE event stream 看到过程事件。

---

## 11. V1 不做清单

- 不做完整 A2A 兼容实现，只做最小 adapter 或 AgentCard import/export。
- 不做 payment gateway / payment settlement；coding V1 只记录 ClosureRecord / SLA audit。
- 不做自动代码合并冲突解决。
- 不做多 worker 并行开发和自动 patch merge。
- 不做长期 memory 系统。
- 不做严格 RFC 8785 JCS，继续沿用当前确定性 JSON，安全收紧后移。
- 不做完整 UI 产品化，Dashboard 只需能展示主链路。

---

## 12. 风险与反证

| 风险 | 说明 | 应对 |
|------|------|------|
| A2A 成为事实标准 | Agent-to-agent task/message 可能被 A2A 吃掉 | AgentNexus 做 adapter 和 coordination overlay |
| 编排框架能力增强 | OpenAI/ADK/CrewAI 等会覆盖更多内部编排 | AgentNexus 聚焦跨 session/runtime/trust boundary |
| 多 Agent 是伪需求 | 简单任务无需多 Agent | V1 默认从单 Agent 启动，按需升级 topology |
| 数据模型过重 | 新对象太多会拖慢实现 | Phase 1 只落最小字段，先打通 timeline |
| Secretary 过度拟人化 | 容易被理解为聊天助理 | 文档和代码命名逐步升级为 Coordination Controller |

---

## 13. 结论

Coding Coordination V1 的核心不是让 AgentNexus 变成 coding agent，而是用 coding 场景证明：

> AgentNexus 可以把不同 Agent、session、runtime、模型和工具协调成一条可审计、可授权、可验收的企业级任务链。

这条链路一旦跑通，同样可以迁移到合同审查、风控复核、客服升级、采购审批和运维处置等企业流程。

---

## 14. 设计评审记录

> 评审日期：2026-05-08 | 评审者：评审 Agent

### 评审结论：有条件通过

设计方向正确，定位清晰。存在 3 个阻塞性问题需在 Phase 1 开发前明确，5 个建议性问题可在实现过程中迭代。

---

### 阻塞性问题 (P)

| # | 问题 | 章节 | 回应 | 状态 |
|---|------|------|------|------|
| P1 | `CoordinationSession` 与现有 `secretary_intakes` + `playbook_runs` 的映射关系未明确。文档说"现有字段可作为兼容"，但没说一个 coordination session 是否对应多个 playbook run（review fork 场景）。 | 5.1 | **决议**：`coordination_session` 是根容器（1:N 个 playbook run）。`playbook_runs` 表新增 `coordination_session_id` 列作为外键。`secretary_intakes` 表新增 `coordination_session_id` 列，创建 intake 时关联。`CoordinationSession` 模型新增 `intake_session_id` 字段指向入口 intake。 | 已采纳 |
| P2 | `DelegationRecord` 与现有 `Capability Token` + `stage_executions` 的关系未对齐。文档说可复用，但没说 delegation 创建时是否自动签发 capability token，以及 `stage_executions` 是否需 `delegation_id` 反向引用。 | 5.3 | **决议**：Phase 1 新建 `delegations` 表（最小字段），每行必须关联一个 `capability_token_id`。`stage_executions` 新增 `delegation_id` 列，实现 delegation→stage 的反向追踪。delegation 创建时自动签发 capability token，token_id 写入 delegation 记录。 | 已采纳 |
| P3 | `RuntimeEvent` 统一 event log 的实现方式未定义。新建表还是聚合视图？写入时机在哪里？各关键操作手动写 event 容易遗漏。 | 5.4 | **决议**：新建 `runtime_events` 表。在 `storage.py` 中新增 `emit_event()` 统一写入函数。所有关键操作（dispatch、_start_stage、on_stage_completed、submit_artifact、submit_receipt、fork_session）统一调用。Phase 1 先覆盖核心事件类型，后续扩展。 | 已采纳 |

---

### 建议性问题 (S)

| # | 问题 | 章节 | 回应 | 状态 |
|---|------|------|------|------|
| S1 | `ContextPack` 与现有 Playbook `context_snapshot` 可能重复实现。现有 `_build_context_snapshot()` 已构建上下文，V1 的 ContextPack 引入了 `allowed_sources`、`excluded_sources`、`constraint_hash`。 | 5.5 | **决议**：Phase 1 直接复用现有 `context_snapshot` 结构，不新建 ContextPack 表。Phase 2 再升级为一等模型并添加 `constraint_hash`。避免重复实现两套 context 机制。 | 已采纳 |
| S2 | `TopologyPolicy` 的信号输入来源不明确（`complexity`、`risk_level`、`cost_policy` 是自动判断还是用户输入？存储在哪里？）。 | 9.1 | **决议**：在 `CoordinationSession` 模型中新增 `policy_json` 字段（JSON），intake 时由 Secretary 自动初步判断 + 用户可手动调整。默认值：`complexity=medium, risk_level=normal, cost_policy=balanced`。 | 已采纳 |
| S3 | SDK `coordination` facade 与现有 Orchestration SDK 的关系未明确。`create_session()` 内部是否调用 `secretary.dispatch`？还是完全独立的新 API？ | 8 | **修正决议**：`coordination` facade 复用 Secretary / Enclave / Run 主链路，但 `create_session()` 只创建协调容器，不隐式 dispatch。`coding_intake()` / `advance()` 再调用 Secretary / Run API。 | 已采纳 |
| S4 | `advance` API 的推进逻辑过于模糊。receipt 是 `changes_requested` 时怎么办？谁决定下一步？ | 7.4 | **决议**：Phase 1 内置 `coding.v1` Playbook，`advance()` 按指定 `run_id` 读取 PlaybookRun 的 stage snapshot 推进，不从 CoordinationSession 读取运行时游标。receipt 为 `changes_requested` 时阻塞推进或按 stage snapshot 的 `on_reject` 回退。Phase 2 再引入动态 workflow editor 和复杂 DAG。 | 已采纳 |
| S5 | Artifact `content_hash` 的存储和校验实现未定义。由服务端计算还是客户端传入？如何与 Vault 内容校验？ | 5.6 | **决议**：服务端在写入 Vault 时自动计算 hash（SHA-256），写入 artifact 记录。客户端提交 artifact 时只需传 `content_ref`（Vault key），不需传 hash。receipt 引用 `subject_artifact_id` 时可间接验证 hash 一致性。 | 已采纳 |

---

### 文档结构建议 (D)

| # | 建议 | 章节 | 状态 |
|---|------|------|------|
| D1 | 第 6 节映射表增加"预估工作量"列，Phase 1-4 每个"必做"项标注优先级（P0/P1/P2）。 | 6, 10 | ⬚ 后续优化 |
| D2 | 开发计划验收标准缺少测试要求，每个 Phase 应写明需要补充的测试文件和场景。 | 10 | ⬚ 后续优化 |
| D3 | 建议在文档开头增加"与 Phase B 的关系"小节——Phase B 已实现的 Delivery Manifest、Context Budget、Owner abort 等功能哪些可直接复用、哪些需改造。 | 1-2 | ⬚ 后续优化 |

---

### 与现有代码库的关键差距

| 设计文档要求 | 当前代码状态 | 差距评估 |
|---|---|---|
| `CoordinationSession` 表 | 不存在 | 全新实现 |
| `SessionLink`（fork 关系） | 不存在 | 全新实现 |
| `DelegationRecord` 表 | 不存在（`capability_tokens` + `stage_executions` 可复用部分字段） | 新建关联表 + 修改现有表 |
| `RuntimeEvent` 统一事件日志 | 不存在（分散在 messages/stage_executions/vault） | 新建表 + `emit_event()` 辅助函数 |
| `Artifact` 一等模型 | 不存在（Vault + Delivery Manifest 雏形） | 新建 schema + API |
| `Receipt` 一等模型 | 不存在（manifest 雏形） | 新建 schema + API |
| `TopologyPolicy` | 不存在（dispatch 仅按 capability 匹配） | 新增策略层 |
| Session timeline API | 不存在 | 新建聚合查询 |
| coding workflow 硬编码阶段 | 不存在（现有 playbook stages 是自定义的） | 新增预设 playbook 模板 |

---

### 决议采纳清单

以下决议已更新到本文档对应章节：

- **P1** → 已更新 5.1 `CoordinationSession` 模型，新增 `intake_session_id`；第 6 节映射表已明确 `coordination_session_id`
- **P2** → 已更新 5.3 `DelegationRecord` 模型，确认与 `capability_tokens` 的 1:1 关联；`stage_executions` 增加 `delegation_id`
- **P3** → 已更新 5.4 `RuntimeEvent`，补充 `emit_event()` 函数设计；第 10 节 Phase 1 必做项已更新
- **S1** → 已更新 5.5 `ContextPack`，标注 Phase 1 复用现有 snapshot
- **S2** → 已更新 5.1 `CoordinationSession`，新增 `policy_json` 字段
- **S3** → 已更新第 8 节 SDK 设计，补充内部调用关系说明，并修正 `create_session()` 不隐式 dispatch
- **S4** → 已更新 7.4 `advance` API 说明，标注 Phase 1 使用指定 PlaybookRun 的 stage snapshot，而不是核心逻辑硬编码阶段
- **S5** → 已更新 5.6 `Artifact`，补充 hash 自动生成说明
