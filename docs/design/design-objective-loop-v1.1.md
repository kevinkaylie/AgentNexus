# AgentNexus 设计专题 — Objective Loop V1.1

> 状态：已评审（有条件通过，已补开发契约；详见第 20 节评审记录）
> 目标版本：v1.1（范围收缩为 L0 本机 Objective Loop；L1/L2 后移到 v1.2+）
> 主题：跨运行时、跨机器、跨网络的目标驱动 Agent 协作循环
> 评审日期：2026-06-18 | 评审结论：4 个阻塞性问题 + 5 个建议性问题 + 7 个细节问题；本文已采纳并补充开发契约
> 关联文档：
> - [design-secretary-orchestration.md](design-secretary-orchestration.md)
> - [design-coding-coordination-v1.md](design-coding-coordination-v1.md)
> - [design-coding-coordination-v1-release.md](design-coding-coordination-v1-release.md)
> - [design-sdk-orchestration.md](design-sdk-orchestration.md)
> - [../product.md](../product.md)
> - [../project-status.md](../project-status.md)

---

## 1. 定位

AgentNexus v1.1 的核心目标不是再做一个本地多 Agent team mode，而是把 v1.0 已具备的 DID、Relay、Secretary、CoordinationSession、Enclave、Playbook、Artifact、Receipt 和 Delivery Manifest 收敛成一个可运行的 **Objective Loop**。

一句话：

> AgentNexus 是面向异构 Agent 的网络原生目标循环：让本机、局域网和公网 Relay 上的 Agent，在 DID 身份、授权委托、产物交接、验收收据和秘书人机交互下，自动协作完成目标。

**v1.1 交付边界**：本版本只交付 **L0 本机 Objective Loop**，即在同一台机器上通过 local-runner 自动拉起 Claude Code / Codex / pytest / script 等本地执行端，跑通 objective → execution → artifact → receipt → advance → retry / DecisionGate → closure。L1 局域网和 L2 公网 Relay 是产品愿景和协议预留，开发排期后移到 v1.2+。

**L0 的完成定义** 需要分成两层，避免把 fake demo 误判为真实可用：

| 层级 | 定义 | 进入下一阶段的要求 |
|------|------|-------------------|
| L0-Demo | 单机 fake worker / runtime-mock 可跑通 7-stage 状态流 | 仅证明数据模型、API、状态机连通 |
| L0-Ready | 单机真实异构 Worker（Codex / Claude Code / pytest / script / OpenClaw 入口）能由同一 objective loop 自动调度，且身份、产物、收据、失败、人工决策都可追踪 | v1.2 LAN/Relay 开发前必须达到 |

v1.1 的实际收口目标是 **L0-Ready**，不是只完成 L0-Demo。L1/L2 仍后移，但 L0-Ready 必须把本机视为一个小型分布式 Agent Team：不同进程、不同 CLI/SDK 运行时、不同 Worker DID 通过统一 CoordinationSession 协作完成目标。

Objective Loop 的停止条件不是“某个 Agent 回复了一段文本”，而是以下之一：

- 目标达成，生成 Closure。
- 达到失败或重试上限，生成失败 Closure。
- 触发人工决策点，由 Secretary 向人类请求确认、审计或接管。
- Owner 显式 abort / pause / takeover。

---

## 2. 背景与趋势

截至 2026 年，主流 AI 编程与 Agent 产品已经在强化本地或单产品内的 team mode：

- Codex / Claude Code 等工具可以在一个产品内部启动子 Agent、分派子任务、合并结果。
- OpenClaw / 本地 PM Agent 可以在本机拉起多个本地角色完成协作。
- MCP 让这些工具更容易接入外部工具和本地上下文。

这些能力会继续增强，因此 AgentNexus 不应把核心差异放在“本机多 Agent 分工”上。单产品内的 team mode 通常仍然有这些边界：

| 边界 | 单产品 team mode 常见状态 | AgentNexus 目标 |
|------|--------------------------|-----------------|
| 运行时 | 同一产品或同一框架内部 | OpenClaw / Codex / Claude Code / SDK / Webhook / 自定义 Agent |
| 网络 | 主要本机或同一执行环境 | 本机、局域网、公网 Relay |
| 身份 | 共享产品账号或弱身份 | DID / Owner DID / Worker DID / actor_did |
| 授权 | 工具权限或 prompt 约束 | Capability Token / Gatekeeper / Trust |
| 上下文 | 会话上下文或内部状态 | Context Snapshot / Artifact Ref / Vault |
| 交付 | 文本结果或工具内部日志 | Artifact / Receipt / Delivery Manifest / Closure |
| 人类交互 | 当前产品会话里介入 | Secretary 统一联系人类 |

因此，v1.1 必须把产品主线从“能通信、能 demo”推进到“跨运行时自动完成目标”。

---

## 3. 非目标

v1.1 不做以下事情：

- 不替代 Codex、Claude Code、OpenClaw、CrewAI、AutoGen 等框架的内部编排能力。
- 不要求所有 Worker 都是 LLM Agent；脚本、HTTP 服务、测试命令、远程服务都可以是 Worker。
- 不把公网 Relay 变成中心化存储；大产物仍通过 Vault / Git / HTTP pull / manifest 引用传递。
- 不要求所有阶段完全无人参与；高风险、不确定或审计节点必须通过 Secretary 找人。
- 不在 Secretary 主进程里直接拼接并执行本地命令；本地命令执行必须由独立 runner / launcher sidecar 负责。
- 不在 v1.1 强制实现企业级 per-agent token、完整审计日志、Strict JCS 和 signed delivery package；这些进入 v1.5 安全收紧。
- 不在 v1.1 实现基于 cost 的动态 Worker 路由；per-agent 成本计量依赖 per-agent token，属于 v1.5 范围。v1.1 仅支持静态 user-configured priority hint（如 `preferred_worker` 或 `local_first`），不做动态成本排序。

---

## 4. 核心概念

### 4.1 Objective

Objective 是系统要达成的目标，不是单条消息。

最小字段：

```json
{
  "objective_id": "obj_...",
  "owner_did": "did:agentnexus:...",
  "controller_did": "did:agentnexus:...",
  "title": "实现并评审登录模块",
  "acceptance_criteria": [
    "代码通过 pytest",
    "Review 无 P0/P1 问题",
    "生成 Delivery Manifest"
  ],
  "constraints": {
    "network_access": "deny_by_default",
    "max_retries_per_stage": 2,
    "human_approval_required_for": ["scope_change", "secret_access", "destructive_command"]
  }
}
```

v1.1 可以先把 Objective 映射到现有 `CoordinationSession.objective` 和相关 metadata，不必新增独立表。后续若目标需要多 run、多 fork、多 plan 版本，再提升为一等对象。

**字段说明**：

- `owner_did`：目标归属者（人类或 Owner Agent），拥有最终决策权。
- `controller_did`：执行控制者（v1.1 中通常是 Secretary Agent 的 DID），负责创建 session、启动 Loop Engine、响应 DecisionGate。当 Owner 自行控制时，`controller_did == owner_did`。

### 4.2 Objective Loop Engine

Objective Loop Engine 是状态机，不是聊天 Agent。它读取当前 session/run/artifact/receipt/decision 状态，决定下一步动作。

基础循环：

```text
while session not closed:
  load session/run/current_stage
  load artifacts/receipts/decisions/events
  if pending human decision:
    wait or notify Secretary
  elif current stage has no assigned execution:
    select worker and delegate
  elif execution is running:
    monitor lease / timeout / status  # 事件驱动 + 轮询 fallback（默认 5s 间隔）
  elif stage has artifact but no receipt:
    request review or auto-issue receipt per policy
  elif receipt approved/passed:
    advance
  elif receipt changes_requested/failed:
    retry or follow on_reject
  elif retry limit exceeded:
    create human decision gate
  else:
    emit blocked event
```

### 4.3 ExecutionBackend

ExecutionBackend 负责“怎么执行”，不负责“目标是否完成”。

> **命名决议**：评审后定名为 `ExecutionBackend`。不再使用 `RuntimeAdapter` 作为实现类名，避免与已有 `PlatformAdapter` 混淆。本文早期语境中的 RuntimeAdapter 均指 ExecutionBackend。

统一接口：

```python
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ExecutionHandle:
    execution_id: str
    backend_kind: str
    worker_did: str
    stage: str
    status: str
    external_session_id: str = ""
    lease_expires_at: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class ExecutionResult:
    execution_id: str
    status: str  # completed | changes_requested | failed | blocked
    artifact_type: str
    artifact_body: str
    summary: str
    evidence_refs: list[str]
    human_decision_request: dict[str, Any] | None = None
    raw_output_ref: str = ""


class ExecutionBackend(Protocol):
    kind: str

    async def can_execute(self, worker: dict, stage: dict, objective: dict) -> bool: ...

    async def start_execution(
        self,
        *,
        coordination_session_id: str,
        run_id: str,
        stage: str,
        worker_did: str,
        input_refs: list[dict],
        constraints: dict,
    ) -> ExecutionHandle: ...

    async def poll_execution(self, handle: ExecutionHandle) -> ExecutionHandle: ...

    async def collect_result(self, handle: ExecutionHandle) -> ExecutionResult: ...

    async def cancel_execution(self, handle: ExecutionHandle, reason: str) -> None: ...
```

