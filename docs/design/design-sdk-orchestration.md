# AgentNexus 设计专题 — Orchestration SDK 改造

> 状态：活跃
> 目标：在不推翻现有 SDK 的前提下，快速补齐 Owner / Secretary / Team / Run / Worker Runtime API，让 SDK 适配当前“常驻秘书 + Agent 团队协作编排”主链路。
> 关联文档：
> - [design-secretary-orchestration.md](design-secretary-orchestration.md) — 常驻秘书与 Agent 团队协作编排
> - [design-v0.x.md](design-v0.x.md) — v0.8 SDK、Action Layer、Enclave SDK
> - [ADR-006 SDK 架构与 Daemon 通信协议](../adr/006-sdk-daemon-communication.md)
> - [ADR-007 Action Layer 协作协议](../adr/007-action-layer-protocol.md)

---

## 1. 背景与结论

现有 `agentnexus-sdk` 的核心定位是：

- 连接本地 Daemon
- 注册 Agent DID
- 收发消息
- 封装 Action Layer（`propose_task / claim_task / sync_resource / notify_state`）
- 封装 Discussion / Emergency / Enclave 基础 API

这套能力仍然有用，但它不再是 AgentNexus 当前产品主链路的完整表达。当前主链路已经变成：

```text
Owner DID
  -> Secretary Agent
  -> /secretary/dispatch
  -> Worker Registry + Presence
  -> Enclave + Playbook Run
  -> Worker Runtime
  -> Vault Artifact + Delivery Manifest
  -> Result Callback / Owner Takeover
```

因此 SDK 不应推倒重写，而应拆成两层：

| 层 | 处理方式 | 说明 |
|----|----------|------|
| Core SDK | 保留 | `connect / send / Action Layer / Discussion / Enclave / Vault / Push` 继续兼容 |
| Orchestration SDK | 新增 | 面向 Owner、Secretary、Team、Run、Worker Runtime 的高层 API |

---

## 2. 设计目标

### 2.1 Phase SDK-B1 — 快速可用

目标是让开发者不用手写 Daemon HTTP 请求，即可完成：

1. 注册 Owner DID。
2. 注册并绑定 Secretary 子 Agent。
3. 注册并绑定 Worker Agent。
4. 查询 Worker Registry / Presence。
5. 通过 Secretary 发起 Dispatch。
6. 查询 Intake / Run 状态。
7. Worker 收到 stage task 后读写 Vault 并 deliver。
8. Owner 可 abort 一个 session。

### 2.2 非目标

Phase SDK-B1 暂不做：

- 不做自动 CLI Launcher。
- 不做完整 Webhook HMAC Adapter SDK。
- 不做 Capability Token 全链路强制封装。
- 不改现有 `propose_task / claim_task / notify_state` 的兼容行为。
- 不把 SDK 变成独立编排引擎；流程状态仍以 Daemon 的 Enclave / Playbook / StageExecution 为准。

---

## 3. 包结构调整

在 `agentnexus-sdk/src/agentnexus/` 下新增：

```text
agentnexus/
  owner.py        # Owner DID、绑定、Owner inbox/workers
  team.py         # Worker Registry / Presence / worker_type
  secretary.py    # Secretary 注册、Intake、Dispatch、Confirm、Abort
  runs.py         # RunStatus / IntakeStatus 查询封装
  worker.py       # WorkerRuntime、StageContext、deliver()
  orchestration.py# 聚合 facade，可选
```

现有文件保留：

```text
client.py       # Core AgentNexusClient
actions.py      # Action Layer，需小幅扩展 StateNotify
enclave.py      # Enclave/Vault API，需小幅补 actor_did/owner_did 语义
sync.py         # 同步 wrapper，覆盖 Owner / Team / Secretary / Run / Enclave 主链路
```

`AgentNexusClient.__init__` 初始化高层 facade：

```python
self.owner = OwnerClient(self)
self.team = TeamClient(self)
self.secretary = SecretaryClient(self)
self.runs = RunClient(self)
self.worker = WorkerRuntime(self)
```

---

## 4. 通用 HTTP 封装

当前 SDK 多处手写 `self._session.get/post/...`，新增 Orchestration API 前应先补一个内部 `_request()`，避免重复鉴权和错误处理。

```python
async def _request(
    self,
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    auth: bool = True,
) -> dict:
    ...
```

规则：

