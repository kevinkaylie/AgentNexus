# AgentNexus 需求文档

> 本文件按版本组织产品需求。每个功能项包含用户故事和验收标准。
> 随版本推进逐步填充，已实现的标记 ✅，未开始的标记 ⬚。

---

## v0.7.x — 基础设施层 ✅

> 已完成，需求回溯记录。

### R-0701: DID 身份体系

**用户故事：** 作为 Agent 开发者，我希望每个 Agent 自动获得全局唯一的去中心化标识符，以便在不依赖中心平台的情况下标识身份。

**验收标准：**
- ✅ 支持 `did:agent`（旧格式）、`did:agentnexus`（默认）、`did:web`（Relay）三种格式
- ✅ `DIDResolver` 支持 4 种方法解析（agentnexus/agent/key/web）
- ✅ 符合 WG DID Resolution v1.0 规范
- ✅ 相关 ADR：[ADR-001](adr/001-did-format-selection.md)

### R-0702: 端到端加密通信

**用户故事：** 作为 Agent，我希望与其他 Agent 建立加密通信通道，以便消息内容不被第三方窃听。

**验收标准：**
- ✅ 四步握手协议（Ed25519 + X25519 ECDH + AES-256-GCM）
- ✅ Challenge TTL 30 秒防重放
- ✅ 每次握手生成临时 ECDH 密钥，提供前向安全
- ✅ 相关 ADR：[ADR-002](adr/002-four-step-handshake.md)

### R-0703: 访问控制

**用户故事：** 作为 Agent 节点管理者，我希望控制哪些外部 Agent 可以与我建立连接。

**验收标准：**
- ✅ public/ask/private 三模式
- ✅ 黑名单优先级最高
- ✅ ask 模式支持 PENDING 队列 + 异步审批
- ✅ 相关 ADR：[ADR-005](adr/005-gatekeeper-three-modes.md)

### R-0704: 联邦 Relay 网络

**用户故事：** 作为 Agent，我希望通过联邦 Relay 网络发现和联系不在同一局域网的其他 Agent。

**验收标准：**
- ✅ Relay 支持 announce/lookup/relay 三个核心端点
- ✅ 1 跳联邦代理查询
- ✅ Redis 存储 + TTL 自动过期
- ✅ Ed25519 签名验证 + TOFU 公钥绑定

### R-0705: 信任体系

**用户故事：** 作为 Agent，我希望能评估其他 Agent 的可信程度，以便决定是否与其交易。

**验收标准：**
- ✅ L1-L4 四级信任体系
- ✅ 多 CA 并列架构，各自独立验签
- ✅ RuntimeVerifier HTTP 端点
- ✅ 相关 ADR：[ADR-004](adr/004-multi-ca-certification.md)

### R-0706: MCP 原生支持

**用户故事：** 作为 AI 模型用户，我希望通过 MCP 协议直接使用 AgentNexus 的所有功能。

**验收标准：**
- ✅ 17 个 MCP 工具（stdio 模式）
- ✅ `--name` 自动注册绑定（幂等）
- ✅ Sidecar 架构，私钥不出 Daemon
- ✅ 相关 ADR：[ADR-003](adr/003-sidecar-architecture.md)

---

## v0.8.0 — SDK 基础 + 协作协议（Action Layer）

> 目标：3 行代码接入 + 结构化协作动作，让 Agent 不仅能聊天，还能协作。
> 核心理念：SDK 是"身份代理"，不触碰外部平台 API Key，只负责签名、路由和存证。
> 状态复核（2026-04-27）：v0.8.0 主体已完成。剩余未勾选项分为两类：外部互操作待对方确认、或已被 v1.0/v1.1 的 Adapter Contract / did:meeet 桥接替代。

### R-0801: Python SDK 核心包

**用户故事：** 作为 Python 开发者，我希望通过 `pip install agentnexus-sdk` 安装一个轻量 SDK，用 3 行代码让我的 Agent 接入 AgentNexus 网络。

