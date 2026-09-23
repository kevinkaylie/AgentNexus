# 第三轮复审反馈修复确认（R3-1～R3-4）

对应复审记录 [2026-09-22-l0-r3-review.md](2026-09-22-l0-r3-review.md)。提交方：开发 Agent。日期：2026-09-22。

> 本文件是**修复确认**，不是复审结论。评审方需按 §5 的命令独立复核后自行给出结论。

## 1. 阻塞项

### R3-1 / P1：未知 session 的消息绕过资源授权（已修复）

**根因**：消息入口在查不到 session 时把**空字符串**交给 `require_resource`，而后者在"目标为空但凭据登记了任意资源范围"时不拒绝 → 未授权 session 的合法回执被 202 并持久化。

**修法**（`routers/code_review.py` + `code_review_store.resolve_profile_session`）：

1. 新增 `resolve_profile_session()` 返回 `ok` / `not_found` / `ambiguous`——**不再 `fetchone()` 取第一条**，歧义不再被任意挑一条掩盖；
2. 消息入口：`session_id` 缺失 → 422 `input_mismatch`；`not_found` → **409 `stale_assignment`**；`ambiguous` → **409 `idempotency_conflict`**。**"查不到"不再是放行条件**；
3. 资源许可与角色许可分离：改用 `principal.require_session(profile_session_id)`（要求命中凭据的 session 范围），不再用可空参数走 `require_resource` 的宽松分支；
4. **受信任关联核对**：信封 `run_id` 必须等于该会话绑定的 `external_run_id`；assignment 的 `payload.coordinator_id` 必须由已认证主体代表（§1 不取自报值）；
5. 契约 §4 明确：**新 Run 的绑定由受信任的部署初始化流程建立，本组端点不承担创建职责**——不接受以"查不到"触发的隐式创建。

**验证**：`test_r31_unknown_session_is_rejected_without_side_effects`（409 且业务表无变化、message 行数为 0）、`test_r31_session_must_match_the_run_it_claims`（真实 session 配错 Run → 409 无副作用）、`test_r31_same_identity_across_sessions_still_scoped`（同身份跨 session → 403 无副作用）。矩阵行 `messages.unknown_session` 覆盖 wire 层。

> 该测试写完第一次运行即**红**：当时 router 只按 `session_id` 解析，**没有**核对信封 `run_id` 与该会话绑定 Run 的一致性，配错 Run 的回执仍被 202。已补上该检查。

### R3-2 / P1：租约不参与校验、分配未在提交事务内复检（已修复）

**修法**：

1. `resolve_assignment_binding` 增加读取 `lease_expires_at`；入口增加**租约过期**检查（409 `stale_assignment`）；
2. 新增 `_verify_assignment_in_transaction()`：在 `commit_artifact_with_idempotency` 的 `BEGIN IMMEDIATE` 事务内**重新读取**同一分配，逐项校验 profile_session/external_run、worker DID、`assignment_epoch`、执行状态、**租约**、deadline。任一项失效即抛错回滚，**不登记产物、不置 committed**；
3. 入口检查保留为"快速失败"，但契约 §4 明确：**提前查询不构成原子围栏**，字节已写入外部存储也不能代替当前授权。

**验证**：`test_r32_expired_lease_is_rejected`、`test_r32_cancel_after_binding_read_is_caught_in_commit_transaction`、`test_r32_epoch_change_after_binding_read_is_caught`、`test_r32_deadline_pass_after_binding_read_is_caught`——后三者用 `vault_put` 注入点**确定性地**制造"读取绑定后、提交前"的状态变化，断言 409 且业务表无变化。

## 2. 建议项

### R3-3 / P2：同 key 并发上传主键冲突返回 500（已修复）

**修法**：`commit_artifact_with_idempotency` 在事务内**先看幂等状态**：同命名空间同键已 `committed` → 直接返回**已存在**的产物（`replayed`），不再无条件 `INSERT`；未 committed 才写入；冲突仍严格拒绝。

**验证**：`test_r33_concurrent_same_key_same_projection`（确定性屏障让两个真实 ASGI 请求同时到达 Vault 阶段）断言 **`[201, 201]` 且同一 artifact、只登记一份产物**；`test_r33_concurrent_same_key_different_projection` 断言 `[201, 409]`（不得 500）。

### R3-4 / P2：幂等比较用原始字节 / 完整信封（已修复）

**修法**：新增 `agent_net/code_review/projection.py`，把 §7 的比较规则实现成**一个**显式函数对：