- `path` 统一传 `"/owner/register"` 这种相对路径。
- `auth=True` 时自动加 `Authorization: Bearer <token>`。
- 401 -> `AuthenticationError`。
- 403 -> `PermissionError` 或新增 `AuthorizationError`。
- 404 -> `AgentNotFoundError` / `KeyError` 由调用方按语义转换。
- 非 2xx -> `AgentNexusError(await resp.text())`。

---

## 5. Owner SDK

### 5.1 目标

Owner SDK 负责个人主 DID 和子 Agent 绑定关系。

### 5.2 API

```python
owner = await nexus.owner.register("Kevin")
await nexus.owner.bind(owner.did, worker_did)
await nexus.owner.unbind(owner.did, worker_did)
agents = await nexus.owner.list_agents(owner.did)
profile = await nexus.owner.get_profile(owner.did)
```

### 5.3 Endpoint 映射

| SDK | Daemon |
|-----|--------|
| `owner.register(name)` | `POST /owner/register` |
| `owner.bind(owner_did, agent_did)` | `POST /owner/bind` |
| `owner.unbind(owner_did, agent_did)` | `DELETE /owner/unbind` |
| `owner.list_agents(owner_did)` | `GET /owner/agents/{owner_did}?actor_did=<owner_did>` |
| `owner.get_profile(owner_did)` | `GET /owner/profile/{owner_did}` |

### 5.4 数据模型

```python
@dataclass
class OwnerInfo:
    did: str
    public_key_hex: str
    profile: dict

@dataclass
class OwnedAgent:
    did: str
    profile: dict
    last_seen: float
```

---

## 6. Team SDK

### 6.1 目标

Team SDK 负责 Worker Registry、Presence 和 worker_type。

### 6.2 API

```python
workers = await nexus.team.list_workers(owner_did)
workers = await nexus.team.list_workers(owner_did, role="developer", presence="available")
presence = await nexus.team.get_presence(worker_did)
await nexus.team.set_worker_type(worker_did, "interactive_cli", actor_did=owner_did)
await nexus.team.set_blocked(worker_did, True, actor_did=owner_did, reason="quota exceeded")
```

### 6.3 Endpoint 映射

| SDK | Daemon |
|-----|--------|
| `team.list_workers(owner_did)` | `GET /owner/workers/v2/{owner_did}` |
| `team.get_presence(did)` | `GET /workers/{did}/presence` |
| `team.set_blocked(...)` | `PATCH /workers/{did}/blocked` |
| `team.set_worker_type(...)` | `PATCH /agents/{did}/worker-type` |

### 6.4 数据模型

```python
@dataclass
class WorkerInfo:
    did: str
    owner_did: str
    worker_type: str
    profile_type: str
    capabilities: list[str]
    tags: list[str]
    presence: str
    presence_source: str
    presence_ttl: float | None
    active_run_id: str | None
    active_stage: str | None
    load: int
```

---

## 7. Secretary SDK

### 7.1 目标

Secretary SDK 是新的主入口封装。它不替代 Daemon 编排，只负责把外部请求转成标准 Intake / Dispatch。

### 7.2 注册 Secretary

当前 Daemon 没有专门的 HTTP `register_secretary` 端点，但可以用现有端点组合实现：

```python
secretary = await nexus.secretary.register(owner_did, name="Secretary")
```

内部步骤：

1. `POST /agents/register`
   - `type="secretary"`
   - `capabilities=["orchestrate", "intake", "dispatch"]`
   - `worker_type="resident"`
2. `POST /owner/bind`
   - `owner_did`
   - `agent_did = secretary.did`
3. 如果第 2 步绑定失败，SDK 必须 best-effort 调用 `DELETE /agents/{secretary_did}?actor_did=<secretary_did>` 回滚刚注册的 Secretary，避免留下未绑定孤儿 Agent。

> 后续如果 Daemon 增加 `POST /secretary/register`，SDK 内部实现可切换，外部 API 不变。

### 7.3 Intake API

```python
intake = await nexus.secretary.create_intake(
    session_id="sess_001",
    owner_did=owner_did,
    actor_did=secretary_did,
    objective="完成登录模块设计评审并实现",
    required_roles=["architect", "developer", "reviewer"],
    source={"channel": "webhook", "message_ref": "msg_123"},
)

intake = await nexus.secretary.get_intake("sess_001", actor_did=secretary_did)
intakes = await nexus.secretary.list_intakes(owner_did, actor_did=owner_did, status="running")
```

### 7.4 Dispatch API

