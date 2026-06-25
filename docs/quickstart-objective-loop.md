# AgentNexus Objective Loop — Quickstart

> 目标版本：v1.1 (L0 本机) | 预计时间：10 分钟

## 1. 概述

Objective Loop 是 AgentNexus v1.1 的核心能力——让本机多个 Worker（Claude Code、Codex、pytest、脚本等）在 DID 身份、产物收据和人工决策门下自动协作完成目标。

本 quickstart 带你完成：
1. 启动 Daemon
2. 运行完整 7-stage demo
3. 查看 Dashboard
4. 启动 local-runner 自动轮询

## 2. 环境要求

- Python 3.10+
- 已安装依赖：`pip install -r requirements.txt`
- 已安装 SDK：`pip install -e agentnexus-sdk`

## 3. 启动 Daemon

```bash
python main.py node start
```

输出：
```
[AgentNet] Starting Node Daemon on :8765 ...
[Node] Started. Public endpoint: ...
```

Daemon 监听 `http://127.0.0.1:8765`，提供所有 API 端点。

## 4. 运行 Objective Loop Demo

新开一个终端，运行：

```bash
python main.py node objective demo
```

这会创建一个 Owner、一个 coding.v1 session，并按顺序执行全部 7 个 stage：

```
=== Objective Loop V1.1 Demo ===
Owner:      did:agentnexus:z6Mk...
Session:    cs_xxxxxxxxxxxxxxxx
Objective:  Implement login module with email+password
Dashboard:  http://127.0.0.1:8765/ui/coordination/cs_xxxxxxxxxxxxxxxx
Stages:     clarify → design → design_review → implement → code_review → test → final

  [1/7] clarify... OK
  [2/7] design... OK
  [3/7] design_review... OK
  [4/7] implement... OK
  [5/7] code_review... OK
  [6/7] test... OK
  [7/7] final... OK

=== Demo complete ===
```

每个 stage 会创建 artifact + receipt，Loop Engine 自动判断下一步动作。

## 5. 查看 Dashboard

打开浏览器访问 Dashboard URL（demo 输出中包含），可以看到：

- **Session 详情**：Objective、Playbook、当前 stage、Owner/Controller DID
- **Next Action**：Loop Engine 实时计算的下一步动作（start_execution/poll_execution/advance/...）
- **Timeline**：所有 runtime events 的时间线
- **Artifacts**：每个 stage 的产物（RequirementSpec、DesignArtifact、...）
- **Receipts**：每个 stage 的验收收据（approved/changes_requested）
- **Executions**：所有 objective_execution 记录（status、lease、attempt）
- **Decisions**：所有 DecisionGate 记录（人工决策点）

## 6. 查询 Loop Engine 状态

```bash
# 替换 <session_id> 和 <owner_did> 为 demo 输出的值
python main.py node objective status <session_id> --actor <owner_did>
```

输出示例：
```
Session: cs_xxxxxxxxxxxxxxxx
Next action: closed
Stage: final
Reason: Final stage final approved
```

## 7. 使用 Local Runner 自动轮询

### 7.1 准备配置

```bash
cp .agentnexus/local-runner.yaml.example .agentnexus/local-runner.yaml
```

编辑 `.agentnexus/local-runner.yaml`，填入你的 owner_did 和 secretary_agent：

```yaml
daemon_url: http://127.0.0.1:8765
secretary_agent: "did:agentnexus:z6Mk..."  # 替换为你的 owner DID（demo 输出中）
owner_did: "did:agentnexus:z6Mk..."         # 同上
```

### 7.2 启动 Runner

```bash
python main.py node local-runner start
```

Runner 会：
1. 轮询 Daemon 查找 status=running 的 session
2. 对每个 session 调用 Loop Engine 获取 next_action
3. 若为 start_execution：匹配 worker → 构建 prompt → 创建 execution → 执行 → 提交 result
4. 若为 advance：自动推进到下一 stage
5. 自动处理 on_reject 回退和 DecisionGate

按 `Ctrl+C` 停止。

### 7.3 接入真实 Worker

修改 `.agentnexus/local-runner.yaml` 配置真实 CLI 工具：

```yaml
workers:
  claude_developer:
    agent_name: ClaudeDeveloper
    adapter: local_cli
    command: claude
    args: ["-p", "{prompt}"]       # {prompt} 自动替换为结构化任务描述
    roles: ["developer", "implement"]
    capabilities: ["Code", "Debug", "Implement"]

  pytest_runner:
    agent_name: TestRunner
    adapter: local_cli
    command: python
    args: ["-m", "pytest", "tests/"]
    roles: ["tester", "test"]
    capabilities: ["Test"]
```

Runner 会自动将 objective、artifact refs、constraints 和 acceptance criteria 注入 prompt 模板。

## 8. API 速查

| 端点 | 用途 |
|------|------|
| `GET /coordination/sessions?owner_did=&actor_did=&status=` | 列出 session |
| `GET /coordination/sessions/{id}` | Session 详情 |
| `GET /coordination/sessions/{id}/next-action?actor_did=` | Loop Engine 状态查询 |
| `GET /coordination/sessions/{id}/executions?actor_did=` | 列出 executions |
| `POST /coordination/executions` | 创建 execution lease |
| `PATCH /coordination/executions/{id}` | 更新 execution 状态 |
| `POST /coordination/executions/{id}/result` | 提交 execution 结果（幂等） |
| `GET /coordination/sessions/{id}/timeline` | Timeline 事件流 |
| `GET /coordination/sessions/{id}/artifacts` | 产物列表 |
| `GET /coordination/sessions/{id}/receipts` | 收据列表 |

## 9. 测试

```bash
# 运行全部 Objective Loop 测试
python -m pytest tests/test_objective_*.py tests/test_local_cli_backend.py tests/test_local_runner.py tests/test_runner_loop.py tests/test_secretary_gateway.py tests/test_execution_api.py -v

# 快速 smoke test
python -m pytest tests/test_objective_loop_engine.py -v
```

## 10. 常见问题

**Q: Demo 报 "Failed to create owner: 404"**
A: Daemon 未启动。先运行 `python main.py node start`。

**Q: local-runner 无法发现 session**
A: 检查 `.agentnexus/local-runner.yaml` 中的 `owner_did` 是否与实际 owner DID 一致；检查 daemon token 是否存在（`data/daemon_token.txt`）。

**Q: Worker 提示 "No worker for role"**
A: 检查 YAML 配置中 worker 的 `roles` 列表是否包含所需 role（developer/reviewer/tester/clarifier/designer/coordinator）。

**Q: 真实 Claude/Codex 输出无法被解析**
A: Runner 会自动重试一次（发送简化 JSON 重试 prompt）。如果仍然失败，会创建 DecisionGate 请求人工介入。确保 Worker 输出包含有效的 JSON 块。
