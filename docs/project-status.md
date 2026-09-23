# 项目现状速览

> 2026-09-23 [第六轮复审](reviews/2026-09-23-l0-r6-review.md)：空 Coordinator 绑定在写入、旧记录上传和提交事务三个入口均被拒绝；R5-1 **代码缺陷已关闭**，本次修复通过评审。以下第五轮结论为历史状态。T1–T6 全开放、BINDING-GATE-1 继续关闭。

> 2026-09-23 [第五轮复审](reviews/2026-09-23-l0-r5-review.md) R5-1 已修复，**待复审**（[修复记录](reviews/2026-09-22-l0-r3-fix-confirmation.md) §3.2）：空值围栏缺口的三条建议逐条落实——绑定入口拒绝空身份字段（422）、既有空绑定在入口 fail-closed（409）、事务内 Attempt/Coordinator/worker 比较**去掉全部真值守卫**（`(actual or "") != (expected or "")`）。负例证据：改回旧守卫报 `DID NOT RAISE`。**契约未改**（§1 已要求 ID 非空、§4 已要求在事务内校验 Coordinator，本次属实现未落实），规范包维持 `1.0-draft.2+semantic.14`；全量 **762 passed, 57 skipped, 0 failed, 0 errors**，门禁 exit 0。以下第三至五轮复审条目为历史结论，R4-2 已关闭。**未修**：H/messages 错误映射对齐属外部仓库（HCZJ 侧）；原 S1 仍开放。T1–T6 全开放，BINDING-GATE-1 关闭，未声明 wire conformance。

> 2026-09-23 [第五轮复审](reviews/2026-09-23-l0-r5-review.md)：R4-2 已关闭，R4-1 的正常非空改绑已修复；但空 Coordinator 绑定可写库，事务复检跳过空预期值，独立复现改绑后旧请求错误返回 201 并登记产物（R5-1/P2）。**仍需修改后复审**。以下第四轮状态为历史结论；T1–T6 全开放，BINDING-GATE-1 关闭。

> 2026-09-23 [第四轮复审](reviews/2026-09-23-l0-r4-review.md)：**需修改后复审**。R3-1/R3-3/R3-4 原问题关闭；R3-2 尚有 R4-1（提交事务遗漏 Attempt/Coordinator 比较）、R4-2（等待写锁后仍使用旧时间）两处缺口，独立复现均错误返回 201 并登记产物。以下“已修复、待复审”为历史提交方状态，以本条为准。T1–T6 与 BINDING-GATE-1 状态不变。

> 2026-09-22 第三轮复审 R3-1～R3-4 已修复，**待复审**（[修复记录](reviews/2026-09-22-l0-r3-fix-confirmation.md)）：消息入口未知/歧义 session 一律拒绝并核对受信任关联；分配有效性（含租约）在**提交事务内**复检；并发同 key 提交阶段直接 replay（不再 500）；新增 `projection.py` 按 §7 做业务投影比较。规范包 `1.0-draft.2+semantic.14`；全量 **761 passed, 57 skipped, 0 failed, 0 errors**，门禁 exit 0。**未修**：H/messages 错误映射对齐属外部仓库；原 S1 仍开放。

> 2026-09-22 消息幂等键裁决落地：**POST A/messages 必须携带 `Idempotency-Key` 且取值等于信封 `message_id`**（§1 管传输位置、§4 管取值，同一个逻辑幂等键）；四条执行规则已实现并有专项用例。`POST H/messages` 同理但 delivery 例外（`delivery_id`）。

> 2026-09-22 HTTP 契约矩阵：新增 `tests/test_code_review_http_contract.py`（行是数据 + 真实 HTTP + 冻结 schema 校验），**首次运行红 27 项**并一次抓出前三轮"字段存在但 wire 不一致"的同类问题，均已修复。见 [矩阵说明](reviews/2026-09-22-http-contract-matrix.md)。

