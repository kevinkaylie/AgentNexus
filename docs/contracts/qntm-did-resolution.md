# 接口契约：QNTM Working Group — DID Resolution v1.0

## 基本信息

| 字段 | 值 |
|------|---|
| 合作方 | QNTM Working Group (@vessenes) |
| 接口名称 | DID Resolution v1.0 |
| 协议版本 | 1.0.0 |
| 状态 | 已对齐（v1.0 RATIFIED, 4 founding members signed off, 2026-03-24） |
| 最后更新 | 2026-03-27 |

## 数据格式

### 解析接口

所有符合规范的实现必须提供以下接口：

```
resolve_did(did_uri: string) → { public_key: bytes(32), method: string, metadata: map }
```

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `did_uri` | string | DID URI 字符串（如 `did:web:example.com`、`did:key:z6Mk...`） |

#### 返回值

| 字段 | 类型 | 说明 |
|------|------|------|
| `public_key` | bytes(32) | 32 字节 Ed25519 公钥，必须恰好 32 字节 |
| `method` | string | DID 方法名（如 `"web"`、`"key"`、`"aps"`、`"agentid"`） |
| `metadata` | map | 方法特定的元数据，可为空；应包含信任相关字段（trust score、delegation chain depth 等） |

### 支持的 DID 方法

| 方法 | 级别 | 解析算法 |
|------|------|---------|
| `did:web` | REQUIRED | 解析 `https://<domain>/.well-known/did.json`，提取 Ed25519 公钥 |
| `did:key` | REQUIRED | 解码 multibase (z-prefix = base58btc)，校验 multicodec 前缀 `0xed01`，提取 32 字节公钥 |
| `did:aps` | RECOMMENDED | 与 `did:key` 相同的字节布局（multicodec `0xed01`），兼容旧版 raw hex 格式 |
| `did:agentid` | RECOMMENDED | 本地缓存查找或远程 API 查询 `https://getagentid.dev/api/v1/agents/<id>/certificate` |

### sender_id 推导

从解析得到的公钥推导 sender_id：

```
sender_id = SHA-256(public_key)[0:16]
```

- 产生 16 字节（128 位）标识符
- 文本显示时使用小写十六进制编码（32 字符）
- 必须与 QSP-1 信封的 `sender` 字段匹配

### 请求（DID 解析）

```json
{
  "action": "resolve_did",
  "did_uri": "did:web:relay.agentnexus.top"
}
```

### 响应（解析结果）

```json
{
  "public_key": "<32_bytes_ed25519_hex>",
  "method": "web",
  "metadata": {
    "did_document_url": "https://relay.agentnexus.top/.well-known/did.json",
    "verification_method_type": "Ed25519VerificationKey2020"
  }
}
```

## 认证方式

### DID 密码学验证

1. **Ed25519 multicodec 前缀**：`0xed01`（2 字节），用于 `did:key` 和 `did:aps` 方法的自描述编码
2. **did:web 公钥提取优先级**（按顺序检查 `verificationMethod`）：
   - `publicKeyMultibase` + `Ed25519VerificationKey2020`：解码 base58btc（去 `z` 前缀），去 2 字节 multicodec 前缀
   - `publicKeyBase58` + `Ed25519VerificationKey2018`：直接 base58 解码
   - `publicKeyJwk` + `kty: "OKP"`, `crv: "Ed25519"`：base64url 解码 `x` 字段
3. **QSP-1 信封验证**：当信封包含 `did` 字段时，接收方必须解析 DID → 公钥 → 计算 sender_id → 与信封 `sender` 字段比对，不匹配则拒绝消息

### HTTP 要求（did:web）

- 必须使用 HTTPS
- 必须设置描述性 `User-Agent` 头（部分 CDN 会拦截默认 UA）
- 应跟随重定向（最多 3 跳）
- 应设置 10 秒超时

## 错误处理约定

| 错误码 | 含义 | 处理方式 |
|--------|------|---------|
| `did_not_found` | DID 无法解析（网络错误、404、DNS 失败） | 返回解析失败，消息排队等待网络恢复后重试 |
| `key_type_unsupported` | 解析到的密钥不是 Ed25519 | 返回错误，不回退到未验证密钥 |
| `key_extraction_failed` | DID Document 存在但密钥提取失败（verificationMethod 格式错误） | 返回错误，记录 DID Document 详情供调试 |
| `method_unsupported` | DID 方法不被当前解析器支持 | 返回错误，提示支持的方法列表 |

### 安全约束

