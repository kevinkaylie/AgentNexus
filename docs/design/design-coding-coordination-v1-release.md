# AgentNexus 设计专题 — Coding Coordination V1 Release Closure

> 状态：设计中
> 目标：先补齐 Coding Coordination V1 后端可运行闭环，再收口成新开发者可运行、可观察、可复现的 alpha/demo 产品路径。
> 关联文档：
> - [design-coding-coordination-v1.md](design-coding-coordination-v1.md) — CoordinationSession / Delegation / Event / Artifact / Receipt / Closure 主设计
> - [design-sdk-orchestration.md](design-sdk-orchestration.md) — Orchestration SDK 基础 facade
> - [design-dashboard-setup-v1.0.md](design-dashboard-setup-v1.0.md) — Dashboard / Setup 收口
> - [../api-reference.md](../api-reference.md) — 当前 API 端点
> - [../project-status.md](../project-status.md) — 当前版本状态唯一来源

---

## 1. 背景

Coding Coordination V1 的目标主链路是：

```text
coding intake
  -> CoordinationSession
  -> Artifact
  -> Receipt
  -> receipt-gated advance
  -> FinalResultReceipt
  -> ClosureRecord / SLA audit
  -> timeline / SSE events
```

当前代码状态不是“已实现后端闭环”，而是“设计完成 + router 草稿存在 + 后端 foundation 未接入”：

| 组件 | 当前状态 | 发布影响 |
|------|----------|----------|
| `agent_net/node/routers/coordination.py` | 文件存在，但不可导入；缺少 `_models.py` 中的 coordination request models | Daemon 无法加载 coordination routes |
| `agent_net/storage.py` | 缺少 coordination session / delegation / event / artifact / receipt / closure 相关存储函数 | router 草稿无法运行 |
| `agent_net/node/daemon.py` | 未注册 coordination router | HTTP API 对外不可用 |
| coordination tests | 被 import error 阻塞 | 不能作为已闭环证据 |

因此本设计必须分成两步：

1. **P0 后端 foundation**：让 coordination models、storage、router registration、核心 API 和测试先变成可运行闭环。
2. **Release closure**：在 P0 成立后，再实现 SDK facade、CLI demo、Dashboard 只读视图和 Quickstart。

对外发布或让新开发者理解 AgentNexus 价值，需要一个可用入口：

- SDK 能用少量代码跑通。
- CLI 能一条命令生成 demo session。
- Dashboard 能看到同一条 session 的 timeline、artifact、receipt、closure。
- Quickstart 能让用户 10 分钟复现。

本设计仍然不重新定义底层模型，但必须把后端 foundation 作为 release closure 的前置阻塞项维护。

---

## 2. Release 目标

### 2.1 一句话

> 新开发者 clone 项目后，可以通过 SDK 示例或 CLI 命令跑通完整 coding coordination 闭环，并在 Dashboard/API 中看到同一条可审计 session。

前置条件：后端 P0 foundation 必须先完成并通过测试，否则本目标不可验收。

### 2.2 用户路径

```text
install
  -> start relay/node
  -> run coordination demo
  -> inspect session detail
  -> inspect timeline/events
  -> inspect artifacts/receipts/closure
```

### 2.3 V1 Release 边界

权威“不做”清单集中在第 11 节维护。本节只说明 release closure 的核心边界：

> 本阶段先把 coordination 后端 foundation 补到可运行闭环，再把它变成可运行、可观察、可复现的入口；不新增真实 coding agent 能力，也不扩展支付、A2A 或企业级策略系统。

---

## 3. 范围

| 模块 | 本阶段目标 | 不做 |
|------|------------|------|
| SDK facade | 暴露 `nexus.coordination.*`，覆盖 V1 happy path | 不做完整 async event client 重连策略 |
| CLI demo | 一条命令跑通内置 coding demo；复用 SDK facade | 不调用真实 LLM 生成代码 |
| Dashboard | 只读展示 CoordinationSession 详情 | 不做编辑、审批、拖拽编排 |
| Quickstart | 10 分钟复现闭环 | 不覆盖企业部署 |
| Tests | 覆盖 SDK facade、CLI demo、Dashboard API 依赖 | 不做浏览器端 E2E 完整视觉测试作为阻塞项 |

