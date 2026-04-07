# ADR-008: did:meeet 跨平台桥接架构

## 状态

提议

## 日期

2026-04-04

## 背景

MEEET 平台有 1020 个 Agent，使用 `did:meeet:agent_{uuid}` 格式，密钥存储在 Solana 链上。AgentNexus 需要与这些 Agent 互操作，使其可被 x402 payer 发现并发起支付。

核心设计问题：

1. **桥接模式**：为 MEEET Agent 生成新的 did:agentnexus 密钥对，还是复用其 Ed25519 公钥？
2. **解析路径**：did:meeet 的解析走 Relay 还是 Daemon？
3. **Solana 依赖**：如何处理 Solana API 不可达的情况？
4. **信任映射**：MEEET reputation score 如何映射到 AgentNexus 信任体系？

与 MEEET 团队的技术对齐结论（2026-04-04）：
- **主权优先**：`did:meeet` → `did:agentnexus` 通过 Ed25519 密钥直接映射，不经过 APS passport
- **APS 可选**：APS passport 是治理层注解，不在身份链路上
- **试点验证**：先跑通 Ed25519 签名往返，再叠加治理层

## 决策

### 1. 映射模式：复用 MEEET Ed25519 公钥，不生成新密钥

```
did:meeet:agent_xxx
  └── Solana state → Ed25519 公钥 (32 bytes)
        └── 推导 did:agentnexus:z{base58btc(0xED01 || pubkey)}
              └── 同一把公钥，两个 DID 格式
```

不生成新密钥对的理由：
- MEEET Agent 的 Ed25519 私钥在其自己的环境中，AgentNexus 不托管
- 同一把公钥保证密码学层面的身份一致性——验签只需要一把公钥
- 符合"主权优先"原则：外部 DID 是身份源头，AgentNexus DID 是格式映射

### 2. 解析路径：Relay 侧解析，Daemon 回落

```
GET /resolve/did:meeet:agent_xxx
  │
  ├── Relay DIDResolver._resolve_meeet()
  │     ├── 查 Redis 缓存 relay:meeet:{did}
  │     │     └── 命中 → 返回缓存的 DID Document
  │     └── 未命中 → 查询 MEEET Solana state API
  │           ├── 成功 → 构建 DID Document + 写入 Redis 缓存（TTL 24h）
  │           └── 失败 → 返回 did_not_found 错误
  │
  └── Daemon /resolve/{did}
        └── 本地无 → 转发到 Relay → 同上流程
```

解析在 Relay 侧执行的理由：
- Relay 已有 Redis，适合缓存外部 API 结果
- Relay 是联邦网络的公共节点，其他 Daemon 都可以查询
- 避免每个 Daemon 都直连 Solana API

### 3. 桥接映射表（Redis 持久化）

```
Key:   relay:meeet:{did:meeet:agent_xxx}
Value: {
  "agentnexus_did": "did:agentnexus:z6Mk...",
  "pubkey_hex": "<ed25519_hex>",
  "meeet_reputation": 500,
  "x402_score": 72,
  "registered_at": 1711000000.0,
  "last_verified": 1711000000.0
}
TTL:   86400 (24h，自动刷新)
```

### 4. 批量注册流程

```
MEEET Agent 批量注册（1020 个）：

1. 前置：MEEET 平台方向 Relay 注册一个"桥接管理员"身份
   → MEEET 提交平台级 Ed25519 公钥到 Relay
   → Relay 将其写入 meeet_bridge_admins 列表（Redis 存储，键：meeet:admins）
   → 此密钥用于签名批量注册请求（平台级认证）

2. MEEET 侧：每个 Agent 用自己的 Ed25519 私钥签名 nonce
   → 证明 did:meeet 所有权（Agent 级认证）

3. Relay 侧：POST /meeet/batch-register
   → 验证请求级签名（平台管理员密钥）→ 拒绝未授权调用方
   → 逐条验证 Agent 签名（每个 Agent 的 Ed25519）→ 拒绝伪造条目
   → 从公钥推导 did:agentnexus
   → 写入 Redis 映射表
   → 注册到 ANPN directory（可被 lookup 发现）

4. 验证：GET /resolve/did:meeet:agent_xxx
   → 返回 DID Document（含 Ed25519 公钥 + meeet_reputation）
```

