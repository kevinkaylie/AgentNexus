# L0 三方服务接口契约 RC2

状态：2026-09-20，**RC2 已按 Q1–Q3/S1–S7 修订，待复核，新增接口尚未实现**。本文件补充 `l0-agentnexus-http.md` 的 T1–T6；不修改已批准 Profile 的消息 schema、状态权威或实施门禁。冲突时以 Profile 为准并阻止定版。RC2 是 binding 修订号，不是新的 Profile 版本。

## 1. 地址、身份和公共传输规则

部署注册表由管理员配置三项 loopback base URL：Nexus、HCZJ、AgentNexus；禁止从消息正文接收任意服务 URL。HCZJ 稳定身份为 `urn:code-review:coordinator:<deployment-id>`，重启不变。AgentNexus 必须持久化 external_coordinator_id、external_run_id、external_attempt_id、assignment_epoch 与执行映射（Profile §15.6）。Run 唯一关联键为 (external_coordinator_id, external_run_id)，Attempt 关联键为 (external_coordinator_id, external_run_id, external_attempt_id)，分配版本再包含 assignment_epoch。不同 Coordinator 的同名 ID 不得碰撞；查证与 CAS 均须核对此身份元组，旧 epoch 不得覆盖新分配。external_coordinator_id 取受信任部署注册及已认证 Coordinator，不取 worker 自报值。

新增接口使用独立 Bearer 凭据，服务端凭据记录绑定 principal_id、角色、允许的 instance/project/session。缺少配置必须拒绝，不能沿用“未配置 token 则放行”。`sender_id` 必须与认证主体一致；委托关系须在服务端登记。角色为 requester、coordinator、worker、validator、publisher、policy_admin、evidence_reader；一项凭据可登记多个角色，但 worker 不得拥有 accepted/published 写权限。Admin Cookie/CSRF 不用于这些服务接口。Nexus 旧共享 NEXUS_API_TOKEN 只代表旧接口能力，部署 Profile 前须增加项目资源授权适配层。

除原始字节读取外均为 `application/json; charset=utf-8`，请求/响应 UTF-8 无 BOM。严格拒绝重复键、非有限数和未知字段。新增接口必带 `X-Correlation-Id`；变更接口带 `Idempotency-Key`。信封中的 correlation_id 必须与头一致。认证失败先于资源详情返回，日志屏蔽凭据。所有响应 `Cache-Control: no-store`。

Profile 消息正文直接引用 `../schemas/envelope.schema.json`，不额外包一层或随意追加字段。以下 HTTP ACK/查询 DTO 属 binding，不是新 Profile 消息类型。标记 optional 的字段可缺省，其余字段必需，未声明字段拒绝。ID 为非空字符串；revision/epoch 为正整数；digest 为 `sha256:`+64 位小写十六进制；UTC 时间使用 RFC3339 Z；分页 cursor 为不透明字符串。

## 2. Nexus：事件、证据和原始报告（T1/T2）

| 方法与路径 | 状态 | 请求与成功响应 | 认证/幂等与 ACK |
|---|---|---|---|
| GET /v3/review/events?after_seq=N&limit=L | 已有 | N≥0，1≤L≤500；200 `{items,next_seq}`，事件 `nexus.review_event.v1` | HCZJ evidence_reader；重复读取允许，按 event_id 去重 |
| POST /v3/review/events/ack | 已有 | `{consumer:"hczj-review",through_seq:N}`；200 `{acked:N}` | 同上；累计 ACK，禁止越过已投递最大 seq，重复不回退 |
| GET /v3/review/jobs/{job_id} | 已有 | 200 现有 job 投影 | evidence_reader；只读 |
| GET /v3/review/reports/{report_id} | 已有 | 200 `nexus.review_impact.v1` JSON | evidence_reader；解析结果，不保证响应字节等于持久化报告 |
| POST /v3/review/reports/{report_id}/source | 已有 | `{side,snapshot_id,path,start_line,end_line}`；现有源码投影 | evidence_reader；只读，不执行扫描 |
| POST /v3/review/reports/{report_id}/call-chain | 已有 | `{side,snapshot_id,interface_id,direction,depth,min_confidence}`；现有图查询投影 | evidence_reader；只读 |
| GET /v3/review/reports/{report_id}/diagnostics | 已有 | query side/kind/offset/limit；现有 diagnostics 投影 | evidence_reader；只读 |
| GET /v3/review/reports/{report_id}/artifact | **新增** | 200 ArtifactRef，schema_version=`nexus.review_impact.v1` | evidence_reader，服务端按报告归属校验项目；只读 |
| GET /v3/review/reports/{report_id}/raw | **新增** | 200 report.json 原始字节；Content-Type: application/json；Content-Length 精确 | 同上；只读，禁止重新序列化、压缩或换行变换 |
| POST /v3/review/reports/{report_id}/source-bytes | **新增** | `{side,snapshot_id,path,start_line,end_line}`；200 原始区间字节，application/octet-stream | 同上；只读，行号从 1 开始、闭区间；不得截断到合法范围 |

新增 artifact/raw/source-bytes 错误使用 §7；旧接口错误由客户端适配，不宣称旧响应已经是 Profile error。旧查询 DTO 的冻结依据是双方源码与对应版本样例，不能在未知 contract_revision 上猜测字段兼容。

ArtifactRef 使用既有 schema 全部必填项：locator=`nexus-report:<provider_id>:<report_id>`；两个 ID 作为 URI 分量百分号编码，解析后只可查注册服务，禁止当 URL 或磁盘路径使用；media_type=`application/json`；access_scope=`service_private`。digest/byte_length 取已持久化并经 manifest 校验的 report.json，retention_until 由存储承诺给出，不得猜测；本 L0 绑定加严（非 Profile 通用要求）：要求非空且至少覆盖 Run deadline，不能承诺时拒绝注册产物。artifact_id 取持久化 report_id，producer_id 取注册 Nexus 服务身份，digest_algorithm 固定 sha256-bytes-v1。raw 响应 `ETag: "sha256:<hex>"` 必须与 ArtifactRef 一致；若有 `If-Match` 且不同，返回 412 evidence_digest_mismatch。先完整校验再发送；过期 410 artifact_expired，缺失 404 evidence_unavailable，存储摘要损坏 409 evidence_digest_mismatch。

