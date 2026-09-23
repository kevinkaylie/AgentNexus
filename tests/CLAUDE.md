# tests - CLAUDE.md

## 全量回归硬规则（改动后必须执行）

**任何**对 `agent_net/` 或 `tests/` 的改动，都必须跑**全量**测试并通过基线门禁；只跑"改动相关的测试"会漏掉跨模块覆盖型回归——例如新增模块中的函数与既有函数在 `agent_net.storage` 星号导入链上**同名互相覆盖**时，新增测试全绿而既有测试成批失败（2026-09-20 的 `store_message` 冲突造成 22 个既有测试 `TypeError`）。

```bash
$env:PYTHONIOENCODING='utf-8'   # 必须：否则中文跳过原因按 GBK 落盘，门禁无法逐字匹配（中文 Windows）
python -m pytest tests/ -q -p no:cacheprovider --tb=no -rs > .pytest_full_report.txt 2>&1
python scripts/check_full_suite.py --input .pytest_full_report.txt
# 退出码：0=通过（无未登记失败/跳过）1=回归 2=基线需维护 3=报告编码受损（须以 UTF-8 重跑）
```

纪律：

- 失败集合必须与 `tests/full_suite_baseline.json` **逐条一致**；出现未登记失败即按**回归**处理，**先修复**，不得直接刷新基线。
- 基线只登记**可归因于运行环境**的失败并写明原因；**当前环境性失败为空**。
- 提交与评审请求必须附上汇总行（`N passed, M failed …`）。

### 环境依赖用例：能力探针 + 显式跳过（2026-09-21 评审 S4 收窄后）

此前把受限沙箱下必然失败的 25 个用例登记进基线当作"环境性失败"。评审在**不受限**环境跑出
679 passed / 0 failed，证明这些用例本身是好的——登记成失败等于让基线长期携带一批实际能过的
条目，也会掩盖真实回归。现已改为**能力探针**：

`tests/conftest.py` 的 `pytest_collection_modifyitems` 会探测两项能力，缺失时把相关文件整体
**显式 skip**（原因写在 skip reason 里）：

| 探针 | 覆盖文件 | 缺失原因 |
|---|---|---|
| `asyncio.create_subprocess_exec` 可用 | `test_local_cli_backend.py`、`test_local_runner.py`、`test_runner_loop.py`、`test_vault_git.py` | 受限环境禁止创建子进程 |
| 工作区外临时目录/家目录可读写 | `test_relay_did_web.py` | 受限环境不可读写 |

`scripts/check_full_suite.py` 相应按**原因逐字匹配**区分"环境跳过"与"无理由跳过"：
环境跳过必须与 `ENVIRONMENT_DEPENDENT_FILES` 的原因字符串一致，其余跳过必须落在基线
`counts.skipped` 以内；通过数下限 = 基线通过数 − 环境跳过数。于是正常环境与受限环境**都应 exit 0**。

> 探针必须用被测代码**实际使用**的 API：沙箱下 `asyncio.create_subprocess_exec` 抛
> `PermissionError`，而同步 `subprocess.run` 可能仍可用——只探后者会漏判（实测过一次）。

另：pytest 的 tmpdir 以 `mode 0o700` 建目录，在受限沙箱下建完即不可扫描，会让**所有**使用
`tmp_path` 的测试报 `WinError 5`。`tests/conftest.py` 因此加入**探针式** `tmp_path` 兜底
（仅当探针失败时覆盖，正常 CI 行为不变）。该兜底**不覆盖** `tempfile`。

## 测试用例说明
对应规格书中的5个验收测试用例，使用 pytest + asyncio。

## 运行方式
```bash
# 推荐：通过主入口运行
python main.py test

# 直接pytest
python -m pytest tests/ -v

# 不依赖pytest的简单runner
python tests/test_cases.py
```

## test_cases.py — 网络与路由用例

