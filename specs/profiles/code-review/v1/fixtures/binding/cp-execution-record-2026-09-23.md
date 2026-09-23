# CP-01～26 执行记录（AgentNexus 侧，2026-09-23）

本记录由 `scripts/run_cp_matrix.py` 生成，可重跑。**不声明符合性、不声明 wire conformance**：`verified` 只表示本仓声明的证据在同一次运行中执行通过；裁定权在 HCZJ / Nexus 的用例标为`blocked`，只覆盖一半的标为 `partial`，二者都不构成该 CP 已通过。

## 运行输入

- 规范包版本：`1.0-draft.2+semantic.16`
- manifest 摘要：**故意不内嵌**——本记录本身由 manifest 登记，内嵌会对「记录被登记」形成循环；方向是 manifest 固定本记录的摘要（见 `manifest.json` 中本文件条目），版本变化后须重新生成本记录。
- CP 定义：`fixtures/cp-matrix.json`（sha256 `32799440b4d46075ce1f477e2c4e0543047ffa5dcf0f5df94855245ef71c205d`）
- 覆盖映射：`bindings/l0-agentnexus-cp-coverage.json`（sha256 `bcc80ed024469cfe5c37d6ac1f1af46bf7e99ba8fbddd5a9df5d162fa04f917a`）
- 行为测试获取方式：--input（外部报告）
- 命令：`python -m pytest <48 node ids> -q -p no:cacheprovider --tb=no -rA > .pytest_cp_report.txt`
- 环境：受限沙箱（禁止创建子进程的环境跳过相关文件）；行为测试使用合成存储、进程内 ASGI/Flask 客户端与临时数据库，不访问生产服务、不执行真实 GitLab 写入。

## 逐用例结果

| CP | 阶段 | 类型 | 声明状态 | 结构/摘要判定 | 行为证据 | 结果 |
|---|---|---|---|---|---|---|
| CP-01 | ingest | behavioral | verified | — | 3/3 passed | AgentNexus 侧通过 |
| CP-02 | ingest | behavioral | verified | — | 3/3 passed | AgentNexus 侧通过 |
| CP-03 | assignment | behavioral | verified | — | 2/2 passed | AgentNexus 侧通过 |
| CP-04 | validation | behavioral | verified | ok 1 | 2/2 passed | AgentNexus 侧通过 |
| CP-05 | execution | behavioral | verified | — | 3/3 passed | AgentNexus 侧通过 |
| CP-06 | execution | behavioral | blocked | — | — | 无本仓证据 |
| CP-07 | execution | behavioral | verified | — | 3/3 passed | AgentNexus 侧通过 |
| CP-08 | validation | structural | verified | ok 3；spec-doc 1（非机器判定） | 3/3 passed | AgentNexus 侧通过 |
| CP-09 | validation | structural | verified | ok 3；spec-doc 1（非机器判定） | 3/3 passed | AgentNexus 侧通过 |
| CP-10 | evidence | behavioral | partial | ok 1 | 3/3 passed | 部分通过 |
| CP-11 | delivery | behavioral | verified | ok 2 | 3/3 passed | AgentNexus 侧通过 |
| CP-12 | publication | behavioral | blocked | — | — | 无本仓证据 |
| CP-13 | publication | behavioral | blocked | — | — | 无本仓证据 |
| CP-14 | execution | behavioral | verified | ok 1 | 2/2 passed | AgentNexus 侧通过 |
| CP-15 | execution | behavioral | blocked | — | — | 无本仓证据 |
| CP-16 | assignment | behavioral | partial | ok 2 | 3/3 passed | 部分通过 |
| CP-17 | validation | behavioral | verified | — | 3/3 passed | AgentNexus 侧通过 |
| CP-18 | recovery | behavioral | partial | — | 2/2 passed | 部分通过 |
| CP-19 | execution | behavioral | partial | — | 2/2 passed | 部分通过 |
| CP-20 | execution | behavioral | partial | — | 2/2 passed | 部分通过 |
| CP-21 | ingest | behavioral | blocked | — | — | 无本仓证据 |
| CP-22 | execution | behavioral | partial | — | 2/2 passed | 部分通过 |
| CP-23 | validation | digest | verified | ok 2 | 3/3 passed | AgentNexus 侧通过 |
| CP-24 | authorization | behavioral | verified | — | 4/4 passed | AgentNexus 侧通过 |
| CP-25 | assignment | behavioral | verified | ok 1 | 2/2 passed | AgentNexus 侧通过 |
| CP-26 | validation | digest | verified | ok 2 | 2/2 passed | AgentNexus 侧通过 |

