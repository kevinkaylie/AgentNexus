# 复审反馈修复确认（R2-1～R2-6）

对应复审记录 [2026-09-22-l0-rereview.md](2026-09-22-l0-rereview.md)。提交方：开发 Agent。日期：2026-09-22。

> **第三轮复审结论（2026-09-22）**：见[第三轮报告](2026-09-22-l0-r3-review.md)。确认 R2-3/R2-4/R2-5/R2-6 原问题修复；消息幂等头裁决已落地。仍有 R3-1～R3-4：消息资源授权、失效分配提交围栏、同 key 并发、业务投影比较。整体需修改后复审；以下为提交方历史说明。

> 本文件是**修复确认**，不是复审结论。评审方需按 §4 的命令独立复核后自行给出结论。

## 1. 逐项处置

| 项 | 处置 | 位置 | 验证用例 |
|---|---|---|---|
| **R2-1** 幂等预留先提交，存储失败后同 key 无法恢复 | **已修复** | `code_review_artifact_idempotency` 新增 `state`（pending/committed）；`reserve_artifact_idempotency` 只在**同 key 不同请求内容**时判冲突，pending 表示"上次未提交成功"→允许**续用同一 artifact_id** 重试；新增 `commit_artifact_with_idempotency` 把**产物登记与置 committed 放在同一事务**，任一步失败整体回滚、映射保持 pending | `test_r21_vault_failure_then_same_key_retry_recovers`（503 → 201 → 同 artifact_id）、`test_r21_artifact_insert_failure_leaves_no_committed_mapping` |
| **R2-2** 上传未绑定真实 Run/Attempt/epoch；空 session 放行 | **已修复** | 上传路径改为：未知 Run → **422** `input_mismatch`；`principal.require_session(profile_session_id)` 强制资源范围；新增 `resolve_assignment_binding` 按 `(session, run, attempt)` 解析**唯一**绑定，`unknown_run`/`ambiguous` → **409** `stale_assignment`；校验 `assignment_epoch` 等于当前分配、执行状态在 `(pending, running)`、未过 `deadline`、认证 DID 是该 Attempt 的 `worker_did`；消息读取的当事人分支**同样**执行 session 范围检查 | `test_r22_unregistered_run_is_rejected`、`test_r22_unassigned_attempt_and_wrong_epoch_are_rejected`、`test_r22_other_worker_is_rejected`、`test_r22_cancelled_assignment_is_rejected`、`test_cr_api_message_read_requires_party_or_session_scope`（新增"当事人但无该 session 范围 → 403"） |
| **R2-3** 回执仍先独立落库，冲突消息产生业务记录 | **已修复** | 新增 `store_receipt_message`：**单事务**内先校验消息幂等投影与回执幂等投影（同 `receipt_id` 必须同投影，否则 `idempotency_conflict`），**全部通过后**才写回执行、inbox 与 `processed`，冲突在写入前抛出故**无副作用**；路由不再预先调用 `create_profile_receipt` | `test_r23_conflicting_message_has_no_receipt_side_effect`（409 后 receipt 计数不变）、`test_r23_receipt_id_reuse_with_different_projection_conflicts`（同 receipt_id 不同投影 → 409 且计数不变） |
| **R2-4** validator/publisher 被额外要求 coordinator | **已修复** | `require_receipt_authority` 改为**返回**该 kind 唯一对应的角色，路由统一用它做 `require_role` 与 `_enforcement_level`，删除 `required_role or "coordinator"` 的兜底 | `test_r24_validator_and_publisher_roles_work_under_real_grants`（真实 role_grant 下 validated/published → 202）、`test_r24_role_grant_required_even_if_credential_declares_role` |
| **R2-5** null findings 仍被转换为空列表 | **已修复** | `_strict_list` 区分**字段缺失**与**显式 null**：`findings`/`omitted_files`/`inherited_gaps` 为必填集合，缺失或 null 一律 `invalid_output`；可选字符串集合只在类型错误时报错 | `test_null_findings_is_rejected_not_reported_as_no_findings`、`test_missing_findings_is_rejected`、`test_null_gap_collections_are_rejected` |
| **R2-6** 拒绝证据未按冻结 schema 与场景语义验证 | **已修复** | `load_error_contract` 现在构建**可执行 validator**（含 `common.schema.json` 的 registry），`verify_refusal_sample` 真正运行 `error.schema.json`（类型/const/additionalProperties/allOf）；新增 `REFUSAL_EXPECTATIONS` 把每个用例绑定到**主体角色、方法+端点、允许错误码**；未登记期望的用例直接失败 | `test_r26_legal_403_from_unrelated_scenario_is_rejected`、`test_r26_schema_invalid_error_body_is_rejected`（`retryable="yes"`/`scope=123`/`retry_after_seconds=-99`/`schema=not-an-error-schema`）、`test_r26_error_code_must_match_the_scenario`、`test_r26_unregistered_refusal_case_is_rejected`、`test_refusal_sample_accepts_real_403` |

