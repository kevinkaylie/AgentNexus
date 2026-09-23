# Code Review V1：跨 Agent 合并前评审

日期：2026-09-07。状态：设计草案，待评审；本轮仅编写需求与设计，不表示 AgentNexus 已实现该流程。

> 2026-09-18 补充：[Code Review Collaboration Profile v1](code-review-collaboration-profile-v1.md) 定义详细协作契约。根据 Nexus/HCZJ 2026-09-14 已确认 Run 身份，Profile 提议由 HCZJ 作为评审状态唯一权威、AgentNexus 作为协作适配层。下文关于 AgentNexus 新建 ReviewRun/独占调度的内容是早期方案，不应直接实施；职责调整已由 [ADR-015](../adr/015-code-review-state-authority.md) 采纳（2026-09-18），本文件保留为历史需求与早期方案，不改变外部已确认契约。Nexus 已推进到自动证据扫描，不能再按下文 N-M1 时间点判断其当前完成度。

## 需求

| ID | 需求 | 验收 |
|---|---|---|
| CR-01 | 接收 GitLab MR 的创建、重新打开、代码更新和人工重评 | 标题修改不重复触发；可信适配器获取 MR diff refs |
| CR-02 | 固定实例、项目 ID、MR IID、base/head、目标分支版本和策略版本 | 运行中不切换输入提交；新提交触发新一代任务 |
| CR-03 | 调用 Nexus_Agent 获取版本化影响证据 | 前后证据分开；缺失版本/解析失败显式呈现 |
| CR-04 | 通过 Profile adapter 关联 HCZJ 权威评审（ADR-015 已采纳） | 复用外部 Run，输出适配先于通用状态映射 |
| CR-05 | HCZJ 管业务 Run/预算、Nexus 管扫描、AgentNexus 管本地适配与 epoch 镜像 | 双侧本地 CAS；旧 epoch 拒绝；不承诺跨库原子性 |
| CR-06 | 验证并发布 MR 摘要 | 发布前核验当前 head；旧报告标记 superseded，不标绿 |
| CR-07 | 人工重跑及问题反馈 | 有效/误报/已修复/暂不处理均关联报告与问题 ID |
| CR-08 | 明确授权与审计 | 仓库读取与评论写入分权；模型不能操作发布凭据 |

一期为本机开发者预览，优先 Java 业务 MR。自动修复、合并、跨公网 Worker、多租户、强签名交付和 Python 图谱后移。

## 架构与复用（历史方案，已被取代）

> 本节保留用于追溯，**不得作为开发依据**。现行设计以 [Profile draft.2](code-review-collaboration-profile-v1.md) §2、§15.2、§15.6～15.7 及 [ADR-015](../adr/015-code-review-state-authority.md) 为准；HCZJ 管理业务 ReviewRun，AgentNexus 仅保存外部关联与本地适配状态。下述旧表和接口建议未获本节重新授权。

复用 Secretary intake、CoordinationSession、PlaybookRun、StageExecution、Objective Execution、Vault artifact/receipt 和 DecisionGate。增加 code_review.v1 模板：impact -> review -> validate -> publish。不得复制一套通用调度器；ReviewRun 是业务关联记录，运行阶段状态由 PlaybookRun 负责。

Nexus_Agent 只提供知识和证据；HCZJ 只负责评审 Skill 内的模型/工具循环；AgentNexus 负责跨服务推进。GitLab 适配器首版可在 Nexus webhook 所在进程接收事件，归一化后提交 Daemon；不能绕过 Daemon 写数据库。

接入方式优先使用现有 L0 ExecutionBackend/CLI adapter：Nexus 的 JSON CLI 输出封装为 ImpactReport artifact；HCZJ 的后台 CLI 输出归一到现有 agentnexus_json_v1 交付格式。HTTP worker 后端单独评审后再实现，不能把本设计当成已有远程 Worker 支持。

## 数据模型与接口契约（历史方案，已被取代）

