# 三方代码评审协作契约登记

状态：1.0-draft.2，2026-09-18，**设计已评审通过**（Profile §14.10、ADR-015 已采纳）；尚无 wire binding/符合性声明，L0 binding 需单独评审定版。

参与方：Nexus_Agent（扫描证据）、HCZJ_ASSISTANT_AGENT（评审状态权威）、AgentNexus（协作适配）。

规范正文唯一来源：[Code Review Collaboration Profile v1](../design/code-review-collaboration-profile-v1.md)。职责提案：[ADR-015](../adr/015-code-review-state-authority.md)。Run 身份沿用外部已确认记录 RUN-ID-2026-09-14，不以本登记重新定义该身份。

当前已明确字段、摘要、角色与状态决议；实施前需复核 ADR/设计、定版 L0 binding 和机器可读兼容清单。schemas/fixtures 的计划宿主及发布方式见 Profile §15.9。此处不复制 schema，避免三个仓库分别维护权威副本。

## L0 服务接口 RC1（2026-09-20）

[权威 wire 契约](../../specs/profiles/code-review/v1/bindings/l0-service-contract.md) 已补齐 T1–T6 的端点与行为设计，状态为待评审。新增接口尚未实现；不改变 Profile 设计已通过的结论，也不关闭生产样例和 CP 实施门禁。

2026-09-20 RC2：Q1–Q3/S1–S7 已修订并提交复核，原评审记录保留；binding 未定版，行为用例尚未执行。

## T1–T6 关闭追踪（2026-09-20）

T1–T6 的关闭状态以规范包内 [`bindings/evidence/closure-checklist.json`](../../specs/profiles/code-review/v1/bindings/evidence/closure-checklist.json) 为**唯一追踪器**：25 条逐项证据要求，各自写明责任人（Nexus 9 / HCZJ 13 / 三方 3）、采集模板与机械验收条件。三方按 [`bindings/evidence/README.md`](../../specs/profiles/code-review/v1/bindings/evidence/README.md) 回填 `received/T{n}.json`；校验器 `tools/check_evidence.py` 重算原始字节摘要、拒绝虚假关闭，并在 T1–T6 未全部关闭时拒绝放宽 `compatibility.json`。本地合成证据（`docs/evidence/l0-*`）一律登记为 `non_closing`，其 `production=false` 标签不得改写。**当前六项全部开放，BINDING-GATE-1 维持关闭。**
