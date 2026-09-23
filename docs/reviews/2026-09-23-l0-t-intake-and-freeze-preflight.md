# L0 T1–T6 证据 intake 与 compatibility 冻结预检（2026-09-23）

本文件推进路线图**第 2 步**（补齐实际部署样例与版本证据，逐项关闭 T1–T6）与**第 3 步**（三方冻结 `compatibility.json`）中 AgentNexus 侧可完成的部分。

> 性质：提交方的**证据征集与预检清单**，不是评审结论，也不构成符合性声明。
> 依据：`specs/profiles/code-review/v1/bindings/evidence/closure-checklist.json`（`binding_revision=RC2`，`updated_at=2026-09-20`）与 `compatibility.json`。
> 机械裁判：`tools/check_evidence.py`（`--require-host-audit`）+ `tools/validate.py`；本文件所有"要什么"都能在那两个脚本里复算，不存在只有本文件才认的条目。

## 0. 当前状态（可复算）

| 项 | 现状 | 复算方式 |
|---|---|---|
| T1–T6 | **6/6 仍为 `open`**，25 条证据要求全部 `blocking=true` | `check_evidence.py` 逐项打印 |
| 本地证据包 | `docs/evidence/l0-2026-09-21`，`closing=false`（合成样例，`production=false`） | 同上；改标签冒充生产证据会被拒 |
| 采集 pin | 仍为 `semantic.9` 原值，未改写；版本漂移以 `profile_manifest_rechecks` 追加记录 | `check_evidence.py` 的 S3 检查 |
| BINDING-GATE-1 | **closed** | `closure-checklist.json.gate.status` |
| compatibility | `default_decision=reject`，`nexus.schema_versions=[]`、`contract_revisions=[]`、两个 `operative_allowlist=false`、`artifact_access_scope=[]` | `tools/validate.py` + `tests/test_code_review_cp_matrix.py::test_compatibility_allowlists_stay_empty_while_gate_closed` |
| CP-01～26 | AgentNexus 侧可验证部分已执行：**15 通过 / 6 部分 / 5 无本仓证据 / 0 失败** | `scripts/run_cp_matrix.py`，记录见 `fixtures/binding/cp-execution-record-2026-09-23.md` |

**结论：第 2 步与第 3 步的阻塞项都不在本工作区**——它们要求 Nexus 与 HCZJ 的**实际部署**版本证据、生产/联调样例与三方签字。本仓能做的只有三件：把要求写准、把机械裁判接上、把本地已有的对照证据标成 `non_closing`。下面逐项列出。

## 1. 第 2 步：T1–T6 intake（谁提供什么）

填写落点：`bindings/evidence/templates/T{n}.json` → 填好后放入 `bindings/evidence/received/T{n}.json`，再把清单里对应 `items[].status` 改到与实际一致。**不得改声明迁就实际**（校验器会以"虚假关闭/声明不一致/提前放行"失败）。

| T | owner | 要求数 | 模板 | 本地对照证据（`non_closing`） | 关闭前必须补上的东西 |
|---|---|---|---|---|---|
| T1 | Nexus_Agent | 5 | `templates/T1.json` | `nexus-http-samples.json`、`nexus-test-results.xml` | 部署版本证据（source_revision/artifact_identifier/endpoint 的真实取值）；事件+ACK 生产样例；`contract_revision` 允许值与未知值拒绝口径；查询 DTO 冻结样例；raw 字节端点样例（摘要/ETag/Content-Length 三者一致） |
| T2 | Nexus_Agent | 4 | `templates/T2.json` | 同上（CRLF/Unicode 切分对照） | 已持久化 report 的**原始字节**样例（含 manifest 摘要一致）；`GET` 与持久化字节的差异声明；行边界向量；locator/retention 决策记录（不能承诺 retention 时拒绝） |
| T3 | Hczj_Assistant_Agent | 4 | `templates/T3.json` | `hczj-http-samples.json`、`hczj-service-results.xml`、`hczj-unit-results.xml` | HCZJ 部署版本证据；服务鉴权契约（凭据种类、角色映射、资源范围、未配置时拒绝样例，且不得是 admin/session）；Run/Attempt CAS 样例（含冲突样例）；Attempt 标签映射 fixture |
| T4 | Hczj_Assistant_Agent | 4 | `templates/T4.json` | `hczj-http-samples.json`、`hczj-service-results.xml` | Coordinator 身份形式与**重启稳定性**证据；消息 wire 样例（含 TransportAck 形状）；幂等冲突样例；回执签发权限（kind→role 映射 + 伪造回执拒绝样例） |
| T5 | Hczj_Assistant_Agent | 5 | `templates/T5.json` | `hczj-http-samples.json`、`hczj-service-results.xml` | Publisher 边界与凭据隔离（含 worker 发布拒绝样例）；outbox 持久化（迁移 ID/表/唯一键/同事务证明/崩溃恢复样例）；发布状态样例；GitLab 写入验证（note_id、分页完整性、禁止操作缺失）；重放不重复评论证明（note 计数前后相等） |
| T6 | three-party | 3 | `templates/T6.json` | `hczj-http-samples.json`、`hczj-service-results.xml` | `artifact_ref.access_scope` 词表与授权语义（含不存在时的泄露防护）；`compat_freeze_record`（维护者/冻结日期/三方签字/冻结后允许列表）；severity 与 outcome/coverage 映射 fixture（P0–P3 + 未知值拒绝 + 四象限） |

