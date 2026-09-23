# L0 Binding 草案：AgentNexus HTTP（Code Review Collaboration Profile v1.0-draft.2）

状态：**草案，待评审**（2026-09-18）。依据 Profile §15.1：本版为语义 Profile，本 binding 未定版前**只允许独立语义验证开发，不得启动"符合本 Profile"的集成运行**，也不得声明 wire conformance。

本文件只覆盖 **AgentNexus 侧**的 L0 承载（本机 Daemon `:8765`），把 Profile 消息映射到现有 `/coordination/*` 路由并列出必须新增的改造。外部两段（Nexus 扫描与证据查询、HCZJ ReviewRun/Attempt/activation）不在本仓库范围内，见 §7 和 2026-09-20 跨项目确认记录。

证据基线：本文所有"现状"均来自对 `agent_net/node/routers/` 的只读核对（26 条 `/coordination/*` 路由 + `/owner/decisions*`），下文引用具体文件与行号。

---

## 1. 范围

| 覆盖 | 不覆盖 |
|---|---|
| AgentNexus 本机 Daemon 的消息承载、认证主体、幂等、ACK、错误映射 | Nexus / HCZJ 的端点与认证（§7 TBD） |
| Profile 消息 → 现有路由的映射与差距 | GitLab 写入细节（属 Publisher 外部适配器，尚未实现） |
| 必须由 AgentNexus 实现的改造清单（指向 Profile §15.2–15.7） | 跨域签名、canonicalization、跨库原子性 |

---

## 2. 传输与编码

- **协议**：HTTP/1.1，JSON。
- **编码**：UTF-8，**无 BOM**；`Content-Type: application/json; charset=utf-8`。UTF-8 严格解码失败必须拒绝，不得替换字符后冒充原摘要（§15.3）。
- **端点**：默认 `http://127.0.0.1:8765`（Daemon）。仅 loopback（127.0.0.1/::1）且带认证的 L0 HTTP 不要求 TLS；0.0.0.0 监听不能自动视为 L0，跨主机部署不在 v1 范围（T7 设计确认，未验证部署）。
- **版本协商**：Profile 版本由信封 `profile` 字段显式携带（`agentnexus.code-review/1.0-draft.2`）；不匹配或缺失返回 `unsupported_profile`。同一 Session 固定版本。
- **消息登记表**：信封 `type` 为封闭枚举（10 类），见 `schemas/envelope.schema.json`；未登记类型必须拒绝，不得静默降级。
- **结构拒绝项**：重复键、`NaN`/`Infinity`、类型不符、未知关键字段（`additionalProperties: false`）、`critical_extensions` 中未支持的扩展（返回 `unsupported_critical_extension`）。前两项无法由 JSON Schema 判定，必须有行为测试。
- **事件流**：`GET /coordination/sessions/{id}/events/stream`（SSE，`coordination_common.py:335-337` 的 `_sse_frame`）。**仅用于进度观察**，既不是 ACK 也不是状态权威。

---

## 3. 认证与主体绑定

### 3.1 现状（已核对）

| 层 | 机制 | 位置 |
|---|---|---|
| 传输 | 单一共享 Daemon token：`Authorization: Bearer <token>`；未配置 token 时不校验；不匹配返回 401 | `agent_net/node/_auth.py:74-78` |
| 主体 | 请求体 `actor_did` 必须是本 Daemon 管理的 DID，且通过会话访问校验 | `_verify_actor`（`_auth.py:96+`）、`_verify_actor_can_access_session`（`routers/coordination_common.py:280-299`） |
| 会话访问 | 允许 owner、controller、owner 的子 Agent、已接受的 delegate；否则 403 | 同上 |
| 控制类 | `_verify_actor_can_control_session` / `_verify_actor_can_represent_owner` 用于流程控制与 Owner 决策 | `coordination_common.py:302-332` |

**结论：当前没有角色级授权。** 任何能访问 Session 的主体都可以写 result / artifact / receipt；`POST /coordination/receipts` 甚至不校验 `decision` 枚举（`routers/coordination_records.py:196-230`）。这与 Profile §2 的权威表与 §7 的 Receipt 分层冲突 —— 即评审 P7。

### 3.2 定版前必须完成（§15.7）

