# Changelog

### 2026-09-21 L0 外部端点实现与本地证据

- 两外部项目新增 RC2 服务接口及验证；Nexus 29 项通过，HCZJ 全量 4229 通过/2 跳过，最终服务定向 14 项通过。
- [T1–T6 本地证据包](docs/evidence/l0-2026-09-21/README.md) 含脱敏合成 HTTP 样例、JUnit 与源码指纹；不是生产证据，不关闭门禁、不改兼容允许列表。

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### 路线图第 2–4 步：CP 执行记录、T 项 intake 与冻结预检（2026-09-23）

**第 4 步（CP-01～26 执行并留档）** —— 半机械、半行为，可重跑：

- 新增 `scripts/run_cp_matrix.py`：把 `fixtures/cp-matrix.json` 的 26 个用例逐个落到可执行证据上——`structural` 用冻结 schema 复核 fixture（valid 必过、invalid 必不过），`digest` 直接复算 `digest_vectors.json`，`behavioral` 运行覆盖映射里的 AgentNexus 行为测试并按 node id 记结果；支持 `--run` 与受限环境的 `--input` 两种取数方式。运行记录**不内嵌 manifest 摘要**（记录本身由 manifest 登记，内嵌会成环）。
- 新增 `bindings/l0-agentnexus-cp-coverage.json`（binding 级，非 Profile 通用要求）：逐条 CP 的状态与证据映射——**15 个 AgentNexus 侧通过、6 个部分（其余裁定权在 HCZJ/Nexus）、5 个本仓无证据、0 个证据失败**；blocked 必须写明 owner 与限制，partial 必须写明限制。有 5 个 CP（CP-06/12/13/15/21）明确不声称通过，其中 CP-15 是预算/网络强制点缺失（§15.5、评审 C-1）。
- 新增运行记录 `fixtures/binding/cp-execution-record-2026-09-23.md`（87 个行为用例通过，0 失败）。
- 新增 `tests/test_code_review_cp_matrix.py`（14 项守卫）：CP 集合与 cp-matrix 完全一致、映射的 node id 必须真实存在（改测试名会让记录立刻变红）、blocked/partial 不得被渲染成通过、渲染器对参数化用例要按前缀归并取最坏结果、记录必须覆盖全部 26 项且限制小节与声明一致。
- 修正 `compatibility.json` 的 adapter 段：由 `not_implemented`（且列出 §15.2–15.7 等"未实现"项）改为 `implemented_pending_wire_validation`，把已实现项与非声明清单分开写清；**允许列表仍全部为空**。

**第 2–3 步（T 项 intake 与冻结预检）** —— 见 [T 项 intake 与冻结预检](docs/reviews/2026-09-23-l0-t-intake-and-freeze-preflight.md)：

- 逐一列出 6 个 T 项、25 条 `blocking` 证据要求的 owner、模板、`record_key`、必需字段与机械检查，以及本地 `non_closing` 对照证据与**缺口**；明确哪些是 AgentNexus 侧已做掉、不需要外部提供的。
- 冻结预检：列出四方输入清单、冻结程序与防"提前放行"的机械底线；新增回归用例把底线固化——T1–T6 关闭前任何允许列表的非空填写都会让 `test_compatibility_allowlists_stay_empty_while_gate_closed` 变红。
- 诚实边界：T1–T6 **仍 6/6 开放**；生产/部署证据与三方签字不在本工作区，`docs/evidence/l0-2026-09-21` 仍是 semantic.9 时期产物（采集 pin 未改写，仅追加 `profile_manifest_rechecks`）。

规范包 `1.0-draft.2+semantic.14` → `+semantic.16`（63/63 manifest；契约 24 码；正例 9/9；反例 14/14）。

### 全量门禁加固：报告编码与跳过明细（2026-09-23）

`scripts/check_full_suite.py` 有两处会让门禁**误判或崩溃**的缺陷，均为本轮自查实测触发：

- **报告编码**：中文 Windows 上 pytest 重定向输出用的是 locale 编码（GBK），门禁原先只按 UTF-8 读，跳过的**原因**全变成 U+FFFD，环境跳过逐字匹配 0/48 命中，被误报成"出现无理由跳过"。新增 `decode_report()`：按 `utf-8` → `utf-16` → `cp936` 逐个**严格**解码，`--run` 分支同样走它。
- **类型错用**：`check()` 把 `classify_skips()` 返回的**列表**当字典用（`other_skips.items()`），一旦真有无法解释的跳过就抛 `AttributeError`——门禁最需要给出逐条明细时恰好崩掉。已改为按明细逐条打印，并把变量名与返回类型对齐（`unexplained`）。
- **信息已丢失时不猜原因**：报告若已含 U+FFFD（中文不可还原），新增退出码 `3` 明确拒绝判定，并提示以 `$env:PYTHONIOENCODING='utf-8'` 重跑；同时 `sys.stdout.reconfigure(errors="replace")`，避免中文控制台打印受损文本时二次崩溃。
- 硬规则命令同步补上编码前置条件（`CLAUDE.md`、`tests/CLAUDE.md`），退出码说明补 `3`。

### L0 三项残余问题跟进（2026-09-23）

- HCZJ H/messages 缺/错幂等头映射按 RC2 §4 修复，Delivery `reviewer_id` 与分配 worker 绑定；HCZJ 单元 4243 passed / 2 skipped。代码修复待独立评审。
- S5 台账拆成公开规则和被 Git 忽略的本地历史记录；C-1 仍 `declared_only`，测试夹具改用合成组件名避免把 `local_cli` 误报为网络强制器。见[修复确认](docs/reviews/2026-09-23-three-residual-fix-confirmation.md)。
- AgentNexus 全量 810 passed / 9 skipped，基线门禁 exit 0，规范包自检通过。

### L0 第六轮复审（2026-09-23）

- 独立全量 810 passed / 9 skipped，回归门禁 exit 0；HTTP 契约专项 69 passed，规范包及宿主审计通过。
- [独立评审](docs/reviews/2026-09-23-l0-r6-review.md)：R5-1 代码缺陷关闭；空绑定写入、旧库空绑定上传、事务空预期比较均已独立验证，常规竞争路径保持正确。整体实施门禁仍关闭。

### L0 第五轮复审 R5-1 修复（2026-09-23）

针对[第五轮复审](docs/reviews/2026-09-23-l0-r5-review.md)的 R5-1 做修复，确认见[修复记录](docs/reviews/2026-09-22-l0-r3-fix-confirmation.md) §3.2。

- **R5-1 空 Coordinator 绕过事务身份围栏（P2）**：`external_coordinator_id` 可为空字符串，而事务复检写作 `if expected_coordinator_id and ...`——**预期值为空时整段比较被跳过**，于是"从空 ID 改绑到另一 Coordinator"不被发现，旧上传仍 201 并登记产物。根因是把空值当成"无需比较"的信号；**空字符串是可比较的值**。
- **修法（三条建议逐条落实）**：① 绑定入口 `bind_execution_assignment()` 要求 `profile_session_id`/`external_coordinator_id`/`external_run_id`/`external_attempt_id` 非空白且 `assignment_epoch ≥ 1`，否则 422 `input_mismatch`——从源头拒绝不完整绑定；② 上传入口对**既有空绑定** fail-closed → 409 `stale_assignment`；③ 事务内三处身份比较（Attempt/Coordinator/worker）**去掉全部真值守卫**，改为 `(actual or "") != (expected or "")`（空与空相等、空与非空判失败）。函数 docstring 写明该原则，防止回退。
- **负例证据**：把 Coordinator 比较改回旧守卫后，`test_r32_in_transaction_comparison_has_no_truthiness_guard` 报 `DID NOT RAISE`（空值确实被跳过），对照组仍通过；恢复后两条均通过。临时回退已还原并经脚本核对无残留。
- **契约文本无需改动**：`bindings/l0-service-contract.md` §1 已要求"ID 为非空字符串"，§4「上传的分配围栏」已要求在事务内校验 Coordinator——本次是**实现未落实既有契约**（真值守卫），故规范包维持 `1.0-draft.2+semantic.14`，不改动、不重生成清单。
- 测试：`test_code_review_http_contract.py` 68 → 69（新增绑定入口拒绝空身份、既有空绑定入口 409、事务内无真值守卫 + 对照组）；Code Review Profile 系列 257 tests + 1 skip。
- 全量门禁：**762 passed, 57 skipped, 0 failed, 0 errors** → `[PASS]` exit 0。
- **未修**：H/messages 的错误映射对齐属外部仓库（HCZJ 侧）；原 S1 仍开放。T1–T6 全开放、BINDING-GATE-1 维持关闭、未声明 wire conformance。

### L0 第五轮复审（2026-09-23）

- 独立全量 806 passed / 9 skipped、回归门禁 exit 0；HTTP 契约专项 65 passed，规范包自检及宿主审计通过。
- [独立评审](docs/reviews/2026-09-23-l0-r5-review.md)：R4-2 关闭，R4-1 的普通改绑已修复；发现空 Coordinator 绑定可绕过事务身份比较，上传仍登记产物。需修改后复审；T1–T6 与 BINDING-GATE-1 不变。

### L0 第四轮复审（2026-09-23）

- 独立全量 803 passed / 9 skipped，回归门禁 exit 0；规范包自检及宿主审计通过，HCZJ 定向/跨仓库组合 25 passed。
- [独立评审](docs/reviews/2026-09-23-l0-r4-review.md)：R3-1/R3-3/R3-4 原问题关闭，R3-2 仍需修复；真实 ASGI/SQLite 探针确认改绑 Attempt/Coordinator 后旧上传仍成功，以及等待写锁期间租约到期仍成功。
- 新增评审复现脚本与证据，未修改运行时代码、测试基线或兼容清单。整体需修改后复审，BINDING-GATE-1 维持关闭。

### L0 第三轮复审 R3-1～R3-4 修复（2026-09-22）

针对[第三轮复审](docs/reviews/2026-09-22-l0-r3-review.md)的 4 项问题做修复，确认见[修复记录](docs/reviews/2026-09-22-l0-r3-fix-confirmation.md)。

- **R3-1 未知 session 绕过资源授权（P1）**：新增 `resolve_profile_session()` 返回 `ok`/`not_found`/`ambiguous`（不再 `fetchone()` 取第一条）；消息入口对未登记 session → **409 `stale_assignment`**、歧义 → 409、缺 `session_id` → 422，**"查不到"不再是放行条件**；资源许可改用 `require_session` 与角色许可分离；新增**受信任关联核对**（信封 `run_id` 必须等于会话绑定的 Run；assignment 的 `coordinator_id` 必须由已认证主体代表）。契约 §4 明确新 Run 绑定由部署初始化流程建立，本组端点不承担创建职责。
- **R3-2 租约不参与校验、分配未在事务内复检（P1）**：`resolve_assignment_binding` 读取 `lease_expires_at`，入口增加租约过期拒绝；新增 `_verify_assignment_in_transaction()`，在 `commit_artifact_with_idempotency` 的 `BEGIN IMMEDIATE` 内**重新读取并校验** session/run、worker、epoch、执行状态、租约、deadline——任一项失效即回滚，不登记产物、不置 committed。契约 §4 明确"提前查询不构成原子围栏"。
  - **补修一（第三轮复审）**：身份元组（Attempt / Coordinator）此前"读了不用"，且过期判断取的是 `BEGIN` **之前**的时间戳。已改为整体比对 + 在持锁后读时钟。
  - **补修二（第四轮复审）**：比较仍带真值守卫 `if expected_x and ...`，**预期值为空时整段被跳过**——"从空 Coordinator 改绑到另一 Coordinator"逃过围栏。已去掉全部守卫（空与空相等、空与非空判失败），入口侧同步去守卫并新增"分配未绑定 Coordinator 即拒绝"。
- **R3-3 同 key 并发上传 500（P2）**：提交事务内先看幂等状态，已 committed 直接返回**原产物**（replay），不再无条件 `INSERT`；只有未 committed 才写入。
- **R3-4 幂等比较用原始字节/完整信封（P2）**：新增 `agent_net/code_review/projection.py` 实现 §7 规则——消息剔除 `message_id`/`created_at`/`correlation_id`/`causation_id` 并固定缺省，产物取业务字段且 `artifact_body` **原样取字符串**；递归排序键、数组原顺序、无空白 UTF-8、**禁止浮点**；命名空间 `(principal, action, resource_scope)` 与幂等 key 分离。
- **保留建议**：`retention_until_text` 改为**写库**（不再只靠内存回显）；`assignment_epoch` 新增 `_strict_positive_int()` 拒绝 bool/小数/字符串；同名 Run 歧义改为显式 `ambiguous` 并拒绝。
- **测试有效性有负例证据**：每一处补修都先用"临时回退修复"确认对应用例会变红（改绑/写锁等待/空值守卫分别复现 201 或 `DID NOT RAISE`），再恢复修复。
- 规范包 `semantic.13` → `semantic.14`。测试：`test_code_review_http_contract.py` 47 → 68。
- 全量门禁：**761 passed, 57 skipped, 0 failed, 0 errors** → `[PASS]` exit 0。
- **未修**：H/messages 的错误映射对齐属外部仓库（HCZJ 侧）；原 S1 仍开放。T1–T6 全开放、BINDING-GATE-1 维持关闭。

### L0 第三轮代码复审（2026-09-22）