API 边界处将 dataclass 序列化为 dict，内部实现保持类型明确。

v1.1 首批 backend：

| Backend | 范围 | 说明 | v1.1 状态 |
|---------|------|------|
| `local_cli` | 本机 | 通过独立 local-runner 拉起 Claude Code / Codex / pytest / 自定义命令 | 必交 |
| `local_service` | 本机 | 调用本机 HTTP / SDK 常驻 Worker | 可选 |
| `lan_node` | 局域网 | 直连远程 AgentNexus Node endpoint | v1.2 |
| `relay_node` | 公网 | 通过 Relay 投递 delegation / message / result ref | v1.2 |

> **与已有 PlatformAdapter 的关系**：代码库中已存在 `agent_net/adapters/base.py` 的 `PlatformAdapter`（负责外部平台→AgentNexus SDK 协议转换，如 OpenClaw/Webhook）。ExecutionBackend 关注的是不同层面——"AgentNexus 语义→具体执行通道"。两者的分层关系为：
>
> ```text
> 外部平台 (OpenClaw/Webhook/Codex)
>   → PlatformAdapter (协议转换，已有)
>     → AgentNexus API / SDK
>       → Objective Loop Engine
>         → ExecutionBackend (执行通道，本设计新增)
>           → 具体 Runtime (CLI/HTTP/Relay)
> ```
>
> OpenClaw / Webhook 在 v1.1 中仍作为入口 PlatformAdapter，不作为 stage execution backend。Local stage execution 由 `local_cli` / `local_service` backend 负责。

### 4.4 Secretary Human Gateway

Secretary 不是总控大脑，而是人类交互边界：

- 接收人类目标。
- 创建或转发 Objective / CoordinationSession。
- 请求人类确认、审计、暂停、接管。
- 汇报最终 Closure 和 Delivery Manifest。
- 把人类回复转换为 DecisionReceipt / Owner action。

Worker 不应直接打扰人类。所有人工节点统一走 Secretary。

### 4.5 架构迁移路径：Secretary 角色演进与 Loop Engine 部署

**Secretary 角色变迁**：

Coding Coordination V1 中 Secretary 定位为 "Coordination Controller"（负责 intake → classify → dispatch → monitor → collect → deliver）。Objective Loop V1.1 将 Controller 职责上移到 Loop Engine，Secretary 收缩为 "Human Gateway"。

这不是推翻重来，而是职责分层：

```text
V1.0（当前）:
  Secretary = Intake + Controller + Human Contact

V1.1（目标）:
  Loop Engine = Controller（状态机、stage 调度、retry/fallback）
  Secretary   = Intake + Human Gateway（创建 Objective、请求确认、汇报 Closure）
```

迁移路径：

1. 现有 `POST /secretary/dispatch` 保留，作为 "intake → 创建 CoordinationSession + 启动 Loop Engine" 的入口。
2. Loop Engine 接管 `advance()` 的调用权（现有 `POST /coordination/coding/{id}/runs/{run_id}/advance` 继续可用，Loop Engine 作为其调用方）。
3. Secretary 新增 DecisionGate 相关端点：`POST /secretary/decision-requests`（向人类请求决策）、`POST /secretary/decision-responses`（人类回复）。
4. 现有 Secretary router 中纯 Controller 逻辑（dispatch 选 Worker、monitor 状态）逐步迁移到 Loop Engine service。

**Loop Engine 部署拓扑**：

目标架构中 Loop Engine 作为 **Daemon 内置 service**（类似现有 Playbook `advance()` 逻辑但更通用），确保状态权威来源在服务端：

```text
AgentNexus Daemon (:8765)
  ├── coordination router（已有）
  ├── secretary router（已有，保留 intake + human gateway）
  ├── Loop Engine service（新增）
  │     ├── next-action 状态计算
  │     ├── Worker selection + lease
  │     ├── retry / on_reject / fallback
  │     └── DecisionGate 触发
  └── ...
```

MVP 阶段可以先在 CLI/SDK 侧实现 `next-action` 逻辑做验证（如第 11.2 节所述），但文档已明确目标为服务端部署。客户端实现的限制：
- 客户端崩溃 → 所有 lease 僵尸
- 多机场景下无法确定权威 Loop Engine 实例
- 事件/状态一致性依赖客户端写入 DB

因此 Phase 2 必须将 Loop Engine 服务端化。

### 4.6 v1.1 实现模块映射

| 模块 | 文件 | 类型 | 说明 | 测试 |
|------|------|------|------|------|
| Loop Engine service | `agent_net/node/loop_engine.py` | 新增 | `next_action()`、`tick()`、retry / DecisionGate / advance 调用 | `tests/test_objective_loop_engine.py` |
| ExecutionBackend base | `agent_net/node/execution_backends/base.py` | 新增 | `ExecutionBackend` Protocol、`ExecutionHandle`、`ExecutionResult` | `tests/test_execution_backend_base.py` |
| Local CLI backend | `agent_net/node/execution_backends/local_cli.py` | 新增 | 命令模板、进程启动、timeout、stdout/stderr capture、result parse | `tests/test_local_cli_backend.py` |
| Local Runner CLI | `main.py` + `agent_net/node/local_runner.py` | 新增 | `node local-runner run/start`，读取 YAML 配置并调用 Loop Engine / backend | `tests/test_local_runner_cli.py` |
| Objective CLI | `main.py` | 新增 | `node objective start/status`，复用 coordination intake / status | `tests/test_objective_cli.py` |
| Execution router | `agent_net/node/routers/coordination.py` 或新增 `routers/executions.py` | 扩展 | executions CRUD、result submit、next-action API | `tests/test_objective_execution_api.py` |
| Storage | `agent_net/storage.py` | 扩展 | execution lease 字段、DecisionGate 复用、idempotency | `tests/test_objective_storage.py` |
| SDK facade | `agentnexus-sdk/src/agentnexus/coordination.py` | 扩展 | `next_action()`、`create_execution()`、`submit_execution_result()` | `agentnexus-sdk/tests/test_coordination_client.py` |
| Dashboard | `agent_net/node/static/coordination.html` | 扩展 | 展示 execution lease、next action、DecisionGate | smoke / 手工验收 |

实现顺序必须先做 storage + backend + runner 的本机 happy path，再做服务端 Loop Engine 自动 tick。不要先做 Dashboard 或 Tauri。

---

## 5. 网络半径

Objective Loop 必须覆盖三个半径，且对上层状态机保持同一语义。

### 5.1 L0 本机

```text
OpenClaw / Web / SDK / CLI
  -> Secretary
  -> Objective Loop Engine
  -> local-runner
  -> Claude Code / Codex / pytest / scripts
  -> Artifact / Receipt / Advance
```

验收：

- OpenClaw 只输入目标。
- local-runner 自动执行 implement / code_review / test。
- review failed 自动回退 implement。
- 超过 retry limit 通过 Secretary 请求人类决策。
- 不要求用户手动切到 Claude Code / Codex 调用 `fetch_inbox`。
- （L0 场景下所有 Worker 与 Secretary 共享同一 Daemon，inbox 机制不是瓶颈；L1/L2 场景下 Worker 的 inbox 模型沿用现有 Relay 离线投递 + `fetch_inbox` 机制。）

### 5.2 L1 局域网 [v1.2+]

```text
Machine A: Secretary + Loop Engine
Machine B: Developer Worker Node
Machine C: Reviewer Worker Node
LAN Relay or direct endpoint
```

验收：

- 不同机器的 Worker 通过 DID / endpoint / presence 被发现。
- Loop Engine 能选择局域网 Worker 并委派阶段。
- Worker 产物通过 Artifact Ref / Vault / Git / HTTP pull 传回。
- 节点离线时能够 fallback 或进入 blocked / retry。

### 5.3 L2 公网 Relay [v1.2+]

```text
Secretary Node
  -> Relay
  -> Remote Worker Node
  -> Relay
  -> Secretary Node
```

验收：

- 服务型 Worker 使用 public profile 公告到 Relay。
- Delegation 通过 Relay 投递；Worker 离线时进入 inbox。
- 大产物不经过公网种子 Relay，消息只携带 signed manifest / artifact ref。
- Remote Worker 的 receipt 可回传并推进同一个 CoordinationSession。

---

## 6. 本地 Runner / CLI Launcher

### 6.1 原则

本地命令执行风险高，不能放进 Secretary 主进程。v1.1 必须把 CLI Launcher 设计为独立 sidecar：

```text
AgentNexus Daemon
  -> Objective Loop Engine
  -> local-runner sidecar
  -> allowed command templates
```

安全原则：

