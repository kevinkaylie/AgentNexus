# Code Review Collaboration Profile v1

版本：1.0-draft.2 · 日期：2026-09-18 · 状态：设计评审已通过（P1–P7 关闭、S1–S14 采纳，见 §14.10）；实施门禁见 §15.1/§15.9，尚未声明实现符合性。

本版为语义设计，不定义 wire binding；规范补充及字段映射见 §15，逐项回应见 §14.9，复核结论见 §14.10。

本文是 Nexus_Agent、HCZJ_ASSISTANT_AGENT 与 AgentNexus 的场景协作契约，细化 [Code Review V1](design-code-review-v1.md)。MUST/必须表示本 Profile 的符合性要求，SHOULD/建议表示允许有理由偏离；不表示现有代码已全部实现。

## 1. 基准、目标与非目标

目标：对一个明确版本的 MR 取得影响证据、执行评审、验证产物并发布建议性结果；在重复通知、重试、策略变更及服务中断下不误用旧结果。

本次核对的基准：

- AgentNexus [Adapter Contract](../integrations/agent-adapter-contract.md)、[RFC-000](../../specs/rfcs/000-agent-collaboration-framework.md) 与 RFC-001～003。
- Nexus_Agent `docs/premerge-review-m3-design.md` §7、`docs/premerge-review-m3-delivery.md`、`impact/review_models.py`、`api/routes/v3_review.py`。
- HCZJ `docs/specs/2026-09-14-hczj-auto-review-design.md` §5.1/5.2；已确认记录 RUN-ID-2026-09-14。

跨仓库路径是仓库内稳定路径，部署不依赖同级磁盘目录。Nexus 当前接口已含依赖快照、持久化报告及按报告查询证据；本 Profile 不再假设它仅处于 N-M1。不重复承诺外部仓库的测试或交付状态。

范围为同一维护域内的开发者预览。自动合并、自动修复、任意不受信任远程 Worker、法律责任裁定、共识投票不属于 v1。评审无问题不等于代码正确或允许合并。

## 2. 参与者与唯一状态权威

| 角色 | 当前归属 | 权威范围 |
|---|---|---|
| Evidence Provider | Nexus_Agent | MR 观测、generation、ScanJob/execution_revision、冻结证据 |
| Review Coordinator | HCZJ 评审应用服务 | ReviewRun、review_revision、Attempt、策略 activation、有效评审目标 |
| Reviewer | HCZJ CodeReviewSkill 或经适配的 Worker | 产生候选结果，无权自行声明 current 或发布 |
| Publisher | 由 Coordinator 管理的发布适配器 | 获取有限写入权限、执行发布并回报外部操作结果 |
| Collaboration Adapter | AgentNexus | 身份/授权上下文、上层 Session、产物引用和协调视图 |
| Human Principal | 维护者 | 配置策略、重评、反馈及独立的业务合并决策 |

每个部署必须配置唯一 coordinator_id；Nexus 的扫描租约与 HCZJ 的评审租约各自管理，不共用 token。AgentNexus 接入现有 HCZJ 服务时 MUST 复用已有 run_id，不能再分配 review_revision、策略 activation 或把自己的镜像状态覆盖 HCZJ。

未来若由 AgentNexus 承担 Coordinator，需要单独设计状态迁移、旧写入者停用与 epoch 切换；本草案不隐式批准迁移。上层 PlaybookRun 可编排“请求评审/等待/展示”，但不能据自己的 completed 推导底层报告 current。

## 3. 协议版本与边界编码

协作信封 profile 固定为 `agentnexus.code-review/1.0-draft.2`；同一 Session 固定版本，正式 1.0 另行发布。信封含 message_id、type、sender_id、receiver_id、session_id、correlation_id、causation_id（可 null）、created_at（UTC RFC3339）、payload。任务消息另含 run_id、attempt_id、assignment_epoch；首次请求尚无 Run 时用 request_id。

所有 ID 为非空不透明字符串；revision/generation 为正整数；哈希为带算法语义的 SHA256 十六进制。Git SHA 保持 40/64 位并校验 commit 类型。时间戳用于审计，排序和有效性不能只靠发送方时间。

采用 UTF-8 JSON，拒绝重复键、NaN/Infinity、类型不符、未知关键字段。扩展只放 extensions，critical_extensions 列出的未知扩展必须拒绝；不得静默降级版本或丢弃关键权限/覆盖信息。

产物摘要使用 `sha256-bytes-v1`：对存储并传输的原始 UTF-8 字节取 SHA256；字节口径与处理顺序见 §15.3：先解析外层 JSON，取 artifact_body 字符串严格编码为 UTF-8，验证该产物字节摘要后再解析内层报告；不得重新序列化内层报告来计算原摘要。策略摘要和 Nexus 内部摘要沿用各自产生方既有算法，视为不透明标识，跨组件不擅自重算；算法升级必须另定契约版本。这不宣称实现了 RFC 8785 或跨域签名互通。

## 4. 身份、输入冻结和幂等

### 4.1 ReviewRequest

以下均必填，nullable 项例外：

| 字段 | 含义 |
|---|---|
| request_id / idempotency_key | 调用请求标识；动作+资源范围内的幂等 key |
| instance_id / project_id / mr_iid | GitLab 实例允许列表标识、稳定项目 ID、项目内 MR 编号 |
| generation / execution_revision / job_id / report_id | Nexus 版本及扫描执行身份 |
| base_sha / head_sha / target_sha | 差异基线、待审提交、目标分支版本，均来自可信 MR 解析 |
| impact_artifact | 不可变产物引用，含 digest 和 Nexus 契约版本 |
| review_policy_sha256 | 冻结策略族，由 Coordinator 注册的策略确定 |
| operation | initial / rereview；rescan 应先交 Nexus 产生新证据 |
| authority_ref / requested_by | 权限引用、已认证的请求者，不能仅信任正文自报身份 |

Coordinator 验证请求与 Nexus 当前版本/报告对应后分配 Run。dependency snapshot set、扫描参数/配置摘要从 ImpactReport 冻结引用，不能评审时换成“最新图谱”。target_sha 的适配映射必须注明 GitLab 具体字段，不能用 oldrev 猜 MR base。

### 4.2 沿用已确认 Run 身份

唯一键为 `(job_id, report_id, review_policy_sha256, review_revision)`。review_revision 在前三项定义的策略族内从 1 原子分配。MR 身份、generation/execution 和 SHA 同时冻结校验。自动重试新增 Attempt，不新增 revision；人工重评新增 revision；rescan 产生新的扫描 job/execution 后建立新的策略族空间。

重复事件及对账复用已有最新 revision，不能覆盖人工新目标。相同动作/资源/key 与不同正文返回 idempotency_conflict；相同正文返回原结果。正文比较采用首次保存的规范字段，凭据不得进入幂等摘要。

activation_revision 不进入 Run 唯一键；策略启用与回滚均遵循 HCZJ 已确认的 activation CAS。回滚可以重新核验已有 completed 报告，但旧 epoch 的正在执行者不能因此恢复提交权；failed/superseded 不自动复活。

## 5. 接单、执行和状态

### 5.1 Assignment / Acceptance

Assignment 必填 run_id、attempt_id、assignment_epoch、coordinator_id、input_manifest_digest、output_schema、policy_ref、authority_ref、deadline、limits、required_capabilities。input manifest 包含 ReviewRequest 冻结字段、ImpactReport 引用以及依赖快照引用。

limits 至少含最大工具轮次、累计输入/输出 token 上限、wall-clock 秒数、最大成本与币种；不可计量项显式 null 并按本地策略禁止或限制，不以零代表未知。允许的模型服务、数据出境约束及工具范围属于执行约束。预算在同一 Run 各 Attempt 间累计，不能重试清零。

Worker 返回 AssignmentAcceptance：assignment 身份、accepted/rejected、input_manifest_digest、output_schema、reason_code。accepted 必须原样绑定约定；不支持语言/格式/权限时明确拒绝，不能悄悄减少范围。接收 ACK 不等于接受执行。

L0 CLI 可由受信任 adapter 在校验参数/能力后记录 accepted，注明 issuer=adapter；不能伪称远端 Worker 已签署同意。

### 5.2 Run 与 Attempt

沿用 HCZJ 六态；validating 仅为 running 内部 phase：

| 当前 | 允许转移 | 条件 |
|---|---|---|
| queued | running / failed / superseded | 接受分配 / 不可恢复拒绝 / 已有更新目标 |
| running | completed / retry_wait / failed / superseded | 产物验证通过 / 暂时故障 / 不可恢复错误 / 目标替换 |
| retry_wait | running / failed / superseded | 新 Attempt / 次数或预算耗尽 / 目标替换 |
| completed、failed、superseded | 无 | 不复活；人工重评新建 Run |

completed 仅表示有效产物已保存。current 是单独核验结果，不是第七个 Run 状态；已 completed 的历史报告可失去 current，无需修改其终态。

Coordinator 持久化每次分配的单调 assignment_epoch（可映射现有租约 token 的代次语义）和截止时间。接收交付必须原子检查当前 Run 目标、Attempt、epoch、未过期租约及状态。旧 epoch 即使结果格式和签名正确也只能作为审计候选，不能推进状态。

取消是请求，不是停止事实：CancelRequest 使分配失效，Worker 返回 CancelAcknowledgement 表明 stopped/too_late/unknown。MR/策略替换按 superseded；人工停止未完成 Run 在 v1 映射 failed + cancelled_by_owner，独立保留 cancel_requested/cancel_acknowledged 事件。不因进程未停止而恢复提交权限。

## 6. 产物、证据与评审报告

### 6.1 ArtifactRef 与 EvidenceRef

ArtifactRef 必填 artifact_id、producer_id、media_type、schema_version、digest_algorithm、digest、byte_length、locator、access_scope、retention_until（可 null，表示不保证长期可用）。locator 是允许列表服务内的不透明引用，不是模型可指定的任意 URL；读取需要再次鉴权。