- [第三轮报告](docs/reviews/2026-09-22-l0-r3-review.md)确认消息幂等头规则、HTTP 矩阵及 R2-3～R2-6 修复；仍有 R3-1～R3-4（2 P1、2 P2）：消息资源授权、失效分配提交围栏、并发上传幂等、业务投影比较。附确定性并发/取消及重放复现，不批准整体完成。
- semantic.13 规范包及强制宿主审计通过；HCZJ 25 项定向及跨仓库组合通过。生产门禁不变，本轮未修改运行时代码或测试基线。
- 本轮独立 AgentNexus 全量 **788 passed / 9 skipped**（440.14 秒），回归检查器 exit 0；4 项发现均由补充边界复现确认，常规回归通过不能替代修复。

### 消息幂等键裁决落地（2026-09-22）

按评审裁决「**POST A/messages 必须携带 `Idempotency-Key`，且值必须等于信封 `message_id`**」修订契约与实现——§1 规定**传输位置**（HTTP 头），§4 规定**取值**，二者表示同一个逻辑幂等键，**不分别建立幂等记录**；§1 保留，§4 表同步澄清（此前表述有歧义）。

- **契约 §4 修订**（`bindings/l0-service-contract.md`）：幂等键列改为「**必须**经 `Idempotency-Key` 头传递」并写明取值（`= envelope.message_id`；`POST H/messages` 的 **delivery 例外** `= delivery_id`，不得机械要求等于 `message_id`）；新增四条执行规则的统一表格，并声明冲突判定必须在**任何写入之前**完成。
- **实现**（`agent_net/node/routers/code_review.py`）：缺少/空头 → **422 `input_mismatch`**（在解析正文前拒绝，属传输层要求）；头 ≠ `message_id` → **409 `idempotency_conflict`**；两种情况都不写入。同键同投影 → 返回原结果；同键不同投影 → 409 且**无副作用**。
- **信封严格性统一**：`parse_envelope` 改为复用 `parse_strict_json`，信封与产物上传遵守**完全相同**的 §3 规则（严格 UTF-8、拒 BOM、拒重复键、拒 NaN/Infinity），不再一个严格一个宽松。
- **测试**：矩阵新增行 `messages.idempotency_missing`；新增四条执行规则的专项用例（含"不写入"与"无副作用"断言）以及上传键独立性用例。`test_code_review_api.py` 的客户端按信封自动注入该头（业务语义文件），该头本身的契约行为由矩阵覆盖。
- 规范包 `1.0-draft.2+semantic.12` → `semantic.13`。全量门禁：**740 passed, 57 skipped, 0 failed, 0 errors** → `[PASS]` exit 0。
- **结论不变**：T1–T6 全部开放、BINDING-GATE-1 维持关闭、未声明 wire conformance。

### HTTP 契约矩阵（2026-09-22）

按复审建议「补实际 HTTP 契约矩阵后收口，避免再次出现『字段存在但 wire 不一致』」新增 `tests/test_code_review_http_contract.py`（41 项）。矩阵**行是数据**：每个端点 × 每个声明的失败/成功条件各一行，执行器发**真实 HTTP 请求**，并对**实际响应**做三重校验——状态码、`code`/`scope`、**真正通过冻结 schema**（错误响应跑 `error.schema.json` 的类型/const/additionalProperties/allOf）。

**首次运行即红 27 项**，一次抓出前三轮评审陆续发现的那类问题（详见 [矩阵说明](docs/reviews/2026-09-22-http-contract-matrix.md)）：

- **错误响应不是合法的 `code_review.error.v1`**：`correlation_id` 为空（schema 要求 `minLength: 1`），约 20 处失败路径都如此 → 异常处理器就地生成并回显；同时给 `error_envelope()` 加**守卫**，schema 未声明的顶层字段直接抛错而不是静默拼进去。
- **413 响应体不合法**：`limit`/`limit_value`/`observed` 在顶层 → 移入 `extensions.read_limit`；`violations`、`unsatisfied`/`declared` 同类问题一并移入 `extensions`。
- **JSON 响应缺 `charset=utf-8`** → 前缀级中间件补齐（raw 端点除外，必须原样返回 media_type）。
- **缺 `X-Correlation-Id` 未被强制** → 四个新端点统一拒绝（422）。
- **raw 的 `If-Match` 不匹配返回 409** → 改为 **412**（RC2 §2）；409 保留给"存储字节与登记摘要不一致"。
- **`Range` 未显式拒绝**（静默返回全量）→ 显式 422。
- **上传用裸 `json.loads`**（重复键/NaN/BOM 全放行）→ 新增 `parse_strict_json`，与信封共用同一套 §3 严格规则。

另发现一处**契约措辞冲突待裁决**：§1 说"变更接口带 `Idempotency-Key`"，§4 表却说 A/messages 的幂等键是 `message_id`。当前采取不冲突处理（仍以 `message_id` 为准；若给出该头则必须与之一致，否则 409），已在矩阵说明中登记待评审裁决。

全量门禁：**734 passed, 57 skipped, 0 failed, 0 errors** → `[PASS]` exit 0。**结论不变**：T1–T6 全部开放、BINDING-GATE-1 维持关闭、未声明 wire conformance。

### L0 复审 R2-1～R2-6 修复（2026-09-22）

针对[整体复审](docs/reviews/2026-09-22-l0-rereview.md)的 6 项阻塞问题做修复，确认见[修复记录](docs/reviews/2026-09-22-l0-rereview-fix-confirmation.md)。复审已**关闭 B8 与 B10 的代码缺陷**。

- **R2-1 幂等失败可恢复**：`code_review_artifact_idempotency` 新增 `state`（pending/committed）；预留只在"同 key **不同请求内容**"时判 `delivery_conflict`，pending 表示上次未提交成功 → 允许**续用同一 artifact_id** 重试；新增 `commit_artifact_with_idempotency` 把产物登记与置 committed 放进**同一事务**，任一步失败整体回滚。原"Vault 失败一次 → 同 key 永久 409"已封堵。
- **R2-2 上传绑定真实分配**：未知 Run → 422；强制 `require_session`；新增 `resolve_assignment_binding` 解析**唯一** `(session, run, attempt)` 绑定，未分配/歧义/epoch 不符/已取消/超 deadline → 409 `stale_assignment`，非该 Attempt 的 worker → 403；消息读取的当事人分支同样执行 session 范围检查。原"unregistered-run / unassigned-attempt / epoch=999 都 201"已封堵。
- **R2-3 回执与 inbox 同事务**：新增 `store_receipt_message`，在**单事务**内先校验消息与回执的幂等投影（同 `receipt_id` 必须同投影），全部通过后才写回执、inbox 与 `processed`；冲突在写入前抛出，**无副作用**。原"409 之后 receipt 仍落库"已封堵。
- **R2-4 回执角色回归**：`require_receipt_authority` 改为**返回**该 kind 唯一对应的角色，路由统一用它做角色与强制级别判定，删除 `or "coordinator"` 兜底。原"合法 validator/publisher 被要求 coordinator（403）"已修复。
- **R2-5 显式 null 不再当空集合**：`_strict_list` 区分字段缺失与显式 null；`findings`/`omitted_files`/`inherited_gaps` 为必填集合，缺失或 null 一律 `invalid_output`。原"outcome=findings_present + findings=null → no_findings"已封堵。
- **R2-6 拒绝证据按冻结 schema 与场景验证**：`check_evidence.py` 现在构建**可执行 validator** 并真正运行 `error.schema.json`（类型/const/additionalProperties/allOf），新增 `REFUSAL_EXPECTATIONS` 把每个用例绑定到主体角色、方法+端点与允许错误码；未登记期望的用例直接失败。原"无关 403 + 键齐全但 schema 不合法"已封堵。
- **部署依赖**：`pyproject.toml` 的 `dependencies` 与 `dev` 补登 `jsonschema>=4.18.0`、`referencing>=0.30.0`（`frozen.py` 运行时导入的强制校验路径）。
- **协议边界（部分）**：新增 `artifacts.retention_until_text`，`retention_until` **原样回显请求字符串**，不再经 float 反格式化丢微秒。其余边界（消息接口未强制 `Idempotency-Key`、`X-Correlation-Id` 可缺省、上传 `json.loads` 不拒重复键、raw `If-Match` 不匹配返回 409 而 RC2 要求 412、Range 未显式拒绝）记录为下一批。
- 规范包 `1.0-draft.2+semantic.11` → `semantic.12`。测试：`test_code_review_api.py` 30 → 41、provider 12 → 15、收口裁判 48 → 53。
- 全量门禁：**693 passed, 57 skipped, 0 failed, 0 errors** → `[PASS]` exit 0。
- **结论不变**：T1–T6 全部开放、**BINDING-GATE-1 维持关闭**、`compatibility.json` 保持默认拒绝、未声明 wire conformance。原 S1（HCZJ reviewer 归属）仍开放，属外部仓库。

### L0 第二轮整体复审（2026-09-22）

- [复审](docs/reviews/2026-09-22-l0-rereview.md)确认 B8/B10 对应代码缺陷关闭，剩余 R2-1～R2-6 六项阻塞：上传幂等故障恢复、Run/分配资源授权、回执事务副作用、严格角色表下的合法回执误拒、null finding 转换、拒绝样例 schema/场景校验。附隔离复现与源码指纹，整体需修改后复审。
- 独立全量 **722 passed / 9 skipped**，基线检查 exit 0；规范包及强制宿主审计 exit 0，独立复制包自检通过；Nexus/HCZJ 定向 **12/25 passed**。T1–T6 与生产门禁不变。本次仅写评审材料，未修改生产代码或基线。

### B8 修复：HCZJ 到 Nexus 的独立凭据接线（2026-09-21）

- 按用户要求修复 HCZJ 客户端：L0 raw/source-bytes 与旧 MR/Job 元数据使用显式不同凭据，旧读桥接器执行项目范围和 job 归属校验，缺配置拒绝且不回退凭据；报告证据改走 L0 raw。
- 定向 25 passed（含两侧真实路由/鉴权组合），HCZJ 全量 4240 passed / 2 skipped。B8 已修复并本地验证、待复审；其余问题和门禁不变。详见[跟进记录](docs/reviews/2026-09-21-l0-overall-code-review.md)与[B8 新证据](docs/reviews/2026-09-21-b8-fix-evidence.json)，未改写旧采集快照。

### L0 代码评审 B1–B9 修复与基线收窄（2026-09-21）

针对 [整体代码评审](docs/reviews/2026-09-21-l0-overall-code-review.md) 的阻塞项做修复，修复确认见[修复记录](docs/reviews/2026-09-21-l0-review-fix-confirmation.md)。**B8 超出本工作区写权限（外部仓库），未修复**。

- **B1 身份与角色**：新增 `agent_net/code_review/service_auth.py` 与服务凭据登记表（只存 sha256 摘要）。服务接口不再用 Daemon token + 信封 `sender_id` 判断身份：未登记任何凭据一律 **401 拒绝**（不再"未配置则放行"），`sender_id`/`issuer_id` 必须落在凭据可代表的 DID 内，回执 kind 按角色路由并要求 issuer 绑定。原冒充路径（同一 token 改 sender → 403 变 202 且标记 enforced）已封堵。
- **B2 资源授权**：消息与产物读取必须命中凭据的 session 范围；产物读取另有保留期检查（过期 → 410 `artifact_expired`）。不再"知道 ID 就能读"。
- **B3 wire 契约**：新增 `agent_net/code_review/frozen.py`，以冻结 `envelope.schema.json`/`artifact_ref.schema.json` 做接收前与返回前校验。上传只接受契约七字段；`retention_until` 按 RFC3339 严格解析、持久化并**原样返回**（不再静默 null）；ArtifactRef 不再多出 schema 禁止的 `enforcement`；TransportAck 恰好三字段、MessageView 恰好四字段且 `receipts` 为 Profile 回执**信封**。
- **B4 幂等与不可变**：Vault key 改为按内容摘要寻址（失败请求不再覆盖已登记字节）；按 `(principal, Idempotency-Key)` 做幂等映射，同 key 同请求返回原 artifact_id，内容不同 409 `delivery_conflict`，缺幂等键 422。
- **B5 入站校验**：接收前用冻结 schema 校验信封**及其按 type 的 payload**；`enforcement_requirements` 缺失/为空一律拒绝（不再当空数组）；信封与 payload 的 `run_id`/`attempt_id`/`assignment_epoch` 必须一致。空 Assignment 曾被 202 ACK 的路径已封堵。
- **B6 崩溃恢复**：消息 + 回执 + `processed` 状态**同一事务**提交，并提供 `reprocess_pending_messages()` 与 GET 路径的可重放补偿；不再出现"重试永远跳过处理"。
- **B7 provider 严格校验**：`provider_adapter` 删除全部 `isinstance(Mapping)` 静默过滤，改为逐项严格校验（非法 finding / 缺口条目 → `invalid_output`），`source_report_schemas`/`source_coverage_schemas` 由"仅声明"变为**强制核对**。原"malformed finding 被丢掉后报 no_findings"已封堵。
- **B9 收口裁判**：三个自述检查（worker 发布被拒 / 伪造回执被拒 / 未配置被拒）改为**样例级校验**——必须给出样例、主体、端点、401/403 状态、可解码的冻结错误信封与允许的错误码；布尔与文字不再作数。
- **B10 包可移植性**：宿主证据审计与包内自检分离（`host_markers` 自动跳过，`--require-host-audit` 收紧）；**真实包复制到任意目录后 `validate.py` 通过**已作为测试固定。
- **S3 采集 pin**：恢复采集时 pin，删除此前"直接刷新 pin"的做法，改为 `capture_package_version` + `profile_manifest_rechecks` 复核记录（并显式声明**未**重跑旧样例）。
- **S4 基线收窄**：不再把环境失败登记进基线。`tests/conftest.py` 增加能力探针，能力缺失时**显式跳过**并写明原因；`environmental_failures` 收窄为**空**；`scripts/check_full_suite.py` 改为"未登记失败/未登记跳过一律失败，通过数下限 = 基线 − 可解释的环境跳过数"。
- 规范包 `1.0-draft.2+semantic.10` → `semantic.11`。测试：`test_code_review_api.py` 按新契约重写（30 项，含评审要求的全部负例）、provider 回归 +5、收口裁判 28 → 48。
- **结论不变**：T1–T6 全部开放、**BINDING-GATE-1 维持关闭**、`compatibility.json` 保持默认拒绝、未声明 wire conformance。

