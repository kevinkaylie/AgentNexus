# 三项残余问题核对与修复确认（2026-09-23）

本记录是提交方对代码与文档的自查，供后续独立评审使用；不宣称 L0 wire conformance，不改 T1–T6 的关闭状态。

| 项目 | 本轮处理 | 状态 |
|---|---|---|
| HCZJ H/messages 错误映射 | 缺/空 `Idempotency-Key` 在解析正文前返回 422 `input_mismatch`；头与 `message_id`（Delivery 例外 `delivery_id`）不符返回 409 `idempotency_conflict`，不写入新消息。Flask 真 HTTP 测试覆盖缺头、错头、Delivery 特例和正确头。 | 代码已修复，待独立评审 |
| HCZJ 原 S1 reviewer 归属 | Delivery 接受事务比对 `report.reviewer_id` 与当前绑定 worker；不匹配时异步 MessageView 拒绝，未写报告、未签 accepted Receipt。当前仅有 `worker_confirmed` 路径；未来若加入 `adapter_attested`，先设计受信任身份映射。 | 当前路径代码已修复，待独立评审 |
| 评审 S5 台账 | 受 Git 跟踪的 `threads/README.md` 改成公开可读的归属和记录规则；历史线索迁入 `.gitignore` 排除的 `threads/local-ledger.md`，统一线索 ID 小写、角色称谓为“维护者”，标注 2026-07-09 快照和待复核状态。`docs/community/` 为 Git 跟踪的拟公开论坛草案；本轮未向外部论坛发布。 | 文档整理完成 |
| C-1 网络约束 | `local_cli` 只启动本机 argv 子进程，没有 OS 网络隔离器，`network_access: deny_by_default` 仍为 `declared_only`。YAML 显式注释；两个测试夹具把误导性的 `local-cli` enforced 组件改名为 `synthetic-test-enforcer`，表明只测注册门禁。 | **继续开放**，不得作为 CP-25 网络强制证据 |

## 验证

- HCZJ 服务及跨仓库鉴权组合：**28 passed**；HCZJ `tests/unit/`：**4243 passed / 2 skipped**（176.87 秒）。新增负例包括原 S1 的 `unassigned:reviewer`，结果为 rejected / `authority_denied` / 无 accepted Receipt；H/messages 错头为 409，缺头为 422。
- AgentNexus 代码评审 API/HTTP 合成注册门禁专项：**110 passed**；全量 **810 passed / 9 skipped / 0 failed / 0 errors**（418.59 秒），`scripts/check_full_suite.py --input .pytest_three_residual_report.txt` **exit 0**，未刷新基线。规范包 `tools/validate.py` exit 0。
- `threads/local-ledger.md` 经 `git check-ignore -v` 确认为本地文件；公开 README 不含历史个人跟进动态。仅通过文件状态确认归属，没有以旧台账推断 2026-09 的外部进展。
- 整理的是当前工作树的公开内容；此前已被 Git 跟踪的台账文本仍可能存在于历史提交。本轮没有改写仓库历史。

## C-1 收口条件

要把 `network_access` 从 `declared_only` 提升为 `enforced`，需要实际受控执行环境：子进程在隔离容器/沙箱中运行，默认拒绝出站网络和绕过路径；部署注册项绑定到该执行组件，并在真实子进程上验证直连、DNS、代理及网络开启/关闭行为。接单时对要求强制隔离而未装配的环境返回 `enforcement_unavailable`，且不得启动模型。当前仓库的注册表单元测试、配置传递和 prompt 文本均不能替代这些证据。
