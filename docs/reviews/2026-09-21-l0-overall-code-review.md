# L0 三方实现整体代码评审（2026-09-21）

对应 CR-REVIEW-2026-09-21-01。结论：**需修改后复审，不批准本批实现完成；BINDING-GATE-1 维持关闭，T1–T6 全部开放。**

范围包括 AgentNexus 当前工作树 A/B/C 组，以及此前本助手在 Nexus_Agent、Hczj_Assistant_Agent 编写的 L0 端点、客户端、服务与本地证据。外部实现也按同一标准评审，不能因已有单测和样例视为已接通。当前为未提交工作树审查，不是固定 commit 的发布认证。本次仅新增评审材料、填写评审结论与状态记录，没有修改运行时代码、测试基线、兼容允许列表或旧采集样例。

## 阻塞性问题

### B1 / P1：角色授权使用调用方自报身份，能冒充 Coordinator

位置：`agent_net/node/routers/code_review.py:205`、`:232`，`agent_net/node/_auth.py:80`。

新服务入口仅校验共享 Daemon token，然后用信封 `sender_id` 查角色；没有凭据→principal→sender 的绑定。隔离实测，同一 token、同一消息，只把 sender 从 worker 改为已登记 coordinator，结果由 **403 变为 202，且 enforcement=enforced**。`receipt.issuer_id` 也可独立自报。未配置 `_daemon_token` 时旧依赖还会直接放行。此行为违反 RC2 §1 的独立凭据、缺配置拒绝、sender 绑定与 worker 权限隔离；降级注释不能解释已登记角色时的假 enforced。

修复：新服务建立独立认证依赖并返回受信任 principal，强制角色与资源授权；sender/issuer 必须与认证主体或登记委托一致。补跨主体冒充、未配置、worker 伪造 accepted/published 的负例。

### B2 / P1：消息及产物读取未执行 session/Run 资源授权

位置：`agent_net/node/routers/code_review.py:303`、`:426`。

GET message 不传 actor 即跳过检查；传未登记角色主体也因 `if roles` 条件放行。GET raw 完全不使用 actor，按 artifact_id 直接读通用 artifacts 表和 Vault，未约束相同 session/Run，也未检查保留期。实测无 actor 的消息读取与 raw 读取均为 **200**。持有一个服务 token 的调用方可读取知道 ID 的其他任务产物；`service_private` 标签没有形成 RC2 §4 所需资源边界。

修复：从认证主体推导允许的 project/session/Run，查询与返回前验证资源归属、Profile 类型和过期状态；补跨 Run、跨 session、已过期与未授权读取测试。不要仅将 actor 改为必填。

### B3 / P1：上传请求和返回引用无法与 HCZJ wire 校验衔接

位置：`agent_net/node/routers/code_review.py:343`、`:354`、`:367`、`:415`；RC2 §4，`schemas/artifact_ref.schema.json`。

按契约七字段上传 DTO 发送会 **403**，因为实现额外要求正文 producer_id/actor_did。加上该非契约字段后，UTC 字符串 `retention_until="2099-01-01T00:00:00Z"` 被静默改为 **null**，返回 **201**，绕过保留承诺上限。返回引用还有 schema 禁止的 `enforcement` 字段；传数字保留期也不是冻结 schema 的时间字符串。HCZJ 的严格 schema 校验会拒绝该引用，即使删除额外字段也会因无保留承诺拒绝 delivery。

同一边界另有 DTO 漂移：GET MessageView 包了一层 `{status,message}`，且 receipts 保存的是内部记录而非 Profile receipt 信封；TransportAck 也增加未约定字段。修复应以实际响应跑冻结 schema/DTO 契约测试，而非只断言几个字段。producer 从认证取得；保留期严格解析、持久化并完整返回，超出承诺拒绝。

### B4 / P1：重复上传破坏已登记不可变产物，上传幂等未实现

位置：`agent_net/node/routers/code_review.py:377`、`:380`；`agent_net/persistence/deliverable_store.py:78`。

调用方可传 artifact_id，代码先覆盖相同 Vault key，再 INSERT 主键冲突。实测首次 **201**，相同 ID 不同正文第二次 **500**，之后读原产物变为 **409 evidence_digest_mismatch**：失败请求已破坏原始字节。相同 Idempotency-Key 的普通重试还会返回两个不同 artifact_id。