EvidenceRef 必填 provider_id、report_id、side(before/after)、snapshot_id、project、commit_sha、path、blob_sha、start_line/end_line、content_sha256。行号从 1 开始、闭区间，绑定原版本；没有源码位置的图关系使用 type=relation 和关系记录 artifact 引用，不伪造行号。

使用 Nexus 按 report/side/snapshot 查询接口，不能引用旧报告却读取实时默认图谱。内容改变必须产生新 artifact；修正使用 replaces 引用，不覆盖原字节。权限撤销或过期不代表报告字节改变，但会影响证据是否仍可核验。

### 6.2 ImpactReport 适配

保留 Nexus `nexus.review_impact.v1` 及 contract_revision，原始字节入库。adapter 显式声明支持的 contract_revision；缺少必需字段或未知 revision 返回 unsupported_contract，不能凭相同 schema_version 接受任意结构。

必须保留 before/after、依赖 snapshot、配置/规则摘要、覆盖缺口、truncated 和 diagnostics。局部 complete 不能覆盖整份报告的 partial。现有 Nexus report_id 是来源身份，不替代传输产物 digest。

### 6.3 ReviewReport

必填 schema_version=`code_review.report.v1`、run_id、attempt_id、input_manifest_digest、impact_artifact、review_policy_sha256、review_revision、base/head/target、generation/execution_revision、reviewer_id、coverage、outcome、findings、limitations、execution_metadata、usage。

coverage 包含 status=complete/partial、planned_files、reviewed_files、omitted_files（path/reason）、gap_reasons。complete 仅针对冻结 file_selection，不能暗示整个仓库或依赖均已评审。继承输入证据缺口，新增预算/工具失败缺口必须保留。

outcome 为 issues_found / no_findings / inconclusive。findings 非空必须 issues_found；无 findings 且 partial 必须 inconclusive；no_findings 要求声明范围 complete。无足够证据完成任何有意义评审应失败，不能制造空成功报告。

Finding 必填 finding_id、severity(critical/high/medium/low)、title、trigger、impact、location、evidence_refs（非空）、suggested_validation。location 使用对应 side 的 commit/path/line；删除行绑定 before。无法证实的问题写入 limitations 或待核实项，不冒充确定缺陷。ID 只保证报告内唯一；跨报告相同问题关联由反馈层显式维护。

execution_metadata 记录 provider/model、可得的模型版本、Skill/工具/校验器版本和时间；模型版本未知必须注明，不承诺复现模型权重。usage 区分已知用量和 unknown，超时可能计费的请求不能当作零成本释放预算。

### 6.4 通用 Adapter 映射

外层 `agentnexus_json_v1.status=completed` 表示取得评审产物；artifact_type=CodeReviewReport，artifact_body 为上述对象序列化后的 JSON 字符串。schema 和证据校验成功后才允许底层 Run completed。

发现代码问题时仍可 completed + outcome=issues_found；不得把它自动映射为 Worker 失败重试。text_artifact 或 wrapper 自动包装的 completed 只表示适配成功，不能跳过本 Profile 校验。blocked 映射需人工处理的失败/DecisionGate，不新增 HCZJ 状态。外层 changes_requested 不能单独作为本场景有效评审结论。

## 7. 交付、校验和 Receipt

每次 Delivery 含 delivery_id、assignment 身份、input_manifest_digest、artifact_ref。重复 delivery_id+相同 digest 返回原 Receipt；不同 digest 返回 delivery_conflict。先保存候选，再校验身份/版本/范围/证据，最后按当前租约 CAS 提交不可变报告。

Receipt 必填 receipt_id、type、issuer_id、subject_ref、run_id、attempt_id（发布可 null）、decision、reason_code、created_at、authority_ref、evidence_refs。类型严格区分：

| type | 表示 | 不表示 |
|---|---|---|
| received | 字节已保存 | 格式或业务有效 |
| validated | 契约与证据引用检查通过 | 代码没有问题 |
| accepted | Coordinator 接受交付为该任务产物 | 当前 MR 或允许合并 |
| published | Publisher 观察到外部评论写入 | 人工批准或永久 current |

校验失败用相应 type + decision=rejected，并给错误码；权限拒绝不回显私有资源详情。同维护域 v1 使用已认证通道与服务端审计归属，不把无签名 Receipt 称为跨域可验证证明。跨域签名/canonicalization 留给后续绑定。

## 8. current、发布与人工反馈

发布前必须从权威服务核验 MR opened/eligible、generation/execution、SHA、目标 run_id/review_revision、当前 activation_revision 和策略摘要；核验失败/超时为 freshness_unknown，禁止作为当前结论发布。仅比对 head_sha 不足以确认 current。

Publisher 的 PublicationRequest 固定 operation_id、MR 身份、run_id、report_digest、expected_version、expected_activation_revision、authority_ref。持久化 outbox，外部状态为 pending/in_flight/unknown/published/failed/obsolete。

网络超时为 unknown，保留 operation_id，先按稳定评论标记查证；不得直接再新增评论。查不到且确认没有已执行结果后，才可在当前性复核通过时重试；无法排除则保持 unknown 并人工处理。写入前后核验，后验发现更新则将评论标为过期；不承诺跨 GitLab/数据库原子性或 exactly-once。

旧报告保留历史，不因新报告失败恢复为当前。Feedback 含 feedback_id、report_digest、finding_id、label(valid/false_positive/fixed/deferred)、actor_id、comment；fixed 附修复版本和验证依据。反馈属于人工断言，不自动改写原报告、通过合并或更新全局模型规则。

## 9. 错误语义

错误信封：code、retryable、action_required、scope、correlation_id、safe_message、retry_after_seconds（可 null）。HTTP 状态由绑定映射，不能仅据 500/超时无限重试。

| code | 行为 |
|---|---|
| unsupported_profile / unsupported_contract / unsupported_capability | 拒绝接单；调整契约或路由 |
| authority_denied / data_policy_denied | 不重试模型；维护者处理 |
| input_mismatch / evidence_digest_mismatch | 拒绝产物，保留审计 |
| evidence_unavailable | 临时不可达可有界重试；永久缺失转人工处理 |
| stale_assignment / superseded_input / policy_changed | 拒绝推进，保存历史，等待新目标 |
| idempotency_conflict / delivery_conflict | 冲突，不以新请求覆盖原记录 |
| budget_exhausted / deadline_exceeded | 停止当前执行，不重试绕过累计预算 |
| invalid_output | 仅可修复结构错误允许同 Attempt 一次纠正；再次失败结束 Run |
| temporarily_unavailable / rate_limited | 有界退避，同 Run 新 Attempt 或当前性查询重试，按故障阶段区分 |
| freshness_unknown / publication_unknown | 只核验外部状态，不重新运行评审模型 |

身份伪造、越权、非法证据不进入格式纠正。传输消息去重与业务任务去重分开；Nexus outbox ACK 表示消费者已持久化事件处理责任，不表示评审完成。

## 10. 权限与数据约束

分别授权 evidence:read、review:execute、review:candidate_submit、review:deliver、publication:write。读源码不自动允许向任意模型服务发送源码；允许 provider、资源范围与披露策略在 Assignment 冻结，并由工具端执行。撤销后在敏感读取与发布时重新校验，不只在接单时检查。

GitLab 写凭据只交 Publisher，模型输入输出不含凭据。正文里的 actor_id、DID、authority_ref 都必须和认证上下文绑定。Nexus 当前共享 token 不提供 per-agent ACL，不得宣称本 Profile 已解决跨租户隔离。

候选代码、仓库提示文件、评审报告内的文字都是不可信数据，不能修改工具权限、目标 MR 或发布正文来源。日志记录关联 ID 和摘要，源码及业务私密数据遵守 artifact 的访问与保留策略。

## 11. 正常流程示例

示例标识只是说明，不是完整 wire fixture：

1. Nexus 发布 scan.succeeded：job=J1、report=R1、generation=3、execution_revision=1。
2. HCZJ 校验并创建 (J1,R1,P1,1)，分配 Attempt A1/epoch=8，绑定输入清单 D1；adapter 接受任务。
3. Worker 交付 D1 对应报告 F1，coverage=partial、findings=[]、outcome=inconclusive。
4. Coordinator 验证后 Run completed；报告清楚表示评审不充分。它可以按明确发布策略发布“部分评审”摘要，不得发布通过标记。
5. Publisher 核验版本和 activation，发布摘要，持久化 note_id 与 published Receipt。
6. 新提交到来：generation=4；F1 成为历史，创建新证据/评审，旧 Worker 的任何结果不能推进新任务。

## 12. 一致性验收矩阵

| ID | 输入/故障 | 必须观察到 |
|---|---|---|
| CP-01 | 同一事件重复投递 | 同一目标/Run；先持久化再 ACK |
| CP-02 | 同 key 不同请求正文 | conflict，原请求不变 |
| CP-03 | Worker 不支持契约 revision | rejected，不悄悄包装文本成功 |
| CP-04 | 读取与清单不同的 commit/blob | input/evidence mismatch，不能 accepted |
| CP-05 | A 超时 B 接管后 A 返回 | stale_assignment，不覆盖 B |
| CP-06 | 人工重评与自动对账并发 | 自动路径不覆盖更高人工 revision |
| CP-07 | 策略变更后回滚相同摘要 | 旧 epoch 不能提交，completed 只能重新核验 |
| CP-08 | 部分分析、零 finding | inconclusive，不能显示通过 |
| CP-09 | 有有效 finding | completed+issues_found，不触发执行失败重试 |
| CP-10 | evidence 403/404/超时 | 权限/缺失/暂时不可达分类，不伪造证据 |
| CP-11 | 交付同 ID 不同摘要 | delivery_conflict |
| CP-12 | 发布成功但响应丢失 | unknown→查证原操作，不重复评论 |
| CP-13 | 发布前后 MR 改变 | 阻止当前发布或标记已发评论过期 |
| CP-14 | 取消后 Worker 仍返回 | 旧分配无提交权，停止事实单独记录 |
| CP-15 | 网络失败重试且预算已耗尽 | 不清零预算、不再调用模型 |
| CP-16 | 私有源码请求未批准 provider | data_policy_denied |
| CP-17 | 普通 stdout 被包装 completed | 缺少 ReviewReport 校验时不能完成 Run |
| CP-18 | 进程重启及旧事件重放 | 恢复持久化目标，不回退 revision/activation |