---

## 3.1 P0 后端 Foundation 阻塞项

Release closure 开工前必须先补齐以下后端能力：

| 阻塞项 | 必须完成的工作 | 最小验收 |
|--------|----------------|----------|
| Request models | 在 `agent_net/node/_models.py` 定义 coordination router 引用的 request models，或把 router 统一改为 dict + 显式校验 | `python -c "import agent_net.node.routers.coordination"` 不再失败 |
| Storage functions | 在 `agent_net/storage.py` 实现 coordination session、delegation、runtime event、artifact、receipt、closure 的 CRUD / list 函数，并确保 `GET /coordination/sessions` 可用 | coordination router 单元测试可调用真实 SQLite storage；session list API 可按 owner/status/workflow_id/actor 授权查询 |
| Router registration | 在 `agent_net/node/daemon.py` 注册 coordination router | Daemon 启动后 OpenAPI / HTTP 可访问 coordination endpoints |
| Migration/init | 在 SQLite 初始化路径创建 coordination 相关 tables | 空数据库启动后可创建 coding coordination session |
| Tests | 修复 `tests/test_v10_sec_10_coordination.py` 和 `tests/test_v10_sec_11_coordination_flow.py` 的 import/runtime failures | coordination 后端测试不再因为 ImportError 全量失败 |

P0 完成后，才允许把后续章节中的 SDK / CLI / Dashboard 状态从“待实现”升级为“release closure 实施中”。

---

## 4. SDK Facade

### 4.1 入口

决策：`CoordinationClient` 挂到 `AgentNexusClient` 上，入口为 `nexus.coordination.*`。

原因：

- README 和 quickstart 已经把 `agentnexus.connect()` 返回对象作为主入口。
- `AgentNexusClient` 当前已经直接挂载 `owner`、`team`、`secretary`、`runs`、`worker`、`orchestration` facade。
- Coordination 是跨 Secretary / Enclave / Playbook 的更高层任务容器，不应藏在 `orchestration.coordination` 下让用户多一层心智负担。

实现位置：

- 新增 `agentnexus-sdk/src/agentnexus/coordination.py`
- 在 `agentnexus-sdk/src/agentnexus/client.py` 的 `AgentNexusClient.__init__` 中挂载：

```python
self.coordination = CoordinationClient(self)
```

使用方式：

```python
nexus = await agentnexus.connect("Team Admin", caps=["Admin"])
nexus.coordination
```

保留关系：`nexus.orchestration` 可以在后续版本转发或聚合 coordination 能力，但 V1 release closure 不实现 `nexus.orchestration.coordination`。

SDK / CLI packaging 边界：

- 根项目 CLI 入口仍是 `main.py` / `agentnexus` command。
- Coordination SDK facade 放在独立 SDK 包：`agentnexus-sdk/src/agentnexus/coordination.py`。
- 因此本地开发和 demo 运行必须同时安装根项目与 SDK 包：

```bash
pip install -e .
pip install -e agentnexus-sdk
```

- CLI coordination commands 启动时必须检查 SDK facade 是否可导入；如果不可导入，应失败并输出明确提示：`Please install the AgentNexus SDK: pip install -e agentnexus-sdk`。
- 不允许在 CLI 中复制一套 HTTP coordination client。CLI 可以调用现有 SDK facades，包括 `owner`、`team`、`secretary`、`enclave/vault` 与 `coordination`；其中 `coordination` 只负责 session / delegation / artifact / receipt / closure，不承担 owner/team/vault bootstrap 的全部职责。

### 4.2 最小方法

```python
session = await nexus.coordination.coding_intake(
    owner_did=owner.did,
    actor_did=secretary.did,
    objective="Implement login module",
    complexity="medium",
    risk_level="normal",
    cost_policy="balanced",
)

artifact = await nexus.coordination.submit_artifact(
    coordination_session_id=session.coordination_session_id,
    stage="design",
    artifact_type="DesignArtifact",
    producer_did=designer.did,
    content_ref="vault://enc_demo/design.md",
)

receipt = await nexus.coordination.submit_receipt(
    coordination_session_id=session.coordination_session_id,
    stage="design",
    receipt_type="DesignReceipt",
    issuer_did=reviewer.did,
    decision="approved",
    subject_artifact_id=artifact.artifact_id,
)

state = await nexus.coordination.advance(
    coordination_session_id=session.coordination_session_id,
    actor_did=secretary.did,
)

timeline = await nexus.coordination.timeline(
    coordination_session_id=session.coordination_session_id,
    actor_did=secretary.did,
)

closures = await nexus.coordination.closures(
    coordination_session_id=session.coordination_session_id,
    actor_did=secretary.did,
)
```