### L0 三方整体代码评审（2026-09-21）

- 对当前 Profile 适配器、收口裁判及此前 Nexus/HCZJ 端点一并完成[代码评审](docs/reviews/2026-09-21-l0-overall-code-review.md)，结论为**需修改后复审，不批准实现完成**。B1–B10 涉及身份/资源授权、wire 契约、不可变上传及幂等、消息校验及恢复、finding 丢失、跨项目鉴权接线、证据裁判和包可移植性；附隔离复现脚本及输出。
- 本次独立全量 **679 passed / 9 skipped，无失败**；基线检查器 exit 2，原 25 项环境失败豁免已过时，未修改基线。规范包与证据自检 exit 0，Nexus/HCZJ 定向测试分别 12/14 passed。测试通过未覆盖的缺陷已复现，T1–T6 全部开放、BINDING-GATE-1 维持关闭。
- 本次只写评审与状态记录，没有修复生产代码或改写旧采集证据；此前本助手编写的 HCZJ 客户端接线问题也纳入阻塞项 B8。

### T1–T6 收口清单与证据采集包（2026-09-20）

**把「T1–T6 关了没有」从自述变成可重算的事实。** 此前唯一的进度信号是 binding 文档自己写的「契约定义已补齐」，而它从不包含生产样例——于是「已在源码确认」很容易被读成「已经关闭」。

- **新增唯一收口追踪器** `specs/profiles/code-review/v1/bindings/evidence/closure-checklist.json`：把 T1–T6 展开为 **25 条逐项证据要求**，每条写明责任人（Nexus_Agent 9 条 / Hczj_Assistant_Agent 13 条 / 三方 3 条）、采集模板、必需字段、机械验收检查与最小样例数。`items[].status` 是**声明**，实际状态由收到的记录计算，两者不一致即失败。
- **新增采集模板** `bindings/evidence/templates/T1–T6.json` 与落点 `bindings/evidence/received/`，配 `bindings/evidence/README.md` 说明采集约定：原始字节以 base64 承载、脱敏不得改字节口径、部署版本不得用工作树冒充、每项除正例还须给拒绝例、不得提交凭据。
- **新增校验器** `specs/profiles/code-review/v1/tools/check_evidence.py`（接入 `tools/validate.py`）：重算所有 `*_bytes_b64` 的 sha256 与 byte_length；声明 `closed` 但残留 `__TODO__`、缺必需字段、缺用例覆盖、缺部署版本或摘要不符 → 直接失败；T1–T6 未全部关闭时 `compatibility.json` 的 `operative_allowlist` 必须为 `false` 且 `artifact_access_scope` 必须为空，否则失败（拒绝提前放行）；`gate.status` 与按证据计算的门禁状态不一致也失败。
- **接入既有本地证据包** `docs/evidence/l0-2026-09-21/`：清单逐项登记该包为 `non_closing` 本地证据（已交付什么、尚不能关闭什么），校验器机械保证 ① 快照登记的 6 个 artifact 摘要与磁盘一致、② 合成样例持续声明 `production=false`（**禁止复核时改标签把本地样例变成生产证据**）、③ 清单引用的 artifact 确实存在。中央包 manifest 摘要漂移时**告警**并要求在快照中显式刷新，而不是静默改写他人证据。
- **修掉一处真实的跨引用失效**：本地证据包快照记录的 `profile_manifest_sha256` 因规范包升级而失效。已在该快照中**显式**新增 `profile_manifest_refreshed`（保留旧值、写明包版本前后与原因）并刷新字段，同时在 `docs/evidence/l0-2026-09-21/README.md` 留痕——不静默改写证据。
- **负例验证**（证明校验器不为空转）：`tests/test_code_review_evidence_checklist.py`（28 tests）覆盖摘要填错、长度填错、残留 `__TODO__`、缺必需字段、缺用例覆盖、声明 closed 无证据、声明 open 却有证据、语义检查失败、`operative_allowlist` 提前放行、门禁提前开启、模板缺 record key、未登记检查名、items 不完整、本地证据包缺失/生产标签被改/artifact 漂移/引用不存在/未标 `non_closing`，均在正确原因上失败；证据完整时关闭被接受。
- 文档同步：`l0-agentnexus-http.md` §7 声明「关闭状态的唯一追踪器」；`l0-service-contract.md` §8 说明为何另立追踪器；`external-confirmations-2026-09-20.md` 补「交付方式」；包 `README.md` 更新目录与自检范围。
- 规范包升级 `1.0-draft.2+semantic.10`（61 文件，自检 `[PASS]`：契约 24 码、正例 9/9、反例 14/14、CP 矩阵 26、收口清单自洽）。
- **结论不变**：T1–T6 **全部开放**，**BINDING-GATE-1 维持关闭**，`compatibility.json` 保持默认拒绝，不声明 wire conformance。本批交付的是关闭的**入口与裁判**，不是关闭本身——真正的关闭仍需 Nexus/HCZJ 的生产样例与部署版本证据。

### 评审方适配器泛化：HCZJ 降为一个 provider（2026-09-20）

- **新增厂商无关管线** `agent_net/code_review/provider_adapter.py`：`ReviewProviderAdapter` 基类 + provider 注册表（`register_provider` / `get_provider` / `list_providers` / `detect_provider`）+ 厂商无关入口 `build_profile_report(provider_id=..., native_report=..., native_coverage=...)`（省略 `provider_id` 时按 `schema_version` 自动识别）。
- **厂商无关规则由基类统一收敛，provider 无法绕过**：§6.3 outcome 推导、覆盖**不得提升**（`_finalize_coverage`）、finding 必填与证据非空（`_finalize_findings`）、溯源写入 `extensions`、结构校验。子类只能提供映射钩子 `_map_findings` / `_map_coverage`，并声明原生词表（`source_report_schemas` / `source_outcomes` / `coverage_complete_token` / `native_outcome_key` / `native_status_key` / `severity_map` / `provenance_key`）。
- **HCZJ 降为一个 provider**：`hczj_adapter.py` 现在只声明 `HczjReviewProvider`（`provider_id="hczj"`）并注册；`build_profile_report(...)` 与 `HCZJ_OUTCOMES` 保留为兼容入口。
- **严重度映射不再归属单一厂商**（原 `NEXUS_SEVERITY_MAP` / `nexus_severity_to_profile` 已移除）：改为 `DEFAULT_PRIORITY_SEVERITY_MAP` + `priority_to_severity(priority, mapping=...)`，未知词元仍拒绝、不降级；provider 可用 `severity_map` 覆盖为自家词表（如 S1–S4）。
- **呈现规则独立**为 `agent_net/code_review/presentation.py`（`render_review_summary` / `validate_publish_body` / `presentation_requirements`），与 provider 无关；`hczj_adapter` 仅做兼容性再导出。
- **可插拔性证明**：新增 `tests/test_code_review_provider_adapter.py`（7 tests）用一个词表与字段形状**完全不同**的评审方（ACME：`acme.review.v2`、outcome `defects|clean|unknown`、severity `S1–S4`、finding 字段 `id/level/summary/repro/consequence/span/proof`、覆盖 `verdict/scanned/skipped/inherited`）走完整管线，验证：注册与自动识别、未知 provider/schema → `unsupported_contract`（不静默降级）、厂商无关不变式不可绕过、HCZJ 便捷入口与通用入口语义一致、呈现与发布前校验与 provider 无关。
- 重构期自查修掉两个**泛化漏洞**（都是真实缺陷，非测试问题）：① 子类覆写 `normalize_coverage` 即可绕过"覆盖不得提升"——改为基类最终收敛；② `provenance()` 假设原生键名为 `status`，导致 ACME 的 `source_coverage_status` 为 None——改为 provider 声明 `native_status_key`/`native_outcome_key`。
- 文档：`docs/api-reference.md` 增加"评审方可插拔"一节（含最小接入示例）；`tests/CLAUDE.md` 登记新测试文件与实测用例数。
- 规范包升级 `1.0-draft.2+semantic.9`（q3 执行记录随模块布局重新生成；自检通过）。
- 全量门禁：**626 passed / 9 skipped / 13 failed / 19 errors**，失败集合与基线逐条一致 → `[PASS]` exit 0。

### RC2 残留建议 R2-1～R2-4 收口（2026-09-20）

- **R2-1**（413 未入错误表）：契约 §7 补 413 行（`data_policy_denied` + `scope=read_limit`），并声明本表覆盖契约使用的全部状态码；`specs/profiles/code-review/v1/tools/validate.py` 新增 `check_contract_error_table()`——契约 §7 的每个 code 必须在本包 `error.schema.json` 枚举内，且枚举中的每个码都必须出现在表中。
- **R2-2**（同码多成因）：契约 §7 固定 `data_policy_denied` 三类 `scope`——`read_limit`(413 超限) / `retention`(422 保留期) / `policy`(403 披露策略)，并明文禁止"仅凭 code 判断原因"；实现侧 `agent_net/code_review/errors.py` 落同一分类学，新增测试锁定三种 (scope, HTTP) 组合。
- **R2-3**（残留修订标签）：契约 §8 改为"本契约定版后…"，不再自指修订号（从根上消除该类过时）；`l0-agentnexus-http.md` §9 去掉 RC1 硬编码并补现状；§7 的 T1–T7 表新增"状态"列，T7 标注"设计范围已确认、部署验证仍待做"。
- **R2-4**（机器校验边界）：契约 §8 新增"机器校验边界"段——`validate.py` 强制范围仅限 `fixtures/valid/` 与 `fixtures/invalid/`；`fixtures/binding/` 的 Markdown 不经 schema 校验、仅由 `manifest.json` 固定摘要；须登记 harness 命令与实际结果，未登记前不得标为已通过。
- **新门禁经负例验证**（证明不为空转）：注入未登记码 `payload_too_large`、删除 `scope=read_limit` 标注、删去一条已登记码的表行 —— 三种情形自检均正确报错。
- 规范包升级 `1.0-draft.2+semantic.8`（自检：契约 24 码与枚举一致、正例 9/9、反例 14/14、manifest 51/51）。记录见契约 §12 与 Profile §14.14。
- **结论不变**：R2 收口属文本级修订，**BINDING-GATE-1 维持关闭**，binding 仍不得定版；剩余条件为 T1–T6 关闭、兼容清单三方冻结、CP-01～26 运行记录。
- 全量门禁：**619 passed / 9 skipped / 13 failed / 19 errors**，失败集合与基线逐条一致 → `[PASS]` exit 0。

### q3 行为用例 harness（2026-09-20）

- 新增 `agent_net/code_review/hczj_adapter.py`：把 HCZJ `hczj.review_report.v1` + `hczj.review_coverage.v1` 转换为 Profile 报告，并实现呈现与发布前校验。
  - outcome 按 §6.3 重新推导（非空 findings ⇒ `issues_found`；空 findings + partial ⇒ `inconclusive`），**不沿用** HCZJ 原 outcome，也不得因原 outcome=inconclusive 丢弃 findings；
  - coverage 在任一缺口信号（遗漏文件/缺口原因/继承缺口/原状态非 complete）存在时**上限为 partial**，绝不提升为 complete；
  - 原始 outcome、来源 schema、来源 report_id 与推导结果一并保留在 `extensions["hczj.provenance"]` 作为溯源；
  - severity 按 RC2 §6 映射（P0→critical…），未知值拒绝而非降级。
- 新增 `render_review_summary()` 与 `validate_publish_body()`：摘要必须**同时**呈现 outcome 与 coverage；覆盖非 complete 时须带缺口警示、遗漏范围与继承缺口，且禁止"评审充分/全部评审完成/无问题/全部评审"表述；发布前校验失败返回 **422 `invalid_output`** 并一次列出全部问题。
- 新增 `tests/test_code_review_q3_harness.py`（12 passed + 1 skip）：覆盖 q3 四组用例（正常转换、重复交付、错误转换与呈现、空发现不等于无问题），并与冻结 fixture `valid/09` 交叉校验关键不变式。发布重放半场属 HCZJ 边界（RC2 §5），以 **skip 显式标记，不视为通过**。
- 新增 `scripts/run_q3_harness.py`：执行用例并生成执行记录 `specs/profiles/code-review/v1/fixtures/binding/q3-execution-record-2026-09-20.md`（真实摘要、实际渲染文本、重放前后计数、A–D 拒绝阶段、未验证项）。规范包升级 `1.0-draft.2+semantic.7`（51 文件，自检通过）。
- 实现期自查修掉两处自身缺陷：渲染的缺口警示文案含"无问题"（会被自身校验器判违规），以及 `run_q3_harness.py` 攒了输出却忘记打印（退出码 0 但记录 0 字节）。
- 全量门禁：**618 passed / 9 skipped / 13 failed / 19 errors**，失败集合与基线逐条一致 → `[PASS]` exit 0。

