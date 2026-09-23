# 评审反馈修复确认（B1–B10 / S1–S6）

对应评审记录 [2026-09-21-l0-overall-code-review.md](2026-09-21-l0-overall-code-review.md)（CR-REVIEW-2026-09-21-01）。
提交方：开发 Agent。日期：2026-09-21。

> **2026-09-22 独立复审补记**：本修复说明的历史自评保留；当前结论以[第二轮整体复审](2026-09-22-l0-rereview.md)为准。B8 已由外部项目修复并复核，B10 已验证关闭；剩余 R2-1～R2-6 必须修改。全量 722 passed / 9 skipped、回归门禁 exit 0，不等于整体实现获批。

> 本文件是**修复确认**，不是复审结论。评审方需按 §7 的复现命令独立复核后自行给出结论。

## 1. 逐项处置

| 项 | 处置 | 位置 | 验证 |
|---|---|---|---|
| **B1** 角色授权用调用方自报身份 | **已修复** | `agent_net/code_review/service_auth.py`（新增）、`agent_net/node/routers/code_review.py`、`agent_net/persistence/code_review_store.py`、`agent_net/persistence/schemas.py` | 新增 `code_review_service_principals` 凭据登记（只存 sha256）；`require_service_principal` 做认证，未登记任何凭据 → **401 拒绝**（不再"未配置则放行"）；`sender_id`/`issuer_id` 必须落在凭据可代表的 DID 内；回执 kind → 角色 + issuer 绑定。负例：`test_cr_api_rejects_everything_when_no_credential_configured`、`test_cr_api_rejects_unknown_credential`、`test_cr_api_sender_must_be_bound_to_credential`、`test_cr_api_worker_cannot_forge_accepted_receipt`、`test_cr_api_receipt_issuer_must_be_bound` |
| **B2** 读取无 session/Run 资源授权 | **已修复** | 同上 + `api_get_message` / `api_get_artifact_raw` | 读取必须命中凭据的资源范围（`principal.require_session`）；消息当事人或具读取角色且同 session 才可读；产物读取另有保留期检查（过期 → **410** `artifact_expired`）。负例：`test_cr_api_message_read_requires_party_or_session_scope`、`test_cr_api_artifact_read_requires_session_scope_and_retention`、`test_cr_api_expired_artifact_returns_410` |
| **B3** 上传/响应 DTO 与 wire 契约不一致 | **已修复** | `agent_net/code_review/frozen.py`（新增）、`code_review.py` 的 `_artifact_ref` / `_parse_iso` | 只接受契约七字段（`producer_id`/`actor_did`/`artifact_id` 等一律 422）；`retention_until` 严格按 RFC3339 解析、持久化并**原样返回字符串**（不再静默 null），数字时间戳 422，超出承诺 422 `data_policy_denied(scope=retention)`；ArtifactRef **先过冻结 `artifact_ref.schema.json`** 再返回（不再多出 `enforcement`）；TransportAck 恰好三字段、MessageView 恰好四字段且 `receipts` 为 Profile 回执**信封**。验证：`test_cr_api_upload_rejects_fields_outside_contract`、`test_cr_api_upload_retention_is_parsed_persisted_and_returned`、`test_cr_api_upload_rejects_numeric_retention`、`test_cr_api_upload_rejects_retention_beyond_commitment`、`test_cr_api_artifact_ref_validates_against_frozen_schema`（以实际 HTTP 响应跑冻结 schema）、`test_cr_api_assignment_ack_is_exactly_three_fields` |
| **B4** 重复上传破坏不可变产物、幂等未实现 | **已修复** | `code_review_store.reserve_artifact_idempotency`、`code_review.py` | Vault key 改为**按内容摘要寻址**（`.../{digest}.body`）：同 locator 不可能出现不同字节，失败请求不会覆盖已登记字节；幂等按 `(principal, Idempotency-Key)` 映射，同 key 同请求返回原 artifact_id，内容不同 → 409 `delivery_conflict`；缺 `Idempotency-Key` → 422。验证：`test_cr_api_same_idempotency_key_returns_same_artifact`、`test_cr_api_same_key_different_body_conflicts_without_corrupting`、`test_cr_api_upload_requires_idempotency_key`、`test_cr_api_vault_key_is_content_addressed` |
| **B5** 入站只校验外壳，空 Assignment 被 ACK | **已修复** | `frozen.validate_envelope`、`_require_consistent_ids`、`declared_enforcement_requirements` | 接收前用冻结 `envelope.schema.json` 校验信封**及其按 type 的 payload**（其 `allOf` 已编码每种 type 的必需字段）；`enforcement_requirements` 缺失或为空一律拒绝（不再当成空数组）；信封与 payload 的 `run_id`/`attempt_id`/`assignment_epoch` 必须一致。验证：`test_cr_api_rejects_empty_assignment_payload`、`test_cr_api_rejects_assignment_without_enforcement_requirements`、`test_cr_api_rejects_assignment_with_unknown_payload_field` |
| **B6** 回执与业务处理分事务、崩溃后永不处理 | **已修复** | `code_review_store.store_message_with_receipt`、`_complete_pending_receipt`、`reprocess_pending_messages` | 消息 + 回执 + `processed` 状态**同一事务**（BEGIN IMMEDIATE）提交；`GET` 与 `reprocess_pending_messages()` 对仍为 `stored` 的回执消息做可重放补偿。验证：`test_cr_api_receipt_processed_atomically_and_view_returns_envelopes`、`test_cr_api_receipt_crash_window_is_recovered_on_read` |
| **B7** provider 转换静默丢弃 finding | **已修复** | `agent_net/code_review/provider_adapter.py` | 删除全部 `isinstance(..., Mapping)` 过滤，改为 `_strict_list` 逐项严格校验（finding 非对象、omitted_files/inherited_gaps 元素非法 → `invalid_output`）；`_require_native_schemas` 让 `source_report_schemas`/`source_coverage_schemas` 从"仅声明"变为**强制核对**（不受支持 → `unsupported_contract`）；`_map_coverage` 的原状态键改用 `native_status_key`（原先硬编码 `status`）。验证：`test_malformed_finding_is_rejected_not_silently_dropped`、`test_malformed_gap_signal_is_rejected_not_silently_dropped`、`test_unlisted_native_schema_is_unsupported_contract`、`test_unlisted_coverage_schema_is_unsupported_contract`、`test_valid_hczj_report_still_converts_after_strictening` |
| **B8** HCZJ 客户端无法同时通过 Nexus 新旧鉴权 | **未修复（超出本工作区写权限）** | 外部 `Hczj_Assistant_Agent` / `Nexus_Agent` | 提交方沙箱仅可写 `AgentNexus` 工作区，实测对外部仓库建档被拒（`Access to the path ... is denied`）。已在 `docs/wip.md` 登记为跨仓库待办并附评审给出的修复方向（带资源授权的 L0 facade，或按 endpoint audience 区分凭据）；**不得以关闭旧鉴权或共享 token 作为验收**。需要外部仓库方实施后由评审复核 |
| **B9** 收口裁判可把无拒绝事实判为满足 | **已修复** | `specs/profiles/code-review/v1/tools/check_evidence.py` | 三个自述检查改为**样例级校验**（`verify_refusal_sample`）：必须有样例、`subject`/`endpoint`、HTTP 状态 ∈ {401,403}、原始字节能解码为冻结错误信封（必填字段齐全）、错误码在 `error.schema.json` 枚举内且 ∈ {authority_denied, data_policy_denied}、声明的 `expected_error_code` 与实际一致。模板 T3/T4/T5 相应改为 `refusal_samples`。验证：`test_boolean_without_refusal_sample_is_rejected`、`test_refusal_sample_with_200_is_rejected`、`test_refusal_sample_with_wrong_code_is_rejected`、`test_refusal_sample_unknown_code_is_rejected`、`test_refusal_sample_missing_subject_is_rejected`、`test_refusal_sample_not_error_envelope_is_rejected`、`test_unconfigured_text_cannot_satisfy_refusal_check`（正是评审的 `does not reject; allows requests` 反例） |
| **B10** 规范包自检强依赖宿主证据 | **已修复** | `check_evidence.py`、`closure-checklist.json` | 拆成「包内可移植自检」与「宿主证据审计」：宿主审计按 `host_markers`（AGENTS.md / docs/wip.md / tests/conftest.py）判定，非中央仓库时 `[SKIP]`；中央仓库可用 `--require-host-audit` 把标记缺失升级为失败；宿主标记齐备而证据缺失仍为**失败**。验证：真实包复制到任意目录后自检通过（`test_real_package_copied_anywhere_still_passes`）、`test_package_without_host_markers_skips_host_audit`、`test_require_host_audit_flag_turns_skip_into_failure`、`test_missing_host_evidence_with_markers_present_is_rejected` |