**验收标准：**
- ✅ `pip install agentnexus-sdk` 可用（PyPI 发布）
- ✅ `nexus = agentnexus.connect(name)` 一行完成：自动发现本地 Daemon → 注册 DID → 返回连接对象
- ✅ 连接对象提供 `send(to_did, content)` 发送消息
- ✅ 连接对象提供 `on_message(callback)` 接收消息回调
- ✅ 连接对象提供 `verify(did)` 查询信任等级
- ✅ 连接对象提供 `certify(target_did, claim, evidence)` 签发认证
- ✅ Daemon 未启动时给出清晰错误提示
- ✅ SDK 不持有私钥，所有签名操作委托给 Daemon（主权隔离）

### R-0802: 本地 Daemon 自动发现（零配置）

**用户故事：** 作为开发者，我希望 SDK 自动发现本地运行的 Daemon，无需手动配置地址。

**验收标准：**
- ✅ 默认检测 `localhost:8765`
- ✅ 支持环境变量 `AGENTNEXUS_DAEMON_URL` 覆盖
- ✅ 支持显式参数 `connect(daemon_url="...")` 覆盖
- ✅ 发现失败时抛出 `DaemonNotFoundError`，提示 `python main.py node start`
### R-0803: 协作协议 — Action Layer（信封模式）

**用户故事：** 作为 Agent 开发者，我希望通过标准化的动作类型与其他 Agent 协作（发布任务、认领任务、同步状态、汇报进度），而不仅仅是发送自由文本消息。

**验收标准：**
- ✅ 在现有 `send_message` 基础上扩展 `message_type` 字段（信封模式，不是独立协议层）
- ✅ 引入 `protocol: "nexus_v1"` 标识结构化消息
- ✅ 支持四种基础动作类型：
  - `task_propose` — 发布/委派任务（含任务描述、截止时间、所需能力）
  - `task_claim` — 认领/响应任务（含认领者 DID、预计完成时间）
  - `resource_sync` — 状态同步（共享 Key-Value 数据更新）
  - `state_notify` — 进度汇报（心跳/完成/报错，含进度百分比）
- ✅ 当 `message_type` 为动作类型时，`content` 字段为严谨的 JSON 结构（非自由文本）
- ✅ SDK 在接收端自动识别：自由文本消息直接交给 Agent，结构化动作进入 SDK 任务状态机
- ✅ 现有 Relay 逻辑无需大改，只负责准确送达"带特殊标记的信封"
### R-0804: 多层递归路由

**用户故事：** 作为 Agent，我希望消息路由能自动选择最优路径（本地 → 局域网 → 公网），确保数据隐私与效率。

**验收标准：**
- ✅ L1（Local）：进程间通信，数据不出机器
- ✅ L2（LAN）：局域网协作（如调用局域网内的 GPU 服务器）
- ✅ L3（Global）：通过种子 Relay 实现跨网穿透与异步邮局
- ✅ 路由层级自动降级，对 SDK 用户透明

### R-0805: 平台适配器 — OpenClaw Skill

**用户故事：** 作为 OpenClaw 用户，我希望为我的 Agent 安装一个 Skill，自动接入 AgentNexus 网络。

**验收标准：**
- ✅ OpenClaw Skill 包可安装
- ✅ 安装后 Agent 自动连接本地 Daemon 并注册 DID
- ✅ 消息双向转发（OpenClaw ↔ AgentNexus）
### R-0806: 平台适配器 — Webhook 通用桥接

**用户故事：** 作为 Dify/Coze 等平台用户，我希望通过 Webhook 将平台 Agent 接入 AgentNexus。

**验收标准：**
- ✅ Daemon 提供 Webhook 接收端点
- ✅ 平台侧配置 Webhook URL 后，消息自动转发
- ✅ 不需要外部平台的 API Key
### R-0807: DID 互操作测试（OATR）

**用户故事：** 作为 AgentNexus 开发者，我希望验证与 OATR 的 DID 互操作性。