- 命令模板白名单。
- 固定 workdir 或 workdir allowlist。
- 环境变量 allowlist。
- 默认不注入 secrets。
- 每次执行有 lease、timeout、stdout/stderr capture。
- 结果写 artifact，不把任意 stdout 当作可信状态。
- destructive / network / secret access 通过 DecisionGate 升级人类。
- stdout/stderr 必须有最大长度限制，超过限制后截断并保留本地 raw output ref。
- 启动命令不得经过 shell 字符串拼接；使用 argv list 形式调用子进程。
- `timeout_sec` 到期后必须 kill 进程树，并写入 `timed_out` execution 状态。

> **重要安全前提 — Sandbox 隔离**：白名单和 DecisionGate 属于"前置审批"和"事后拦截"机制，但无法阻止已获授权的 LLM Worker 在 session 内执行危险操作（如 `rm -rf` 或外传数据）。v1.1 的 local-runner 执行环境必须满足：
>
> - Worker 进程应在 **容器/sandbox** 中运行（Docker / Podman / Windows Sandbox），不直接使用宿主机 shell。
> - `workdir` 应 mount 为只读或 copy-on-write，防止 Worker 修改允许范围外的文件。
> - 网络访问默认切断（`network_access: deny_by_default`），需要时经 DecisionGate 开启。
> - Prompt 中注入 hard constraints 作为纵深防御（如 "You are running in an isolated sandbox. The workspace is read-only outside of /workspace/output."）。
>
> 在没有 sandbox 隔离的环境中，local-runner 的安全保证仅限于 "信任 Worker DID 的 Owner 自行承担风险"。

**v1.1 P0 安全要求**：

| 要求 | v1.1 行为 |
|------|-----------|
| command allowlist | 只允许 YAML 中显式声明的命令模板 |
| argv execution | 使用 argv list，不通过 shell 拼接 |
| workdir allowlist | 默认只允许仓库根目录和 `.agentnexus/workspaces/*` |
| env allowlist | 默认只继承最小环境；额外 env 必须显式配置 |
| network policy | 配置项必须存在；默认 `deny_by_default`，本机 MVP 可以先记录并提示，不承诺 OS 级强制 |
| destructive preflight | 检测明显 destructive command token，触发 DecisionGate |
| timeout kill | 超时 kill 进程树，execution 标记 `timed_out` |
| output limit | stdout/stderr 分别限制大小，默认 1MB |
| raw output handling | raw output 只作为 artifact 证据，不直接作为状态 |

完整容器/sandbox 标准化配置后移到 v1.3+ 产品化，但以上 P0 要求必须随 local-runner MVP 一起实现。

### 6.2 配置

> **CLI 路径兼容性**：`command` 字段支持简短名称（`claude`、`codex`）或全路径。Runner 启动时通过 `shutil.which()` 解析简短名称；解析失败时应报错退出，不静默 fallback。

L0-Ready 要求 worker 配置不再只描述“命令”，还必须描述 **身份、授权边界和输出契约**。`agent_name` 仅用于显示，不能作为执行身份。Runner 启动时必须校验：

- `worker_did` 必填，且是本 Daemon 已注册 Agent。
- `worker_did` 必须绑定到同一 `owner_did`，或持有可验证的 capability token。
- `worker_type` 必须为 `interactive_cli`、`resident` 或 `service_worker` 之一；v1.1 的 `local_cli` 只执行 `interactive_cli` 或明确允许的本机脚本 worker。
- `adapter` v1.1 只允许 `local_cli`；`local_service` 是可选增强，`lan_node` / `relay_node` 必须 fail fast。
- `roles` / `capabilities` 至少命中一个当前 Playbook stage。
- `workdir` 必须落在 allowlist 内；相对路径按配置文件所在目录解析。
- `env` 只能引用 allowlist 中的环境变量名，不允许把任务文本拼进环境变量。
- `output_contract` 必须声明 `agentnexus_json_v1`；Runner 只接受这个 contract 作为状态来源。

```yaml
# .agentnexus/local-runner.yaml
daemon_url: http://127.0.0.1:8765
secretary_agent: did:agentnexus:z6MkSecretary...
owner_did: did:agentnexus:z6MkOwner...
poll_interval_sec: 2

defaults:
  workdir: D:\PycharmProjects\AgentNexus
  timeout_sec: 1800
  max_retries_per_stage: 2
  network_access: deny_by_default
  max_output_bytes: 1048576

workers:
  claude_developer:
    worker_did: did:agentnexus:z6MkClaudeDeveloper...
    agent_name: ClaudeDeveloper
    worker_type: interactive_cli
    adapter: local_cli
    command: claude
    args: ["-p", "{prompt}"]
    roles: ["developer", "implement"]
    capabilities: ["Code", "Debug", "Implement"]
    output_contract: agentnexus_json_v1
    workdir: D:\PycharmProjects\AgentNexus

  codex_reviewer:
    worker_did: did:agentnexus:z6MkCodexReviewer...
    agent_name: CodexReviewer
    worker_type: interactive_cli
    adapter: local_cli
    command: codex
    args: ["exec", "{prompt}"]
    roles: ["reviewer", "code_review"]
    capabilities: ["Review", "Code", "QA"]
    output_contract: agentnexus_json_v1

  pytest_runner:
    worker_did: did:agentnexus:z6MkLocalTestRunner...
    agent_name: LocalTestRunner
    worker_type: interactive_cli
    adapter: local_cli
    command: python
    args: ["-m", "pytest"]
    roles: ["tester", "test"]
    capabilities: ["Test"]
    output_contract: agentnexus_json_v1
```

### 6.3 Prompt Contract

Runner 给 CLI Worker 的 prompt 必须结构化，避免传完整聊天历史。

```text
You are an AgentNexus worker.

CoordinationSession: {coordination_session_id}
Run: {run_id}
Stage: {stage}
Role: {role}
Objective: {objective}

Input refs:
{artifact_refs}

Constraints:
{constraints}

Return a JSON block with:
- summary
- status: completed | changes_requested | failed | blocked
- artifact_type
- artifact_body
- evidence_refs
- human_decision_request, optional
```

#### 6.3.1 Structured Result Contract `agentnexus_json_v1`

真实 CLI Agent 可以在 stdout 中输出解释文本，但必须包含一个可解析 JSON object。Runner 只把该 JSON object 作为 execution result；其他 stdout/stderr 只能作为证据或 debug log。

最小 schema：

```json
{
  "contract": "agentnexus_json_v1",
  "summary": "short human-readable summary",
  "status": "completed | changes_requested | failed | blocked",
  "artifact_type": "RequirementSpec | DesignArtifact | ImplementationArtifact | CodeReviewArtifact | TestResultArtifact | DeliveryManifest | Other",
  "artifact_body": "markdown or compact text body",
  "artifact_refs": [
    {"kind": "file", "ref": "vault://enc/key"}
  ],
  "evidence_refs": [],
  "human_decision_request": {
    "gate": "network_access | secret_access | low_confidence | max_retry_exceeded",
    "question": "What should the owner decide?"
  }
}
```

字段规则：

- `contract` 缺失时 v1.1 可兼容旧 worker，但必须 emit warning；L0-Ready 验收要求真实 worker 输出 `contract=agentnexus_json_v1`。
- `artifact_body` 适合小型 Markdown / diff summary；大文件必须写入 allowlisted output directory，再通过 `artifact_refs` 引用。
- `artifact_refs` 中的本地文件必须由 runner 写入 Vault 后转换为 `vault://` ref；不得把任意本地绝对路径直接暴露给下一 stage。
- `status=blocked` 必须附带 `human_decision_request`；否则按 `low_confidence` 处理。
- `changes_requested` 必须说明需要回退的原因，Loop Engine 根据 Playbook `on_reject` 决定回退 stage。

#### 6.3.2 推荐 CLI Profile

L0-Ready 必须提供并验收以下内置 profile 示例，而不是只提供 fake worker：

| Profile | 用途 | 推荐命令 | 关键要求 |
|---------|------|----------|----------|
| `codex_exec` | 实现、评审、修复 | `codex exec {prompt}` | 必须固定 working tree，输出 JSON result，不直接提交 git |
| `claude_code_print` | 设计、实现、评审 | `claude -p {prompt}` | 必须限制输出大小，失败时保留 raw output |
| `pytest` | 测试阶段 | `python -m pytest <path>` | Runner 包装 pytest 输出为 `TestResultArtifact` |
| `script_json` | 可重复脚本 worker | `python script.py --input <json>` | 脚本直接输出 `agentnexus_json_v1` |

Runner 必须容忍 Worker 输出包含解释文本；只把可解析的 structured result 作为状态依据。解析失败时的处理策略：

1. **自动重试（1 次）**：Loop Engine 向同一 Worker 发送简化重试 prompt（"Your previous response could not be parsed as valid JSON. Please reformat your result as the specified JSON structure only."），不收取额外 stage 重试配额。
2. **重试仍失败**：写入 raw artifact，并创建 `blocked` receipt 或 `low_confidence` DecisionGate，请求人类判断。
3. **可选增强**：如果 ExecutionBackend 支持 structured output / function calling（如 `local_service` backend 对接支持 tools 的 API），应优先使用该能力作为主路径，Prompt Contract 作为 fallback。

### 6.4 Runner 可靠性与幂等