## 2. 建议与边界

| 项 | 处置 |
|---|---|
| **原 S1** HCZJ reviewer 归属 | 仍开放，属外部仓库实现（与 B8 同域），本工作区不可写 |
| **部署依赖 / P2** `frozen.py` 运行时导入未登记 | **已修复**：`pyproject.toml` 的 `dependencies` 与 `dev` 均加入 `jsonschema>=4.18.0`、`referencing>=0.30.0`，并注明用途（接收前冻结 schema 校验）。本沙箱无法做干净安装验证，需评审方在干净环境确认 |
| **协议边界 / P2** retention 精度 | **已部分修复**：新增 `artifacts.retention_until_text`，`retention_until` **原样回显请求字符串**（不再经 float 反格式化丢微秒），验证 `test_cr_api_retention_is_echoed_verbatim`（`2026-12-31T00:00:00.123456Z`） |
| **协议边界 / P2** 其余（消息接口未强制 `Idempotency-Key`、`X-Correlation-Id` 可缺省、上传用宽松 `json.loads` 不拒重复键、raw `If-Match` 不匹配返回 409 而 RC2 要求 412、Range 未显式拒绝） | **未修复**，记录为下一批；本批聚焦 R2-1～R2-6。建议与评审方确认优先级后按"实际 HTTP 契约矩阵"一次性收口 |
| **C 组网络约束** | 仍为 `declared_only`，未注册 `enforced`，未据此产生任何 CP-25 证据 |

## 3. 本轮包与运行时变更

- 规范包 `1.0-draft.2+semantic.11` → `semantic.12`（`tools/check_evidence.py` 的拒绝校验与 pin 复核规则）。
- 运行时：`agent_net/persistence/schemas.py`（幂等 `state` 列、`retention_until_text` 列）、`agent_net/persistence/code_review_store.py`（`reserve_artifact_idempotency` 重写、`commit_artifact_with_idempotency`、`resolve_assignment_binding`、`store_receipt_message`）、`agent_net/persistence/deliverable_store.py`（读取新列）、`agent_net/node/routers/code_review.py`（R2-1～R2-4）、`agent_net/code_review/service_auth.py`（`require_receipt_authority` 返回角色）、`agent_net/code_review/provider_adapter.py`（R2-5）、`pyproject.toml`（运行时依赖）。
- 测试：`tests/test_code_review_api.py` 30 → 41（新增 R2-1～R2-4 与 retention 原样回显）、`tests/test_code_review_provider_adapter.py` 12 → 15（R2-5）、`tests/test_code_review_evidence_checklist.py` 48 → 53（R2-6 与历史复核记录规则）。
- S3 采集 pin 仍为 semantic.9 原值 `69d3748a…`，未改写；新增 `semantic.11`、`semantic.12` 两条 `profile_manifest_rechecks`（均 `reexecuted: false`，注明未重跑旧样例）。校验规则同时放宽为"历史条目可指向当时摘要，但必须有一条指向当前包"。

## 4. 请求复审

```bash
python -m pytest tests/ -q -p no:cacheprovider --tb=no -rs > .pytest_full_report.txt 2>&1
python scripts/check_full_suite.py --input .pytest_full_report.txt
python specs/profiles/code-review/v1/tools/validate.py
python specs/profiles/code-review/v1/tools/check_evidence.py --require-host-audit
```

建议重点复核：R2-1 的"失败后同 key 可恢复"是否在 Vault 失败、artifact INSERT 失败与并发同 key 三种情形下都成立；R2-2 的未登记 Run / 未分配 Attempt / 错误 epoch / 非分配 worker 是否都被拒；R2-3 的冲突是否**全表无副作用**；R2-4 在启用真实 role_grant 后 validator/publisher 能否工作；R2-6 的拒绝校验能否拒绝"合法 403 但错误场景"与"键齐全但 schema 不合法"。

## 5. 未关闭声明

T1–T6 全部开放；**BINDING-GATE-1 维持关闭**；`compatibility.json` 保持默认拒绝；未声明 wire conformance、未声明实现符合性。`manifest.source.worktree_dirty=true` → 规范包仍为候选。