### 全量回归门禁固化为硬规则（2026-09-20）

- 新增 `scripts/check_full_suite.py`：解析全量 pytest 输出并与 `tests/full_suite_baseline.json` 比对。退出码语义：**0=通过 / 1=回归（出现未登记失败或通过数下降）/ 2=基线需维护（登记项不再失败或存在未分类项）**。纯分析实现，不依赖子进程，受限环境与 CI 均可运行。
- 新增 `tests/full_suite_baseline.json`：逐条登记 25 个**可归因于运行环境**的失败（受限沙箱禁止创建子进程、工作区外临时目录不可访问），每条写明原因；未分类失败拒绝写入基线（`--allow-unclassified` 会被标记待人工确认）。
- 规则落位：`CLAUDE.md` 的 Workflow Rules、`tests/CLAUDE.md`（含受限沙箱已知失败清单与探针式 `tmp_path` 兜底说明）、`docs/agent-workflow.md` 代码评审检查清单第 7 项（评审必须附门禁退出码 0，出现未登记失败不得批准）。
- 触发原因：本次实现中新增模块的 `store_message` 与既有 `messaging.store_message` 在星号导入链上同名互相覆盖，**新测试全绿而 22 个既有测试失败**——只跑局部测试无法发现此类跨模块覆盖型回归。
- 已实测三种判定：与基线一致 → `0`；注入未登记失败 → `1`；登记项不再失败 → `2`。未修改生产代码行为。

### AgentNexus 侧 L0 实现（第一批，2026-09-20）

- 新增 `agent_net/code_review/`（纯逻辑层）：`digest.py` 落地 §15.3 字节口径（严格 UTF-8、拒绝 BOM/孤立 surrogate、LF 行区间不做换行归一）；`errors.py` 落地 `code_review.error.v1`（RC2 §7 的 24 个码、`retryable=false ⇒ retry_after_seconds=null`、429 必带退避、读取上限 413）；`validation.py` 落地信封解析（重复键/NaN/Infinity/关键扩展/消息登记表）与 ReviewReport 的 5 条不变式 + **§15.2 状态翻译责任层**；`authz.py` 收敛 §15.7 的角色判定与 kind→角色映射（唯一实现点）。
- **§15.2 落到源头**：`local_cli` 输出适配器新增 `_apply_profile_translation()`，在 runner 通用重试分支**之前**翻译 Profile 报告——合法的 `changes_requested` 归一为 `completed`（不再被当作重跑信号，CP-09），普通文本包装的 `completed` 直接失败（CP-17）；仅对 `artifact_type=CodeReviewReport` 生效，其他 stage 行为不变。
- **§15.6 交付入口（单事务 CAS）**：`commit_profile_delivery()` 在一个 `BEGIN IMMEDIATE` 事务内校验状态/租约/deadline/输入清单/摘要幂等，随后写入 artifact（含 §15.3 的 `content_hash`/`byte_length`/media_type/access_scope 元数据）、交付记录与 `received` 回执，并更新执行行；产物字节先入 Vault，**存储失败必须失败**（不再有 500 字符截断 fallback）。
- `/coordination/executions/{id}/result` 对 **Profile 绑定执行**走专用路径：Daemon 二次校验（不信任客户端已校验）+ 上述 CAS，只签发 `received`（`validated`/`accepted`/`published` 分别属注册验证服务、Coordinator、Publisher，本入口不越权）；未绑定 Profile 的执行保持旧语义不变。
- §15.7/CP-24：旧通用 `POST /coordination/receipts` 对 Profile Session 一律 403 并要求改走 A/messages；新入口按回执 kind → 角色硬校验；未登记任何角色时降级为部署约定并如实标注 `declared_only`。
- §15.5 强制能力 fail-closed（端到端）：接单时按 `enforcement_requirements` 与本部署注册表比对，未标记 `enforced` 的必需约束一律返回 `422 enforcement_unavailable`（附 `unsatisfied` 列表）且不启动模型调用；拒绝事实先落库（消息 `state=rejected`），**重放同样复核**以保证同一消息结果一致（避免调用方从 202 误判接单成功）；能力补齐后重放可恢复为 `stored`。
- 文档：`docs/api-reference.md` 增加 Code Review Profile v1 的 L0 端点、角色矩阵、错误信封与读取上限说明，并标注 Profile 绑定执行的专用交付语义。
- 测试：`tests/test_code_review_profile.py`（39）、`tests/test_code_review_store.py`（17）、`tests/test_code_review_api.py`（12）、`tests/test_code_review_delivery.py`（10），共 **78 项**，并直接引用冻结规范包的 fixture/反例/摘要向量交叉校验。
- **修复一处自身回归**：`code_review_store.store_message` 与既有 `messaging.store_message` 在 `agent_net.storage` 星号导入链上同名互相覆盖（22 个既有测试 `TypeError`）。已改为显式导入 + `store_profile_message`。
- **测试环境修复**：`tests/conftest.py` 增加探针式 `tmp_path` 兜底（受限沙箱下 `os.mkdir(mode=0o700)` 建出的目录不可扫描，pytest tmpdir 会让所有用 `tmp_path` 的测试报 `WinError 5`）；仅当探针失败时覆盖，正常 CI 行为不变。
- 尚未完成：`fixtures/binding/` 行为用例的可执行 harness；CP-01～26 的可复现运行记录（涉及真实 worker 子进程的用例需非沙箱环境）。未声明实现符合性或 wire conformance。

### L0 RC2 复核与规范包 semantic.6（2026-09-20）

- 完成 `bindings/l0-service-contract.md`（RC2）复核：**修订核实通过；RC1 的 Q1–Q3 与 S1–S7 全部关闭，契约文本层面已无阻塞项**，但 **BINDING-GATE-1 维持关闭**（T1–T6 未关闭、§15.2–15.7 未实现、兼容清单未三方冻结、CP-01～26 未执行）。记录写入契约 §11、Profile §14.13。
- 独立复核（不依赖自述）：Q1 三级关联键与 epoch 围栏、Q2 §3.1 七标签到 Profile 可观察事实的映射（`expired` 正确分流为 deadline / 仅租约失效 / 目标已更新）、Q3 §6 联合呈现 + `fixtures/binding/q3-outcome-coverage.md` 四组行为用例，均已核实；RC2 §7 错误表仍 **24 码零偏差**。
- 复核者复算外部证据：`source-evidence.json` 12 个文件摘要在 RC2 **复算 12/12 相符**；其 `repository_states` 的 `unavailable` 记录经实测确认**准确**（`Nexus_Agent` 无 `.git`，`Hczj_Assistant_Agent\.git` 为空目录、无 HEAD）——未以推测值填充。
- RC2 新增建议（不阻塞）：R2-1 §10.1 的 HTTP 413 未进入 §7 错误表；R2-2 `data_policy_denied` 同时承载超限与保留期拒绝，建议以 `scope` 区分；R2-3 残留 "RC1" 标签与 T7 行未标注已确认；R2-4 `fixtures/binding/` 的机器校验边界宜在 §8 点明。
- 规范包升级 `1.0-draft.2+semantic.6`（manifest 50 个文件）：`fixtures/index.json` 与 README 标明机器校验范围仅限 `valid/`+`invalid/`（`fixtures/binding/` 为行为规范、不经 schema 校验）；cp-matrix 的 CP-08/CP-09 增加 `#anchor` 指向 q3 行为用例；`compatibility.json` 登记 RC2 端点为未实现项、binding 状态改为 `rc2_reviewed_not_frozen`；`tools/validate.py` 支持 `#anchor` 引用。自检 正例 9/9、反例 14/14、manifest 50/50。
- 未修改生产代码；未声明 wire conformance 或实现符合性。

### L0 RC2 评审修订（2026-09-20）

- 修订 Q1–Q3：补齐 Coordinator/Run/Attempt/epoch 关联，明确 Attempt 内部标签映射，补 outcome/coverage 联合呈现与行为验收用例。
- 处理 S1–S7：统一候选词表、加严说明、重试/幂等规则、证据 Git 状态、fixture 宿主及读取上限；保留评审新增 valid/09。
- 包升级 semantic.5，双方引用摘要同步；新增接口及行为验收未实现，修订待复核。

### L0 RC1 契约评审与规范包修订（2026-09-20）

- 完成 `bindings/l0-service-contract.md`（RC1）评审：**有条件通过，binding 仍不得定版**；评审记录写入该契约 §9，Profile 同步 §14.12。
- 独立复核（不依赖自述）：契约 §7 的 **24 个错误码与冻结 `error.schema.json` 枚举逐一相符**（无未登记、无遗漏）；`source-evidence.json` 的 **12 个外部文件摘要在本机 Nexus_Agent / Hczj_Assistant_Agent 上重算 12/12 相符**；RC1 的 outcome/coverage 适配规则与冻结 `review_report.schema.json` 的 5 条不变式一致；摘要口径与 §15.3/CP-23 一致。
- 阻塞项（定版前必须补）：**Q1** RC1 §1 遗漏 `external_coordinator_id`/`assignment_epoch`（与 Profile §15.6 不一致）；**Q2** AttemptView 引入 Profile 未定义的新状态机，需声明为内部细节并给映射或走设计变更；**Q3** "有发现且覆盖不足"缺契约用例与呈现规则。
- 建议项 7 条（S1–S7）：`access_scope` 候选词表表述统一、binding 加严需标注、`retry_after_seconds` 不变式引用、幂等 key 与投影措辞统一、`source-evidence.json` 补 commit/dirty、fixture 宿主统一、`/raw` 与 `/source-bytes` 补大小上限。
- 规范包升级 `1.0-draft.2+semantic.4`（manifest 49 个文件）：收紧 `publication_request.outbox_state`（客户端只能缺省或 null），新增正例 `valid/09`（findings + inherited_gap ⇒ issues_found + coverage=partial）与反例 `invalid/publication_request_client_set_outbox_state.json`，`compatibility.json` 记录 `access_scope` 候选但 `operative_allowlist=false`；自检 正例 9/9、反例 14/14、manifest 49/49。
- 门禁：BINDING-GATE-1（§14.10 门禁 1）维持关闭；不得启动"符合本 Profile"的集成运行，不得声明 wire conformance。未修改生产代码。

### L0 服务接口契约 RC1（2026-09-20）

- 补齐 Nexus 原始证据、HCZJ 状态与协作、AgentNexus 产物、Publisher 的服务端点和认证/幂等/ACK/CAS/错误/超时契约；同步双方实施登记。
- 包升级 semantic.3；新增接口待评审、未实现，兼容允许清单保持空。

### L0 binding 跨项目确认（2026-09-20）

- 在 Nexus/HCZJ 分别登记确认记录，中央汇总 T1–T7 源码证据和剩余条件；T7 设计范围确认，T1–T6 保留开放项，binding 未定版。
- 核实 Nexus 持久化字节与 HTTP JSON 差异、HCZJ outcome/coverage 差异及缺少外部协作/发布接口；运行兼容允许清单继续为空。
- Nexus 定向测试 17 项、HCZJ 定向测试 132 项通过；不代表三方 wire 或 CP 验收。规范包升级为 `1.0-draft.2+semantic.2`，未修改生产代码。

### Code Review Profile v1 规范包与 L0 binding 草案（2026-09-18）

- 新增 `specs/profiles/code-review/v1/` 语义规范包（包版本 `1.0-draft.2+semantic.1`）：15 个 JSON Schema、8 个正例、13 个结构反例（各自绑定一条 Profile MUST）、CP-01～26 矩阵、`compatibility.json`（默认空列表拒绝全部）、`manifest.json`（44 个文件摘要 + Git revision）、README。
- 摘要口径按 §15.3 用真实 SHA256 冻结为 `fixtures/digest_vectors.json`（CP-23/CP-26），并给出"重序列化会改变摘要"的反例向量；明确旧 `result_hash` 不兼容且不得补造 `report_digest`。
- 新增自检工具 `tools/validate.py` 与 `tools/make_manifest.py`；当前自检结果：正例 8/8 通过、反例 13/13 被拒、无孤儿 fixture、摘要向量一致、manifest 44/44 一致。
- 新增 L0 binding 草案 `bindings/l0-agentnexus-http.md`：把 Profile 消息映射到现有 26 条 `/coordination/*` 路由，逐条列出与 §15.2–15.7 的差距（缺 `delivery_id`/`assignment_epoch`/`output_schema` 校验/结构化错误信封、自动签发 `approved` receipt、无角色级写授权），并列出外部 TBD（Nexus 事件与证据查询、HCZJ Run/Attempt/activation、发布适配器归属、`access_scope` 词表）。
- 补正 R3 收尾：`docs/design/design-code-review-v1.md` 第 5、14 行的"待评审/ADR-015 提议"措辞已改为"已由 ADR-015 采纳"。
- 边界：**未声明 wire conformance，未声明实现符合性**；AgentNexus 侧改造（§15.2–15.7）与 wire fixture 尚未实现，本轮未修改生产代码。

### Profile 非阻塞建议收口（2026-09-18）

- 落实 R1～R3：澄清摘要解析顺序，补充 coordinator_unavailable 错误语义，显式标记上位设计旧架构与数据模型已被取代。
- 保留设计通过结论及实施门禁，未修改生产代码。

### Code Review Collaboration Profile v1 设计评审通过（2026-09-18）