**平台管理员密钥注册接口：**
- `POST /meeet/admin/register` — 注册平台管理员密钥（需 Relay 本地信任的密钥签名，或通过 Relay 管理界面手动添加）
- `GET /meeet/admin/status` — 查询已注册的管理员列表（仅返回公钥指纹，不返回私钥）

两层认证设计：
- **平台级**：批量注册请求必须由 MEEET 桥接管理员密钥签名，防止任意第三方伪造批量注册
- **Agent 级**：每个 Agent 条目必须包含该 Agent 自己的 nonce 签名，防止平台方伪造单个 Agent 身份

这与 Relay 现有的 Ed25519 签名验证 + TOFU 绑定机制一致。

速率限制：批量注册端点限制 10 req/min per 管理员密钥，单次最大 100 条。

Relay 新增端点：
- `POST /meeet/register` — 单个 Agent 注册（Agent 自签名即可，无需平台管理员）
- `POST /meeet/batch-register` — 批量注册（需平台管理员签名 + 每条 Agent 签名）
- `GET /meeet/status` — 查询映射状态统计（公开，无需认证）

### 5. 信任评分映射（v0.8 短期方案）

MEEET reputation score（0-850+）线性映射到 x402 score（0-100）：

```
x402_score = min(100, 10 + (meeet_reputation / 850) * 82)
```

| MEEET Reputation | x402 Score | 含义 |
|-----------------|------------|------|
| 0 (NEW)         | 10         | 新注册，最低信任 |
| 200 (BEGINNER)  | 29         | 有基础交互历史 |
| 500             | 58         | 活跃用户 |
| 850+ (EXPERT)   | 92+        | 专家级 |

映射结果写入 DID Document metadata：

```json
{
  "didDocumentMetadata": {
    "source": "meeet_solana",
    "meeet_reputation_score": 500,
    "x402_score": 58
  }
}
```

v0.9 长期方案：reputation 映射到 `trust_score` 的 `behavior_delta` 分量，与 L 级信任体系解耦。

### 6. Solana API 不可达处理

- 首次解析：Solana 不可达 → 返回 `did_not_found`，不回退到未验证密钥
- 已缓存：Redis 缓存有效期内直接返回，不依赖 Solana
- 缓存过期：尝试刷新，失败则返回过期缓存 + `stale: true` 标记
- 批量注册：单个失败不影响其他，返回逐条结果

### 7. DID Document 结构

```json
{
  "@context": ["https://www.w3.org/ns/did/v1", "https://w3id.org/security/multikey/v1"],
  "id": "did:agentnexus:z6Mk...",
  "alsoKnownAs": ["did:meeet:agent_xxx"],
  "verificationMethod": [{
    "id": "#key-1",
    "type": "Multikey",
    "controller": "did:agentnexus:z6Mk...",
    "publicKeyMultibase": "z6Mk..."
  }],
  "authentication": ["#key-1"],
  "service": [
    {"id": "#relay", "type": "AgentRelay", "serviceEndpoint": "https://relay.agentnexus.top"},
    {"id": "#anpn", "type": "AgentService", "serviceEndpoint": "https://relay.agentnexus.top/relay/anpn-lookup/{did}/anpn", "protocol": "anpn/1.0"}
  ]
}
```

关键字段：
- `alsoKnownAs`：关联原始 `did:meeet` 标识符。符合 W3C DID Core §10.1 定义（字符串数组，每个元素为 URI），QNTM WG 规范未额外约束此字段
- `verificationMethod`：复用 MEEET 的 Ed25519 公钥
- `service`：包含 AgentRelay 和 AgentService（ADR-006 中 SDK 可发现的端点）

## 理由

### 为什么映射模式而不是代理模式

| 维度 | 映射模式（选定） | 代理模式 |
|------|----------------|---------|
| 密钥管理 | 复用 MEEET 密钥，不托管 | AgentNexus 生成新密钥，需托管 |
| 主权 | MEEET Agent 保持密钥主权 | 密钥主权转移到 AgentNexus |
| 验签 | 一把公钥，两个 DID 都能验 | 两把公钥，需要映射表才能关联 |
| 复杂度 | 低（公钥推导是确定性的） | 高（需要密钥托管 + 签名代理） |
| 安全风险 | 低（不持有他人私钥） | 高（托管私钥是攻击面） |

