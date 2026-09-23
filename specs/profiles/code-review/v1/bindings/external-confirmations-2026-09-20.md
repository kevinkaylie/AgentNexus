# L0 跨项目确认与评审输入（2026-09-20）

记录号：L0-CONFIRM-2026-09-20。依据用户授权，由总负责人核对 Nexus_Agent 与 HCZJ 当前工作树、设计和隔离测试，并在双方仓库落地记录。此记录是源码确认与设计建议，不替代独立 binding 评审、生产响应证据或实现符合性验收。

## T1–T7 结论

| 项 | 已确认事实／本轮设计决议 | 尚需完成／关闭条件 |
|---|---|---|
| T1 Nexus 事件与查询 | `/v3/review/events` 拉取、`/events/ack` 累计 ACK；Bearer；事件 `nexus.review_event.v1`；源码产出 `nexus.review_impact.v1`、contract_revision=3；报告冻结查询端点存在 | 缺生产方对应部署的响应样例、版本证据与适配验证；3 只是源码观察值，未加入运行允许清单 |
| T2 Nexus 报告字节 | report.json 使用 ensure_ascii=False、sort_keys=True、indent=2 的 UTF-8 字节，无尾换行；manifest.report_sha256 哈希此字节。建议 media_type=application/json、locator=`nexus-report:<provider_id>:<report_id>` | GET report 会解析并重序列化，不能用 HTTP 响应字节代替持久化字节；需原始字节读取/适配与 locator resolver。源码 splitlines 与 Profile LF 行边界也需验证 |
| T3 HCZJ 状态权威 | ReviewStore 已有 Run/Attempt、lease、activation_revision/target_revision CAS；运营 BFF 已存在 | BFF 是 Admin session/CSRF/项目权限接口；缺服务间 Run/Attempt/activation wire 契约与认证，不能用运营会话冒充服务凭据 |
| T4 HCZJ Coordinator | Coordinator 权威仍在 HCZJ；建议部署登记稳定 `urn:code-review:coordinator:<deployment-id>` | 缺 Assignment/Acceptance/Delivery 外部端点及 Profile ACK；需定义 HTTP 方法、凭据、幂等、错误与超时，并实现映射和行为测试 |
| T5 HCZJ Publisher | 建议 Publisher 归 HCZJ 应用边界，独立 GitLab 写凭据；publication outbox/operation_id 由 ReviewStore 新迁移持久化 | HCZJ 首版 F-223 明确不写 GitLab；这是待评审扩展，当前没有发布接口/outbox。不能把本地 current 指针切换当 published |
| T6 兼容清单 | 确认由 AgentNexus 维护中央清单、双方提供生产方版本证据，binding 评审和适配验证后冻结；建议候选 access_scope=`service_private` | 责任与冻结流程已确认；词表仍需认证/资源授权语义及跨项目评审，运行词表仍为空；T6 整体未关闭 |
| T7 L0 边界 | 确认仅 loopback（127.0.0.1/::1）允许带认证 HTTP，无 TLS；跨主机不属于本版 | 设计范围确认；不表示部署已验证。0.0.0.0 监听不能自动认定 L0，跨主机须另行 binding 与安全评审 |

**关闭状态：T1–T6 保留开放项，T7 的设计问题已确认。§14.10 门禁 1 仍未关闭，L0 binding 不予定版。** 不得将本次源码确认等同生产响应确认。所有新增接口仍须在 binding 中完整定义端点、方法、认证、Content-Type、幂等、ACK、超时、错误映射；“尚未实现”不构成接口契约。

## 必须先解决的语义差异

HCZJ 当前报告是 `hczj.review_report.v1`，覆盖率是 `hczj.review_coverage.v1`，outcome 为 findings_present/no_findings/inconclusive。存在实质 coverage gap 时，即使有 findings 也可为 inconclusive；Profile 则要求非空 findings 对应 issues_found。适配不能只重命名字段：需显式保留 findings 与 coverage，按 Profile 不变式生成目标 outcome，并为“有发现且覆盖不足”添加契约用例。原 HCZJ outcome 应保留于原始产物，不能把信息丢掉后宣称两者等价。该映射须经设计评审。

Nexus report_id 不是报告字节摘要；HTTP JSON 重序列化可能改变字节，必须以已验证的持久化原始字节构造 ArtifactRef。Nexus scan outbox 也不是 GitLab publication outbox。

## 双方交付与证据

- Nexus：`Nexus_Agent/docs/l0-binding-confirmation-2026-09-20.md`。主要源码：`api/routes/v3_review_jobs.py`、`api/routes/v3_review.py`、`review_jobs/store.py`、`impact/review.py`、`impact/review_artifacts.py`、`impact/review_queries.py`。
- HCZJ：`Hczj_Assistant_Agent/docs/specs/2026-09-20-l0-binding-confirmation.md`。主要源码：`admin/routes_reviews.py`、`skills/code_review/contracts.py`、`skills/code_review/storage/store_runs.py`、`store_targets.py`、`store_verify.py`；设计：`docs/specs/2026-09-14-hczj-auto-review-design.md`。
- 当前工作树文件摘要见 [source-evidence.json](source-evidence.json)，仅用于标识本次核对对象，不能证明已部署版本。

隔离测试（2026-09-20）：

```text
Nexus_Agent:
python -m pytest tests/test_review_jobs_api.py tests/test_review_artifacts.py -q
17 passed

Hczj_Assistant_Agent:
python -m pytest tests/unit/test_code_review_contracts.py tests/unit/test_code_review_h3_freshness.py tests/unit/test_code_review_bff.py -q
132 passed
```

上述测试只验证已有组件，不是 CP-01～26 全套，也不是三方 wire 端到端验收。本轮不读取生产凭据、不发送 GitLab 评论、不修改生产实现。

## 后续交付顺序

1. Nexus：提供部署版本对应的脱敏响应样例；设计原始字节读取契约和冻结证据行边界。
2. HCZJ：补机器调用 API 与认证、Assignment/Acceptance/Delivery/取消契约、outcome 映射；独立评审 Publisher 扩展与存储迁移。
3. AgentNexus：将这些契约写入完整 L0 wire 表，落实 §15.2–15.7 的适配、角色授权与 CAS；三方复核 T1–T6 后定版兼容清单和 binding。
4. 按 §15.1/§15.9 门禁开展集成与 CP 验收；在此之前保持默认拒绝，不声明 wire conformance。

## 交付方式（2026-09-20 补）

T1–T6 的关闭不再靠本记录自述，而在 [`evidence/closure-checklist.json`](evidence/closure-checklist.json) 逐条追踪：25 条证据要求，各自写明责任人、采集模板与机械验收条件。双方按 [`evidence/README.md`](evidence/README.md) 复制 `evidence/templates/T{n}.json` 到 `evidence/received/T{n}.json` 回填即可；**原始字节以 base64 承载并由 `tools/check_evidence.py` 重算摘要**，因此"与生产一致"这类自述不能作为关闭依据。每项除正例还须给出冲突/越权/未知值的拒绝例；部署版本必须以 `deployment_version` 记录，本记录与 `source-evidence.json` 都只定位核对对象，不作部署证据。