| 用例 | 测试点 | 关键断言 |
|------|--------|----------|
| tc01 | 本地自动注册 | `list_local_agents` 返回正确DID和name |
| tc02 | 内网点对点通信 | method=local，延迟<5ms |
| tc03 | NAT穿透降级 | P2P/Relay不可达时 method=offline |
| tc04 | 离线消息投递 | B离线时消息入库，上线后fetch_inbox取到且不重复 |
| tc05 | 语义寻址 | search_agents('Bank') 精确匹配能力标签 |

## test_handshake.py — 加密握手用例

| 用例 | 测试点 | 关键断言 |
|------|--------|----------|
| tc-h01 | 完整握手 | 双方 session key 相等且为 32 字节 |
| tc-h02 | 身份伪造 | verify_key 与签名不匹配时抛 `PermissionError` |
| tc-h03 | 会话加解密 | A 加密，B 用相同 session key 解密还原明文 |
| tc-h04 | 密钥唯一性 | 每次握手 X25519 临时密钥不同，session key 不重复 |
| tc-h05 | 过期 Challenge | timestamp 超过 TTL(30s) 时抛 `ValueError: expired` |
| tc-h06 | 状态机保护 | 无 pending challenge 时 `verify_response` 抛 `RuntimeError` |
| tc-h07 | 状态机保护 | 握手未完成时 `get_session_key` 抛 `RuntimeError` |

## test_gatekeeper.py — 访问控制用例

| 用例 | 测试点 | 关键断言 |
|------|--------|----------|
| tg01 | public 模式全部放行 | `GateDecision.ALLOW` |
| tg02 | private 模式拦截未知DID | `GateDecision.DENY` |
| tg03 | private 模式白名单放行 | `GateDecision.ALLOW` |
| tg04 | 黑名单优先（public模式下也拒绝）| `GateDecision.DENY` |
| tg05 | ask 模式未知DID写入pending队列 | `GateDecision.PENDING`，DB有记录 |
| tg06 | resolve allow 唤醒握手协程 | Future返回 `"allow"`，DB status=allow |
| tg07 | resolve deny 中断握手 | Future返回 `"deny"`，DB status=deny |
| tg08 | 重复 resolve 返回 False | 第二次 `resolve()` 返回 `False` |
| tg09 | list_pending 仅返回未处理记录 | 已 resolve 的不出现在列表 |
| tg10 | 白/黑名单文件持久化 | 新实例可读到前一实例写入的条目 |

## 测试隔离
- `use_test_db` fixture 通过 `monkeypatch` 替换 `storage.DB_PATH` 为临时目录
- `isolated` fixture 同时重定向 gatekeeper 的 `CONFIG_DIR`、`WHITELIST_PATH`、`BLACKLIST_PATH`、`MODE_PATH`
- 每个用例使用独立SQLite文件，互不干扰
- tc03 使用不可达地址模拟NAT穿透失败，无需真实网络
- 握手测试和 Gatekeeper 测试均为纯内存/纯本地，无网络依赖

## 新增测试规范
- 文件名以 `test_` 开头
- 每个用例对应一个 `test_t<prefix><nn>_<描述>()` 函数（Objective Loop 测试使用 `test_obj_*` 前缀）
- 异步测试使用 `@pytest.mark.asyncio` + `async def`，禁止使用 `asyncio.run()` 包裹（每次 run() 创建独立 ProactorEventLoop，导致 aiosqlite worker thread 泄漏）
- fixture 使用 `@pytest_asyncio.fixture`（async fixture），共享 pytest-asyncio 管理的单一 event loop
- fixture `isolated` 同时 monkeypatch DB 路径和 gatekeeper 配置目录，保证测试隔离
- Objective Loop 测试使用 `@pytest_asyncio.fixture(autouse=True)` + `setup_db` 模式，每个测试独立 DB

## test_objective_execution_storage.py — Objective Loop 存储测试（P0-1, 12 tests）

