# 项目现状速览

> **唯一状态源**：本文档是 AgentNexus 项目版本、功能状态、关键数字的唯一权威来源。
> 其他文档（CLAUDE.md、architecture.md、AGENTS.md 等）引用本文档，不重复维护状态。
> 最后更新：2026-04-23（v1.0 Phase 2 开发中）

## 一句话总结

AgentNexus 是 AI Agent 的通信基础设施——去中心化身份 + 联邦发现 + 端到端加密 + 智能路由 + 协作协议 + 治理信任。v1.0 正在做 Web 仪表盘和鉴权收紧。

## 关键数字

| 指标 | 值 |
|------|-----|
| 当前版本 | v1.0 Phase 2 开发中 |
| 测试数 | 390 collected, 382 passed, 8 skipped |
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
| v1.0 Phase 2 | 🚧 开发中 | 意图路由 (1.0-05)、Web 仪表盘 (1.0-01)、接入向导 (1.0-03)、鉴权矩阵收紧、Consistency Level L0/L1 |
| v1.5 | 📋 规划中 | 企业版 MVP：Admin API、审计日志、多租户、RBAC、统一策略引擎、决策一致性分级 |

## 模块状态

| 模块 | 状态 | 说明 |
|------|------|------|
| DID 身份（did:agentnexus） | ✅ | Ed25519 multikey，自证明 |
| 四步握手 + AES-256-GCM | ✅ | 端到端加密通信 |
| Node Daemon（:8765） | ✅ | Gatekeeper + 智能路由 + SQLite |
| Relay Server（:9000） | ✅ | 联邦互联，1 跳查询 |
| MCP Server（37 个工具） | ✅ | Claude Desktop / Cursor / Claude Code |
| L1-L4 信任体系 | ✅ | 多 CA + RuntimeVerifier + 信任衰减 |
| Python SDK | ✅ | async/sync 双模式，3 行接入 |
| Action Layer + Discussion | ✅ | 任务委派/认领/投票/结论 |
| Push 注册 + 推送 | ✅ | SIP REGISTER 风格 + HMAC 签名 |
| Enclave + Playbook | ✅ | 项目组 + 角色绑定 + 自动编排 |
| Governance + Trust Network | ✅ | MolTrust/APS + Web of Trust + 声誉 |
| 个人主 DID + 消息中心 | ✅ | Owner DID 管理 N 个 Agent |
| Capability Token | ✅ | Ed25519 签名 + 约束哈希 + 委托链收窄 |
| 意图路由 | ✅ | 主 DID → 子 Agent 自动转发 |
| Consistency Level | ✅ L0, 🚧 L1 | 决策一致性分级 |
| Web 仪表盘 | 🚧 | Vue 3 + Vite + PrimeVue，Phase B |
| 鉴权矩阵 v3 | 📋 设计定稿 | actor DID 校验 + /deliver 签名验证，待实现 |
| did:meeet 桥接 | 📋 设计完成 | ADR-008，待开发 |

## 活跃外部合作

| 合作方 | 内容 | 状态 |
|--------|------|------|
| Giskard | CA 认证签发 | 等待对方提供 pubkey hex |
| OATR | 信任注册表 + JWT Attestation | 对接中 |
| QNTM WG | DID Resolution 规范 | ✅ 已完成 |
| MEEET | did:meeet 互操作 | 设计完成，待开发 |
| APS (aeoess) | agent-governance-vocabulary crosswalk | ✅ PR 已合并 |
| A2A | Consistency Level Proposal | 📋 草稿待提交 |

## 当前阻塞项

> 详见 `docs/wip.md`

1. **鉴权矩阵实现**（P1-P3）：消息面鉴权、actor DID 校验、Enclave 读接口私有化。设计 v3 已定稿，待实现。
2. **文档单一事实源**（P4）：本文档正在收敛中。
3. **严格 JCS 实现**（S5）：当前为确定性 JSON 序列化，跨语言互操作需升级为 RFC 8785。

## 新人最小阅读清单

1. **[AGENTS.md](../AGENTS.md)** — 文档索引
2. **[docs/architecture.md](architecture.md)** — 架构全貌
3. **[CLAUDE.md](../CLAUDE.md)** — 开发约定
4. **[docs/quickstart.md](quickstart.md)** — 动手跑一遍
5. **本文档** — 当前进度