source-bytes 仅以 LF 字节 0x0A 分行，保留 CRLF 与原编码字节、末行无 LF；空文件无第 1 行。start/end 越界或 start>end 返回 422 input_mismatch；snapshot 与 report/side 不符返回 409 input_mismatch。响应 ETag 对所返回区间原字节取 SHA256；不能复用旧 source 的 splitlines 结果。路径只允许冻结包内已登记文件，禁止路径穿越/符号链接越界。证据引用按 Profile 行范围与相同字节摘要构造。

HCZJ 必须先将每个事件及处理意图持久化，再推进连续已落地 seq 的 ACK；某条失败不能跳过后 ACK 更大 seq。ACK 表示接管事件，不表示评审完成。scan.succeeded 必须有 job_id/report_id/generation/execution_revision；按 report 冻结查询，禁止回退实时图谱。源码观察的 contract_revision=3 只作候选，生产方版本样例确认前不启用。

## 3. HCZJ：状态、激活与租约（T3）

以下 `/api/service/code-review/v1` 简写为 H，全部新增；不替代运营 BFF。

| 方法与路径 | 主体 | 正文/响应与状态 |
|---|---|---|
| POST H/requests | requester | ReviewRequest 信封；202 RequestAck；幂等 key=payload.idempotency_key |
| GET H/requests/{request_id} | 原 requester/coordinator | 200 RequestAck；未登记 404 input_mismatch |
| GET H/runs/{run_id} | 授权 requester/coordinator/该 Run worker | 200 RunView |
| GET H/runs/{run_id}/attempts/{attempt_id} | coordinator/该 Attempt worker | 200 AttemptView，不返回 lease secret |
| GET H/targets/{instance_id}/{project_id}/{mr_iid} | requester/coordinator/publisher | 200 TargetView；无目标 404 input_mismatch |
| POST H/targets/{instance_id}/{project_id}/{mr_iid}/activation | policy_admin | `{review_policy_sha256,expected_activation_revision,expected_target_revision}`；200 TargetView；Idempotency-Key |
| POST H/runs/{run_id}/attempts/{attempt_id}/renew | 该 Attempt worker | `{assignment_epoch,requested_lease_seconds}`；200 AttemptView；Idempotency-Key |

RequestAck=`{request_id,run_id,review_revision,status_url}`。入站事务建立请求映射及初始调度意图后才返回 202；run_id 恒为 HCZJ Run ID，同一幂等投影返回原 ACK，不能多建 Run。status_url 是相对 H 路径。request_id 是独立的请求定位唯一约束，不属于业务比较投影；同 request_id 必须绑定原主体、资源、幂等 key 和投影，否则返回 idempotency_conflict。同幂等 key、同投影但新 request_id 返回原 RequestAck，不另建请求或 Run；调用方使用返回的原 request_id 查询。Run 四元唯一键保持 `(job_id,report_id,review_policy_sha256,review_revision)`；initial/重复扫描事件复用正确 revision，rereview 由 HCZJ 分配，不由调用方递增。

RunView=`{run_id,job_id,report_id,review_policy_sha256,review_revision,state,active_attempt_id,target_revision,activation_revision,current,accepted_report_digest}`；current 与 accepted_report_digest 分别为布尔值与可空 digest，active_attempt_id 可空；state 使用 Profile Run 状态，内部状态必须经映射。读取完成不代表 current。

AttemptView=`{run_id,attempt_id,assignment_epoch,state,lease_expires_at,deadline}`，state 为 offered/accepted/running/completed/rejected/expired/cancelled，仅是 binding 查询 DTO 的内部观察标签，不是新增 Profile 状态机，不据标签单独改变 Run 或签发回执；映射见 §3.1。时间可空仅限尚未发出租约的 offered。TargetView=`{instance_id,project_id,mr_iid,generation,execution_revision,review_revision,activation_revision,target_revision,review_policy_sha256,run_id,report_digest,freshness}`，尚无报告时后两 ID/digest 可空，freshness=verified/unknown/stale。新目标不存在时激活请求两个 expected revision 均为 null，只有“确实不存在”才允许创建；已存在必须均为正整数并相等。创建或改变策略与目标及调度意图在同一事务提交。激活同策略不隐式 rereview。

Coordinator 内部调度事务分配 Attempt 和单调 epoch、冻结输入摘要及目标版本，再写 Assignment outbox。**不提供 worker 自选 Run/抢占 claim 接口**。worker 接受 Assignment 即完成领取；内部 lease_token 不跨服务传输，认证主体+Attempt+epoch 绑定现有内部租约。renew 只允许当前未过期且未取消 Attempt，requested_lease_seconds 为 1..60，实际续期不超过 Run deadline，不改变 epoch；过期不能复活。同 key 返回原到期时间，不重复延长。

Delivery 提交必须在 HCZJ 本地事务复核角色、Attempt、epoch、租约、deadline、input_manifest_digest、冻结目标及激活 revision；事务保存唯一报告与 accepted 回执。策略变化返回 policy_changed，输入变化 superseded_input，租约/epoch 失效 stale_assignment。Nexus 当前性依赖外部读取，不伪装成跨库事务；无法核验则 freshness_unknown，不更新 current。

### 3.1 Attempt 内部观察标签与 Profile 映射（Q2）