1. 新增 `review:candidate_submit`（被分配 Worker，仅提交候选）与 `review:deliver`（Coordinator，仅生成权威 accepted 交付）。
2. `validated` 由注册验证服务签发，`received` 由接收存储服务签发，`published` 仅 Publisher 在观察到实际写入后签发。
3. Daemon 必须基于**已认证凭据**绑定角色与 actor，覆盖 `result`、`artifact`、`receipt` 全部写入口；"能访问 Session"不足以授权。
4. Profile Session 上，旧通用 `POST /coordination/receipts` 必须拒绝不合规写入（CP-24）。
5. `issuer_did` / `signature` 等正文字段不得赋予权限。
6. 若部署仍使用共享 token 且无法区分调用方，本 binding 只能作为**部署约定**，不得运行符合性授权测试，也不得声明强制隔离。

---

## 4. Profile 消息 → 现有路由映射

| Profile 消息 | 方向 | 现有 L0 端点 | 现状语义 | 与 Profile 的差距 |
|---|---|---|---|---|
| ReviewRequest（请求评审） | AgentNexus → HCZJ | 无本地专用入口；本地容器最近似 `POST /coordination/sessions`（`coordination_sessions.py:35`）或 `POST /coordination/coding/intake`（`coordination_coding.py:37`） | 创建 CoordinationSession(+PlaybookRun) | 出站提交端点属 HCZJ（§7 TBD）；本地需 `external_coordinator_id` / `external_run_id`（§15.6，**尚未实现**）；`coding/intake` 的字段与 Profile 无关，不得直接当 Profile 入口 |
| Assignment（分配） | HCZJ → AgentNexus/Worker | `POST /coordination/executions`（`coordination_executions.py:65`），body `CreateExecutionRequest{coordination_session_id, run_id, stage, worker_did, backend_kind, actor_did, lease_ttl_sec, metadata}`（`_models.py:263-271`） | 创建执行并写 `lease_expires_at` | 缺 `attempt_id`、`assignment_epoch`、`input_manifest_digest`、`output_schema`、`limits`、`enforcement_requirements`、`required_capabilities`；`lease_ttl_sec` **不等于** `deadline`（§15.6 需新增持久化 epoch 与目标版本） |
| AssignmentAcceptance（接单） | Worker → Coordinator | **无端点** | — | 必须新增，或经 `PATCH /coordination/executions/{id}`（`coordination_executions.py:127`）承载；`acceptance_mode` / `reason_code` / `issuer_id` 无处持久化（§5.1、§15.8） |
| Delivery（交付） | Worker → Coordinator | `POST /coordination/executions/{execution_id}/result`（`coordination_executions.py:154`），body `SubmitExecutionResultRequest{actor_did, result{status, artifact_type, artifact_body, summary, evidence_refs, human_decision_request}}`（`_models.py:282-293`） | 落 Vault、建 artifact、**自动签发 receipt**（status→decision 一一对应，`:226-233`）；按 `result_hash` 幂等，不同 hash 409 | 缺 `delivery_id`（幂等键）、`assignment_epoch`、lease/目标 CAS、`output_schema` 校验；自动签发 `approved` 违反 §15.2／CP-09；`changes_requested` 会被当重试信号（`runner_loop.py:289-311`） |
| Receipt（回执） | Coordinator / Publisher → 各方 | `POST /coordination/receipts`（`coordination_records.py:196`）；result 路径自动生成 | 调用方可任意指定 `receipt_type`/`decision`/`issuer_did`/`signature`，仅校验会话访问 | 与 `code_review.receipt.v1` 词表冲突（§15.4）；缺 `kind`/`decision=confirmed\|rejected` 语义与角色约束（§15.7） |
| ArtifactRef（产物） | Worker / Publisher | `POST /coordination/artifacts`（`coordination_records.py:131`）或 result 路径自动创建；读 `GET /coordination/sessions/{id}/artifacts`（`:185`） | 直传路径已计算 `content_hash = "sha256:"+sha256(vault_value.encode())`（`:159`），**与 §15.3 的 B 口径一致**；result 路径**未填** `content_hash`（`coordination_executions.py:215-223`） | 记录缺 `byte_length` / `media_type` / `access_scope` / `retention_until`；`schema_version` 默认 `"1"`，不承载 `code_review.report.v1`（§15.4 需新增 profile 元数据） |
| Evidence（证据读取） | 各方 | 本地：`GET /coordination/sessions/{id}/artifacts`；源码/图谱证据经 Nexus 查询（§7 TBD） | 无 Profile 级证据查询语义 | 必须按 report/side/snapshot 冻结查询，禁止"引用旧报告读实时默认图谱"（§6.1） |
| Feedback（反馈） | 人工 → Coordinator | **无端点** | — | 需新增，绑定 `report_digest` + `finding_id`（§8） |
| PublicationRequest（发布） | Coordinator → Publisher | **无端点、无 outbox** | — | 全新实现：`operation_id`、outbox 状态机、写入前后核验（§8） |
| CancelRequest / CancelAcknowledgement | 双向 | 最近似 `PATCH /coordination/executions/{id}`（状态/租约更新）+ DecisionGate（`POST /coordination/decisions`、`POST /owner/decisions/{id}/respond`） | 无取消请求/确认语义 | 需新增 `cancel_requested` / `cancel_acknowledged` 事件与 epoch 失效；`stopped/too_late/unknown` 无落点（§5.2） |
| Error（错误） | 双向 | `HTTPException(status, detail)` → `{"detail": "<字符串>"}` | 非结构化 | 必须改为 `code_review.error.v1`（`code/retryable/action_required/scope/correlation_id/safe_message/retry_after_seconds`），见 §6 |