| 用例 | 测试点 | 关键断言 |
|------|--------|----------|
| test_obj_create_execution_minimal | 最小字段创建 + 默认值 | status=pending, attempt=1 |
| test_obj_create_execution_full | 全字段创建 | lease_expires_at, metadata 正确存入 |
| test_obj_get_nonexistent | 查询不存在的执行 | 返回 None |
| test_obj_list_by_session | 按 session 过滤列表 | 返回正确数量和归属 |
| test_obj_list_by_run_and_stage | 按 run+stage 组合过滤 | 精确匹配 |
| test_obj_list_by_status | 按 status 过滤 | running/completed 分类正确 |
| test_obj_list_empty | 空列表查询 | 返回 [] |
| test_obj_update_execution | 更新 status/lease/metadata | updated_at >= created_at |
| test_obj_update_nonexistent | 更新不存在的执行 | 返回 False |
| test_obj_mark_result_completed | 标记结果完成 | artifact_id/receipt_id 写入 |
| test_obj_mark_result_idempotent_same_hash | 相同 hash 重复提交 | 返回既有记录 |
| test_obj_mark_result_idempotent_nonexistent | 不存在执行标记结果 | 抛出 ValueError |

## test_local_cli_backend.py — ExecutionBackend + LocalCLIBackend 测试（P0-2, 10 tests）

| 用例 | 测试点 | 关键断言 |
|------|--------|----------|
| test_obj_execution_handle_defaults | ExecutionHandle dataclass | 默认值正确 |
| test_obj_execution_result_fields | ExecutionResult dataclass | 字段正确 |
| test_obj_execution_result_with_human_decision | 带人工决策的 result | decision request 正确 |
| test_obj_local_cli_backend_successful_run | 成功执行 + JSON 解析 | status=completed, artifact 正确 |
| test_obj_local_cli_backend_invalid_json_retry | 无合法 JSON → blocked | status=blocked, raw_output 保留 |
| test_obj_local_cli_backend_timeout | 超时 kill | status=timed_out |
| test_obj_local_cli_backend_disallowed_command | 命令不在白名单 | status=blocked, reason 包含错误 |
| test_obj_local_cli_backend_output_truncation | 超大输出截断 | raw_output_ref 非空 |
| test_obj_local_cli_backend_constraints_from_start_execution | 参数透传 | timeout 约束生效 |
| test_obj_local_cli_backend_cancel | 取消执行 | status=cancelled |

## test_objective_loop_engine.py — Loop Engine 状态机测试（P0-4, 9 tests）

| 用例 | 测试点 | 关键断言 |
|------|--------|----------|
| test_obj_engine_next_action_start_execution | 无执行 → 启动 | action_type=start_execution |
| test_obj_engine_next_action_poll_execution | 运行中 → 轮询 | action_type=poll_execution |
| test_obj_engine_next_action_start_execution_when_timed_out | 超时 → 重试 | action_type=start_execution |
| test_obj_engine_next_action_decision_gate_on_max_retry | 超过重试上限 → 决策门 | action_type=create_decision_gate |
| test_obj_engine_next_action_advance_after_receipt | 审批通过 → 推进 | action_type=advance |
| test_obj_engine_next_action_on_reject_back | 驳回 → 回退到 on_reject stage | stage=design |
| test_obj_engine_next_action_closed | 最终 stage 审批通过 → 关闭 | action_type=closed |
| test_obj_engine_next_action_blocked_execution | 被拦截执行 → 决策门 | action_type=create_decision_gate |
| test_obj_engine_next_action_wait_pending_decision | 有待审批 → 等待 | action_type=wait |

## test_local_runner.py — Local Runner 测试（P0-3, 10 tests）

| 用例 | 测试点 | 关键断言 |
|------|--------|----------|
| test_obj_runner_load_config_basic | YAML 配置加载 | daemon_url 等字段正确 |
| test_obj_runner_load_config_workers | Workers 解析 | command/roles/capabilities 正确 |
| test_obj_runner_load_config_defaults | 默认值填充 | poll_interval_sec=2 等 |
| test_obj_runner_load_config_missing_daemon_url | 缺失 daemon_url | 抛出 ValueError |
| test_obj_runner_config_nonexistent_file | 文件不存在 | 抛出 FileNotFoundError |
| test_obj_runner_find_worker_by_role | 按 role 查找 worker | 返回正确 worker |
| test_obj_runner_find_worker_by_capability | 按 capability 查找 worker | 返回正确 worker |
| test_obj_runner_find_worker_not_found | 未找到 worker | 返回 None |
| test_obj_runner_execute_single_stage | 执行单个 stage | result.status=completed |
| test_obj_runner_execute_stage_blocked_command | 拦截危险命令 | result.status=blocked |