```python
run = await nexus.secretary.dispatch(
    session_id="sess_001",
    owner_did=owner_did,
    actor_did=secretary_did,
    objective="完成登录模块设计评审并实现",
    required_roles=["architect", "developer", "reviewer"],
    entry_mode="owner_pre_authorized",
    source={"channel": "openclaw", "message_ref": "msg_123"},
)
```

返回：

```python
@dataclass
class DispatchResult:
    status: str
    session_id: str
    run_id: str | None
    enclave_id: str | None
    playbook_name: str | None
    current_stage: str | None
    selected_workers: dict[str, str]
    missing_roles: list[str]
```

### 7.5 Owner 确认与接管

```python
await nexus.secretary.confirm(session_id, owner_did=owner_did, actor_did=owner_did)
await nexus.secretary.abort(session_id, actor_did=owner_did, reason="user cancelled")
```

Endpoint 映射：

| SDK | Daemon |
|-----|--------|
| `secretary.create_intake(...)` | `POST /secretary/intake` |
| `secretary.get_intake(...)` | `GET /secretary/intake/{session_id}` |
| `secretary.list_intakes(...)` | `GET /secretary/intakes/{owner_did}` |
| `secretary.dispatch(...)` | `POST /secretary/dispatch` |
| `secretary.confirm(...)` | `POST /secretary/intake/{session_id}/confirm` |
| `secretary.abort(...)` | `POST /secretary/intake/{session_id}/abort` |

---

## 8. Run SDK

### 8.1 目标

Run SDK 负责统一查询 Playbook Run、Stage 状态和 Intake 状态。

### 8.2 API

```python
intake = await nexus.runs.get_intake(session_id, actor_did=secretary_did)
status = await nexus.runs.get_status(enclave_id, run_id)
await nexus.runs.abort(session_id, actor_did=owner_did, reason="wrong requirement")
```

### 8.3 数据模型

```python
@dataclass
class IntakeInfo:
    session_id: str
    owner_did: str
    actor_did: str
    status: str
    objective: str
    required_roles: list[str]
    selected_workers: dict[str, str]
    run_id: str | None

@dataclass
class RunStatus:
    run_id: str
    enclave_id: str
    playbook_name: str
    current_stage: str
    status: str
    stages: dict
```

### 8.4 Endpoint 映射

| SDK | Daemon |
|-----|--------|
| `runs.get_intake(session_id, actor_did)` | `GET /secretary/intake/{session_id}` |
| `runs.get_status(enclave_id, run_id)` | `GET /enclaves/{enclave_id}/runs/{run_id}` |
| `runs.abort(...)` | `POST /secretary/intake/{session_id}/abort` |

注意：当前 Daemon 没有按 `run_id` 直接查询的全局端点，因此 SDK 必须保存或传入 `enclave_id`。`SecretaryClient.dispatch()` 返回值必须保留 `enclave_id`。

不新增 `runs.get_status(session_id=...)` 的原因：当前 `secretary_intakes` 不持久化 `enclave_id`，仅有 `run_id` 不足以调用现有 Enclave Run 查询端点。Phase SDK-B1 采用 `DispatchResult.enclave_id + run_id` 作为稳定查询句柄；如后续 Intake 表补 `enclave_id`，可再增加 session-based 便捷查询。

---

## 9. Worker Runtime SDK

### 9.1 目标

Worker Runtime 是 SDK 改造的关键。Worker 不应该手写消息解析、Vault path、`notify_state` payload。SDK 应提供 `StageContext`。

### 9.2 API

```python
@nexus.worker.on_stage(role="developer")
async def implement(ctx: StageContext):
    req = await ctx.vault.get("requirements/intake.json")

    patch = generate_patch(req.value)

    await ctx.deliver(
        kind="code_diff",
        key="impl/diff.patch",
        value=patch,
        summary="完成登录模块实现",
    )
```

### 9.3 StageContext

```python
@dataclass
class StageContext:
    task_id: str
    run_id: str
    enclave_id: str
    stage_name: str
    role: str
    from_did: str
    assigned_did: str
    context_snapshot: dict
    vault: VaultProxy
```

### 9.4 task_propose 解析

Worker Runtime 从现有 `task_propose` 消息中解析：

```json
{
  "task_id": "task_xxx",
  "enclave_id": "enc_xxx",
  "run_id": "run_xxx",
  "stage_name": "implement",
  "role": "developer",
  "context_snapshot": { ... }
}
```

如果某些字段缺失：