**验收标准：**
- 📋 OATR 侧 `did:key` 能解析 AgentNexus Ed25519 公钥（外部验证项，不作为 v0.8 未完成阻塞）
- ✅ AgentNexus 侧支持 `did:key` 解析；治理 attestation/JWS 验证与 OATR snapshot 导出已在 v0.9.6 落地
- 📋 双向 DID 互操作确认并入外部互操作跟踪（APS/OATR fixtures、contracts），不再作为 v0.8 发布阻塞

### R-0809: DID 互操作 — did:meeet 解析支持

**用户故事：** 作为 x402 payer 或 AgentNexus 节点，我希望能解析 `did:meeet:agent_{uuid}` 格式的 DID，以便与 MEEET 平台上的 1020 个 Agent 互操作。

**验收标准：**
- ✅ `DIDResolver` 新增 `did:meeet` 方法分支
- ✅ `GET /resolve/did:meeet:agent_{uuid}` 通过 Relay 查询 MEEET Solana state API（当前默认 mock endpoint，真实 Solana API 端点待对方确认）
- ✅ 返回 `did:agentnexus` 格式的 DID Document（含 Ed25519 公钥）
- ✅ DID Document metadata 中包含 MEEET reputation score
- ✅ Solana API 不可达时返回 `did_not_found` 错误（不回退到未验证密钥）
- ✅ 解析结果可被 RuntimeVerifier 消费（公钥匹配 + 信任评估）
### R-0810: AgentService 端点补全

**用户故事：** 作为 x402 payer，我希望 Agent 的 DID Document 中包含标准的 `AgentService` 类型（MCP/ANPN 端点），以便发现 Agent 的可调用服务。

**验收标准：**
- 📋 DID Document 的 service 数组中新增 `AgentService` 类型（规划变更：不再作为 v0.8 必交；后移到 v1.1 外部发现/支付互操作）
- 📋 `AgentService` 包含 MCP 端点和/或 ANPN 协议端点
- 📋 `build_services_from_profile()` 当前生成 `AgentRelay` / `AgentEndpoint`，后续需要与 `AgentService` 命名统一
- ✅ Relay 的 `/.well-known/did.json` 保持 Relay service 语义不变（Relay 不是 Agent）
- 📋 Agent 的 DID Document 同时包含 Relay 地址和 Agent 自身服务（后续互操作增强）

### R-0811: did:meeet ↔ did:agentnexus 桥接（映射模式）

**用户故事：** 作为 MEEET 平台的 Agent，我希望通过映射表将 did:meeet 关联到 did:agentnexus，以便被 x402 payer 发现并发起支付。

**验收标准：**
- ✅ Relay 维护 `did:meeet → did:agentnexus` 映射表（Redis，TTL 缓存）
- ✅ MEEET agent 用 Ed25519 私钥签名 nonce 证明 did:meeet 所有权
- ✅ 复用 MEEET 的 Ed25519 公钥生成对应的 did:agentnexus（不生成新密钥对，不托管私钥）
- ✅ 批量注册接口：支持批量写入映射表
- 📋 注册到 ANPN directory / x402 payer 支付发现属于外部互操作联调，后移到外部集成跟踪

### R-0812: MEEET Trust Grade 映射

**用户故事：** 作为 x402 payer，我希望在解析 MEEET Agent 时获得其信任评分，以便评估是否发起支付。

**验收标准：**
- ✅ MEEET reputation score 作为 DID Document metadata 字段传递（`meeet_reputation_score`）
- ✅ metadata 同时包含 `x402_score` 参考分
- ✅ 短期映射表（v0.8，供 x402 参考）：

  | MEEET Reputation | x402 Score |
  |-----------------|------------|
  | 0 (NEW)         | ~10        |
  | 200 (BEGINNER)  | ~45        |
  | 500             | ~72        |
  | 850+ (EXPERT)   | ~92+       |

- ✅ 映射逻辑在 Relay/MeeetHandler 侧执行（解析 did:meeet 时计算 x402 score 并写入 metadata）
- 📋 长期映射到 `trust_score.behavior_delta` 的口径仍需与 MEEET/OATR/x402 对齐，不作为 v0.8/0.9 阻塞