Fork 示例：

```python
child_session = await nexus.coordination.fork_session(
    coordination_session_id=session.coordination_session_id,
    actor_did=secretary.did,
    link_type="review_fork",
    reason="independent design review",
)
```

### 4.3 方法清单

| 方法 | API | 说明 |
|------|-----|------|
| `coding_intake()` | `POST /coordination/coding/intake` | 创建 coding.v1 root session |
| `get_session()` | `GET /coordination/sessions/{id}` | 查询 session |
| `list_sessions(owner_did, actor_did, status=None, workflow_id=None)` | `GET /coordination/sessions` | 查询 owner 下 coordination sessions；Dashboard 前置 API |
| `fork_session(coordination_session_id, actor_did, link_type, reason)` | `POST /coordination/sessions/fork` | 创建 review/session fork |
| `delegate_stage()` | `POST /coordination/sessions/{id}/stages/{stage}/delegate` | 委托阶段并签发 capability token |
| `accept_delegation()` | `POST /coordination/delegations/{id}/accept` | 接受委托 |
| `reject_delegation()` | `POST /coordination/delegations/{id}/reject` | 拒绝委托 |
| `submit_artifact()` | `POST /coordination/artifacts` | 提交 artifact |
| `submit_receipt()` | `POST /coordination/receipts` | 提交 receipt |
| `advance()` | `POST /coordination/coding/{id}/advance` | 按 receipt gate 推进 workflow |
| `events()` | `GET /coordination/sessions/{id}/events` | 查询 runtime events |
| `stream_events(session_id, actor_did, last_event_id=None, limit=None, timeout_seconds=None)` | `GET /coordination/sessions/{id}/events/stream` | 返回 async iterator；不做自动 reconnect |
| `timeline()` | `GET /coordination/sessions/{id}/timeline` | 查询聚合 timeline |
| `artifacts()` | `GET /coordination/sessions/{id}/artifacts` | 查询 artifacts |
| `receipts()` | `GET /coordination/sessions/{id}/receipts` | 查询 receipts |
| `closures()` | `GET /coordination/sessions/{id}/closures` | 查询 ClosureRecord / SLA audit |

### 4.4 返回对象

SDK 可先使用轻量 dataclass，不引入复杂 schema：

- `CoordinationSessionInfo`
- `CoordinationArtifact`
- `CoordinationReceipt`
- `CoordinationEvent`
- `CoordinationTimelineEntry`
- `CoordinationClosure`
- `CoordinationDelegation`

字段与 API response 直接对齐；复杂校验后移。

---

## 5. CLI Demo

### 5.1 命令

新增 node 子命令：

```bash
agentnexus node coordination demo
agentnexus node coordination show <coordination_session_id>
agentnexus node coordination timeline <coordination_session_id>
```

兼容未安装 CLI 的运行方式：

```bash
python main.py node coordination demo
python main.py node coordination show <coordination_session_id>
python main.py node coordination timeline <coordination_session_id>
```

### 5.2 Demo 行为

决策：CLI demo 通过 SDK facade 调用，不直接手写 HTTP API。

原因：

- CLI demo 是 SDK facade 的第一个真实消费者，可以反向验证 SDK 方法是否足够顺手。
- CLI 与 SDK 共享 bootstrap / artifact / receipt / advance 逻辑，避免两套调用路径漂移。
- 后端 API 必须先由 P0 测试覆盖，CLI 层应专注参数解析、输出格式和 demo runner。

实施含义：