### 考虑的替代方案

1. **代理模式（为每个 MEEET Agent 生成新密钥对）** — AgentNexus 持有代理密钥，可以代替 MEEET Agent 签名。但违反"私钥不出户"原则，且引入密钥托管的安全风险。
2. **纯解析模式（不维护映射表）** — 每次解析都实时查询 Solana。简单但慢（Solana RPC 延迟 200-500ms），且 Solana 不可达时完全不可用。
3. **MEEET 侧注册 did:agentnexus** — 让 MEEET Agent 主动注册到 AgentNexus Relay。最干净，但需要 MEEET 侧改代码，增加对方工作量。作为 v0.9 的理想方案保留。

## 影响范围

- `agent_net/common/did.py`：`DIDResolver` 新增 `_resolve_meeet()` 方法
- `agent_net/relay/server.py`：新增 `/meeet/register`、`/meeet/batch-register`、`/meeet/status` 端点；`/resolve/{did}` 新增 meeet 分支
- Redis：新增 `relay:meeet:*` 键空间
- 需要 MEEET 团队提供：Solana state API 端点 URL、Agent 列表格式、reputation score 查询接口

## 测试要求

| 测试场景 | 类型 | 说明 |
|---------|------|------|
| did:meeet 解析返回正确 DID Document | 集成 | 含 `alsoKnownAs`、公钥、service |
| Solana API 不可达时返回 `did_not_found` | 单元 | 首次解析不回退到未验证密钥 |
| Redis 缓存命中时不查询 Solana | 单元 | 验证缓存路径 |
| 缓存过期 + Solana 不可达返回 stale 标记 | 单元 | `stale: true` 降级行为 |
| 平台管理员密钥注册 | 单元 | 首次注册写入 Redis meeet:admins |
| 重复注册管理员密钥幂等 | 单元 | 不报错，返回成功 |
| 非管理员密钥调用批量注册被拒绝 | 单元 | 401 响应 |
| 批量注册中单条 Agent 签名无效被跳过 | 单元 | 其他条目正常写入 |
| reputation → x402_score 映射边界值 | 单元 | 0→10, 850→92, 1000→100(上限) |
| `alsoKnownAs` 字段格式符合 W3C DID Core | 单元 | 字符串数组，值为有效 DID |

## 相关 ADR

- ADR-001: DID 格式选择（did:agentnexus multikey 格式是映射目标）
- ADR-004: 多 CA 认证架构（MEEET reputation 作为外部 attestation 输入）
- ADR-006: SDK 架构（SDK 通过 Daemon → Relay 解析 did:meeet）

## 评审记录

| 日期 | 评审者 | 结果 | 备注 |
|------|--------|------|------|
| 2026-04-04 | 评审 Agent | 条件批准 | 需补充平台管理员注册流程细节和测试用例 |

## 答疑记录

| 日期 | 提问者 | 问题 | 回复 | 是否触发设计变更 |
|------|--------|------|------|----------------|
| 2026-04-04 | 开发 Agent | Q7: MEEET Solana state API 端点 URL 目前是否已有？如暂无，是否先用 Mock 实现？ | 目前未确认，先用 Mock 实现。接口定义为 `MEEET_SOLANA_RPC_URL` 环境变量，默认值指向 Mock server，等 MEEET 方确认后替换。 | 否 |
| 2026-04-04 | 开发 Agent | Q8: `POST /meeet/admin/register` 需要"Relay 本地信任的密钥签名"，这个密钥是什么？是 Relay 自身签名密钥还是需新增配置？ | 是 Relay 自身的 Ed25519 identity key（启动时生成）。管理员注册请求需 Relay 运营者用此密钥签名，等同于"运营者手动批准该平台管理员"。复用现有密钥，不需要新增配置。 | 否 |
| 2026-04-04 | 开发 Agent | Q9: 批量注册单次最大 100 条，MEEET 有 1020 个 Agent，是否需要调用 11 次接口？还是可以一次性提交全部？ | 需要调用 11 次（10×100 + 1×20）。单次 100 条是安全限制。SDK 可封装 `batch_register_all()` 方法自动分片，开发不需要手动拆分。 | 否 |