### 1.1 每个要求的必需字段与机械检查

以下由 `closure-checklist.json` 直接摘录；校验器会逐条检查字段是否存在、是否残留占位符、样例字节是否自洽。T 项内的 `record_key` 就是模板里要填的键名。

**T1（Nexus_Agent）**

| record_key | kind | 必需字段 | 机械检查 |
|---|---|---|---|
| `deployment_version` | deployment_version | `source_revision`, `artifact_identifier`, `endpoint_base_url`, `captured_at`, `captured_by`, `capture_method` | `loopback_url`, `rfc3339`, `no_placeholder` |
| `event_ack_samples` | production_sample | `samples`, `attested_by` | `sample_bytes`, `scan_succeeded_fields` |
| `contract_revision_allowlist` | design_decision | `allowed_values`, `unknown_value_behavior`, `decided_by`, `decided_at` | `no_placeholder`, `unknown_behavior_must_refuse` |
| `query_dto_freeze` | production_sample | `samples`, `attested_by` | `sample_bytes`, `covers_endpoints` |
| `raw_byte_endpoints` | production_sample | `samples`, `attested_by` | `sample_bytes`, `artifact_digest_matches_raw`, `etag_matches_digest`, `content_length_matches` |

**T2（Nexus_Agent）**

| record_key | kind | 必需字段 | 机械检查 |
|---|---|---|---|
| `persisted_report_bytes` | raw_bytes | `raw_bytes_b64`, `sha256`, `byte_length`, `media_type`, `provider_id`, `report_id`, `manifest_report_sha256`, `attested_by` | `sample_bytes`, `report_digest_matches_manifest`, `media_type_is_json` |
| `get_vs_persisted_divergence` | production_sample | `report_id`, `get_response_bytes_b64`, `get_response_sha256`, `persisted_sha256`, `same_caliber`, `explanation`, `attested_by` | `sample_bytes`, `divergence_stated` |
| `line_boundary_vectors` | mapping_fixture | `vectors`, `attested_by` | `line_vector_bytes` |
| `locator_and_retention` | design_decision | `locator_template`, `media_type`, `access_scope`, `retention_source`, `refuses_when_unable_to_promise`, `decided_by`, `decided_at` | `no_placeholder`, `locator_shape` |

**T3（Hczj_Assistant_Agent）**

| record_key | kind | 必需字段 | 机械检查 |
|---|---|---|---|
| `deployment_version` | deployment_version | `source_revision`, `artifact_identifier`, `endpoint_base_url`, `captured_at`, `captured_by`, `capture_method` | `loopback_url`, `rfc3339`, `no_placeholder` |
| `service_auth_contract` | auth_evidence | `credential_kind`, `principal_role_mapping`, `resource_scope_rules`, `unconfigured_behavior`, `samples`, `refusal_samples`, `attested_by` | `sample_bytes`, `must_refuse_when_unconfigured`, `not_admin_session` |
| `run_attempt_cas_samples` | production_sample | `samples`, `attested_by` | `sample_bytes`, `covers_endpoints`, `conflict_samples_present` |
| `attempt_label_mapping_fixtures` | mapping_fixture | `fixtures`, `attested_by` | `covers_labels` |