修复：严格拒绝 DTO 外 artifact_id，落实凭据/资源域内幂等映射；不可变字节采用不会覆盖已登记产物的存储方式，冲突检查与登记应保证失败不修改原产物。补相同 key 重放/冲突、并发和存储后失败测试。

### B5 / P1：入站消息只校验信封外壳，空 Assignment 也被 ACK

位置：`agent_net/code_review/validation.py:222`，`agent_net/node/routers/code_review.py:235`。

parse_envelope 只确认 payload 是 dict，没有按 type 校验 payload schema；缺少 enforcement_requirements 被当成空列表。实测 `assignment.payload={}` 返回 **202 stored**，缺少冻结输入、输出 schema、预算和 deadline 的任务进入 inbox。未知字段、若干字段类型和信封/payload 关联 ID 也没有完整核验。当前测试把空 payload 当成功样例，因此通过数无法证明 RC2 admission 正确。

修复：接收前执行冻结 envelope 及按消息类型的 payload schema，并检查双方关联 ID 一致；需要能力未提供时明确拒绝，不能通过缺省空数组绕过约束。以全部合法 fixtures 和对应删字段/类型错误负例覆盖真实 HTTP 入口。

### B6 / P1：receipt inbox 与业务处理分事务，崩溃后重试永久不处理

位置：`agent_net/node/routers/code_review.py:236`、`:259`、`:280`。

store_message 已提交后才写 receipt；receipt 分支仅在 `state == "created"` 执行。模拟 inbox 持久化后写 receipt 抛异常：首次 **500**，恢复后同消息重试 **202**，数据库仍为 **stored，receipts=[]**。重放因状态为 replayed 永远跳过处理，没有该入口的重启恢复消费者补偿。这违反 RC2 §4 的 inbox/处理意图及业务变更/回执事务要求。

修复：用原子 inbox+处理意图及可重启消费者，或同事务写 receipt 与完成状态；以业务幂等键保护重复处理。补三个故障窗口：写 inbox 后、写 receipt 后、更新 processed 前。

### B7 / P1：provider 转换静默丢弃 finding，产生错误的无发现报告

位置：`agent_net/code_review/provider_adapter.py:136`–`:140`。

`_map_findings` 先过滤非 Mapping 元素，后续 `_finalize_findings` 的类型校验永远看不到被过滤项。实测 HCZJ 原 outcome=findings_present、findings=["malformed-finding"]、coverage=complete，经公共管线输出 **no_findings、findings=[]**，未报错。该错误会把无法解释的评审发现转成可发布的无发现结论。同类过滤也用于 omitted_files/inherited_gaps，可能丢失缺口信号。

修复：对输入 finding/coverage 集合逐项严格验证，格式错误直接 invalid_output，不允许过滤后推导结论；检查原生 schema 版本（当前 source_coverage_schemas 仅声明未强制），补混合合法/非法条目和缺口条目反例。

### B8 / P1：HCZJ 实际客户端无法同时通过 Nexus 新旧两套鉴权

位置：外部 `Hczj_Assistant_Agent/skills/code_review/service_runtime.py:18`，`service_clients.py:94`–`:96`；`Nexus_Agent/api/routes/v3_review.py:21`、`v3_review_binding.py:75`。

这是此前本助手实现中的接线缺陷。HCZJ 每个 provider 仅配置一个 base_url/token，先用它读新 `/reports/{id}/raw`，随后又读旧 `/mrs/...`、`/jobs/...`，证据核验还读旧 `/reports/{id}`。新端点验证独立 principal token，旧端点仍验证 NEXUS_API_TOKEN；按独立凭据部署，raw 成功后旧请求会鉴权失败，ReviewRequest 无法完成核验。单测用回调代替 verify_input，合成样例没有发现这条链路。

修复：为必要旧读端点增加带资源授权的 L0 facade，或在受信任注册中区分 endpoint audience 与凭据，同时保留资源授权。不能以关闭旧鉴权或共享两种 token 作为验收方案。补一个真实组合两侧应用、不同 token、经过 verify_input/verify_evidence 的本地集成测试。

### B9 / P1：收口裁判可以把没有拒绝事实的记录判为满足拒绝检查