## test_secretary_gateway.py — Secretary DecisionGate 测试（P0-5, 3 tests）

| 用例 | 测试点 | 关键断言 |
|------|--------|----------|
| test_obj_gateway_handle_decision_gate_creates_request | destructive_command gate | 创建 decision_request, status=pending |
| test_obj_gateway_handle_decision_gate_max_retry | max_retry gate | 创建 pending decision |
| test_obj_gateway_handle_decision_gate_low_confidence | low_confidence gate | 创建 pending decision, stage 正确 |

## Code Review Profile v1 测试（2026-09-23，271 tests + 1 skip = 272 collected）

| 文件 | 用例数 | 覆盖 |
|------|--------|------|
| `test_code_review_profile.py` | 40 | §15.3 字节口径与摘要（含 CP-23 冻结向量）、`code_review.error.v1` 与 `data_policy_denied` 的 scope 分类学、信封解析、ReviewReport 5 条不变式、§15.2 翻译层、严重度映射可配置 |
| `test_code_review_store.py` | 17 | Profile 会话唯一键（含 coordinator_id）、epoch 单调、执行绑定、交付幂等/冲突/纠正、Profile 回执、消息 inbox、角色授权、强制能力注册 |
| `test_code_review_http_contract.py` | 69 | **HTTP 契约矩阵 + R3/R4/R5 回归**（复审建议）：**行是数据**，执行器发真实 HTTP 请求并对**实际响应**校验状态码、`code`/`scope`、**真正通过冻结 schema**。矩阵覆盖缺头/重复键/NaN/BOM/超限/越权/412/`Range`/认证优先等；另含**消息幂等四条规则**、**R3-1 未知与歧义 session 无副作用**、**R3-2 租约过期 + "读取后提交前"取消/换 epoch/过 deadline/改绑 Attempt/改绑 Coordinator + 等待写锁期间过期 + 空值围栏（无真值守卫）与其对照组**（确定性注入）、**R3-3 两个真实并发同 key 请求**（同/不同投影）、**R3-4 排版与追踪字段变化按重放、业务变化 409**、`retention_until_text` 落库、`assignment_epoch` 严格整数；**R5-1 空 Coordinator/空 worker 在绑定入口即被拒（422）、既有空绑定在入口 409、事务内比较无真值守卫（负例回退报 `DID NOT RAISE`）** |
| `test_code_review_api.py` | 41 | **B1–B6 + 复审 R2-1～R2-4**：凭据绑定（未登记/未知凭据/sender 冒充/issuer 自报/worker 伪造 accepted）；读取资源授权（跨 session、过期 410、当事人仍受 session 限制）；契约七字段 DTO、retention 严格解析与**原样回显**、ArtifactRef 过冻结 schema、TransportAck 三字段/MessageView 四字段；**R2-1 幂等失败可恢复**；**R2-2 分配绑定**；**R2-3 冲突无副作用**；**R2-4 validator/publisher 在真实 role_grant 下可用**；§15.5 fail-closed；CP-24 |
| `test_code_review_delivery.py` | 10 | 输出适配器翻译（CP-09/CP-17）、§15.6 单事务 CAS（状态/租约/deadline/输入清单）、交付入口 Profile 路径 |
| `test_code_review_q3_harness.py` | 12 (+1 skip) | q3 行为用例：HCZJ→Profile 转换（两种原 outcome 同语义、原义保留、溯源）、呈现规则与发布前拒绝（422）、交付重放幂等；发布重放半场属 HCZJ 边界，显式 skip |
| `test_code_review_provider_adapter.py` | 15 | **可插拔性证明** + **B7/R2-5 回归**：注册表与 schema 自动识别、第二个 provider（ACME）走同一管线、未知 provider/schema → `unsupported_contract`、厂商无关不变式不可绕过；malformed finding/缺口条目 → `invalid_output`、未登记 schema → `unsupported_contract`；**显式 null 与字段缺失都不得当作空集合** |
| `test_code_review_evidence_checklist.py` | 53 | **T1–T6 收口裁判的负例验证**：清单/模板自洽；摘要/长度/占位符/必填/覆盖/声明与实际不一致等按预期失败；**B9 + R2-6 拒绝事实样例级校验**（真正运行 `error.schema.json`；主体角色/方法+端点/错误码必须与场景匹配）；**B10 可移植性**；**S3 采集 pin**（改写 pin、复核记录缺失/时序错误/未声明重跑被拒） |
| `test_code_review_cp_matrix.py` | 14 | **CP-01～26 执行记录的机械守卫**：覆盖映射与 `fixtures/cp-matrix.json` 的 CP 集合完全一致（增删 CP 会强制补映射）；映射的 node id 必须真实存在（测试改名立刻变红）；blocked 必须给 owner+限制、partial 必须给限制、verified 必须有测试；渲染器对参数化用例按前缀归并取最坏结果，blocked/partial 永不被写成"通过"；已提交记录必须覆盖全部 26 项、限制小节与声明一致、并声明 0 个证据失败；**门禁关闭期间 `compatibility.json` 允许列表必须全空**（防提前放行） |