## 2. 建议性/信息性事项

| 项 | 处置 |
|---|---|
| **S1** HCZJ reviewer 归属 | 属外部仓库实现，与 B8 一并交回外部方；本工作区不推定其归属规则 |
| **S2** C 组运行约束只能是 declared_only | 采纳。`agent_net/CLAUDE.md`/配置未声称 `enforced`；本批未把 `network_access` 注册为强制能力，也**未**据此产生任何 CP-25 证据 |
| **S3** 采集 pin 不应因包升级改写 | **已按建议改正**：`source-snapshot.json` 恢复采集时 pin `69d3748a…`（semantic.9），删除此前"直接刷新 pin"的 `profile_manifest_refreshed`；新增 `capture_package_version` 使"pin 是否被改写"可判定；新增 `profile_manifest_rechecks` 复核记录（`checked_against_sha256` 指向当前包、`checked_at` 晚于采集时间、附命令/范围/结果、`reexecuted=false` 并注明**未**重跑旧样例）。README 同步说明。验证：`test_rewritten_capture_pin_is_rejected`、`test_same_version_pin_must_match_current`、`test_snapshot_must_record_capture_package_version`、`test_drifted_pin_with_valid_recheck_is_accepted`、`test_drifted_pin_without_recheck_is_rejected`、`test_recheck_before_capture_time_is_rejected`、`test_recheck_claiming_reexecution_needs_artifacts`、`test_recheck_must_point_at_current_package` |
| **S4** 基线维护 | **已按建议收窄**：不再把环境失败登记进基线。`tests/conftest.py` 增加能力探针（`asyncio.create_subprocess_exec`、工作区外临时目录），能力缺失时由 `pytest_collection_modifyitems` **显式跳过**并写明原因；`tests/full_suite_baseline.json` 的 `environmental_failures` 收窄为**空**、`counts.failed/errors` 为 0，新增 `environment_dependent_files`。`scripts/check_full_suite.py` 相应改为：未登记失败/未登记跳过一律失败，通过数下限 = 基线 − 可解释的环境跳过数。两种环境都应 exit 0 |
| **S5** 公开材料与提交组织 | 采纳建议：C 组（`.agentnexus/local-runner.yaml`、`threads/README.md`、`docs/community/`）**建议与 A/B 组分开提交**；未做任何对外发布 |
| **S6** 维护性 | 部分采纳：`no_placeholder`/`sample_bytes` 仍为标记式检查（已注释说明由通用规则承担）；导入校验器仍会写 `__pycache__`（未在本次改）；`sample_list` 取首个列表键的问题在 T3/T4/T5 改为 `refusal_samples` 后不再触发，但根因仍在；CHANGELOG 条目顺序未动。其余记录为后续改进 |