L0-Ready 的 local-runner 可以仍是 sidecar，但必须具备“可重启、可接管、不会重复破坏状态”的行为。它不是聊天客户端，而是本机 Objective Loop 的执行调度器。

#### 6.4.1 Tick 幂等

每个 tick 必须满足：

- 同一 `coordination_session_id + run_id + stage` 同一时间最多只有一个 active execution（`pending|running`）。
- 如果已有 active execution，runner 只能 `poll_execution` 或等待 lease，不得创建第二个 execution。
- `POST /coordination/executions/{id}/result` 必须用 `result_hash` 幂等；相同结果重复提交返回既有 artifact/receipt，不同结果返回 conflict。
- `advance` 只能在 artifact + approved/passed receipt 存在时调用；重复 `advance` 必须安全。
- runner 进程重启后，先从 Daemon 拉取 active executions，再决定接管、等待或标记 timed_out。

#### 6.4.2 Lease 与恢复

Lease 是 Daemon 侧权威状态，不是 runner 内存状态。Runner 必须：

1. 创建 execution 时写入 `lease_expires_at`。
2. 本地进程仍在运行时可续租；续租失败时不应继续无限执行。
3. 本地进程退出但未提交 result 时，按 return code / timeout 写回 execution 状态。
4. runner 崩溃后重启，发现过期 lease 时按策略处理：
   - 有可验证 output ref → collect/submit。
   - 无 output → retry 同 worker。
   - 超过 retry 上限 → DecisionGate。
5. Ctrl+C 或系统停止时尽力 cancel running subprocess，并写入 `cancelled` 或保留 lease 等待超时。

#### 6.4.3 Loop Budget

每个 objective 必须有可配置预算，防止自动循环失控：

```yaml
defaults:
  max_retries_per_stage: 2
  max_total_executions: 30
  max_wall_clock_sec: 14400
  require_final_acceptance: false
```

超过预算时，Loop Engine 创建 `max_retry_exceeded` 或 `budget_exceeded` DecisionGate，不得继续自动执行。

---

## 7. Stage 策略

v1.1 先以 coding objective 验证，但模型必须通用于其他流程。

默认 coding stage 策略：

| Stage | 执行者 | Artifact | Receipt | 备注 |
|-------|--------|----------|---------|------|
| `clarify` | Secretary / auto | RequirementSpec | approved | 不确定则问人 |
| `design` | Planner / Claude / auto | DesignArtifact | approved | MVP 可模板化 |
| `design_review` | Reviewer / Codex | DesignReviewArtifact | approved / changes_requested | 可选 |
| `implement` | ClaudeDeveloper | ImplementationArtifact | approved | 输出 diff / summary |
| `code_review` | CodexReviewer | CodeReviewArtifact | approved / changes_requested | rejected 回 implement |
| `test` | pytest_runner | TestResultArtifact | passed / failed | failed 回 implement |
| `final` | Loop Engine | DeliveryManifest | passed | 自动 closure |

Receipt-gated advance 保持现有 Coordination API 语义：

- stage 有 artifact。
- stage 有 approved / passed receipt。
- `advance()` 推进到 next。
- changes_requested / failed 按 playbook `on_reject` 回退或 blocked。

### 7.1 与现有 Playbook / PlaybookRun 的映射

Objective Loop 不替代现有 Playbook 系统，而是在其之上增加自动化调度层。映射关系：

| Objective Loop 概念 | 现有实现（Coding Coordination V1） | v1.1 改动 |
|---|---|---|
| Stage 定义 | `Playbook.stages`（`coding.v1` 内置定义） | 不变，继续作为权威 stage 来源 |
| Stage 执行状态 | `PlaybookRun` + `stage_executions` 表 | 新增 `execution_id`（lease 追踪）、`retry_count` |
| Stage 推进 | `POST /coordination/coding/{id}/runs/{run_id}/advance` | Loop Engine 调用 advance()，不替代 |
| 重试/回退逻辑 | Playbook stage `on_reject` 字段 | Loop Engine 增加 retry counter，上限后触发 DecisionGate |
| 人工决策点 | 无（依赖调用方自行判断） | 新增 DecisionGate 表 + `decision_requests`（storage 已有该表雏形） |
| Worker 选择 | Secretary dispatch 按 capability 匹配 | Loop Engine 接管，增加 presence/lease/network_scope 排序 |
| 产物引用 | `artifacts` 表 + `content_ref` (`vault://`) | v1.1 本机场景继续使用 `vault://`；`artifact://` 为 v1.2+ 远程场景预留（见第 10 节） |
| 事件流 | `runtime_events` 表 + SSE stream | Loop Engine 通过 `emit_event()` 写入，保持兼容 |

---

## 8. 人工决策点

Human DecisionGate 是 Objective Loop 的一等路径，不是异常。

触发类型：

| Gate | 触发条件 | Secretary 行为 |
|------|----------|----------------|
| `scope_change` | Worker 发现目标范围扩大 | 请求 Owner 同意或收窄 |
| `secret_access` | 需要凭据、token、私有服务 | 请求授权或替代方案 |
| `destructive_command` | 删除、重置、迁移、生产写入 | 请求确认 |
| `network_access` | 需要外网、下载依赖、调用第三方 | 请求许可 |
| `low_confidence` | Worker 自评低信心或输出不可解析 | 请求人类判断 |
| `review_conflict` | 多 reviewer 结论冲突（v1.2+；v1.1 仅串行 review，此 gate 暂不触发） | 请求仲裁 |
| `max_retry_exceeded` | 同一 stage 超过重试上限 | 请求接管 / 放弃 / 放宽约束 |
| `final_acceptance` | 目标要求人工最终验收 | 请求验收 |

人类回复必须落成结构化 DecisionReceipt：

```json
{
  "decision": "approved | changes_requested | rejected | aborted",
  "comment": "...",
  "actor_did": "<owner_or_delegate_did>",
  "evidence_refs": []
}
```

### 8.1 DecisionGate 恢复语义

DecisionGate 不是终态。Owner 或授权代表回复后，Loop Engine 必须按结构化决策恢复流程：

| human decision | Loop Engine 行为 |
|----------------|------------------|
| `approved` / `passed` | 对当前 stage 重新进入 `start_execution` 或继续被批准的动作；如果 gate 是 `final_acceptance`，生成 closure |
| `changes_requested` | 按当前 stage 的 `on_reject` 回退；如果无 `on_reject`，重试当前 stage |
| `rejected` / `failed` | 标记当前 stage failed；有 fallback worker 则切换，否则创建失败 closure |
| `aborted` | 将 PlaybookRun / CoordinationSession 标记 aborted，生成 aborted closure |

恢复时必须满足：

- 已 resolved 的 decision 不得再次阻塞当前 stage。
- 只等待当前 stage 的 pending decision；历史 stage 的遗留 pending decision 不得死锁 session。
- decision response 必须写 runtime event 和 receipt，便于 Dashboard / audit 追踪。
- Secretary 负责通知人类和收集回复；Loop Engine 只消费结构化 decision 状态。

---

## 9. Worker 选择与 Lease

Worker selection 输入：

- required role / capabilities
- presence: available / busy / offline
- network scope: local / lan / relay
- trust score / governance
- owner binding / project membership
- adapter compatibility
- user-configured priority hint（如 `preferred_worker`、`local_first`；v1.1 不做动态 cost 排序，原因见第 3 节非目标）

MVP 排序：

1. 同 Owner 绑定 Worker。
2. capability 精确匹配。
3. available 优先于 busy，busy 优先于 offline。
4. v1.1 中所有 Worker 均为 local 范围；v1.2+ 扩展为 local 优先于 lan、lan 优先于 relay，除非用户指定 remote。
5. 最近成功执行过同类 stage 的 Worker 优先。

### 9.1 L0 Worker 准入

L0 不是“无身份命令池”。每个可被 runner 调度的本机 Worker 必须先进入 Worker Registry：

| 字段 | 要求 |
|------|------|
| `worker_did` | 必须是本地 Daemon 管理的 DID |
| `owner_did` | 必须等于 objective owner，或由 capability token 授权 |
| `worker_type` | `interactive_cli` / `resident` / `service_worker` |
| `presence` | `available` 才可自动分派；`busy` 仅在无 available 且策略允许时使用 |
| `roles` / `capabilities` | 必须与 stage role 或 required capability 匹配 |
| `adapter` | v1.1 默认 `local_cli` |
| `trust_policy` | v1.1 可先使用 owner-bound 信任；陌生 DID 后移到 v1.2+ |

Runner 启动时应把 YAML worker profile 与 Registry 记录做一次 reconcile：

- YAML 有、Registry 无 → fail fast，并提示先注册/bind worker。
- Registry 有、YAML 无 → 不自动执行，只作为可见 worker。
- DID owner 不匹配 → 拒绝执行。
- presence 非 `available` → 默认跳过。

### 9.2 Fallback 策略

L0-Ready 必须支持最小 fallback：