## 13. 实施分工及评审出口

Nexus：提供已固定版本的报告/查询/事件，补充符合性 fixtures，不为 Profile 新建评审 Run。

HCZJ：实现接单/后台评审/候选校验/Receipt 映射，沿用已确认的 Run、Attempt、预算与 activation 设计。

AgentNexus：新增 Profile-aware adapter、Session 与外部 run_id 映射、产物/Receipt 显示；不得让通用 wrapper 的 completed 绕过 Profile 校验。

首批开发交付应包括机器可读 JSON Schema（请求、Assignment、交付、报告、Receipt、错误）、至少一条完整 wire fixture 和 CP-01～18 反例；schema 只能检查结构，状态与摘要必须通过行为测试。该批完成前不能声称 wire conformance。

评审需确认：Coordinator 归属、现有两侧字段到本 Profile 的精确映射、支持的 Nexus contract_revision 清单、模型数据策略、部分评审发布策略、Receipt 认证级别。本文完成这些决策的提案，不伪称跨团队已批准；不需要等待 RFC-004～006 全部完成，后续将验证过的通用语义提炼入 RFC。

---

## 14. 设计评审记录

> 评审日期：2026-09-18 ｜ 评审者：评审 Agent（AI 辅助）｜ 依据：[docs/processes/design-review.md](../processes/design-review.md)
> 评审方式：只读比对本文与其引用的 `design-code-review-v1.md`、`agent-adapter-contract.md`、RFC-000/002/003，以及 AgentNexus 现有实现（未修改任何代码）。

| 日期 | 评审者 | 结果 | 备注 |
|------|--------|------|------|
| 2026-09-18 | 评审 Agent | 有条件通过（draft.1） | 7 个阻塞项（P1–P7）、14 个建议项（S1–S14）、4 条信息性备注。阻塞项决议写入本文前不得开始实现，也不得声明 wire conformance |
| 2026-09-18 | 评审 Agent | 通过（draft.2 复核） | P1–P7 全部关闭、S1–S14 全部采纳、ADR-015 批准为已采纳；3 条残余建议（R1–R3）不阻塞；实施门禁见 §14.10 |
| 2026-09-18 | 评审 Agent | R1/R2 已落实，R3 部分落实 | 复核见 §14.11；R3 遗留 2 处状态措辞（`design-code-review-v1.md` 第 5、14 行）与 ADR-015 已采纳冲突，需补正；不影响 §14.10 的设计批准结论 |

### 14.1 评审结论

文档方向与边界划分正确，是本项目第一份把 AgentNexus 定位为**适配层而非状态权威**的三方场景契约；边界声明克制可核查（"不表示现有代码已全部实现"、"不伪称跨团队已批准"、"不重复承诺外部仓库测试状态"），§5.2 的"completed ≠ current"、§7 四类 Receipt 的"表示/不表示"分割、§12 的 18 条一致性矩阵均有实际价值，建议保留 §12 用例 ID 作为后续 conformance/fixture 的稳定锚点。

主要风险不是设计取向，而是**规范语义与 AgentNexus 现有执行链、数据模型冲突或没有强制落点**：照现状实现会出现"契约写着 A、代码做着 B"。因此判为**有条件通过**：P1–P7 必须在本文形成规范级决议后方可进入开发。

### 14.2 阻塞性问题（P）

| # | 阻塞问题 | 章节 | 证据 | 评审建议 | 状态 |
|---|----------|------|------|----------|------|
| P1 | §6.4 要求"发现代码问题不得映射为 Worker 失败重试"（CP-09），但 AgentNexus 现有链路会把 review 的 `changes_requested` 当作可重试信号重跑 Worker，并按 `on_reject` 把整个 coding run 退回 implement | 6.4, 12 | `agent_net/node/runner_loop.py:289-311`（重跑且重试 prompt 声称 JSON 解析失败）、`agent_net/node/routers/coordination_executions.py:226-233`（status→decision 一一对应）、`agent_net/node/loop_engine.py:315-334`、`agent_net/persistence/session_store.py:94`（默认 `coding.v1` 的 `code_review.on_reject="implement"`） | 在 §6.4 写出规范性规则：明确**翻译责任层**（Profile-aware 输出适配器须在 AgentNexus 状态语义生效前把评审判定归一为 `completed` + 域内 verdict），规定本场景不得使用带 `on_reject` 与 changes_requested 重试的阶段；并把"未知 status 必须硬拒绝"写成要求（现仅告警：`agent_net/node/execution_backends/local_cli.py:396-402`；`local_cli.py:405` 接受任意 status 字符串） | 已关闭（见 §14.9 决议、§14.10 复核） |
| P2 | §3 的 `sha256-bytes-v1` 禁止"重新序列化计算摘要"，但现有投递摘要正是重新序列化计算，且**当前不存在"产物字节摘要"这一事实** | 3, 7, 8 | `agent_net/node/routers/coordination_executions.py:171-178`（`result_hash = sha256(json.dumps({execution_id,status,artifact_type,artifact_body,summary}, sort_keys=True))`）、同文件 `:215-223` 建 artifact 时未传 `content_hash`（字段定义见 `agent_net/persistence/deliverable_store.py:49-58`，默认空） | 明确 `report_digest`/delivery digest = 对**传输中的 `artifact_body` 原始字节**取 SHA256；把 `result_hash` 标注为"既有内部幂等键、不构成本 Profile 的产物摘要"并给出映射/迁移结论；要求 AgentNexus 填充 `content_hash`。另需说明 `artifact_body` 是 JSON 字符串，避免"重序列化 vs 原始字节"两种口径直接触发 `delivery_conflict` | 已关闭（见 §14.9 决议、§14.10 复核） |
| P3 | Receipt 与 ArtifactRef 词表同既有实现撞车，会污染 §13 的"产物/Receipt 显示"交付 | 6.1, 7 | `agent_net/persistence/schemas.py:352-368` + `agent_net/node/routers/coordination_executions.py:256-261`（既有 `receipt_type` 由 stage 推导为 `ReviewReceipt`）、`agent_net/node/routers/coordination_records.py:316`（既有 `decision ∈ approved/passed/changes_requested/rejected/failed/aborted`，且 `signature` 恒空）；artifact 现存字段不含 byte_length/access_scope/retention/media_type（`agent_net/persistence/deliverable_store.py:49-83`） | 加命名空间（如 `code_review.receipt.v1`、`artifact_ref.v1`）并给出与既有 `receipt_type/decision`、artifact 字段的双向映射表；`retention_until`/`access_scope` 需说明由谁存储与执行。RFC-000 §7.21/§6.10 把 Receipt 定义为签发者断言，本文既已声明非签名证明，更应避免共用裸词 | 已关闭（见 §14.9 决议、§14.10 复核） |
| P4 | §10 要求 provider/资源范围/披露策略"由工具端执行"（CP-16），但基线上**没有强制点** | 10, 5.1, 6.3 | `agent_net/node/execution_backends/local_cli.py:5,236-263`（仅 argv 白名单/destructive 检测/超时/输出上限）；`network_access` 仅被透传（`agent_net/node/runner_loop.py:39-40`）无 backend 消费；Loop "budget" 只是执行次数与墙钟（`agent_net/node/loop_engine.py:121-149`），无 token/成本计量 | 明确"声明 vs 强制"边界与强制点归属、fail-closed 范围，并把无法强制的项排除出符合性声明；否则 §5.1 的 token/成本上限、§6.3 的 `usage`、CP-15/CP-16 均不可验证 | 已关闭（见 §14.9 决议、§14.10 复核） |
| P5 | 缺 transport binding（RFC-000 §13 要求端点/编码/关联/ACK/重复投递映射），且"谁发起"未定义 | 1, 4.1, 9, 11 | 全文只有语义、无 binding；§9 引用了未定义的"Nexus outbox ACK"；`design-code-review-v1.md:26` 原方案把 GitLab webhook 入口放在 Nexus 进程，新归属下未重新指派；全库无 outbox/gitlab/note_id/publication/delivery_id 标识符，交付最自然的绑定是 `POST /coordination/executions/{execution_id}/result`（`agent_net/node/routers/coordination_executions.py:154`） | 补一节 binding（L0 具体 HTTP 路径/MCP 工具、内容类型、版本协商、ACK 语义），或在 §1 显式声明"v1 不定义 binding 且不得做 wire conformance 声明"。§13 的 schema/fixture 在无 binding 时无法编写 | 已关闭（见 §14.9 决议、§14.10 复核） |
| P6 | `run_id` 命名空间与 `assignment_epoch` 围栏在两侧对不上，CP-05/CP-14 无机制 | 2, 3, 5.2 | AgentNexus 自有 `run_id`（`agent_net/persistence/objective_store.py:19`）且无 `external_run_id`（最近似为 `external_session_id`，`agent_net/persistence/schemas.py:416`）；`submit_execution_result` 只检查执行存在 + session 访问 + `result_hash`（`agent_net/node/routers/coordination_executions.py:154-193`），无 epoch/fencing token，`attempt` 仅作重试计数（`agent_net/node/loop_engine.py:203`） | 规定 `run_id` = HCZJ ReviewRun id、AgentNexus 必须存为 external 字段且禁止复用自身 ID 空间；把"新增单调 `assignment_epoch` 列 + 提交时 CAS 校验目标/epoch/租约"写成 AgentNexus 侧必需变更 | 已关闭（见 §14.9 决议、§14.10 复核） |
| P7 | §2 的授权模型在基线上没有强制点，Worker 可自签 `approved` 收据 | 2, 7, 10 | `agent_net/node/routers/coordination_records.py:196-230`：`POST /coordination/receipts` 允许调用方任意指定 `receipt_type`/`decision`/`issuer_did`/`signature`/`evidence_refs`，鉴权仅 token + "actor 可访问该 session"（`:203`），无角色校验，且该路由不校验 `decision` 枚举 | 把"本 Profile 必须对 receipt/artifact 写入做角色级授权（`review:deliver` 仅 Coordinator、`publication:write` 仅 Publisher）"列入 AgentNexus 侧必需变更；若 v1 沿用共享 token，则 §2 权威表只能声明为**部署约定**而非可强制属性，且不得据此宣称符合性 | 已关闭（见 §14.9 决议、§14.10 复核） |