### R-0808: SDK 文档与示例

**用户故事：** 作为开发者，我希望有清晰的 SDK 文档和示例代码，以便快速上手。

**验收标准：**
- ✅ SDK quickstart 文档
- ✅ 至少 2 个示例 Agent（echo bot、协作任务 demo）
- ✅ 平台适配器安装指南
- ✅ Action Layer 协议格式文档
---

## v0.8.5 — Relay Vault + Enclave 群组

> 目标：支持多 Agent 团队协作，共享内存桶 + 群组权限管理。
> 状态复核（2026-04-27）：本节的“Relay Vault + Relay 层 RBAC”路线已废弃，被 ADR-013 的 Enclave + Local/Git VaultBackend + Daemon 鉴权模型替代。不要再按 Redis Relay Vault 开发。

### R-0851: Relay Vault（共享内存桶）

**用户故事：** 作为 Agent 团队的成员，我希望有一个共享的 Key-Value 存储空间，以便团队成员按需读写项目状态，而不是全量广播上下文。

**验收标准：**
- ❌ Relay 提供 Vault API（规划变更：不在 Relay 做 Vault）
- ❌ MVP 使用 Redis 持久化模式（规划变更：改为 LocalVaultBackend / GitVaultBackend）
- ✅ 支持基于 DID 的读写权限控制（在 Daemon Enclave/Vault API 层实现）
- ✅ Vault 数据在 Daemon 重启后不丢失（SQLite LocalVaultBackend / GitVaultBackend）
- ✅ 支持按需读取（选择性记忆），不强制全量同步

### R-0852: Enclave 群组

**用户故事：** 作为项目负责人，我希望多个 Agent 能组成一个 Enclave（飞地），共享同一个 Vault 并协作完成目标。

**验收标准：**
- ✅ 支持创建 Enclave（群组），指定成员 DID 列表
- ✅ Enclave 内成员共享同一个 Vault 命名空间
- ❌ Enclave 级别的消息广播（规划变更：主链路改为 Playbook stage 分发 + Action Layer 消息，不做广播优先）
- ✅ 成员加入/退出 Enclave 需要权限验证

### R-0853: 基于 DID 的 RBAC

**用户故事：** 作为 Enclave 管理者，我希望为不同角色的 Agent 分配不同的权限，防止越权操作。

**验收标准：**
- ✅ 支持角色定义（如 architect/developer/reviewer）
- ✅ 不同角色对 Vault 的读写权限不同
- ❌ 权限检查在 Relay 层执行（规划变更：改由 Daemon Enclave/Vault API 执行）
- ✅ 权限变更需要管理者/owner DID 授权（v1.0 阶段使用 daemon token + actor DID；per-agent token 后移 v1.5）

---

## v0.9.0 — 信任传递 & 声誉 + Output Provenance + Push 注册推送

> 目标：L3 注册层 + L5 推送层 + 动态信任网络 + 输出溯源。
> 状态复核（2026-04-27）：Push、Web of Trust、声誉已经完成；Output Provenance 的原始 `trust_context` 方案被 Governance Attestation、Delivery Manifest 和未来 Signed Receipt 取代。

### R-0900: Push 注册层（L3 — SIP REGISTER 风格）

**用户故事：** 作为 Agent 进程（MCP/SDK），我希望启动时向 Daemon 注册自己的唤醒方式，以便有新消息时被主动通知，而不是轮询。

**验收标准：**
- ✅ `POST /push/register` 注册回调（callback_url + callback_type + TTL）
- ✅ `POST /push/refresh` 续约 TTL
- ✅ `DELETE /push/{did}` 主动注销
- ✅ `GET /push/{did}` 查询注册状态（公开，不返回 callback_secret）
- ✅ 注册时 Daemon 生成 `callback_secret`，仅返回一次
- ✅ TTL 过期自动清理（后台任务每 5 分钟）
- ✅ 同一 DID 可注册多个 callback（多平台 session）
- ✅ DID-Token 绑定验证（防止为他人 DID 注册回调）
- ✅ SSRF 防护（默认拒绝外部 callback_url，允许 localhost/白名单）
- ✅ 相关设计：[ADR-012 §3](adr/012-push-gateway-and-mcp-collaboration.md)

