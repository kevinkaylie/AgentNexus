# tests - CLAUDE.md

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

## 测试运行

```bash
python main.py test          # 全部测试（80+ collected）
python -m pytest tests/test_objective_*.py -v   # Objective Loop 系列
python -m pytest tests/test_local_cli_backend.py -v   # Backend 系列
```