| 内部观察标签 | Profile 可观察事实与约束 |
|---|---|
| offered | 已持久化 Assignment，等待 AssignmentAcceptance；Run queued（重试仍沿用 retry_wait），不声称已执行 |
| accepted | 接单已确认；Run 可由 Coordinator 转 running；不是报告 accepted Receipt |
| running | Run running，校验中也只属内部 phase |
| completed | 本 Attempt 已结束；只有通过 Delivery CAS 保存有效产物，Run 才可 completed；current 仍独立核验 |
| rejected | AssignmentAcceptance rejected 并保留 reason_code；不可恢复则 Run failed，可恢复按既有重试策略处理；不得从标签猜测错误码 |
| expired | 超出 Run deadline→deadline_exceeded/failed；仅租约失效→stale_assignment，Run 按预算进入 retry_wait 或 failed；目标已更新则 superseded，不一概归 deadline_exceeded |
| cancelled | 保留 CancelRequest/ACK 事实；人工停止映射 Run failed + cancelled_by_owner 审计原因；目标/策略替换映射 superseded；cancelled 标签不证明 worker 已 stopped |

查询 RunView.state 始终仅六态 queued/running/retry_wait/completed/failed/superseded；外部决策依据权威 Run、结构化错误与回执，禁止将 Attempt 标签当第二套权威状态机。历史终态不因上述映射复活。

## 4. 协作消息、产物与回执（T4）

AgentNexus `/coordination/code-review/v1` 简写为 A，以下全部新增。本节不授权通用 `/coordination/receipts` 写 Profile 权威回执。

| 方法与路径 | 发送者 → 接收者 | 正文/成功响应 | 幂等键（**必须**经 `Idempotency-Key` 头传递） |
|---|---|---|---|
| POST A/messages | HCZJ coordinator → AgentNexus | assignment/cancel_request 信封；202 TransportAck | `= envelope.message_id`（必填） |
| POST H/messages | 已分配 worker → HCZJ | assignment_acceptance/delivery/cancel_acknowledgement 信封；202 TransportAck | `= envelope.message_id`；**delivery 例外**：`= delivery_id` |
| POST H/messages | requester → HCZJ | feedback/cancel_request 信封；202 TransportAck | `= envelope.message_id`（必填） |
| POST A/messages | 已登记 coordinator/validator/publisher → AgentNexus | receipt/error 信封；202 TransportAck | `= envelope.message_id`（必填） |
| GET A/messages/{message_id} 或 H/messages/{message_id} | 原发送者或授权 coordinator | 200 MessageView | 只读 |
| POST A/artifacts | 被分配 worker | `{run_id,attempt_id,assignment_epoch,artifact_body,media_type,schema_version,retention_until}`；201 ArtifactRef | `Idempotency-Key`（上传自有键，取值不由 message_id 规定） |
| GET A/artifacts/{artifact_id}/raw | 授权 coordinator/validator/publisher | 200 原始字节，按 media_type；Content-Length/ETag | 只读 |
| GET H/runs/{run_id}/receipts?after=C&limit=L | 授权该 Run 主体 | 200 `{items,next_cursor}`，items 为 receipt 信封，next_cursor 可空，1≤L≤100 | 只读 |

**消息幂等键的传输位置与取值（2026-09-22 裁决，消除此前歧义）**：§1 与本节不是两套独立幂等键，而是分别规定**传输位置**与**取值**——§1 规定变更请求通过 HTTP `Idempotency-Key` 头传递幂等键；本节规定消息类接口的幂等键**取值**为 `envelope.message_id`（delivery 例外为 `delivery_id`）。两者表示**同一个**逻辑幂等键，**不得**分别建立幂等记录。**发送方与接收方都必须实现该头，不得省略**。

执行规则（所有消息类 POST 端点一致）：

| 情况 | 结果 |
|---|---|
| 缺少或空 `Idempotency-Key` | **422 `input_mismatch`**，不写入（在解析正文前先拒绝） |
| 头与规定取值不一致（如 ≠ `envelope.message_id`） | **409 `idempotency_conflict`**，不写入 |
| 两者一致，同键同业务投影 | 返回原处理结果（幂等重放，不重复签发/不新建记录） |
| 两者一致，同键不同业务投影 | **409 `idempotency_conflict`**，**无副作用** |

冲突判定必须在**任何写入之前**完成；被拒请求不得留下消息、回执或产物记录。

**入站消息的资源授权（2026-09-22 澄清，对应复审 R3-1）**：`session_id` 必须解析到**唯一**已登记的 Profile 会话，无法解析（未登记）或解析出多条（歧义）**一律拒绝**——"查不到"不是放行条件，角色许可也不替代资源许可。此外必须核对**受信任关联**：信封 `run_id` 必须等于该会话已绑定的 `external_run_id`；assignment 的 `coordinator_id` 必须由已认证 Coordinator 代表（§1：`external_coordinator_id` 取受信任部署注册及已认证 Coordinator，不取自报值）。**新 Run 的绑定由受信任的部署初始化流程建立，本组端点不承担创建职责**；不接受来自消息正文的隐式创建。

**上传的分配围栏（对应复审 R3-2）**：上传除入口检查外，必须在**登记产物的事务内**重新读取并校验同一分配的 worker、Coordinator、Attempt、epoch、**租约 `lease_expires_at`**、deadline 与执行状态；任一项失效即不得登记产物、不得把幂等映射置为 committed。外部存储可先写入内容寻址字节，但字节已存在**不能**代替当前授权。同命名空间同键已 committed 时，提交阶段直接返回原产物（不得以数据库冲突收场，对应复审 R3-3）。

TransportAck=`{message_id,status:"stored",status_url}`，只在 inbox 和处理意图原子持久化后返回；不是 received/validated/accepted Receipt。MessageView=`{message_id,state,receipts,error}`，state=stored/processed/rejected，receipts 是 Profile receipt 信封数组，error 为 error.schema.json 或 null。持续轮询可观察异步拒绝，不因 202 放弃查证。inbox 消费与业务变更、回执 outbox 在同一事务提交，崩溃可重放。

Artifact 上传严格按 §15.3 解码 artifact_body 后编码 UTF-8 获取 B；无 BOM、孤立 surrogate 拒绝。服务器计算 digest/byte_length，不接受调用方自报摘要代替校验。locator=`agentnexus-artifact:<artifact_id>`，仅注册 resolver 可解析；access_scope=service_private，retention_until 不得小于请求值，无法承诺则 422 data_policy_denied。产物不可变，上传不是业务接收。读取仅允许相同 session/Run 的服务身份；过期/摘要冲突按 §2 处理。

