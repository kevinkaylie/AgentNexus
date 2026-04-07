# 进行中变更追踪（Work In Progress）

> 完成的变更从此文件移除，确认已记录在 `CHANGELOG.md` 中。

## v0.8.0 里程碑

| 变更标题 | 负责角色 | 关联编号 | 状态 | 预计完成 | 依赖项 | 待同步文档 |
|---------|---------|---------|------|---------|--------|-----------|
| Python SDK 包（agentnexus-sdk） | 开发 Agent | 0.8-01 | ✅ 完成 | 2026-04-04 | — | ADR-006, api-reference.md |
| `AgentNexus.connect(name)` 一行接入 | 开发 Agent | 0.8-02 | ✅ 完成 | 2026-04-04 | 0.8-01 | quickstart.md |
| 本地 Agent 自动发现 | 开发 Agent | 0.8-03 | ✅ 完成 | 2026-04-04 | 0.8-01 | — |
| SDK 消息收发 API | 开发 Agent | 0.8-04 | ✅ 完成 | 2026-04-04 | 0.8-01 | api-reference.md |
| SDK 信任查询 API | 开发 Agent | 0.8-05 | ✅ 完成 | 2026-04-04 | 0.8-01 | api-reference.md |
| SDK 认证管理 API | 开发 Agent | 0.8-06 | ✅ 完成 | 2026-04-04 | 0.8-01 | api-reference.md |
| SDK Action Layer（四种协作动作） | 开发 Agent | 0.8-11 | ✅ 完成 | 2026-04-04 | 0.8-01 | ADR-007 |
| did:meeet 桥接支持 | 开发 Agent | 0.8-13 | ✅ 完成 | 2026-04-04 | — | ADR-008 |
| Discussion Protocol 讨论协议实现 | 开发 Agent | — | ✅ 完成 | 2026-04-05 | ADR-011 | — |
| 平台适配器架构实现 | 开发 Agent | 0.8-07/08 | ✅ 完成 | 2026-04-05 | ADR-010 | — |
| SDK 文档 & 示例 | 开发 Agent | 0.8-09 | ✅ 完成 | 2026-04-05 | 0.8-01 | README.md |
| PyPI 发布 | 开发 Agent | 0.8-10 | 待开始 | — | 0.8-01 | — |
| DID 互操作测试（OATR） | 开发 Agent | 0.8-12 | 待开始 | — | — | contracts/oatr-jwt-attestation.md |
| DID Method Handler 注册表重构 | 开发 Agent | — | ✅ 完成 | 2026-04-04 | — | ADR-009 |
| 平台适配器与 Skill 注册架构设计 | 设计 Agent | — | ✅ 完成 | 2026-04-04 | — | ADR-010 |
| Discussion Protocol 讨论协议设计 | 设计 Agent | — | ✅ 完成 | 2026-04-05 | ADR-007 | ADR-011 |
| ACP 协议栈设计（Push Gateway + MCP 协作） | 设计 Agent | — | ✅ 完成 | 2026-04-06 | ADR-007, ADR-011 | ADR-012, architecture.md |
| MCP Action Layer 工具（4 个） | 开发 Agent | 0.8-14 | ✅ 完成 | 2026-04-07 | ADR-012 | mcp-setup.md |
| MCP Discussion 工具（4 个） | 开发 Agent | 0.8-15 | ✅ 完成 | 2026-04-07 | ADR-012 | mcp-setup.md |
| MCP Emergency + Skill 工具（2 个） | 开发 Agent | 0.8-16 | ✅ 完成 | 2026-04-07 | ADR-012 | mcp-setup.md |
| 跨平台 MCP 配置文档 | 开发 Agent | 0.8-17 | ✅ 完成 | 2026-04-07 | 0.8-14~16 | mcp-setup.md, scenarios.md |

## 已阻塞

| 变更标题 | 阻塞原因 | 等待依赖 |
|---------|---------|---------|
| Giskard CA 正式集成 | 等待 CA pubkey hex、claim values、Gatekeeper 偏好 | Giskard 团队 |