---

## 5. 关联、幂等、ACK、重复投递与超时

| 主题 | L0 规则（草案） | 现状 |
|---|---|---|
| 请求关联 | 信封 `message_id` / `correlation_id` 需在传输层可见；建议请求头 `X-Message-Id`、`X-Correlation-Id` | 现有路由无此头部 |
| 幂等键 | 交付必须携带 `delivery_id`；建议请求头 `Idempotency-Key: <delivery_id>` | 仅有 `result_hash`（重序列化摘要，§15.3 明令不得用于 Profile 冲突判断） |
| 重复投递 | 同 `delivery_id` + 相同 digest → 返回原 Receipt（**不得** 409）；不同 digest → `delivery_conflict` (409) | 与"不同 hash 409"部分吻合，但同 hash 返回的是既有 artifact/receipt 引用，不是 Profile Receipt |
| ACK 分层 | 2xx 只表示该阶段事实：`received`（字节已保存）→ `validated`（契约与证据引用通过）→ `accepted`（Coordinator 接受）。**不得**因一次 result 提交直接产生 `accepted` | 一次提交即产生 `approved` receipt（`coordination_executions.py:226-281`） |
| 状态提交 CAS | 交付入口须在**单个本地事务**内校验认证角色、关联 ID、目标版本、`assignment_epoch`、未过期租约与允许状态 | 现仅校验执行存在 + 会话访问 + `result_hash`（`:154-193`） |
| 超时 | Worker 层 `timeout_sec` / `lease_ttl_sec`；网络层超时按 unknown 处理；**不得**因超时清零预算或再次调用模型 | 有 lease 与 timeout；无预算累计（Loop "budget" 只是次数/墙钟，`loop_engine.py:121-149`） |
| 事件流 | SSE 只作观察，不作为 ACK/权威 | 已存在 |

---

## 6. 错误映射（HTTP ↔ `code_review.error.v1`）

现状所有失败均返回 `{"detail": "<人类可读字符串>"}`（FastAPI `HTTPException`），**无法承载** `code`/`retryable`/`action_required`/`scope`/`correlation_id`/`retry_after_seconds`。定版前必须二选一：新增结构化错误响应，或在适配层做确定性映射。

| 现状 HTTP | 建议 Profile `code` | `retryable` | 说明 |
|---|---|---|---|
| 400 / 422 | `invalid_output` | false | 结构或类型不合法；仅可修复结构错误允许同 Attempt 一次纠正 |
| 401 | `authority_denied` | false | 未认证；不得回显私有资源详情 |
| 403 | `authority_denied` / `data_policy_denied` | false | 按语义区分权限拒绝与数据策略拒绝 |
| 404（证据/报告引用缺失） | `evidence_unavailable` | 视情况 | 永久缺失转人工处理 |
| 404（交付目标缺失） | `input_mismatch` | false | 保留审计 |
| 409（同 ID 不同摘要） | `delivery_conflict` | false | 不以新请求覆盖原记录 |
| 409（幂等投影不同） | `idempotency_conflict` | false | 见 §15.8 的投影与比较算法 |
| 429 | `rate_limited` | true | 有界退避 |
| 500 | `temporarily_unavailable` | true | 不得仅凭 500 无限重试 |
| 503 | `temporarily_unavailable` | true | 按故障阶段区分 |

**不得**用 HTTP 状态本身驱动无限重试；错误必须回到 Profile §9 的行为列。

---

## 7. 外部确认项（2026-09-20 已核对，仍有开放项）

