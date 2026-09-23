# 代码评审请求：Profile 适配器泛化 + T1–T6 收口准备（含同工作区其他改动）

| 项 | 值 |
|---|---|
| 记录号 | CR-REVIEW-2026-09-21-01 |
| 提交方 | 开发 Agent |
| 提交日期 | 2026-09-21 |
| 基线 revision | `85d3c15`（`main`，2026-07-29） |
| 变更规模 | 23 个已跟踪文件修改（+815 / −30）+ 21 项新增（未跟踪） |
| 评审类型 | 代码评审（触发条件：新功能实现完成 / HTTP API 变更 / 多模块重构 / 权限变更） |
| 依据流程 | `docs/agent-workflow.md` 代码评审流程与 7 项检查清单 |

> **本文件是评审请求，不是评审记录。** 评审结论应由评审 Agent 独立给出并记录在 `CHANGELOG.md` 与本文件末尾的"评审结论"占位处；提交方不对自己的代码出具结论。

---

## 0. 复现命令

```bash
# 1. 全量回归门禁（硬规则，评审前置条件）
python -m pytest tests/ -q -p no:cacheprovider --tb=no > .pytest_full_report.txt 2>&1
python scripts/check_full_suite.py --input .pytest_full_report.txt   # 0=通过 1=回归 2=基线需维护

# 2. 规范包自检（含 T1–T6 收口裁判）
python specs/profiles/code-review/v1/tools/validate.py

# 3. 收口裁判单独运行（用于对照"声明 vs 实际"）
python specs/profiles/code-review/v1/tools/check_evidence.py

# 4. 新增测试
python -m pytest tests/ -q -p no:cacheprovider -k code_review   # 127 collected
```

### 本次门禁汇总行（硬规则要求）

```
全量结果：654 passed, 9 skipped, 13 failed, 19 errors
基线：654 passed, 25 条登记的环境性失败
[PASS] 全量结果与基线一致：无未登记失败，通过数未下降。   exit 0
```

规范包自检：

```
[PASS] package self-check passed (structure + digests).   exit 0
       schema 15、正例 9/9、反例 14/14、CP 矩阵 26、契约错误码 24、收口清单自洽、manifest 61/61
```

**基线变更声明**：`tests/full_suite_baseline.json` 的 `counts.passed` 由 626 改为 654（本次新增 28 项测试）。`environmental_failures` **未新增、未删除任何一条**。基线总失败数仍为 25 条环境性失败（沙箱禁止创建子进程 + 工作区外临时目录不可访问），已在 `tests/CLAUDE.md` 逐条归因。

---

## 1. 评审范围与文件清单

按用户要求，**本工作区全部改动一并评审**，不划分"相关/无关"。共三组。

### A 组：运行时代码（`agent_net/`、`tests/`、`scripts/`）

**A1 新增模块（`agent_net/code_review/` 8 文件 / 1547 行）**

| 文件 | 行数 | 说明 |
|---|---|---|
| `agent_net/code_review/provider_adapter.py` | 393 | **新增**。`ReviewProviderAdapter` 基类 + provider 注册表 + 厂商无关入口 `build_profile_report(...)` |
| `agent_net/code_review/validation.py` | 508 | 信封解析、报告 5 条不变式、§15.2 状态翻译（**已删除** `NEXUS_SEVERITY_MAP` / `nexus_severity_to_profile`） |
| `agent_net/code_review/errors.py` | 149 | `code_review.error.v1`、24 码、读取上限、`data_policy_denied` 三类 scope |
| `agent_net/code_review/presentation.py` | 130 | **新增**。呈现与发布前校验，与 provider 解耦 |
| `agent_net/code_review/__init__.py` | 105 | 导出 |
| `agent_net/code_review/authz.py` | 100 | 角色与回执 kind 授权 |
| `agent_net/code_review/digest.py` | 92 | §15.3 字节口径 |
| `agent_net/code_review/hczj_adapter.py` | 70 | **重写**为薄声明（原实现迁入 provider_adapter） |

**A1' 其他新增运行时文件**

| 文件 | 行数 | 说明 |
|---|---|---|
| `agent_net/persistence/code_review_store.py` | 1078 | **新增**。Profile 会话/交付/回执/消息/授权/强制能力，单事务 CAS |
| `agent_net/node/routers/code_review.py` | 496 | **新增**。A/messages、A/artifacts、raw 端点与错误信封 |

