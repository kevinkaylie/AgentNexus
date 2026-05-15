# AgentNexus 设计文档

> 本文件为设计文档索引。设计按版本拆分为独立文件。
> 已实现的架构参考 [architecture.md](architecture.md)，关键决策参考 [ADR](adr/)。

---

## 设计文档索引

| 文件 | 版本范围 | 状态 | 行数 |
|------|---------|------|------|
| [design/design-v1.0.md](design/design-v1.0.md) | v1.0.0 团队协作开发者预览 + v1.5 前瞻 + 鉴权矩阵 | **活跃** | ~1400 |
| [design/design-coding-coordination-v1.md](design/design-coding-coordination-v1.md) | Coding Coordination V1：跨 session / runtime 的可信协调闭环 | 设计/草稿实现未接入 | ~750 |
| [design/design-coding-coordination-v1-release.md](design/design-coding-coordination-v1-release.md) | Coding Coordination V1 Release Closure：SDK / CLI / Dashboard / Quickstart 收口 | 设计中 / P0 阻塞 | ~430 |
| [archive/design-v0.x.md](archive/design-v0.x.md) | v0.7–v0.9 | 归档 | ~440 |
| [design/design-secretary-orchestration.md](design/design-secretary-orchestration.md) | 常驻秘书 + 企业 Agent 团队协作编排专题 | 活跃 | ~1500 |
| [design/design-sdk-orchestration.md](design/design-sdk-orchestration.md) | Orchestration SDK 改造专题 | 活跃 | ~700 |
| [design/design-dashboard-setup-v1.0.md](design/design-dashboard-setup-v1.0.md) | Dashboard / Setup v1.0 收口专题 | 活跃 | ~250 |

## 快速导航

### v1.0.0（活跃）

当前 v1.0.0 范围已收敛为“团队协作开发者预览”：Orchestration SDK + Secretary Phase B 基础闭环 + Web Dashboard 基础入口 + Setup 向导 + 鉴权矩阵 v3。Coding Coordination V1 仍是设计/草稿实现未接入状态；如果纳入 v1.0.0，必须先完成后端 P0 foundation（models、storage、router registration、SQLite init、tests），再进入 SDK facade、CLI demo、Dashboard 只读视图和 Quickstart release closure。

- [Coding Coordination V1](design/design-coding-coordination-v1.md)
- [Coding Coordination V1 Release Closure](design/design-coding-coordination-v1-release.md)
- [1.0-04 个人主 DID](design/design-v1.0.md#104-个人主-did)
- [1.0-06 消息中心](design/design-v1.0.md#106-消息中心)
- [1.0-08 Capability Token](design/design-v1.0.md#108-a2a-capability-token-envelope)
- [1.0-05 意图路由](design/design-v1.0.md#105-意图路由)
- [Dashboard / Setup v1.0 收口](design/design-dashboard-setup-v1.0.md)
- [1.0-01 Web 仪表盘基础设计](design/design-v1.0.md#101-web-仪表盘)
- [1.0-03 接入向导基础设计](design/design-v1.0.md#103-agent-接入向导)
- [鉴权矩阵 v3](design/design-v1.0.md#鉴权矩阵设计-v3p1-p4-修复方案)
- [常驻秘书与 Agent 团队协作编排](design/design-secretary-orchestration.md)
- [Orchestration SDK 改造](design/design-sdk-orchestration.md)
- [决策一致性分级](design/design-v1.0.md#v15-前瞻--决策一致性分级1513)

### 后移范围

- v1.1：Tauri 桌面壳、系统托盘通知、CLI Launcher、Dashboard 产品化、Adapter 产品化、Skill 版本精细绑定、花费限额组合。
- v1.5：per-agent token、Capability 强制执行、`/deliver` hard-enforce、Strict JCS、审计日志、签名交付包、企业 RBAC。

### v0.x（归档）

- [v0.8.0 SDK + Action Layer](archive/design-v0.x.md#v080--sdk-基础--协作协议action-layer)
- [v0.8.5 Enclave 群组](archive/design-v0.x.md#v085--relay-vault--enclave-群组)
- [v0.9.0 信任传递 + 声誉](archive/design-v0.x.md#v090--信任传递--声誉--output-provenance)

### 专题设计（活跃）

- [Coding Coordination V1](design/design-coding-coordination-v1.md)
- [Coding Coordination V1 Release Closure](design/design-coding-coordination-v1-release.md)
- [常驻秘书与 Agent 团队协作编排](design/design-secretary-orchestration.md)
- [Orchestration SDK 改造](design/design-sdk-orchestration.md)