### 14.3 建议性问题（S）

| # | 问题 | 章节 | 建议 | 状态 |
|---|------|------|------|------|
| S1 | 治理路径未说明：状态权威由 AgentNexus 移至 HCZJ，推翻了 `design-code-review-v1` 的 CR-04/CR-05 及既有"PlaybookRun 是运行态状态源"表述 | 2 | 按 `docs/agent-workflow.md`（推翻已批准架构须走新 ADR）新开 ADR 记录 Coordinator 归属与双层状态权威，并同步修订 CR-04/CR-05 与 `docs/project-status.md`、`docs/quickstart.md` 措辞；另按 `docs/contracts/` 惯例登记为跨团队契约 | 已关闭（见 §14.9 决议、§14.10 复核） |
| S2 | ACF 对齐未固定版本（RFC-000 §18.10 要求声明所实现的 RFC 版本）；§3 已声明不实现 RFC 8785，而 RFC-002 §23.4 要求按 profile 定义确定性 canonicalization | 1, 3 | 固定所引用 RFC 版本，并显式声明"本 Profile 不主张 RFC-002/003 profile 符合性" | 已关闭（见 §14.9 决议、§14.10 复核） |
| S3 | 错误码未与 ACF failure class 映射（RFC-003 要求 `unsupported_critical_extension`；RFC-000 §12 的 `policy_rejected`/`requirements_unsatisfied` 等无对应） | 9 | 补与 RFC-000 §12 / RFC-002 §21 / RFC-003 的映射表，或声明本 Profile 错误码为局部命名空间 | 已关闭（见 §14.9 决议、§14.10 复核） |
| S4 | §5.1 的 Acceptance（任务接单）与 RFC-003 的 Grant Acceptance/`acceptance_pending` 同名 | 5.1 | 改名（如 `AssignmentAcceptance`）或加命名空间 | 已关闭（见 §14.9 决议、§14.10 复核） |
| S5 | 状态映射不完整：仅列 `agentnexus_json_v1` 的 4 个 status，未覆盖 `objective_executions.status`（含 `timed_out`/`cancelled`）与 Loop Engine 的 `wait`/`create_decision_gate` 动作 | 6.4, 13 | 补完整双向状态映射表（含 blocked→HCZJ 终态 + DecisionGate、timed_out、cancelled→failed+cancelled_by_owner 的落点） | 已关闭（见 §14.9 决议、§14.10 复核） |
| S6 | 状态机缺取消/超时转移：queued 阶段收到 CancelRequest、等待 Acceptance 超 deadline 均无对应转移 | 5.2 | 补 queued→failed(`cancelled_by_owner`/`deadline_exceeded`)，并说明"等待 Acceptance"归属 queued 还是 running | 已关闭（见 §14.9 决议、§14.10 复核） |
| S7 | coverage 规则不闭合：§6.2 要求继承输入证据缺口，§6.3 的 `complete` 是否允许携带继承缺口未定义 | 6.3 | 明确"继承缺口 ⇒ coverage 上限 partial"，或要求单列 `inherited_gaps` 且 `complete` 仅指本层冻结 `file_selection` | 已关闭（见 §14.9 决议、§14.10 复核） |
| S8 | "相同正文"不可判定（幂等比较缺规范字段投影）；§9 的 `invalid_output` 一次性纠正是否复用 `delivery_id` 未说明（会撞 §7 `delivery_conflict`） | 4.1, 7, 9 | 定义幂等比较字段投影 + 算法（排除凭据），并规定纠正必须使用新 `delivery_id` | 已关闭（见 §14.9 决议、§14.10 复核） |
| S9 | `EvidenceRef.content_sha256` 语义未定义（整 blob 还是行区间字节、行尾如何归一），与 `blob_sha` 职责边界不清 | 6.1 | 明确"对绑定版本的行区间原始字节取 SHA256"并固定行尾归一规则 | 已关闭（见 §14.9 决议、§14.10 复核） |
| S10 | L0 adapter 代签 Acceptance 只靠 `issuer=adapter` 区分，下游易误当 Worker 同意 | 5.1 | 增加显式字段（如 `acceptance_mode=adapter_attested`） | 已关闭（见 §14.9 决议、§14.10 复核） |
| S11 | 运行中 authority 撤销的处置缺失（§10 仅要求读取/发布时重新校验），未定义在途 Run 终止与部分产物标注 | 10 | 补"撤销 ⇒ 终止当前 Attempt + failed(`authority_denied`)，历史产物保留并标注撤回" | 已关闭（见 §14.9 决议、§14.10 复核） |
| S12 | 策略变更语义："策略变更但不重扫"是新建 Run、新 revision 还是 supersede 未定；CP-07 只覆盖回滚到相同摘要 | 4.2 | 明确 `review_policy_sha256` 变化后的 Run/revision 语义 | 已关闭（见 §14.9 决议、§14.10 复核） |
| S13 | 缺"更新目标"定序规则：§3 称排序不能只靠发送方时间，但 §5.2 的 superseded 条件"已有更新目标"无可比序；同一 MR 两个 job 竞争时谁 current 未定 | 5.2, 12 | 定义 MR 维度单调序，并补反例：CP-19 并发 Run、CP-20 运行中撤销、CP-21 旧 scan 事件乱序不得回退 revision、CP-22 策略变更 vs 回滚 | 已关闭（见 §14.9 决议、§14.10 复核） |
| S14 | schema/fixture 的规范宿主未定（跨 Nexus/HCZJ/AgentNexus 三仓库，谁是权威副本） | 13 | 指定版本化路径（建议 AgentNexus 仓库内的 `specs/` 或 schema 目录）与发布方式 | 已关闭（见 §14.9 决议、§14.10 复核） |

### 14.4 信息性备注（I）

- **I1 文档同步基本到位**（检查清单第 6 项）：`AGENTS.md`、`docs/design.md:3`、`docs/requirements.md:5`（CR-01～08 归属说明）、`docs/wip.md:5`、`docs/project-status.md:3` 均已更新。唯一遗漏：`docs/design.md` 的索引表（14–23 行）未收录本 Profile，建议补一行。
- **I2** §1"现有 Nexus report_id 已含依赖快照、持久化报告及按报告查询证据"为外部仓库断言，本轮无法在 AgentNexus 内验证，建议附 Nexus 侧 commit/report 标识（已有 `RUN-ID-2026-09-14` 可引用）。
- **I3** §2"AgentNexus 共享 token 不提供 per-agent ACL，不得宣称本 Profile 已解决跨租户隔离"与鉴权矩阵 v3 现状准确对应，是本轮最值得保留的诚实边界声明。
- **I4** §12 的 CP-01～18 是本文最大价值，建议冻结 ID、只追加不改语义，作为后续 schema/fixture 的锚点。

### 14.5 与现有代码库的关键差距

| 本文要求 | 当前代码状态 | 差距评估 |
|----------|--------------|----------|
| ReviewReport 校验通过后才允许 Run completed（§5.2/§6.4，CP-17） | 契约校验仅告警（`agent_net/node/execution_backends/local_cli.py:396-402`）；daemon 原样接受 `artifact_type`/`artifact_body` 并签发 `approved` 收据（`agent_net/node/routers/coordination_executions.py:214-281`）；无 jsonschema、无 ReviewReport 类型、无 schema 文件 | 需新增 Profile-aware 校验层（AgentNexus 侧） |
| 产物摘要 `sha256-bytes-v1`（§3） | 只有重新序列化的 `result_hash`；`content_hash` 恒空 | 需字节级摘要 + 填充 `content_hash` |
| `assignment_epoch` 单调 + 提交时原子 CAS（§5.2） | 无 epoch 概念；提交仅查存在性/`result_hash` | 需新增 fencing token + 提交前目标/epoch/租约校验 |
| `run_id` = HCZJ ReviewRun（§2/§3） | 无 `external_run_id`，最近似为 `external_session_id` | 需外部 ID 映射字段 |
| 发布 outbox / pending·in_flight·unknown·published（§8） | 发布适配器、outbox、`operation_id` 均不存在（`docs/wip.md:8` 亦自认未开始） | 全新实现 |
| `ArtifactRef`（digest/byte_length/media_type/access_scope/retention）（§6.1） | artifact 记录字段不足 | 需扩展模型 |
| Provider/数据策略"由工具端执行"（§10） | local_cli 无网络/provider 强制，`network_access` 无人消费 | 需明确强制点或降级声明 |
| Receipt 词表与角色级写入授权（§2/§7） | 既有 `ReviewReceipt` + `decision ∈ approved/passed/…`、从不签名；`POST /coordination/receipts` 无角色校验 | 需命名空间 + 映射表 + 写入授权 |

> 上表属"待实现差距"，本身不是文档缺陷；但它意味着 §13 的符合性声明必须逐项显式排除未实现项。