1. 同一 stage 首选 worker 执行失败或 timed out。
2. 如果未超过 `max_retries_per_stage`，优先 retry 同 worker 一次。
3. 如果同 role 有其他 available worker，切换 worker，并在 execution metadata 记录 `fallback_from`。
4. 所有候选失败后创建 DecisionGate。
5. `changes_requested` 不等同 worker failure，应按 Playbook `on_reject` 回退。

每个 execution 必须有 lease：

```json
{
  "execution_id": "exec_...",
  "stage": "implement",
  "worker_did": "did:agentnexus:...",
  "adapter_kind": "local_cli",
  "lease_expires_at": 1777056000,
  "status": "pending | running | completed | failed | timed_out | cancelled"
}
```

Lease 过期后，Loop Engine 可以：

- 续租。
- 重试同 Worker。
- fallback 到另一个 Worker。
- 创建 human DecisionGate。

---

## 10. Artifact Transport

Objective Loop 不传完整上下文，只传 ref。

| 范围 | Artifact 策略 | 传输机制 |
|------|---------------|----------|
| 本机 | Local Vault / file path / Git diff | 直接文件系统访问，`vault://enclave/key` |
| 局域网 [v1.2+] | HTTP pull / Git Vault / direct daemon fetch | Worker Node 暴露 `GET /artifacts/{artifact_id}/content`；Loop Engine 通过 `artifact://<node_endpoint>/<path>` 解析 |
| 公网 [v1.2+] | Relay message 只传 manifest ref；大内容走可授权下载或 Git remote | Relay envelope 仅携带 `manifest_ref`；Worker 自行通过 HTTPS 或 Git remote pull 获取内容 |

**ArtifactRef 格式**（统一协议定义；实现版本见注释）：

```text
vault://<enclave_id>/<key>              # v1.1 本机 Vault（已有，v1.1 唯一必需格式）
artifact://<node_did>/<artifact_id>     # v1.2+ 远程 Daemon artifact endpoint
git://<repo_url>@<rev>/<path>           # v1.2+ Git 引用
https://<url>                           # v1.2+ 通用 HTTPS 下载
```

**不可解析 ref 的处理**：

1. Loop Engine 尝试解析 ref → 失败。
2. 记录 `blocked` event（原因：`artifact_ref_unresolvable`）。
3. 如果 Worker 在线 → 自动重试 1 次。
4. 仍不可解析 → 创建 `low_confidence` DecisionGate，请求人类提供替代产物来源或跳过该 stage。
5. 不自动跳过——缺失 artifact 的阶段不应标记为 `approved`。

> v1.1 本机场景只要求支持 `vault://`。`artifact://`、`git://` 和 `https://` 是 v1.2+ 跨节点 Artifact Transport 的协议预留；v1.1 可以解析并拒绝未启用的远程 scheme，但不得声称已支持远程拉取。

Delivery Manifest 必须汇总：

- objective
- session / run
- stages
- artifact refs
- receipts
- decisions
- closure status
- human intervention summary

---

## 11. API / CLI 影响

### 11.1 新 CLI

```bash
python main.py node objective start \
  --owner <owner_did> \
  --actor <secretary_did> \
  --objective "实现并评审登录模块" \
  --roles developer,reviewer,tester

python main.py node local-runner start \
  --config .agentnexus/local-runner.yaml

python main.py node local-runner run \
  <coordination_session_id> <run_id> \
  --config .agentnexus/local-runner.yaml

python main.py node objective status <coordination_session_id> \
  --actor <did>
```

### 11.2 API 增量

优先复用现有 Coordination API。必要时新增：

| API | 说明 |
|-----|------|
| `GET /coordination/sessions?status=running` | Runner 查找可接管 session |
| `GET /coordination/sessions/{id}/next-action` | Loop Engine 计算下一步 |
| `POST /coordination/executions` | 创建 StageExecution lease |
| `PATCH /coordination/executions/{id}` | 更新执行状态 |
| `POST /coordination/executions/{id}/result` | 提交 runner result，服务端转换 artifact/receipt/event |

MVP 可以先在 CLI/SDK 内实现 next-action 逻辑，验证后再服务端化。

### 11.3 API Contract

#### GET `/coordination/sessions/{id}/next-action`

用途：由 Loop Engine 或 local-runner 获取当前应该执行的下一步动作。

请求：

```http
GET /coordination/sessions/cs_123/next-action?actor_did=did:agentnexus:...
```

响应：

```json
{
  "status": "ok",
  "action": {
    "action_type": "start_execution",
    "coordination_session_id": "cs_123",
    "run_id": "run_123",
    "stage": "implement",
    "role": "developer",
    "worker_did": "did:agentnexus:z...",
    "backend_kind": "local_cli",
    "input_refs": [
      {"ref": "vault://enc_123/design/spec.md", "kind": "DesignArtifact"}
    ],
    "constraints": {
      "timeout_sec": 1800,
      "network_access": "deny_by_default",
      "max_output_bytes": 1048576
    },
    "reason": "stage has no active execution and no artifact"
  }
}
```

`action_type` 枚举：

| 值 | 含义 |
|----|------|
| `start_execution` | 创建 execution 并启动 backend |
| `poll_execution` | 已有 execution running，需要 poll |
| `collect_result` | execution completed，需要收集结果 |
| `submit_receipt` | stage 有 artifact 但缺 receipt |
| `advance` | stage 可推进 |
| `create_decision_gate` | 需要人工决策 |
| `wait` | 等待外部事件 / 人类回复 |
| `closed` | session 已闭环 |
| `blocked` | 无可执行动作 |

#### POST `/coordination/executions`

请求：

```json
{
  "coordination_session_id": "cs_123",
  "run_id": "run_123",
  "stage": "implement",
  "worker_did": "did:agentnexus:z...",
  "backend_kind": "local_cli",
  "actor_did": "did:agentnexus:secretary",
  "lease_ttl_sec": 1800,
  "metadata": {
    "config_worker": "claude_developer",
    "command_template_hash": "sha256:..."
  }
}
```

响应：

```json
{
  "status": "created",
  "execution": {
    "execution_id": "exec_123",
    "coordination_session_id": "cs_123",
    "run_id": "run_123",
    "stage": "implement",
    "worker_did": "did:agentnexus:z...",
    "backend_kind": "local_cli",
    "status": "pending",
    "lease_expires_at": 1777056000.0
  }
}
```

#### PATCH `/coordination/executions/{execution_id}`

请求：

```json
{
  "actor_did": "did:agentnexus:z...",
  "status": "running",
  "lease_ttl_sec": 1800,
  "external_session_id": "local-cli-abc",
  "metadata": {
    "pid": 12345
  }
}
```

响应：

```json
{
  "status": "updated",
  "execution_id": "exec_123"
}
```

#### POST `/coordination/executions/{execution_id}/result`

请求：

```json
{
  "actor_did": "did:agentnexus:z...",
  "result": {
    "status": "completed",
    "artifact_type": "ImplementationArtifact",
    "artifact_body": "Implemented login flow...",
    "summary": "完成登录流程实现",
    "evidence_refs": ["vault://enc_123/raw/exec_123.stdout"],
    "human_decision_request": null
  }
}
```

响应：

```json
{
  "status": "accepted",
  "execution_id": "exec_123",
  "artifact_id": "art_123",
  "receipt_id": "rcpt_123",
  "next_action_hint": "advance"
}
```

处理规则：

- `completed` → submit artifact + approved receipt（除 review/test 等特殊 stage 可按策略生成 receipt）。
- `changes_requested` → submit artifact + changes_requested receipt。
- `failed` → submit artifact + failed receipt。
- `blocked` 且含 `human_decision_request` → create DecisionGate。
- result submit 必须幂等：同一 `execution_id` 重复提交返回同一 artifact / receipt，不重复创建。

---

## 12. 存储与迁移

v1.1 优先扩展现有 coordination 存储，不另起一套 objective 数据库模型。

### 12.1 表结构

新增 `objective_executions` 表，用于 execution lease 和 backend 状态。原因：现有 `stage_executions` 偏向 Playbook stage assignment，已被 Enclave / Secretary 使用；Objective Loop 需要一对多 execution attempts、lease、backend metadata 和幂等 result，不宜直接把所有字段塞进旧表。

```sql
CREATE TABLE IF NOT EXISTS objective_executions (
    execution_id TEXT PRIMARY KEY,
    coordination_session_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    worker_did TEXT NOT NULL,
    backend_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    lease_expires_at REAL,
    attempt INTEGER DEFAULT 1,
    external_session_id TEXT DEFAULT '',
    artifact_id TEXT DEFAULT '',
    receipt_id TEXT DEFAULT '',
    result_hash TEXT DEFAULT '',
    error TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL
);

CREATE INDEX IF NOT EXISTS idx_objective_executions_session
  ON objective_executions(coordination_session_id, run_id, stage);

CREATE INDEX IF NOT EXISTS idx_objective_executions_status
  ON objective_executions(status, lease_expires_at);
```

状态枚举：

```text
pending | running | completed | changes_requested | failed | blocked | timed_out | cancelled
```

### 12.2 复用表

