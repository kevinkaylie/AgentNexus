# Dashboard / Setup v1.0 收口设计

> 状态：活跃设计
> 范围：v1.0.0 团队协作开发者预览
> 关联：R-1004 Web Dashboard 基础入口、R-1005 Agent 接入向导、Secretary Phase B
> 旧基础设计：`design-v1.0.md` §1.0-01 / §1.0-03。本文覆盖 v1.0.0 收口主链路，开发优先以本文为准。

## 1. 目标

把现有 Web 前端从“基础管理页面”升级为可完成一次团队协作闭环的产品入口：

```text
设置 token
  -> 创建 Owner
  -> 注册 Secretary
  -> 注册/绑定 Worker
  -> 查看 Worker presence
  -> 发起 Dispatch
  -> 查看 Intake / Enclave / Run / Stage / Manifest 状态
```

v1.0.0 不追求完整产品化 Dashboard，不做 Tauri、通知、CLI Launcher、多人并行评审、自动超时重分配、per-agent token 或签名交付包。

## 2. 页面范围

| 页面 | v1.0.0 必交 | 说明 |
|------|-------------|------|
| Setup | ✅ | 完成 Owner + Secretary + Worker + Dispatch 首次闭环 |
| Dashboard | ✅ | 展示核心状态和当前 Run 概览 |
| Agents | ✅ | 展示 Owner 下子 Agent、worker_type、presence、capabilities |
| Runs | ✅ | 可作为 Enclaves 页面的一部分，展示 intake/run/stage/manifest |
| Messages | 🟡 基础 | 展示 Owner 聚合消息即可 |
| TrustNetwork | ⬚ 后移 | v1.0.0 可保留占位或只展示基础表格 |

## 3. Setup 闭环设计

### 3.1 步骤

| Step | 名称 | 操作 | 成功条件 |
|------|------|------|----------|
| 0 | 设置 Token | 输入 daemon token，写入 localStorage | 后续 API 请求带 `Authorization: Bearer <token>` |
| 1 | 创建 / 选择 Owner | 调 `POST /owner/register` 或读取已有 `owner_did` | localStorage 有 `owner_did` |
| 2 | 注册 Secretary | 兼容当前 `POST /agents/register` + `POST /owner/bind` 链路；若后端后续提供专用端点，再收敛到 `POST /owner/secretary` | localStorage 有 `secretary_did`，且绑定到 Owner |
| 3 | 注册 / 绑定 Worker | 生成 MCP / SDK / CLI Worker 命令，或选择已有 Agent 绑定 | 至少一个 Worker 绑定到 Owner |
| 4 | 配置团队角色 | 为 Worker 设置 `worker_type`，确认 capabilities / profile_type 覆盖 required_roles | `GET /owner/workers/v2/{owner_did}` 返回可用 Worker |
| 5 | 发起 Dispatch | 输入 objective、required_roles、preferred_playbook，可选 source | `POST /secretary/dispatch` 返回 `run_id` 和 `enclave_id` |
| 6 | 验证结果 | 跳转 Run 视图 | 能看到 intake、selected_workers、current_stage |

### 3.2 Dispatch 表单

字段：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `session_id` | string | 否 | `sess_<timestamp>` | 用户可编辑，默认自动生成 |
| `owner_did` | string | 是 | localStorage owner | 不允许手填成其他 Owner |
| `actor_did` | string | 是 | secretary_did | 默认由 Secretary 代表 Owner dispatch |
| `objective` | textarea | 是 | 无 | 任务目标 |
| `required_roles` | string[] | 是 | `["developer"]` | UI 用 chips 或 checkbox |
| `preferred_playbook` | string | 否 | 空 | 为空时使用默认 playbook |
| `entry_mode` | enum | 是 | `owner_pre_authorized` | v1.0.0 默认预授权 |
| `source.channel` | string | 否 | `web` | 标记来自 Dashboard |
| `source.message_ref` | string | 否 | 空 | 可为空 |

请求示例：

```json
{
  "session_id": "sess_1777056000",
  "owner_did": "did:agentnexus:owner",
  "actor_did": "did:agentnexus:secretary",
  "objective": "实现并评审登录模块",
  "required_roles": ["developer", "reviewer"],
  "preferred_playbook": "",
  "entry_mode": "owner_pre_authorized",
  "source": {
    "channel": "web",
    "message_ref": ""
  }
}
```

成功后保存：

```text
last_session_id
last_enclave_id
last_run_id
```