### 14.6 对 §13「评审需确认」六项的逐项意见

| 待确认项 | 评审意见 |
|----------|----------|
| Coordinator 归属（HCZJ） | 方向合理（复用已确认 Run 身份、避免双写），但须走 ADR 并写明"AgentNexus 不自建评审状态"的边界，同时明确单侧部署（无 HCZJ）时的行为 |
| 两侧字段精确映射 | 当前缺失且是最大交付风险：需覆盖 status（含 timed_out/cancelled）、receipt、artifact、run_id、epoch、预算六类，见 P1/P3/P6/S5 |
| 支持的 Nexus `contract_revision` 清单 | 不能只写正文，应产出机器可读清单 + 不支持时的 `unsupported_contract` fixture（CP-03） |
| 模型数据策略 | 需先确定强制点（P4）；无强制能力前只能声明为 declared-only 并禁止据此宣称合规 |
| 部分评审发布策略 | §11 步骤 4 的最小规则（可发布"部分评审"摘要、不得发通过标记）正确，建议升格为规范性条款并配反例 |
| Receipt 认证级别 | "已认证通道 + 服务端审计归属、非签名证明"的定性正确，建议同时禁止使用裸词 Receipt（P3） |

### 14.7 后续行动项

1. **设计 Agent**：就 P1–P7 在本文形成规范级决议（翻译责任层、摘要字节口径、词表命名空间、强制点、binding、ID/围栏、写入授权），并逐项填写上表"状态"。
2. **设计 Agent**：补术语与映射（状态/收据/产物/ID 四张映射表 + ACF 错误码映射，S2/S3/S5），并补 S6/S7/S12/S13 的语义与反例。
3. **评审通过后（设计 Agent + 评审 Agent）**：新开 ADR 记录 Coordinator 归属与双层状态权威；按 `docs/contracts/` 惯例登记三方契约；修订 `design-code-review-v1` 的 CR-04/CR-05 与 `docs/project-status.md`、`docs/quickstart.md` 相关表述（S1）。
4. **首批交付重新排序（开发 Agent）**：先出"字段映射表 + 摘要算法定版 + binding"，再出 JSON Schema 与 CP-01～18 反例，否则 fixture 会返工（P2/P5/S14）。
5. **文档状态**：维持"尚未声明实现符合性"；P1–P7 决议写入前不得进入开发、不得声称 wire conformance。

### 14.8 决议采纳清单

> draft.2 已填写；复核完成，全部关闭。

| 项 | 决议 | 状态 |
|----|------|------|
| P1–P7 | 逐项规范决议见 §14.9/§15，复核确认见 §14.10 | 已关闭 |
| S1–S14 | 逐项决议见下方及 §15，S1 的 ADR-015 已批准 | 已采纳 |

### 14.9 draft.2 设计回应（2026-09-18）

以下为设计者回应，不代替评审者的关闭确认；§14.2/14.3 原意见保留。

| 项 | 决议与位置 | 状态 |
|---|---|---|
| P1 | §15.2 在通用状态生效前翻译；禁用 coding.v1/on_reject，未知状态硬拒绝 | 已采纳，复核通过 |
| P2 | §15.3 定义解码后 artifact_body 的 UTF-8 字节，独立于 result_hash，必须填 content_hash | 已采纳，复核通过 |
| P3 | §15.4 命名空间、双向映射、保留期与 ACL 执行者 | 已采纳，复核通过 |
| P4 | §15.5 强制点、能力声明、fail-closed、预算不支持时拒绝 | 已采纳，复核通过 |
| P5 | §15.1 明确本版为语义设计，不定义 wire binding；单列 binding 交付门禁 | 已采纳（评审允许的语义范围方案），复核通过 |
| P6 | §15.6 外部 ID、持久化 epoch、双侧本地 CAS 与非原子边界 | 已采纳，复核通过 |
| P7 | §15.7 分离 Worker 候选提交和 Coordinator 权威交付，封堵通用写入口 | 已采纳，复核通过 |
| S1 | ADR-015（提议→已采纳）、跨团队契约登记、上位设计/状态/quickstart 同步 | 已采纳，复核通过 |
| S2 | §15.1 固定 RFC 版本并限制符合性声明 | 已采纳，复核通过 |
| S3 | §15.8 错误局部命名空间及 critical extension 拒绝 | 已采纳，复核通过 |
| S4 | §15.8 使用 AssignmentAcceptance，区分 Grant Acceptance | 已采纳，复核通过 |
| S5 | §15.2 包含 timed_out/cancelled/wait/DecisionGate 映射 | 已采纳，复核通过 |
| S6 | §15.8 接单等待归 queued；取消/超时转移补齐 | 已采纳，复核通过 |
| S7 | §15.8 输入缺口强制使覆盖上限 partial | 已采纳，复核通过 |
| S8 | §15.8 幂等字段投影与确定性比较，纠正使用新 delivery_id | 已采纳，复核通过 |
| S9 | §15.3 源码行区间摘要和行尾口径 | 已采纳，复核通过 |
| S10 | §15.8 acceptance_mode 和已认证签发者 | 已采纳，复核通过 |
| S11 | §15.8 撤销时终止执行、禁止发布、保留审计 | 已采纳，复核通过 |
| S12 | §15.8 策略变化建立新族 revision=1 | 已采纳，复核通过 |
| S13 | §15.6 权威序与 CP-19～22 | 已采纳，复核通过 |
| S14 | §15.9 规范宿主、发布顺序、支持清单交付门禁 | 已采纳，复核通过 |

I1 已补设计索引表；I2 的外部依据固定为 RUN-ID-2026-09-14 与 Nexus N-M3 交付记录（2026-09-09/09-14），未取得可发布 commit，不以此声明代码符合性。保留 I3 的共享 token 局限；CP-01～18 ID 与原语义保持不变。

### 14.10 复核确认与批准（2026-09-18，draft.2）

**结论：通过（批准）。** P1–P7 全部关闭，S1–S14 全部采纳，ADR-015 批准为"已采纳"。设计层面不再有阻塞项。本轮批准的是**设计**；§14.5 的代码差距仍未实现，需按 §15.9 顺序落地并通过 CP 验收后才可声明实现符合性。

独立复核（不依赖 §14.9 自述，逐项核对正文与仓库实际状态）：

| 复核项 | 核对结果 | 关闭依据 |
|---|---|---|
| P1 翻译责任层 | 明确"在 runner_loop 通用重试分支、Daemon 自动签发收据及 Loop Engine 状态映射**之前**"校验翻译，Daemon 入口二次验证；专用模板禁用 `coding.v1` 的 code_review 与 `on_reject`；未知 status/普通文本 completed 硬拒绝 | §15.2 状态映射表 |
| P2 摘要口径 | 定义 B=解码外层 JSON 后 `artifact_body` 字符串的严格 UTF-8 字节，外层转义不参与、内层禁止重序列化；`content_hash` 必须填 `sha256:<hex>`；禁止 500 字符截断 fallback。**复核发现该口径与既有 `POST /coordination/artifacts` 的实现完全一致**（`agent_net/node/routers/coordination_records.py:159`：`"sha256:" + sha256(vault_entry["value"].encode())`），且 `coordination_common.py:357` 已按只读方式消费该字段，填充后 Delivery Manifest 的 checksum 才有意义 → 可无冲突实施 | §15.3 |
| P3 词表命名空间 | `code_review.artifact_ref.v1` / `code_review.receipt.v1`；kind=received/validated/accepted/published、decision=confirmed/rejected，与旧 `ReviewReceipt.decision=approved` 隔离；双向映射表 + access_scope/retention 执行者 + artifact_expired | §15.4 |
| P4 强制点 | Assignment 增 `enforcement_requirements`；部署注册 enforced/declared_only/unsupported 及执行组件；接单 fail-closed 返回 `enforcement_unavailable`；明示"普通 local_cli argv 白名单不等于网络隔离"、"无预算计量或网络执行点不得声称 CP-15/16 通过" | §15.5 + CP-25 |
| P5 binding 与发起方 | 本版明确为语义设计、不定义 binding、不声明 wire conformance；发起职责固定（Nexus 归一化 GitLab 事件 → HCZJ 消费持久化事件建目标 → AgentNexus 仅适配）；单列 L0 binding 评审门禁，并声明既有 `/coordination/executions/{id}/result` 未经 §15.2–15.7 改造不得绑定 | §15.1 |
| P6 ID 与围栏 | Profile `run_id` 恒为 HCZJ Run ID；新增 `external_coordinator_id/external_run_id/external_attempt_id/assignment_epoch` 与权威目标版本，本地 ID 独立且唯一关联键含 `coordinator_id`；epoch 由唯一 Coordinator 单调分配；双侧本地 CAS、不宣称跨库原子；按权威维度比较而非跨源求最大 | §15.6 + CP-19/21 |
| P7 角色授权 | 新增 `review:candidate_submit`（Worker 仅候选）与 `review:deliver`（Coordinator 权威交付）；Daemon 覆盖 result/artifact/receipt 全部写入口并按已认证凭据绑定角色；旧 `/coordination/receipts` 对 Profile Session 拒绝不合规写入；共享 token 场景只能声明为部署约定、不得跑符合性授权测试 | §15.7 + CP-24 |
| S1 治理路径 | ADR-015 存在且已被复核批准；跨团队契约已登记（`docs/contracts/code-review-collaboration.md`，draft.2，正文以 Profile 为唯一来源、不复制 schema）；CR-04/CR-05 已按新归属重写；`docs/project-status.md`、`docs/quickstart.md`、`docs/requirements.md` 已同步 | ADR-015 + 契约 + 上位文档 |
| S2/S3/S4/S5 | RFC 版本已固定（RFC-000 v0.3、001 v0.1、002 v0.1、003 v0.3）并限制符合性声明；错误码收敛为 `code_review.error.v1` 局部词表；`AssignmentAcceptance` 与 RFC-003 Grant Acceptance 已区分；状态映射覆盖 timed_out/cancelled/wait/create_decision_gate | §15.1/§15.2/§15.8 |
| S6–S13 | 接单等待归 queued 且取消/超时转移补齐；inherited_gap 强制 coverage 上限 partial；幂等字段投影与确定性比较字节 + 纠正用新 delivery_id；行区间摘要与行尾口径；`acceptance_mode`；运行中撤销处置；策略变更建新族 revision=1；权威序与 CP-19～22 | §15.6/§15.8 |
| S14 规范宿主 | 权威路径 `specs/profiles/code-review/v1/`（schemas/fixtures/bindings/compatibility.json/manifest.json）；**复核确认该目录当前不存在**，与 §15.9"计划路径、尚未生成的文件不得当作已有交付"一致；compatibility.json 默认空列表拒绝、禁用通配 | §15.9 |
| I1/I2/I4 | `docs/design.md` 索引表已补行（I1 关闭）；外部依据固定为 RUN-ID-2026-09-14 与 N-M3 交付记录且不据此声明代码符合性（I2 接受）；CP-01～18 ID 与语义未被改动、新增为 CP-19～26（I4 满足） | 文档 + §15.9 |