- `task_id` 缺失：拒绝处理，交给普通 `on_task_propose`。
- `enclave_id / run_id / stage_name` 缺失：仍触发旧 Action Layer callback，不构造 `StageContext`。

这样保持旧 Action Layer 兼容。

### 9.5 deliver()

```python
await ctx.deliver(
    kind="design_doc",
    key="design/spec.md",
    value=markdown,
    summary="完成登录模块设计",
    status="completed",
)
```

内部步骤：

1. 如果传入 `value`，调用 `VaultProxy.put(key, value, message=summary)`。
2. 构造 Artifact Ref：

```python
artifact_ref = {"enclave_id": ctx.enclave_id, "key": key}
```

3. 调用扩展后的 `notify_state()`：

```python
await nexus.notify_state(
    to_did=ctx.from_did,
    task_id=ctx.task_id,
    status=status,
    output_ref=artifact_ref,
)
```

### 9.6 reject()

```python
await ctx.reject(reason="测试未通过，需要补充边界用例")
```

等价于：

```python
await nexus.notify_state(
    to_did=ctx.from_did,
    task_id=ctx.task_id,
    status="rejected",
    reason=reason,
)
```

---

## 10. Action Layer 兼容扩展

现有 `notify_state()` 参数不足，无法传 `output_ref / reason / context`。Phase SDK-B1 必须扩展，但保持向后兼容。

### 10.1 新签名

```python
async def notify_state(
    self,
    to_did: str,
    status: str,
    task_id: str | None = None,
    progress: float | None = None,
    error: str | None = None,
    output_ref: dict | str | None = None,
    reason: str | None = None,
    context: dict | None = None,
) -> None:
    ...
```

### 10.2 StateNotify 模型

`StateNotify.to_content()` 输出：

```json
{
  "task_id": "task_xxx",
  "status": "completed",
  "progress": 1.0,
  "output_ref": {"enclave_id": "enc_xxx", "key": "design/spec.md"},
  "reason": null,
  "context": null
}
```

兼容规则：

- 旧调用不传 `output_ref` 时输出不变或仅多出 null 字段；Daemon 应可忽略。
- `rejected` 状态优先使用 `reason`。
- `completed` 状态优先使用 `output_ref`。

---

## 11. Enclave SDK 修正

现有 `EnclaveManager.create()` 默认 `owner_did = self.agent_info.did`，这不符合 Secretary 代表 Owner 创建 Enclave 的新语义。

### 11.1 新签名

```python
await nexus.enclaves.create(
    name="login-feature",
    owner_did=owner_did,
    actor_did=secretary_did,
    members={...},
    vault_backend="local",
)
```

兼容规则：

- `owner_did` 默认仍为 `self.agent_info.did`。
- `actor_did` 默认仍为 `self.agent_info.did`。
- Secretary SDK 调用时必须显式传 `owner_did + actor_did`。

### 11.2 VaultDelete 修正

当前 Daemon 删除 Vault 需要 body：

```json
{"author_did": "<did>"}
```

SDK `VaultProxy.delete()` 已按 body 传 `author_did`，保留。

---

## 12. 快速操作示例

### 12.1 Owner + Worker + Secretary

```python
import agentnexus

nexus = await agentnexus.connect("bootstrap", caps=["Admin"])

owner = await nexus.owner.register("Kevin")

architect = await agentnexus.connect("Architect", caps=["architect", "design"])
developer = await agentnexus.connect("Developer", caps=["developer", "code"])
reviewer = await agentnexus.connect("Reviewer", caps=["reviewer", "review"])

await nexus.owner.bind(owner.did, architect.agent_info.did)
await nexus.owner.bind(owner.did, developer.agent_info.did)
await nexus.owner.bind(owner.did, reviewer.agent_info.did)

secretary = await nexus.secretary.register(owner.did, name="Secretary")
```

### 12.2 Dispatch

```python
result = await nexus.secretary.dispatch(
    session_id="sess_login_001",
    owner_did=owner.did,
    actor_did=secretary.did,
    objective="完成登录模块设计、实现、测试和评审",
    required_roles=["architect", "developer", "reviewer"],
    entry_mode="owner_pre_authorized",
    source={"channel": "webhook", "message_ref": "msg_001"},
)

print(result.run_id, result.enclave_id, result.current_stage)
```

### 12.3 Worker

```python
worker = await agentnexus.connect(did=developer.agent_info.did)

@worker.worker.on_stage(role="developer")
async def handle(ctx):
    spec = await ctx.vault.get("design/spec.md")
    patch = implement(spec.value)
    await ctx.deliver(
        kind="code_diff",
        key="impl/diff.patch",
        value=patch,
        summary="完成登录模块实现",
    )
```