- `docs/design/code-review-collaboration-profile-v1.md`（1.0-draft.2）完成第二轮复核：**设计评审通过（批准）**，复核确认写入文档 §14.10。
- 结论：P1–P7 全部关闭、S1–S14 全部采纳；[ADR-015：代码评审双层状态权威](docs/adr/015-code-review-state-authority.md) 批准为"已采纳"；三方契约登记同步更新。
- 独立复核要点：§15.2 状态翻译责任层 + 禁用 `coding.v1`/`on_reject` + 未知 status 硬拒绝；§15.3 摘要口径（解码后 `artifact_body` 的严格 UTF-8 字节）**与既有 `POST /coordination/artifacts` 的 `content_hash` 计算一致**（`agent_net/node/routers/coordination_records.py:159`），可无冲突实施；§15.4 词表命名空间与双向映射；§15.5 强制点与 `enforcement_unavailable` fail-closed；§15.1 语义/绑定边界与 L0 binding 评审门禁；§15.6 external ID 与 epoch 围栏；§15.7 角色级写入授权。`specs/profiles/` 尚未生成，与文档"计划路径"声明一致。
- 残余建议复核：R1（§3 字节口径与处理顺序）已落实、R2（`coordinator_unavailable` 入 `code_review.error.v1`）已落实、R3 部分落实——`design-code-review-v1.md` 两个旧模型章节已标为"历史方案，已被取代"，但该文件第 5、14 行仍有 2 处"待评审/提议"措辞与 ADR-015 已采纳冲突，待补正（不影响设计批准结论）。
- 实施门禁：L0 binding 单独评审 + `specs/profiles/code-review/v1/` schema/兼容清单/fixtures 冻结 + CP-01～26 验收前，不得声明实现符合性或 wire conformance。本轮仅文档评审，未修改生产代码。

### Profile 评审修订（2026-09-18）

- 升级到 1.0-draft.2，逐项回应 P1–P7/S1–S14，保留原评审并标注待复核。
- 补齐状态/摘要/收据/外部 ID 映射、授权强制点、语义与 wire binding 边界，以及 CP-19～26。
- 新增 ADR-015 提议及三方契约登记，同步上位需求和 quickstart；未修改生产代码。

### Code Review Collaboration Profile v1 首轮设计评审（2026-09-18）

- `docs/design/code-review-collaboration-profile-v1.md`（1.0-draft.1）完成首轮设计评审：**有条件通过**，评审记录写入文档 §14。
- 结论：7 个阻塞项（P1–P7）、14 个建议项（S1–S14）、4 条信息性备注（I1–I4）；阻塞项决议写入文档前不进入开发，也不得声明 wire conformance。
- 阻塞项集中在"规范语义与现有实现冲突或无强制落点"：P1 review 的 `changes_requested` 会被 `runner_loop` 重跑并按 `on_reject` 退回 implement（与 §6.4 / CP-09 冲突）；P2 `sha256-bytes-v1` 无落点且既有 `result_hash` 为重新序列化摘要；P3 Receipt/ArtifactRef 词表与既有 `ReviewReceipt`/artifact 字段撞车；P4 provider 与数据策略无强制点（CP-16 不可验证）；P5 缺 transport binding 且发起方未定；P6 `run_id` 命名空间与 `assignment_epoch` 围栏缺失（CP-05/CP-14 无机制）；P7 `POST /coordination/receipts` 无角色校验，Reviewer 可自签 `approved`。
- 同步 `docs/wip.md`；本轮仅文档评审，未修改代码、未实现 Profile。

### Code Review Collaboration Profile v1 草案（2026-09-18）

- 新增 1.0-draft.1 场景契约：任务接受、不可变输入、四元 Run 身份、Attempt/epoch、分层 Receipt、证据覆盖与发布结果未知处理。
- 对齐 Nexus/HCZJ RUN-ID-2026-09-14，提议 HCZJ 保持评审状态权威、AgentNexus 适配接入；标注早期设计的职责差异待评审。
- 补充 CP-01～18 一致性验收矩阵，同步文档入口。纯设计文档变更，未声明实现符合性。

### Code Review V1 规划（2026-09-07）

- 新增跨项目自动代码评审需求与设计草案，明确 Nexus_Agent、HCZJ 和 AgentNexus 职责。
- 定义版本绑定、过期任务、证据契约、GitLab 发布恢复及 CR-01～CR-08 验收要求；同步需求、设计索引和 WIP。本轮未实现 AgentNexus 生产代码。

### ACF RFC-003 Capability Negotiation, Authority Grants, and Delegation（2026-07-29）

- 新增并迭代 RFC-003 Draft v0.3，明确 Capability、Permission、Authority、Authority Grant 与 Delegation 的边界。
- 定义 receiver-driven Capability Requirements、Authority Request/Grant、Grant Acceptance、Constraint、Condition、Obligation、Proof of Possession 与结构化 Verification Result。
- 规定派生授权的 action、resource、audience、purpose、validity、allocation 与 delegation depth 必须单调收窄，约束和各类保护语义只能保持或增强。
- 修正委托主体模型：Authority Scope 使用子集规则，Grantee / Executor 使用独立的 Subject Transition 验证；普通委托保持 Represented Principal 不变。
- 对金额、次数、库存和配额等可消耗 Authority 增加 partitioned/shared-counter/exclusive-transfer/single-use 分配与全授权树会计不变量。
- 明确 immutable Grant Body 是授权事实来源，Delegation Record 只承担审计和关联；补充摘要覆盖、Critical Extensions、多 Grant 组合与 Purpose Assurance。
- 闭合 Grant Acceptance 生命周期：增加 acceptance_pending、countered、accepted_pending_activation；conditional acceptance 必须产生 replacement Grant，不能直接激活。
- Obligation 增加唯一 ID，状态改为技术中立的 status mechanism descriptor，并允许严格匹配条款的 request-time pre-acceptance。
- 将 Purpose Assurance、授权相关 Critical Extensions 与状态机制兼容性纳入委托保护不变量；关键扩展剥离和 Purpose Assurance 降级必须失败。
- 定义 Accounting Domain Continuity，禁止子 Grant 通过切换到独立账本绕过父级可消耗预算。
- 区分 Obligation retention 与 propagation，增加安全的 Delegate Policy 默认值，并澄清联合/Threshold Grant Composition 与离线撤销传播边界。
- 规定子 Grant 携带的 Delegate Policy 必须单调收窄父级 redelegation ceiling，并区分当前受让者资格与下游再委托上限。
- Condition 替换必须通过确定性的逻辑蕴含检查；Grant Composition 必须显式保留 Purpose Assurance、Critical Extensions 与状态要求。
- 增加 `status_mechanism_incompatible` 等结构化失败语义，并将 Delegate Policy JSON、selector、完整测试向量、Condition implication、canonicalization、proof suite 与 JSON Schema 列为 Baseline Profile 交付项。
- 明确 Grant Composition 默认不产生委托权或 Grant Issuance Authority；显式 composed Delegate Policy 必须落在所有适用 redelegation ceilings 的交集内。
- 明确 Condition 数组默认使用 AND 语义，并更新父 Grant Delegate Policy 与 Verification Result 示例。
- 使用 `session_proposal_id` 解除 Authority Grant 与未来 Session Agreement 的循环依赖。
- 增加 RFC 9396、RFC 9635、RFC 8693、RFC 9767、RFC 9449 和 W3C VC 2.0 的正式语义映射表。
- 增加 Capability Requirement / Statement / Result 示例与最小负向测试向量。
- 将现有 `CapabilityToken` 重新定位为实验性的 Authority Grant Token profile；协议验证不替代 Receiver 的本地授权决策。
- 同步 RFC-000、README 与 AGENTS 文档索引。

### L0-Ready Real Worker Smoke（2026-06-29）

- 新增 `scripts/l0_ready_real_workers_demo.py`，可复现注册 Owner DID 和 3 个真实本机 Worker DID，并以 script/pytest、Claude CLI、OpenClaw CLI 跑完整 Objective Loop。
- 成功验收形态：`session_status=completed`、6 次 worker execution、6 个 artifact、7 个 receipt；`coding.v1` final stage 由 advance API 自动收口。
- 新增 `docs/assets/l0-ready-real-workers-evidence.png`，README、Objective Loop Quickstart、release notes 和推广清单同步引用。
- 修复 `agent_net/node/static/coordination.html` 中 `execs` 同名声明导致 session detail 页面 `SyntaxError` 的问题。

### Agent Adapter Contract（2026-06-29）

- LocalCLIBackend 新增输出归一化器，支持 `agentnexus_json_v1`、`openclaw_json`、`json_text`、`text_artifact` 四种 `output_adapter`。
- OpenClaw `--json` wrapper 可通过 `payloads[].text` / `meta.finalAssistantRawText` 归一为 AgentNexus artifact；任意 JSON wrapper 可通过 `output_text_paths` 接入。
- local-runner 默认命令 allowlist 增加 `claude.cmd`、`codex.cmd`、`openclaw.cmd`，并支持大小写不敏感的 basename / 全路径匹配。
- runner 命令模板支持 `{stage}`、`{role}`、`{objective}`、`{coordination_session_id}`、`{run_id}`，用于 OpenClaw session key、外部 agent routing key 等场景。
- 新增 `docs/integrations/agent-adapter-contract.md`，明确任意 Agent 接入范式：DID 负责身份，roles/capabilities 负责路由，local_cli 负责启动，output_adapter 负责输出归一化。

### Developer Preview 推广收口（2026-06-26）

- README 首屏新增 Developer Preview 入口，明确第一版公开定位：DID 身份、授权、产物交付和 Objective Loop 的多 Agent 协作底座。
- 新增 `docs/promotion.md`，沉淀推广完成度清单、发布边界、最小 demo、目标受众、首批外发文案和 L0-ready preview gate。
- `docs/project-status.md` 增加推广状态，统一 `v1.0.1 developer preview → v1.1 L0-Ready` 口径。
- 根包与 SDK 元数据对齐到 `1.0.1`，修复 SDK 项目链接。
- 修复 Dashboard 推广截图阻塞项：API client 使用当前 origin、`actor_did` 深链可恢复本地身份、Run detail stage 状态聚合 artifact + approved receipt，并新增 Objective Loop Dashboard 截图。

### 评审问题修复与拆分后清理（2026-06-25）

- 修复 `relay start --host` 导入顺序问题，确保自定义 host 在 Relay DID 初始化前生效。
- 声明 `pyyaml` 运行时依赖，并修复 `load_runner_config()` 浅拷贝污染 `DEFAULT_CONFIG` 的问题。
- `execute_stage()` 显式拒绝未支持的 `backend_kind`，避免参数被静默忽略。
- Execution API 统一使用 Coordination session 访问控制，覆盖 owner/controller/owner-bound agent/accepted delegation；同时修复 session list 中 secretary 判定的旧调用签名问题。
- Loop Engine 不再被历史 stage 的 pending decision 阻塞，只等待当前 stage 的待处理决策。
- 删除 Relay 中已迁移至 DIDResolver 的 `_resolve_meeet_via_solana()` 死代码。
- CLI、Coordination 路由子模块、Relay 业务子模块移除 star-import；仅保留 `agent_net/relay/server.py` 兼容聚合器的 re-export。
- SDK 新增共享常量模块，收敛 `PROTOCOL_NEXUS_V1` 与 push callback URL；移除无字段 mixin 的 `@dataclass` 和拆分文件中的未使用导入。
- 补充回归测试：默认配置不污染、未支持 backend 拒绝、历史决策不阻塞当前 stage。

**验收结果：** 后端 `547 passed, 8 skipped`（跳过 online），SDK `129 passed`；compileall 与 Ruff 均通过。

### 大文件领域拆分与资源生命周期收口（2026-06-24）

- `agent_net/storage.py` 改为兼容门面，持久化实现按 core、schema、governance、enclave、coordination 拆分。
- Coordination API 按 sessions、delegations、records、coding、executions 拆分，保留原 router 和 URL。
- `main.py` 改为 CLI 聚合入口，命令实现迁移到 `agent_net/cli/`。
- Relay Server 按 registry、federation、identity、ANPN、MEEET 拆分，保留旧 monkeypatch/import 契约。
- SDK client 拆为 lifecycle/actions/polling mixin；discussion 拆为 models/state/manager。
- LocalCLIBackend 取消执行时显式终止并回收子进程；Execution API 改为原生 async，移除请求级 `asyncio.run()`。
- 新增 Ruff correctness 门禁，并将 pytest async loop 设为 session scope，避免 Windows Proactor 资源耗尽。

**验收结果：** 后端 `544 passed, 8 skipped`，SDK `129 passed`，0 warnings；源码 compileall 与 Ruff 均通过。

### Objective Loop V1.1 — 阻塞问题修复（2026-06-22）

修复 7 个阻塞/高优先级问题，demo 验证通过（7/7 stages OK）。

**修复内容：**

| # | 问题 | 修复 |
|---|------|------|
| 1 | Runner 无 token/auth，401/400 | `local-runner start` 读取 daemon token，传递 `owner_did`/`actor_did`，所有 API 请求带 `Authorization` header |
| 2 | 自动循环不完整，仅记录不推进 | `runner_tick()` 新增 `call_advance`/`create_decision` 回调；`start` 命令处理全部 7 种 action_type |
| 3 | Worker 无任务上下文，{prompt} 不替换 | 新增 `build_worker_prompt()` 构建结构化 prompt（objective/artifact refs/constraints/acceptance criteria）；模板变量替换 |
| 4 | 重试/on_reject 闭环断裂 | `retry_attempt` 传入 execution metadata；`on_reject` 查找目标 stage 的 role；PlaybookRun 正确更新 |
| 5 | Execution API 无访问控制 | 新增 `_verify_session_access()` 校验 actor_did 对 session 的 owner/controller/secretary 权限 |
| 6 | Result 契约不满足（覆盖/无DecisionGate/截断） | 不同 hash → 409；blocked → 自动创建 DecisionGate；artifact body 写入 Vault（不截断）；emit audit event；幂等正确 |
| 7 | LocalCLIBackend 缺 JSON 重试/workdir | 首次 JSON 解析失败返回 `changes_requested`（重试信号）；新增 `workdir` + `env` 约束支持 |