并跳转 `/enclaves/:enclave_id/runs/:run_id` 或当前 Enclaves 页面中的 Run 详情区域。

## 4. Dashboard / Run 视图设计

### 4.1 Dashboard 首页

首页只做状态摘要，不做复杂操作：

| 模块 | 数据 | API |
|------|------|-----|
| Agents | Owner 子 Agent 数 | `GET /owner/agents/{owner_did}?actor_did=<owner_did>` |
| Workers | Worker presence 汇总 | `GET /owner/workers/v2/{owner_did}?actor_did=<owner_did>` |
| Intakes | 最近 intake 状态 | `GET /secretary/intakes/{owner_did}?actor_did=<owner_did>` |
| Runs | 活跃 run 数、当前 stage | `GET /enclaves?actor_did=<owner_did>` + `GET /enclaves/{id}/runs?actor_did=<owner_did>` |
| Messages | 未读消息数 | `GET /owner/messages/stats?owner_did=<owner_did>&actor_did=<owner_did>` |

### 4.2 Run 详情

Run 详情必须展示：

| 区块 | 字段 |
|------|------|
| Intake | `session_id`, `status`, `objective`, `selected_workers`, `source_channel`, `run_id` |
| Enclave | `enclave_id`, `name`, `members` |
| Run | `run_id`, `status`, `playbook_name`, `current_stage`, `started_at`, `completed_at` |
| Stages | `stage_name`, `role`, `assigned_did`, `status`, `retry_count`, `task_id`, `output_ref`, `started_at`, `completed_at` |
| Manifest | stage manifest ref、final manifest ref、summary、missing_outputs |
| Context Budget | `estimated_context_tokens_planned`, `estimated_context_tokens_actual`, `policy` |
| Failure | `blocked`, `rejected`, `failed`, `aborted` 的原因和可选 Owner 操作 |

v1.0.0 必须可见的状态：

```text
intake: pending / awaiting_owner_confirm / running / blocked / completed / failed / aborted
run: running / completed / failed / aborted
stage: pending / active / completed / rejected / blocked / timeout
```

### 4.3 Manifest 展示

UI 不直接假设产物是文件路径。`output_ref` / `manifest_ref` 按 Artifact Ref 展示：

```json
{
  "enclave_id": "enc_x",
  "key": "manifests/run_x/developer"
}
```

若 ref 是字符串，按兼容模式展示原文；若是对象，则提供“查看 Vault 内容”入口，调用：

```text
GET /enclaves/{enclave_id}/vault/{key}?actor_did=<owner_did>
```

## 5. 前端 API 契约

### 5.1 actor_did 规则

前端 `api/client.ts` 必须集中处理 token，但不能自动猜所有 actor。调用方按场景明确传入：

| 场景 | actor_did |
|------|-----------|
| Owner 管理子 Agent、查看聚合消息 | `owner_did` |
| Secretary dispatch / create intake | `secretary_did` |
| Dashboard list intakes / get owner-level intake state | `owner_did` |
| Enclave / Vault / Run 查询 | 默认 `owner_did`，因为 Owner 是 Enclave member |
| Worker presence / blocked / worker_type | 默认 `owner_did` |

本轮开发要求：所有需要 `actor_did` 的 API helper 显式参数化，不在 helper 内隐式读取 localStorage。

示例：

```ts
listWorkers(ownerDid: string, actorDid: string)
listIntakes(ownerDid: string, actorDid: string)
dispatch(req: DispatchRequest)
getRun(enclaveId: string, runId: string, actorDid: string)
getVault(enclaveId: string, key: string, actorDid: string)
```

### 5.2 必补 API helper

| Helper | HTTP |
|--------|------|
| `registerSecretary(ownerDid, name)` | 当前用 `POST /agents/register` + `POST /owner/bind`；后续可收敛为 `POST /owner/secretary` |
| `listWorkers(ownerDid, actorDid)` | `GET /owner/workers/v2/{ownerDid}?actor_did=<actorDid>` |
| `setWorkerType(did, workerType, actorDid)` | `PATCH /agents/{did}/worker-type`，body 携带 `actor_did` |
| `listIntakes(ownerDid, actorDid)` | `GET /secretary/intakes/{ownerDid}?actor_did=<actorDid>`；Dashboard 调用传 `owner_did` |
| `dispatchSecretary(req)` | `POST /secretary/dispatch` |
| `abortIntake(sessionId, actorDid, reason)` | `POST /secretary/intake/{sessionId}/abort`，body 携带 `actor_did` |
| `getRun(enclaveId, runId, actorDid)` | `GET /enclaves/{enclaveId}/runs/{runId}?actor_did=<actorDid>` |
| `getVaultEntry(enclaveId, key, actorDid)` | `GET /enclaves/{enclaveId}/vault/{key}?actor_did=<actorDid>` |