**T4（Hczj_Assistant_Agent）**

| record_key | kind | 必需字段 | 机械检查 |
|---|---|---|---|
| `coordinator_identity` | design_decision | `coordinator_id_form`, `sample_value`, `restart_stability_samples`, `decided_by`, `decided_at` | `no_placeholder`, `restart_stability_evidenced` |
| `message_wire_contract` | production_sample | `samples`, `attested_by` | `sample_bytes`, `covers_endpoints`, `transport_ack_shape` |
| `idempotency_conflict_samples` | production_sample | `samples`, `attested_by` | `sample_bytes` |
| `receipt_issuance_authority` | auth_evidence | `receipt_kind_to_role`, `samples`, `refusal_samples`, `attested_by` | `sample_bytes`, `covers_receipt_kinds`, `forged_receipt_refused` |

**T5（Hczj_Assistant_Agent）**

| record_key | kind | 必需字段 | 机械检查 |
|---|---|---|---|
| `publisher_ownership` | design_decision | `publisher_boundary`, `credential_separation`, `worker_publish_refusal_sample`, `refusal_samples`, `decided_by`, `decided_at` | `sample_bytes`, `no_placeholder`, `worker_refusal_evidenced` |
| `outbox_persistence` | schema_evidence | `migration_id`, `tables`, `unique_keys`, `same_transaction_proof`, `crash_recovery_sample`, `attested_by` | `sample_bytes`, `no_placeholder`, `unique_key_declared` |
| `publication_samples` | production_sample | `samples`, `attested_by` | `sample_bytes`, `covers_publication_states`, `summary_text_not_executed` |
| `gitlab_write_verification` | production_sample | `samples`, `pagination_completeness`, `forbidden_operations_absent`, `attested_by` | `sample_bytes`, `note_id_recorded`, `no_forbidden_operations` |
| `publication_replay_proof` | behavior_evidence | `operation_id`, `note_count_before`, `note_count_after`, `replay_samples`, `attested_by` | `note_count_unchanged`, `no_placeholder` |

**T6（三方）**

| record_key | kind | 必需字段 | 机械检查 |
|---|---|---|---|
| `access_scope_vocabulary` | design_decision | `vocabulary`, `authorization_semantics`, `storage_services_implemented`, `nonexistence_leak_prevented`, `decided_by`, `decided_at` | `no_placeholder`, `vocabulary_has_service_private` |
| `compat_freeze_record` | cross_review | `maintainer`, `freeze_date`, `attestations`, `allowlist_after_freeze` | `three_party_attested`, `allowlist_only_after_closure` |
| `mapping_fixtures` | mapping_fixture | `severity_fixtures`, `outcome_coverage_fixtures`, `unknown_value_refusal`, `attested_by` | `severity_covers_p0_p3_and_unknown`, `outcome_quadrants_present`, `unknown_severity_refused` |

### 1.2 AgentNexus 侧已经做掉、不需要外部提供的部分

这些不再算阻塞项（虽然 T 项整体仍开放，因为关闭要求"外部生产证据 + 三方签字"）：

- §15.2–15.7 与 RC2 §10.1 的读取上限/413、§7 幂等投影、事务内分配围栏：已实现并有测试（CP 记录逐条可复算）。
- CP-01～26 的 **AgentNexus 侧一半**：已执行并留档；其中 5 项（CP-06/12/13/15/21）明确标为"本仓无证据"、6 项标为"部分"，二者都不计入通过。
- 采集 pin 纪律：pin 保持原值，版本漂移只以追加 `profile_manifest_rechecks` 记录（本文件对应 semantic.15→16 的一次）。

## 2. 第 3 步：compatibility 冻结预检

### 2.1 冻结的前置条件（全部满足才允许改动 `default_decision`）

1. `T1–T6.status` 全部为 `closed`，且由 `tools/check_evidence.py` 计算（不接受本文件或清单自述）；
2. `T6.compat_freeze_record` 存在且 `three_party_attested` + `allowlist_only_after_closure` 两项检查通过；
3. `CP-01～26` 在门禁允许范围内执行并留档（AgentNexus 侧已完成；其余部分见 §1）；
4. `tools/validate.py` 通过（含 manifest 摘要一致、契约错误表 24 码一致）。

