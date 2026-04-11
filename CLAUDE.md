# AgentNexus - CLAUDE.md (updated 2026-04-11)

## 项目概述

AI时代的软件定义网络 - 去中心化Agent通信基础设施。

- WG DID Resolution 规范：https://github.com/corpollc/qntm/blob/main/specs/working-group/did-resolution.md
- did:key 实现参考：https://w3c-ccg.github.io/did-method-key/

## 当前状态：v0.9.6 — Governance Attestation + Trust Network

### 全部 301 个测试通过 ✅

### 已实现模块

| 模块 | 说明 |
|------|------|
| `agent_net/common/crypto.py` | Base58BTC、multikey Ed25519/X25519、ed25519→x25519 推导 |
| `agent_net/common/did.py` | DIDGenerator、DIDResolver（4种方法）、DIDResolutionResult |
| `agent_net/common/profile.py` | NexusProfile sign/verify、create_certification、verify_certification |
| `agent_net/common/runtime_verifier.py` | AgentNexusRuntimeVerifier（L1-L4 信任体系，多 CA 架构） |
| `agent_net/common/handshake.py` | 四步握手协议 |
| `agent_net/common/keystore.py` | export/import（argon2id+SecretBox） |
| `agent_net/common/governance.py` | GovernanceClient（MolTrust/APS）、GovernanceRegistry、JWS 验证 |
| `agent_net/common/trust_graph.py` | Web of Trust、信任传递、路径发现（BFS） |
| `agent_net/common/reputation.py` | ReputationScore、BehaviorScorer、ReputationStore |
| `agent_net/node/daemon.py` | FastAPI :8765 入口，组装 routers |
| `agent_net/node/routers/` | 8 个功能模块（agents/messages/handshake/adapters/push/enclave/governance） |
| `agent_net/node/mcp_server.py` | MCP stdio，33 个工具 |
| `agent_net/node/gatekeeper.py` | public/ask/private 三模式访问控制 |
| `agent_net/relay/server.py` | 联邦 Relay，Redis 存储，`/.well-known/did.json` |
| `docs/did-method-spec.md` | did:agentnexus 规范文档（草稿） |

## 文档体系

项目采用结构化文档体系支持多 Agent 协作开发。入口文件：**`AGENTS.md`**。

```
AGENTS.md              ← 文档总索引，新 Agent 从这里开始
├── docs/requirements.md    ← 项目需求（按版本，含用户故事和验收标准）
├── docs/design.md          ← 项目设计（按版本，含 API 设计和技术方案）
├── docs/roadmap.md         ← 产品路线图（版本规划 + 进度，仅本地）
├── docs/wip.md             ← 进行中变更追踪（仅本地）
├── docs/devlog.md          ← 开发提交日志（仅本地）
├── CHANGELOG.md            ← 已发布版本变更记录
├── docs/adr/               ← 架构决策记录（ADR-001~005）
├── docs/contracts/         ← 跨团队接口契约（Giskard/OATR/QNTM WG）
├── docs/roles/             ← Agent 角色手册（设计/开发/评审/测试）
├── docs/processes/         ← 流程文档（设计评审流程）
└── docs/templates/         ← 文档模板（ADR/契约/角色/WIP 条目）
```

### 开发流程闭环

```
roadmap（规划什么）→ requirements（做到什么程度）→ design（怎么做）
→ wip（做到哪了）→ devlog（每次做了什么）→ CHANGELOG（发布了什么）
```

### 开发时必读

- 开始新功能前：查 `docs/requirements.md` 确认验收标准，查 `docs/design.md` 确认技术方案
- 开发过程中：更新 `docs/wip.md` 状态
- 每次提交后：在 `docs/devlog.md` 记录变更内容和测试结果
- 功能完成后：从 `docs/wip.md` 移除，更新 `CHANGELOG.md` 和 `docs/roadmap.md`
- 新架构决策：写 ADR 到 `docs/adr/`，经评审后标记"已采纳"

### 仅本地保留（不提交 GitHub）

`docs/roadmap.md`、`docs/wip.md`、`docs/devlog.md`、`docs/giskard-*.md`、`docs/contracts/giskard-ca-certification.md`、`docs/contracts/oatr-jwt-attestation.md`

## DID 格式

- `did:agent:<hex>` — 旧格式（向后兼容）
- `did:agentnexus:<multikey>` — 新格式（默认），multikey = `z` + base58btc(0xED01 || ed25519_pubkey)
- `did:web:<domain>` — Relay 身份（v0.7.1），通过 `/.well-known/did.json` 解析

