# AgentNexus Roadmap (updated 2026-03-27)

> **本文件仅本地保留，不提交 GitHub。**
> 每完成一项打 ✅，新增需求直接追加到对应版本段落末尾。

---

## 项目定位

**Agent 世界的微信** — 去中心化 Agent 通信基础设施。

```
通信是骨架，身份是血液，信任是免疫系统，支付是造血能力。
```

## 产品矩阵

```
┌─────────────────────────────────────────────────────────────┐
│                    AgentNexus 产品矩阵                       │
├──────────────────────┬──────────────────────────────────────┤
│  AgentNexus Personal │    AgentNexus Enterprise             │
│  （C端 · 个人版）      │    （B端 · 企业版）                   │
├──────────────────────┼──────────────────────────────────────┤
│ 桌面应用（一键安装）     │ 私有部署包（Docker/K8s）              │
│ Agent 仪表盘           │ Admin 管控台                        │
│ 自动发现 & SDK         │ 审计日志 & 合规报告                   │
│ 个人主 DID            │ 组织架构映射 & RBAC                   │
│ Agent 市场入口         │ SSO 集成                            │
│ 手机端管理             │ 数据防泄漏 & 内容审查                  │
│                      │ Agent 生命周期管理                    │
│                      │ SLA 监控 & 告警                      │
├──────────────────────┴──────────────────────────────────────┤
│                    共用基础设施                                │
│  DID · Relay · 握手 · Gatekeeper · RuntimeVerifier          │
│  Certification · Storage · MCP · 联邦协议                    │
└─────────────────────────────────────────────────────────────┘
```

## 商业模式

| 层级 | 模式 | 类比 |
|------|------|------|
| C端个人版 | 免费 — 获客 + 网络效应 | 微信个人版 |
| B端企业版 | 按 Agent 数 / 节点数订阅收费 | 企业微信按席位 |
| 增值服务 | 高可用 Relay 集群 / CA 认证服务 / Agent 市场抽成 | 微信支付手续费 |

---

## 版本路线图

### v0.7.0 — RuntimeVerifier ✅

核心信任层完成，137 个测试全部通过。