**Demo 验证：**
```
=== Objective Loop V1.1 Demo ===
  [1/7] clarify... OK
  [2/7] design... OK
  [3/7] design_review... OK
  [4/7] implement... OK
  [5/7] code_review... OK
  [6/7] test... OK
  [7/7] final... OK
=== Demo complete ===
```

**测试结果：** 92 passed, 0 failed（无变化，所有修复向下兼容）

### Dashboard + Quickstart 收口（2026-06-22）

- **Dashboard**: 新增 Executions 标签页（展示 objective_executions 状态/attempt/lease/artifact/receipt）；新增 Next Action 面板（实时显示 Loop Engine 决策）；新增 execution 状态徽章样式
- **API**: 新增 `GET /coordination/sessions/{id}/executions` 端点，支持按 run_id/stage 过滤
- **Quickstart**: 新增 `docs/quickstart-objective-loop.md`（10 分钟快速上手指南，涵盖 daemon 启动、demo 运行、Dashboard 查看、local-runner 配置、API 速查、FAQ）

完成 L0 本机 Objective Loop 全部核心模块 + daemon API 集成 + runner poll loop + CLI demo，严格遵循 TDD 流程（RED→GREEN→REFACTOR）。

**P0-1 ~ P0-5 核心模块**：
- P0-1: `objective_executions` 表 + 5 CRUD 函数 + 幂等 result 提交
- P0-2: `ExecutionBackend` Protocol + `LocalCLIBackend`（argv 执行/白名单/timeout/JSON 解析）
- P0-3: `local_runner`（YAML 配置/worker 匹配/stage 执行）
- P0-4: `loop_engine` — `next_action()` 状态机，9 种 action_type
- P0-5: `secretary_gateway` — DecisionGate handler，8 种 gate 类型

**Daemon API 集成**：
- `GET /coordination/sessions/{id}/next-action` — Loop Engine 状态查询
- `POST /coordination/executions` — 创建 execution lease
- `PATCH /coordination/executions/{id}` — 更新 execution 状态
- `POST /coordination/executions/{id}/result` — 提交结果（幂等，自动创建 artifact+receipt）

**Runner Poll Loop**：
- `agent_net/node/runner_loop.py` — `runner_tick()` 单轮轮询 + `process_action()` 单步执行
- `python main.py node local-runner start` — 完整 poll loop（自动发现 session → 获取 next_action → 匹配 worker → 执行 → 提交结果）
- `.agentnexus/local-runner.yaml.example` — 配置模板（含 fake workers）

**CLI Demo**：
- `python main.py node objective demo` — 完整 7-stage coding 闭环演示（clarify → design → … → final）
- `python main.py node objective status <id>` — 查看 Loop Engine 状态

**测试结果：** 新增 56 个测试；92 passed, 0 failed；无回归

**新增文件：**
```
agent_net/node/
├── loop_engine.py                    # 状态机
├── local_runner.py                   # YAML 配置 + worker 匹配 + 执行
├── runner_loop.py                    # Poll loop
├── secretary_gateway.py              # DecisionGate handler
└── execution_backends/
    ├── __init__.py
    ├── base.py                       # ExecutionHandle, ExecutionResult, Protocol
    └── local_cli.py                  # argv 子进程执行

tests/
├── test_objective_execution_storage.py  (12 tests)
├── test_local_cli_backend.py            (10 tests)
├── test_objective_loop_engine.py        (9 tests)
├── test_local_runner.py                 (10 tests)
├── test_runner_loop.py                  (5 tests)
├── test_secretary_gateway.py            (3 tests)
└── test_execution_api.py               (7 tests)
```

**P0-1 Storage** — `objective_executions` 表与 CRUD：
- 新增 `objective_executions` 表（execution_id, coordination_session_id, run_id, stage, worker_did, backend_kind, status, lease_expires_at, attempt, artifact_id, receipt_id, result_hash, metadata, timestamps）
- 5 个存储函数：`create_objective_execution`, `get_objective_execution`, `list_objective_executions`, `update_objective_execution`, `mark_execution_result`
- `mark_execution_result` 支持幂等（相同 result_hash 返回既有记录）
- 2 个索引：`(coordination_session_id, run_id, stage)` + `(status, lease_expires_at)`

**P0-2 ExecutionBackend** — 执行通道抽象层：
- 新增 `agent_net/node/execution_backends/` 包
- `ExecutionHandle` / `ExecutionResult` dataclass，`ExecutionBackend` Protocol
- `LocalCLIBackend`：argv list 子进程执行（无 shell）、命令白名单、destructive pattern 检测、timeout kill 进程树、stdout/stderr output size 限制、JSON 结构化输出提取

**P0-3 Local Runner** — 本地 Runner 配置与执行：
- 新增 `agent_net/node/local_runner.py`
- YAML 配置加载与校验（`load_runner_config`），worker 按 role/capability 匹配
- `execute_stage()`：从 Loop Engine 的 `start_execution` action 通过 LocalCLIBackend 执行单个 stage
- CLI 入口：`python main.py node local-runner run/start`
- 配置模板：`.agentnexus/local-runner.yaml.example`（含 fake worker）

**P0-4 Loop Engine** — 目标循环状态机：
- 新增 `agent_net/node/loop_engine.py`
- `next_action()` 函数：读取 session/run/execution/artifact/receipt/decision 状态，计算下一步动作
- 9 种 `action_type`：`start_execution` / `poll_execution` / `advance` / `submit_receipt` / `create_decision_gate` / `wait` / `closed` / `blocked`
- retry counter + max_retries → DecisionGate；`on_reject` 回退按 Playbook stage 定义
- CLI 入口：`python main.py node objective status <session_id> --actor <did>`

**P0-5 Secretary Human Gateway** — 人工决策点：
- 新增 `agent_net/node/secretary_gateway.py`
- `handle_decision_gate()`：将 Loop Engine 的 `create_decision_gate` action 转换为持久化 `decision_request`
- 8 种 DecisionGate 类型（scope_change / secret_access / destructive_command / network_access / low_confidence / review_conflict / max_retry_exceeded / final_acceptance），每种带人类可读的问题描述、风险等级和选项列表

**测试结果：** 新增 44 个测试（P0-1: 12, P0-2: 10, P0-3: 10, P0-4: 9, P0-5: 3）；80 个全部通过；无回归

**设计文档：** `docs/design/design-objective-loop-v1.1.md` 通过 4P + 5S + 7D 评审，已补开发契约、P0 任务拆分、API Contract、存储方案、安全检查清单

---

### Coding Coordination V1 Alpha Readiness — 已完成（2026-05-26）

- 完成最终闭环 Delivery Manifest：stage/final manifest 自动落入 Enclave Vault，FinalResultReceipt 与 ClosureRecord 持有 manifest evidence refs
- Dashboard Coordination 详情页补齐 run、closure evidence、Delivery Manifest 展示，并支持从 Vault 读取 manifest 内容
- SDK 增加 `coordination.emit_event()`；CLI 增加 `node coordination runtime-mock`，用于模拟外部 runtime adapter 接入 stage
- CLI `delegate` 补齐 `--run`，多 run 场景可显式委派到目标 PlaybookRun
- Quickstart 增加 demo 输出、Dashboard URL、runtime-mock、policy gate/on_reject 示例

**测试结果：** 63 passed（coordination + manifest + CLI 回归）；`py_compile` 通过

---

### Coding Coordination V1 Run-State Refactor — 已完成（2026-05-20）

- 将 `advance` 改为 run 级 API：`POST /coordination/coding/{coordination_session_id}/runs/{run_id}/advance`
- `PlaybookRun` 成为 `current_stage/status` 的运行态状态源；CoordinationSession 只作为审计、权限和聚合容器
- artifact / receipt 增加 `run_id` 维度，避免多 run 同名 stage 串线
- `playbook_runs.coordination_session_id` 改为真实写入，timeline 从 session 关联 run 聚合
- fork 创建独立 child PlaybookRun；Enclave run 明确为 `coordination_mode=standalone`
- SDK、CLI、Quickstart、README、设计文档同步到 `playbook_id/run_id` 语义

**测试结果：** 133 passed（相关回归）；53 个 coordination 测试通过

---

### Architecture Review & P1 Cleanup — 已完成（2026-05-09）

全项目架构审查（详见 `docs/architecture-review-2026-05-09.md`）并实施 P1 修整：

- **删除无引用旧入口文件**：`agent_net/daemon.py`（v0.1.0 旧 Daemon）、`agent_net/mcp_server.py`（7 工具旧 MCP Server），均已被 `agent_net/node/` 下版本完全替代
- **删除被 package 遮蔽的死文件**：`agent_net/identity.py`（被 `agent_net/identity/` 包目录遮蔽，Python 导入优先匹配 package 目录）
- **移除死代码**：`agent_net/node/routers/agents.py` 中无效的 `global _heartbeat_task_ref` 及 `import _self`
- **向后兼容重导出添加 `@deprecated`**：`agent_net/auth/handshake.py`、`agent_net/identity/did_generator.py`，引导调用方迁移到 `common` 模块
- **移除 `router.py` 死字段**：`RELAY_URL` 常量及 `Router.relay_url` 参数（类内无任何路径读取该字段）
- **更新 `common/did.py` `@context` URI**：`https://agent-net.io/v1` → `https://agentnexus.top/contexts/agent-profile/v1`
- **给 P2P/Relay 异常加上 `logger.warning`**：`router.py`、`node/_config.py` 中原为裸 `except Exception: pass` 的 5 处

**测试结果：** 471 passed, 8 skipped

---

### Code Review — 已完成（2026-04-30）

#### Dashboard / Setup + Secretary Phase B 收口 — 代码评审通过

**本轮解决项：**

- **API Client 契约修复**：`web/src/api/client.ts` 全部重写，所有需要 `actor_did` 的 helper 显式参数化（§5.2 要求）
- **Worker API**：新增 `listWorkers`、`setWorkerType`、`getWorkerPresence`
- **Secretary API**：新增 `dispatchSecretary`、`listIntakes`、`abortIntake`、`getIntake`
- **Run/Vault API**：新增 `getRun`、`getVaultEntry`、`listVaultKeys`
- **Phase B 细节修复**：重复 `create_stage_execution`、Context Snapshot objective 来源、`context_budget` 字段名对齐设计文档
- **CLI worker init**：移除冗余 PATCH（注册已包含 worker_type）
- **Adapter token**：`_intake_and_dispatch` 自动读取 daemon token
- **Dashboard**：新增 Worker presence、Active Runs、Recent Intakes 聚合
- **Setup**：6 步闭环（Token → Owner → Secretary → Workers → Dispatch → Result）
- **Agents**：worker_type 可编辑下拉、presence 状态列
- **Enclaves**：Run 详情、Owner abort、面包屑状态清理

**遗留项（后移到 v1.1）：**
- D-SEC-04 角色选择与回退策略
- D-SEC-06 超时/重试/fallback 自动化
- CLI Launcher 自动拉起
- Playwright / API 级 smoke test

**测试结果：** 432 passed, 8 skipped, TypeScript/vite build 通过

---

### Code Review — 历史（2026-04-30 前）

---

## [1.0.1] - 2026-04-21

### Added

#### A2A Protocol: Decision Consistency Levels (L0/L1)
- **consistency_level.py** — `ConsistencyLevel` 枚举（L0-L3）、`EvaluationContext` 数据类、L1 窗口验证（`check_l1_window`）
- **capability_token.py** — `verify_token()` 新增 `consistency_level` 参数，成功响应携带 `evaluation_context`（L0 省略，向后兼容）
- **design.md** — 协议层一致性级别设计规格
- **test_consistency_level.py** — 7 个测试用例覆盖 L0/L1/L2 构建、窗口边界、序列化往返
- 382 tests pass（新增 7 个，无破坏）
- A2A proposal 已发布：https://github.com/a2aproject/A2A/issues/1717#issuecomment-4289144462

---

## [1.0.0] - 2026-04-15

### Added

#### 1.0-04 个人主 DID
- **agents 表新增 owner_did 列**：支持层级关系，主 DID 的 owner_did=NULL
- **register_owner(name)**：注册主 DID（profile.type="owner"）
- **bind_agent/unbind_agent**：绑定/解绑 Agent 到主 DID
- **list_owned_agents**：列出主 DID 下所有子 Agent
- **端点**：`POST /owner/register`, `/bind`, `DELETE /unbind`, `GET /owner/agents`, `GET /owner/profile`

#### 1.0-06 消息中心
- **fetch_owner_inbox**：聚合主 DID 下所有子 Agent 的未读消息
- **fetch_owner_messages**：聚合全部消息（分页）
- **fetch_owner_message_stats**：各子 Agent 消息统计（未读数、最后消息时间）
- **端点**：`GET /owner/messages/inbox`, `/all`, `/stats`