- `message_projection()`：剔除信封 `message_id` / `created_at` / `correlation_id` / `causation_id`，保留 `type`/sender/receiver/session/run/attempt/epoch 及 `payload`；信封可选属性缺失时补固定缺省 `None`；
- `artifact_projection()`：取契约 DTO 的业务字段，其中 `artifact_body` **原样取字符串**，绝不重序列化内部内容；
- `canonical_json()`：**递归排序键、数组保持原顺序、无空白 UTF-8、禁止浮点**（出现 float 直接 `invalid_output`）；
- `projection_digest(..., namespace=(principal, action, resource_scope))`：实现 §7 的"幂等键按认证 principal + 动作 + 资源范围隔离"——同一 key 换到别的资源范围属于**不同操作**，不按冲突处理。

消息与上传各自持久化投影摘要（`code_review_messages.projection_digest`、幂等表按投影比较），比较不再触碰原始字节或完整信封。

**验证**：`test_r34_upload_dto_reformatting_is_a_replay`（键序反转 + `indent=4` → 201 同 artifact）、`test_r34_message_tracking_field_change_is_a_replay`（只改 `created_at`/`causation_id`/`correlation_id` → 202 同响应）、`test_r34_message_business_change_is_a_conflict`（payload 变化 → 409，已存信封未被改写、记录数不变）、`test_r34_receipt_replay_keeps_original_receipt_and_timestamps`（重放返回**原**回执，业务时间未重建）。

## 3. 保留建议的处置

| 建议 | 处置 |
|---|---|
| `retention_until_text` 只靠内存回显 | **已修复**：`commit_artifact_with_idempotency` 现在把该列**写入数据库**；`test_retention_text_is_persisted_in_database` 直接查库断言原文，并断言重放也返回原文 |
| `assignment_epoch` 用 `int()` 转换 | **已修复**：新增 `_strict_positive_int()`，拒绝 bool / 小数 / 字符串 → 422；`test_assignment_epoch_must_be_strict_positive_integer` 覆盖 `True` / `1.0` / `"1"` |
| 仅按 `external_run_id` 查询导致同名 Run 歧义 | **已修复**：`resolve_profile_session` 与 `resolve_assignment_binding` 都返回 `ambiguous` 并**拒绝**，不再任意挑一条；消息入口另外核对 Run 与会话绑定的一致性 |
| H/messages 的错误映射需与 §4 裁决对齐 | **属外部仓库**（HCZJ `service_http`/`message`），本工作区不可写；契约 §4 表已写清取值规则，仍须 HCZJ 侧对齐后由其验证 |
| 原 S1（HCZJ reviewer 归属） | **仍开放**，不在本批范围 |

## 3.1 R3-2 的两处补修（第三轮复审补评）

首轮修复后复审指出 R3-2 仍有两处缺口。两处均已修复，且**都先验证了测试能复现原缺陷**（见文末附记）。

**P1 — 分配身份复检不完整（上传期间改绑 Attempt 或 Coordinator 仍 201）**

根因：`_verify_assignment_in_transaction` 把 `external_attempt_id` / `external_coordinator_id`
查出来却分别命名为 `_attempt_id` / `_coordinator_id`，**从未比较**——即"读了不用"。

修法：把身份元组整体带入事务复检。`resolve_assignment_binding` 现在一并返回
`external_attempt_id`；`commit_artifact_with_idempotency` 接收
`expected_attempt_id` / `expected_coordinator_id`，并在事务内逐项比对，任一不符 →
409 `stale_assignment` 并回滚。

验证：`test_r32_attempt_rebinding_after_binding_read_is_caught`、
`test_r32_coordinator_rebinding_after_binding_read_is_caught`（在 Vault 阶段注入改绑）。

**P2 — 过期判断使用旧时间（等待写锁期间租约过期仍 201）**

根因：`now` 在 `BEGIN IMMEDIATE` **之前**取好并作为参数传入；事务在写锁上等待时，
租约可能在等待期间过期，而检查仍用等待前的旧时间通过。

修法：**取消把时间当参数传递**——`_verify_assignment_in_transaction` 在函数内（即已持锁后）
自行读取时钟，调用方无法再传入陈旧值；`commit_artifact_with_idempotency` 的 `now`
也移到 `BEGIN IMMEDIATE` 之后。

验证：`test_r32_lease_expiring_while_waiting_for_write_lock_is_caught` 用**另一条连接**
持有 `BEGIN IMMEDIATE` 写锁、由后台任务在租约过期后才释放，使提交事务确实在锁上等到租约过期。

### 附记：两处补修的测试有效性验证（负例证据）