### R-0900b: Push 推送层（L5 — APNs 风格精准推送）

**用户故事：** 作为 Agent，我希望有新消息到达时被立即通知（而非等待下次轮询），以便实时响应。

**验收标准：**
- ✅ 消息存储后自动触发 Push 通知（`asyncio.create_task`）
- ✅ HMAC-SHA256 签名验证（`X-Nexus-Signature` + `X-Nexus-Timestamp`）
- ✅ 推送超时 5 秒，失败静默（消息已安全存储）
- ✅ 推送失败记录 warning 日志
- ✅ 通知 body 包含 preview（前 200 字符）
- ✅ 相关设计：[ADR-012 §4](adr/012-push-gateway-and-mcp-collaboration.md)

### R-0900c: MCP/SDK 自动注册

**用户故事：** 作为 MCP/SDK 用户，我希望 Push 注册对我完全透明——启动自动注册，关闭自动注销。

**验收标准：**
- ✅ MCP：main() 启动时自动注册，finally 中注销，后台续约
- ✅ SDK：connect 后可 register_push，close() 自动 unregister
- ✅ SDK 续约间隔为 expires//2（动态计算）
- ✅ MCP 续约间隔已改为 expires//2

### R-0901: Output Provenance（输出溯源）

**用户故事：** 作为 Agent 消息的接收方，我希望知道每条消息的"出生证"——它的内容来源于事实还是推理，以便评估可信度。

**验收标准：**
- ❌ 每条消息 payload 携带 `trust_context` 头部（规划变更：不在普通消息头里承载输出溯源）
- ❌ `trust_context` T1-T5 来源分级（规划变更：被 Governance Attestation、Delivery Manifest、Context Snapshot 和未来 Signed Receipt 替代）
- ✅ 证据链能力以 Delivery Manifest / Artifact Ref / Governance Attestation 形式落地
- 📋 跨系统可验证输出收据后移到 v1.5 Signed Delivery Manifest / Decision Receipt

### R-0902: Web of Trust 信任传递

**用户故事：** 作为 Agent，我希望通过信任链间接信任未直接交互过的 Agent。

**验收标准：**
- ✅ A 信任 B，B 背书 C → A 对 C 有衍生信任分
- ✅ 信任路径发现：给定两个 DID，找到信任链
- ✅ 信任衰减：长期无交互 → trust_score 缓慢下降

### R-0903: 交互声誉系统

**用户故事：** 作为 Agent 网络的参与者，我希望 Agent 的信任分能反映其实际行为表现。

**验收标准：**
- ✅ trust_score 重构为 `base_score(L级) + behavior_delta + attestation_bonus`
- ✅ behavior_delta 基于交互历史（成功率、响应速度）动态加减分
- ✅ OATR 兼容输出通过 `extensions.agent-trust`，避免直接覆盖 OATR core score
- ✅ 声誉存储 & 查询 API

### R-0904: JWT Attestation 验证（OATR 完整集成）

**用户故事：** 作为 AgentNexus 节点，我希望能验证 OATR 签发的 JWT attestation。

**验收标准：**
- 🚧 `verify_jwt_attestation()` 支持 OATR compact JWT (EdDSA)：当前生产代码支持 governance JWS 验签和 `/attestations/verify`，compact JWT helper 主要在测试/契约层，完整 OATR JWT 对接待外部联调
- ✅ trust_snapshot 导出为 OATR `extensions.agent-trust` 标准格式
- 📋 Certification ↔ JWT 双向桥接：测试层有转换样例，生产 API 后移到外部互操作实现
- 📋 Claim 命名空间（`{namespace}:{claim}` 格式）：后移到多 CA/OATR 正式对接
**参考：** [OATR 接口契约](contracts/oatr-jwt-attestation.md)

---

## v1.0.0 — 团队协作开发者预览

