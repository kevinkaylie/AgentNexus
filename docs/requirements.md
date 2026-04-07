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

### R-0801: Python SDK 核心包

**用户故事：** 作为 Python 开发者，我希望通过 `pip install agentnexus-sdk` 安装一个轻量 SDK，用 3 行代码让我的 Agent 接入 AgentNexus 网络。

**验收标准：**
- ⬚ `pip install agentnexus-sdk` 可用（PyPI 发布）
- ✅ `nexus = agentnexus.connect(name)` 一行完成：自动发现本地 Daemon → 注册 DID → 返回连接对象
- ✅ 连接对象提供 `send(to_did, content)` 发送消息
- ✅ 连接对象提供 `on_message(callback)` 接收消息回调
- ✅ 连接对象提供 `verify(did)` 查询信任等级
- ✅ 连接对象提供 `certify(target_did, claim, evidence)` 签发认证
- ✅ Daemon 未启动时给出清晰错误提示
- ✅ SDK 不持有私钥，所有签名操作委托给 Daemon（主权隔离）
✅
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
- ⬚ OATR 侧 `did:key` 能解析 AgentNexus Ed25519 公钥
- ⬚ AgentNexus 侧能解析 OATR attestation 基本格式
- ⬚ 双向 DID 互操作确认

### R-0809: DID 互操作 — did:meeet 解析支持

**用户故事：** 作为 x402 payer 或 AgentNexus 节点，我希望能解析 `did:meeet:agent_{uuid}` 格式的 DID，以便与 MEEET 平台上的 1020 个 Agent 互操作。

**验收标准：**
- ✅ `DIDResolver` 新增 `did:meeet` 方法分支
- ✅ `GET /resolve/did:meeet:agent_{uuid}` 通过 Relay 查询 MEEET Solana state API
- ✅ 返回 `did:agentnexus` 格式的 DID Document（含 Ed25519 公钥）
- ✅ DID Document metadata 中包含 MEEET reputation score
- ✅ Solana API 不可达时返回 `did_not_found` 错误（不回退到未验证密钥）
- ✅ 解析结果可被 RuntimeVerifier 消费（公钥匹配 + 信任评估）
### R-0810: AgentService 端点补全

**用户故事：** 作为 x402 payer，我希望 Agent 的 DID Document 中包含标准的 `AgentService` 类型（MCP/ANPN 端点），以便发现 Agent 的可调用服务。

**验收标准：**
- ⬚ DID Document 的 service 数组中新增 `AgentService` 类型（区别于现有的 `AgentRelayService`）
- ⬚ `AgentService` 包含 MCP 端点和/或 ANPN 协议端点
- ⬚ `build_services_from_profile()` 支持生成 `AgentService` 条目
- ⬚ Relay 的 `/.well-known/did.json` 保持 `AgentRelayService` 不变（Relay 不是 Agent）
- ⬚ Agent 的 DID Document 同时包含 `AgentRelayService`（Relay 地址）和 `AgentService`（Agent 自身服务）

### R-0811: did:meeet ↔ did:agentnexus 桥接（映射模式）

**用户故事：** 作为 MEEET 平台的 Agent，我希望通过映射表将 did:meeet 关联到 did:agentnexus，以便被 x402 payer 发现并发起支付。

**验收标准：**
- ⬚ Relay 维护 `did:meeet → did:agentnexus` 映射表（Redis 持久化）
- ⬚ MEEET agent 用 Ed25519 私钥签名 nonce 证明 did:meeet 所有权
- ⬚ 复用 MEEET 的 Ed25519 公钥生成对应的 did:agentnexus（不生成新密钥对，不托管私钥）
- ⬚ 批量注册接口：支持 1020 个 Agent 批量写入映射表 + 注册到 ANPN directory
- ⬚ x402 payer 通过 did:agentnexus 发现 Agent 并发起支付

### R-0812: MEEET Trust Grade 映射

**用户故事：** 作为 x402 payer，我希望在解析 MEEET Agent 时获得其信任评分，以便评估是否发起支付。

**验收标准：**
- ⬚ MEEET reputation score 作为 DID Document metadata 字段传递（`meeet_reputation_score`）
- ⬚ x402 可直接从 metadata 读取 reputation score
- ⬚ 短期映射表（v0.8，供 x402 参考）：

  | MEEET Reputation | x402 Score |
  |-----------------|------------|
  | 0 (NEW)         | ~10        |
  | 200 (BEGINNER)  | ~45        |
  | 500             | ~72        |
  | 850+ (EXPERT)   | ~92+       |

