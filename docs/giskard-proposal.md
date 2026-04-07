# AgentNexus × Giskard Integration Proposal

**中文版在下方 | [English version first](#english)**

---

<a id="english"></a>

## English

### Summary

We see a natural two-layer integration between AgentNexus and Giskard:

- **AgentNexus** = identity + routing + discovery (the "address" layer)
- **Giskard** = memory + payments + on-chain marks (the "economy" layer)

This proposal outlines concrete technical changes on the AgentNexus side and the integration points we'd like to align on.

---

### What We're Building in v0.5

#### 1. Session Management (solving "every conversation is new")

Currently, messages between agents are stateless — each message is independent with no conversation context. In v0.5, we're adding:

```
send_message(
  from_did="did:agent:aaa",
  to_did="did:agent:bbb",
  content="Please continue translating the next paragraph",
  session_id="sess_abc123def456",    # NEW: conversation identifier
  reply_to=5                          # NEW: which message this replies to
)
```

- First message in a conversation: omit `session_id` → Daemon auto-generates one
- Subsequent messages: include the same `session_id` → both sides know it's the same conversation
- New MCP tool `get_session(session_id)` → retrieve full conversation history
- Fully compatible with offline messaging (async store-and-forward)

**Integration point for Giskard**: Giskard Memory's `/store_direct` + `/recall_direct` could key on `session_id` to persist conversation context. An agent with a DID could store/recall session state via Giskard Memory, achieving cross-session continuity without custom infrastructure.

#### 2. Multi-Party Certification System (solving "who can I trust?")

Current problem: DIDs are self-sovereign — an agent can generate a new DID at zero cost, meaning there's no trust signal. We're adding a **certifications** layer to NexusProfile:

```json
{
  "header": { "did": "...", "pubkey": "...", "version": "1.0" },
  "content": { "name": "TranslateBot", ... },
  "signature": "<Ed25519 over content>",
  "certifications": [
    {
      "issuer": "did:agent:ca_giskard",
      "issuer_pubkey": "ed25519_hex",
      "claim": "payment_verified",
      "evidence": "mark:GENESIS:pioneer-001",
      "issued_at": 1711000000.0,
      "signature": "<issuer's Ed25519 over {did, claim, evidence, issued_at}>"
    }
  ]
}
```

Key design decisions:
- **Certifications are a top-level field**, not inside `content` — so third parties can add certifications without requiring the agent to re-sign its profile
- **Each certification is independently signed** by the issuer's Ed25519 key
- **Trust is computed by the verifier**, not declared by the certified agent — each agent weights issuers differently based on its own policy
- **N certifiers per agent** — decentralized, no single CA

**This is exactly where Giskard Marks fit in.** The formula `S(A) = ΣVerify(Sig_Provider)` maps directly: an agent's trust score = sum of all verifiable third-party signed evidence. No relay can forge or tamper with scores.

---

### Proposed Integration Architecture

```
AgentNexus DID          →  Stable agent address ("who I am")
AgentNexus Session      →  Conversation context ("what we're discussing")
AgentNexus Certifications → Verifiable trust evidence ("why you should trust me")
│
├── Giskard Marks (on-chain)  →  Immutable behavioral record
├── Giskard Memory            →  Persistent knowledge (keyed by DID + session)
└── Giskard Payments          →  Economic history (strongest trust signal)
```

Concrete integration points:

| AgentNexus Side | Giskard Side | Integration |
|----------------|-------------|-------------|
| `did:agent:<hex>` | `agent_id` in Giskard | Map DID → Giskard agent identity. Agent registers once with DID, carries payment history across sessions/machines |
| `certifications[]` in NexusProfile | Giskard Marks | A Mark becomes a certification entry: `{issuer: "did:agent:giskard_ca", claim: "GENESIS", evidence: "arb:0x...", signature: "..."}` |
| `session_id` in messages | Giskard Memory namespace | Memory keyed by `{did}:{session_id}` for session-specific recall |
| `search_agents(keyword)` | Giskard service discovery | Giskard services register as `is_public=True` agents with capabilities like `Memory`, `Search`, `Payment` |
| Semantic Gatekeeper | Payment verification | Gatekeeper auto-approves agents with `payment_verified` certification from Giskard |

---

### Joint Demo Proposal

**Scenario**: An agent discovers and pays for a translation service through the network.

```
1. Agent A registers with AgentNexus DID: did:agent:aaa
2. Agent A: search_agents(keyword="Translate")
   → Finds TranslateBot (did:agent:ttt) via federated relay lookup
3. Agent A: send_message(to_did="ttt", content="Translate: hello world")
   → Auto-generates session_id="sess_xxx"
4. TranslateBot checks A's certifications:
   → Has Giskard payment_verified mark? → Process immediately
   → No mark? → Request payment via Lightning/Arbitrum
5. Agent A pays → Giskard issues a Mark → Mark becomes a certification on A's NexusProfile
6. Next interaction: A's certification is already there → trusted, skip payment check
7. Full conversation history available via get_session("sess_xxx")
```

---

### Timeline

| Phase | AgentNexus | Giskard | Target |
|-------|-----------|---------|--------|
| v0.5 | Session management + Certifications spec | Review certification format, confirm Mark → certification mapping | 2 weeks |
| v0.6 | Key export/import ("soul portability") | DID → Giskard agent_id mapping | 4 weeks |
| Demo | Joint demo: discover → certify → pay → trust | Giskard services as public agents on AgentNexus relay | 6 weeks |

---

### Open Questions for Alignment

1. **Mark → Certification mapping**: What fields from a Giskard Mark should we include in the `evidence` field? Is the Arbitrum transaction hash sufficient, or should we include the full Mark metadata?

2. **Giskard as Certification Authority**: Should Giskard run a dedicated CA agent (`did:agent:giskard_ca`) that signs certifications, or should each Giskard service sign its own?

3. **Memory keying**: For Giskard Memory integration, is `{did}:{session_id}` a good key structure, or do you prefer a different namespace scheme?

4. **Service registration**: Would Giskard services be willing to register as `is_public=True` agents on the AgentNexus relay network, making them discoverable via `search_agents()`?

Both projects are Apache 2.0. Looking forward to digging into the technical integration.

---

---

<a id="chinese"></a>

## 中文版

### 概要

AgentNexus 和 Giskard 天然形成两层互补：

- **AgentNexus** = 身份 + 路由 + 发现（"地址"层）
- **Giskard** = 记忆 + 支付 + 链上凭证（"经济"层）

本提案描述 AgentNexus 侧的具体技术变更，以及我们希望对齐的集成点。

---

### v0.5 我们在做什么

#### 1. 会话管理（解决"每次都是新对话"）

当前 Agent 间消息是无状态的——每条消息独立，没有对话上下文。v0.5 新增：

```
send_message(
  from_did="did:agent:aaa",
  to_did="did:agent:bbb",
  content="请继续翻译下一段",
  session_id="sess_abc123def456",    # 新增：会话标识
  reply_to=5                          # 新增：回复哪条消息
)
```

- 首条消息不传 session_id → Daemon 自动生成
- 后续消息带同一 session_id → 双方知道是同一段对话
- 新增 MCP 工具 `get_session(session_id)` → 查询完整会话历史
- 完全兼容离线消息（异步存储转发）

**Giskard 集成点**：Giskard Memory 可以按 `session_id` 存取会话上下文。Agent 用 DID 注册后，通过 Giskard Memory 实现跨会话记忆持久化。

#### 2. 多方认证体系（解决"谁可以信任"）

当前问题：DID 是自主生成的，Agent 可以零成本换 DID，没有信任信号。我们在 NexusProfile 中新增 **certifications** 层：

```json
{
  "header": { "did": "...", "pubkey": "...", "version": "1.0" },
  "content": { "name": "TranslateBot", ... },
  "signature": "<Ed25519 签名>",
  "certifications": [
    {
      "issuer": "did:agent:ca_giskard",
      "issuer_pubkey": "ed25519_hex",
      "claim": "payment_verified",
      "evidence": "mark:GENESIS:pioneer-001",
      "issued_at": 1711000000.0,
      "signature": "<issuer 对 {did, claim, evidence, issued_at} 的 Ed25519 签名>"
    }
  ]
}
```

关键设计：
- **certifications 是顶层字段**，不在 content 内——第三方可以追加认证而无需 Agent 重新签名
- **每条认证独立签名**
- **信任分由验证方计算**，不由被认证方声明
- **一个 Agent 可有 N 个认证方**——去中心化

**这正是 Giskard Marks 的接入点。** 公式 `S(A) = ΣVerify(Sig_Provider)` 直接映射：信用 = 所有可验证的第三方签名证据之和。Relay 无法伪造或篡改。

---

### 集成架构

```
AgentNexus DID          →  稳定地址（"我是谁"）
AgentNexus Session      →  会话上下文（"我们在聊什么"）
AgentNexus Certifications → 可验证信任证据（"为什么信任我"）
│
├── Giskard Marks (链上)  →  不可篡改的行为记录
├── Giskard Memory        →  持久记忆（按 DID + session 索引）
└── Giskard Payments      →  经济历史（最强信任信号）
```

| AgentNexus 侧 | Giskard 侧 | 集成方式 |
|---------------|------------|---------|
| `did:agent:<hex>` | Giskard agent_id | DID 映射到 Giskard 身份，注册一次即可跨会话/跨机器 |
| NexusProfile `certifications[]` | Giskard Marks | Mark 成为一条 certification 条目 |
| 消息中的 `session_id` | Giskard Memory namespace | 按 `{did}:{session_id}` 索引记忆 |
| `search_agents(keyword)` | Giskard 服务发现 | Giskard 服务注册为 `is_public=True` 的 Agent |
| 语义门禁 Gatekeeper | 支付验证 | 有 `payment_verified` 认证的 Agent 自动放行 |

---

### 联合 Demo 方案

```
1. Agent A 用 AgentNexus DID 注册
2. search_agents("Translate") → 联邦查询找到 TranslateBot
3. send_message → 自动生成 session_id
4. TranslateBot 检查 A 的 certifications：
   → 有 Giskard payment_verified？→ 直接服务
   → 没有？→ 要求 Lightning/Arbitrum 支付
5. A 支付 → Giskard 发放 Mark → Mark 写入 A 的 NexusProfile certifications
6. 下次交互：A 已有认证 → 可信，跳过支付检查
7. 完整对话历史通过 get_session("sess_xxx") 获取
```

---

### 时间线

| 阶段 | AgentNexus | Giskard | 目标 |
|------|-----------|---------|------|
| v0.5 | 会话管理 + 认证规范 | 审核认证格式，确认 Mark→certification 映射 | 2 周 |
| v0.6 | 密钥导出/导入 | DID→Giskard agent_id 映射 | 4 周 |
| Demo | 联合演示 | Giskard 服务作为公开 Agent 接入 | 6 周 |

---

### 待对齐的开放问题

1. **Mark → Certification 映射**：Giskard Mark 的哪些字段应写入 `evidence`？Arbitrum 交易哈希够用，还是需要完整 Mark 元数据？
2. **Giskard 作为认证方**：Giskard 运行一个统一 CA Agent（`did:agent:giskard_ca`）签发认证，还是每个服务各自签？
3. **Memory 索引**：`{did}:{session_id}` 作为 Giskard Memory 的 key 结构是否合适？
4. **服务注册**：Giskard 服务是否愿意注册为 AgentNexus relay 网络上的 `is_public=True` Agent？