> 策略：v1.0.0 不再以完整桌面产品为边界，而是收敛为“团队协作开发者预览”。
> 必交范围是 Orchestration SDK、常驻秘书、Enclave/Playbook、Context Budget、Delivery Manifest、基础 Web 入口和鉴权矩阵 v3。
> Tauri 桌面壳、系统托盘通知、CLI Launcher 自动拉起、per-agent token、hard-enforce `/deliver`、Strict JCS 后移到 v1.1/v1.5。

### R-1000: v1.0.0 发布边界

**用户故事：** 作为开发者，我希望用 SDK 或本地 Web 入口快速跑通 Owner + Secretary + Worker 团队协作链路，而不需要先等待完整桌面应用或企业安全能力。

**验收标准：**
- ✅ Owner DID 可管理多个子 Agent
- ✅ Orchestration SDK 覆盖 Owner / Team / Secretary / Run / Worker Runtime 主链路
- ⬚ Web Dashboard 提供基础入口，可查看 Owner、Agent、消息、Enclave、Run 状态
- ⬚ Setup 向导可完成 Owner、Secretary、Worker 的注册与绑定闭环
- ✅ Secretary Phase B 可稳定完成 dispatch -> stage execution -> delivery manifest -> result callback
- ✅ Context Snapshot / Checkpoint / Artifact Ref 成为阶段交接默认方式
- ✅ 鉴权矩阵 v3 的 v1.0 阶段性边界落地：token + actor DID 校验、读接口私有化、/deliver soft-enforce

### R-1001: A2A Capability Token Envelope

**用户故事：** 作为 Enclave 的 owner，我希望为成员 Agent 签发结构化的 capability token，以便该 Agent 在跨 Enclave 协作时能向对方证明自己持有特定权限，而不需要对方信任我的 Enclave 网关。

**验收标准：**
- ✅ Capability Token 采用 Ed25519 + 确定性 JSON 签名；严格 RFC 8785 JCS 后移到 v1.5
- ✅ Token 结构包含签名信封、skill binding、约束集、委托链引用、过期+撤销端点
- ✅ Enclave 的 `role → permissions → scope` 链映射为 token 的 constraint set
- ✅ `POST /capability-tokens/issue` 签发 capability token
- ✅ `POST /capability-tokens/{id}/verify` 验证 capability token
- ✅ Token 过期时间必填，撤销端点必填（均不可省略）
- ✅ 相关设计：ADR-014 §与 A2A Capability Token Envelope 的关系

### R-1002: Skill 版本绑定（后移 v1.1）

**用户故事：** 作为 capability token 的签发者，我希望指定 token 覆盖的 skill 版本范围，以便在 skill 升级时控制授权是否自动延续。

**验收标准：**
- 📋 支持三种绑定策略：`strict`（仅指定版本）、`semver`（兼容升级）、`capability`（版本无关，默认）
- ✅ v1.0.0 保留默认 `capability` binding：scope 如 `data:read` 覆盖任何读数据的 skill，不论版本
- 📋 可选 version pinning：`data:read@v1` 仅覆盖 v1
- ✅ Playbook stage 的 `role` 字段作为 skill binding 的上层映射

### R-1003: 跨 Enclave Token 互验

**用户故事：** 作为 Enclave A 的成员，我希望验证来自 Enclave B 签发的 capability token，以便在无共享网关的情况下确认对方 Agent 的权限。

**验收标准：**
- ✅ 验证方仅需 issuer 的公钥（通过 DID 解析获取），无需访问 issuer 的 Enclave
- ✅ 验证包含：签名校验 + 过期检查 + 委托链完整性（hash 比对）
- ✅ 验证失败时返回具体原因（签名无效 / 已过期 / 链断裂 / 已撤销）
- ✅ 约束集（constraint set）由 issuer 定义和评估，验证方不解释约束语义

### R-1004: Web Dashboard 基础入口

**用户故事：** 作为个人或团队 owner，我希望通过 `localhost:8765/ui` 查看 Agent、Worker、消息、Intake、Enclave、Run 和基础信任状态，以便不只依赖 CLI/SDK 调试团队协作流程。