> **CP 执行记录**（自动生成，可重跑）：
> ```bash
> python scripts/run_cp_matrix.py --list-tests
> python scripts/run_cp_matrix.py --input <pytest -rA 报告> --date <YYYY-MM-DD>
> ```
> 当前记录：`specs/profiles/code-review/v1/fixtures/binding/cp-execution-record-2026-09-23.md`（15 通过 / 6 部分 / 5 本仓无证据 / 0 失败；blocked 逐条写明 owner，不得读成通过）。

> **写新测试的纪律**：Profile 接口的 wire 行为一律写进 `test_code_review_http_contract.py` 的
> `MATRIX`（加一行），不要再写散落的 `assert resp.json()["field"]`——前三轮评审的同类缺陷
> （B3/R2-2/R2-3 与遗留 P2）都是这么漏掉的。

**q3 执行记录**（自动生成，可重跑）：

```bash
python -m pytest tests/test_code_review_q3_harness.py -q -p no:cacheprovider
python scripts/run_q3_harness.py > specs/profiles/code-review/v1/fixtures/binding/q3-execution-record-<date>.md
```

当前记录：`specs/profiles/code-review/v1/fixtures/binding/q3-execution-record-2026-09-20.md`（真实摘要、实际渲染文本、重放前后计数、A–D 拒绝阶段）。

**T1–T6 收口裁判**（改 `bindings/evidence/` 或 `tools/check_evidence.py` 时必须重跑）：

```bash
python specs/profiles/code-review/v1/tools/check_evidence.py   # 0=清单自洽 1=虚假关闭/不一致/提前放行 2=清单损坏
python specs/profiles/code-review/v1/tools/validate.py         # 已内置上一步
```

纪律：T1–T6 全开放是**合法**状态，校验通过不代表任何 T 项已关闭。要关闭一项，必须回填 `bindings/evidence/received/T{n}.json` 并把清单中的 `items[].status` 改到与实际一致——**不得改声明迁就实际**。本地合成证据（`docs/evidence/l0-*`）在清单中一律登记为 `non_closing`，`production=false` 标签不得改写。

## 测试运行

```bash
python main.py test          # 全部测试（80+ collected）
python -m pytest tests/test_objective_*.py -v   # Objective Loop 系列
python -m pytest tests/test_local_cli_backend.py -v   # Backend 系列
python -m pytest tests/test_code_review_*.py -v       # Code Review Profile 系列
```