## Relay did:web 身份（v0.7.1）

**存储**：`data/relay_identity.json`
```json
{
  "private_key_hex": "...",
  "public_key_hex": "...",
  "did": "did:web:relay.agentnexus.top",
  "created_at": 1711000000.0
}
```

**端点**：
- `GET /.well-known/did.json` — 返回 Relay 自身的 DID Document
- `GET /resolve/{did}` — 解析注册到 Relay 的 Agent DID

**域名配置优先级**：`--host` 参数 > `RELAY_HOST` 环境变量 > 默认值

## RuntimeVerifier 信任体系

```
L1  DID 可解析，无 cert               permissions: [discover, read]        spending: $0
L2  + 任意有效 cert                   permissions: + message               spending: $10
L3  + trusted CA cert                permissions: + transact              spending: $100
L4  + trusted CA entity_verified      permissions: + delegate              spending: $1000
```

多 CA 架构：`trusted_cas = {ca_did: pubkey_hex}`，N 个 CA 并列，各自独立验签。
Giskard CA 集成：`{"did:agent:giskard_ca": "<hex>"}` → `payment_verified` cert → L3。

**HTTP 入口：** `POST /runtime/verify`
```json
{ "agent_did": "did:agentnexus:z...", "agent_public_key": "<hex>", "trusted_cas": {} }
```

## Governance Attestation（v0.9.6）

集成外部治理服务（MolTrust/APS）的 `validate-capabilities` API：

```bash
# 调用治理服务验证能力
curl -X POST http://localhost:8765/governance/validate \
  -H "Content-Type: application/json" \
  -d '{
    "agent_did": "did:agentnexus:z...",
    "requested_capabilities": [{"scope": "data:read"}]
  }'
```

**GovernanceAttestation 结构：**
```json
{
  "signal_type": "governance_attestation",
  "issuer": "api.moltrust.ch",
  "subject": "did:agentnexus:z...",
  "decision": "permit",
  "scopes": ["data:read"],
  "trust_score": 75,
  "passport_grade": 2,
  "jws": "eyJhbGciOiJFZERTQSIs..."
}
```

**三维信任评分：**
```
trust_score = base_score(L级) + behavior_delta + attestation_bonus
```

| 分量 | 来源 | 范围 |
|------|------|------|
| base_score | L 级映射 | 15/40/70/95 |
| behavior_delta | 交互行为 | -20 ~ +20 |
| attestation_bonus | 治理认证 | 0 ~ +15 |

## Certification 格式

```json
{
  "version": "1.0",
  "issuer": "did:agent:giskard_ca",
  "issuer_pubkey": "<ed25519_hex>",
  "claim": "payment_verified",
  "evidence": "arb:0x<txhash>",
  "issued_at": 1711000000.0,
  "signature": "<ed25519_sig_hex>"
}
```

- `evidence` 只放链上交易哈希，`issuer_pubkey` 是独立字段（不拼接）
- certifications 是 NexusProfile 的顶层字段，第三方追加不影响 content 签名

## 常用命令

```bash
python main.py node start                      # 启动 Daemon :8765
python main.py node mcp --name "TestAgent"     # 启动 MCP 并注册新 DID
python main.py test                            # 运行全部 301 个测试
python main.py relay start                     # 启动 Relay :9000（需 Redis）
python main.py relay start --host my.domain    # 启动 Relay 并指定域名（用于 did:web）
python main.py agent export <did> --output agent.key --password pw
python main.py agent import agent.key --password pw
python main.py agent profile <did>             # 调 daemon HTTP 生成签名名片

# 治理服务测试（需要 API Key）
export MOLTRUST_API_KEY="mt_xxx"
python scripts/cross_verify_demo.py            # Cross-verify 演示
```

## Workflow Rules

- **Git push 顺序**：本地测试通过 → 线上测试通过 → 再 commit + push
- 不能只跑单元测试就 push，需要手动线上联调验证后再提交
- 新功能开发前查 `docs/requirements.md` + `docs/design.md`，开发中更新 `docs/wip.md`，完成后更新 `docs/devlog.md` + `CHANGELOG.md` + `docs/roadmap.md`
- 新架构决策写 ADR（`docs/adr/`），经评审流程（`docs/processes/design-review.md`）后标记"已采纳"
