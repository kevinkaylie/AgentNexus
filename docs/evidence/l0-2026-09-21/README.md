# T1–T6 实施与本地证据包（2026-09-21）

**可以提供本地、可复现的接口样例与实施证据；本包不是生产响应证据。** 两个项目已新增 RC2 服务接口及测试。样例由实际 FastAPI/Flask 路由和临时 SQLite/归档生成，使用合成输入与测试验证器；未访问真实 GitLab、模型或生产凭据。BINDING-GATE-1 保持关闭，compatibility 运行允许列表未放宽。

## 证据索引

| 项 | 本次可以交付 | 尚不能据此关闭的部分 |
|---|---|---|
| T1 | [Nexus HTTP 样例](nexus-http-samples.json)：事件拉取/累计 ACK、报告 schema/revision=3；原有 API 定向测试 | scan.succeeded 是合成种子，不是实际扫描完成；仍缺真实部署响应、版本来源及 target_sha 字段映射确认 |
| T2 | 同一文件中的 ArtifactRef/raw/source-bytes；真实字节摘要/长度、CRLF/Unicode 分隔符测试、401/403/410/412/413 等拒绝用例 | 实际部署的持久化/保留承诺、原有接口授权及容量适配未验收 |
| T3 | [HCZJ HTTP 样例](hczj-http-samples.json)：请求/重放/Run/Target/401；同库 CAS、activation、renew 测试 | 全局 activation 限制、无目标初始化降级仍需评审；生产服务身份尚未登记 |
| T4 | Coordinator/Run/Attempt/epoch 持久化、消息 inbox/outbox、TransportAck 与 Receipt 区分、交付与取消围栏测试 | 后台可靠投递、旧 worker/BFF 的完整 Profile 适配和强制能力注册仍需接通；不能将入库 ACK 当成执行完成 |
| T5 | HCZJ publication 操作/尝试表、GitLab 客户端、Publisher 独立身份、unknown 查证不重发、coverage 同显测试 | 测试使用假 GitLab；未发送真实评论，未取得部署级写入/读回/过期修正证据 |
| T6 | service_private 项目/session/角色检查与拒绝测试；本次源码指纹、规范包摘要引用 | 候选词表尚未三方冻结；中央允许列表仍为空，未声明 wire conformance |

## 测试记录与证据等级

- [Nexus 定向 JUnit](nexus-test-results.xml)：29 通过，其中新增绑定测试 12 项。
- [HCZJ 全量单元 JUnit](hczj-unit-results.xml)：4229 通过、2 跳过；共 4231 项。包含本次 14 项服务测试。
- [HCZJ 服务复跑 JUnit](hczj-service-results.xml)：最后收紧 Publisher 身份与错误 action_required 后，14 项全部通过。全量记录早于这两处收紧；最终服务代码由此复跑覆盖。
- [源码与证据摘要](source-snapshot.json)：源文件、样例/JUnit SHA256、Git 可用性、中央 Profile manifest 摘要。外部两目录没有可用 Git HEAD，commit/dirty 记录 unknown，不能伪造版本证明。
- 中央 `tools/validate.py` 仍通过（9 正例、14 反例、51 文件摘要）；不把其 26 项 CP 矩阵结构检查称为 26 项行为测试通过。

**采集 pin 与复核记录（2026-09-21，按评审 S3 更正）**：`source-snapshot.json` 的 `profile_manifest_sha256` 是**采集当时**的包摘要 pin，**不得因为包升级而改写**——它记录的是"这批样例是在哪个包版本下产生的"。中央包此后升级到 `1.0-draft.2+semantic.10`，pin 因此与当前包摘要不一致，这是**预期**的；正确做法是保留原 pin 并在 `profile_manifest_rechecks` 中另记复核证据（检查时间、`checked_against_sha256`、命令、范围、结果，以及**是否重跑过旧样例**）。

本包此前曾把 pin 直接改成新值并附 `profile_manifest_refreshed`，评审指出：**替换采集时 pin 不足以证明新版兼容**，且该记录的 `refreshed_at` 还早于 `captured_at`。现已回退为原 pin + 复核记录。

**必须明确**：这些 HTTP/JUnit 样例是在 semantic.9 时期产生的，**未**在 semantic.10 下重跑；`reexecuted` 为 `false`。因此它们只能作为"非关闭的历史样例"，不能据此推断新版兼容；正式关闭证据必须匹配其声明版本并重新执行必要检查。

T1–T6 的收口清单见 `specs/profiles/code-review/v1/bindings/evidence/closure-checklist.json`：本包在清单中逐项登记为 `non_closing` 本地证据，因此**本包的存在不会关闭任何 T 项**，也不会放宽兼容允许列表。该审计是中央仓库专有项——规范包复制到别处后按宿主标记自动跳过，仍可独立交付。

样例中的 HTTP 401/403 是故意验证的拒绝结果，不是采集失败。HCZJ MessageView 示例由 requester 查询 worker 的消息得到 403，证明查询主体限制；accepted Receipt 通过有权限的 Run 回执列表读取。报告、ID、工程名均是合成数据。测试凭据不写入样例。

## 重现

在 Nexus_Agent 工作目录：

```powershell
python -m pytest tests/test_review_binding.py tests/test_review_jobs_api.py tests/test_review_artifacts.py -q
python tools/capture_l0_samples.py <nexus-output.json>
```

在 Hczj_Assistant_Agent 工作目录：

```powershell
python -m pytest tests/unit/test_code_review_service.py -q
python -m pytest tests/unit/ -q --tb=short
python tools/capture_l0_samples.py <hczj-output.json>
```

测试默认引用同级 AgentNexus 规范包；非同级布局设置 `CODE_REVIEW_PROFILE_PACKAGE`。样例的时间与 UUID 每次重现可变，应比较契约不变式与各次对应 manifest，而非要求跨次文件字节完全相同。

## 实施范围与剩余门禁

Nexus 实施说明：`Nexus_Agent/docs/l0-binding-implementation.md`。HCZJ 实施/降级声明：`Hczj_Assistant_Agent/docs/specs/2026-09-21-l0-service-implementation.md`。本次没有修改 AgentNexus §15.2–15.7 的运行时代码，没有自动启动服务、常驻调度或 GitLab Publisher。

下一份部署证据需绑定：真实部署 commit/构建摘要、脱敏响应、已登记的主体/角色/资源授权、Nexus contract_revision/target_sha 映射、原始字节保留承诺及实际发布查证记录。所有测试样例始终保留 `production=false`，不得在复核时替换标签来关闭 T1–T6。