已进入 Nexus/HCZJ 两个仓库完成源码与测试核对，详见 [跨项目确认记录](external-confirmations-2026-09-20.md)。**T1–T6 尚未关闭**；**T7 的设计范围已确认**（见下表状态列）。以下保留原关闭要求，不代表全部通过。

| # | 归属 | 待确认内容 | 状态 |
|---|---|---|---|
| T1 | Nexus | `scan.succeeded` 的承载方式与字段（job/report/generation/execution_revision）；按 report/side/snapshot 查询证据的端点、认证主体、**允许的 `contract_revision` 取值**及生产响应样例 | 开放 |
| T2 | Nexus | ImpactReport 的 `locator` 形态、`media_type`、以及"持久化报告"的字节口径（供 `artifact_ref.digest` 计算） | 开放 |
| T3 | HCZJ | ReviewRun / Attempt / `activation_revision` / `target_revision` 的 API、认证主体、CAS 语义 | 开放 |
| T4 | HCZJ | `coordinator_id` 的标识形态；Assignment / Acceptance / Delivery 的接收端点与 ACK 语义 | 开放 |
| T5 | HCZJ | 发布适配器与 GitLab 写入接口的归属；outbox 与 `operation_id` 的持久化位置 | 开放 |
| T6 | 三方 | `compatibility.json` 的填充责任人与冻结时点；`artifact_ref.access_scope` 词表 | 开放 |
| T7 | 三方 | 本机 L0 是否允许 HTTP（无 TLS）；跨主机部署是否在后续版本纳入 | **设计范围已确认**（仅 loopback 允许带认证 HTTP；跨主机另行 binding），部署验证仍待做 |

每个 TBD 关闭时必须给出：端点、方法、认证主体、Content-Type、幂等键、ACK 语义、超时、错误映射。

**关闭状态的唯一追踪器是 [`evidence/closure-checklist.json`](evidence/closure-checklist.json)**（2026-09-20 新增）：它把上表每一行展开为逐条证据要求、责任人、采集模板与机械验收条件，并声明各项状态。声明必须与实际一致——`tools/check_evidence.py` 会重算收到的原始字节摘要、拒绝残留占位符、拒绝「声称关闭却拿不出证据」，并在 T1–T6 未全部关闭时拒绝 `compatibility.json` 放行。采集与回填方式见 [`evidence/README.md`](evidence/README.md)。

因此上表「开放」不再靠人工记忆：**只要 `evidence/received/T{n}.json` 未按模板回填并通过校验，该项就是开放**，任何"已在源码确认"的说法都不能把它变成关闭。

---

## 8. 定版门槛与明确排除

**定版条件（全部满足）**

1. Profile §15.2–15.7 的 AgentNexus 侧改造完成，或对该部署明确声明降级（`declared_only` / `unsupported`）并拒绝需要强制能力的任务。
2. §7 的 T1–T7 全部关闭并记录。
3. `compatibility.json` 由三方确认填充；默认空列表拒绝策略不得放宽为通配。
4. `schemas/` + `fixtures/` + `fixtures/digest_vectors.json` 通过 `tools/validate.py`。
5. CP-01～26 各自至少一次可复现运行记录（schema 只能判结构，状态与摘要必须行为验证）。

**明确排除**

- 本 binding 不声明 wire conformance、不声明跨域签名或 canonicalization 互通。
- 不承诺跨 GitLab / 数据库原子性或 exactly-once。
- 不覆盖 L1 局域网 / L2 公网 Relay 的 artifact transport。

## 9. 服务接口补充（2026-09-20）

[T1–T6 服务接口契约](l0-service-contract.md) 补齐新增端点、认证、DTO、ACK、CAS、错误及发布恢复规则。§4 的旧路由仅用于差距分析；本契约采用专用新入口，不把旧路由视为已兼容。契约评审已完成（RC1 结论见 [l0-service-contract.md §9](l0-service-contract.md)：有条件通过；**RC2 复核见其 §11**：Q1–Q3/S1–S7 已全部关闭、文本层面无阻塞项），但 **binding 仍不得定版**，生产样例与实施证据仍未齐。

2026-09-20 现状：规范包 `1.0-draft.2+semantic.8`；AgentNexus 侧 §15.2–15.7 与 L0 端点已实现并有测试（见 `docs/api-reference.md` 的 Code Review Profile 一节）；q3 行为用例已有可执行 harness 与[执行记录](../fixtures/binding/q3-execution-record-2026-09-20.md)；**BINDING-GATE-1 仍关闭**（T1–T6 未关闭、兼容清单未三方冻结、CP-01～26 未执行）。
