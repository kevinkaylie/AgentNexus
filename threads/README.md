# 线索追踪系统

## 原则

**广撒网，筛选有效信息，长期跟进**

1. 继续在 GitHub 相关 Issues 上广泛回复，扩大覆盖面
2. 有合作意向 / 讨论内容 / 对我们有帮助 → 记录为"线索"
3. 无用电报 / 讨论 → 标记剔除，不再跟进

## 跟进频率

| 级别 | 条件 | 频率 |
|------|------|------|
| 🔴 **一级-已对接** | 已有实质合作/对接 | 每 3 小时 |
| 🟡 **二级-跟进中** | 有需要继续跟进的 | 每 6 小时 |
| 🟢 **三级-观察** | 暂无实质反馈的 | 每天 |
| ❌ **待剔除** | 2 天以上无有效信息 | 删除 |

## 当前线索

（下方表格由首辅维护）

| 线索 ID | 项目 | Issue/讨论 | 级别 | 最后检查 | 状态 |
|--------|------|------------|------|---------|------|
| gemini-cli-22323 | google-gemini/gemini-cli | #22323 | 🟡二级 | 2026-07-09 06:00 | rpelevin 7/5 02:19 新评论（technical discussion on terminal-state mismatch），未提及 AgentNexus；继续观察 |
| A2A-1672 | a2aproject/A2A | #1672 | 🟡二级 | 2026-07-09 06:00 | 臣评论后无新回复；继续观察 |
| langgraph-7303 | langchain-ai/langgraph | #7303 | 🔴一级 | 2026-07-09 06:00 | **🔥 重大进展**：Correctover 7/3 14:00 正式邀请陛下作为 ICLR 2027 论文合著者（20K workflow 信任治理研究）；**需 48 小时内回复**；等待陛下圣裁 |
| crewAI-6350 | crewAIInc/crewAI | #6350 | 🔴一级 | 2026-07-09 06:00 | **✅ 高质量技术讨论**：kawacukennedy 7/4 10:57 提出 3 个深度问题（receipt 跨 Relay dedup 策略、capability token delegation depth on/off-chain 执行、wallet-as-identity 推导）；需臣回应技术细节 |
| a2a-1713 | a2aproject/A2A | #1713 | 🟡二级 | 2026-07-09 06:00 | **✅ 新回复**：tomjwxf 7/8 08:19 介绍 Legate Warrant 实现（离线可验证凭证、签名回执链），建议将运营商法律身份作为凭证一级声明；chopmob-cloud 7/8 17:56 回复确认 crypto-agility layering 方向正确，提及 Substrate 2 PQC 工作（Falcon-1024 签名、混合验证）；需臣回应 |
| cosai-47 | cosai-oasis/ws4-secure-design-agentic-systems | #47 | 🟢三级 | 2026-07-09 06:00 | benhylau 6/18 确认纳入白皮书，之后无新动态；每日观察 |

### 已剔除
- ~~bitrouter-176~~（最后动态 3/24，近 3 个月无更新）
- ~~up2itnow0822~~（最后动态 3/16，Issue #17 已 404）
- ~~yuquan2088~~（最后动态 3/?，无有效信息）
- ~~FransDev-oatr~~（Issue #2 已 404，仓库可能已删除/转私有）
- ~~x402-1777~~（最后动态 3/27，沉寂超 3 个月）
- ~~msaleme-rtbtaf~~（最后动态 4/2，沉寂近 3 个月）
- ~~openclaw-49971~~（最后动态 4/1，沉寂近 3 个月）
- ~~mcpso-1308~~（最后动态 3/31，沉寂超 3 个月）
- ~~a2a-1672-dup~~（重复线索，已合并至二级）
- ~~aeoess-aps-13~~（最后动态 4/11，沉寂近 3 个月）

### 关键 Repo 地址备忘
- x402 foundation：`x402-foundation/x402`（注意不是 coinbase/x402！）
- msaleme harness：`msaleme/red-team-blue-team-agent-fabric`

### 近期跟进任务
- [x] **google-gemini/gemini-cli#22323**：✅ 臣已评论 Objective Loop + Context Budget 方案
- [x] **a2aproject/A2A#1672**：✅ 臣已评论 did:agentnexus 规范 + 联邦 Relay
- [x] **langchain-ai/langgraph#7303**：✅ 臣已跟进评论 Capability Token + trust annotation 映射方案
- [x] **crewAIInc/crewAI#6350**：✅ 臣已评论 DID 身份 + Delivery Manifest + Objective Loop
- [x] **a2aproject/A2A#1713**：✅ 臣已跟进评论 did:agentnexus PQC-ready 身份层 + ZKP federation
- [ ] **cosai-47**：benhylau 确认将 AGNTCY Agent Identity 纳入白皮书；可评论提供 did:agentnexus spec 作为参考实现
