# 接口契约：OATR — JWT Attestation 验证

## 基本信息

| 字段 | 值 |
|------|---|
| 合作方 | OATR (@FransDevelopment) |
| 接口名称 | JWT Attestation 验证 |
| 协议版本 | 0.1.0（草稿） |
| 状态 | 草稿 |
| 最后更新 | 2026-03-27 |

## 数据格式

### JWT Compact 格式

OATR Attestation 采用 JWT compact 格式（`header.payload.signature`），使用 EdDSA (Ed25519) 签名。

#### Header

```json
{
  "alg": "EdDSA",
  "typ": "JWT"
}
```

#### Payload

```json
{
  "iss": "<oatr_issuer_id>",
  "sub": "<agent_did>",
  "claim": "behavior_attested",
  "score": 85,
  "score_breakdown": {
    "response_rate": 0.95,
    "success_rate": 0.88,
    "uptime": 0.99
  },
  "iat": 1711000000,
  "exp": 1711086400
}
```

#### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `iss` | string | 是 | OATR 签发方标识（issuer ID） |
| `sub` | string | 是 | 被评估 Agent 的 DID |
| `claim` | string | 是 | 声明类型（如 `"behavior_attested"`、`"trust_scored"` 等） |
| `score` | integer | 否 | OATR 行为评分（0-100 连续评分） |
| `score_breakdown` | object | 否 | 评分细项（response_rate、success_rate、uptime 等） |
| `iat` | integer | 是 | 签发时间（Unix epoch，秒） |
| `exp` | integer | 是 | 过期时间（Unix epoch，秒） |

#### Signature

- 算法：EdDSA (Ed25519)
- 签名输入：`base64url(header) + "." + base64url(payload)` 的 UTF-8 字节
- 签名输出：Ed25519 签名的 base64url 编码

### 请求（JWT Attestation 提交）

外部 Agent 或 OATR 服务向 AgentNexus 节点提交 JWT Attestation 进行验证：

```json
{
  "action": "verify_jwt_attestation",
  "agent_did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "jwt": "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJvYXRyLWlzc3Vlci0wMDEiLCJzdWIiOiJkaWQ6YWdlbnRuZXh1czp6Nk1raGFYZ0JaRHZvdERrTDUyNTdmYWl6dGlHaUMyUXRLTEdwYm5uRUd0YTJkb0siLCJjbGFpbSI6ImJlaGF2aW9yX2F0dGVzdGVkIiwic2NvcmUiOjg1LCJpYXQiOjE3MTEwMDAwMDAsImV4cCI6MTcxMTA4NjQwMH0.<ed25519_signature_base64url>"
}
```

### 响应（验证结果）

```json
{
  "valid": true,
  "issuer": "oatr-issuer-001",
  "subject": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "claim": "behavior_attested",
  "score": 85,
  "expires_at": 1711086400,
  "trust_delta": {
    "attestation_bonus": 8.5,
    "applied_to": "trust_score"
  }
}
```

## 认证方式

### JWT 验签 (EdDSA)

1. 解析 JWT compact 格式，分离 header、payload、signature 三部分
2. 验证 header 中 `alg` 为 `"EdDSA"`，`typ` 为 `"JWT"`
3. 通过 OATR issuer 的公钥（Ed25519）验证签名
4. 检查 `exp` 是否已过期
5. 检查 `sub` 是否与目标 Agent DID 匹配

### OATR 公钥获取

- v0.8 阶段：通过 `did:web` 解析 OATR issuer 的 DID Document，提取 Ed25519 公钥
- v0.9 阶段：OATR issuer 注册到 Relay 的 `/.well-known/agent.json`，包含 `identity.did`、`public_key`、`oatr_issuer_id`

## AgentNexus 侧集成路线

### v0.8：did:web Quick Path（DID 互操作测试）

| 步骤 | 说明 |
|------|------|
| 1 | 验证 OATR 侧 `did:key` 解析 AgentNexus Ed25519 公钥 |
| 2 | 验证 AgentNexus 侧解析 OATR 的 attestation 基本格式 |
| 3 | 双向 DID 互操作确认 |

### v0.9：完整集成