| 能力 | 表 / 函数 | v1.1 用法 |
|------|-----------|-----------|
| Session | `coordination_sessions` | objective 仍存在 session objective 字段 |
| Playbook runtime | `playbook_runs` | current_stage / status 权威来源 |
| Stage assignment | `stage_executions` | 保留现有 Secretary / Enclave 语义；可记录 active worker |
| Artifact | coordination artifacts | execution result 转 artifact |
| Receipt | coordination receipts | execution result 转 receipt |
| DecisionGate | `decision_requests` | 复用现有 Owner decision request |
| Timeline | `runtime_events` | execution lifecycle 写事件 |

### 12.3 新增 Storage 函数

```python
async def create_objective_execution(...)-> dict: ...
async def get_objective_execution(execution_id: str) -> dict | None: ...
async def list_objective_executions(
    coordination_session_id: str,
    run_id: str | None = None,
    stage: str | None = None,
    status: str | None = None,
) -> list[dict]: ...
async def update_objective_execution(execution_id: str, **kwargs) -> bool: ...
async def mark_execution_result(
    execution_id: str,
    *,
    artifact_id: str,
    receipt_id: str,
    result_hash: str,
    status: str,
) -> dict: ...
```

幂等要求：`mark_execution_result` 如果 `result_hash` 相同且已有 artifact / receipt，应返回既有记录；如果同一 execution 提交不同 result hash，应返回 409 conflict。

---

## 13. OpenClaw 入口体验

OpenClaw 作为 Secretary 人类入口，目标体验：

```text
请通过 AgentNexus 发起一个目标：
实现本地登录流程 demo，要求有代码实现、代码评审和测试报告。
风险：normal。
需要人工确认：最终验收。
```

OpenClaw 只需要：

1. 调用 AgentNexus intake / objective start。
2. 返回 session/run/dashboard URL。
3. 在 DecisionGate 或 Closure 时和人类对话。

不再要求用户手动切换到 Claude Code / Codex 执行 `fetch_inbox`。

### 13.1 L0-Ready 使用路径

OpenClaw 对话里不直接执行 stage，也不直接拼接本机命令。它只作为入口和人机交互界面：

```text
用户 -> OpenClaw
  -> /adapters/openclaw/invoke 或 MCP tool
  -> objective intake
  -> CoordinationSession + PlaybookRun
  -> local-runner 自动执行本机 Worker profiles
  -> DecisionGate / Closure 回到 OpenClaw 或 Dashboard
```

OpenClaw 入口必须返回：

- `coordination_session_id`
- `run_id`
- Dashboard URL
- 当前 next action
- 如果没有运行 local-runner，提示启动命令

DecisionGate 触发后，OpenClaw / Secretary 必须能展示：

- gate 类型和风险级别
- 触发 stage、worker DID、execution ID
- artifact / raw output evidence refs
- 可选决策按钮：approve / request changes / reject / abort

---

## 14. 验收标准

### 14.1 L0 本机验收

L0-Demo 验收：

- 一条 OpenClaw / SDK objective 创建 running session。
- `local-runner start` 自动发现 session。
- fake worker 可跑通 clarify → design → design_review → implement → code_review → test → final。
- final closure 自动生成 Delivery Manifest。
- Dashboard 能看到 timeline / artifacts / receipts / decisions / closure。

L0-Ready 验收：

- 至少 3 个真实本机 Worker DID 已注册并绑定同一 Owner：developer、reviewer、tester。
- `.agentnexus/local-runner.yaml` 中每个 worker profile 都有 `worker_did`、`worker_type`、`output_contract` 和 allowlisted `workdir`。
- Claude/Codex 或等价 CLI Worker 完成 implement / code_review，pytest 或等价脚本 Worker 完成 test。
- 所有真实 Worker 输出 `agentnexus_json_v1`；invalid JSON 会自动重试一次，仍失败则进入 `low_confidence` DecisionGate。
- review/test failed 时自动回 implement 或 fallback 到同 role 下一个 available Worker，最多重试 2 次。
- runner 重启后不会重复创建 active execution；能接管或等待已有 lease。
- DecisionGate pending 时只阻塞当前 stage；人类 approve 后继续，abort 后生成 aborted closure。
- execution 的 `worker_did` 是真实 DID，不是 display name。
- artifact body / artifact refs 写入 Vault；下一 stage 通过 `vault://` ref 获取上下文，不依赖完整聊天历史。
- OpenClaw / SDK / CLI 三种入口至少一种能发起 objective，并返回 session/run/dashboard URL。

### 14.2 L1 局域网验收 [v1.2+]

- 至少两台机器，各自运行 AgentNexus Node。
- Secretary 在机器 A，Developer 在机器 B。
- A 能通过 DID / Relay / endpoint 找到 B。
- B 执行一个 stage 并回传 artifact/receipt。
- B 离线时 A 能标记 blocked 或 fallback。

### 14.3 L2 公网验收 [v1.2+]

- Worker 通过 public Relay 可发现。
- Delegation 可通过 Relay 投递。
- Worker 离线时 inbox 持久化。
- Worker 上线后处理任务并回传 receipt。
- 大产物不进入公网 Relay 正文。

---

## 15. 实施顺序

> **v1.1 范围边界**：Phase 1–3 构成 v1.1 的最小可验收版本（L0 本机 Objective Loop 闭环）。Phase 4（LAN Worker）和 Phase 5（Relay Worker）推后到 v1.2；Phase 6（产品化）推后到 v1.3+。原因：Coding Coordination V1 从 P0 foundation 到 release closure 已是一个大版本的工作量；Objective Loop 涉及的 RuntimeAdapter 框架、Loop Engine 状态机、DecisionGate 系统和 Secretary 角色重构，仅本机闭环就已相当于 2–3 倍的 Coding Coordination V1 开发量。先验证 L0 核心假设，再扩展网络半径。

### Phase 1 — Local Runner MVP **[v1.1]**

- `.agentnexus/local-runner.yaml`
- `python main.py node local-runner run <session_id> <run_id>`
- 支持 implement / code_review / test 三类 stage。
- 复用 `submit_artifact` / `submit_receipt` / `advance`。
- 替代 `runtime-mock` 作为真实本机 worker demo。
- Worker profile 必须绑定真实 `worker_did`，不再用 display name 代替执行身份。

### Phase 2 — Objective Loop Engine **[v1.1]**

- `next-action` 状态计算。
- retry / on_reject / DecisionGate。
- session discovery：自动接管 running sessions。
- Dashboard 展示 loop state。
- active execution 去重、lease 过期恢复、runner restart 幂等。

### Phase 3 — Secretary Human Gateway **[v1.1]**

- OpenClaw / Web / SDK 入口统一 objective intake。
- DecisionGate 经 Secretary 推给人类。
- 人类回复写 DecisionReceipt。
- human decision 恢复语义接入 Loop Engine。

### Phase 3.5 — L0-Ready Hardening **[v1.1 必须完成后才进入 v1.2]**

- Codex / Claude / pytest / script 的推荐 Worker Profile。
- `agentnexus_json_v1` structured result contract。
- Worker Registry 与 YAML profile reconcile。
- 本机 fallback：同 role 多 worker 切换。
- Runner crash/restart 恢复测试。
- OpenClaw 或 SDK objective 入口 smoke test。
- 真实 CLI 缺失时的清晰错误、fallback 指引和文档。

### Phase 4 — LAN Worker **[v1.2]**

- Worker endpoint / presence / lease。
- LAN node adapter。
- 局域网 artifact transport。

### Phase 5 — Relay Worker **[v1.2]**

- Relay delegation delivery。
- Offline inbox resume。
- Remote receipt / manifest ref 回传。

### Phase 6 — Productization **[v1.3+]**

- Tauri desktop shell。
- System tray notification。
- Dashboard objective view。
- Adapter marketplace / version binding。

---

## 16. 设计风险

| 风险 | 处理 |
|------|------|
| CLI 命令执行安全风险 | 独立 sidecar、白名单、固定 workdir、DecisionGate |
| Worker 输出不可解析 | raw artifact + blocked receipt + human gate |
| Relay 被误用为存储 | Relay 只传 envelope / manifest ref |
| Loop Engine 变成另一个 PM Agent | 状态机优先，LLM 只作为 planner/worker，可替换 |
| 单产品 team mode 发展太快 | AgentNexus 聚焦跨运行时/跨网络/身份授权/审计 |
| 多机 artifact 同步复杂 | v1.1 先支持 ref/manifest，完整同步后移 |
| 自动循环失控 | retry limit、lease、cost/time budget、human gate |

---

## 17. P0 开发任务拆分

### P0-1 Storage + API

目标：建立 execution lease 和 result submit 的服务端权威状态。

交付：

- `objective_executions` 表和 CRUD。
- `POST /coordination/executions`
- `PATCH /coordination/executions/{execution_id}`
- `POST /coordination/executions/{execution_id}/result`
- result submit 幂等测试。

验收：

- 单元测试覆盖 create/update/list/result conflict。
- result submit 能创建 artifact + receipt。

### P0-2 Local CLI Backend

目标：用安全的 argv 子进程执行本机 worker。

交付：