**A2 既有模块修改**

| 文件 | 变更量 | 关注点 |
|---|---|---|
| `agent_net/node/routers/coordination_executions.py` | +88 | Profile 绑定执行的交付专用路径 |
| `agent_net/node/execution_backends/local_cli.py` | +57 | `_apply_profile_translation`（两条分支） |
| `agent_net/persistence/schemas.py` | +144 | 6 张新表 + artifacts/executions 新列 |
| `agent_net/persistence/coordination.py` | +32 | 显式导入列表（避免 `store_message` 同名覆盖回归） |
| `agent_net/persistence/objective_store.py` | +15 | `SELECT`/行映射扩展 |
| `agent_net/persistence/deliverable_store.py` | +33 | 同上 + `create_artifact` 新参数 |
| `agent_net/node/routers/coordination_records.py` | +12 | 旧 `/coordination/receipts` 拒绝 Profile 会话 |
| `agent_net/node/daemon.py` | +4 | 挂载 Profile router 与错误处理器 |
| `agent_net/persistence/database.py` | +2 | 初始化调用 |

**A3 测试与脚本**

| 文件 | 行数 / 用例 |
|---|---|
| `tests/test_code_review_profile.py` | 370 行 / 40 |
| `tests/test_code_review_store.py` | 467 行 / 17 |
| `tests/test_code_review_api.py` | 481 行 / 12 |
| `tests/test_code_review_delivery.py` | 411 行 / 10 |
| `tests/test_code_review_q3_harness.py` | 460 行 / 12 (+1 skip) |
| `tests/test_code_review_provider_adapter.py` | 340 行 / 7 |
| `tests/test_code_review_evidence_checklist.py` | 423 行 / 28 |
| `tests/conftest.py` | +48（**探针式** `tmp_path` 兜底） |
| `scripts/check_full_suite.py` | **新增** 229 行（全量门禁判定，exit 0/1/2） |
| `scripts/run_q3_harness.py` | **新增** 382 行（q3 执行记录生成） |

合计 **127 项** code-review 测试 + 1 skip。

### B 组：规范包与文档

| 路径 | 说明 |
|---|---|
| `specs/profiles/code-review/v1/` | **新增** 64 文件 / 6174 行，`1.0-draft.2+semantic.10` |
| ├ `schemas/`（15） | JSON Schema Draft 2020-12 |
| ├ `fixtures/`（28） | 正例 9 + 反例 14 + index/cp-matrix/digest_vectors + binding 行为规范与执行记录 |
| ├ `bindings/`（13） | L0 binding、RC2 服务契约、跨项目确认、源码证据、**evidence/ 收口包（9 文件）** |
| ├ `tools/`（5） | `validate.py`、`make_manifest.py`、**`check_evidence.py`（870 行）** 等 |
| `docs/evidence/l0-2026-09-21/` | **新增** 7 文件 / 739 行（外部双方本地实施证据包，`production=false`） |
| `docs/design/code-review-collaboration-profile-v1.md` | **新增**（Profile 规范正文，§15.9 状态段本次更新） |
| `docs/design/design-code-review-v1.md` | **新增**（需求/设计草案） |
| `docs/adr/015-code-review-state-authority.md` | **新增**（ADR-015，已采纳） |
| `docs/contracts/code-review-collaboration.md` | **新增**（三方契约登记） |
| `docs/api-reference.md` | +56（L0 端点、角色、错误信封、可插拔 provider） |
| `docs/reviews/2026-09-21-l0-adapter-and-closure-review-request.md` | **新增**（本文件，329 行） |
| `docs/agent-workflow.md`、`docs/design.md`、`docs/quickstart.md`、`docs/requirements.md`、`AGENTS.md`、`CLAUDE.md`、`tests/CLAUDE.md`、`CHANGELOG.md`、`docs/wip.md`、`docs/project-status.md` | 文档同步 |
| `.gitignore` | +8（沙箱临时目录与全量报告） |

### C 组：同工作区其他改动（一并评审）

| 文件 | 变更量 | 提交方对本组的认知 |
|---|---|---|
| `.agentnexus/local-runner.yaml` | +32 / −16 | **非本批工作产物**，同工作区既有改动。已就约束语义做实测核对，见 §5.1 |
| `threads/README.md` | +32 / −16 | **非本批工作产物**。外部社区线索台账，含公开披露相关问题，见 §5.2 |
| `docs/community/`（5 文件 / 2448 行） | 新增 | **非本批工作产物**。GitHub Discussions 草稿与 RFC 评审帖，见 §5.2 |