> 2026-09-22 L0 复审修复：R2-1～R2-6 已修复，**待复审**（[修复记录](reviews/2026-09-22-l0-rereview-fix-confirmation.md)）。复审已关闭 B8/B10 的代码缺陷。**原 S1（HCZJ reviewer 归属）仍开放**，属外部仓库。

> 2026-09-21 L0 评审修复：B1–B7、B9、B10 与 S3/S4 已修复（[修复记录](reviews/2026-09-21-l0-review-fix-confirmation.md)）。测试基线按评审 S4 收窄：环境依赖用例改由能力探针显式跳过，`environmental_failures` 为空。

> 2026-09-21 L0 三方代码评审：结论为**需修改后复审，不批准**（[评审记录](reviews/2026-09-21-l0-overall-code-review.md)）；B1–B10 阻塞项，独立复现脚本与输出见 `docs/reviews/`。评审在不受限环境实测 **679 passed / 9 skipped / 0 failed**。

> 2026-09-21 T1–T6 收口准备：新增唯一收口追踪器 [closure-checklist.json](../specs/profiles/code-review/v1/bindings/evidence/closure-checklist.json)（25 条逐项证据要求，Nexus 9 / HCZJ 13 / 三方 3）与采集模板，配机械裁判 `tools/check_evidence.py`（重算原始字节摘要、拒绝虚假关闭、拒绝提前放行 `compatibility.json`，已接入 `tools/validate.py`）。本地证据包 `docs/evidence/l0-2026-09-21/` 在清单中登记为 `non_closing`，采集 pin 不再改写。**T1–T6 仍全部开放，BINDING-GATE-1 维持关闭**。

> 2026-09-21 L0 外部实现：Nexus/HCZJ 服务接口与隔离证据已提交，待代码评审。Nexus 29 通过；HCZJ 全量 4229 通过/2 跳过，最终服务测试 14 通过。生产样例、后台调度及强制能力装配仍待完成，BINDING-GATE-1 不变。见 [证据包](evidence/l0-2026-09-21/README.md)。

> L0 最新：RC2 已回应 Q1–Q3/S1–S7 并通过复核，binding 未定版、CP-01～26 行为用例未执行；T1–T6 关闭进度以收口追踪器为准。

> 2026-09-20 RC1 更新：接口契约已补齐，见 [服务契约](../specs/profiles/code-review/v1/bindings/l0-service-contract.md)，待单独评审；实施与生产证据门禁不变。

> 2026-09-20 Code Review L0：已完成 Nexus/HCZJ 源码与隔离测试确认（17/132 项通过）。T7 设计范围确认；T1–T6 尚有开放项，binding 未定版，兼容允许清单为空。详见 [跨项目确认记录](../specs/profiles/code-review/v1/bindings/external-confirmations-2026-09-20.md)。

> 2026-09-18 评审结论：Profile 1.0-draft.2 的 7 个阻塞项（P1–P7）**已全部关闭**、14 个建议项（S1–S14）已采纳，**设计评审通过**（记录见 Profile §14.10），ADR-015 已采纳。HCZJ 管业务评审、AgentNexus 管本地适配的双层权威**尚未宣告实施**；L0 wire binding 仍需单独评审，未评审前不得启动"符合本 Profile"的集成运行。

> 2026-09-18 专题增补：[Code Review Collaboration Profile v1](design/code-review-collaboration-profile-v1.md) 已编写为 1.0-draft.2，设计评审通过，实施门禁见 Profile §15.1/§15.9。对齐两侧已确认 Run 身份，提议 HCZJ 负责评审状态、AgentNexus 负责适配；本轮仅修改文档，未实现 Profile 或重新验证外部测试。

> 2026-09-07 专题增补：Code Review V1 已形成[需求与设计草案](design/design-code-review-v1.md)，待评审，AgentNexus 尚未实现自动评审流程。以下历史版本与测试数字未在本轮重新验证。

> **唯一状态源**：本文档是 AgentNexus 项目版本、功能状态、关键数字的唯一权威来源。
> 其他文档（CLAUDE.md、architecture.md、AGENTS.md 等）引用本文档，不重复维护状态。
> 最后更新：2026-06-29
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

