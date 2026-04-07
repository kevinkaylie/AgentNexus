# AgentNexus × Giskard Integration — Technical Confirmation

**AgentNexus × Giskard 集成技术确认**

---

## What We've Understood / 我们已理解的

Based on your feedback, here's our understanding of the integration:

根据你们的反馈，我们对集成的理解如下：

### ✅ Agreed / 已确认

| Item | Decision |
|------|----------|
| **CA Architecture** | Single dedicated CA: `did:agent:giskard_ca` |
| **Evidence Format** | `"arb:0x<txhash>"` (tx hash only; issuer pubkey is a separate field in the certification) |
| **Memory Keying** | `{did}:{session_id}` for Giskard Memory namespace |
| **Verification Method** | CA public key pre-configured in AgentNexus trusted CA list (local lookup, no network resolution needed) |
| **Service Discovery** | Giskard services can register as `is_public=True` agents (optional, for future) |

| 项目 | 决定 |
|------|------|
| **CA 架构** | 单一专用 CA：`did:agent:giskard_ca` |
| **Evidence 格式** | `"arb:0x<txhash>"`（仅交易哈希；issuer pubkey 是认证中的独立字段）|
| **记忆索引** | `{did}:{session_id}` 用于 Giskard Memory 命名空间 |
| **验证方式** | CA 公钥预置到 AgentNexus trusted CA 列表（本地查找，无需网络解析）|
| **服务发现** | Giskard 服务可注册为 `is_public=True` 的 Agent（可选，后续）|

---

## What We Need From You / 需要你们提供的

### 1. CA Public Key / CA 公钥（必需）

**Q:** Please provide the hex-encoded Ed25519 public key for `did:agent:giskard_ca`.

We will pre-configure this key in our nodes' trusted CA list. All certifications signed by this key will be cryptographically verified locally.

**问：** 请提供 `did:agent:giskard_ca` 的十六进制编码 Ed25519 公钥。

我们将把此公钥预置到节点的可信 CA 列表中。所有由此密钥签发的认证将在本地进行密码学验证。

---

### 2. Claim Values / Claim 值

**Q:** What are the exact `claim` string values that Giskard CA will issue?

Examples we've discussed:
- `"payment_verified"` — what else?

**问：** Giskard CA 将签发的准确 `claim` 字符串值是什么？

我们讨论过的例子：
- `"payment_verified"` — 还有其他的吗？

---

### 3. Gatekeeper Behavior / Gatekeeper 行为

**Q:** When an agent presents a valid certification with `claim: "payment_verified"` from `did:agent:giskard_ca`:

- **Option A:** Auto-approve (skip PENDING state, let the agent through immediately)
- **Option B:** Add trust score only (still go through normal Gatekeeper flow)

Which behavior do you prefer?

**问：** 当一个 Agent 出示来自 `did:agent:giskard_ca` 且 `claim: "payment_verified"` 的有效认证时：

- **方案 A：** 自动批准（跳过 PENDING 状态，直接放行）
- **方案 B：** 仅增加信任分（仍然走正常 Gatekeeper 流程）

你们希望哪种行为？

---

### 4. Certification Example / 认证示例

**Q:** Can you provide a complete example of a certification JSON that Giskard CA would issue? This helps us verify our parsing and validation logic.

Expected format (based on our proposal):

```json
{
  "issuer": "did:agent:giskard_ca",
  "issuer_pubkey": "<hex>",
  "claim": "payment_verified",
  "evidence": "arb:0x<txhash>",
  "issued_at": 1711000000.0,
  "signature": "<issuer's Ed25519 signature over {did, claim, evidence, issued_at}>"
}
```

**问：** 能否提供一个 Giskard CA 将签发的完整认证 JSON 示例？这有助于我们验证解析和验证逻辑。

期望格式（基于我们的提案）：

```json
{
  "issuer": "did:agent:giskard_ca",
  "issuer_pubkey": "<hex>",
  "claim": "payment_verified",
  "evidence": "arb:0x<txhash>",
  "issued_at": 1711000000.0,
  "signature": "<issuer 对 {did, claim, evidence, issued_at} 的 Ed25519 签名>"
}
```

---

## Summary / 总结

| What we need / 需要的 | Status / 状态 |
|----------------------|--------------|
| CA public key (hex) / CA 公钥（十六进制）| ⏳ Waiting / 等待中 |
| Claim values / Claim 值 | ⏳ Waiting / 等待中 |
| Gatekeeper behavior preference / Gatekeeper 行为偏好 | ⏳ Waiting / 等待中 |
| Certification JSON example / 认证 JSON 示例 | ⏳ Waiting / 等待中 |

Once we have these, we can implement the integration immediately.

一旦收到这些信息，我们可以立即实现集成。

---

*AgentNexus / 2026-03-27*