同 delivery_id 的输入先核对绑定 Run/Attempt/epoch，不允许换目标；相同 artifact digest 返回原处理结果/原 Receipt，不重复签发。不同 digest 返回 409 delivery_conflict。纠正必须新 delivery_id、replaces_delivery_id 与 correction_no=1，遵守 Profile 一次纠正规则。其余消息 key 相同但 payload/关联目标不同返回 409 idempotency_conflict。

received 仅存储服务签发；validated 仅已登记 validator；accepted 仅 HCZJ Coordinator 经 CAS 后签发；published 仅 Publisher 观察到实际写入后签发。回执路由必须校验 kind 对应角色。worker 自带 receipt、issuer_did 或 signature 不赋权。取消先由 HCZJ 持久化撤销与 epoch 围栏再投递通知；等不到 worker ACK 也不能让旧交付恢复有效。

## 5. Publisher 与 GitLab 边界（T5）

这是 HCZJ F-223 首版之外的**待评审扩展**。Publisher 位于 HCZJ 应用边界，用独立 GitLab 凭据；worker 无发布权限。

| 方法与路径 | 主体 | 正文/成功响应 |
|---|---|---|
| POST H/publications | coordinator | publication_request 信封；Idempotency-Key=operation_id；202 PublicationView |
| GET H/publications/{operation_id} | coordinator/publisher/授权 requester | 200 PublicationView |

PublicationView=`{operation_id,run_id,report_digest,state,gitlab_note_id,receipt,error}`；state=pending/in_flight/unknown/published/failed/obsolete，gitlab_note_id 为可空正整数，receipt/error 可空；receipt 为 Profile receipt 信封，error 为 Profile error。客户端不得设置 outbox_state（只能缺省或 null）。summary_text 不直接执行或透传：服务端基于 accepted 报告与确定性模板生成正文；不一致的非空 summary_text 返回 422 invalid_output。

HCZJ ReviewStore 新迁移建立 publication_operations（operation_id 唯一）、publication_attempts（尝试与核验）、message_outbox。保存意图、不可变投影、报告摘要、模板版本/正文摘要、expected target_revision、Profile expected_version/activation、状态及审计时间；创建操作与 outbox 同事务。target_revision 从 HCZJ 权威记录获取并冻结，不由新增 Profile 字段携带。相同 operation_id 比较全部意图字段（不含 outbox_state），不同为 idempotency_conflict。