#### 1.0-08 Capability Token Envelope（ADR-015）
- **capability_tokens 表**：存储结构化权限令牌
- **delegation_chain_links 表**：委托链关系
- **stage_executions 新增字段**：evaluated_constraint_hash, capability_token_id
- **CapabilityToken dataclass**：完整 Token 结构（12 个字段）
- **compute_constraint_hash**：JCS 规范化 + SHA256，符合 qntm WG decision artifact 要求
- **scope_is_subset**：单调收窄验证（child ⊆ parent）
- **issue_token/sign_token**：Ed25519 + JCS 签名
- **verify_token**：5 步验证（状态→签名→有效期→委托链→权限）
- **端点**：`POST /capability-tokens/issue`, `GET/{id}`, `POST/{id}/verify`, `POST/{id}/revoke`, `GET/by-did/{did}`
- **权限映射**：admin/rw/r → 细粒度权限数组，与 SINT T2/T1/T0 对齐
- **撤销端点必填**：revocation_endpoint 字段

### Phase 2 新增（2026-04-17）

#### 1.0-05 意图路由
- **_intent_route 方法**：根据消息内容关键词匹配子 Agent capabilities
- **匹配阈值 MIN_MATCH_SCORE=2**：避免低质量转发（S1-05-1）
- **set 去重关键词**：避免 tags 继承 capabilities 导致重复计数
- **递归路由**：匹配成功后递归调用 route_message 转发到子 Agent

#### 1.0-01 Web 仪表盘 Phase A
- **Vue 3 + Vite + PrimeVue**：前端框架选型
- **web/ 目录**：前端源码（不打包进 pip install）
- **构建产物**：输出到 `agent_net/node/static/`
- **StaticFiles(html=True)**：SPA fallback，支持 Vue Router history mode
- **API 调用层**：`src/api/client.ts`（fetchApi wrapper + Token 携带）
- **路由配置**：Dashboard/Agents/Messages/Enclaves/TrustNetwork/Setup
- **基础页面组件**：Dashboard.vue、Agents.vue、Messages.vue、Enclaves.vue、TrustNetwork.vue、Setup.vue

### Fixed

#### 代码评审问题修复（2026-04-15）
- **P1**: `verify_token` 委托链验证改为直接调用 `get_delegation_chain_func(token.token_id)`，不依赖动态属性 `_parent_token_id`
- **P2**: `api_issue_token` 在保存前手动补上 `_parent_token_id` 和 `_parent_scope_hash`，确保委托链写入数据库
- **S2**: `verify_token` 的 `parent.scope` 改为 `parent["scope"]`，兼容 dict 和 CapabilityToken 对象

### Tests
- 375 passed, 8 skipped
- 新增测试文件：test_v10_owner.py (6), test_v10_messages.py (4), test_v10_capability_token.py (9), test_v10_intent_route.py (4)
- 补充测试用例：委托链端到端（T1）、单调收窄拒绝（T2）、过期 Token（T3）、意图路由匹配/无匹配/阈值/无子Agent

### Fixed（Phase 2 代码评审修复，2026-04-17）
- **P1**: 意图路由位置从步骤 3.5 移到步骤 1 之后（本地直投之后，P2P/Relay 之前），避免主 DID 有 endpoint 时消息被提前投递
- **P2**: daemon.py 添加 catch-all route `/ui/{path:path}` 处理 Vue Router history mode
- **S1**: Setup.vue 步骤顺序调整：先设置 Token（Step 0）再创建 Owner（Step 1）
- **S2**: Dashboard.vue 调用 `listEnclaves()` 获取 Enclave 数量
- **S3**: Messages.vue 判断 content 类型后再 slice

### Compliance
- 符合 qntm WG Authority Constraints 最小互操作面
- evaluated_constraint_hash 约束集内容寻址
- monotonic narrowing 委托链单调收窄验证

### Interop Enhancements（2026-04-18）

- **verify_token 成功响应增加 `checks` 字段**：5 步验证结果结构化返回（status / signature / validity / chain / scope_is_subset / permission），支持跨验证器对比
- **Track A interop fixtures**：生成 `interop/fixtures/agentnexus/happy-path.json` + `scope-expansion.json`，包含 JCS 规范化、Ed25519 签名、委托链完整信息
- **PR #17 提交到 APS**：`aeoess/agent-passport-system` interop fixtures 目录

---

## [0.9.6] - 2026-04-11

### Added

#### Governance Attestation 集成（ADR-014）
- **GovernanceClient 抽象基类**：可插拔的治理服务客户端
- **MolTrustClient**：集成 MolTrust `validate-capabilities` API
- **APSClient**：集成 APS `validate-capabilities` API
- **GovernanceRegistry**：管理多客户端，聚合验证结果
- **GovernanceAttestation**：治理认证数据结构，支持 JWS 签名验证
- **等级映射**：MolTrust/APS passport_grade → AgentNexus L1-L4（参考）

#### Web of Trust 信任网络
- **TrustGraph**：信任图结构，BFS 路径搜索
- **TrustEdge**：信任边，score 0.0-1.0
- **TrustPath**：信任路径，自动计算衍生分数
- **TrustGraphStore**：SQLite 持久化信任边
- **信任衰减**：每跳衰减 15%，支持配置

#### Reputation 声誉系统
- **ReputationScore**：三维信任评分 `base_score + behavior_delta + attestation_bonus`
- **BehaviorScorer**：基于成功率、响应速度、活跃度的行为评分
- **ReputationStore**：SQLite 持久化交互记录和声誉缓存
- **OATR 格式导出**：`to_oatr_format()` 输出标准格式

