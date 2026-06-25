# 项目现状速览

> **唯一状态源**：本文档是 AgentNexus 项目版本、功能状态、关键数字的唯一权威来源。
> 其他文档（CLAUDE.md、architecture.md、AGENTS.md 等）引用本文档，不重复维护状态。
> 最后更新：2026-06-23
> 
> **本轮修复：**
> - 8 个 sync fixture → `@pytest_asyncio.fixture` async（消除 `asyncio.run()` / `new_event_loop()` 重复创建 ProactorEventLoop）
> - 4 个 `yield TestClient(app)` → `with TestClient(app) as client: yield client`（上下文管理确保 httpx 连接池释放）
> - `init_db()` 连接合并 6→1（`init_*_tables(db)` 必传参数，连接由调用者管理）
> - 7 个测试文件 DB 隔离（`tmp_path` 重定向，不碰默认 `data/agent_net.db`）
> - 5 个测试文件 `asyncio.run()` → `@pytest.mark.asyncio async def`（`test_cases.py` / `test_gatekeeper.py` / `test_v10_intent_route.py` / `test_v10_messages.py` / `test_v10_owner.py`），共用 pytest-asyncio 单一 event loop
> 
> **结果：544 passed, 8 skipped, 1 warning**（`I/O operation on closed pipe`，非 aiosqlite/资源泄漏类）

## 一句话总结

AgentNexus 是 AI Agent 的通信基础设施与团队协作编排底座——去中心化身份 + 联邦发现 + 端到端加密 + 智能路由 + 协作协议 + Enclave/Playbook + Context Budget + 治理信任。v1.0.0 收敛为”团队协作开发者预览”：Orchestration SDK + 常驻秘书 + Enclave/Playbook + 基础 Web 入口。Coding Coordination V1 后端闭环、SDK facade、CLI demo/runtime-mock、Dashboard detail、Quickstart、Delivery Manifest closure 已完成。Objective Loop V1.1 核心模块（storage/backend/runner/loop engine/gateway）已开发完成，进入 daemon 集成和 quickstart 阶段。

## 关键数字

| 指标 | 值 |
|------|-----|
| 当前版本 | v1.0.0→v1.1 过渡中（团队协作开发者预览已发布；Coding Coordination V1 release closure 完成；Objective Loop V1.1 P0-1~P0-5 核心模块开发完成，待 daemon 集成与 quickstart） |
| 测试数 | 全量：544 passed, 8 skipped, 1 warning（`I/O operation on closed pipe`，非资源泄漏类）；前端 build 通过 |
| MCP 工具数 | 37 |
| Python | 3.10+ |
| 存储 | SQLite (aiosqlite) |
| 加密 | Ed25519 + X25519 + AES-256-GCM |

## 版本状态

| 版本 | 状态 | 核心内容 |
|------|------|---------|
| v0.1–v0.7 | ✅ 已发布 | DID 身份、握手加密、Relay 联邦、Gatekeeper、智能路由、MCP、信任体系 |
| v0.8.0 | ✅ 已发布 | Python SDK、Action Layer 协作、Discussion 投票、紧急熔断、平台适配器 |
| v0.9.0 | ✅ 已发布 | Push 注册推送、STUN 穿透 |
| v0.9.5 | ✅ 已发布 | Enclave 项目组、VaultBackend、Playbook 自动编排 |
| v0.9.6 | ✅ 已发布 | Governance Attestation、Web of Trust、信任衰减 |
| v1.0 Phase 1 | ✅ 已实现 | 个人主 DID (1.0-04)、消息中心 (1.0-06)、Capability Token (1.0-08)、委托链收窄 (1.0-10) |
| v1.0.0 | 🚧 开发中 | 团队协作开发者预览：意图路由、鉴权矩阵 v3、Orchestration SDK、Secretary Phase B、Dashboard/Setup 主链路已完成；代码评审阻塞项已解决 |
| Coding Coordination V1 | ✅ 已实现 | 以 coding 场景验证 protocol-agnostic trusted coordination loop；PlaybookRun 作为运行态状态源，closure 自动生成 Delivery Manifest 并写入 Enclave Vault；63 个 coordination/manifest 回归测试通过 |
| Coding Coordination V1 Release Closure | ✅ 已完成 | SDK facade、CLI demo、runtime-mock、Dashboard detail、Quickstart 已全部完成；新开发者可通过 SDK 示例或 CLI 命令跑通完整 coding coordination 闭环 |
| v1.1 | 🚧 开发中 | Objective Loop（L0 本机）：P0-1~P0-6 全部完成（含 Execution API、Daemon 集成、Quickstart）；Runner poll loop 验证中；L1/L2 后移到 v1.2+ |
| v1.5 | 📋 规划中 | 企业版 MVP：per-agent token、Admin API、审计日志、多租户、RBAC、统一策略引擎、强授权与可信交付 |

## 模块状态