- `ExecutionBackend` base。
- `local_cli` backend。
- YAML 配置加载和校验。
- worker profile 校验：`worker_did`、owner binding、`worker_type`、`output_contract`、workdir allowlist。
- timeout kill、output limit、raw output ref。
- JSON result 解析 + 1 次解析重试。

验收：

- fake command 输出 valid JSON → completed result。
- fake command 输出 invalid JSON → retry 后 blocked / DecisionGate。
- timeout command → timed_out。
- 未在 allowlist 的 command → 拒绝启动。
- YAML worker DID 未注册或 owner 不匹配 → fail fast。

### P0-3 Local Runner CLI

目标：替代 `runtime-mock`，手动指定 session/run 可真实执行本机 stage，并能在 `start` 模式自动接管 running sessions。

交付：

- `python main.py node local-runner run <session_id> <run_id>`
- 支持 implement / code_review / test 三类 stage。
- 复用 submit artifact / receipt / advance。
- `python main.py node local-runner start` 自动发现、执行、advance、DecisionGate。
- active execution 去重，runner 重启后可恢复或等待 lease。

验收：

- 用 fake workers 跑通 implement → code_review → test → final。
- review `changes_requested` 能按 `on_reject` 回 implement。
- 重启 runner 后不会重复创建 execution。
- 同 role fallback worker 可被选中。

### P0-4 Loop Engine MVP

目标：把 next-action 状态计算服务端化。

交付：

- `agent_net/node/loop_engine.py`
- `GET /coordination/sessions/{id}/next-action`
- retry counter / max retry / DecisionGate。
- lease 过期处理。

验收：

- 当前 stage 无 execution → `start_execution`。
- execution running → `poll_execution`。
- artifact + approved receipt → `advance`。
- failed / changes_requested → retry 或 on_reject。
- retry 超限 → `create_decision_gate`。

### P0-5 Secretary Human Gateway

目标：让人工节点通过 Secretary 统一交互。

交付：

- DecisionGate 创建 helper。
- Secretary decision request / response API 或复用 owner decisions API 并补入口文档。
- OpenClaw 入口 prompt / MCP 使用说明。

验收：

- local-runner 遇到 `network_access` 或 `low_confidence` 能创建 pending decision。
- 人类 approve 后 Loop Engine 继续。
- 人类 aborted 后 session closure 为 aborted / failed。
- 历史 stage pending decision 不会阻塞当前 stage。
- OpenClaw / Dashboard 能展示 decision evidence 并提交结构化回复。

### P0-6 Docs + Quickstart

目标：让开发者能按文档复现。

交付：

- `.agentnexus/local-runner.yaml.example`
- `docs/quickstart-objective-loop.md`
- README 增加 v1.1 preview 路径。

验收：

- 新 clone 后按 quickstart 可跑 fake-worker objective loop。
- 真实 Claude/Codex CLI 未安装时，有明确报错和 fallback 指引。

### P0-7 L0-Ready 真实 Worker 验收

目标：证明 AgentNexus 已经具备本机分布式 Agent Team 能力，而不仅是 fake demo。

交付：

- `local-runner.yaml.example` 增加 `worker_did` 版真实 profile 模板。
- Codex / Claude / pytest / script profile 文档和 smoke tests。
- `agentnexus_json_v1` schema 文档与解析测试。
- Worker Registry reconcile：YAML profile 与 DID / owner binding 校验。
- OpenClaw / SDK objective 入口到 local-runner 的端到端说明。

验收：

- 同一 objective 由至少 3 个真实本机 Worker DID 协作完成。
- execution 记录中的 `worker_did` 均为真实 DID。
- 所有阶段产物可通过 `vault://` ref 串联。
- 至少覆盖一次失败回退或 DecisionGate 恢复。
- 后端测试包含 runner restart / duplicate active execution 防护。

---

## 18. 文档与产品定位同步

v1.1 后，README 和产品文档应统一使用以下表达：

> AgentNexus is a network-native objective loop for heterogeneous agents. Local, LAN, and relay-connected workers can collaborate under DID identity, capability-bound delegation, artifact-based handoff, receipt-gated progress, and human decision gates through a Secretary Agent.

中文：

> AgentNexus 是面向异构 Agent 的网络原生目标循环。它让本机、局域网和公网 Relay 上的 Worker，在 DID 身份、授权委托、产物交接、验收收据和秘书人机交互下协作完成目标。

这一定义不替代现有”通信基础设施与团队协作编排底座”，而是把 v1.1 的产品主线从基础设施能力收敛到用户可感知的目标闭环。

---

## 19. 开发前检查清单

- [ ] `ExecutionBackend` 命名已同步到代码、文档和测试。
- [ ] `objective_executions` migration 已实现且兼容旧数据库。
- [ ] result submit 幂等和 conflict 规则有测试。
- [ ] local-runner 不通过 shell 字符串拼接执行命令。
- [ ] local-runner timeout 能 kill 进程树。
- [ ] stdout/stderr 有大小限制。
- [ ] YAML 配置校验失败时 fail fast。
- [ ] YAML worker profile 必须绑定真实 `worker_did`，且 owner binding 校验通过。
- [ ] 真实 CLI worker 输出 `agentnexus_json_v1` contract。
- [ ] runner 重启不会重复创建 active execution。
- [ ] 同 role fallback worker 有测试。
- [ ] fake worker happy path 能跑通 final closure。
- [ ] 至少 3 个真实本机 Worker DID 能完成 L0-Ready smoke。
- [ ] review rejected path 能回退 implement。
- [ ] DecisionGate path 能暂停并恢复。
- [ ] 历史 stage pending decision 不会死锁当前 stage。
- [ ] README / quickstart 标明 v1.1 只交付 L0，本机以外是 v1.2+。

---

## 20. 设计评审记录

> 评审日期：2026-06-18 | 评审者：Claude（结合项目现状和愿景）

### 评审结论：有条件通过

设计方向正确，定位清晰——准确把握了 AgentNexus 的差异化价值（跨运行时、跨网络、DID 身份、产物收据驱动），并将 v1.0 已实现的 CoordinationSession / Artifact / Receipt / Playbook 能力收敛到可运行的 Objective Loop 中。三层网络半径（L0/L1/L2）的划分合理，非目标清单完整。

存在 **4 个阻塞性问题**需在 Phase 1 开发前明确，**5 个建议性问题**可在实现过程中迭代，**7 个细节问题**需关注。

---

### 阻塞性问题 (P)

| # | 问题 | 章节 | 回应 | 状态 |
|---|------|------|------|------|
| P1 | `RuntimeAdapter` 与已有 `PlatformAdapter`（`agent_net/adapters/base.py`）命名冲突、职责重叠。`openclaw_skill` 同时出现在 RuntimeAdapter 列表中，但 OpenClaw 已有 PlatformAdapter 实现。两套 adapter 抽象的关系未澄清。 | 4.3 | **决议**：明确两层关系——PlatformAdapter 负责”外部平台→AgentNexus 语义”（协议转换），RuntimeAdapter 负责”AgentNexus 语义→具体执行通道”（执行通道）。`openclaw_skill` 和 `webhook` 应复用已有 PlatformAdapter 做协议转换，再通过对应 RuntimeAdapter 做 stage 执行。实现时 RuntimeAdapter 建议命名为 `ExecutionBackend` 或 `StageRunner` 避免混淆。文档已新增分层关系图和说明。 | 已采纳 |
| P2 | Secretary 角色发生根本性变迁——Coding Coordination V1（已实现）中定位为 “Coordination Controller”，Objective Loop 中收缩为 “Human Gateway”。Controller 职责转移到 Loop Engine，但迁移路径未定义。现有 `POST /secretary/dispatch` 的定位变得模糊。 | 4.4 | **决议**：这不是推翻重来，而是职责分层。Loop Engine 接管 Controller 职责（状态机、stage 调度、retry/fallback），Secretary 保留 Intake + Human Gateway。现有 `dispatch` 作为 intake 入口保留；`advance()` 由 Loop Engine 调用（不替代）；Secretary 新增 DecisionGate 端点。文档新增 4.5 节说明架构迁移路径。 | 已采纳 |
| P3 | Objective Loop Engine 的部署位置未定义——在 Daemon 内？独立 sidecar？SDK 客户端侧？不同位置对 Lease 监控可靠性、多机状态一致性、崩溃恢复有根本性影响。 | 4.2, 11.2 | **决议**：目标架构中 Loop Engine 作为 **Daemon 内置 service**（类似现有 Playbook `advance()` 但更通用），确保状态权威来源在服务端。MVP 可先在客户端实现 `next-action` 做验证（如 11.2 节所述），但 Phase 2 必须服务端化。文档新增 4.5 节明确部署拓扑和客户端实现的限制。 | 已采纳 |
| P4 | Worker 选择输入包含 “cost / time / user preference”（第 9 节），但第 3 节非目标明确说”不在 v1.1 强制实现企业级 per-agent token”。没有 per-agent token 就无法做 per-agent 成本计量，cost-based selection 在 v1.1 不可实现。 | 3, 9 | **决议**：将 “cost / time” 从 v1.1 selection 输入降级为 “user-configured priority hint”（如 `preferred_worker`、`local_first`），不做动态成本排序。真正的 cost-based routing 推迟到 v1.5。第 3 节非目标新增明确说明，第 9 节已更新。 | 已采纳 |