AgentNexus 是 AI Agent 的通信基础设施与团队协作编排底座——去中心化身份 + 联邦发现 + 端到端加密 + 智能路由 + 协作协议 + Enclave/Playbook + Context Budget + 治理信任。v1.0.x 收敛为”团队协作开发者预览”：Orchestration SDK + 常驻秘书 + Enclave/Playbook + 基础 Web 入口。Coding Coordination V1 后端闭环、SDK facade、CLI demo/runtime-mock、Dashboard detail、Quickstart、Delivery Manifest closure 已完成。Objective Loop V1.1 核心模块（storage/backend/runner/loop engine/gateway）已开发完成；L0-Ready hardening 完成（worker_did 真实 DID、contract 校验、Registry reconcile、lease 恢复、loop budget、fallback chain、DecisionGate 终端路径）；新增 Agent Adapter Contract，可将 Claude Code / Codex / OpenClaw / 任意 CLI wrapper 输出归一为 `agentnexus_json_v1`；L0 真实 Worker 验收已跑通 script/pytest + Claude CLI + OpenClaw CLI 三 Worker DID 完整 Objective Loop。

## 关键数字

| 指标 | 值 |
|------|-----|
| 当前版本 | v1.0.1 developer preview → v1.1 L0-Ready 过渡中（团队协作开发者预览已发布；Coding Coordination V1 release closure 完成；Objective Loop V1.1 L0-Ready hardening + 3 Worker DID 真实本机烟测完成） |
| 测试数 | 全量：547+ passed, 8 skipped（含 Objective Loop / Adapter Contract 回归）；前端 build 通过 |
| MCP 工具数 | 37 |
| Python | 3.10+ |
| 存储 | SQLite (aiosqlite) |
| 加密 | Ed25519 + X25519 + AES-256-GCM |

## 推广状态

| 项 | 状态 | 说明 |
|----|------|------|
| 第一版推广 | ✅ 可启动 | 以 developer preview 口径推广，目标是技术反馈、协议评审和早期集成，不承诺生产级多机运行 |
| 对外主叙事 | ✅ 已收敛 | DID 身份、授权、产物交付和目标循环的多 Agent 协作底座 |
| 最短验证路径 | ✅ 已具备 | `docs/quickstart.md`、`docs/quickstart-coding-coordination.md`、`docs/quickstart-objective-loop.md` |
| L0 真实 Worker 验收 | ✅ 已完成 | `scripts/l0_ready_real_workers_demo.py` 跑通 script/pytest + Claude CLI + OpenClaw CLI：3 Worker DID、6 executions、6 artifacts、7 receipts、session completed |
| 生产级安全承诺 | 📋 后续 | per-agent token、Strict JCS、signed delivery package、hard-enforce `/deliver` 后移 |

## 版本状态