| 模块 | 状态 | 说明 |
|------|------|------|
| DID 身份（did:agentnexus） | ✅ | Ed25519 multikey，自证明 |
| 四步握手 + AES-256-GCM | ✅ | 端到端加密通信 |
| Node Daemon（:8765） | ✅ | Gatekeeper + 智能路由 + SQLite |
| Relay Server（:9000） | ✅ | 联邦互联，1 跳查询 |
| MCP Server（37 个工具） | ✅ | Claude Desktop / Cursor / Claude Code |
| L1-L4 信任体系 | ✅ | 多 CA + RuntimeVerifier + 信任衰减 |
| Python SDK | ✅ | async/sync 双模式，Core Messaging + Orchestration SDK |
| Action Layer + Discussion | ✅ | 任务委派/认领/投票/结论 |
| Push 注册 + 推送 | ✅ | SIP REGISTER 风格 + HMAC 签名 |
| Enclave + Playbook | ✅ | 项目组 + 角色绑定 + 自动编排 |
| Governance + Trust Network | ✅ | MolTrust/APS + Web of Trust + 声誉 |
| 个人主 DID + 消息中心 | ✅ | Owner DID 管理 N 个 Agent |
| Capability Token | ✅ | Ed25519 签名 + 约束哈希 + 委托链收窄 |
| 意图路由 | ✅ | 主 DID → 子 Agent 自动转发 |
| Consistency Level | ✅ L0, 🚧 L1 | 决策一致性分级 |
| 秘书编排（Phase A） | ✅ | D-SEC-01 Worker Registry + D-SEC-02 Intake/Dispatch 已实现 |
| 秘书编排（Phase B） | ✅ | 已完成开发：Presence、Adapter Contract、Message Envelope、Delivery Manifest、Context Budget & Handoff、Owner abort、SDK/CLI 原生入口 |
| Coding Coordination V1 | ✅ | 将 Secretary 升级为 Coordination Controller：PlaybookRun 作为运行态状态源，closure 自动生成 Delivery Manifest 并写入 Enclave Vault；63 个 coordination/manifest 回归测试通过 |
| Coding Coordination V1 Release Closure | ✅ | SDK facade、CLI demo、runtime-mock、Dashboard detail、Quickstart 已全部完成；新开发者可通过 SDK 示例或 CLI 命令跑通完整 coding coordination 闭环 |
| Objective Loop V1.1 P0-1~P0-5 | ✅ | objective_executions 表 + CRUD、ExecutionBackend/Protocol + LocalCLIBackend、local_runner YAML + stage 执行、Loop Engine next_action() 状态机、Secretary DecisionGate handler；新增 56 个测试 |
| Objective Loop Daemon 集成 | ✅ | Execution API endpoints（POST/GET executions、runner poll loop）、execution 集成测试已完成 |
| Web 仪表盘 | ✅ | Setup 六步闭环（Token→Owner→Secretary→Workers→Dispatch→Result）、Dashboard 聚合视图、Agents worker_type/presence、Enclaves Run 详情/manifest/context_budget 已实现并构建同步 |
| 鉴权矩阵 v3 | ✅ | 已实现 v1.0 阶段性边界：token + actor DID 校验、读接口私有化、/deliver soft-enforce 签名验证；per-agent token 和 hard-enforce 后移 |
| did:meeet 桥接 | 🚧 部分实现 | Relay/DIDResolver handler、映射端点、x402_score metadata 已实现；真实 Solana API 与外部评分口径待确认 |

## v1.1 发布范围

| 类别 | 内容 |
|------|------|
| 已完成 | P0-1 objective_executions 存储、P0-2 ExecutionBackend + LocalCLIBackend、P0-3 local_runner + YAML config + worker 匹配、P0-4 Loop Engine next_action() 状态机、P0-5 Secretary DecisionGate handler、P0-6 Execution API endpoints + daemon 集成 + Quickstart；56 个新测试 |
| 进行中 | Runner auto-discover poll loop 验证、Dashboard execution/decision gate 视图 |
| 后移到 v1.2 | LAN Worker、Relay Worker、artifact transport 跨网络 |
| 后移到 v1.3+ | Productization：Tauri 桌面壳、系统托盘通知、Adapter marketplace |

## 活跃外部合作

| 合作方 | 内容 | 状态 |
|--------|------|------|
| Giskard | CA 认证签发 | 等待对方提供 pubkey hex |
| OATR | 信任注册表 + JWT Attestation | 对接中 |
| QNTM WG | DID Resolution 规范 | ✅ 已完成 |
| MEEET | did:meeet 互操作 | 代码部分完成，外部端点待确认 |
| APS (aeoess) | agent-governance-vocabulary crosswalk | ✅ PR 已合并 |
| A2A | Consistency Level Proposal | 📋 草稿待提交 |

## 当前待办与风险

> 详见 `docs/wip.md`

1. **v1.0.0 发布收口**：同步 README、quickstart、SDK 示例和 CHANGELOG，固定端到端操作路径。
2. **D-SEC-04 角色选择与回退策略**：改进 dispatch 选人逻辑（按 worker 能力评分排序、离线降级、fallback）。
3. **D-SEC-06 超时/重试/fallback**：stage 超时检测、retry_count 自动重试、失败后自动 fallback 到下一个匹配 worker。
4. **严格 JCS 实现**（S5）：当前为确定性 JSON 序列化，跨语言互操作需升级为 RFC 8785；不阻塞 v1.0.0 开发者预览，后移到 v1.5 安全收紧。

## 新人最小阅读清单

1. **[AGENTS.md](../AGENTS.md)** — 文档索引
2. **[docs/architecture.md](architecture.md)** — 架构全貌
3. **[CLAUDE.md](../CLAUDE.md)** — 开发约定
4. **[docs/quickstart.md](quickstart.md)** — 动手跑一遍
5. **本文档** — 当前进度