位置：`specs/profiles/code-review/v1/tools/check_evidence.py:342`、`:420`、`:428`。

独立确认提交方 S-1：worker_refusal_evidenced=true 且无拒绝样例可通过；forged_receipt_rejected 样例返回 **200** 也可通过；unconfigured_behavior 写 `does not reject; allows requests` 因含 reject 通过。三项调用均返回空 failures。这里验证的是这些特定检查被绕过，并非声称伪造三个字段即可通过所有 25 项要求。

修复：按样例的主体、操作、实际 HTTP status、解码错误码及错误 schema 校验拒绝事实，要求原始字节摘要与样例一致；缺样例/200/错误主体/错误端点/错误码均拒绝。人工来源确认仍必需，但已具备机器可判条件不能只信布尔或文字。

### B10 / P2：规范包自检强依赖宿主仓库的非关闭证据，不能独立交付

位置：`specs/profiles/code-review/v1/tools/check_evidence.py:33`、`:718`、`:835`。

复制完整 v1 包到独立临时目录，运行 validate.py，进程退出 **1**，唯一实质缺项为 `docs/evidence/l0-2026-09-21` 不存在。这是中央仓库本地合成证据，未随 manifest 包交付，也不参与关闭 T1–T6，却被当成外部使用包的必需文件。独立复现确认 S-2。

修复：拆分可移植规范包自检与中央仓库证据审计；包内 received 关闭证据仍须严格检查，不能为可移植性整体跳过关闭验证。增加复制到任意目录/只读包的验收。

## 建议性与信息性事项

- **S1 / P2，HCZJ 报告归属**：`service_messages.py:116` 起检查 Run/Attempt/摘要等，但不检查 reviewer_id。在既有隔离 fixture 中改为 unassigned:reviewer，仍 processed 并签 accepted。建议与分配 worker/登记代理归属核对；若有 adapter_attested 归属差异，先明确转换规则。复现使用信任测试回调，不代表已验证真实证据抓取。
- **S2，C 组运行约束**：LocalCLIBackend 未执行 network_access；stdout/stderr 解码后按字符截取 max_output_bytes，不能证明字节预算或网络隔离。作为明确标注 declared_only 的本地配置可保留；不能据此注册 enforced。若要用于 Profile，缺真实强制器必须拒绝相应 assignment。单纯更改配置声明不构成 CP-25 证据。
- **S3，证据出处**：原 source-snapshot 的 profile_manifest_sha256 是采集时 pin，不应只因为包升级就改成新 pin。当前虽留旧值和理由，仍不能据此推断旧 HTTP/JUnit 在 semantic.10 下执行过；refreshed_at 还早于 captured_at。保留原 pin，另记 checked_against/检查时间/命令/新结果。漂移对 non_closing 历史样例可以告警；正式关闭证据必须匹配其声明版本并重新执行必要检查。
- **S4，基线维护**：此次全量没有失败，旧 25 项环境豁免均已失效。原生检查器退出码为 **2**，不是代码回归；评审未修改基线。提交方应在相同环境明确收窄基线，再提供 exit 0，不能以更新基线掩盖 B1–B10。
- **S5，公开材料与提交组织**：建议 C 组与 A/B 分开提交，理由是配置和社区文案生命周期不同，便于追溯，不代表要求用户新增授权。未发现足以仅凭这些公开项目链接判定机密泄露的依据；台账角色称谓、ID 大小写、公开/本地归属应整理。没有执行任何对外发布。
- **S6，维护性**：sample_list 只取第一个列表键、导入校验器可能写 __pycache__、无作用检查标记、CHANGELOG 条目位于 Unreleased 之前，均记录后续改进；B9/B10 修复时宜覆盖多列表与只读场景。没有必要倒拆未发布 semantic.10 的历史版本；修复规范包内容后更新 manifest/版本，并重新 pin 外部使用方。

## 评审请求 §8 的八项答复