- 网络分区时，**不得**回退到未验证的密钥
- 解析缓存 TTL 建议 3600 秒（1 小时），不应无限期缓存
- 必须验证 multicodec 前缀为 `0xed01`，防止密钥混淆攻击

### 错误场景示例

**DID 未找到：**
```python
from agent_net.common.did import DIDResolver, DIDNotFoundError

resolver = DIDResolver()
try:
    result = await resolver.resolve("did:web:nonexistent.example.com")
except DIDNotFoundError:
    # DID 无法解析，消息排队等待重试
    log.warning("DID resolution failed, queuing message for retry")
```

**密钥类型不支持：**
```python
from agent_net.common.did import DIDKeyTypeUnsupportedError

try:
    result = await resolver.resolve("did:key:z6LSbysY2xFMRpGMhb7tFTLMpeuPRaqaWM1yECx2AtzE3KCc")
except DIDKeyTypeUnsupportedError:
    # 非 Ed25519 密钥，拒绝
    log.warning("Resolved key is not Ed25519")
```

## 完整示例

### 请求示例 1：解析 did:web

```python
from agent_net.common.did import DIDResolver

resolver = DIDResolver()
result = await resolver.resolve_did("did:web:relay.agentnexus.top")
```

请求：
```json
{
  "action": "resolve_did",
  "did_uri": "did:web:relay.agentnexus.top"
}
```

响应：
```json
{
  "public_key": "3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048a18b59da29",
  "method": "web",
  "metadata": {
    "did_document_url": "https://relay.agentnexus.top/.well-known/did.json",
    "verification_method_type": "Ed25519VerificationKey2020",
    "service_endpoints": ["https://relay.agentnexus.top"]
  }
}
```

### 请求示例 2：解析 did:key

```python
result = await resolver.resolve_did("did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK")
```

请求：
```json
{
  "action": "resolve_did",
  "did_uri": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
}
```

响应：
```json
{
  "public_key": "2c70e12b7a0646f92279f427c7b38e7334d8ebc4a09f0ba2e0c0e217b0264e4e",
  "method": "key",
  "metadata": {}
}
```

### 请求示例 3：sender_id 推导

```python
from agent_net.common.did import DIDResolver

resolver = DIDResolver()
result = await resolver.resolve("did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK")
sender_id = resolver.derive_sender_id(result.public_key)
# sender_id = SHA-256(public_key)[0:16] → 32 字符小写 hex
```

响应：
```json
{
  "public_key": "2c70e12b7a0646f92279f427c7b38e7334d8ebc4a09f0ba2e0c0e217b0264e4e",
  "sender_id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
}
```

### 请求示例 4：错误响应

```json
{
  "action": "resolve_did",
  "did_uri": "did:web:nonexistent.example.com"
}
```

错误响应：
```json
{
  "error": "did_not_found",
  "did_uri": "did:web:nonexistent.example.com",
  "message": "Failed to fetch DID Document: HTTP 404"
}
```

## AgentNexus 实现

| 组件 | 路径 | 说明 |
|------|------|------|
| DIDResolver | `agent_net/common/did.py` | 主解析器，支持 4 种 DID 方法 |
| DIDResolutionResult | `agent_net/common/did.py` | 解析结果数据类，含 `to_wg_format()` 方法 |
| DIDGenerator | `agent_net/common/did.py` | DID 生成器（`did:agent`、`did:agentnexus`） |
| 测试向量 | `specs/test-vectors/did-resolution.json` | WG 规范一致性测试向量 |
| 测试用例 | `tests/test_did_resolution.py` | DID 解析单元测试 |

### 跨项目验证状态

| 源 | 目标 | 状态 |
|----|------|------|
| qntm → `did:web:trust.arkforge.tech` | ArkForge | ✅ 已验证 |
| ArkForge → `did:web:inbox.qntm.corpo.llc` | qntm | ✅ 已验证 |
| AgentID → `did:aps:z6QQ5...` | APS | ✅ 已验证 |
| APS → `did:agentid:...` | AgentID | ✅ 已验证 |
| qntm → `did:web:the-agora.dev` | Agent Agora | ✅ 已验证 |

## 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 1.0.0 | 2026-03-27 | 初始版本，基于 WG DID Resolution v1.0 RATIFIED 规范 |

## 参考文档

- [WG DID Resolution v1.0 规范](../../specs/working-group/did-resolution.md)
- [DID 解析测试向量](../../specs/test-vectors/did-resolution.json)
- [ADR-001: DID 格式选择](../adr/001-did-format-selection.md)
