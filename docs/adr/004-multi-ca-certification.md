# ADR-004: 多 CA 认证架构

## 状态

已采纳

## 日期

2026-03-26

## 背景

AgentNexus 中的 Agent 使用自主生成的 DID 作为身份标识，任何人都可以零成本创建新 DID。这意味着 DID 本身不携带信任信号——一个恶意 Agent 可以随时生成新身份。项目需要一套信任体系来区分不同 Agent 的可信程度。

核心需求：
1. **信任分层**：不同信任级别的 Agent 应有不同的权限（发现、消息、交易、委托）。
2. **去中心化**：不依赖单一认证机构，避免单点故障和权力集中。
3. **可扩展**：支持接入新的认证方（如 Giskard、OATR 等外部合作方）。
4. **独立验签**：认证信息可以离线验证，不依赖网络查询。

## 决策

采用多 CA 并列架构，配合四级信任体系：

### 信任级别

| 级别 | 条件 | 权限 | 消费限额 |
|------|------|------|---------|
| L1 | DID 可解析，无认证 | discover, read | $0 |
| L2 | + 任意有效认证 | + message | $10 |
| L3 | + 受信 CA 认证 | + transact | $100 |
| L4 | + 受信 CA entity_verified | + delegate | $1000 |

### 多 CA 架构

```python
trusted_cas = {ca_did: pubkey_hex}  # N 个 CA 并列
```

- 每个节点独立配置自己信任的 CA 列表。
- 各 CA 独立验签，互不依赖。
- 信任分由验证方（RuntimeVerifier）计算，不由被认证方声明。

### Certification 格式

Certifications 是 NexusProfile 的顶层字段（不在 `content` 签名内），第三方可追加认证而无需 Agent 重新签名：

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

- `evidence` 仅存放链上交易哈希，`issuer_pubkey` 是独立字段。
- 签名覆盖 `{did, claim, evidence, issued_at}`，可离线验证。

### Giskard CA 集成

```python
trusted_cas = {"did:agent:giskard_ca": "<hex>"}
```

Giskard CA 签发 `payment_verified` 认证 → Agent 信任级别提升至 L3。

## 理由

多 CA 架构的核心优势：

- **去中心化信任**：N 个 CA 并列，任何单一 CA 的失效不影响整体信任体系。每个节点可以根据自身策略选择信任哪些 CA。
- **可组合性**：信任分公式 `S(A) = ΣVerify(Sig_Provider)` 允许灵活组合多个认证来源。
- **独立验签**：每条认证包含 issuer 公钥和签名，任何人持有认证即可离线验证，无需查询 CA 服务器。
- **非侵入式**：certifications 作为 NexusProfile 的顶层字段，第三方追加认证不影响 Agent 自身的 content 签名。
- **渐进式信任**：四级信任体系允许 Agent 从零信任逐步积累信用，符合现实世界的信任建立过程。

### 考虑的替代方案

1. **单一 CA 架构** — 实现简单，但存在单点故障风险，且与去中心化理念矛盾。如果唯一的 CA 被攻破，整个信任体系崩溃。
2. **Web of Trust（信任网络）** — 类似 PGP 的互相签名模式，去中心化程度最高，但信任传递路径复杂，难以计算和解释信任分。
3. **链上信任（纯区块链）** — 所有认证上链，不可篡改，但增加了对区块链基础设施的依赖，且链上操作有延迟和成本。
4. **Certifications 放在 content 签名内** — 更强的完整性保证，但每次新增认证都需要 Agent 重新签名 profile，不利于第三方独立追加认证。

## 影响范围

- `agent_net/common/profile.py`：`create_certification()`、`verify_certification()` 函数，NexusProfile 的 `certifications` 顶层字段
- `agent_net/common/runtime_verifier.py`：`AgentNexusRuntimeVerifier`，L1-L4 信任级别计算
- `agent_net/node/daemon.py`：`POST /agents/{did}/certify`、`GET /agents/{did}/certifications`、`POST /runtime/verify` 端点
- `agent_net/node/mcp_server.py`：`certify_agent`、`get_certifications` MCP 工具
- `agent_net/storage.py`：certifications 数据存储

## 相关 ADR

- ADR-001: DID 格式选择（认证中的 issuer 和 agent DID 使用统一的 DID 格式）
- ADR-005: Gatekeeper 三模式设计（Gatekeeper 可结合认证信息进行访问控制决策）
