# 进行中变更追踪（Work In Progress）

> 完成的变更从此文件移除，确认已记录在 `CHANGELOG.md` 中。

## v0.8.0 里程碑 — ✅ 已发布 (2026-04-08)

**发布地址：**
- GitHub Release: https://github.com/kevinkaylie/AgentNexus/releases/tag/v0.8.0
- PyPI: https://pypi.org/project/agentnexus-sdk/0.8.0/

所有 v0.8.0 任务已完成，变更已记录在 `CHANGELOG.md`。

## v0.9.0 规划（待开始）

| 变更标题 | 负责角色 | 关联编号 | 状态 | 依赖项 |
|---------|---------|---------|------|--------|
| L3 注册层实现（Agent 报到 + TTL 续约） | 开发 Agent | 0.9-01 | 待开始 | ADR-012 §3 |
| L5 推送层实现（Push Gateway + Webhook） | 开发 Agent | 0.9-02 | 待开始 | ADR-012 §4 |
| MCP 自动注册 + 后台续约 | 开发 Agent | 0.9-03 | 待开始 | 0.9-01 |
| SDK 自动注册 + 断线清理 | 开发 Agent | 0.9-04 | 待开始 | 0.9-01 |

## 已阻塞

| 变更标题 | 阻塞原因 | 等待依赖 |
|---------|---------|---------|
| Giskard CA 正式集成 | 等待 CA pubkey hex、claim values、Gatekeeper 偏好 | Giskard 团队 |