## 汇总

- AgentNexus 侧通过：**15**；部分通过：**6**；无本仓证据（blocked）：**5**；证据失败/缺失：**0**
- 行为测试实际执行：87 passed / 0 failed / 0 skipped

## 限制与未覆盖（不得据此声称通过）

- **CP-06**（blocked，owner=Hczj_Assistant_Agent）：『自动路径不得覆盖更高人工 revision』的仲裁点是目标 revision 权威，按 ADR-015 属 HCZJ，本仓只镜像不裁决。
- **CP-10**（partial，owner=AgentNexus）：本仓验证的是协议侧分类（缺失 404 / 过期 410 / 错误信封字段冻结）；真实证据源的权限、缺失与暂时不可达分类需要与 Nexus 证据端点联调（T1/T2）。
- **CP-12**（blocked，owner=Hczj_Assistant_Agent）：发布 outbox 的 unknown→查证原操作逻辑在 HCZJ 侧；本仓只有发布角色授权，没有发布操作查询能力（q3 harness 对应用例显式 skip）。
- **CP-13**（blocked，owner=Hczj_Assistant_Agent）：『阻止当前发布或标记已发评论过期』属 HCZJ 发布状态机；本仓不持有 GitLab 写入权威。
- **CP-15**（blocked，owner=AgentNexus）：本仓没有 token/成本计量点，也没有网络/预算强制器：Assignment 的预算只被透传，`network_access` 仍是 declared_only。缺强制点不得声称 CP-15 通过（§15.5，评审 C-1）。
- **CP-16**（partial，owner=AgentNexus）：接单 fail-closed（enforcement_unavailable / data_policy_denied）已实现并验证；声明为 enforced 的**实际强制**依赖真实隔离执行环境，属 T1–T6 之外的部署条件。
- **CP-18**（partial，owner=AgentNexus）：崩溃窗口的持久化恢复已验证；『不回退 revision/activation』的裁决权在 HCZJ 目标权威。
- **CP-19**（partial，owner=AgentNexus）：本仓的交付 CAS（状态/租约/deadline/输入清单/绑定）已验证；『按 Nexus 版本 × HCZJ 目标』的跨侧 CAS 需双侧联调（T1–T5）。
- **CP-20**（partial，owner=AgentNexus）：历史只读（过期 410）与 epoch 失效拒绝已验证；『未完成 Run failed』的状态迁移属 HCZJ 状态机。
- **CP-21**（blocked，owner=Hczj_Assistant_Agent）：『不回退版本、不重建旧目标』由目标/版本权威裁定，本仓不持有该状态。
- **CP-22**（partial，owner=AgentNexus）：旧 epoch 无提交权已在事务内验证；『新 activation 与策略族核验规则』属 HCZJ。

## 结论

- 本记录只覆盖**门禁允许范围**（BINDING-GATE-1 关闭、仅独立语义验证，无集成运行）。T1–T6 仍未关闭，`compatibility.json` 未三方冻结，因此 **CP-01～26 不构成符合性结论**。
- 上表 `blocked` / `partial` 的用例在相应 owner 提供证据并复核前一律视为未通过。
- 重跑：见文件头用法；记录内所有摘要可按输入自行复算核对。