| 问题 | 结论 |
|---|---|
| 1. S-1 | 阻塞，见 B9，须样例级检查与反例。 |
| 2. S-2 | 阻塞规范包独立交付，见 B10；不是现有仓库内自检失败。 |
| 3. C-1 | 本地 declared_only 可接受；宣称/要求 enforced 则阻塞，缺强制器拒绝接单，见 S2。 |
| 4. C-4 | 建议明确公开/本地归属并分离提交；本次证据不足以认定泄密，不增设披露审批。 |
| 5. S-4 | 留痕可接受，替换采集时 pin 不足以证明新版兼容；应保留旧 pin 并新增复核证据，见 S3。不把所有验证退化成告警。 |
| 6. S-10 | 无需追溯拆为两次；后续实质修复按内容升级并重算 manifest。 |
| 7. C 与 A/B | 建议拆分提交，整体评审仍涵盖两者；拆分不能豁免各自问题。 |
| 8. S-13 | 遗留临时目录清理不作为批准条件；后续优化兜底目录与资源关闭。评审不删除不明历史目录。 |

## 独立验证与复现

| 检查 | 本次结果 |
|---|---|
| AgentNexus 全量 `python -m pytest tests/ -q -p no:cacheprovider --tb=no` | **679 passed, 9 skipped，无 failed/errors**；原始报告 `.pytest_review_full_report.txt` |
| `scripts/check_full_suite.py --input .pytest_review_full_report.txt` | **进程 exit 2**：旧 25 个环境失败项未再失败，需维护基线；通过数未下降 |
| 规范包 `tools/validate.py` | exit 0；15 schemas、9 正例、14 反例、26 CP 条目、61 manifest 文件；CP 条目检查不等于 26 个行为测试通过 |
| `tools/check_evidence.py` | exit 0；0/6 closed，gate closed，6 个本地非关闭证据 artifact |
| AgentNexus `pytest tests/ -q -p no:cacheprovider -k code_review` | **126 passed, 1 skipped, 561 deselected**；与请求中的 127 collected 一致 |
| Nexus `tests/test_review_binding.py` | **12 passed** |
| HCZJ `tests/unit/test_code_review_service.py`，指向当前中央包 | **14 passed** |
| 独立复制规范包后 validate | **exit 1**，缺宿主 docs/evidence 目录，见 B10 |

复现命令（从 AgentNexus 根目录运行）：

```powershell
python docs/reviews/l0_review_repro.py
python docs/reviews/l0_hczj_review_repro.py
```

脚本使用临时数据库、虚拟凭据、既有测试 fixture 与故障注入，无生产网络。第一份覆盖 B1/B2/B3/B4/B5/B6/B7/B9，第二份覆盖建议 S1。记录见 [2026-09-21-l0-review-probes.json](2026-09-21-l0-review-probes.json)。脚本 exit 0 表示复现过程成功，不表示被审实现通过验收。

本次未重跑 HCZJ 整仓数千项历史测试，未验证生产部署或真实 GitLab 写入；未将合成样例转为关闭证据。B8 依据两侧真实调用路径与认证实现的静态交叉核对，仍需上述组合集成用例确认修复。

## B8 修复跟进（2026-09-21，用户授权实施）

原评审发现保留。HCZJ 已修复：L0 与 legacy metadata 客户端/凭据分离，显式配置不同 token；可信旧读桥接器在 IO 前校验 instance/project，并先确认 MR 身份及 job 指针才读 job；证据报告改读 L0 raw，保留 Nexus 项目及保留期授权，无凭据回退。

新增 `tests/unit/test_code_review_evidence_auth.py` 与 `tests/support/l0_nexus_auth_probe.py`；定向 **25 passed**，包含真实 Nexus/HCZJ 路由和鉴权的组合测试（合成存储、进程内 HTTP），错误凭据与跨项目拒绝均覆盖。此次修复后 HCZJ 全量 **4240 passed, 2 skipped**，exit 0；组合测试实际运行，无 skip。配置迁移见外部 `Hczj_Assistant_Agent/docs/specs/2026-09-21-l0-service-implementation.md` 的 B8 节。

B8 状态为**已修复并本地验证，待复审**。该状态不修改原评审事实，也不关闭其他问题、T1–T6 或 BINDING-GATE-1。旧 token 的宽权限由可信 HCZJ 桥接器限制，不声称 Nexus 旧元数据接口自身已改为细粒度授权。旧证据包不改写，新指纹及结果见 [B8 修复证据](2026-09-21-b8-fix-evidence.json)。
