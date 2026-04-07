# 接口契约：Giskard — CA 认证签发与验证

## 基本信息

| 字段 | 值 |
|------|---|
| 合作方 | Giskard |
| 接口名称 | CA 认证签发与验证 |
| 协议版本 | 1.0.0 |
| 状态 | 草稿（等待 Giskard 提供 CA pubkey） |
| 最后更新 | 2026-03-27 |

## 数据格式

### Certification JSON

Giskard CA 签发的认证采用 AgentNexus Certification 格式，作为 `NexusProfile.certifications[]` 的条目存储。认证是顶层字段，第三方追加不影响 Agent 自身的 `content` 签名。

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

#### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `version` | string | 是 | 认证格式版本，当前固定为 `"1.0"` |
| `issuer` | string | 是 | 签发方 DID，Giskard CA 固定为 `"did:agent:giskard_ca"` |
| `issuer_pubkey` | string | 是 | 签发方 Ed25519 公钥的十六进制编码（64 字符） |
| `claim` | string | 是 | 认证声明类型，如 `"payment_verified"`、`"entity_verified"` |
| `evidence` | string | 是 | 链上证据，格式为 `"arb:0x<txhash>"`（Arbitrum 交易哈希） |
| `issued_at` | float | 是 | 签发时间戳（Unix epoch，秒） |
| `signature` | string | 是 | Ed25519 签名的十六进制编码（128 字符） |

### 签名载荷

签名载荷为以下四个字段的 canonical JSON（`sort_keys=True, separators=(',',':')`）：

```json
{"claim":"payment_verified","did":"did:agentnexus:z6Mk...","evidence":"arb:0xabc123...","issued_at":1711000000.0}
```

> 注意：签名载荷中包含被认证 Agent 的 `did`，但该字段不出现在 certification JSON 本身中——它来自 NexusProfile 的 `header.did`。

### 请求（认证签发）

Giskard CA 在链上支付确认后，构造并签名 certification JSON，附加到目标 Agent 的 NexusProfile：

```json
{
  "action": "add_certification",
  "target_did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "certification": {
    "version": "1.0",
    "issuer": "did:agent:giskard_ca",
    "issuer_pubkey": "<ed25519_hex>",
    "claim": "payment_verified",
    "evidence": "arb:0xabc123def456789...",
    "issued_at": 1711000000.0,
    "signature": "<ed25519_sig_hex>"
  }
}
```

### 响应（认证验证结果）

AgentNexus RuntimeVerifier 验证认证后返回信任等级：

```json
{
  "did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "trust_level": 3,
  "trust_score": 75.0,
  "permissions": ["discover", "read", "message", "transact"],
  "certifications_verified": 1,
  "resolution_status": "resolved",
  "timestamp": "2026-03-27T12:00:00Z"
}
```

## 认证方式

### Ed25519 签名验证

1. Giskard 运行单一专用 CA Agent：`did:agent:giskard_ca`
2. CA 公钥（Ed25519）预置到 AgentNexus 节点的 `trusted_cas` 配置中：
   ```json
   {
     "trusted_cas": {
       "did:agent:giskard_ca": "<ca_pubkey_hex>"
     }
   }
   ```
3. 验证流程：
   - 从 certification 中提取 `issuer` 和 `issuer_pubkey`
   - 检查 `issuer` 是否在 `trusted_cas` 列表中
   - 检查 `issuer_pubkey` 是否与 `trusted_cas` 中预置的公钥一致
   - 构造 canonical JSON 签名载荷：`{"claim":..., "did":..., "evidence":..., "issued_at":...}`
   - 使用 `issuer_pubkey` 验证 Ed25519 签名
4. 验证通过后，根据 `claim` 类型提升信任等级：
   - `payment_verified` → L3（permissions: discover, read, message, transact）
   - `entity_verified` → L4（permissions: discover, read, message, transact, delegate）

### 信任等级映射

| 等级 | 条件 | 权限 | 消费限额 |
|------|------|------|---------|
| L1 | DID 可解析，无 cert | discover, read | $0 |
| L2 | + 任意有效 cert | + message | $10 |
| L3 | + trusted CA cert（如 `payment_verified`） | + transact | $100 |
| L4 | + trusted CA `entity_verified` | + delegate | $1000 |

## 错误处理约定

| 错误码 | 含义 | 处理方式 |
|--------|------|---------|
| `BadSignatureError` | Ed25519 签名验证失败 | 拒绝该 certification，信任等级不提升；记录日志供审计 |
| `KeyError` | certification JSON 缺少必填字段 | 跳过该 certification，返回解析错误详情 |
| `ValueError` | 字段格式错误（如 pubkey 非合法 hex、issued_at 非数字） | 跳过该 certification，返回格式错误详情 |

### 错误场景示例

**签名无效：**
```python
from nacl.exceptions import BadSignatureError

try:
    verify_certification(cert, target_did)
except BadSignatureError:
    # certification 签名无效，不计入信任评估
    log.warning(f"Invalid certification from {cert['issuer']} for {target_did}")
```

**字段缺失：**
```python
try:
    claim = cert["claim"]
    evidence = cert["evidence"]
    issued_at = cert["issued_at"]
except KeyError as e:
    # 缺少必填字段
    log.warning(f"Missing field in certification: {e}")
```

## 完整示例

### 请求示例：签发认证

Agent A 在 Arbitrum 上完成支付后，Giskard CA 签发 `payment_verified` 认证：

```json
{
  "action": "add_certification",
  "target_did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "certification": {
    "version": "1.0",
    "issuer": "did:agent:giskard_ca",
    "issuer_pubkey": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
    "claim": "payment_verified",
    "evidence": "arb:0x7f3e8a2b1c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f",
    "issued_at": 1711000000.0,
    "signature": "e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3"
  }
}
```

### 响应示例：RuntimeVerifier 验证结果

AgentNexus 节点验证该 Agent 的信任等级：

```json
{
  "did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "trust_level": 3,
  "trust_score": 75.0,
  "permissions": ["discover", "read", "message", "transact"],
  "certifications_verified": 1,
  "resolution_status": "resolved",
  "timestamp": "2026-03-27T12:00:00Z",
  "details": {
    "did_resolved": true,
    "has_valid_cert": true,
    "has_trusted_ca_cert": true,
    "trusted_ca_issuer": "did:agent:giskard_ca",
    "claim": "payment_verified"
  }
}
```

## 待确认项

| 项目 | 状态 | 说明 |
|------|------|------|
| CA 公钥（Ed25519 hex） | ⏳ 等待中 | 需要 Giskard 提供 `did:agent:giskard_ca` 的公钥 |
| Claim 值列表 | ⏳ 等待中 | 已知 `payment_verified`，是否还有其他 claim 类型 |
| Gatekeeper 行为偏好 | ⏳ 等待中 | 方案 A（自动批准）或方案 B（仅增加信任分） |
| 认证 JSON 完整示例 | ⏳ 等待中 | 需要 Giskard 提供一个真实签名的示例用于验证解析逻辑 |

## 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 1.0.0 | 2026-03-27 | 初始草稿，基于 Giskard 集成提案和技术确认文档 |

## 参考文档

- [Giskard 集成提案](../giskard-proposal.md)
- [Giskard 集成技术确认](../giskard-integration-checklist.md)
- [ADR-004: 多 CA 认证架构](../adr/004-multi-ca-certification.md)