> 提交方无法为 C 组提供设计意图或变更理由；仅提供事实核对结果与风险提示，请评审方按同样标准审查并判定是否应与 A/B 组同批提交。

本评审请求文件自身（`docs/reviews/2026-09-21-l0-adapter-and-closure-review-request.md`）亦属本次新增，供评审方核对"提交方自述"与"代码事实"是否一致——**若发现本文与代码不符，应以代码为准并按阻塞项处理**。

---

## 2. 变更意图

### 2.1 A1 组：适配器泛化

**问题**：原实现把 Nexus/HCZJ 的字段名、outcome 词表与严重度映射硬编码在 AgentNexus 源码里（`NEXUS_SEVERITY_MAP`、`nexus_severity_to_profile`）。第二家评审方接入必须改核心。

**做法**：抽出 `ReviewProviderAdapter` 接口，HCZJ 降为其中一个实现（薄声明 + 注册）。厂商无关不变式（outcome 推导、覆盖不得提升、finding 必须有证据、溯源）由基类收敛，子类只能提供映射钩子并声明词表。严重度映射改为 `priority_to_severity(priority, *, mapping=None, scope=...)`，未知词元拒绝、不降级。

**证据**：`tests/test_code_review_provider_adapter.py` 注册了第二个 provider（ACME：`acme.review.v2`、outcome `defects|clean|unknown`、severity `S1–S4`、字段名全不同），走通同一条管线。

**重构期自查修掉的两个真实缺陷**：
1. 子类覆写 `normalize_coverage` 即可绕过"覆盖不得提升" → 规则下沉到基类 `_finalize_coverage`；
2. `provenance()` 硬编码假设存在 `status` 键 → 改为 provider 声明 `native_status_key` / `native_outcome_key`。

### 2.2 B 组：T1–T6 收口准备

**问题**：T1–T6 关闭状态此前唯一的进度信号是 binding 文档自述的"契约定义已补齐"，而该文档在设计上不含生产样例——容易把"源码已确认"读成"已关闭"。

**做法**：新增唯一收口追踪器 `bindings/evidence/closure-checklist.json`（25 条证据要求），配采集模板与机械裁判 `tools/check_evidence.py`（重算原始字节摘要、拒绝虚假关闭、拒绝提前放行 `compatibility.json`）。既有本地证据包 `docs/evidence/l0-2026-09-21/` 逐项登记为 `non_closing`，并机械保证其 `production=false` 标签不可改写。

**边界**：交付的是"关闭的入口与裁判"，**不是关闭本身**。T1–T6 六项全部开放，BINDING-GATE-1 维持关闭。

---

## 3. 验证证据

| 验证项 | 命令 | 结果 |
|---|---|---|
| 全量门禁 | `pytest tests/ -q …` + `check_full_suite.py` | `654 passed, 9 skipped, 13 failed, 19 errors` → `[PASS]` exit 0 |
| 规范包自检 | `tools/validate.py` | `[PASS]` exit 0；61/61 manifest |
| 收口裁判 | `tools/check_evidence.py` | `[PASS]` exit 0；`0/6 已关闭` |
| 收口裁判负例 | `tests/test_code_review_evidence_checklist.py` | 28 passed |
| 适配器可插拔性 | `tests/test_code_review_provider_adapter.py` | 7 passed |
| 包覆盖完整性 | 脚本比对磁盘与 manifest | 磁盘有而 manifest 未登记：仅 `manifest.json` 与 2 个 `__pycache__/*.pyc`（均为设计排除）；反向 0 项 |

**未验证**：未在非沙箱环境跑全量；未复跑 Nexus/HCZJ 两仓库测试；未做真实部署或三方 wire 联调。规范包 `manifest.source.worktree_dirty=true` → 属**候选**，非发布件。

---

## 4. 提交方自查发现（请评审方确认等级）

### 4.1 提交方建议定为**阻塞性**

**S-1 三个"自述型"检查可被绕过**（`tools/check_evidence.py` + `closure-checklist.json`）