| 版本 | 状态 | 核心内容 |
|------|------|---------|
| v0.1–v0.7 | ✅ 已发布 | DID 身份、握手加密、Relay 联邦、Gatekeeper、智能路由、MCP、信任体系 |
| v0.8.0 | ✅ 已发布 | Python SDK、Action Layer 协作、Discussion 投票、紧急熔断、平台适配器 |
| v0.9.0 | ✅ 已发布 | Push 注册推送、STUN 穿透 |
| v0.9.5 | ✅ 已发布 | Enclave 项目组、VaultBackend、Playbook 自动编排 |
| v0.9.6 | ✅ 已发布 | Governance Attestation、Web of Trust、信任衰减 |
| v1.0 Phase 1 | ✅ 已实现 | 个人主 DID (1.0-04)、消息中心 (1.0-06)、Capability Token (1.0-08)、委托链收窄 (1.0-10) |
| v1.0.1 | ✅ Developer Preview | 团队协作开发者预览：意图路由、鉴权矩阵 v3、Orchestration SDK、Secretary Phase B、Dashboard/Setup 主链路已完成；代码评审阻塞项已解决 |
| Coding Coordination V1 | ✅ 已实现 | 以 coding 场景验证 protocol-agnostic trusted coordination loop；PlaybookRun 作为运行态状态源，closure 自动生成 Delivery Manifest 并写入 Enclave Vault；63 个 coordination/manifest 回归测试通过 |
| Coding Coordination V1 Release Closure | ✅ 已完成 | SDK facade、CLI demo、runtime-mock、Dashboard detail、Quickstart 已全部完成；新开发者可通过 SDK 示例或 CLI 命令跑通完整 coding coordination 闭环 |
| v1.1 | 🚧 开发中 | Objective Loop（L0 本机）：P0-1~P0-8 全部完成；Agent Adapter Contract 已加入本机 runner；真实异构 Worker 烟测完成；L1/L2 后移到 v1.2+ |
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
| Objective Loop V1.1 P0-1~P0-7 | ✅ | objective_executions 表 + CRUD、ExecutionBackend/Protocol + LocalCLIBackend、local_runner YAML + stage 执行、Loop Engine next_action() 状态机、Secretary DecisionGate handler、Agent Adapter Contract；支持 `agentnexus_json_v1` / `openclaw_json` / `json_text` / `text_artifact` 输出归一化 |
| Objective Loop Daemon 集成 | ✅ | Execution API endpoints（POST/GET executions、runner poll loop）、execution 集成测试已完成 |
| Web 仪表盘 | ✅ | Setup 六步闭环（Token→Owner→Secretary→Workers→Dispatch→Result）、Dashboard 聚合视图、Agents worker_type/presence、Enclaves Run 详情/manifest/context_budget 已实现并构建同步 |
| 鉴权矩阵 v3 | ✅ | 已实现 v1.0 阶段性边界：token + actor DID 校验、读接口私有化、/deliver soft-enforce 签名验证；per-agent token 和 hard-enforce 后移 |
| did:meeet 桥接 | 🚧 部分实现 | Relay/DIDResolver handler、映射端点、x402_score metadata 已实现；真实 Solana API 与外部评分口径待确认 |

## v1.1 发布范围

| 类别 | 内容 |
|------|------|
| 已完成 | P0-1 objective_executions 存储、P0-2 ExecutionBackend + LocalCLIBackend、P0-3 local_runner + YAML config + worker 匹配、P0-4 Loop Engine next_action() 状态机、P0-5 Secretary DecisionGate handler、P0-6 Execution API endpoints + daemon 集成 + Quickstart；P0-7 L0-Ready hardening（worker_did 真实 DID、agentnexus_json_v1 contract 校验、Worker Registry reconcile、lease 过期恢复、loop budget、fallback chain、DecisionGate 终端路径）；P0-8 Agent Adapter Contract（OpenClaw wrapper / generic JSON text / plain text artifact 输出归一化） |
| 进行中 | 推广收口：同步 quickstart / release notes / README 证据图，等待 GitHub Actions 在远端确认绿灯 |
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

1. **第一版推广收口**：同步 README、quickstart、SDK 示例、状态源和推广材料，固定端到端操作路径。
2. **D-SEC-04 角色选择与回退策略**：改进 dispatch 选人逻辑（按 worker 能力评分排序、离线降级、fallback）。
3. **D-SEC-06 超时/重试/fallback**：stage 超时检测、retry_count 自动重试、失败后自动 fallback 到下一个匹配 worker。
4. **严格 JCS 实现**（S5）：当前为确定性 JSON 序列化，跨语言互操作需升级为 RFC 8785；不阻塞 v1.0.0 开发者预览，后移到 v1.5 安全收紧。

## 新人最小阅读清单

1. **[AGENTS.md](../AGENTS.md)** — 文档索引
2. **[docs/architecture.md](architecture.md)** — 架构全貌
3. **[CLAUDE.md](../CLAUDE.md)** — 开发约定
4. **[docs/quickstart.md](quickstart.md)** — 动手跑一遍
5. **本文档** — 当前进度