- `P0 后端 Foundation` 和 `SDK facade` 是 `CLI demo` 的前置依赖。
- 本地运行 CLI demo 前必须安装根项目和 SDK 包：`pip install -e .` 与 `pip install -e agentnexus-sdk`。
- CLI coordination commands 应在启动时检查 `nexus.coordination` 是否存在；缺失时给出可执行安装提示，而不是抛出裸 `ImportError`。
- CLI 可与 Quickstart 文档并行推进，但 CLI happy path 必须在 SDK facade 完成后合入。
- 代码结构建议把 demo 主逻辑抽到可测试函数，例如 `run_coordination_demo(client, ...)`；CLI 只负责解析参数和打印结果。

`demo` 命令自动完成：

1. 确认 Node Daemon 可访问。
2. 创建或复用 demo owner。
3. 创建或复用 demo secretary / designer / developer / reviewer / tester。
4. 创建 demo enclave/vault content。
5. 调用 `coding_intake()`。
6. 依次提交每个 stage 的 artifact。
7. 依次提交 receipt。
8. 调用 `advance()` 到 completed。
9. 输出：
   - `coordination_session_id`
   - Dashboard URL
   - timeline summary
   - closure id

### 5.3 输出示例

```text
Coding Coordination demo completed

Session: cs_abc123
Status : completed
Stages : clarify -> design -> design_review -> implement -> code_review -> test -> final
Closure: clo_abc123 (sla_status=met)

Open:
  http://127.0.0.1:8765/ui/coordination/cs_abc123
```

### 5.4 Demo 数据边界

Demo 使用固定前缀，避免污染真实数据：

- owner name: `Demo Owner`
- agent names: `Demo Secretary`, `Demo Designer`, `Demo Developer`, `Demo Reviewer`, `Demo Tester`
- enclave id / vault key 使用 `demo_coordination_*`
- objective: `Implement demo login module`

重复运行可以创建新 session，但应复用 demo identities。

Vault 生命周期：

- demo artifact 必须写入本地 Vault 后再提交 `vault://` 引用，因为后端会在 `submit_artifact` 时实时读取 Vault 内容并计算 hash。
- artifact record 保存的是 `content_ref` 和 `content_hash`；历史 session 的 artifact provenance 仍可审计，但如果 Vault 条目被清理，Dashboard 后续无法重新读取 artifact 正文。
- V1 demo 不引入 TTL。文档需明确：demo 数据随本地 SQLite/Vault 生命周期保存；删除 `data/agent_net.db` 或清理 Vault 后，历史 demo session 只保证 metadata/hash 可见，不保证 artifact 原文可读取。

---

## 6. Dashboard 只读视图

### 6.0 API 依赖

Dashboard V1 只读视图依赖以下 API：

| 页面能力 | API | 当前状态 |
|----------|-----|----------|
| Session list | `GET /coordination/sessions?owner_did=&status=&workflow_id=&actor_did=` | **缺失，P0 前置阻塞** |
| Session detail | `GET /coordination/sessions/{coordination_session_id}` | router 草稿存在，但当前不可用 |
| Timeline | `GET /coordination/sessions/{coordination_session_id}/timeline` | router 草稿存在，但当前不可用 |
| Events | `GET /coordination/sessions/{coordination_session_id}/events` | router 草稿存在，但当前不可用 |
| SSE refresh | `GET /coordination/sessions/{coordination_session_id}/events/stream` | router 草稿存在，但当前不可用 |
| Artifacts | `GET /coordination/sessions/{coordination_session_id}/artifacts` | router 草稿存在，但当前不可用 |
| Receipts | `GET /coordination/sessions/{coordination_session_id}/receipts` | router 草稿存在，但当前不可用 |
| Closures | `GET /coordination/sessions/{coordination_session_id}/closures` | router 草稿存在，但当前不可用 |
| Delegations | `GET /coordination/sessions/{coordination_session_id}/delegations` | **缺失，详情页可选前置** |

因此 Dashboard 实现前必须先完成第 3.1 节 P0 后端 Foundation。P0 已覆盖 session list：

```text
GET /coordination/sessions
```

参数：

- `owner_did` 必填
- `actor_did` 必填，用于授权
- `status` 可选
- `workflow_id` 可选

授权语义：