| 位置 | 现状 | 漏洞 |
|---|---|---|
| `T5.publisher_ownership` | `check_worker_refusal_evidenced` 只断言布尔 `worker_refusal_evidenced: true` | `refusal_sample_bytes_b64` **不在 `required_fields`**，填写方删除该键即可通过，无任何拒绝字节被验证 |
| `T4.receipt_issuance_authority` | 要求存在名为 `forged_receipt_rejected` 的样例 | **不检查其 `response_status`**：一个 200 的样例挂上该名字即可通过 |
| `T3.service_auth_contract` | `check_must_refuse_when_unconfigured` 做**文本包含判断**（含"拒绝"/"401"/"403"字样） | 不是样例验证，可用任意文字满足 |

建议：三者统一改为"必须存在对应样例 + `response_status ∈ {401,403}` + 可从该字节解析出 `code_review.error.v1` 信封"，并补负例测试。

**S-2 `REPO_ROOT = BASE.parents[3]` 是硬编码层级假设**（`tools/check_evidence.py`）

规范包的设计用途是被其他仓库按"版本 + 摘要"引用（包 README §4）。一旦包被放在不同路径，`REPO_ROOT` 指向错误位置，`check_local_evidence_package` 必然报"本地证据包不存在"→ **外部副本跑 `validate.py` 会失败**。

该缺陷已被提交方自己的测试证明：`tests/test_code_review_evidence_checklist.py::test_local_evidence_package_must_exist` 断言此情形返回 1。

建议：清单中的 `local_evidence_package` 是 AgentNexus 仓库独有的引用，应在包外缺省为"跳过"而非"失败"，或加"仅当仓库根可识别时才校验"的守卫。

### 4.2 提交方建议定为**建议性**

**S-3 `min_samples` / `required_case_coverage` 依赖列表键顺序推断**：`SAMPLE_LIST_KEYS = (samples, replay_samples, fixtures, vectors)`，取第一个存在的列表。若某 record 同时含 `samples` 与 `fixtures`，只校验前者。当前模板恰好未触发。

**S-4 提交方改写了他人证据文件** `docs/evidence/l0-2026-09-21/source-snapshot.json`：新增 `profile_manifest_refreshed`（保留旧值 69d374…、写明包版本前后与原因）、刷新 `profile_manifest_sha256`，并用 `json.dumps(indent=2)` **重写了整个文件**（键序保留，但格式细节可能变化）。虽已留痕，但程序上应经证据所有者确认。建议评审判定是否改为"仅告警、由所有者刷新"。

**S-5 manifest 漂移只告警不失败**（`[WARN]` 而非 exit 1）：理由是每次包升级都会漂、避免门禁噪音；代价是漂移可长期不处理。请判定是否应强失败或限定刷新窗口。

**S-6 `validate.py` 通过 importlib 加载 `check_evidence.py`，会在只读版本包目录生成 `tools/__pycache__`**。`.gitignore` 已覆盖、manifest 不登记、摘要不受影响，但"只读包被写入"原则上有瑕疵。建议加 `sys.dont_write_bytecode = True`。

**S-7 测试用 monkeypatch 模块全局变量重定向路径**，与 `validate.py` 的 importlib 加载方式不完全一致，存在"测试路径 ≠ 生产路径"的风险。建议给 `check_evidence.py` 加 `--root` 参数或纯函数入口。

**S-8 清单中 `no_placeholder` / `sample_bytes` 是 no-op 标记**（实际由通用规则执行），语义上误导。建议显式执行或从清单移除。

### 4.3 提交方建议定为**信息性**

**S-9 通过校验 ≠ 证据为真**（设计边界，需确认文档是否足够显眼）：`required_case_coverage` 只查用例**存在性**不查内容；`artifact_digest_matches_raw` 只比较记录内两个字段相等，**不验证二者来自同一报告**（记录可自洽地填错）；`covers_endpoints` 只做端点字符串归一化匹配。`bindings/evidence/README.md` 已写"不判断证据内容的业务正确性"，但 `l0-agentnexus-http.md` §7 未作同等声明，存在被读成"行为已验证"的风险。

**S-10 版本号语义**：本批同时含"收口清单"与"证据包引用修复"，合并为 `semantic.10`。是否应拆分由评审判定。

**S-11 `CHANGELOG.md` 顶部存在一个不在 `## [Unreleased]` 下的条目**（2026-09-21 L0 外部端点实现）。既有格式异常，提交方未修，请判定是否应由本批修正。

**S-12 `docs/project-status.md` 语义修改**：把"RC2 待评审复核"改为"已通过复核"，并移除 `semantic.5` 版本号信息。依据是契约 §11 确已复核，但这是状态源文件的语义变更，请确认未丢失历史信息。

