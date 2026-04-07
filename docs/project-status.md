# 项目现状速览

> 最后更新：2026-04-05（v0.8.0 开发中）
> 每个版本发布时由设计 Agent 更新此文档。

## 一句话总结

AgentNexus 是 AI Agent 的通信基础设施——去中心化身份 + 联邦发现 + 端到端加密 + 智能路由。v0.7.x 已完成核心基础设施，v0.8.0 正在做 Python SDK 和协作协议。

## 架构现状

| 模块 | 状态 | 说明 |
|------|------|------|
| DID 身份（did:agentnexus） | ✅ 已实现 | Ed25519 multikey，自证明 |
| 四步握手 + AES-256-GCM 加密 | ✅ 已实现 | 端到端加密通信 |
| Node Daemon（:8765） | ✅ 已实现 | Gatekeeper + 智能路由 + SQLite 存储 |
| Relay Server（:9000） | ✅ 已实现 | 联邦互联，1 跳查询 |
| MCP Server（17 个工具） | ✅ 已实现 | Claude Desktop / Cursor / Claude Code |
| L1-L4 信任体系 | ✅ 已实现 | 多 CA + RuntimeVerifier |
| Python SDK（agentnexus-sdk） | 🚧 开发中 | ADR-006，3 行代码接入 |
| Action Layer 协作协议 | 🚧 设计完成 | ADR-007，四种基础动作 |
| did:meeet 跨平台桥接 | 🚧 设计完成 | ADR-008，1020 Agent 互操作 |
| DID Method Handler 注册表 | ✅ 设计完成 | ADR-009，支持任意 DID 方法插件化扩展 |
| 平台适配器与 Skill 注册 | ✅ 设计完成 | ADR-010，OpenClaw / Webhook 统一适配层 |
| Discussion Protocol 讨论协议 | 🚧 设计中 | ADR-011（草稿），Agent 间讨论/投票/结论落盘 + Human-via-Agent + 紧急熔断 |

## 活跃外部合作

| 合作方 | 内容 | 状态 |
|--------|------|------|
| Giskard | CA 认证签发 | 等待对方提供 pubkey hex |
| OATR | 信任注册表 + JWT Attestation | 对接中 |
| QNTM WG | DID Resolution 规范 | ✅ 已完成（v1.0 RATIFIED） |
| MEEET | did:meeet 互操作（1020 Agents） | 设计完成，待开发 |

## 新人最小阅读清单

1. **[AGENTS.md](../AGENTS.md)** — 文档索引，找到任何文档的入口
2. **[docs/architecture.md](architecture.md)** — 架构全貌（Daemon / Relay / MCP 三层）
3. **[CLAUDE.md](../CLAUDE.md)** — 项目上下文和开发约定
4. **[docs/quickstart.md](quickstart.md)** — 动手跑一遍：注册 → 发现 → 对话
5. **本文档** — 你正在读的这个，了解当前进度和重点