- `actor_did` 必须能被解析为本地已知 DID。
- 当 `actor_did == owner_did` 时，可以列出该 owner 名下 coordination sessions。
- 当 `actor_did != owner_did` 时，必须验证 `actor_did` 是该 owner 绑定的 secretary/controller，或满足现有 delegate/participant 授权规则。
- list 接口不得因为 actor 参与过某一个 session，就返回同 owner 下全部 sessions；非 owner actor 只能看到它被授权访问的 sessions。
- 未授权时返回 `403`，不要返回空列表掩盖授权失败。
- 实现可复用 coordination router 已有的 actor/session 授权 helper；如果 helper 只支持单 session 检查，需要先补 owner-level/list-level helper。

响应：

```json
{
  "status": "ok",
  "sessions": [],
  "count": 0
}
```

`GET /coordination/sessions/{id}/delegations` 可作为 V1.0 release closure 的 P2；如果不补，Dashboard 的 Delegations tab 先隐藏。

### 6.1 导航

新增 Dashboard 入口：

```text
Coordination
  -> Sessions
  -> Session Detail
```

### 6.2 Session List

字段：

- `coordination_session_id`
- `objective`
- `workflow_id`
- `status`
- `owner_did`
- `controller_did`
- `created_at`
- `updated_at`

筛选：

- owner
- status
- workflow_id

V1 可以先只展示最近 N 条本地 session。

### 6.3 Session Detail

布局：

```text
Header: objective / status / workflow_id / owner / controller

Tabs:
  Timeline
  Artifacts
  Receipts
  Delegations
  Closure
  Raw JSON
```

### 6.4 Timeline

按时间升序展示：

- event type
- stage
- actor
- source: `coordination` / `stage_execution`
- payload summary

SSE event stream 用于详情页实时刷新；失败时退化为手动刷新。

### 6.5 Artifacts / Receipts / Closure

Artifacts：

- stage
- artifact_type
- producer_did
- content_ref
- content_hash

Receipts：

- stage
- receipt_type
- issuer_did
- decision
- subject_artifact_id

Closure：

- closure_id
- status
- sla_status
- sla_metrics
- receipt_id
- evidence_refs

### 6.6 Dashboard 不做

- 不在 Dashboard 内编辑 workflow。
- 不在 Dashboard 内提交 artifact/receipt。
- 不做可视化编排画布。
- 不做支付或结算展示。

---

## 7. Quickstart / Examples

### 7.1 新增文档

新增：

```text
docs/quickstart-coding-coordination.md
```

内容：

1. 安装依赖。
2. 启动 relay/node。
3. 运行 CLI demo。
4. 用 API 查询 timeline。
5. 用 SDK 查询 closure。
6. 打开 Dashboard 查看 session。
7. 常见问题。

### 7.2 新增示例

新增：

```text
agentnexus-sdk/examples/coding_coordination_demo.py
```

示例应完整展示：

- owner / secretary / worker bootstrap
- vault content 写入
- coding intake
- artifact / receipt
- advance
- timeline / closure 查询

---

## 8. 测试策略

### 8.1 后端 API

目标覆盖：

- coordination session CRUD
- runtime events
- artifact hash
- receipts
- delegation + signed capability token
- receipt-gated advance
- FinalResultReceipt
- ClosureRecord
- SSE event stream

这些后端测试必须先从 ImportError 状态修复为可运行状态，并继续保持为 release blocker。

新增 release blocker：

- 第 3.1 节 P0 后端 Foundation。
- `GET /coordination/sessions` list API 属于 P0 范围，不在 Dashboard extras 中重复实现。
- 如 Dashboard 启用 Delegations tab，则补 `GET /coordination/sessions/{id}/delegations`。

### 8.2 SDK

新增测试：

- `test_coordination_client_coding_intake`
- `test_coordination_client_submit_artifact_receipt_advance`
- `test_coordination_client_timeline_and_closure`
- `test_coordination_client_rejects_unauthorized_actor`

SDK 测试可使用 TestClient 或 mock HTTP adapter，优先复用现有 SDK 测试风格。

### 8.3 CLI

新增测试：

- `test_cli_coordination_demo_happy_path`
- `test_cli_coordination_show`
- `test_cli_coordination_timeline`

如果完整 CLI demo 太慢，允许把 demo runner 抽成可测试函数，CLI 只做参数解析。

### 8.4 Dashboard

最小测试：

- build 通过。
- API client 方法存在。
- session detail 页面能处理空列表、正常列表、错误状态。

浏览器视觉 E2E 不作为 V1 release blocker，但建议手动验收。