**S-13 工作区遗留沙箱临时目录**：`.probe_*`、`.pytest_bt_*`、`.pytest_cache`、`.pytest_root`、`.pytest_scratch`、`.pytest_tmp` 均存在且**不可读**（沙箱权限），已被 `.gitignore` 覆盖、不出现在 `git status`。来源是 `tests/conftest.py` 的 `tmp_path` 兜底与 `validate.py` 的 `__pycache__` 写入。是否需要清理或改进兜底实现（避免在工作区留残留），请判定。

---

## 5. C 组改动专项分析

### 5.1 `.agentnexus/local-runner.yaml`

**变更内容**：切换 `secretary_agent` DID；移除 `owner_did`（注释称改由 `--owner` 传入以跳过 reconcile）；`timeout_sec` 300→60；新增 `max_total_executions: 30`、`max_wall_clock_sec: 3600`、`max_output_bytes: 1048576`、`network_access: deny_by_default`；worker `fake_dev`→`fake_all`，新增 `worker_did`、`worker_type: interactive_cli`、`output_contract: agentnexus_json_v1`，扩角色与能力。

**提交方实测核对结果**：

| 键 | 是否被代码读取 | 是否**被强制** |
|---|---|---|
| `max_total_executions` | ✅ `local_runner.py:84`、`loop_engine.py:122` | ✅ |
| `max_wall_clock_sec` | ✅ `local_runner.py:84`、`loop_engine.py:123` | ✅ |
| `max_output_bytes` | ✅ `local_runner.py:86`、`runner_loop.py:37` | ⚠️ 见 C-2 |
| `network_access` | ✅ `local_runner.py:86`、`runner_loop.py:39` | ❌ 见 C-1 |
| `worker_type` / `output_contract` | ✅ `local_runner.py:282` 等 | ✅ |
| `owner_did` 省略 | ✅ `local_runner.py:193-195` | 见 C-3 |

**C-1（提交方建议：阻塞性或至少必须在文档标注）`network_access: deny_by_default` 是"声明"而非"强制"**

`grep` 全仓结果：`network_access` 只出现在 `local_runner.py`（配置加载）与 `runner_loop.py:_build_constraints`（合并后放进 constraints、进而进入 worker prompt）。**`execution_backends/local_cli.py` 从不读取该键**——它是 argv 子进程执行器，无法限制子进程的网络访问。也就是说：配置文件与提示词声明"默认拒绝网络"，但被启动的 CLI 子进程**仍可自由联网**。

这与本项目在 Profile §15.5 一贯坚持的"declared_only 不得当作 enforced"是同一类风险。建议：要么在该 YAML 或 `agent_net/CLAUDE.md` 明确标注该键为 `declared_only`，要么在 `LocalCLIBackend` 中真正落地（或以"无法强制"为由拒绝启动要求该约束的执行）。

**C-2（提交方建议：建议性）`max_output_bytes` 的截断单位与命名不符**

`local_cli.py:490/492/595/596/609/610` 统一为 `stdout.decode("utf-8", errors="replace")[:self.max_output_bytes]` —— 对 **`str` 按字符数**切片，而字段名为 `max_output_bytes`、YAML 值为 `1048576`（字节口径）。对多字节 UTF-8 内容，实际截断上限会显著大于声明的字节数（最坏约为 4 倍）。建议改为对 bytes 切片或重命名并声明单位。

**C-3（提交方建议：信息性）省略 `owner_did` 会同时跳过 owner 绑定校验**

`local_runner.py:193-195`：`owner_did` 为空即返回 `"No owner_did in config; skipping Worker Registry reconciliation."`。被跳过的路径中包含 `local_runner.py:266-270` 的 owner 绑定一致性检查（注册 worker 的 `owner_did` 必须与配置一致）。YAML 注释对此有说明，属有意为之；请确认该文件不用于任何 gated/演示/CI 路径，否则等于默认关闭一项绑定校验。

### 5.2 `threads/README.md` 与 `docs/community/`

**内容性质**：`threads/README.md` 是外部社区线索台账（含真实仓库/Issue 编号、最后检查时间、后续跟进任务清单），使用内部角色化称谓（"陛下"/"臣"）。`docs/community/` 是 5 份中英双语 GitHub Discussions 草稿（欢迎与规则、首帖、RFC-000/001/002 评审帖），其中链接指向 `github.com/kevinkaylie/AgentNexus`。