GitLab 适配器只允许注册实例与项目，操作限定 MR 普通评论：建立评论、按已保存 note_id 更新本操作评论、分页列出评论查证。协议不允许 approve/merge/执行正文命令。GitLab API v4 固定使用 POST `/projects/:id/merge_requests/:merge_request_iid/notes` 创建（JSON `{body}`），PUT 同路径加 `/:note_id` 更新（JSON `{body}`），GET 列表及 GET `/:note_id` 查证；id/IID/note_id 必须来自允许项目与持久化记录。凭据用 PRIVATE-TOKEN 头，列表必须读取全部分页后再作查证结论。创建成功记录响应 id；更新成功仍需读取验证正文。依据 [GitLab Notes API](https://docs.gitlab.com/api/notes/)（2026-09-20 核对）；实际部署版本兼容性仍须集成验证，不接受任意 URL。稳定标记为 `<!-- agentnexus-code-review:<operation_id> -->`，operation_id 在此须编码为安全的 URL 分量；查证同时匹配发布机器人身份、MR、正文摘要，不能仅信任别人复制的标记。

pending→in_flight 必须先提交尝试记录再外部调用。写入前核对 Nexus generation/execution_revision/SHA 与 HCZJ review_revision/activation/target/current/report_digest；任何未知不得写。明确成功并查证实际正文后持久化 note_id 与 published Receipt；网络中断/进程崩溃留下的 in_flight 恢复为 unknown，先查证而非再次 POST。分页查证无法证明未执行时保持 unknown，人工处理；不能仅因暂未读到评论而重发。

写后再次核验，若目标变化，操作转 obsolete，并仅更新自己那条评论标注过期；修正超时保留审计及待核验状态，不能宣称已消除旧评论。重放相同操作不能创建新评论。跨 GitLab/数据库不承诺原子性或 exactly-once。

## 6. 兼容、映射与持久化期限（T6）

运行 allowlist 仍为空。待 Nexus 提交脱敏真实响应、部署 revision/源码指纹，HCZJ 提交映射 fixtures 与服务鉴权证据，AgentNexus 汇总适配器版本与 CP 记录后，由 binding 评审冻结 compatibility.json。不得以候选值提前放行。

access_scope 与 compatibility.json 保持一致：`observed_candidates=["service_private"]`、`operative_allowlist=false`、运行 `artifact_access_scope=[]`。此候选值仅审计记录，尚未放行：持有服务凭据还必须通过产物所属项目、session/Run 和角色授权；无授权不泄露 locator 存在性。两个存储服务均须实现后方可加入运行词表。

HCZJ 原始 report/coverage 保留不变。适配器合并两者生成 Profile 报告：非空 findings→issues_found；无 findings 且 coverage complete→no_findings；无 findings 且 partial/none→inconclusive。有 inherited_gap 时 coverage 至多 partial。不得据原 outcome 推断 coverage complete。本 binding 加严/特定映射（非 Profile 对 HCZJ 的通用要求）：severity 映射固定为 P0→critical、P1→high、P2→medium、P3→low；未知值拒绝 invalid_output，不降为 low。该映射随本契约评审，四项及未知值均需 fixture 后启用。

展示与发布必须在同一摘要中同时呈现 outcome 和 coverage.status；coverage 非 complete 时同时显示缺口警示、遗漏范围及 inherited_gaps，不能仅给 issues_found 徽标或将其表述为“已充分评审”。无 findings 且覆盖不足必须显示“结论不充分”，不得显示“无问题”。保留原始 HCZJ report/coverage 与转换溯源。行为用例见 fixtures/binding/q3-outcome-coverage.md；valid/09 只锁定结构，不能代替适配或 UI/Publisher 行为验收。

inbox/outbox/幂等记录至少保留至 Run 终态后 30 天，并且不得早于其 artifact retention_until；未决 publication unknown 不自动清理。压缩历史时保留 key+比较投影摘要+结果定位的 tombstone，禁止 key 被清理后执行成新操作。读到已过期产物返回 artifact_expired，不能重新生成同 locator 的新字节。

## 7. 超时、比较与错误映射

连接超时 2 秒，普通请求总超时 10 秒，raw/source-bytes 30 秒；无长轮询。仅读操作或同 key 写重放允许最多 3 次网络尝试（含首次），退避 1/2 秒并受 Run deadline 限制；429 按 Retry-After 等待但不超出预算。10 秒后未知写结果必须查 status_url；查不到不代表原请求未提交，同 key 才可重放，不重新调用模型。Coordinator 未配置时不重试。

ReviewRequest 幂等投影严格沿用 Profile §15.8。其他 binding DTO 比较所有业务字段，排除凭据、头部 correlation ID；消息排除信封 message_id/created_at/correlation_id/causation_id，但保留 type/sender/receiver/session/run/attempt/epoch 及 payload。固定缺省后用递归排序键、数组原顺序、无空白 UTF-8 JSON 比较，禁止浮点；这是局部比较规则，不是产物摘要算法。Delivery 的 digest 冲突优先按 §4 处理。幂等键按认证 principal+动作+资源范围隔离，publication operation_id 另有全局唯一约束。

所有新增错误直接返回 error.schema.json（不是 `detail` 字符串）；携带 correlation_id，retry_after_seconds 遵守冻结 error.schema.json 的不变式：retryable=false 时必须为 null；retryable=true 时只能为 null 或正整数，429 必须为正整数。action_required 指需要人工修正/介入，不表示必须再发一次请求。

| HTTP | code | retryable / action_required | 条件 |
|---|---|---|---|
| 400/422 | invalid_output / input_mismatch | false/true | 结构、类型、关联错误；格式纠正仅按 Profile 允许范围 |
| 401/403 | authority_denied / data_policy_denied | false/true | 凭据、角色或资源权限拒绝（`data_policy_denied` 时 `scope=policy`） |
| 404/410 | evidence_unavailable / artifact_expired | false/true | 固定证据缺失或过期 |
| 409/412 | evidence_digest_mismatch | false/true | 字节或 If-Match 不符 |
| 409 | delivery_conflict / idempotency_conflict | false/true | 相同 key 不同内容 |
| 409 | stale_assignment / superseded_input / policy_changed | false/false | 旧任务终止，由权威调度处理新目标 |
| 413 | data_policy_denied | false/true | binding 读取/载荷超限（§10.1）；**必须**带 `scope=read_limit`，不得与披露策略拒绝混淆 |
| 422 | unsupported_profile / unsupported_contract / unsupported_capability / unsupported_critical_extension / enforcement_unavailable | false/true | 不兼容或不能强制执行 |
| 422 | data_policy_denied | false/true | 无法承诺所请求的保留期；**必须**带 `scope=retention` |
| 409 | budget_exhausted / deadline_exceeded | false/false | 当前执行停止 |
| 429 | rate_limited | true/false | retry_after_seconds 必填正整数 |
| 503 | temporarily_unavailable | true/false | 暂时服务故障，有界重试 |
| 503 | coordinator_unavailable | 未配置 false/true；暂不可达 true/false | 禁止本地替代 Run |
| 503 | freshness_unknown | true/false | 仅有界重查权威，不发布 |
| 409 | publication_unknown | false/true | 禁止自动重写 GitLab，转查证/人工；查询仍允许 |

**同一 code 多种成因时必须用 `scope` 区分**：`data_policy_denied` 至少区分 `read_limit`（读取/载荷超限）、`retention`（保留期无法承诺）、`policy`（披露或权限策略拒绝）三类。调用方与运维**不得仅凭 `code` 判断原因**——否则会把容量问题误读为策略决定（评审 R2-2）。本表覆盖本契约使用的**全部** HTTP 状态码；新增状态码必须同时补入本表。

未预期 5xx/非 JSON/响应截断都按传输结果 unknown 处理，不据状态码自动换 key 或重调模型。异步业务错误保存 MessageView/PublicationView；其 GET 仍返回 200（查询成功），内部 error 才表示业务失败。

## 8. 评审与验收清单

契约定义已补齐不等于 T1–T6 实施证据已齐。评审至少覆盖：角色隔离；同 key 超时重放；ACK 后崩溃恢复；原始字节/CRLF/无末尾 LF；激活并发与租约过期；取消竞态；有 findings+coverage gap；发布 unknown 与伪造标记；写后过期修正；artifact 过期与 tombstone。每项需正常、重复及拒绝 fixture，并与 CP-01～26 对照。统一宿主为本包 fixtures/binding/，按 <主题>-<场景> 命名；语义 schema 正反例仍放 valid/invalid 并登记 index.json。

**机器校验边界（避免误读，评审 R2-4）**：`tools/validate.py` 的强制校验范围**仅限** `fixtures/valid/` 与 `fixtures/invalid/`（通过 `fixtures/index.json` 绑定 schema）。`fixtures/binding/` 下的 Markdown 行为规范**不经** schema 校验、也不由 `validate.py` 执行，仅由 `manifest.json` 固定其文件摘要；因此"manifest 摘要一致"**不等于**行为已验收。已实现可执行 harness 的用例必须登记命令与实际结果（示例：q3 用例见 [q3-execution-record-2026-09-20.md](../fixtures/binding/q3-execution-record-2026-09-20.md)），未登记结果前不得标为已通过。三仓库引用同包版本/摘要，不各自维护副本。

**本契约定版后**才更新 binding 决议（此处不再写具体修订号，避免下次修订后标签再次过时，评审 R2-3）；Nexus 生产样例、适配器实现和 CP 证据仍独立追踪，不以文档完备代替运行符合性。三仓库只维护本契约的版本/摘要引用与各自实施清单。

**T1–T6 关闭的唯一追踪器**（2026-09-20 新增）：[`evidence/closure-checklist.json`](evidence/closure-checklist.json)。§2–§6 定义的端点、DTO、认证与错误要求在此被展开为 25 条逐项证据要求（责任人、采集模板、机械验收条件），T6 的 `mapping_fixtures` 覆盖 §6 的 severity/outcome 映射与未知值拒绝。之所以另立追踪器而不是继续靠本文件自述：本文件的"契约定义已补齐"曾是唯一可见的进度信号，而它从不包含生产样例。回填与校验方式见 [`evidence/README.md`](evidence/README.md)；`tools/check_evidence.py` 重算摘要、拒绝虚假关闭，并在 T1–T6 未全部关闭时拒绝 `compatibility.json` 放行。

## 9. 评审记录

| 日期 | 评审者 | 结果 | 备注 |
|---|---|---|---|
| 2026-09-20 | 评审 Agent | 有条件通过（**binding 仍不得定版**） | RC1 可作为定版候选；Q1–Q3 阻塞项待补、S1–S7 建议；Profile §14.10 门禁 1 维持关闭 |

### 9.1 结论与立场

RC1 把 T1–T6 从"待确认"推进为**有源码依据的候选契约**，且自我约束正确：明确声明"契约定义已补齐不等于 T1–T6 实施证据已齐"、"§14.10 门禁 1 仍未关闭，L0 binding 不予定版"。**评审同意该立场：本次不批准 binding 定版**，仅确认契约内容可作为后续定版基础。

### 9.2 独立复核（不依赖自述）

1. **错误码词表完全对齐**：§7 错误表引用的 **24 个码与冻结 `schemas/error.schema.json` 枚举逐一相符**（脚本核对：无未登记码、无遗漏码）。
2. **外部证据可信**：`bindings/source-evidence.json` 的 12 个文件摘要已在 `D:\PycharmProjects\Nexus_Agent`、`Hczj_Assistant_Agent` 上逐个重算，**12/12 相符、0 不匹配**。证据记录忠实；但仍不证明部署版本（记录本身也如此声明）。
3. **摘要口径一致**：确认记录 T2 指出"GET report 会解析并重序列化，不能用 HTTP 响应字节代替持久化字节"，与 Profile §15.3 及其 CP-23 向量一致；新增 `/raw` 是正确解法。
4. **outcome/coverage 不变式一致**：§6 的适配规则与冻结 `review_report.schema.json` 的 5 条 `allOf` 不变式完全一致。
5. **ACK 分层正确**：TransportAck 明确"不是 received/validated/accepted Receipt"，正面回应了 P7/ACK 分层的关切。
6. **发布正文来源被锁死**：§5 规定服务端按模板生成正文、不一致的 `summary_text` 返回 422，消除了"候选文本成为发布正文"的注入面。

### 9.3 阻塞项（定版前必须补）

- **Q1（§1 与 Profile §15.6 不一致）**：§1 只要求 AgentNexus 保存 `external_run_id`/`external_attempt_id`，遗漏 **`external_coordinator_id` 与 `assignment_epoch`**，也未提"唯一关联键须含 coordinator_id"。按 §15.6 补齐，否则实现可能只存两项。
- **Q2（binding 引入未定义语义）**：AttemptView.state 的 `offered/accepted/running/completed/rejected/expired/cancelled` 是 Profile 未定义的**新状态机**；Profile 只定义 Run 六态并把 validating 作为 running 内部 phase。需二选一并写入契约：(a) 显式声明 Attempt 状态为**内部实现细节**并给出到 Profile 可观察语义的映射（`expired`→`deadline_exceeded`、`cancelled`→`failed`+`cancelled_by_owner` 等）；或 (b) 走设计变更把 Attempt 语义写入 Profile。未定前不得把该词表当作已批准协议语义。
- **Q3（"有发现且覆盖不足"缺契约用例与呈现规则）**：确认记录已正确识别 HCZJ `findings_present` + coverage gap 与 Profile"非空 findings ⇒ issues_found"的差异，方向（以 Profile 为准、保留原产物）正确；但缺该情形的合同用例与呈现规则。评审已在规范包补 `fixtures/valid/09_review_report_issues_found_with_inherited_gap.artifact_body.json`（findings 非空 + inherited_gaps 非空 + coverage=partial + outcome=issues_found）锁住结构；契约侧仍需补 HCZJ 映射的行为用例，并规定**展示/发布时必须同时呈现 coverage，禁止只显示 outcome**，避免 `issues_found` 被读成"评审充分"。

### 9.4 建议项（不阻塞）

- **S1**：`compatibility.json` 已按本次评审补 `observed_candidates: ["service_private"]` + `operative_allowlist: false`；§6 宜引用同一表述，避免同一事实两处不同写法。
- **S2**：§2 对 Nexus ArtifactRef 的 `retention_until`"非空且覆盖 Run deadline"、§6 的 severity 映射（P0→critical…未知拒绝）都是**在 Profile 之上的加严**，建议显式标注"binding 加严，非 Profile 要求"，防止后续以 Profile 为由放宽。
- **S3**：§7 未写 `retry_after_seconds` 的取值不变式（仅 429 必填）；冻结 `error.schema.json` 有"`retryable=false` ⇒ `retry_after_seconds` 必须为 null"，建议直接引用，避免 400 也带退避时间。
- **S4**：§3 用 `idempotency_key` 作幂等 key，又用"相同 request_id 不同投影"描述拒绝条件；Profile §15.8 的投影**排除** `request_id`/`idempotency_key`。两处措辞需统一，避免实现把 key 与投影混为一谈。
- **S5**：`source-evidence.json` 缺两个外部仓库的 **commit/工作树状态**；建议与 `manifest.json` 一致地记录 `git rev-parse HEAD` 与 dirty 标记，否则日后无法判断证据对应哪个版本。
- **S6**：§8 要求"每项需正常、重复及拒绝 fixture"，但未指定宿主与命名；建议统一落在 `specs/profiles/code-review/v1/fixtures/`（可在其下分 `binding/`），否则三仓库会各写一套。
- **S7**：新增 `/raw`、`/source-bytes` 只读端点要求 30s 内完成，但未声明响应与区间大小上限及分页；建议补上限，避免实现各自设限。

### 9.5 未验证项（本轮无法闭环）

- 外部隔离测试数字（Nexus 17 passed、HCZJ 132 passed）与两仓库实现语义：只核对了文件摘要，**未复跑其测试**，也未审查其实现是否符合本契约。
- `service_private` 的认证/资源授权语义、T1–T6 的生产响应样例仍未取得。

### 9.6 门禁

RC1 契约**有条件通过**（定版候选）。Q1–Q3 补齐后由三方复核；在此之前 **§14.10 门禁 1 维持关闭**：不得启动"符合本 Profile"的集成运行，不得声明 wire conformance。契约内的错误码、ACK 分层与 outcome 不变式可直接用于实现与 fixture 编写，因为它们已与本 Profile 的冻结语义核对一致。

## 10. RC2 修订回应（设计方，待评审复核）

保留 §9 的原评审意见与结论；以下记录修订，不代替评审批准。门禁 1 尚未通过，不得启动符合性集成。

| 项 | 修订落点 |
|---|---|
| Q1 | §1 补齐四项持久化字段、含 Coordinator 的唯一关联键与 epoch 围栏 |
| Q2 | §3.1 明确内部观察标签及 Run/错误/回执映射，未新增 Profile 状态机 |
| Q3 | §6 同时呈现 outcome/coverage；fixtures/binding/q3-outcome-coverage.md 补转换、重复与错误呈现用例；保留评审新增 valid/09 |
| S1–S4 | §2/§3/§6/§7 统一候选词表、标注加严、重试不变式、key 与投影分离 |
| S5 | source-evidence.json 补本次仓库 commit/dirty 获取结果与文件摘要复核，缺少 Git 时显式 unknown |
| S6–S7 | §8 固定 fixture 宿主；§10.1 固定读取上限及分页/拒绝语义 |

### 10.1 L0 读取上限（binding 加严，新增要求未实现）

raw 报告及 A/artifacts 原字节最大 16 MiB，source-bytes 单次最大 1 MiB 且行数最多 2000；JSON 查询单次序列化响应最大 4 MiB。均指未压缩字节。超过限制在发送成功头部之前拒绝，返回 413 data_policy_denied、`scope=read_limit`、retryable=false、action_required=true、retry_after_seconds=null，不返回截断正文或伪造完整摘要。

raw 不支持分页或 Range（Range 请求返回 422 input_mismatch）；必须完整校验原始产物再返回，不能分块 JSON 后冒充相同 digest。source-bytes 不隐式分页，客户端可按不重叠闭区间分次请求，每次分别生成该区间证据摘要；单行超过 1 MiB 则拒绝，不拆分成伪行。分页列表保留其既定 limit/cursor，服务端可减少本页条数并返回继续游标，单条超限仍拒绝；不得跳过条目。绑定适配层也须对旧接口应用上述限制，不能把它们描述成既有 Nexus 保证。

## 11. RC2 评审复核（评审 Agent，2026-09-20）

| 日期 | 评审者 | 结果 | 备注 |
|---|---|---|---|
| 2026-09-20 | 评审 Agent | 修订核实通过（**binding 仍不得定版**） | RC1 的 Q1–Q3 与 S1–S7 **全部关闭**；契约文本层面已无阻塞项；门禁 1 由外部证据与实现决定 |

### 11.1 核实结论

RC2 的 10 项修订（Q1–Q3、S1–S7）逐条核实，**全部已落实且无信息丢失**；§9 的原评审记录与结论完整保留。RC2 契约文本层面**已无阻塞项**，可作为定版候选。但因 T1–T6 未关闭、§15.2–15.7 未实现、compatibility.json 未三方冻结、CP-01～26 未执行，**binding 仍不得定版**。

### 11.2 逐项核实

| 项 | 核实结果 | 证据 |
|---|---|---|
| Q1 | 已落实，且比评审建议更完整：补齐四项持久化字段 + Run/Attempt/分配三级关联键 + "不同 Coordinator 同名 ID 不得碰撞" + epoch 围栏 + `external_coordinator_id` 取自受信任注册而非 worker 自报 | §1 |
| Q2 | 采用方案 (a)：§3.1 声明标签仅为内部观察标签，给出七标签到 Profile 可观察事实的映射（含 `expired` 的三种分流：deadline / 仅租约失效 / 目标已更新），并禁止把它当作第二套权威状态机；§3 正文同样声明 | §3, §3.1 |
| Q3 | 已落实：§6 规定展示与发布必须在同一摘要中同时呈现 outcome 与 coverage.status，覆盖非 complete 时须显示缺口、遗漏范围与 inherited_gaps，禁止"已充分评审"表述；新增 `fixtures/binding/q3-outcome-coverage.md`（转换/重复/错误呈现/空发现四组用例，含 A/B 结构拒绝与 C/D 呈现拒绝），并声明 valid/09 只锁结构、不代替行为验收 | §6, `fixtures/binding/q3-outcome-coverage.md` |
| S1 | 已落实：§6 引用 compatibility.json 的同一表述（`observed_candidates` / `operative_allowlist=false`） | §6 |
| S2 | 已落实：§2、§6 显式标注"本 binding 加严，非 Profile 通用要求" | §2, §6 |
| S3 | 已落实：§7 直接引用冻结 `error.schema.json` 的 `retry_after_seconds` 不变式 | §7 |
| S4 | 已落实：§3 将 `request_id` 定位约束与业务比较投影分离，并定义"同 key 同投影但新 request_id 返回原 RequestAck" | §3 |
| S5 | 已落实，且经评审者复算：`repository_states` 的 `unavailable` 记录**准确**——实测 `D:\PycharmProjects\Nexus_Agent` 无 `.git`，`Hczj_Assistant_Agent\.git` 为空目录（0 项、无 HEAD），git 确实不可读；12 个文件摘要在 RC2 复算 **12/12 相符** | `source-evidence.json` |
| S6 | 已落实：§8 固定 `fixtures/binding/` 宿主与 `<主题>-<场景>` 命名，区分 schema 正反例（valid/invalid + index.json）与行为规范（Markdown，未实现 harness 前不得标为已通过） | §8 |
| S7 | 已落实：§10.1 给出读取上限（raw/artifact 16 MiB、source-bytes 1 MiB 且 ≤2000 行、JSON 响应 4 MiB）、超限在发送成功头部前拒绝、不得截断或伪造摘要、Range 拒绝、source-bytes 不隐式分页、单行 ≤1 MiB 不拆伪行、列表分页继续游标、并声明适配层同样适用 | §10.1 |

机器复核（评审者自跑）：RC2 §7 错误表仍为 **24 个码、零未登记、零遗漏**，与冻结 `schemas/error.schema.json` 完全一致。

### 11.3 RC2 新增建议（不阻塞）

- **R2-1**：§10.1 引入 HTTP **413**，但 §7 的错误映射表没有 413 行。本契约要求"所有新增错误直接返回 error.schema.json"，其自身映射表就应覆盖它使用的全部状态码；建议补 413 行。
- **R2-2**：`data_policy_denied` 现同时承载"读取/载荷超限（413）"与"保留期无法承诺（422）"。该码在 Profile §9/§10 的语义偏向披露与权限策略（"不重试模型；维护者处理"），用它表示容量限制会让维护者把容量问题误读为策略决定。建议要求 `scope` 显式区分（如 `read_limit` / `policy`），或在下一版 Profile 增加专用码。
- **R2-3**：残留修订标签与状态行需要统一：§8 末段仍写"本 **RC1** 通过后才更新 binding 决议"；`l0-agentnexus-http.md` §9 标题与正文仍写"**RC1** 采用专用新入口"；同文件 §7 前言称 T7"设计范围已确认"，但 T1–T7 表的 T7 行未标注已确认。
- **R2-4**：包内新增 `fixtures/binding/` 存放行为规范，`tools/validate.py` 不校验其内容（该文件也如实声明）。规范包已在 `fixtures/index.json` 与 README 标注这一分工，建议 §8 也点明，避免被误读为"已机器校验"。

### 11.4 未验证项（不变）

外部隔离测试数字（Nexus 17 / HCZJ 132 passed）与两仓库实现语义：**未复跑其测试**，未审查其实现是否符合本契约。T1–T6 的生产响应样例与 `service_private` 的授权语义仍未取得。

### 11.5 门禁

**BINDING-GATE-1（Profile §14.10 门禁 1）维持关闭。** 定版仍需：§15.2–15.7 落地或降级声明、T1–T6 关闭、compatibility.json 三方冻结、`tools/validate.py` 通过（已满足）、CP-01–26 运行记录。RC2 的端点、DTO、错误映射与 Q2 标签映射**可直接用于实现与 fixture 编写**。

## 12. RC2 残留建议收口（2026-09-20）

§11.3 的 R2-1～R2-4 已逐条修订，并由规范包自检**机械化**保证不再复发。

| 项 | 修订落点 | 机械化保证 |
|---|---|---|
| R2-1 | §7 错误表补 **413** 行（`data_policy_denied`，带 `scope=read_limit`），并声明"本表覆盖本契约使用的全部 HTTP 状态码；新增状态码必须同时补入本表" | `tools/validate.py` 新增 `check_contract_error_table()`：契约 §7 表的每个 code 必须在本包 `error.schema.json` 枚举内，且枚举中的每个码都必须在表中出现 |
| R2-2 | §7 表把 401/403 行标注 `scope=policy`、新增 422 行标注 `scope=retention`；表后新增"同一 code 多种成因必须用 `scope` 区分（`read_limit`/`retention`/`policy`），不得仅凭 code 判断原因"；§10.1 的 413 句补 `scope=read_limit` | 自检要求契约文本出现 `scope=read_limit`；实现侧 `agent_net/code_review/errors.py` 以同一分类学落表，并由 `test_cr_data_policy_denied_scopes_are_distinguishable` 锁定三种 (scope, HTTP) 组合 |
| R2-3 | §8 末段改为"**本契约定版后**才更新 binding 决议"（不再写具体修订号，避免下次修订后再次过时）；`l0-agentnexus-http.md` §9 标题与正文去掉 RC1 硬编码、改为现状描述；§7 的 T1–T7 表新增"状态"列，T7 明确标注**设计范围已确认、部署验证仍待做** | 不再用版本号自指，从根上消除该类过时 |
| R2-4 | §8 新增"机器校验边界"段：`validate.py` 的强制范围**仅限** `fixtures/valid/` 与 `fixtures/invalid/`；`fixtures/binding/` 的 Markdown 不经 schema 校验、也不由 validate.py 执行，仅由 manifest 固定摘要；须登记 harness 命令与实际结果（示例链接 q3 执行记录）；未登记结果前不得标为已通过 | 自检的孤儿检查只覆盖 `valid/`+`invalid/`，与该声明一致 |

**评审复核（2026-09-20）**：上述四条均已核实。新门禁经**负例验证**不为空转——注入未登记码（`payload_too_large`）、删除 `scope=read_limit` 标注、删去一条已登记码的表行，三种情形都正确报错。规范包升级 `1.0-draft.2+semantic.8`，自检通过（24 个契约码与枚举一致、正例 9/9、反例 14/14、manifest 51/51）。

**R2 收口不改变 §11 的结论**：**binding 仍不得定版**，BINDING-GATE-1 维持关闭——剩余条件是外部证据与实现验收（T1–T6、兼容清单三方冻结、CP-01～26 运行记录），不是契约文本问题。