| # | 功能 | 状态 |
|---|------|------|
| 0.7-01 | DIDGenerator + DIDResolver（4 种方法） | ✅ 完成 |
| 0.7-02 | NexusProfile sign/verify + certifications | ✅ 完成 |
| 0.7-03 | 四步握手协议（Ed25519 + X25519 ECDH + AES-256-GCM） | ✅ 完成 |
| 0.7-04 | Gatekeeper 三模式访问控制（public/ask/private） | ✅ 完成 |
| 0.7-05 | 联邦 Relay（Redis 存储，1 跳代理，federation/*） | ✅ 完成 |
| 0.7-06 | MCP stdio server（17 个工具） | ✅ 完成 |
| 0.7-07 | 密钥导出/导入（argon2id + SecretBox） | ✅ 完成 |
| 0.7-08 | AgentNexusRuntimeVerifier（L1-L4 信任体系） | ✅ 完成 |
| 0.7-09 | 多 CA 认证架构（Giskard 兼容） | ✅ 完成 |
| 0.7-10 | POST /runtime/verify daemon 端点 | ✅ 完成 |
| 0.7-11 | did:agentnexus 方法规范文档（草稿） | ✅ 完成 |
| 0.7-12 | 公网 Relay 部署（relay.agentnexus.top） | ✅ 完成 |
| 0.7-13 | Docker + nginx + Let's Encrypt 生产部署 | ✅ 完成 |

---

### v0.7.1 — Relay did:web 支持（当前版本）✅

让 Relay 暴露自身 DID Document，支持 `did:web:relay.agentnexus.top` 解析。

| # | 功能 | 状态 |
|---|------|------|
| 0.7.1-01 | Relay 身份持久化（data/relay_identity.json） | ✅ 完成 |
| 0.7.1-02 | `GET /.well-known/did.json` 端点 | ✅ 完成 |
| 0.7.1-03 | CLI `relay start --host` 参数 | ✅ 完成 |
| 0.7.1-04 | DID Document 包含 Ed25519 + X25519 + service | ✅ 完成 |
| 0.7.1-05 | 测试用例（本地 + 线上公网） | ✅ 完成 |

---

### v0.7.6 — Protocol 规范化（与 ANP bridge 互操作）✅

采用 AiAgentKarl 提议的 semi-structured 格式，统一 lowercase 存储。

| # | 功能 | 状态 |
|---|------|------|
| 0.7.6-01 | anpn_register 存储时 normalize protocol lowercase | ✅ 完成 |
| 0.7.6-02 | anpn_lookup 查询时 normalize protocol lowercase | ✅ 完成 |
| 0.7.6-03 | 与 AiAgentKarl ANP bridge 对齐互操作方案 | ✅ 完成 |

---

### v0.8.0 — SDK & 降低门槛 + OATR Quick Path

> 目标：让开发者 3 行代码接入 AgentNexus，C 端用户不需要理解 DID。
>
> 核心理念：**我们不去调用外部平台的 API，而是外部 Agent 来调用我们。**
> 类似 MCP 模式——我们提供工具/适配器，Agent 安装后自动接入。

```
外部 Agent（OpenClaw / Dify / 自建）
  └── 安装 AgentNexus 适配器（Skill / Plugin / SDK）
        └── 适配器自动连接本地 Daemon (localhost:8765)
              └── 注册 DID → 收发消息 → 信任查询
                    不需要外部平台的 API Key
                    Agent 主动调用我们，不是我们调用它
```

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 0.8-01 | Python SDK 包（`agentnexus-sdk`） | ⬚ 未开始 | `pip install agentnexus-sdk`，封装所有 Daemon HTTP 调用 |
| 0.8-02 | `AgentNexus.connect(name)` 一行接入 | ⬚ 未开始 | 自动发现本地 Daemon → 注册 DID → 返回连接对象 |
| 0.8-03 | 本地 Agent 自动发现 | ⬚ 未开始 | Agent 启动时检测 localhost:8765，零配置注册 |
| 0.8-04 | SDK 消息收发 API | ⬚ 未开始 | `nexus.send(to_did, msg)` / `nexus.on_message(callback)` |
| 0.8-05 | SDK 信任查询 API | ⬚ 未开始 | `nexus.verify(did)` → RuntimeVerification |
| 0.8-06 | SDK 认证管理 API | ⬚ 未开始 | `nexus.certify(target_did, claim, evidence)` |
| 0.8-07 | 平台适配器：OpenClaw Skill | ⬚ 未开始 | OpenClaw Agent 安装此 Skill 即接入，消息转发到 Daemon |
| 0.8-08 | 平台适配器：Webhook 通用桥接 | ⬚ 未开始 | Dify/Coze 等平台通过 Webhook 回调接收消息 |
| 0.8-09 | SDK 文档 & 示例 | ⬚ 未开始 | quickstart、适配器安装指南、example agents |
| 0.8-10 | PyPI 发布 | ⬚ 未开始 | `pip install agentnexus-sdk` 可用 |
| 0.8-11 | Relay `/.well-known/did.json` 端点 | ✅ v0.7.1 | relay.agentnexus.top 暴露 DID Document，支持 `did:web` 解析 |
| 0.8-12 | DID 互操作测试（OATR） | ⬚ 未开始 | 验证对方 did:key 解析我们 Ed25519，我们解析对方 attestation 基本格式 |

---

### v0.9.0 — 信任传递 & 声誉 + OATR 完整集成

> 目标：动态信任网络，不仅依赖静态 cert，还纳入行为历史。
> OATR 集成：trust_snapshot 输出、JWT attestation 验证、行为评分引擎。
>
> 三维信任模型：凭证（Giskard）+ 行为（OATR）+ 身份（DID）
> ```
> Giskard  = 经济层（谁付过钱 → 凭证）
> OATR     = 声誉层（行为多好 → 评分）
> QNTM WG  = 身份层（你是谁 → DID 规范）
> AgentNexus = 基础设施（统一评估引擎）
> ```

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 0.9-01 | Web of Trust 信任传递 | ⬚ 未开始 | A 信任 B，B 背书 C → A 对 C 有衍生信任分 |
| 0.9-02 | 信任路径发现 | ⬚ 未开始 | 给定两个 DID，找到信任链 |
| 0.9-03 | 交互声誉系统 | ⬚ 未开始 | 交易成功率、响应速度 → 动态 trust_score 加减分（对应 OATR score_breakdown） |
| 0.9-04 | 声誉存储 & 查询 API | ⬚ 未开始 | SQLite 记录交互历史，daemon 暴露查询端点 |
| 0.9-05 | 信任衰减机制 | ⬚ 未开始 | 长期无交互 → trust_score 缓慢下降 |
| 0.9-06 | Giskard CA 正式集成 | ⬚ 未开始 | 对接 Giskard 线上 CA 服务，实际签发 cert |
| 0.9-07 | 支付网关消息协议 | ⬚ 未开始 | 标准化 Agent 间支付请求/确认/拒绝消息格式 |
| 0.9-08 | JWT Attestation 验证 | ⬚ 未开始 | 新增 `verify_jwt_attestation()` 支持 OATR compact JWT (EdDSA)，与 `verify_certification()` 并行 |
| 0.9-09 | trust_score 计算重构 | ⬚ 未开始 | 从 L 级机械推导改为 `base_score(L级) + behavior_delta + attestation_bonus`，兼容 OATR 0-100 连续评分 |
| 0.9-10 | trust_snapshot 导出 | ⬚ 未开始 | `RuntimeVerification.to_oatr_snapshot()` → 输出 OATR `extensions.agent-trust` 标准格式 |
| 0.9-11 | Relay `/.well-known/agent.json` | ⬚ 未开始 | OATR identity 注册入口（identity.did + public_key + oatr_issuer_id） |
| 0.9-12 | Claim 命名空间 | ⬚ 未开始 | cert claim 改为 `"{namespace}:{claim}"` 格式（如 `giskard:payment_verified`），防多 CA claim 冲突 |
| 0.9-13 | Certification ↔ JWT 桥接 | ⬚ 未开始 | AgentNexus cert 封装为 compact JWT / OATR JWT 解析为内部 cert，双向转换 |

---

### v1.0.0 — 桌面应用 & Web UI

> 目标：C 端用户双击安装，打开浏览器就能管理 Agent。

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 1.0-01 | Web 仪表盘（localhost:8765/ui） | ⬚ 未开始 | 我的 Agent 列表、状态、消息、信任分一览 |
| 1.0-02 | 桌面应用打包（Tauri） | ⬚ 未开始 | Windows/macOS/Linux 一键安装包（< 50MB） |
| 1.0-03 | Agent 接入向导 | ⬚ 未开始 | UI 引导：选平台 → 显示适配器安装命令/二维码 → Agent 侧安装后自动注册 |
| 1.0-04 | 个人主 DID | ⬚ 未开始 | 一个"我"的 DID 代表本人，下挂 N 个 Agent DID |
| 1.0-05 | 意图路由 | ⬚ 未开始 | 外部发消息给主 DID，根据意图自动转发到子 Agent |
| 1.0-06 | 消息中心 | ⬚ 未开始 | 统一查看所有 Agent 收发的消息 |
| 1.0-07 | 通知系统 | ⬚ 未开始 | 系统托盘通知：新消息、认证请求、异常告警 |

---

### v1.5.0 — 企业版 MVP

> 目标：企业 IT 部门可以在内网部署和管控 Agent 集群。

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 1.5-01 | Admin API | ⬚ 未开始 | 管理员级 CRUD：批量注册/注销 Agent、调整权限 |
| 1.5-02 | Admin 管控台 Web UI | ⬚ 未开始 | 全公司 Agent 可视化管理面板 |
| 1.5-03 | 审计日志模块 | ⬚ 未开始 | 所有 Agent 通信记录留痕，满足合规审计 |
| 1.5-04 | 多租户隔离 | ⬚ 未开始 | 不同部门 Agent 网络互相隔离 |
| 1.5-05 | RBAC 权限体系 | ⬚ 未开始 | 角色-权限映射，超越 Gatekeeper 三模式 |
| 1.5-06 | 组织架构映射 | ⬚ 未开始 | Agent 权限跟着部门走，部门变更自动调整 |
| 1.5-07 | 私有 Relay 一键部署 | ⬚ 未开始 | 企业版 docker-compose，内网 Relay + Admin |
| 1.5-08 | SSO 集成 | ⬚ 未开始 | 对接 LDAP / 企业微信 / 钉钉 / OIDC |
| 1.5-09 | 数据防泄漏 (DLP) | ⬚ 未开始 | Gatekeeper 扩展：敏感词拦截、外发审批规则 |
| 1.5-10 | SLA 监控 & 告警 | ⬚ 未开始 | Agent 在线率、响应延迟、错误率仪表盘 |
| 1.5-11 | Agent 生命周期管理 | ⬚ 未开始 | 集中部署、更新、下线 Agent |

---

### v2.0.0 — Agent 协作协议

> 目标：回到主业——多 Agent 协作通信，Agent 群聊和任务委派。

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 2.0-01 | 群组通信（Multi-Agent Channel） | ⬚ 未开始 | 类似微信群，N 个 Agent 共享频道 |
| 2.0-02 | Topic 订阅 / 发布 | ⬚ 未开始 | Pub/Sub 模式，Agent 订阅感兴趣的主题 |
| 2.0-03 | 任务委派协议 | ⬚ 未开始 | 发布任务 → 接单 → 交付 → 确认 → 结算 |
| 2.0-04 | 结构化消息类型 | ⬚ 未开始 | 任务请求、支付请求、文件传输等标准消息格式 |
| 2.0-05 | 跨框架适配器 | ⬚ 未开始 | AutoGen / CrewAI / LangGraph 各自的适配器包，Agent 侧安装即接入 |
| 2.0-06 | Agent 发现市场 | ⬚ 未开始 | 按能力、信誉、价格搜索可用 Agent |
| 2.0-07 | 长会话管理 | ⬚ 未开始 | 持久化多轮对话上下文，跨 session 恢复 |

---

### v3.0.0 — Agent 生态平台

> 目标：终极形态——Agent 小程序生态、链上身份、完整经济体。

| # | 功能 | 状态 | 说明 |
|---|------|------|------|
| 3.0-01 | Agent 小程序 | ⬚ 未开始 | 第三方在 AgentNexus 上发布可调用的 Agent 服务 |
| 3.0-02 | 链上身份锚定 | ⬚ 未开始 | DID 与区块链绑定，不可篡改身份证明 |
| 3.0-03 | Agent 经济体 | ⬚ 未开始 | 完整的 Agent 间价值交换网络 |
| 3.0-04 | 跨链互操作 | ⬚ 未开始 | 多链 DID 解析 & 支付结算 |
| 3.0-05 | 开发者门户 | ⬚ 未开始 | 文档站 + 沙盒环境 + API Playground |

---

## 目标行业 & 场景

### C 端场景

| 场景 | 描述 | 依赖版本 |
|------|------|---------|
| 个人多 Agent 管理 | 用户已有 N 个 Agent（OpenClaw/Dify/自建），各自安装 AgentNexus 适配器后统一管理 | v1.0 |
| Agent 市场购买 | 从市场选一个 Agent 服务，对方 Agent 已内置适配器，一键互联 | v2.0 |
| 跨平台 Agent 互通 | Dify Agent 和 Coze Agent 各装适配器，通过 AgentNexus 对话（双方无需交换 API Key） | v2.0 |

**典型 C 端用户流程（v1.0 目标）：**
```
1. 用户下载安装 AgentNexus 桌面应用（一键安装，自带 Daemon）
2. 打开 Web 仪表盘 → 点"接入 Agent" → 选择 OpenClaw
3. 仪表盘显示：「请在 OpenClaw 中为你的 Agent 安装 AgentNexus Skill」
4. 用户在 OpenClaw 侧安装 Skill → Skill 自动连接本地 Daemon → 注册 DID
5. 仪表盘上出现该 Agent，状态：已连接 ✅
6. 重复步骤 2-5 接入更多 Agent（Dify、自建等）
7. 所有 Agent 通过 AgentNexus 互相通信，用户在仪表盘统一查看消息
```

### B 端场景

| 场景 | 行业 | 描述 | 依赖版本 |
|------|------|------|---------|
| 多 Agent 审批链 | 银行 | 资料审核→征信→风控→审批→通知，全链路内网 | v1.5 |
| 工厂 Agent 协作 | 制造 | 产线监控→诊断→调度→备件，低延迟，断网可用 | v1.5 |
| 案件协作 | 律所 | 案件分析←→法规检索←→文书生成，客户隔离 | v1.5 |
| 诊疗辅助 | 医疗 | 问诊→影像→药品→随访，数据不出院 | v2.0 |

---

## 外部合作 & 集成

| 合作方 | 内容 | 状态 | 说明 |
|--------|------|------|------|
| Giskard | CA 认证（payment_verified / entity_verified） | 🔄 对接中 | 等待：CA pubkey hex、claim values、Gatekeeper 偏好 |
| QNTM WG | DID Resolution 规范 | 🔄 参与中 | RuntimeVerifier 对标其 8-step pipeline |
| OATR | 信任注册表 + x402 支付协议 | 🔄 对接中 | v0.8 did:web quick path → v0.9 完整集成（JWT attestation + 行为评分 + trust_snapshot） |
| OpenClaw | AgentNexus Skill 适配器 | ⬚ 未开始 | 用户在 OpenClaw 安装 Skill，Agent 自动注册到本地 Daemon，消息双向转发 |
| Dify / Coze | Webhook 适配器 | ⬚ 未开始 | 平台侧配置 Webhook URL，Daemon 接收/转发消息，无需平台 API Key |

---

## 技术债务 & 待修复

| # | 项目 | 状态 | 说明 |
|---|------|------|------|
| D-01 | Relay endpoint None 保护 | ✅ 代码已修复 | 需部署到线上（docker-compose up -d --build relay） |
| D-02 | git push 代理问题 | ⬚ 待手动推送 | commit 933c053 已就绪 |
| D-03 | Python 3.14 asyncio 兼容 | ✅ 已处理 | 统一用 asyncio.run()，不用 get_event_loop() |

---

## 总进度一览

```
v0.7.0 ██████████████████████████████ 13/13  100%  ✅
v0.7.1 ██████████████████████████████  5/5   100%  ✅ 当前版本
v0.8.0 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  1/12    8%  ← 下一步
v0.9.0 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0/13    0%  （+6 OATR 完整集成）
v1.0.0 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0/7     0%
v1.5.0 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0/11    0%
v2.0.0 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0/7     0%
v3.0.0 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0/5     0%
───────────────────────────────────────────────────
总计                                   19/68   28%
```

---

## 更新日志

| 日期 | 变更 |
|------|------|
| 2026-03-27 | 初始版本，v0.7.0 基线，v0.8-v3.0 规划 |
| 2026-03-27 | 修正适配器模式：Agent 侧安装适配器主动接入，不需要外部 API Key |
| 2026-03-27 | 新增 OATR 合作：v0.8 加 did:web quick path（0.8-11/12），v0.9 加完整集成（0.9-08~13） |
| 2026-03-27 | v0.7.1 完成：Relay did:web 支持，`/.well-known/did.json` 端点，144 个测试通过 |
