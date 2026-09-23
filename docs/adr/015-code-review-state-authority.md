# ADR-015：代码评审的双层状态权威

## 状态

提议（2026-09-18），设计评审通过并采纳（2026-09-18）。

## 背景

早期 Code Review V1 草案拟由 AgentNexus 管理 ReviewRun；Nexus/HCZJ 已确认 RUN-ID-2026-09-14 的四元 Run 身份。照旧草案实施会形成两个状态写入者。

## 提议决策

Nexus 管理扫描版本与证据；HCZJ 是业务评审 Run/Attempt/策略与 current 的唯一权威；AgentNexus 的 PlaybookRun 只管理本地协作/适配生命周期，关联 external_coordinator_id/external_run_id，不重复分配评审 revision。外部评审结果必须经 Profile 校验，通用 approved 不能推导业务通过。

这不改变 ADR-013 等既有普通 PlaybookRun 的运行态权威；新增的是外部应用任务的映射边界。无 HCZJ 或等价且明确选定的 Coordinator 时，v1 返回 coordinator_unavailable，允许单独查询 Nexus 证据，但不能把本地 demo 冒充自动评审闭环。未来转移 Coordinator 需另行迁移设计。

## 替代方案

1. AgentNexus 重建评审 Run：重复 HCZJ 已确认实现与预算机制，需全面迁移，暂不采用。
2. 双侧同时推进评审状态：冲突与过期无法稳定判定，拒绝。
3. HCZJ 权威、AgentNexus 关联：复用当前契约，代价是外部状态查询、围栏及适配层复杂度。

## 影响与验证

涉及 Profile、外部 ID 映射、角色鉴权、结果入口、Vault 摘要及 UI 投影。详见 [Profile §15](../design/code-review-collaboration-profile-v1.md)。CP-05/19/21/24 必须验证跨层边界；不声明分布式原子事务。

## 评审记录

| 日期 | 评审者 | 结果 | 备注 |
|------|--------|------|------|
| 2026-09-18 | 评审 Agent | 批准（已采纳） | 依据 Profile §15 决议复核：双层权威边界与 ADR-013 的普通 PlaybookRun 权威不冲突；无 Coordinator 时返回 `coordinator_unavailable` 的降级路径明确；替代方案（AgentNexus 重建 Run / 双侧同时写入）驳回理由成立。残余建议 R2：`coordinator_unavailable` 需补入 Profile §15.8 的 `code_review.error.v1` 清单 |

2026-09-18：根据 Profile S1 提出；同日随 Profile draft.2 复核批准，未更改生产代码。