**残余建议（不阻塞批准）**

| # | 建议 | 位置 |
|---|------|------|
| R1 | §3 仍写"接收方先验证字节再解析"，与 §15.3"解析外层 JSON 后取 `artifact_body` 字符串再编码"的字面顺序不同；虽由 §15 的优先级声明兜底，建议在 §3 该句加"字节口径见 §15.3"指针，避免实现者按字面先切字节 | §3 |
| R2 | ADR-015 引入的 `coordinator_unavailable` 未出现在 §15.8 的新增错误码枚举中，建议补入 `code_review.error.v1` 清单 | §15.8 |
| R3 | `design-code-review-v1.md` 的"架构与复用""数据模型与接口契约"两节仍保留"ReviewRun 拟新增 Daemon 存储表 / AgentNexus 负责跨服务推进"的旧模型，目前仅靠文首 2026-09-18 批注兜底；建议将这两节显式标注为被 Profile 取代或移入归档，避免开发 Agent 误引 | `design-code-review-v1.md` |

**批准后的实施门禁（不因批准而取消）**

1. L0 binding 必须单独设计并评审（§15.1）；未定版前只允许独立语义验证开发，不得启动"符合本 Profile"的集成运行。
2. `specs/profiles/code-review/v1/` 的 schema、compatibility.json、manifest.json 冻结后方可声明结构符合性；wire conformance 需 binding 完成之后。
3. §14.5 列出的代码差距（Profile 校验层、字节摘要与 `content_hash`、fencing token、external ID、角色级写入授权、ArtifactRef 元数据、发布 outbox）目前**全部未实现**；CP-01～26 通过前不得声明实现符合性。
4. ADR-015 已采纳，其实施须体现"无 HCZJ 或等价 Coordinator ⇒ `coordinator_unavailable`，不得用本地 demo 冒充自动评审闭环"。

### 14.11 残余建议处理记录（2026-09-18）

| 项 | 处理结果 | 状态 |
|---|---|---|
| R1 | §3 明确外层解析、产物字节验证、内层解析顺序，并引用 §15.3 | 已落实 |
| R2 | §15.8 增补 coordinator_unavailable，区分未配置与暂时不可达，禁止自建替代 Run | 已落实 |
| R3 | 上位设计两节显式标为历史方案、已被取代，并链接现行 Profile 与 ADR-015 | 已落实 |

本次为已通过设计的非阻塞建议补充，不改变 §14.10 的评审结论或 wire binding 实施门禁。

**评审者复核（2026-09-18）**

- **R1 已确认落实**：§3 已补处理顺序与口径指针——"先解析外层 JSON，取 artifact_body 字符串严格编码为 UTF-8，验证该产物字节摘要后再解析内层报告；不得重新序列化内层报告来计算原摘要"，与 §15.3 一致，原"先验证字节再解析"的字面歧义已消除。
- **R2 已确认落实**：§15.8 新增 `coordinator_unavailable`，并区分"未配置（retryable=false / action_required=true）"与"已配置但暂时不可达（retryable=true / action_required=false，仅有界连接与状态查询重试、不重调模型）"；与 §9 错误信封字段及 ADR-015 的降级路径一致，且明确禁止退回本地自建 Run。
- **R3 部分落实**：两个被取代章节已正确标注"（历史方案，已被取代）"并链接 Profile §2/§15.2/§15.6～15.7 与 ADR-015，主诉已解决。但同一文件仍有 2 处状态措辞与"ADR-015 已采纳"冲突，需补正：
  1. `design-code-review-v1.md:5` "职责调整仍待评审" → 建议改为"职责调整已由 [ADR-015](../adr/015-code-review-state-authority.md) 采纳；本文件保留为历史需求与早期方案"；
  2. `design-code-review-v1.md:14` CR-04 "（ADR-015 提议）" → 建议改为"（ADR-015 已采纳）"。
- **信息性观察 I5（非本轮引入）**：`CHANGELOG.md:346` 的历史条目写作"1.0-08 Capability Token Envelope（ADR-015）"，但 `docs/adr/` 中并无 Capability Token 的 ADR；ADR 编号 015 现由"代码评审双层状态权威"占用，建议在该历史条目加注说明，避免编号含义冲突。

结论：**R1、R2 关闭；R3 保留为待补正项**（属状态措辞同步，不影响 §14.10 的设计批准结论与实施门禁）。

> 2026-09-20 补记：R3 的两处状态措辞已由评审 Agent 按状态同步原则直接补正（`design-code-review-v1.md` 第 5 行改为"职责调整已由 ADR-015 采纳"、CR-04 改为"（ADR-015 已采纳）"），**R1–R3 全部关闭**。

### 14.12 L0 binding RC1 契约评审（2026-09-20）

评审对象：`specs/profiles/code-review/v1/bindings/l0-service-contract.md`（RC1）及其支撑记录 `external-confirmations-2026-09-20.md`、`source-evidence.json`。完整评审记录见该契约 §9。

**结论：有条件通过（binding 仍不得定版）。** 本次不批准门禁 1，理由与设计方在确认记录中的自我约束一致——"契约定义已补齐不等于 T1–T6 实施证据已齐"。

独立复核（不依赖自述）：

1. **错误码词表完全对齐**：RC1 §7 引用的 24 个码与冻结 `schemas/error.schema.json` 枚举逐一相符（脚本核对：无未登记码、无遗漏码）。
2. **外部证据可验证**：`source-evidence.json` 的 12 个文件摘要已在本机 `D:\PycharmProjects\Nexus_Agent`、`Hczj_Assistant_Agent` 上重算，**12/12 相符、0 不匹配**；证据忠实，但仍不证明部署版本。
3. **摘要口径与 §15.3 一致**：Nexus 确认记录指出 HTTP 响应会重序列化、不能代替持久化字节，与 §15.3/CP-23 一致；`/raw` 端点是正确解法。
4. **outcome/coverage 不变式一致**：RC1 §6 的适配规则与冻结 `review_report.schema.json` 的 5 条 `allOf` 不变式完全一致。
5. **ACK 分层与发布正文来源**：TransportAck 明确不是 Profile Receipt；发布正文由服务端模板生成、不一致 `summary_text` 返回 422，消除了注入面。

阻塞项（定版前必须补，详见 RC1 §9.3）：**Q1** §1 遗漏 `external_coordinator_id`/`assignment_epoch`（与 §15.6 不一致）；**Q2** AttemptView 引入 Profile 未定义的新状态机，需声明为内部细节并给映射或走设计变更；**Q3** "有发现且覆盖不足"缺契约用例与呈现规则（本次已补规范包 fixture `valid/09_review_report_issues_found_with_inherited_gap.artifact_body.json`，并要求展示/发布必须同时呈现 coverage）。

门禁：BINDING-GATE-1 维持关闭；仍不得启动"符合本 Profile"的集成运行，不得声明 wire conformance。契约内的错误码、ACK 分层与 outcome 不变式可直接用于实现与 fixture 编写。

### 14.13 L0 binding RC2 复核（2026-09-20）

评审对象：`specs/profiles/code-review/v1/bindings/l0-service-contract.md`（RC2）。完整记录见该契约 §11。

**结论：修订核实通过；RC1 的 Q1–Q3 与 S1–S7 全部关闭，契约文本层面已无阻塞项。binding 仍不得定版**（BINDING-GATE-1 维持关闭，由外部证据与实现决定）。

逐项核实要点：

- **Q1 关闭**：§1 补齐 `external_coordinator_id`/`external_run_id`/`external_attempt_id`/`assignment_epoch` 四项，并给出 Run/Attempt/分配三级关联键、"不同 Coordinator 同名 ID 不得碰撞"与 epoch 围栏，`external_coordinator_id` 取自受信任注册而非 worker 自报——比原建议更完整。
- **Q2 关闭**：§3.1 把七个 Attempt 标签明确为**内部观察标签**并逐条给出到 Profile 可观察事实的映射（`expired` 还正确分流为 deadline / 仅租约失效 / 目标已更新三种），同时禁止把它当作第二套权威状态机。该处理优于评审原建议中"expired→deadline_exceeded"的简化说法。
- **Q3 关闭**：§6 规定展示与发布必须在同一摘要同时呈现 outcome 与 coverage，覆盖非 complete 时须显示缺口、遗漏范围与 inherited_gaps，禁止"已充分评审"表述；新增 `fixtures/binding/q3-outcome-coverage.md`（转换/重复/错误呈现/空发现四组行为用例，含结构拒绝与呈现拒绝两类），并如实声明 valid/09 只锁结构。
- **S1–S7 全部关闭**：候选词表统一（S1）、加严标注（S2）、`retry_after_seconds` 不变式引用（S3）、幂等 key 与投影分离（S4）、`repository_states` 显式 unknown（S5）、fixture 宿主统一（S6）、读取上限与拒绝语义（S7）。
- **评审者复算**：RC2 §7 错误表仍为 24 码零偏差；`source-evidence.json` 的 12 个文件摘要在 RC2 复算 **12/12 相符**；其 `unavailable` 记录经实测确认**准确**（`Nexus_Agent` 无 `.git`，`Hczj_Assistant_Agent\.git` 为空目录）。