## 6. 验收标准

### 6.1 UI 手工验收

1. 输入 daemon token。
2. 创建 Owner。
3. 注册 Secretary，并确认 `secretary_did` 绑定到 Owner。
4. 注册或选择至少两个 Worker：developer、reviewer。
5. 设置 Worker `worker_type`，确认 presence 显示。
6. 在 Setup 发起 dispatch。
7. Dashboard 显示 intake running、selected_workers、enclave_id、run_id、current_stage。
8. Worker 完成 stage 后，Run 详情能看到 stage manifest。
9. Run 完成后，Run 详情能看到 final manifest。
10. 触发 rejected 或 blocked 时，UI 能显示状态和原因；Owner 可 abort。

### 6.2 自动或半自动验收

新增一个脚本或测试说明：

```text
SDK/CLI/Webhook -> dispatch -> stage execution -> delivery manifest -> dashboard visible
```

v1.0.0 发布前至少保留一条可重复执行的手工脚本；若时间允许，补 Playwright 或 API 级 smoke test。

## 7. 非目标

- 不实现 Tauri 壳。
- 不实现系统托盘通知。
- 不实现 CLI Launcher 自动拉起。
- 不实现 `resume` / `skip`。
- 不实现 trust score 选人排序。
- 不实现 Strict JCS 或签名交付包。
- 不重做完整设计系统；沿用现有 Vue 3 + PrimeVue。

## 8. 开发顺序

1. 修正 `web/src/api/client.ts` 的 actor_did helper 契约。
2. 改 Setup：Owner / Secretary / Worker / Dispatch 六步闭环。
3. 改 Agents：显示 worker_type、presence、owner_did、capabilities。
4. 改 Enclaves 或新增 Run 详情：展示 intake/run/stage/manifest/context_budget。
5. 改 Dashboard：首页聚合 intakes、workers、active runs。
6. 构建前端并同步 `agent_net/node/static/`。
7. 补手工验收脚本与 README/quickstart 链接。

## 9. 代码评审记录（2026-04-30）

> 评审者：评审 Agent
> 测试结果：相关回归 `56 passed`；全量 `549 passed, 8 skipped, 1 warning`；`npm run build` 通过。

### 评审结论：暂不通过，需修复后复评

当前实现已构建出 Dashboard / Setup 页面和静态产物，但主链路还不能判定为可交付。阻塞问题集中在前端 `actor_did` 契约与后端不一致，以及默认 Playbook 多角色 stage 链缺失。

| 编号 | 问题 | 严重级别 | 处理要求 |
|------|------|----------|----------|
| S1 | `web/src/api/client.ts` 的 `listOwnedAgents / fetchOwnerInbox / fetchOwnerMessages / fetchOwnerStats` 未携带 `actor_did`，会导致 Dashboard / Messages 调用 owner 端点失败。 | 🔴 | helper 必须显式接收 `actorDid`，调用方传 `owner_did`。 |
| S1 | Setup / Dashboard 使用 `secretary_did` 调用 `listWorkers` / `listIntakes`，但当前后端要求 `actor_did == owner_did`。 | 🔴 | 调整调用方 actor：Owner 管理、Worker、Intake 列表使用 `owner_did`；Secretary dispatch 使用 `secretary_did`。 |
| S1 | `/secretary/dispatch` 默认 Playbook 创建多个角色 stage 时未设置 `next` 链，第一阶段完成后 run 会直接 completed，后续角色不会执行。 | 🔴 | 默认 Playbook 生成时按 `required_roles` 串联 `next`，并补两角色端到端推进测试。 |
| S2 | 新增测试偏函数片段，缺少真实 API 闭环和前端 actor 契约覆盖。 | 🟡 | 补 `/secretary/dispatch` 两角色端到端、前端 API helper actor 契约、Dashboard/Setup smoke。 |

### 覆盖率说明

当前环境未安装 `coverage/pytest-cov`，无法生成数值覆盖率报告。本次评审按路径覆盖判断：SDK helper、Context Snapshot、Manifest 有单元覆盖；Dashboard/Setup 前端 actor 契约、真实 dispatch 多阶段推进和 UI smoke 是主要缺口。
