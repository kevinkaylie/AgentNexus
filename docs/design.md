# AgentNexus 设计文档

> 本文件为设计文档索引。设计按版本拆分为独立文件。
> 已实现的架构参考 [architecture.md](architecture.md)，关键决策参考 [ADR](adr/)。

---

## 设计文档索引

| 文件 | 版本范围 | 状态 | 行数 |
|------|---------|------|------|
| [design/design-v1.0.md](design/design-v1.0.md) | v1.0 Phase 1/2 + v1.5 前瞻 + 鉴权矩阵 | **活跃** | ~1400 |
| [design/design-v0.x.md](design/design-v0.x.md) | v0.7–v0.9 | 归档 | ~440 |
| [design/design-secretary-orchestration.md](design/design-secretary-orchestration.md) | 常驻秘书 + 企业 Agent 团队协作编排专题 | 活跃 | ~950 |

## 快速导航

### v1.0（活跃）

- [1.0-04 个人主 DID](design/design-v1.0.md#104-个人主-did)
- [1.0-06 消息中心](design/design-v1.0.md#106-消息中心)
- [1.0-08 Capability Token](design/design-v1.0.md#108-a2a-capability-token-envelope)
- [1.0-05 意图路由](design/design-v1.0.md#105-意图路由)
- [1.0-01 Web 仪表盘](design/design-v1.0.md#101-web-仪表盘)
- [1.0-03 接入向导](design/design-v1.0.md#103-agent-接入向导)
- [鉴权矩阵 v3](design/design-v1.0.md#鉴权矩阵设计-v3p1-p4-修复方案)
- [决策一致性分级](design/design-v1.0.md#v15-前瞻--决策一致性分级1513)

### v0.x（归档）

- [v0.8.0 SDK + Action Layer](design/design-v0.x.md#v080--sdk-基础--协作协议action-layer)
- [v0.8.5 Enclave 群组](design/design-v0.x.md#v085--relay-vault--enclave-群组)
- [v0.9.0 信任传递 + 声誉](design/design-v0.x.md#v090--信任传递--声誉--output-provenance)

### 专题设计（活跃）

- [常驻秘书与 Agent 团队协作编排](design/design-secretary-orchestration.md)
