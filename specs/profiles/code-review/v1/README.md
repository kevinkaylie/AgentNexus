# Code Review Collaboration Profile v1 — 规范包（语义冻结候选）

- **Profile 版本**：`agentnexus.code-review/1.0-draft.2`
- **包版本**：`1.0-draft.2+semantic.14`
- **状态**：语义件已冻结为候选；**L0 wire binding 未定版**（RC2 契约已复核：RC1 的 Q1–Q3/S1–S7 全部关闭、文本层面无阻塞项，但 BINDING-GATE-1 维持关闭；见 `bindings/l0-service-contract.md` §9/§11）；**未声明实现符合性**
- **规范正文**：[`docs/design/code-review-collaboration-profile-v1.md`](../../../../docs/design/code-review-collaboration-profile-v1.md)（本文档是唯一规范来源，本包只是它的机器可读投影）
- **职责依据**：[ADR-015](../../../../docs/adr/015-code-review-state-authority.md)

## 1. 目录

| 路径 | 内容 |
|---|---|
| `schemas/` | 15 个 JSON Schema（Draft 2020-12）：信封与 10 类消息、`artifact_ref`、`evidence_ref`、`error`、`common` |
| `fixtures/valid/` | 9 个正例：`review_request → assignment → acceptance → delivery → report(partial/inconclusive) → receipt` 一条一致链，外加 `issues_found` 报告、"有发现且覆盖不足"（`09`，findings + inherited_gap ⇒ issues_found + partial）与 `freshness_unknown` 错误 |
| `fixtures/invalid/` | 14 个结构反例，每条对应一条 Profile MUST 或 binding 规则，见 `fixtures/index.json` 的 `rule` |
| `fixtures/index.json` | fixture → schema 绑定 + 反例所违反的规则（机器校验范围仅限 `valid/` 与 `invalid/`） |
| `fixtures/binding/` | **行为验收规范（Markdown）**：如 `q3-outcome-coverage.md`（HCZJ 转换与呈现四组用例）。**不经 schema 校验、不由 validate.py 执行**，仅由 manifest 固定摘要；实施后须登记命令与实际结果 |
| `fixtures/cp-matrix.json` | CP-01～26 的 kind（structural / digest / behavioral）、阶段、期望与引用（可用 `#anchor` 指向 `fixtures/binding/` 中的具体用例） |
| `fixtures/digest_vectors.json` | §15.3 字节口径的摘要向量（CP-23/CP-26），含真实 SHA256 值与两个反例向量 |
| `bindings/l0-agentnexus-http.md` | L0 binding **草案**（AgentNexus 侧映射 + 外部 TBD 清单 + 契约指针） |
| `bindings/l0-service-contract.md` | **RC2 三方服务接口契约**（新增端点、认证、DTO、ACK、CAS、错误与发布恢复）；评审记录见其 §9（RC1）与 §11（RC2 复核）：**文本层面无阻塞项，但 binding 仍不得定版** |
| `bindings/external-confirmations-2026-09-20.md` | 跨项目确认记录（T1–T7 结论 + 必须解决的语义差异；明确"门禁 1 未关闭"） |
| `bindings/evidence/` | **T1–T6 关闭证据采集包**：`closure-checklist.json`（唯一收口追踪器，25 条证据要求）、`templates/T1–T6.json`（待填表单）、`received/`（回填落点）。由 `tools/check_evidence.py` 机械校验 |
| `bindings/source-evidence.json` | 本次核对的外部仓库文件摘要（12 条，**已由评审 Agent 在本机逐一重算验证 12/12 相符**） |
| `compatibility.json` | 允许的 Nexus 版本/契约 revision、适配器版本、摘要口径、强制能力注册状态。**默认空列表 = 拒绝全部** |
| `manifest.json` | 文件摘要 + 包版本 + 来源 Git revision（由 `tools/make_manifest.py` 生成） |
| `tools/validate.py` | 规范包自检：schema/fixture/向量/契约错误表/T1–T6 收口清单/manifest |
| `tools/check_evidence.py` | T1–T6 收口校验：重算原始字节摘要、拒绝虚假关闭与提前放行 |
| `tools/make_manifest.py` | 生成/刷新 `manifest.json` |

## 2. 本包覆盖什么、不覆盖什么

| 层 | 是否覆盖 | 说明 |
|---|---|---|
| 结构（字段、类型、枚举、必填、互斥、跨字段蕴含） | ✅ 覆盖 | JSON Schema。§6.3 的 outcome/coverage 不变式、§15.8 的 inherited_gap 上限、usage 的 known/unknown 区分、§5.1 的"不得以 0 代表未知"等均已编码为 schema 规则 |
| 摘要口径 | ✅ 覆盖 | `fixtures/digest_vectors.json` 用真实 SHA256 固定 §15.3 的 B 口径，并给出"重序列化会改变摘要"的反例 |
| 行为语义（状态机、租约、CAS、幂等冲突、发布未知、角色授权） | ❌ 不覆盖 | 必须由行为测试承担；`cp-matrix.json` 中 `kind=behavioral` 的用例即清单 |
| wire 承载（端点、认证、ACK、超时、错误映射） | ❌ 不覆盖 | `bindings/l0-agentnexus-http.md` 是草案，定版前不得据本包启动集成运行 |
| 实现符合性 | ❌ 不覆盖 | AgentNexus 侧改造（§15.2–15.7）尚未实现，见 `compatibility.json` 的 `adapter.unimplemented_requirements` |