> 本节保留用于追溯，**不得作为开发依据**。现行设计以 [Profile draft.2](code-review-collaboration-profile-v1.md) §4～7、§15.3～15.4、§15.6 及 [ADR-015](../adr/015-code-review-state-authority.md) 为准；HCZJ 管理业务 ReviewRun，AgentNexus 仅保存外部关联与本地适配状态。下述旧表和接口建议未获本节重新授权。

ReviewRequest：schema_version、request_id、gitlab_instance_id、project_id、mr_iid、project_alias、base_sha、head_sha、target_sha、policy_version、budget、owner_did、actor_did、attempt_reason。

ReviewRun（拟新增 Daemon 存储表）：run_id、coordination_session_id、playbook_run_id、请求字段、generation、active 标记、创建时间。review_publications：run_id、report_hash、note_id、status、publish_attempt、last_error。finding_feedback：report_id、finding_id、actor_did、label、comment、时间。所有字段访问继承 Owner/actor 校验，迁移与存储测试必须补充。

ImpactReport 使用 Nexus `nexus.review_impact.v1`：project/base/head、前后 snapshot、impact、coverage、limitations。保留原始报告作为 Vault artifact，映射层不能把 partial 改为 complete。

ReviewReport：schema_version、run_id、base/head、impact_artifact_ref、execution_status、coverage、findings、limitations、model_version、policy_version、usage。Finding：id、severity、path、side、line、trigger、impact、evidence_refs、suggested_validation。引用须绑定仓库/commit/blob；解析结构成功不等于事实正确。

拟新增业务入口（尚未实现）：POST /code-reviews、GET /code-reviews/{run_id}、POST /code-reviews/{run_id}/rerun、POST /code-reviews/{run_id}/feedback。使用现有 Daemon API 前缀和鉴权惯例；落地前补 API schema、SDK facade 和鉴权矩阵测试。本设计不在当前 API 参考中标为可用。

## 幂等、过期与恢复

业务去重键包含实例/项目/MR/base/head/target/policy；传输 delivery ID 单独去重。人工重跑新建 attempt 并保留旧产物。更新 MR generation 与 supersede 旧运行在一个事务中完成，阶段租约恢复遵循现有执行器。

发布适配器使用持久化 outbox 与 MR 维度串行发布锁。提交前重新读取 MR 当前 head 与开放状态；失败标记 publication_failed，可重试。评论带稳定 run/report 标记，网络超时结果不确定时先查已有标记，避免盲目新增。发布后再次核验 head，若竞态发生，更新评论为过期。外部 GitLab 不能与 SQLite 原子提交，不承诺严格 exactly-once 或永远无短暂过期窗口。

## 权限与质量

Webhook 校验部署所支持的 GitLab secret；实例/项目映射只接受本地允许列表，禁止 webhook 指定任意 clone URL。解析在受限环境进行，候选源码/注释/文档不能改变工具权限；自动执行测试作为后续独立隔离能力。GitLab write token 仅 publisher 使用，Nexus/HCZJ 不接触。

execution_status=completed/failed/cancelled 与 coverage=complete/partial 分开。findings=[] 不等于通过；缺失证据、预算耗尽、未解析和非支持语言必须保留。一期输出建议性摘要，不替代人工审批或 branch protection。

## 实施与验收

1. 契约固定与本地 fixture；接入 Nexus M1 CLI。
2. HCZJ 真实后台 Skill adapter；一次手动 ReviewRun 全流程。
3. Daemon 业务记录、模板、outbox、事件入口、GitLab 摘要发布。
4. 并发 MR、乱序事件、重复回调、执行器重启、旧 SHA、发布超时、未授权项目等故障回归。
5. 10–20 个历史 MR 回放：使用当时源码/依赖快照，对比 diff、源码、图谱输入；记录人工确认问题、误报、遗漏及成本。

完成标准：真实 MR 更新后得到对应版本的报告；中断可恢复；新提交后旧报告明确过期；用户可反馈并重跑。Nexus 单独产出 ImpactReport 不代表上述整条链路完成。