### 2.2 冻结时各方需要给出的输入

| 提供方 | 输入 | 落到 `compatibility.json` 的哪一段 |
|---|---|---|
| Nexus_Agent | 生产方 schema 版本清单、contract revision 清单、对应真实响应样例（T1/T2） | `nexus.schema_versions`、`nexus.contract_revisions`、`nexus.observed_contract.operative_allowlist` |
| Hczj_Assistant_Agent | severity 与 outcome/coverage 映射 fixture、`artifact_ref.access_scope` 词表及授权语义（T3–T6） | `externally_owned_vocabularies.artifact_access_scope`、`externally_owned_vocabularies.operative_allowlist`、`T6.mapping_fixtures` |
| AgentNexus | 适配器版本（规范包版本 + 已提交 git revision）、摘要算法与绑定 revision、CP 执行记录 | `adapter.version`、`adapter.evidence`、`binding.status` |
| 三方 | `compat_freeze_record`（维护者、冻结日期、三方签字） | `binding.status` → frozen，并解除 §15.1 的集成运行限制 |

### 2.3 防"提前放行"的机械底线（已接上）

- `tools/validate.py` / `check_evidence.py`：T1–T6 未全部关闭时，`nexus.observed_contract.operative_allowlist` 必须为 `false`、`artifact_access_scope` 必须为空，否则直接失败（评审"提前放行"检查）。
- 新增 `tests/test_code_review_cp_matrix.py::test_compatibility_allowlists_stay_empty_while_gate_closed`：把同一底线做成回归用例——`default_decision` 必须为 `reject`、`wildcards_allowed` 必须为 `false`、两个 `operative_allowlist` 必须为 `false`、`schema_versions`/`contract_revisions`/`artifact_access_scope` 必须为空，且 `gate.status` 必须为 `closed`。**任何人在 T1–T6 关闭前把允许列表填上，这条用例立刻变红。**
- `adapter.unimplemented_requirements` 由"§15.2–15.7 未实现"改为空列表，同时新增 `implemented_requirements` 与 `non_claims`：既不再留**已经过时**的"未实现"声明，也不把实现说成符合性。

### 2.4 冻结程序（建议顺序）

1. 外部方按 §1 填写 `received/T{n}.json`，并在 `closure-checklist.json` 把对应 `items[].status` 改到与实际一致；
2. 本仓跑 `check_evidence.py --require-host-audit`（应 exit 0 且逐项显示 closed）；
3. 三方签署 `T6.compat_freeze_record`；
4. 才允许填写 `compatibility.json` 的允许列表并置 `operative_allowlist=true`，同时登记 `adapter.version`；
5. 重新生成 manifest、刷新采集 pin 复核记录、跑 `validate.py`，然后提交**开门评审**。

## 3. 本仓不能做、必须由外部完成的事（阻塞）

- **生产/部署证据**：本工作区没有 Nexus/HCZJ 的部署实例、真实 GitLab 写入权限与生产凭据；沙箱也无法代跑其完整套件（在外部仓库跑测试时 `tmp`/`tempfile` 被拒，`WinError 5`）。因此 T1–T5 的 `production_sample` 类要求只能由对应 owner 提供。
- **三方签字**：`T6.compat_freeze_record` 与 `access_scope` 词表是协议决定，不能由 AgentNexus 单方给出。
- **旧 JUnit/HTTP 样例重跑**：`docs/evidence/l0-2026-09-21` 仍是 `semantic.9` 时期产物，本轮**没有**重跑，采集 pin 保持原值；不得据此推断新版兼容。

## 4. 复算命令

```bash
python scripts/run_cp_matrix.py --list-tests
$env:PYTHONIOENCODING='utf-8'
python -m pytest <上一步输出的 node id> -q -p no:cacheprovider --tb=no -rA > .pytest_cp_report.txt 2>&1
python scripts/run_cp_matrix.py --input .pytest_cp_report.txt --date <YYYY-MM-DD>
python specs/profiles/code-review/v1/tools/validate.py
python specs/profiles/code-review/v1/tools/check_evidence.py --require-host-audit
python -m pytest tests/test_code_review_cp_matrix.py -q -p no:cacheprovider
```
