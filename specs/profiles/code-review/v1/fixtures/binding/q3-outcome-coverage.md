# Q3：HCZJ 转换与呈现行为用例

类型：行为验收规范。语义结构期望引用 `../valid/09_review_report_issues_found_with_inherited_gap.artifact_body.json`，不复制该 fixture。

**执行状态（2026-09-20）**：

- ✅ **转换与呈现已实现**：厂商无关管线 `agent_net/code_review/provider_adapter.py`（`ReviewProviderAdapter` + provider 注册表 + `build_profile_report`），HCZJ 词表 `agent_net/code_review/hczj_adapter.py`（`HczjReviewProvider`），呈现规则 `agent_net/code_review/presentation.py`（`render_review_summary` / `validate_publish_body`）。**新增评审方只需新增一个 provider 子类并注册，无需改动核心**（示例见 `tests/test_code_review_provider_adapter.py` 的 ACME provider）。
- ✅ **已可执行**：`tests/test_code_review_q3_harness.py`（12 passed、1 skipped）。
- ✅ **执行记录**：[q3-execution-record-2026-09-20.md](q3-execution-record-2026-09-20.md)（含真实摘要、实际渲染文本、重放前后计数、A–D 拒绝阶段）。
- ⚠️ **未覆盖**：q3-found-partial-replay 的**发布半场**（"同 operation_id 发布重放不得新增 GitLab 评论"）属 HCZJ 应用边界（RC2 §5），本仓库无 GitLab 写入路径，测试中以 `skip` 显式标记，**不视为通过**。
- ⚠️ 本文件仍**不主张**整体行为验收通过：UI/Publisher 的真实模板渲染、Nexus/HCZJ 生产响应样例（T1–T6）未取得。

## q3-found-partial：正常转换

Given：冻结 HCZJ 原始报告含 finding F7、severity=P2，coverage 计划两个文件、只评审一个文件，另一个遗漏；输入图谱有 inherited_gap。原始 outcome 可为 findings_present，或按现行 HCZJ gap 规则为 inconclusive，两种输入分别执行；该片段是测试前置条件，不是假称生产响应样例。

When：适配器读取同一 Run/Attempt 的不可变报告与覆盖产物。

Then：原始两件产物字节保持不变；目标 findings 仍含 F7、severity=medium，outcome=issues_found、coverage.status=partial；遗漏文件、gap_reasons、inherited_gaps 原义完整保留；身份、来源与证据引用不被换成实时版本。目标完整报告必须通过 review_report.schema.json。不能因原 outcome=inconclusive 丢弃 findings，也不能因有 findings 把 coverage 提升到 complete。

UI 与 Publisher 摘要均须包含“发现问题；覆盖：部分”及遗漏范围、继承缺口警示。正文仍呈现 F7 的触发条件、影响与证据；不得单独展示 issues_found 或“评审充分/全部评审完成”。两种原 outcome 的有效输入应得到相同 outcome/coverage 语义，但保留各自源产物溯源。

## q3-found-partial-replay：重复交付

Given：上一用例已生成产物、Delivery 和 accepted Receipt。

When：相同 Coordinator/Run/Attempt/epoch、delivery_id、产物 digest 再投递。

Then：返回原处理结果/Receipt，不新建报告、不改 findings/coverage、不重新调用模型；同 operation_id 发布重放不得新增 GitLab 评论；重复渲染仍保留缺口警示。

## q3-found-partial-reject：错误转换与呈现

分别注入：A. 非空 findings 但 outcome=inconclusive；B. inherited_gaps 非空但 coverage=complete；C. 结构正确但 UI/发布模板仅呈现 outcome；D. 展示遗漏范围为空但原 coverage 有遗漏文件。

Then：A/B 在结构校验阶段拒绝 invalid_output，不产生 accepted Receipt；C/D 在呈现验收中失败，即使 JSON Schema 已通过也不得作为发布模板交付。若运行时生成的发布正文遗漏必需 coverage 信息，Publisher 在写入前拒绝 422 invalid_output，不向 GitLab 写入。

## q3-empty-partial：无发现不等于无问题

Given：findings=[]、coverage=partial、缺口非空。

Then：outcome=inconclusive；UI/评论摘要“结论不充分；覆盖：部分”，列出缺口，禁止显示“无问题”。此用例不能套用 valid/09 的非空 findings。

## 执行记录要求

实施后分别登记适配器版本、测试命令、原始输入与目标产物摘要、UI/评论实际文本或截图、重复投递前后存储/评论计数及拒绝阶段。规范包自检仅验证 valid/09 结构和本文件 manifest 摘要，不执行上述行为。