### 12.4 Owner Abort

```python
await nexus.secretary.abort(
    session_id="sess_login_001",
    actor_did=owner.did,
    reason="需求变更，终止本次 run",
)
```

---

## 13. 实现顺序

Phase SDK-B1 按以下顺序实现：

1. `AgentNexusClient._request()` 内部通用 HTTP helper。
2. `owner.py` + `OwnerClient` + 数据模型。
3. `team.py` + `TeamClient` + WorkerInfo。
4. `secretary.py` + `SecretaryClient` + DispatchResult / IntakeInfo。
5. `runs.py` + `RunClient`。
6. 扩展 `StateNotify` 和 `AgentNexusClient.notify_state()` 支持 `output_ref / reason / context`。
7. `worker.py` + `WorkerRuntime` + `StageContext.deliver/reject`。
8. 修正 `EnclaveManager.create(owner_did, actor_did)`。
9. 更新 `__init__.py` 导出和 `agentnexus-sdk/README.md` 示例。
10. 同步 wrapper 暴露 Owner / Team / Secretary / Runs / Enclaves 主链路。

---

## 14. 测试计划

### 14.1 单元测试

| 测试 | 目标 |
|------|------|
| `test_owner_client_register_bind` | Owner 注册和绑定 payload 正确 |
| `test_team_list_workers_v2` | role/presence 参数正确传递 |
| `test_secretary_register_composes_agent_and_bind` | Secretary 注册走 `/agents/register` + `/owner/bind` |
| `test_secretary_dispatch_payload` | Dispatch payload 完整，返回 DispatchResult |
| `test_notify_state_output_ref` | `output_ref` 写入 state_notify content |
| `test_worker_runtime_builds_stage_context` | task_propose 可构造 StageContext |
| `test_stage_context_deliver` | deliver 先写 Vault 再 notify completed |

### 14.2 集成测试

| 测试 | 目标 |
|------|------|
| `test_sdk_secretary_dispatch_e2e` | Owner + Secretary + Worker + dispatch 跑通 |
| `test_sdk_worker_deliver_advances_run` | Worker deliver 后 Playbook 推进 |
| `test_sdk_owner_abort` | SDK abort 调用真实端点 |

### 14.3 兼容测试

| 测试 | 目标 |
|------|------|
| `test_legacy_send_still_works` | 旧 send 不受影响 |
| `test_legacy_propose_task_still_works` | 旧 Action Layer 不受影响 |
| `test_legacy_notify_state_without_output_ref` | 旧 notify_state 参数仍可用 |

---

## 15. Daemon 前置修复

SDK-B1 实现前，Daemon 侧至少应先修复以下代码评审问题，否则 SDK 集成测试会暴露运行时失败：

1. `PlaybookEngine.on_stage_completed()` 中 `current_stage` 未定义就被使用。
2. `/secretary/dispatch` 成功路径必须先 `create_intake()` 再 `update_intake()`，且 `update_intake()` 应检查 `rowcount`。
3. `/secretary/intake/{session_id}/abort` 需要正确 import `get_playbook_run`。
4. Stage 完成后 `stage_executions.output_ref` 应更新为 run-scoped manifest ref，而不是原始 artifact ref。
5. Worker 管理端点需要校验 actor 是该 worker 的 owner。

这些不是 SDK 自身问题，但会影响 SDK 端到端验收。

当前代码评审后已确认 1、2、3、5 已在 Daemon 侧修复；4 仍需在端到端联调时确认 Manifest Ref 语义。

补充确认：Manifest Ref 语义已闭环。Worker 原始 `output_ref` 保留在 Stage Delivery Manifest 中；`stage_executions.output_ref` 指向 run-scoped stage manifest artifact ref；Final Delivery Manifest 从 stage manifest 汇总真实交付产物。

---

## 16. 评审标准

SDK-B1 可进入开发完成态的条件：

- 新 API 不破坏现有 `connect / send / Action Layer / Discussion / Enclave`。
- README 和 SDK README 的主示例改为 Owner + Secretary + Dispatch。
- Worker 侧不需要手写 `task_propose` JSON 解析即可处理 stage。
- `deliver()` 默认产出 `{enclave_id, key}` Artifact Ref。
- 所有 Secretary API 都显式要求 `owner_did / actor_did`。
- 至少一个 SDK 集成测试跑通完整链路：dispatch -> worker deliver -> run status。

