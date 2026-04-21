# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

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
- **CP2**: scenarios.md 缺少场景 5 — 补充跨平台协作场景
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
- **Giskard integration proposal** — `docs/giskard-proposal.md` with technical alignment plan
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