### 8.5 Test Count Target

为对齐 `project-status.md` 的统计惯例，release closure 合入时需要更新测试数量。目标新增覆盖：

- SDK facade：不少于 4 个测试。
- CLI demo：不少于 3 个测试。
- 后端 list API / dashboard dependency：不少于 2 个测试。
- Dashboard client / page state：不少于 2 个测试或前端 build + API client 测试。

最低目标：V1 release closure 至少新增 9 个后端/SDK/CLI 测试；若 Dashboard 测试采用前端 test runner，则单独记录。

---

## 9. 验收标准

V1 release closure 完成时，必须满足：

1. `python main.py node coordination demo` 能在本地跑通完整 coding coordination session。
2. CLI demo 冷启动端到端耗时 < 30s（不含首次依赖安装）。
3. CLI 输出 `coordination_session_id`、final status、closure id、Dashboard URL。
4. SDK 示例能跑通同一条 happy path，示例代码 < 100 行。
5. Dashboard 能显示 session list 和 session detail。
6. Dashboard session detail 首屏 API 加载时间 < 2s（本地 daemon、已有数据）。
7. Session detail 至少能看到 timeline、artifacts、receipts、closure。
8. `docs/quickstart-coding-coordination.md` 能让新开发者 10 分钟复现。
9. API reference、README、project-status 文档一致。
10. V1 release closure 至少新增 9 个后端/SDK/CLI 测试。
11. V1 相关测试通过。

---

## 10. 推荐实施顺序

0. **P0 后端 Foundation**（第 3.1 节）
   - 补齐 request models、storage functions、router registration、SQLite migration/init 和后端测试。
   - 完成后必须满足：coordination router 可导入、daemon 可启动、核心 coordination API 可访问、后端测试通过。
1. **SDK facade**
   - 挂载到 `AgentNexusClient`，形成 `nexus.coordination.*`。
   - CLI demo 依赖该 facade。
2. **Backend dashboard extras**
   - P0 已覆盖 `GET /coordination/sessions`，本步骤不重复实现 session list。
   - 只补 P0 未覆盖的 Dashboard 前置项；如果启用 Delegations tab，则补 `GET /coordination/sessions/{id}/delegations`。
3. **CLI demo**
   - 最快形成“看得见的闭环”。
   - 复用 SDK facade，不直接手写 HTTP。
4. **Dashboard 只读视图**
   - 把闭环可视化。
5. **Quickstart / Examples**
   - 固定外部使用路径。
   - CLI 命令和 Dashboard 路径稳定后，再补最终输出和截图/示例。
6. **文档/API reference 收口**
   - 保证 README、quickstart、design、project-status 一致。

---

## 11. 权威不做清单与风险处理

### 11.1 V1 Release 不做

- 不做真实代码生成。
- 不做自动 git merge / 冲突解决。
- 不做 payment gateway / payment settlement。
- 不做完整 A2A 兼容。
- 不做多 worker 并行 patch merge。
- 不做企业级 policy engine。
- 不做 Dashboard 编辑、审批、拖拽编排。
- 不做完整 SSE 自动重连策略；Dashboard 只要求轮询 fallback。

### 11.2 风险处理

| 风险 | 影响 | 处理 |
|------|------|------|
| SDK facade 与后端 API 演进不同步 | 示例失效 | SDK 方法薄封装 API，少做业务逻辑 |
| CLI demo 变成真实 coding agent | 范围失控 | demo 使用固定 artifact 内容，不调用 LLM |
| Dashboard 做太重 | 拖慢 V1 release | V1 只读，不做编辑和编排画布 |
| SSE 在某些环境不可用 | 实时刷新失败 | Dashboard 支持轮询 fallback |
| 新文档和 README 再次漂移 | 用户困惑 | project-status 仍为唯一状态源，release 前做文档一致性检查 |

---

## 12. 最终判断

Coding Coordination V1 的价值验证不在于再多加一个底层协议，而在于让用户直观看到：

> 一个复杂 coding 任务可以被 AgentNexus 串成可授权、可追踪、可验证、可审计的协调闭环。

Release closure 的核心任务，就是先把这个能力从“设计/草稿”推进到“代码里能跑”，再推进到“开发者能用、能看、能复现”。