RC2 新增建议（不阻塞，详见契约 §11.3）：R2-1 §10.1 引入的 HTTP 413 未进入 §7 错误表；R2-2 `data_policy_denied` 同时承载超限与保留期拒绝，建议用 `scope` 区分；R2-3 残留 "RC1" 标签与 T7 行未标注已确认；R2-4 `fixtures/binding/` 的机器校验边界宜在 §8 点明。

### 14.14 RC2 残留建议收口（2026-09-20）

§14.13 记录的 R2-1～R2-4 已全部修订并复核关闭，**且已机械化防止复发**（契约 §12 为完整记录）：

| 项 | 关闭依据 |
|---|---|
| R2-1 | 契约 §7 补 413 行；`specs/profiles/code-review/v1/tools/validate.py` 新增 `check_contract_error_table()`——契约 §7 的每个 code 必须在本包 `error.schema.json` 枚举内，且枚举中每个码都必须出现在表中 |
| R2-2 | 契约 §7 固定 `data_policy_denied` 的三类 `scope`（`read_limit` 413 / `retention` 422 / `policy` 403）并禁止"仅凭 code 判断原因"；实现侧 `agent_net/code_review/errors.py` 落同一分类学，`test_cr_data_policy_denied_scopes_are_distinguishable` 锁定三种 (scope, HTTP) 组合 |
| R2-3 | 契约 §8 改为"本契约定版后…"（不再自指修订号）；`l0-agentnexus-http.md` §9 去掉 RC1 硬编码；§7 的 T1–T7 表新增"状态"列，T7 标注"设计范围已确认、部署验证仍待做" |
| R2-4 | 契约 §8 新增"机器校验边界"段，明确 `validate.py` 强制范围仅限 `fixtures/valid/`+`fixtures/invalid/`，`fixtures/binding/` 的 Markdown 不经 schema 校验、仅由 manifest 固定摘要，并须登记 harness 命令与实际结果 |

**负例验证（证明新门禁不为空转）**：向契约注入未登记码 `payload_too_large`、删除 `scope=read_limit` 标注、删去一条已登记码的表行——三种情形自检均正确报错。

规范包升级 `1.0-draft.2+semantic.8`（自检：契约 24 码与枚举一致、正例 9/9、反例 14/14、manifest 51/51）。

**结论不变**：R2 收口属文本级修订，**BINDING-GATE-1 维持关闭**，binding 仍不得定版；剩余条件为 T1–T6 关闭、兼容清单三方冻结、CP-01～26 运行记录，均为外部证据与实现验收，不是契约文本问题。

## 15. draft.2 规范级补充与实现门禁

本节细化并优先解释前文歧义；以下“必须新增”均为待实现要求，不是已有能力。

### 15.1 范围与 binding 决议（P5/S2）

本版是**语义 Profile 设计**，不定义可实施的 transport binding，不声明 wire conformance；schema 和语义 fixture 也不等于 wire fixture。ACF 参照版本固定为 RFC-000 v0.3、RFC-001 v0.1、RFC-002 v0.1、RFC-003 v0.3；仅借用概念，不主张 RFC-002/003 profile 符合性、JCS 或跨域证明符合性。

发起职责固定：GitLab 事件由 Nexus 自动扫描入口归一化；HCZJ 消费 Nexus 持久化事件并创建评审目标；AgentNexus 仅经适配关联现有 Run。Nexus outbox ACK 仅指 HCZJ 已在本地事务保存事件及恢复责任后的消费确认，不表示任何评审/发布完成；本设计不新增或改写其既有 HTTP。

开始跨仓库集成前必须单独完成并评审 L0 binding：列出实际 HTTP 路径/CLI stdin-stdout 或 MCP 工具、Content-Type、认证主体、profile 协商、请求关联、超时、ACK/cursor、重复投递和错误状态映射。既有 `/coordination/executions/{execution_id}/result` 不能未经 §15.2～15.7 改造直接绑定本 Profile。没有 binding 时只允许独立语义验证开发，不启动“符合本 Profile”的集成运行。

### 15.2 状态翻译的责任层（P1/S5）

Profile-aware 输出适配器必须在 runner_loop 的通用重试分支、Daemon 自动签发收据及 Loop Engine 状态映射**之前**校验和翻译。Daemon 入口必须再次验证，不能相信客户端已校验。专用外部评审模板不得复用 `coding.v1` 的 code_review 阶段，不配置 `on_reject=implement`，不按 findings 或 changes_requested 重跑评审。

| 来源状态/动作 | Profile/HCZJ 语义 | AgentNexus 映射与反向限制 |
|---|---|---|
| 合法报告 completed + issues_found/no_findings/inconclusive | 校验通过后 completed，outcome 原样保留 | completed 仅完成本次观察/交付；反向必须读报告，不从 completed 推断 no_findings |
| changes_requested | 仅当含合法域报告时归一 completed+issues_found；否则 invalid_output | 在通用重试前消费，不产生代码返工分支 |
| failed | 由 Coordinator 按错误码决定 retry_wait/failed | 镜像失败；本地不分配 HCZJ 新 Attempt |
| blocked | failed + action_required，保留领域原因 | 可生成 DecisionGate；人工同意不复活原 Run，重评走 HCZJ |
| timed_out（执行器） | deadline_exceeded；仅在 Run 总期限/预算未耗尽且策略允许时由 Coordinator 重试 | 本地 timed_out，不能自动清零预算或调用模型 |
| cancelled（执行器） | 人工取消为 failed+cancelled_by_owner；目标更新为 superseded | 本地 cancelled；必须保留取消原因，不能反向推导人工取消 |
| queued/running/retry_wait | 按 HCZJ 权威状态展示 | 本地排队/执行状态不覆盖远端状态 |
| wait（Loop 动作） | 查询/等待，非 Run 状态 | 只轮询，不重建评审 |
| create_decision_gate（Loop 动作） | 人工操作入口，非 Run 状态 | 操作回到 HCZJ，Skip 不得制造 accepted 报告 |
| 未知 status / 普通文本 completed | invalid_output | 硬拒绝，不告警后放行 |

### 15.3 字节与摘要映射（P2/S9）

artifact_body 必须是字符串。摘要输入精确定义为：解析外层 JSON 后得到的 artifact_body 字符串，严格编码为 UTF-8（无 BOM、不加尾换行、禁止孤立 surrogate），所得字节称 B。`report_digest=SHA256(B)`，byte_length=len(B)。外层 JSON 的转义方式/空白不参与摘要；内层报告原有空白、顺序、换行均参与。禁止解析内层 JSON 后再序列化来计算原报告摘要。

| 当前字段 | 新增/映射要求 | 反向读取 |
|---|---|---|
| result_hash | 保留为旧内部幂等值，不用于 Profile delivery 冲突判断 | 不能用来补造 report_digest |
| artifact.content_hash | 新 Profile 产物必须填 `sha256:<hex>`，值来自 B | 读取 Vault 原始 B 后重验 |
| artifact_body/content_ref | 将 B 原样持久化到 Vault，引用不可变 | 存储失败必须失败，不允许截取 500 字符作为成功 fallback |
| 无历史 digest 的旧产物 | 非 Profile 产物；若迁移须重新读取完整字节并验证，记录迁移来源 | 不能仅凭旧 approved 升级为符合产物 |

源码 content_sha256 是绑定版本的指定行区间原始字节 SHA256；行分隔以 LF 定界、保留 CRLF 中的 CR、保留最后一行是否有 LF，不做换行归一；blob_sha 仍是完整 Git blob 对象 ID。严格 UTF-8 解码失败必须拒绝，不能替换字符后冒充原摘要。Nexus 既有接口若口径不同，binding 必须新增明确的原字节摘要字段或拒绝该 revision，禁止静默改解释。

### 15.4 词表与持久化映射（P3）

使用 `code_review.artifact_ref.v1` 和 `code_review.receipt.v1`；前文 Receipt 均指后者。ProfileReceipt 的 kind 为 received/validated/accepted/published，decision 为 confirmed/rejected；不与旧 `ReviewReceipt.decision=approved` 共用词表。

| Profile 字段 | AgentNexus 落点要求 | 反向规则 |
|---|---|---|
| artifact_id/producer_id/locator/digest | artifact_id/producer_did/content_ref/content_hash | 四项校验一致才建立引用 |
| schema_version/media_type/byte_length/access_scope/retention_until | 新增 artifact profile metadata 持久化字段或关联表，不能仅存在 UI | 缺任一必填字段不自动构造 Profile ArtifactRef |
| receipt schema/kind/decision/issuer/subject | 新增 Profile receipt payload 及索引；与旧 receipt 可关联但不可替换 | 旧 approved/passed 不能推导 validated/accepted/published |
| accepted receipt | 若上层流程需兼容 approved，仅经专用适配器生成“阶段交接成功”投影 | 投影必须标注来源及不代表代码通过，不能反向生成权威收据 |
| rejected receipt | 显示交付拒绝及 code | 不自动转为 coding run 返工 |

access_scope 由产物所属服务持久化，资源读取服务是执行点；retention_until 由该服务声明并在清理/获取时执行。AgentNexus 镜像不能延长来源服务的保留承诺。过期返回 artifact_expired；提前删除或权限变化必须可审计，不能声称引用永久可读。