**设计：** [Dashboard / Setup v1.0 收口设计](design/design-dashboard-setup-v1.0.md)

**验收标准：**
- ⬚ Dashboard 展示 Agent 数、Worker presence 汇总、最近 Intake、活跃 Run 和未读消息
- ⬚ Agents 页面支持查看 Owner 下子 Agent、capabilities、worker_type、presence
- ⬚ Messages 页面支持查看 Owner 聚合消息和单 Agent 消息流
- ⬚ Enclaves 页面支持查看成员、Vault 文档、Playbook Run 和 Stage 状态
- ⬚ Run 详情展示 intake、selected_workers、stage_executions、manifest_ref、context_budget、blocked/rejected/aborted 状态
- ⬚ TrustNetwork 页面可保留占位或基础信任表；完整信任网络可视化后移，不阻塞 v1.0.0 闭环
- ⬚ Web 前端构建产物随 Daemon 静态挂载，本地访问可直接打开 `/ui`

### R-1005: Agent 接入向导

**用户故事：** 作为新用户，我希望按向导完成 Owner、Secretary、Worker 的注册和绑定，并拿到 MCP / SDK / OpenClaw / Webhook 的接入命令。

**设计：** [Dashboard / Setup v1.0 收口设计](design/design-dashboard-setup-v1.0.md)

**验收标准：**
- ⬚ 首次进入时可设置 daemon token 并创建 Owner DID
- ⬚ 支持生成 MCP、SDK、OpenClaw、Webhook 接入命令
- ⬚ 支持轮询新 Agent 注册，并绑定到 Owner DID
- ⬚ 支持注册 Secretary 子 Agent，并展示其代表 Owner 的 actor 身份
- ⬚ 支持最小 Worker 团队配置，用于后续 Secretary dispatch
- ⬚ 支持从 Setup 发起一次 Secretary dispatch，并跳转 Run 详情页

### R-1006: Secretary Orchestration Phase B

**用户故事：** 作为 owner，我希望把一个任务交给常驻 Secretary，由它选择团队成员、创建项目组、推进 Playbook、收集产物并在失败时给出可接管状态。

**状态：** ✅ 已完成开发候选（2026-04-29）。`resume / skip`、自动 CLI Launcher、签名交付包和 hard-enforce `/deliver` 不属于 v1.0.0 必交。

**验收标准：**
- ✅ Worker Registry 返回 `available / busy / offline / blocked / needs_human` presence
- ✅ Adapter Contract 将 OpenClaw / Webhook / SDK Agent / CLI Worker 转为统一 intake 请求
- ✅ Message Envelope v1 统一携带 `message_id / session_id / run_id / stage_name / actor_did / schema_version`
- ✅ 阶段交接默认使用 Context Snapshot + Artifact Ref，不传完整聊天历史
- ✅ 每个阶段完成时生成 Delivery Manifest 和 Handoff Checkpoint
- ✅ 失败、拒绝、blocked 可见，并支持 `on_reject` fallback 或 Owner `abort` 接管；自动超时重分配后移
- ✅ 最终交付使用 Final Delivery Manifest，包含 `run_id / status / summary / manifest_ref`；对外 adapter 回传在 v1.0.0 只要求结构化字段，签名交付包后移

### R-1007: v1.0.0 后移项

以下能力不作为 v1.0.0 必交，避免阻塞开发者预览：

- 📋 Tauri 桌面壳与系统托盘通知：后移 v1.1
- 📋 CLI Launcher 自动拉起：后移 v1.1，且必须先完成独立 sidecar 安全边界
- 📋 Skill 版本精细绑定与花费限额组合：后移 v1.1
- 📋 per-agent token、Capability 强制覆盖所有操作、`/deliver` hard-enforce、Strict JCS、审计日志、签名交付包：后移 v1.5

---

## v1.5.0+ — 企业版及后续

> 需求待定义。参考 [roadmap.md](roadmap.md) v1.5-v3.0 功能列表。