## 3. 本次同时变更的包与运行时

- 规范包 `1.0-draft.2+semantic.10` → `semantic.11`（B9/B10/S3 落在包内）：`tools/check_evidence.py`、`bindings/evidence/closure-checklist.json`、`bindings/evidence/templates/T3/T4/T5.json`、`README.md`、`manifest.json`。
- 运行时新增模块：`agent_net/code_review/service_auth.py`、`agent_net/code_review/frozen.py`。
- 运行时变更：`agent_net/node/routers/code_review.py`（按 B1–B6 重写）、`agent_net/code_review/provider_adapter.py`（B7）、`agent_net/persistence/code_review_store.py`、`agent_net/persistence/schemas.py`、`agent_net/persistence/coordination.py`。
- 测试：`tests/test_code_review_api.py`（按新契约重写，30 项，含评审要求的负例）、`tests/test_code_review_provider_adapter.py`（+5 项 B7 回归）、`tests/test_code_review_evidence_checklist.py`（28 → 48 项）、`tests/conftest.py`（能力探针）、`tests/full_suite_baseline.json`。

## 4. 未关闭的门禁与声明

- **B8 未修复**（超出本工作区写权限），需外部仓库方实施后由评审复核。
- **S6 部分未改**，如上表所列。
- T1–T6 仍全部开放；**BINDING-GATE-1 维持关闭**；`compatibility.json` 保持默认拒绝；未声明 wire conformance、未声明实现符合性。
- `manifest.source.worktree_dirty=true` → 规范包仍为**候选**，非发布件。

## 5. 请求评审方复核

请按评审记录 §4「独立验证与复现」同样的方式重跑：

```bash
python -m pytest tests/ -q -p no:cacheprovider --tb=no -rs > .pytest_full_report.txt 2>&1
python scripts/check_full_suite.py --input .pytest_full_report.txt
python specs/profiles/code-review/v1/tools/validate.py
python specs/profiles/code-review/v1/tools/check_evidence.py
```

并重点复核：B1 的冒充路径是否真的被堵住（换 sender 不再改变结果）、B4 的失败上传是否仍会破坏原字节、B5 的空 payload 与缺 `enforcement_requirements` 是否仍被拒、B9 的三个检查是否都能被样例级事实驱动、B10 的复制包自检是否通过。