## 3. 自检

```bash
python specs/profiles/code-review/v1/tools/validate.py
```

期望输出：`[PASS] package self-check passed`。自检覆盖：schema 唯一 `$id`、正例全通过、**反例全部被拒**（若某反例竟然通过，说明 schema 漏掉了该 MUST）、无孤儿 fixture、摘要向量一致、CP 矩阵引用存在、**契约 §7 错误表与本包 `error.schema.json` 枚举一致（含 413 与 `scope=read_limit` 标注）**、**T1–T6 收口清单自洽且无提前放行**、manifest 摘要一致。

> 自检工具曾在编写期抓到 3 个真实缺陷并被修复：`evidence_ref` 根级 `additionalProperties:false` 误拒分支属性（导致两个报告反例"因错误原因失败"）、摘要向量的变换标识不可机读、cp-matrix 路径前缀重复。这一过程说明"反例必须因预期原因失败"应作为固定检查项。
>
> 契约错误表检查（评审 R2-1/R2-2）也做过**负例验证**：注入未登记码、删除 `scope=read_limit` 标注、删去一条已登记码的表行，三种情形均正确报错。
>
> T1–T6 收口校验的负例验证见 `tests/test_code_review_evidence_checklist.py`（19 项）：摘要填错、长度填错、残留 `__TODO__`、缺必需字段、缺用例覆盖、声明与实际不一致、`operative_allowlist` 提前放行、门禁提前开启、模板缺 record key、未登记检查名，均被拒绝；证据完整时关闭被接受。

注：`date-time` 的严格格式校验依赖可选的 `rfc3339-validator`；未安装时 schema 中的 `pattern: "Z$"` 仍在检查 UTC 形状。

## 4. 冻结与引用规则（§15.9）

1. 本包是**只读版本包**：其他仓库按"版本 + 摘要"引用，不得各自修改后仍使用同版本名。
2. 任何改动都必须：更新 `manifest.json`（`tools/make_manifest.py`）→ 重跑 `validate.py` → 变更 `package_version`。
3. `compatibility.json` 的默认决策是 `reject`；**禁止**为了"先跑起来"改成通配。
4. 冻结发布必须登记**已提交的 Git revision**；若 `manifest.source.worktree_dirty=true`，该包只是候选，不是发布件。

## 5. 外部核对与剩余门禁

2026-09-20 已完成双方源码核对并各自登记确认记录，见 [T1–T7 结论与证据](bindings/external-confirmations-2026-09-20.md)。T7 设计范围已确认；T1–T6 仍有开放项。源码观察到 revision=3，但生产方样例与适配验证不足，运行允许清单保持为空。

**T1–T6 的收口唯一追踪器是 [`bindings/evidence/closure-checklist.json`](bindings/evidence/closure-checklist.json)**：25 条证据要求，逐条写明责任人、采集模板与机械验收条件（原始字节重算摘要、部署版本证据、拒绝例）。采集与回填方式见 [`bindings/evidence/README.md`](bindings/evidence/README.md)。「源码已确认」既不等于「生产样例已取得」，也不等于「实现已验证」；声称关闭却拿不出证据会被 `tools/check_evidence.py` 直接拒绝。

见 `compatibility.json` 的 `nexus.*` 与 `bindings/l0-agentnexus-http.md` §7（T1–T7）：Nexus 的事件与证据查询端点、允许的 `contract_revision` 取值、HCZJ 的 Run/Attempt/activation API、发布适配器归属、`access_scope` 词表，以及 L0 是否允许无 TLS 的本机 HTTP。

在这些关闭之前：**不得声明 wire conformance，不得声明实现符合性**，只允许独立语义验证开发（Profile §15.1）。

## 6. L0 接口契约 RC1

见 [三方服务接口契约](bindings/l0-service-contract.md)，新增接口尚未实现、待评审。现有语义 schema 未变，包升级 semantic.3。

2026-09-20 RC2：Q1–Q3/S1–S7 已修订并提交复核，原评审记录保留；包版本 semantic.5。binding 未定版，行为用例尚未执行。

2026-09-20 semantic.9/10：Profile 适配器通用化（`review_provider_adapter` 接口 + HCZJ 为其一实现，严重度映射改为厂商无关 `priority_to_severity`）；新增 T1–T6 关闭证据采集包与 `tools/check_evidence.py`。binding 仍未定版，BINDING-GATE-1 维持关闭。

2026-09-21 semantic.14（按代码评审 B9/B10/S3 修订）：收口裁判的**拒绝事实改为样例级校验**（HTTP 状态 + 冻结错误信封 + 错误码枚举；不再接受布尔或文字自述）；宿主证据审计与可移植自检分离（复制包到任意目录后 `validate.py` 仍通过，中央仓库可用 `--require-host-audit` 收紧）；采集 pin 不再改写，改为「保留原 pin + `profile_manifest_rechecks` 复核记录」，并新增 `capture_package_version` 以可判定 pin 是否被改写。评审记录：`docs/reviews/2026-09-21-l0-overall-code-review.md`。
