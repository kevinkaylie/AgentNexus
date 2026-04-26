# AgentNexus 文档索引

> 本文件是所有 AI Agent 角色的入口文档。新 Agent 加入项目时，从这里开始。

## 快速导航

### 按角色推荐阅读顺序

| 角色 | 推荐阅读顺序 |
|------|-------------|
| 设计 Agent | AGENTS.md → [角色手册](docs/roles/design-agent.md) → [ADR 列表](#架构决策记录adr) → [接口契约](#接口契约) → [架构文档](docs/architecture.md) → [路线图](docs/roadmap.md) |
| 开发 Agent | AGENTS.md → [角色手册](docs/roles/development-agent.md) → [CLAUDE.md](CLAUDE.md) → [API 参考](docs/api-reference.md) → [接口契约](#接口契约) → [WIP](docs/wip.md) |
| 评审 Agent | AGENTS.md → [角色手册](docs/roles/review-agent.md) → [设计评审流程](docs/processes/design-review.md) → [ADR 列表](#架构决策记录adr) → [安全文档](SECURITY.md) |
| 测试 Agent | AGENTS.md → [角色手册](docs/roles/testing-agent.md) → [tests/CLAUDE.md](tests/CLAUDE.md) → [API 参考](docs/api-reference.md) → [WIP](docs/wip.md) |

---

## 文档目录

### 角色手册

| 文档 | 路径 | 状态 |
|------|------|------|
| 设计 Agent 手册 | [docs/roles/design-agent.md](docs/roles/design-agent.md) | 生效 |
| 开发 Agent 手册 | [docs/roles/development-agent.md](docs/roles/development-agent.md) | 生效 |
| 评审 Agent 手册 | [docs/roles/review-agent.md](docs/roles/review-agent.md) | 生效 |
| 测试 Agent 手册 | [docs/roles/testing-agent.md](docs/roles/testing-agent.md) | 生效 |

### 架构决策记录（ADR）

| 编号 | 标题 | 状态 | 路径 |
|------|------|------|------|
| ADR-000 | 模板 | — | [docs/adr/000-template.md](docs/adr/000-template.md) |
| ADR-001 | DID 格式选择 | 已采纳 | [docs/adr/001-did-format-selection.md](docs/adr/001-did-format-selection.md) |
| ADR-002 | 四步握手协议设计 | 已采纳 | [docs/adr/002-four-step-handshake.md](docs/adr/002-four-step-handshake.md) |
| ADR-003 | Sidecar 架构（Daemon-MCP 解耦） | 已采纳 | [docs/adr/003-sidecar-architecture.md](docs/adr/003-sidecar-architecture.md) |
| ADR-004 | 多 CA 认证架构 | 已采纳 | [docs/adr/004-multi-ca-certification.md](docs/adr/004-multi-ca-certification.md) |
| ADR-005 | Gatekeeper 三模式设计 | 已采纳 | [docs/adr/005-gatekeeper-three-modes.md](docs/adr/005-gatekeeper-three-modes.md) |
| ADR-006 | SDK 架构与 Daemon 通信协议 | 提议 | [docs/adr/006-sdk-daemon-communication.md](docs/adr/006-sdk-daemon-communication.md) |
| ADR-007 | Action Layer 协作协议设计 | 提议 | [docs/adr/007-action-layer-protocol.md](docs/adr/007-action-layer-protocol.md) |
| ADR-008 | did:meeet 跨平台桥接架构 | 提议 | [docs/adr/008-did-meeet-bridge.md](docs/adr/008-did-meeet-bridge.md) |
| ADR-009 | DID Method Handler 注册表架构 | 已采纳 | [docs/adr/009-did-method-handler-registry.md](docs/adr/009-did-method-handler-registry.md) |
| ADR-010 | 平台适配器与 Skill 注册架构 | 提议 | [docs/adr/010-platform-adapter-skill-registry.md](docs/adr/010-platform-adapter-skill-registry.md) |
| ADR-011 | Discussion Protocol 讨论协议设计 | 草稿 | [docs/adr/011-discussion-protocol.md](docs/adr/011-discussion-protocol.md) |
| ADR-012 | ACP 协议栈（Push Gateway + MCP 协作） | 已采纳 | [docs/adr/012-push-gateway-and-mcp-collaboration.md](docs/adr/012-push-gateway-and-mcp-collaboration.md) |
| ADR-013 | Enclave 协作架构（项目组 + VaultBackend + Playbook） | 已采纳 | [docs/adr/013-enclave-collaboration-architecture.md](docs/adr/013-enclave-collaboration-architecture.md) |
| ADR-014 | Governance Attestation + Trust Network | 已采纳 | [docs/adr/014-governance-trust-network.md](docs/adr/014-governance-trust-network.md) |

### 接口契约

| 文档 | 合作方 | 状态 | 路径 |
|------|--------|------|------|
| CA 认证签发与验证 | Giskard | 草稿 | [docs/contracts/giskard-ca-certification.md](docs/contracts/giskard-ca-certification.md) |
| JWT Attestation 验证 | OATR | 草稿 | [docs/contracts/oatr-jwt-attestation.md](docs/contracts/oatr-jwt-attestation.md) |
| DID Resolution v1.0 | QNTM WG | 已对齐 | [docs/contracts/qntm-did-resolution.md](docs/contracts/qntm-did-resolution.md) |

### 流程文档

| 文档 | 路径 | 状态 |
|------|------|------|
| 设计评审流程 | [docs/processes/design-review.md](docs/processes/design-review.md) | 生效 |
| 代码评审流程 | [docs/processes/code-review.md](docs/processes/code-review.md) | 生效 |

### 需求与设计

| 文档 | 路径 | 状态 |
|------|------|------|
| 项目现状速览 | [docs/project-status.md](docs/project-status.md) | **唯一状态源** |
| 项目需求文档 | [docs/requirements.md](docs/requirements.md) | 生效 |
| 设计文档索引 | [docs/design.md](docs/design.md) | 生效 |
| 设计 v1.0+（活跃） | [docs/design/design-v1.0.md](docs/design/design-v1.0.md) | 生效 |
| 设计 v0.x（归档） | [docs/design/design-v0.x.md](docs/design/design-v0.x.md) | 归档 |
| 秘书与 Agent 团队协作编排专题 | [docs/design/design-secretary-orchestration.md](docs/design/design-secretary-orchestration.md) | 活跃 |

### 变更追踪

| 文档 | 路径 | 说明 |
|------|------|------|
| 进行中变更 | [docs/wip.md](docs/wip.md) | 当前正在开发的功能和阻塞项 |
| 开发日志 | [docs/devlog.md](docs/devlog.md) | 每次开发提交的内容和测试结果 |
| 已发布变更 | [CHANGELOG.md](CHANGELOG.md) | 已完成版本的变更记录 |

### 模板

| 模板 | 路径 | 用途 |
|------|------|------|
| 角色手册模板 | [docs/templates/role-handbook.tmpl.md](docs/templates/role-handbook.tmpl.md) | 创建新角色手册 |
| ADR 模板 | [docs/templates/adr.tmpl.md](docs/templates/adr.tmpl.md) | 创建新架构决策记录 |
| 接口契约模板 | [docs/templates/contract.tmpl.md](docs/templates/contract.tmpl.md) | 创建新接口契约 |
| WIP 条目模板 | [docs/templates/wip-entry.tmpl.md](docs/templates/wip-entry.tmpl.md) | 添加新的进行中变更条目 |

### 现有技术文档

| 文档 | 路径 | 状态 |
|------|------|------|
| 项目上下文 | [CLAUDE.md](CLAUDE.md) | 生效 |
| 模块上下文 | [agent_net/CLAUDE.md](agent_net/CLAUDE.md) | 生效 |
| 测试规范 | [tests/CLAUDE.md](tests/CLAUDE.md) | 生效 |
| 架构设计 | [docs/architecture.md](docs/architecture.md) | 生效 |
| API 参考 | [docs/api-reference.md](docs/api-reference.md) | 生效 |
| DID 方法规范 | [docs/did-method-spec.md](docs/did-method-spec.md) | 草稿 |
| 快速开始 | [docs/quickstart.md](docs/quickstart.md) | 生效 |
| 使用场景 | [docs/scenarios.md](docs/scenarios.md) | 生效 |
| MCP 配置 | [docs/mcp-setup.md](docs/mcp-setup.md) | 生效 |
| CLI 命令 | [docs/commands.md](docs/commands.md) | 生效 |
| 产品路线图 | [docs/roadmap.md](docs/roadmap.md) | 生效（仅本地） |
| WG DID Resolution | [specs/working-group/did-resolution.md](specs/working-group/did-resolution.md) | 生效（v1.0 RATIFIED） |

---

## 跨团队协作状态

| 合作方 | 集成内容 | 状态 | 契约文档 | 关键待办 | 负责角色 |
|--------|---------|------|---------|---------|---------|
| Giskard | CA 认证（payment_verified / entity_verified） | 对接中 | [giskard-ca-certification.md](docs/contracts/giskard-ca-certification.md) | 等待 CA pubkey hex、claim values、Gatekeeper 偏好 | 设计 Agent |
| OATR | 信任注册表 + JWT Attestation + x402 支付 | 对接中 | [oatr-jwt-attestation.md](docs/contracts/oatr-jwt-attestation.md) | v0.8 did:web quick path → v0.9 完整集成 | 开发 Agent |
| QNTM WG | DID Resolution 规范 | 已完成 | [qntm-did-resolution.md](docs/contracts/qntm-did-resolution.md) | — | 设计 Agent |
| MEEET | did:meeet 互操作（1020 Agents, Solana） | 对接中 | — | DIDResolver 新增 did:meeet 分支，待确认 Solana API 端点 | 开发 Agent |
| OpenClaw | AgentNexus Skill 适配器 | 未开始 | — | v0.8 SDK 先行 | 开发 Agent |
| Dify / Coze | Webhook 适配器 | 未开始 | — | v0.8 SDK 先行 | 开发 Agent |