| 功能 | 说明 |
|------|------|
| `verify_jwt_attestation()` | 新增 JWT attestation 验证函数，与 `verify_certification()` 并行 |
| trust_snapshot 导出 | `RuntimeVerification.to_oatr_snapshot()` → 输出 OATR `extensions.agent-trust` 标准格式 |
| 行为评分引擎 | trust_score 重构为 `base_score(L级) + behavior_delta + attestation_bonus`，兼容 OATR 0-100 连续评分 |
| Certification ↔ JWT 桥接 | AgentNexus cert 封装为 compact JWT / OATR JWT 解析为内部 cert，双向转换 |
| Claim 命名空间 | cert claim 改为 `"{namespace}:{claim}"` 格式（如 `oatr:behavior_attested`），防多 CA claim 冲突 |

## 错误处理约定

| 错误码 | 含义 | 处理方式 |
|--------|------|---------|
| `InvalidSignature` | JWT EdDSA 签名验证失败 | 拒绝该 attestation，不计入信任评估；记录日志 |
| `ExpiredToken` | JWT `exp` 字段已过期 | 拒绝该 attestation，提示需要重新获取 |
| `UnsupportedAlgorithm` | JWT header `alg` 不是 `"EdDSA"` | 拒绝该 attestation，仅支持 EdDSA (Ed25519) |
| `SubjectMismatch` | JWT `sub` 与目标 Agent DID 不匹配 | 拒绝该 attestation，防止跨 Agent 冒用 |
| `IssuerUnknown` | 无法解析 OATR issuer 的公钥 | 拒绝该 attestation，提示 issuer 未注册 |

### 错误场景示例

**签名无效：**
```python
try:
    result = verify_jwt_attestation(jwt_token, agent_did)
except InvalidSignature:
    log.warning(f"Invalid JWT signature for {agent_did}")
```

**Token 过期：**
```python
import time

payload = decode_jwt_payload(jwt_token)
if payload["exp"] < time.time():
    raise ExpiredToken(f"JWT expired at {payload['exp']}")
```

## 完整示例

### 请求示例：提交 JWT Attestation

OATR 为 Agent 签发行为评估 attestation，Agent 将其提交到 AgentNexus 节点：

```json
{
  "action": "verify_jwt_attestation",
  "agent_did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "jwt": "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJvYXRyLWlzc3Vlci0wMDEiLCJzdWIiOiJkaWQ6YWdlbnRuZXh1czp6Nk1raGFYZ0JaRHZvdERrTDUyNTdmYWl6dGlHaUMyUXRLTEdwYm5uRUd0YTJkb0siLCJjbGFpbSI6ImJlaGF2aW9yX2F0dGVzdGVkIiwic2NvcmUiOjg1LCJzY29yZV9icmVha2Rvd24iOnsicmVzcG9uc2VfcmF0ZSI6MC45NSwic3VjY2Vzc19yYXRlIjowLjg4LCJ1cHRpbWUiOjAuOTl9LCJpYXQiOjE3MTEwMDAwMDAsImV4cCI6MTcxMTA4NjQwMH0.<ed25519_signature_base64url>"
}
```

### 响应示例：验证通过

```json
{
  "valid": true,
  "issuer": "oatr-issuer-001",
  "subject": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "claim": "behavior_attested",
  "score": 85,
  "score_breakdown": {
    "response_rate": 0.95,
    "success_rate": 0.88,
    "uptime": 0.99
  },
  "expires_at": 1711086400,
  "trust_delta": {
    "attestation_bonus": 8.5,
    "applied_to": "trust_score"
  }
}
```

### 响应示例：验证失败

```json
{
  "valid": false,
  "error": "ExpiredToken",
  "message": "JWT expired at 1711086400, current time is 1711100000",
  "subject": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
}
```

### trust_snapshot 导出示例（v0.9）

AgentNexus 将信任评估结果导出为 OATR 标准格式：

```json
{
  "extensions": {
    "agent-trust": {
      "did": "did:agentnexus:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
      "trust_level": 3,
      "trust_score": 83.5,
      "base_score": 75.0,
      "behavior_delta": 0.0,
      "attestation_bonus": 8.5,
      "certifications_count": 2,
      "last_verified": "2026-03-27T12:00:00Z"
    }
  }
}
```

## 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 0.1.0 | 2026-03-27 | 初始草稿，定义 JWT 格式和验证流程 |

## 参考文档

- [产品路线图 v0.9 OATR 集成计划](../roadmap.md)
- [QNTM WG DID Resolution 规范](../../specs/working-group/did-resolution.md)