| 测试 | 临时回退修复后的结果 | 恢复修复后 |
|---|---|---|
| `test_r32_attempt_rebinding_after_binding_read_is_caught` | **201**（复现评审现象） | 409 `stale_assignment` |
| `test_r32_coordinator_rebinding_after_binding_read_is_caught` | **201** | 409 `stale_assignment` |
| `test_r32_lease_expiring_while_waiting_for_write_lock_is_caught` | **201**（按旧的"BEGIN 之前取时间"结构运行） | 409 `stale_assignment`（"租约已过期"） |

即三条测试确实会在缺陷存在时变红，而不是"改完怎么写都通过"。临时回退已全部还原，
源码中无残留标记（已用脚本核对）。

## 3.2 R3-2 的空值围栏缺口（第四轮 R4-1 补评 · 第五轮 R5-1 定位）

复审指出：`external_coordinator_id` 可以以**空字符串**写入，而事务复检写作
`if expected_coordinator_id and ...` —— 预期值为空时整段比较被**跳过**，于是"从空 ID 改绑到
另一 Coordinator"不被发现，旧上传仍 201 并登记产物（第五轮独立探针：201 / 1 条 artifact）。

**根因**：把空值当成了"无需比较"的信号。空字符串是**可比较的值**；真值守卫让围栏在该情形下
形同不存在。同一类守卫还出现在 worker 比较（`if binding["worker_did"] and ...`）与入口检查。

**修法**（对应 R5-1 给出的三条建议，逐条落实）：

1. **绑定入口拒绝空身份字段**（R5-1 建议一）：`bind_execution_assignment()` 现在要求
   `profile_session_id` / `external_coordinator_id` / `external_run_id` / `external_attempt_id`
   均非空白，并校验 `assignment_epoch ≥ 1`，否则 422 `input_mismatch`——**从源头拒绝非法或
   不完整的受信任绑定记录**，而不是留到上传时兜底；
2. **上传入口对既有空绑定 fail-closed**（R5-1 建议二）：`binding.external_coordinator_id`
   为空 → 409 `stale_assignment`（"无法证明归属"）；
3. **事务内无条件比较**（R5-1 建议三）：三处身份比较（Attempt / Coordinator / worker）全部
   去掉真值守卫，改为 `(actual or "") != (expected or "")`——空与空相等、空与非空判失败；
4. 函数 docstring 写明"空值是可比较的值，不是无需比较的信号"，避免再次被改回守卫形式。

**验证**（含 R5-1 要求的"空值转有效值"负例）：

| 测试 | 覆盖 |
|---|---|
| `test_r51_binding_entry_rejects_empty_coordinator` | 建议一：空/纯空白的 Coordinator、空 Run、空 Attempt 在**绑定入口**即被拒（422），并指出缺失字段名 |
| `test_r32_empty_coordinator_is_refused_at_entry` | 建议二：既有空绑定的 HTTP 路径 → 409，业务表无变化 |
| `test_r32_in_transaction_comparison_has_no_truthiness_guard` | 建议三：直接驱动事务内校验，`expected_coordinator_id=""` 与 `expected_worker_did=""` 都必须抛错 |
| `test_r32_in_transaction_comparison_accepts_matching_identity` | 对照组：身份一致时必须通过（防止写成恒真拒绝） |

**负例证据**：把 Coordinator 比较改回旧的真值守卫（`if expected_coordinator_id and ...`）后，
`test_r32_in_transaction_comparison_has_no_truthiness_guard` 报 **`DID NOT RAISE`**
（即空值确实被跳过比较），对照组仍通过；恢复后两条都通过。临时回退已还原，脚本核对无残留。

> 过程说明：本条最初我写成"空 Coordinator → 中途改绑 → 应 409"的 HTTP 用例，但它被新增的
> 入口拒绝提前挡下，**并不能证明事务内守卫已修**。因此改为直接驱动事务内校验函数，
> 才真正覆盖到该守卫；HTTP 路径由入口拒绝单独覆盖。

## 4. 本轮包与运行时变更

- 规范包 `1.0-draft.2+semantic.13` → `semantic.14`（§4 增加"入站资源授权"与"上传分配围栏"两段澄清）。
- 运行时：新增 `agent_net/code_review/projection.py`；`persistence/schemas.py`（幂等表加 namespace 并重建迁移、messages 加 `projection_digest`）；`persistence/code_review_store.py`（`resolve_profile_session`、`resolve_assignment_binding` 加租约与 attempt、`reserve_artifact_idempotency` 命名空间化、`commit_artifact_with_idempotency` **身份元组整体复检 + 取锁后计时** + replay + 写 `retention_until_text`、消息存储改按投影比较）；`routers/code_review.py`（R3-1/R3-2 入口检查、严格 epoch、投影摘要）。
- 测试：`tests/test_code_review_http_contract.py` 47 → 68（含 R3-2 补修的改绑、写锁等待、空值围栏与对照组用例）；**R5-1 修复后 68 → 69**（绑定入口拒绝空身份、既有空绑定入口 409、事务内无真值守卫与对照组）。Code Review Profile 系列共 257 tests + 1 skip。
- 采集 pin 仍为 semantic.9 原值，未改写；复核记录更新为指向 semantic.14。