### 15.5 强制能力与预算（P4）

Assignment 增加 enforcement_requirements；受信任部署注册给出每项 enforced/declared_only/unsupported 及执行组件，Worker 自报不足以满足要求。接单时对必需项 fail-closed：无执行能力返回 enforcement_unavailable，不启动模型。

| 约束 | 强制点 | 当前边界 |
|---|---|---|
| provider/外发数据范围 | HCZJ 模型网关、证据工具；执行环境限制旁路网络及凭据 | 普通 local_cli argv 白名单不等于网络隔离；不能隔离的 CLI 仅可声明 declared_only |
| token/成本累计上限 | HCZJ Run 预算账本与模型调用前预占/结算 | AgentNexus Loop 的次数/墙钟不能代替；未知消耗保守预占，不能零计费重试 |
| 工具轮次/时间 | Skill runtime 计数、执行器截止/终止 | 进程停止与提交权限失效分别记录 |
| 源码资源范围 | Nexus 查询鉴权与报告快照绑定 | 共享 token 不提供 Worker 级隔离 |

没有预算计量或网络执行点时，不得声称 CP-15/16 通过；要求这些能力的任务必须拒绝。只做 declared_only 的演示须明确标为非完整符合性，不能承接有相应强制要求的任务。

### 15.6 ID、围栏及目标排序（P6/S13）

Profile run_id 永远为 HCZJ Run ID。AgentNexus 必须新增持久化 external_coordinator_id/external_run_id/external_attempt_id/assignment_epoch，以及输入摘要、权威目标版本；本地 run_id/execution_id 保持独立。唯一关联键包含 coordinator_id，不按裸 run_id 全局关联。

epoch 由唯一 Coordinator 为分配单调递增；AgentNexus 存储其镜像，不能另分配竞争值。AgentNexus 交付入口必须在单个本地事务校验认证角色、关联 ID、目标版本、epoch、未过期租约和允许状态后写候选/镜像收据；HCZJ 接受业务交付时也在自身事务执行最终 CAS。两侧数据库无法原子提交，AgentNexus 本地成功只是镜像接收，只有 HCZJ accepted 可推进权威结果；网络分区不宣称全局即时撤销。

目标版本按权威维度比较：Nexus `(generation,execution_revision)` 字典序，仅同 MR 可比；HCZJ activation_revision 与 target_revision 各自在其权威域单调，target_revision 表示该 MR 目标分配顺序，指向确切 run_id/review_revision。接单/提交须匹配整个当前目标元组，不能把这些不同来源的数简单求最大。旧扫描事件不得回退已观测 Nexus 版本；新 activation 但旧 generation 也不能覆盖新 MR。对账回查权威状态，不按消息时间决定新旧。

### 15.7 角色授权（P7）

新增 `review:candidate_submit` 给被分配 Worker，仅提交候选；`review:deliver` 给 Coordinator，仅生成权威 accepted 交付。validated 由注册验证服务签发，received 由接收存储服务签发，published 仅 Publisher 在观察到实际写入后签发。模型和 Worker 不能自签 approved 来推进上层状态。

Daemon 必须基于已认证凭据绑定角色与 actor，覆盖 result、artifact、receipt 所有写入口；仅“能访问 Session”不够。Profile Session 的旧通用 `/coordination/receipts` 写入口必须拒绝不满足上述规则的写入。issuer_did/signature 正文不能赋予权限。

共享 token 无法区分多个不可信调用方时，角色表仅是部署约定，不能运行符合性授权测试或声明强制隔离；必须先接入可信网关的主体映射或独立受限凭据。任何签名字段都不能替代角色授权。

### 15.8 建议项补全

- **AssignmentAcceptance** 是 `code_review.assignment_acceptance.v1`，与 RFC-003 Grant Acceptance 无关；增加 acceptance_mode=worker_confirmed/adapter_attested，issuer 必须绑定认证身份，不能靠该字段自证。
- 等待接单属于 queued；queued 取消→failed(cancelled_by_owner)，超过接单/任务截止→failed(deadline_exceeded)。running 的租约失效按 §15.6 丧失提交权。
- 任一 inherited_gap 非空强制 coverage 上限 partial；保留 inherited_gaps 与本层 gap_reasons，不能用 file_selection 缩小来隐藏输入缺口。部分报告只能按显式策略发布“部分评审”摘要，禁止通过标记。
- 幂等比较投影为 §4.1 除 request_id/idempotency_key 外全部字段，包含已认证 requested_by、authority_ref、artifact digest、operation 和策略；缺省值先按 schema 展开，未知字段拒绝。以递归排序键、数组保持顺序、无空白 JSON、UTF-8（ensure_ascii=false）、禁止浮点/重复键生成比较字节；这只是限定类型的局部算法，不声明 JCS。存储比较字节及 SHA256，相同 key 不同投影返回冲突。
- 格式纠正使用新的 delivery_id，携带 replaces_delivery_id 和 correction_no=1，保持相同 Attempt/epoch；原拒绝记录不改写。传输重发同一候选则复用 delivery_id。
- 权限运行中撤销：失效当前 epoch，未完成 Run→failed(authority_denied)，请求终止 Attempt；候选及历史产物追加撤销关联记录，禁止发布。completed 不改终态，但立即撤销 current/发布资格；不声称已发到外部的数据可被收回。
- 策略内容变更不必重扫：复用有效 job/report，进入新摘要策略族 revision=1，更新 activation/target，旧未完成目标 superseded。回滚按 §4.2，不复活失败/过期 Run。
- 错误码均为 `code_review.error.v1` 局部词表，不与 ACF 错误直接等价。新增 unsupported_critical_extension、enforcement_unavailable、artifact_expired、coordinator_unavailable；前两者不重试并拒绝接单/解析；artifact_expired 需重新取得证据或人工处理；coordinator_unavailable 表示未配置或无法访问唯一 Coordinator，禁止启动评审、发布或退回本地自建 Run。未配置时 retryable=false、action_required=true；已配置但暂时不可达时 retryable=true、action_required=false，仅允许有界连接/状态查询重试，不重调模型。ACF binding 未来必须另给显式映射，禁止通过同名猜测。

### 15.9 规范宿主、交付顺序及新增验收

权威源是 AgentNexus 仓库路径 `specs/profiles/code-review/v1/`：schemas/、fixtures/、bindings/、compatibility.json、manifest.json、tools/。**2026-09-20 现状**：语义件已生成并通过自检——15 个 JSON Schema、9 个正例、14 个结构反例（各自绑定一条 MUST）、CP-01～26 矩阵、§15.3 摘要向量、`compatibility.json`、`manifest.json`（包版本 `1.0-draft.2+semantic.10`），自检入口 `python specs/profiles/code-review/v1/tools/validate.py`；`bindings/` 含 L0 binding 草案、**RC2 服务接口契约**与跨项目确认记录，其中 **RC2 已复核：Q1–Q3/S1–S7 全部关闭、文本层面无阻塞项，但 binding 仍不得定版（见 §14.13 与契约 §11）**；`fixtures/binding/` 存放行为验收规范（Markdown，不经 schema 校验）；wire fixture 尚未生成。任何仍未生成的文件不得当作已有交付。manifest 固定每个文件摘要、Profile 版本和来源 Git revision；发布只读版本包，其他仓库引用版本+摘要，禁止各自修改后仍使用同版本名；`manifest.source.worktree_dirty=true` 时该包仅为候选而非发布件。

**T1–T6 的关闭状态以 `bindings/evidence/closure-checklist.json` 为唯一追踪器**（2026-09-20 新增）：T1–T6 展开为 25 条逐项证据要求（责任人、采集模板、必需字段、机械验收检查），并区分「源码已确认」「本地合成证据（`non_closing`）」「生产/部署证据」三种证据等级——只有第三种能关闭 T 项。裁判为 `tools/check_evidence.py`（已接入 `validate.py`）：重算所有原始字节摘要、拒绝残留占位符、拒绝声明与实际不一致、拒绝在 T1–T6 未全部关闭时放行 `compatibility.json`。本段替代此前「契约定义已补齐」式的自述进度；**该追踪器存在且自检通过，不等于任何 T 项已关闭**。

compatibility.json 必须明确允许的 Nexus schema_version/contract_revision 列表、适配器版本、证据摘要口径；默认空列表拒绝全部，不得使用通配符推测兼容。构建 wire fixture 前先核对生产方对应版本的实际响应。

开发顺序调整为：本修订及 ADR/职责复核 → 字段/摘要/强制点确认与 L0 binding 评审 → schema、支持清单与 fixture 冻结 → 实现入口/存储/适配 → 运行 CP 验收。前文“完整 wire fixture”是 binding 完成后的交付，不是本次语义文档已提供的内容。

| ID | 输入/故障 | 必须观察到 |
|---|---|---|
| CP-19 | 同 MR 两个 job/人工重评并发 | 按 Nexus 版本与 HCZJ 目标 CAS，旧目标不能覆盖新目标 |
| CP-20 | 执行期间撤销权限 | epoch 失效、未完成 Run failed；历史只读，禁止发布 |
| CP-21 | 新 generation 后收到旧 scan.succeeded | 不回退版本、不重建旧目标 |
| CP-22 | 策略变更后回滚旧摘要 | 新 activation；新策略族/旧族核验规则明确，旧 epoch 无提交权 |
| CP-23 | 改变外层 JSON 转义但 artifact_body 相同 | report_digest 相同；内层换行改变则摘要改变 |
| CP-24 | Worker 调旧 receipt 路由伪造 approved | 未授权拒绝，不推进 Profile Session |
| CP-25 | 必需 provider/成本强制点缺失 | enforcement_unavailable，模型调用次数为零 |
| CP-26 | Vault 失败、旧 artifact 无摘要 | 不发布成功、不以截断正文或旧 result_hash 冒充产物 |