**C-4（提交方建议：阻塞性，需明确决策）公开披露边界未定义**

`AGENTS.md` 已有"仅本地保留（不提交 GitHub）"的分类机制（当前含 `docs/roadmap.md`、`docs/wip.md` 等）。本次改动把两类内容**同时**置于可提交状态，但 `AGENTS.md` 的分类表**未收录**它们，因此没有明确它们是"本地"还是"公开"：

- `threads/README.md`：含第三方仓库/Issue 编号与"我方已评论"的事实陈述、内部角色化称谓。若进入公开仓库，等于公开社区运营台账与内部协作语域。
- `docs/community/`：本身即公开发文草稿（意图是公开），但**其内容是否已获准对外发布**、发帖账号归属、以及是否与 `threads/README.md` 的内部台账构成不一致陈述，需产品/对外口径确认。

建议：无论结论如何，都应在 `AGENTS.md` 的"仅本地保留"表中**显式登记**两者的归属，避免下次提交时再次陷入"身份不明"。这属于流程缺口，而非代码缺陷。

**C-5（信息性）**`threads/README.md` 的表格中 `a2a-1713` 与已剔除的 `a2a-1672`、`A2A-1672` 大小写不一致，存在重复线索的来源歧义；台账已有一条"重复线索已合并"记录，建议统一 ID 大小写规范。

---

## 6. 已知边界：不得据本批推断的结论

1. **不得**据本批认为 T1–T6 已关闭、BINDING-GATE-1 已开启、或可声明 wire conformance。六项全部开放。
2. **不得**据 `compatibility.json` 的 `observed_candidates=["service_private"]` 认为 `service_private` 已放行。`operative_allowlist=false`、`artifact_access_scope=[]`，默认拒绝。
3. **不得**据 `docs/evidence/l0-2026-09-21/` 认为生产行为已验证。该包 `production=false`，为本地合成样例；其 `production=false` 标签由裁判机械保护，改写即失败。
4. **不得**据收口裁判通过认为证据为真。裁判只做形状与自洽性检查（见 S-9）。
5. 规范包为**冻结候选**（`worktree_dirty=true`），不是发布件。

---

## 7. 对照 `docs/agent-workflow.md` 代码评审检查清单

| # | 检查项 | 提交方自评（待评审推翻） |
|---|---|---|
| 1 | ADR/设计合规 | §15.2–15.7 已实现并有测试；ADR-015 双层状态权威未被改动；provider 泛化不改变 Profile 消息 schema 与状态权威 |
| 2 | 安全性 | 角色级写授权（`authz.py`）、旧 `/coordination/receipts` 拒绝 Profile 会话、§15.5 fail-closed（含重放复核）、服务端自算摘要、`data_policy_denied` 三类 scope、读取上限 413。**C 组存在 §5.1 的 C-1 强制缺口** |
| 3 | 正确性 | 单事务 CAS、幂等/冲突/纠正、epoch 单调、coverage 不得提升、outcome 推导。**S-1 三个检查可绕过** |
| 4 | 测试覆盖 | 127 项 + 1 skip；含负例验证（收口裁判 28 项、provider 泛化 7 项、q3 12 项） |
| 5 | API 一致性 | `docs/api-reference.md` 已同步 L0 端点、角色、错误信封与可插拔 provider 一节 |
| 6 | 代码规范 | 遵循 `CLAUDE.md` / `agent_net/CLAUDE.md`；显式导入避免星号导入同名覆盖（本次已修复过一次该类回归） |
| 7 | 全量回归证据 | 已附汇总行与 exit 0；基线 `environmental_failures` 未增删 |

---

## 8. 需评审方明确回答的开放问题

1. **S-1** 是否判为阻塞性？若是，要求提交方把三个检查改为样例级验证并补负例。
2. **S-2** 外部仓库引用本包时 `validate.py` 必然失败，是否判为阻塞性？
3. **C-1** `network_access` 属"声明而非强制"——判为阻塞性（须落地或标注 `declared_only`），还是可接受为本地开发配置？
4. **C-4** `threads/README.md` 与 `docs/community/` 的公开披露归属如何判定？是否要求本批**先分离提交**、待口径确认后再单独提交？
5. **S-4** 提交方改写他人证据包快照是否可接受？若否，是否要求回退为"仅告警"？
6. **S-10** `semantic.10` 是否应拆分为两次版本推进？
7. C 组（3 项）与 A/B 组是否应**同批提交**，还是要求拆分？提交方倾向拆分（C 组无设计意图可追溯），但按用户要求一并提交评审。
8. **S-13** 是否要求清理工作区遗留沙箱临时目录，或改进 `tests/conftest.py` 兜底以免再次遗留？