## 5. 请求复审

```bash
python -m pytest tests/ -q -p no:cacheprovider --tb=no -rs > .pytest_full_report.txt 2>&1
python scripts/check_full_suite.py --input .pytest_full_report.txt
python specs/profiles/code-review/v1/tools/validate.py
python specs/profiles/code-review/v1/tools/check_evidence.py --require-host-audit
```

建议重点复核：R3-1 的未知 session / 配错 Run / 跨 session 是否都拒绝且无副作用；R3-2 的租约过期与"读取后、提交前"取消/换 epoch/过 deadline 是否都在事务内被拦；R3-3 的两个真实并发同 key 请求是否不再出现 500；R3-4 的排版变化与仅追踪字段变化是否都按重放处理、业务变化是否仍 409。

## 6. 未关闭声明

T1–T6 全部开放；**BINDING-GATE-1 维持关闭**；`compatibility.json` 保持默认拒绝；未声明 wire conformance、未声明实现符合性。`manifest.source.worktree_dirty=true` → 规范包仍为候选。本批**尚未提交**，等评审确认后再提交。

## 7. 评审方结论（2026-09-23）

**需修改后复审。** 独立复跑历史探针后，R3-1/R3-3/R3-4 原问题可关闭；R3-2 原始复现已通过，但不能整体关闭：事务丢弃读取到的 Attempt/Coordinator，且使用获取写锁前的时间检查期限。两种缺口均已在真实 ASGI/SQLite 路径复现错误 201 + 产物登记。见 [第四轮评审与验证记录](2026-09-23-l0-r4-review.md) 的 R4-1、R4-2；本结论由评审方填写，不改写上文提交方自查记录。

## 8. 评审方第五轮结论（2026-09-23）

R4-2 关闭；R4-1 的普通非空改绑已修复，但空 Coordinator ID 会跳过事务比较，改绑后仍错误返回 201 并登记产物。见[第五轮复审](2026-09-23-l0-r5-review.md)的 R5-1。整体仍需修改后复审；本节是后续结论，上节保留历史记录。

## 9. 评审方第六轮结论（2026-09-23）

R5-1 代码缺陷已关闭，本次修复通过评审：空 Coordinator 绑定写入被拒，旧库空绑定上传被拒且不登记产物，事务内空预期值仍严格比较。见[第六轮复审](2026-09-23-l0-r6-review.md)。本结论不改变 T1–T6 与 BINDING-GATE-1 的开放状态。

## 9. 提交方 R5-1 修复与再次提交（2026-09-23）

针对第五轮 R5-1（空 Coordinator 绕过事务身份比较，P2）的修复，**详细根因、三条建议的逐条落实与负例证据见上文 §3.2**（该节按本条要求从"第四轮"改写为 R4/R5 定位）。要点：

- **改动文件**：`agent_net/persistence/code_review_store.py`（`bind_execution_assignment` 校验空身份字段与 `assignment_epoch ≥ 1`；`_verify_assignment_in_transaction` 及入口比较去除全部真值守卫，改 `(actual or "") != (expected or "")`，docstring 固化"空值是可比较的值"）；`agent_net/node/routers/code_review.py`（既有空绑定入口 409 `stale_assignment`）；`tests/test_code_review_http_contract.py`（+1，并新增两条事务内校验负例/对照用例）。
- **契约未改**：`bindings/l0-service-contract.md` §1 已规定"ID 为非空字符串"，§4「上传的分配围栏」已要求在登记产物的事务内校验 Coordinator——本次属**实现未落实既有契约**（真值守卫），因此规范包维持 `1.0-draft.2+semantic.14`，不重新生成清单、不改动采集 pin。
- **门禁**：`762 passed, 57 skipped, 0 failed, 0 errors`，`scripts/check_full_suite.py` exit 0；基线未改（`counts` 与 `environmental_failures` 均未触碰）。
- **测试有效性**：R5-1 的三处修复各自都有"回退即变红"的负例证据（§3.2 表与负例段落）；临时回退均已还原。

**复核建议**：直接运行 §5 的四条命令，并重点用空值路径独立构造"空 Coordinator → 改绑有效 Coordinator → 旧上传"，确认返回 **409 且业务表无变化**；同时确认正常身份一致的上传仍 201（防止修复被写成恒真拒绝）。

**结论**：R5-1 待评审方复核后关闭。本节由提交方填写，不构成复审结论。