---

## 17. 设计评审记录（2026-04-27）

> 评审者：评审 Agent

### 评审结论：通过，可进入开发

设计方向正确：Core SDK + Orchestration SDK 分层保留旧 API 兼容，Worker Runtime 的 StageContext 是最有价值的抽象。API 与 Daemon 端点映射清晰，兼容性考虑充分。

### 建议性问题

| # | 问题 | 严重性 | 处理决定 | 状态 |
|---|------|--------|----------|------|
| S1 | §6.3 Team SDK 的 4 个 Daemon 端点（`/owner/workers/v2`、`/workers/{did}/presence`、`/workers/{did}/blocked`、`/agents/{did}/worker-type`）尚未在 Daemon 侧实现，SDK-B1 开发前需先补 | 🟡 | 接受 | ✅ 已实现并对齐 SDK |
| S2 | §9.4 task_propose 解析依赖 `role` 和 `context_snapshot`，但 PlaybookEngine 发送的 content 缺少这两个字段 | 🟡 | 接受 | ✅ PlaybookEngine 已补 `role/context_snapshot` |
| S3 | §7.2 Secretary 注册两步组合（register + bind）中间失败会留孤儿 Agent，建议 SDK 内部做 rollback | 🟢 | 接受 | ✅ SDK 绑定失败会调用 `DELETE /agents/{did}` 回滚 |
| S4 | §8 `runs.get_status` 需要 `enclave_id` 但 `runs.abort` 不需要，参数风格不一致。建议支持通过 `session_id` 查询或在 DispatchResult 中保存 enclave_id | 🟢 | 部分接受 | ✅ 已采用 `DispatchResult.enclave_id`；暂不接受 session 查询，原因是 Intake 当前不持久化 `enclave_id` |
| S5 | §10.2 `output_ref` 可能是 dict 或 str，Daemon 侧 `_intercept_playbook_state` 需兼容两种类型 | 🟢 | 接受 | ✅ PlaybookEngine 已兼容 dict/string 并序列化存储 |

---

## 18. 代码评审记录（2026-04-27）

> 评审者：评审 Agent

### 评审结论：通过

SDK 实现与设计文档高度一致。5 个新模块 + StateNotify 扩展 + _request() helper + Worker Runtime StageContext 全部到位。Secretary 注册 rollback 已实现。

### 实现覆盖

| 设计项 | 实现文件 | 状态 |
|--------|---------|------|
| §4 _request() | client.py | ✅ |
| §5 Owner SDK | owner.py + OwnerClient | ✅ |
| §6 Team SDK | team.py + TeamClient + WorkerInfo | ✅ |
| §7 Secretary SDK | secretary.py + SecretaryClient + DispatchResult + IntakeInfo | ✅ |
| §8 Run SDK | runs.py + RunClient + RunStatus | ✅ |
| §9 Worker Runtime | worker.py + WorkerRuntime + StageContext + deliver/reject | ✅ |
| §10 StateNotify 扩展 | actions.py（output_ref/reason/context） | ✅ |
| §11 EnclaveManager 修正 | enclave.py（owner_did + actor_did） | ✅ |
| §13 __init__.py 导出 | __init__.py | ✅ |
| §15 Daemon 前置修复 | agents.py（4 个 Team 端点） | ✅ |

### 建议性问题

| # | 问题 | 严重性 | 处理决定 | 状态 |
|---|------|--------|----------|------|
| S1 | `team.set_blocked/set_worker_type` 用 PATCH + query params，Daemon 端点可能期望 body | 🟡 | 不接受为代码问题 | ✅ Daemon 端点使用 FastAPI scalar params，query params 是正确契约；已补 SDK 测试固定该行为 |
| S2 | Worker Runtime role fallback 到 stage_name，语义不精确 | 🟢 | 部分接受 | ✅ PlaybookEngine 已发送显式 `role`；SDK 保留 `stage_name` fallback 仅用于旧消息兼容，并已加注释 |
| S3 | `__version__` 仍为 0.9.6，应更新 | 🟢 | 接受 | ✅ SDK 包版本与 `agentnexus.__version__` 更新为 `1.0.0` |
| S4 | `test_run_client_abort` 偶发 AttributeError，疑似 import 缓存 | 🟢 | 暂不接受为可复现问题 | ✅ 当前测试稳定通过；`FakeClient` 显式挂载 `RunClient`，保留监控 |