---

## 9. 评审结论

**第三轮最新结论（2026-09-22）**：[第三轮报告](2026-09-22-l0-r3-review.md)确认多项旧问题关闭及幂等头裁决落地，仍有 R3-1～R3-4（2 P1、2 P2）需修改后复审；生产门禁不变。下方保留前两轮历史结论。

**最新复审（2026-09-22）**：[第二轮整体评审](2026-09-22-l0-rereview.md)确认 B8/B10 对应代码缺陷关闭，仍有 R2-1～R2-6 六项阻塞残留，需修改后复审。独立全量 722 passed / 9 skipped，回归门禁 exit 0；Nexus/HCZJ 定向分别 12/25 passed。以下表格为首轮历史结论，保留供追溯。

> 由评审 Agent 填写。请按 `docs/agent-workflow.md` 的问题分类（阻塞性 / 建议性 / 信息性）逐条编号，并对上述 8 个开放问题给出明确答复。
>
> 结论落位：`CHANGELOG.md` 的记录区 + 本小节 + 必要时更新 `docs/wip.md`。

| 项 | 内容 |
|---|---|
| 结论 | 2026-09-21：需修改后复审；含此前 Nexus/HCZJ 实现的[整体评审记录](2026-09-21-l0-overall-code-review.md) |
| 阻塞项 | B1–B10：认证身份冒充、读取资源授权、上传/响应契约漂移、产物覆盖与幂等、payload schema 缺失、receipt 崩溃恢复、finding 静默丢失、HCZJ→Nexus 双鉴权接线、拒绝证据假通过、规范包不可移植。详见评审记录逐项位置、复现及修复要求。 |
| 建议项 | S1–S6：HCZJ reviewer 归属、C 组约束强制级别、采集 pin 与复核 pin 分离、环境基线维护、提交/公开材料归属、裁判及文档维护性。§8 八问已逐项作答。 |
| 门禁复核 | 独立全量 679 passed / 9 skipped，无失败；基线检查器进程 exit 2（25 个旧环境豁免失效，未改基线）；validate.py 与 check_evidence.py 均 exit 0；Nexus 定向 12 passed、HCZJ 定向 14 passed。T1–T6 全部开放，BINDING-GATE-1 维持关闭。 |
| 是否批准 | 否。需修复阻塞项、补负例和跨项目集成证据、维护过时基线后复审；单测和结构自检通过不等于 wire conformance。 |

---

## 10. 附：提交方对自身工作的三点声明

> 2026-09-23 评审方后续结论：见[第四轮复审](2026-09-23-l0-r4-review.md)。R3-1/R3-3/R3-4 原问题关闭；R3-2 尚存完整分配身份复检、锁等待期间期限判断两处缺口，需修改后复审。历史阻塞清单以各轮后续结论为准；BINDING-GATE-1 仍关闭。

> 2026-09-23 第五轮后续结论：见[第五轮复审](2026-09-23-l0-r5-review.md)。正常非空身份改绑与锁等待过期均已修复；空 Coordinator ID 可跳过事务比较（R5-1/P2），整体仍需修改后复审。第四轮结论保留为历史记录。

> 2026-09-23 第六轮后续结论：见[第六轮复审](2026-09-23-l0-r6-review.md)。R5-1 已关闭，本次代码修复通过评审；T1–T6 与 BINDING-GATE-1 仍开放。前述各轮结论保留为历史记录。

1. **角色纪律**：本文件由提交方撰写，不含评审结论。A/B 组的实现与文档同步由提交方完成；Profile 设计文档 §14 的评审记录属此前既有评审产物，本批未新增评审记录。
2. **自查而非自证**：§4 的缺陷是提交方主动查找的结果，其中 S-1、S-2 是会导致**假通过**的真实漏洞。提交方未在提交前修复它们，理由是把"裁判本身是否可信"交给评审判定比单方面修完更符合分工；若评审认为应先修后审，提交方接受。
3. **C 组免责范围**：提交方无法为 C 组提供设计意图、变更理由或回归证据；§5 仅含事实核对与风险提示。