- ⬚ 映射逻辑在 Relay 侧执行（解析 did:meeet 时计算 x402 score 并写入 metadata）
- ⬚ 长期（v0.9）：reputation 映射到 trust_score 的 `behavior_delta` 分量，与 L 级信任体系解耦

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

### R-0851: Relay Vault（共享内存桶）

**用户故事：** 作为 Agent 团队的成员，我希望有一个共享的 Key-Value 存储空间，以便团队成员按需读写项目状态，而不是全量广播上下文。

**验收标准：**
- ⬚ Relay 提供 Vault API（CRUD Key-Value）
- ⬚ MVP 使用 Redis 持久化模式（独立 DB，关闭自动过期）
- ⬚ 支持基于 DID 的读写权限控制
- ⬚ Vault 数据在 Relay 重启后不丢失
- ⬚ 支持按需读取（选择性记忆），不强制全量同步

### R-0852: Enclave 群组

**用户故事：** 作为项目负责人，我希望多个 Agent 能组成一个 Enclave（飞地），共享同一个 Vault 并协作完成目标。

**验收标准：**
- ⬚ 支持创建 Enclave（群组），指定成员 DID 列表
- ⬚ Enclave 内成员共享同一个 Vault 命名空间
- ⬚ 支持 Enclave 级别的消息广播
- ⬚ 成员加入/退出 Enclave 需要权限验证

### R-0853: 基于 DID 的 RBAC

**用户故事：** 作为 Enclave 管理者，我希望为不同角色的 Agent 分配不同的权限，防止越权操作。

**验收标准：**
- ⬚ 支持角色定义（如 architect/developer/reviewer）
- ⬚ 不同角色对 Vault 的读写权限不同
- ⬚ 权限检查在 Relay 层执行
- ⬚ 权限变更需要管理者 DID 签名授权

---

## v0.9.0 — 信任传递 & 声誉 + Output Provenance

> 目标：动态信任网络 + 输出溯源，对抗 AI 幻觉。

### R-0901: Output Provenance（输出溯源）

**用户故事：** 作为 Agent 消息的接收方，我希望知道每条消息的"出生证"——它的内容来源于事实还是推理，以便评估可信度。

**验收标准：**
- ⬚ 每条消息 payload 携带 `trust_context` 头部（即时信任）
- ⬚ `trust_context` 包含来源分级：T1（原始事实/数据库/官方文件）→ T5（纯模型推理/幻觉风险）
- ⬚ `trust_context` 包含证据链（evidence_chain）：引用的数据源 DID 或 URL
- ⬚ Relay 统计 Agent 产生的 T1~T5 比例，沉淀为 Profile 中的"可靠性权重"

### R-0902: Web of Trust 信任传递

**用户故事：** 作为 Agent，我希望通过信任链间接信任未直接交互过的 Agent。

**验收标准：**
- ⬚ A 信任 B，B 背书 C → A 对 C 有衍生信任分
- ⬚ 信任路径发现：给定两个 DID，找到信任链
- ⬚ 信任衰减：长期无交互 → trust_score 缓慢下降

### R-0903: 交互声誉系统

**用户故事：** 作为 Agent 网络的参与者，我希望 Agent 的信任分能反映其实际行为表现。

**验收标准：**
- ⬚ trust_score 重构为 `base_score(L级) + behavior_delta + attestation_bonus`
- ⬚ behavior_delta 基于交互历史（成功率、响应速度）动态加减分
- ⬚ 兼容 OATR 0-100 连续评分体系
- ⬚ 声誉存储 & 查询 API

### R-0904: JWT Attestation 验证（OATR 完整集成）

**用户故事：** 作为 AgentNexus 节点，我希望能验证 OATR 签发的 JWT attestation。

**验收标准：**
- ⬚ `verify_jwt_attestation()` 支持 OATR compact JWT (EdDSA)
- ⬚ trust_snapshot 导出为 OATR 标准格式
- ⬚ Certification ↔ JWT 双向桥接
- ⬚ Claim 命名空间（`{namespace}:{claim}` 格式）
**参考：** [OATR 接口契约](contracts/oatr-jwt-attestation.md)

---

## v1.0.0 — 桌面应用 & Web UI

> 需求待定义。参考 [roadmap.md](roadmap.md) v1.0 功能列表。

---

## v1.5.0+ — 企业版及后续

> 需求待定义。参考 [roadmap.md](roadmap.md) v1.5-v3.0 功能列表。