#### Daemon 模块化重构
- **daemon.py**：从 2000+ 行精简为 70 行入口文件
- **_auth.py**：Token 管理 + DID 绑定
- **_config.py**：节点配置 + Relay 通信
- **_models.py**：所有 Pydantic 请求模型
- **routers/**：8 个功能模块（agents/messages/handshake/adapters/push/enclave/governance）

#### Storage 扩展
- **新增表**：`trust_edges`, `interactions`, `reputation_cache`, `governance_attestations`
- **CRUD 函数**：`add_trust_edge`, `record_interaction`, `save_governance_attestation` 等

#### Daemon 端点（8 个新增）
- `POST /governance/validate` — 调用外部治理服务
- `GET /governance/attestations/{did}` — 获取缓存的治理认证
- `GET /trust/paths` — 查找信任路径
- `POST /trust/edge` — 添加信任边（带权限验证）
- `GET /trust/edges/{did}` — 列出信任边
- `DELETE /trust/edge` — 删除信任边
- `POST /interactions` — 记录交互
- `GET /interactions/{did}` — 获取交互历史
- `GET /reputation/{did}` — 获取声誉评分

#### MCP 工具（4 个新增，33 个总计）
- `validate_governance` — 验证 Agent 能力
- `find_trust_path` — 查找信任路径
- `add_trust` — 添加信任边
- `get_reputation` — 获取声誉评分

### Fixed

#### ADR-014 设计评审问题修复（2026-04-11）
- **P1**：spend_limit 作为参考信息，实际额度由 ADR-004 定义
- **P2**：base_score 设计依据（非线性映射 + 行为空间）
- **P3**：与 ADR-004 关系明确，Gatekeeper 决策优先级
- **S1**：JWS 过期强制检查，防止重放攻击
- **S2**：信任边添加权限验证（from_did owner only）

#### ADR-014 代码评审问题修复（2026-04-12）
- **P1**：`verify_attestation` 添加 `require_jws` 参数，防止无签名 attestation 绕过验证
- **P2**：`DELETE /trust/edge` 添加鉴权 + from_did 归属验证
- **S1**：JWS 验证添加 `logger.warning` 区分错误类型
- **S2**：提供 `set_governance_registry()` / `reset_governance_registry()` 供测试注入
- **S6**：`POST /interactions` 添加鉴权 + 本地 Agent 验证
- **S7**：`GET /reputation/{did}` 从数据库查实际 L 级，移除外部参数

### Tests
- 352 passed, 8 skipped
- 新增测试文件：test_v09_reputation.py, test_v09_web_of_trust.py, test_governance.py, test_governance_api.py
- 新增测试用例：trust_graph 持久化（6个）、reputation compute/get_all（6个）、governance API（9个）
- 线上测试新增：Governance、Trust Edge、Interaction、Reputation 端点（12个），总计 45 个线上测试

### Fixed
- 修复 aiosqlite 使用错误：`async with await _get_db()` → `async with _get_db()`（reputation.py, trust_graph.py）

---

## [0.9.5] - 2026-04-09

### Added

#### Enclave 协作架构（ADR-013）
- **Enclave 项目组**：创建/管理多 Agent 团队，绑定角色（architect/developer/reviewer）和权限（r/rw/admin）
- **VaultBackend 抽象接口**：可插拔文档存储，支持 `get/put/list/history/delete`
- **LocalVaultBackend**：基于 SQLite 的零配置 Vault，版本自增，历史 append-only，`action` 字段区分 create/update/delete
- **GitVaultBackend**：基于 Git 仓库的 Vault，commit hash 作为版本号，支持 `git push/pull` 跨机器同步，路径遍历防护
- **Playbook 引擎**：`PlaybookEngine` 自动推进阶段（start → _start_stage → on_stage_completed/on_stage_rejected）
- **Playbook 消息拦截**：`router._intercept_playbook_state()` 拦截 `state_notify`，按 `task_id` 反查 stage_execution，自动推进或回退
- **Daemon 端点（15 个）**：Enclave CRUD + Member 管理 + Vault 操作（`{key:path}` 多级 key）+ Playbook Run
- **MCP 工具（6 个，27→33）**：`create_enclave` / `vault_get` / `vault_put` / `vault_list` / `run_playbook` / `get_run_status`
- **权限检查**：`_check_vault_permission`（r/rw/admin 三级）
- **Storage 表（7 张）**：enclaves / enclave_members / playbooks / playbook_runs / stage_executions / enclave_vault / enclave_vault_history + 7 个索引

#### SDK Enclave API
- `nexus.create_enclave(name, members)` — 创建 Enclave
- `nexus.enclaves.list()` — 列出参与的 Enclave
- `enclave.vault.put/get/list/history/delete` — Vault 操作
- `enclave.run_playbook(playbook)` — 启动 Playbook
- `enclave.get_run(run_id)` — 获取运行状态
- `nexus.vault_get/vault_put` — 直接访问 Vault
- 新增模块：`agentnexus/enclave.py`（EnclaveManager, VaultProxy, PlaybookRunProxy）

### Tests
- 299 passed（新增 34 Enclave + 8 GitVaultBackend + SDK 测试）

---

## [0.9.0-dev] - 2026-04-09

> ⚠️ 开发中：代码评审有条件通过，2 个安全阻塞项待修复。

### Added

#### L3 注册层（SIP REGISTER 风格）
- **Push 注册端点**：`POST /push/register`（callback_url + callback_type + TTL）
- **TTL 续约**：`POST /push/refresh`
- **主动注销**：`DELETE /push/{did}`
- **状态查询**：`GET /push/{did}`（公开，不返回 callback_secret）
- **callback_secret**：注册时 Daemon 生成 HMAC 签名密钥，仅返回一次
- **TTL 自动清理**：后台任务每 5 分钟清理过期注册
- **多 callback 支持**：同一 DID 可注册多个回调（多平台 session）

#### L5 推送层（APNs 风格精准推送）
- **消息到达即推送**：`route_message()` 存储后 `asyncio.create_task(_push_notify(...))`
- **HMAC-SHA256 签名**：`X-Nexus-Signature: sha256=<HMAC>` + `X-Nexus-Timestamp` 防重放
- **推送超时 5s**：失败静默，消息已安全存储
- **通知 preview**：body 包含消息前 200 字符预览

#### MCP/SDK 自动注册
- **MCP**：`main()` 启动自动注册 → 后台续约 → `finally` 注销
- **SDK**：`register_push()` → `expires//2` 动态续约 → `close()` 自动注销

### Known Issues
- 🔴 DID-Token 绑定未实现（daemon.py:1135 TODO）
- 🔴 SSRF 防护空实现（daemon.py:1142 pass）
- 🟡 MCP 续约间隔硬编码 30min（应为 expires//2）
- 🟡 test_push.py 10 个测试全部 ERROR（async fixture 兼容性）

---

## [0.8.0] - 2026-04-08

**发布地址：**
- GitHub Release: https://github.com/kevinkaylie/AgentNexus/releases/tag/v0.8.0
- PyPI: https://pypi.org/project/agentnexus-sdk/0.8.0/

### Added

#### ACP 协议栈完整实现
- **L0-L2 + L4 + L6-L8 全部就位**，形成完整的 Agent 通信协议
- **九层协议栈**：Identity → Security → Access → Transport → Messaging → Collaboration → Adapters

#### ADR-009: DID Method Handler 注册表架构重构
- **DIDMethodHandler 抽象基类**：可插拔的 DID 方法处理器
- **5 个 Handler 实现**：AgentNexus / AgentLegacy / Key / Web / Meeet
- **注册函数**：`register_daemon_handlers()` / `register_relay_handlers()` / `reset_handlers()`

#### ADR-010: 平台适配器架构
- **PlatformAdapter 抽象基类**：`inbound()` / `outbound()` / `skill_manifest()`
- **AdapterRegistry**：`register()` / `unregister()` / `get()` / `list()`
- **OpenClawAdapter**：4 种 action（invoke_skill / query_status / send_message / get_profile）
- **WebhookAdapter**：HMAC-SHA256 签名验证
- **Skill 注册端点**：`GET/POST/DELETE /skills`

#### ADR-011: Discussion Protocol
- **四种消息类型**：discussion_start / discussion_reply / discussion_vote / discussion_conclude
- **DiscussionStateMachine**：open → voting → concluded 状态机
- **投票模式**：majority / unanimous / leader_decides
- **EmergencyController**：紧急熔断 + callback 机制

#### ADR-012: MCP 协作层工具（27 个工具）
- **Action Layer（4 个）**：propose_task / claim_task / sync_resource / notify_state
- **Discussion（4 个）**：start_discussion / reply_discussion / vote_discussion / conclude_discussion
- **Emergency + Skill（2 个）**：emergency_halt / list_skills

#### Python SDK (agentnexus-sdk) — PyPI 发布
```bash
pip install agentnexus-sdk
```
- **核心 API**：`connect()` / `send()` / `verify()` / `certify()`
- **Action Layer**：`propose_task()` / `claim_task()` / `sync_resource()` / `notify_state()`
- **Discussion**：`start_discussion()` / `reply()` / `vote()` / `conclude()`
- **同步包装器**：`agentnexus.sync.connect()`

#### did:meeet 桥接（ADR-008）
- **管理员注册**：`POST /meeet/admin/register`（Bootstrap + 已注册 admin 验证）
- **Agent 注册**：`POST /meeet/register` / `POST /meeet/batch-register`
- **x402 score 映射**：MEEET reputation → x402 score（已提取到 utils.py 共享）

#### 跨平台 MCP 配置文档
- Kiro CLI / Claude Code / OpenClaw / Claude Desktop / Cursor 配置示例
- 多 Agent 协作流程示例

### Fixed

#### 阻塞性问题
- **B1**: `/meeet/admin/register` 签名验证漏洞 — Bootstrap 模式 + 已注册 admin 验证
- **B2**: DID Document 缺少 `assertionMethod` 字段 — 补全 W3C 规范字段

#### 建议性问题
- **S1**: `_compute_x402_score()` 重复代码 — 提取到 `utils.py` 共享
- **S2**: `TaskStatus.EXPIRED` 写法混乱 — 明确定义 enum
- **S3**: `@context` 顺序错误 — DID Core 在前
- **S4**: dict content 序列化后无标记 — 新增 `content_encoding` 字段
- **CP1**: `start_discussion` 广播失败无日志 — 添加 `logger.warning`
- **CP2**: product.md 补充跨平台协作场景
- **CP3**: 缺少测试覆盖 — 新增 `tests/test_mcp_collaboration.py`（10 个测试）

### Technical
- 测试结果：157 passed, 3 skipped ✅
- 版本号：agentnexus 0.8.0, agentnexus-sdk 0.8.0

---

## [0.8.1] - 2026-04-04

### Changed

#### DID Resolver 架构重构（ADR-009）
- **DIDMethodHandler 注册表模式**：DIDResolver 改为注册表路由，不再硬编码 if/elif 链
- **新增 `agent_net/common/did_methods/` 目录**：
  - `base.py` — DIDMethodHandler 抽象基类
  - `utils.py` — 共用工具方法（build_did_document、extract_ed25519_key_from_doc）
  - `agentnexus.py` — AgentNexusHandler（纯密码学解析）
  - `agent_legacy.py` — AgentLegacyHandler（需 db_path，仅 Daemon 注册）
  - `key.py` — KeyHandler（纯密码学解析）
  - `web.py` — WebHandler（HTTPS 端点获取）
  - `meeet.py` — MeeetHandler（需 redis_client，仅 Relay 注册）
- **注册函数**：
  - `register_daemon_handlers(db_path)` — Daemon 侧注册
  - `register_relay_handlers(redis_client)` — Relay 侧注册
  - `reset_handlers()` — 测试隔离
- **向后兼容**：所有调用方（Gatekeeper、RuntimeVerifier、SDK）零改动

### Technical
- 测试结果：144 passed, 3 skipped ✅

---

## [0.8.0] - 2026-04-04

### Added

#### SDK (agentnexus-sdk)
- **Python SDK 包** — `agentnexus-sdk/` 独立包，3 行代码接入 AgentNexus 网络
  - `pip install agentnexus-sdk` (PyPI 发布准备)
  - 依赖：`aiohttp` + `pydantic`（最小依赖）
- **核心 API**：
  - `agentnexus.connect(name, caps)` — 注册新身份
  - `agentnexus.connect(did=...)` — 复用已注册身份
  - `nexus.send(to_did, content)` — 发送消息
  - `nexus.verify(did)` — 信任查询
  - `nexus.certify(target_did, claim, evidence)` — 签发认证
  - `@nexus.on_message` — 消息回调
- **Action Layer**（ADR-007）：
  - `nexus.propose_task()` — 发布任务
  - `nexus.claim_task()` — 认领任务
  - `nexus.sync_resource()` — 同步资源
  - `nexus.notify_state()` — 汇报状态
  - 四种回调：`on_task_propose` / `on_task_claim` / `on_resource_sync` / `on_state_notify`
- **同步包装器**：`agentnexus.sync.connect()` — 非异步场景支持
- **自动发现**：
  - Daemon URL 发现：显式参数 > 环境变量 > 默认 localhost:8765
  - Token 发现：显式参数 > 环境变量 > 用户目录 > 项目目录
  - Token 权限检查（非 0600 时警告）

#### Daemon 扩展
- **Token 写入用户目录**：`~/.agentnexus/daemon_token.txt`（跨项目共享）
- **messages 表扩展**：新增 `message_type` / `protocol` 列
- **`/messages/send` 支持 Action Layer**：`content: Union[str, dict]`
- **`fetch_inbox()` 返回新字段**：`message_type` / `protocol`

#### did:meeet 桥接（ADR-008）
- **`POST /meeet/admin/register`**：平台管理员注册
- **`POST /meeet/register`**：单个 MEEET Agent 注册
- **`POST /meeet/batch-register`**：批量注册（最大 100 条）
- **`GET /meeet/status`**：映射状态统计
- **`GET /resolve/did:meeet:...`**：解析 MEEET DID → did:agentnexus
- **x402 score 映射**：MEEET reputation → x402 score
- **Mock Solana API**：`MEEET_SOLANA_RPC_URL` 环境变量

### Changed
- `agent_net/router.py`：路由支持 `message_type` / `protocol` 参数
- `agent_net/storage.py`：`store_message()` 新增可选参数
- `agent_net/relay/server.py`：`/resolve/{did}` 支持 `did:meeet` 方法

### Technical
- SDK 包结构：`src/agentnexus/{__init__,client,actions,models,discovery,exceptions,sync}.py`
- 测试结果：144 passed, 3 skipped ✅

---

## [0.6.0] - 2026-03-26

### Added
- **W3C DID Method `did:agentnexus`** — new DID format based on Ed25519 multikey encoding
  - Format: `did:agentnexus:z<base58btc(0xED01 || pubkey)>`
  - New `DIDGenerator.create_agentnexus()` in `common/did.py`
  - `DIDResolver` supports resolution of `did:agentnexus` by pure crypto (no network)
- **W3C DID Document** — `_build_did_document()` now outputs full W3C-compliant DID Doc
  - `Ed25519VerificationKey2018` verification method with multibase encoding
  - `X25519KeyAgreementKey2019` derived from Ed25519 pubkey for ECDH
  - Optional `service` array (relay endpoint + agent endpoint)
- **`GET /resolve/{did}` on Relay** — returns W3C DID Document + source metadata
  - Checks local registry → PeerDirectory → pure crypto (did:agentnexus)
- **`GET /resolve/{did}` on Daemon** — returns W3C DID Document with service endpoints
  - Derives pubkey from stored private key for local agents
  - Falls back to relay for non-local DIDs
- **Key export/import** — `agent_net/common/keystore.py`
  - `export_agent()`: argon2id KDF + AES-256-GCM (nacl SecretBox) encryption
  - `import_agent()`: decrypt and restore DID + private key + profile + certifications
  - Daemon endpoints: `GET /agents/{did}/export`, `POST /agents/import` (token required)
  - CLI: `python main.py agent export <did> --output <file> --password <pw>`
  - CLI: `python main.py agent import <file> --password <pw>`
  - MCP tools: `export_agent` (16th) and `import_agent` (17th)
- **`build_services_from_profile()`** helper in `common/did.py` for DID Doc service extraction
- **44 new tests** in `tests/test_did_resolution.py` (new endpoint tests + async fixes) and `tests/test_keystore.py` (tk01–tk05)

### Changed
- `RegisterRequest` now defaults to `did_format="agentnexus"` — new agents get `did:agentnexus:z...` DIDs
  - `did_format="agent"` preserves legacy `did:agent:<hex>` behavior
  - `public_key_hex` saved to profile for DID resolution without private key
- Relay version: `0.3.0` → `0.6.0`
- Daemon version: `0.5.0` → `0.6.0`
- `requirements.txt`: added `httpx>=0.27.0` (for `did:web` resolution)

### Technical
- Total tests: 124 (up from 80 in v0.5)
- All existing tests pass unchanged

---

## [0.5.0] - 2026-03-26

### Added
- **Session management** — messages now carry `session_id` and `reply_to` fields for conversation continuity
  - Auto-generated `sess_<uuid>` when omitted; explicit session ID preserved when provided
  - New endpoint `GET /messages/session/{session_id}` for full conversation history
  - New MCP tool `get_session` (13th tool) for retrieving conversation context
- **Multi-party certification system** — NexusProfile supports third-party signed certifications
  - `certifications` top-level field (outside signed `content`, independently verifiable)
  - Each certification: `{issuer, issuer_pubkey, claim, evidence, issued_at, signature}`
  - New helper functions: `create_certification()`, `verify_certification()` in `profile.py`
  - New endpoint `POST /agents/{did}/certify` for issuing certifications (token required)
  - New endpoint `GET /agents/{did}/certifications` for listing certifications
  - New MCP tools: `certify_agent` (14th) and `get_certifications` (15th)
  - `GET /agents/{did}/profile` now includes certifications in response
- **Giskard integration proposal** — merged into `docs/contracts/giskard-ca-certification.md`
- 12 new tests (tv01–tv12) in `tests/test_v05.py`

### Changed
- `SendMessageRequest` extended with `session_id` and `reply_to` fields
- `store_message()` and `fetch_inbox()` support session_id and reply_to
- `router.route_message()` passes session_id and reply_to through all routing paths
- Total MCP tools: 12 → 15
- Total test count: 68 → 80

## [0.4.0] - 2025-03-25

### Added
- **Relay announce signature verification** — `/announce` now requires Ed25519 signed payload with TOFU pubkey binding and timestamp replay protection (60s skew)
- **Federation announce signature verification** — `/federation/announce` verifies NexusProfile signature + DID consistency
- **Federation join callback verification** — `/federation/join` verifies the joining relay is reachable via health check callback
- **Rate limiting** — per-DID/per-URL rate limiter (30 req/min) on all three relay write endpoints
- **Daemon signed announce** — `_announce_to_relay()` now signs payloads with agent's Ed25519 private key
- New helper functions: `canonical_announce()`, `verify_signed_payload()` in `profile.py`
- 12 new security tests (ts01–ts12) in `test_federation.py`

### Changed
- `AnnounceRequest` model extended with `pubkey`, `timestamp`, `signature` fields
- 7 existing federation tests updated to send signed payloads
- Total test count: 56 → 68

## [0.3.0] - 2025-03-24

### Added
- **Redis storage for Relay** — migrated from in-memory registry to Redis with TTL-based auto-expiry
- **Docker deployment** — `Dockerfile`, `docker-compose.yml` (redis + relay + nginx + certbot)
- **TLS/SSL support** — nginx reverse proxy with Let's Encrypt auto-renewal via `scripts/init-ssl.sh`
- Cloud seed relay deployment documentation

### Changed
- Relay `_registry` replaced with Redis `SETEX`/`SET` operations
- `_create_redis()` factory function for test isolation (monkeypatch with fakeredis)

## [0.2.0] - 2025-03-23

### Added
- **MCP Agent binding** — `node mcp --name` / `--did` for automatic agent registration and identity binding
- `whoami` MCP tool (12th tool)
- 7 MCP binding tests (tm01–tm07)
- **14 new test cases** covering relay fault tolerance, NexusProfile signing sync, token auth edge cases

### Fixed
- Remove `register_local_session` from agent register handler
- Replace Unicode checkmark with ASCII to avoid GBK encoding errors on Windows
- Add `--entrypoint certbot` to `init-ssl.sh` certbot run command

## [0.1.0] - 2025-03-22

### Added
- **Federated Relay network** — `/federation/join`, `/federation/announce`, 1-hop proxy lookup
- **NexusProfile signed cards** — Ed25519 signed identity cards with `schema_version` in content
- **Token authentication** — `data/daemon_token.txt` Bearer token for all daemon write endpoints
- **Gatekeeper access control** — Public / Ask / Private modes with blacklist/whitelist
- **Four-step handshake** — Ed25519 challenge-response + X25519 ECDH + AES-256-GCM
- **Smart message routing** — local → P2P → relay → offline fallback
- **STUN NAT traversal** — UDP-based public IP:Port discovery
- **MCP stdio server** — 11 tools for AI agent integration
- **SQLite storage** — agents, messages, contacts, pending_requests tables
- **CLI** — `main.py` unified entry point for relay/node/agent/test commands

## [0.0.1] - 2025-03-21

### Added
- Initial commit: project structure, DID generator, basic agent profiles
- The Alien Antenna Duck mascot is born!