---

### 建议性问题 (S)

| # | 问题 | 章节 | 回应 | 状态 |
|---|------|------|------|------|
| S1 | Local Runner 安全模型存在 prompt injection 风险——白名单只限制 command template，不限制 LLM 在 session 内的行为。”destructive / network / secret access 通过 DecisionGate 升级人类” 是被动的事后拦截。 | 6.1 | **决议**：在 6.1 节新增 “重要安全前提 — Sandbox 隔离”，明确 Worker 进程应在容器/sandbox 中运行（Docker/Podman/Windows Sandbox），workdir 应 mount 为只读或 copy-on-write，网络默认切断。Prompt 中注入 hard constraints 作为纵深防御。完整 sandbox 方案在 Phase 6 提供标准配置。 | 已采纳 |
| S2 | Artifact Transport 跨网络实现过于简略——只有一行 per 网络半径的表格，缺乏 artifact ref 格式定义、远程解析机制、不可解析时的 fallback 策略。 | 10 | **决议**：第 10 节已扩展，新增统一 ArtifactRef 协议定义（`vault://`、`artifact://`、`git://`、`https://`）及不可解析 ref 的处理流程（重试 1 次 → DecisionGate → 不自动跳过）。v1.1 只实现 `vault://`；其余远程格式后移到 v1.2+。 | 已采纳 |
| S3 | Playbook 与 Objective Loop 的映射关系缺失——设计提到 stage 策略和 `on_reject` 语义，但没有说明 Loop Engine 是替代 `advance()` 还是调用它，以及 PlaybookRun 是否仍为运行时状态权威来源。 | 7 | **决议**：新增 7.1 节 “与现有 Playbook / PlaybookRun 的映射”，以表格明确 8 个概念的对应关系：Stage 定义→Playbook.stages（不变）、Stage 推进→advance()（Loop Engine 调用，不替代）、人工决策点→新增 DecisionGate 表 等。 | 已采纳 |
| S4 | Prompt Contract 的脆弱性被低估——解析失败直接进入 blocked receipt 或 DecisionGate，考虑到 LLM 结构化输出有一定失败率，这个路径会被频繁触发。 | 6.3 | **决议**：在 6.3 节新增三阶段处理策略：(1) 自动重试 1 次（发送简化重试 prompt，不消耗 stage 重试配额）；(2) 重试仍失败才进 DecisionGate；(3) 如果 RuntimeAdapter 支持 function calling，优先使用该能力作为主路径。 | 已采纳 |
| S5 | 6 阶段实施计划范围过大——涵盖 Local Runner → Loop Engine → Secretary → LAN → Relay → Tauri 桌面，约为 Coding Coordination V1 工作量的 2–3 倍。 | 14 | **决议**：明确 v1.1 范围边界为 Phase 1–3（L0 本机 Objective Loop 闭环）。Phase 4（LAN）和 Phase 5（Relay）推后到 v1.2；Phase 6（产品化）推后到 v1.3+。先验证 L0 核心假设再扩展网络半径。各 phase 标题已标注目标版本。 | 已采纳 |

---

### 细节问题 (D)

| # | 问题 | 章节 | 回应 | 状态 |
|---|------|------|------|------|
| D1 | Objective 定义中 `controller_did` 和 `owner_did` 的关系未说明。Controller 是 Secretary 还是 Loop Engine？ | 4.1 | **已修复**：新增字段说明——`owner_did` 是目标归属者（拥有最终决策权），`controller_did` 是执行控制者（通常是 Secretary Agent DID）。当 Owner 自行控制时两者相同。 | 已采纳 |
| D2 | Loop Engine 循环伪代码中 “monitor lease / timeout / status” 没有说明同步/异步委托语义——Worker 执行期间是轮询还是事件驱动？ | 4.2 | **已修复**：标注为 “事件驱动 + 轮询 fallback（默认 5s 间隔）”。 | 已采纳 |
| D3 | L0 验收说 “不要求用户手动切到 Claude Code / Codex 调用 `fetch_inbox`”——但这只解决了 L0 人类体验，LAN/Relay Worker 的 inbox 模型仍需说明。 | 5.1 | **已修复**：新增备注——L0 场景下所有 Worker 与 Secretary 共享同一 Daemon，inbox 不是瓶颈；L1/L2 场景沿用现有 Relay 离线投递 + `fetch_inbox` 机制。 | 已采纳 |
| D4 | YAML 配置中 `command: claude` 硬编码 CLI 名称，不同环境可能不同（`claude` vs `claude-code` vs 全路径）。 | 6.2 | **已修复**：新增 “CLI 路径兼容性” 说明——`command` 支持简短名称或全路径，Runner 通过 `shutil.which()` 解析，失败时报错退出不静默 fallback。 | 已采纳 |
| D5 | DecisionGate 类型中 “review_conflict”（多 reviewer 结论冲突）在只有串行 review 的 v1.1 中不会触发——暗示了并行 review 能力，与第 7 节的串行 stage 策略矛盾。 | 8 | **已修复**：标注 `review_conflict` 为 **[v1.2+]**，v1.1 仅串行 review 故暂不触发。 | 已采纳 |
| D6 | RuntimeAdapter 接口全部返回 `dict`，与 Coding Coordination V1 中 dataclass response 风格不一致（`CoordinationSessionInfo`、`CoordinationArtifact` 等）。 | 4.3 | **已修复**：新增返回类型约定——v1.1 实现时应定义轻量 dataclass（如 `ExecutionHandle`、`ExecutionResult`），API 边界处序列化为 dict，保持项目风格一致。 | 已采纳 |
| D7 | 关联文档链接有效性——`design-sdk-orchestration.md`、`product.md` 是否真实存在？ | 头部 | **已验证**：所有关联文档均存在于 repo 中，无需修改。 | 已验证 |

---

### 与现有代码库的关键差距

| 设计文档要求 | 当前代码状态 | 差距评估 |
|---|---|---|
| Objective Loop Engine（状态机） | 不存在（`advance()` 仅做 receipt-gated 推进，无 retry/lease/DecisionGate） | 全新实现，但可复用现有 Playbook + advance() |
| ExecutionBackend | 不存在（有 `PlatformAdapter` 但层面不同） | 全新抽象层；v1.1 优先实现 `local_cli`，`local_service` 可选 |
| Local Runner sidecar | 不存在（有 `runtime-mock` 作为 demo 占位） | 替换 `runtime-mock` 为真实 CLI launcher |
| DecisionGate 系统 | `decision_requests` 表已存在于 storage.py，但未接入 Loop Engine | 扩展现有表 + 新增 Loop Engine 触发逻辑 |
| Worker selection + lease | 不存在（Secretary dispatch 仅按 capability 匹配） | 新增 presence/lease/network_scope 排序 |
| Secretary→Human Gateway 重构 | Secretary 当前是 Controller（`/secretary/dispatch`） | 保留 dispatch 作为 intake，新增 DecisionGate 端点 |
| 跨网络 artifact transport | `vault://` 格式已有；远程 `artifact://` 格式不存在 | 新增 ref 格式 + 远程 daemon fetch endpoint |

---

### 决议采纳清单

以下决议已更新到本文档对应章节：

- **P1** → 4.3 节新增 ExecutionBackend 与 PlatformAdapter 分层关系图；最终命名定为 `ExecutionBackend`
- **P2** → 新增 4.5 节 “架构迁移路径：Secretary 角色演进与 Loop Engine 部署”
- **P3** → 新增 4.5 节明确 Loop Engine 部署拓扑（Daemon 内置 service）+ MVP 客户端过渡方案
- **P4** → 第 3 节非目标新增 cost 限制说明；第 9 节将 cost/time 改为 user-configured priority hint
- **S1** → 6.1 节新增 “重要安全前提 — Sandbox 隔离” 段落
- **S2** → 第 10 节扩展为统一 ArtifactRef 格式 + 不可解析 ref 处理流程
- **S3** → 新增 7.1 节 “与现有 Playbook / PlaybookRun 的映射” 表格
- **S4** → 6.3 节新增三阶段 Prompt 解析失败处理策略
- **S5** → 第 14 节新增 v1.1 范围边界说明，Phase 4–6 标注为 v1.2/v1.3+
- **D1–D6** → 已在对应章节修复
- **D7** → 已验证所有关联文档存在

### 后续行动项

1. **Phase 1 开发启动前**：根据 v1.1 收缩后的范围（Phase 1–3）更新 `docs/project-status.md` 和 `docs/roadmap.md`。
2. **Phase 1 开发启动前**：补充 `.agentnexus/local-runner.yaml.example` 和 fake-worker quickstart。
3. **Phase 2 完成时**：Loop Engine 从客户端 MVP 迁移到 Daemon 内置 service，更新 4.5 节状态。
4. **v1.1 release 前**：对照本评审记录和第 19 节开发前检查清单逐项确认状态。
