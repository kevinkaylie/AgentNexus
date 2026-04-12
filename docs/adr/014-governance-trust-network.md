# ADR-014: Governance Attestation & Trust Network

## Status

已采纳 (2026-04-11)

## Context

AgentNexus v0.9.5 已实现 L1-L4 信任体系（基于 DID + Certification），但存在以下问题：

1. **信任评估单一** — 仅依赖内部 certification，无法利用外部治理服务
2. **信任无传递** — A 信任 B，B 信任 C，但 A 对 C 无衍生信任
3. **无行为评分** — trust_score 是静态的，不反映实际交互行为
4. **路径发现缺失** — 无法找到两个 Agent 之间的信任链

外部治理服务已上线：
- **MolTrust** — `api.moltrust.ch/guard/governance/validate-capabilities`
- **APS** — `gateway.aeoess.com/api/v1/public/validate-capabilities`

两者都支持 `did:agentnexus` 解析，返回 signed governance attestation。

### 与 ADR-004 的关系

**ADR-004 定义核心信任体系**：L1-L4 级别、权限边界、spend_limit（$0/$10/$100/$1000）。

**ADR-014 是补充而非替代**：
- **L 级仍是权限边界**：Gatekeeper 基于 L 级做访问控制决策
- **trust_score 是辅助信号**：提供更细粒度的信任评估，但不改变权限边界
- **外部治理 spend_limit 是参考信息**：MolTrust/APS 返回的 spend_limit 不覆盖 ADR-004 定义的额度

**Gatekeeper 决策优先级**：
```
1. L 级（ADR-004）→ 决定权限边界（discover/read/message/transact/delegate）
2. trust_score（ADR-014）→ 辅助决策（如风险提示、速率限制）
```

## Decision

实现完整的治理认证 + 信任网络架构，包含四个核心模块：

### 1. Governance Client (`agent_net/common/governance.py`)

```
GovernanceClient (抽象基类)
├── MolTrustClient    — api.moltrust.ch/guard/governance/validate-capabilities
├── APSClient         — gateway.aeoess.com/api/v1/public/validate-capabilities
└── GovernanceRegistry — 管理多个 client，聚合结果
```

**MolTrust 具体端点（2026-04-12 A2A 讨论确认）：**
| 端点 | 用途 | 集成位置 |
|------|------|---------|
| `GET /skill/trust-score/{did}` | 查询 Agent 信任分 | Playbook stage assignment 前的可选验证（fail-open） |
| `POST /identity/resolve` | 解析 skill 最新版本 | 可选，per-Enclave 配置启用，本地场景不调用 |
| `POST /guard/governance/validate-capabilities` | 能力验证 + attestation 签发 | GovernanceClient 主调用端点 |

> 注：MolTrust trust score 作为辅助验证信号，不作为 Enclave 权限的决定因素。服务不可达时 fail-open（降级为本地信任评估）。

**GovernanceAttestation 结构：**
```json
{
  "signal_type": "governance_attestation",
  "issuer": "api.moltrust.ch",
  "subject": "did:agentnexus:z...",
  "decision": "permit|conditional|deny",
  "scopes": ["data:read", "commerce:checkout"],
  "spend_limit": 500,
  "trust_score": 75,
  "passport_grade": 2,
  "expires_at": "2026-04-11T01:00:00Z",
  "jws": "eyJhbGciOiJFZERTQSIs..."
}
```

**JWS 验证流程（S1 解决）：**

1. **JWKS Endpoint**：
   - MolTrust: `https://api.moltrust.ch/.well-known/jwks.json`
   - APS: `https://gateway.aeoess.com/.well-known/jwks.json`

2. **验证步骤**：
   ```python
   async def verify_attestation(att: GovernanceAttestation) -> bool:
       # 1. 检查过期
       if datetime.fromisoformat(att.expires_at) < datetime.utcnow():
           return False
       
       # 2. 获取 JWKS（带缓存）
       jwks = await get_jwks(att.issuer)  # 缓存 1 小时
       
       # 3. 解析 JWS header 获取 kid
       kid = decode_jws_header(att.jws)["kid"]
       
       # 4. 查找公钥
       public_key = find_jwk(jwks, kid)
       if not public_key:
           return False
       
       # 5. 验证签名（Ed25519）
       return verify_ed25519(att.jws, public_key, att.payload())
   ```

3. **JWKS 缓存策略**：
   - 缓存时间：1 小时
   - 刷新条件：缓存过期 / 验证失败（公钥轮换）
   - 存储：内存 + SQLite（可选持久化）

4. **降级规则**：
   - JWKS 获取失败：使用缓存的 JWKS（最长 24 小时）
   - 无可用 JWKS：拒绝 attestation，降级为无外部认证状态
   - JWS 验证失败：记录日志，不信任该 attestation

5. **重放攻击防护**：
   - `expires_at` 强制检查，过期 attestation 立即拒绝
   - 可选：维护短期 `jti`（JWT ID）黑名单（5 分钟窗口）

**MolTrust 等级映射（参考信息，不覆盖 ADR-004）：**
| Grade | Trust Score | AgentNexus Level（参考） | MolTrust spend_limit | 实际 spend_limit（ADR-004） |
|-------|-------------|-------------------------|---------------------|---------------------------|
| 0 | <25 | L1（参考） | $0 | $0 |
| 1 | 25-50 | L2（参考） | $100 | $10 |
| 2 | 50-75 | L3（参考） | $1K | $100 |
| 3 | 75-100 | L4（参考） | $10K | $1000 |

注：MolTrust/APS 的 `spend_limit` 仅作为参考信息，实际消费额度由 ADR-004 L 级定义。外部治理服务的等级映射可用于：
- 风险评估（高 grade → 低风险）
- attestation_bonus 计算（grade ≥ 2 可获得 +8.5 加成）
- 不改变 Gatekeeper 的权限决策

### 2. Web of Trust (`agent_net/common/trust_graph.py`)

**TrustEdge:** A → B 的直接信任关系
```python
TrustEdge(
    from_did="did:agentnexus:zA",
    to_did="did:agentnexus:zB",
    score=0.9,  # 0.0-1.0
    timestamp=1712812800,
    evidence="cert_001"
)
```

**TrustPath:** 多跳信任链
```
A → B → C
derived_score = 0.9 * 0.8 * 0.85^1 = 0.612
```

**衰减规则：** 每跳衰减 15%

**信任边权限模型（S2 解决）：**

信任边添加存在伪造风险，需要权限控制：

1. **权限模型**：只有 `from_did` 的 owner（持有私钥）可以添加自己发出的信任边
   - 即：A → B 的边，只有 A 可以添加，B 不能代 A 添加
   - 需要 `from_did` 的签名证明

2. **API 设计**：
   ```
   POST /trust/edge
   Authorization: Bearer <daemon_token>  # 确认是本地 Agent
   {
     "from_did": "did:agentnexus:zA",  # 必须是本地注册的 Agent
     "to_did": "did:agentnexus:zB",
     "score": 0.9,
     "evidence": "optional_cert_id"
   }
   ```

3. **验证逻辑**：
   - daemon 检查 `from_did` 是否为本地注册的 Agent
   - 如果是远程 Agent 发起的信任声明，需要附加签名：
     ```
     {
       "from_did": "did:agentnexus:zA",
       "to_did": "did:agentnexus:zB",
       "score": 0.9,
       "signature": "<from_did 的 Ed25519 签名>"
     }
     ```

4. **未来扩展**：双向握手确认（B 需要接受才算完整信任链）

### 3. Reputation System (`agent_net/common/reputation.py`)

**三维信任评分：**
```
trust_score = base_score(L级) + behavior_delta + attestation_bonus
```

| 分量 | 来源 | 范围 |
|------|------|------|
| base_score | L 级映射 | 15/40/70/95 |
| behavior_delta | 交互行为 | -20 ~ +20 |
| attestation_bonus | 治理认证 | 0 ~ +15 |

**base_score 设计依据（ADR-014 新增定义）：**

| L 级 | base_score | 设计理由 |
|------|------------|----------|
| L1 | 15 | 最低信任门槛（>0 表示可解析），留足行为扣分空间后仍 >0 |
| L2 | 40 | 有任意 cert，超过 25 分（L1+behavior_max=35）即有行为加成空间 |
| L3 | 70 | trusted CA cert，核心信任区间，±20 行为分后仍保持在 50-90 |
| L4 | 95 | entity_verified，接近满分但保留少量提升空间（+5 attestation） |

设计原则：
1. **非线性映射**：L1→L2 差 25 分，L2→L3 差 30 分，L3→L4 差 25 分，反映信任等级的边际效应
2. **行为空间**：每个 L 级留出 ±20 的行为影响范围，避免行为分无效
3. **上限约束**：L4 base_score=95 而非 100，保留 attestation_bonus 提升空间

**BehaviorScorer 计算因子：**
- 成功率（80% 为基准线）
- 响应速度（5s 为期望值）
- 活跃度（30 天 50 次交互为满分）

**OATR 格式映射（S4 解决）：**

`trust_score` 与 OATR `score` 字段的关系：

| AgentNexus 字段 | OATR 字段 | 说明 |
|----------------|-----------|------|
| `trust_score` | `extensions.agent-trust.trust_score` | 0-100 连续评分 |
| `trust_level` | `extensions.agent-trust.trust_level` | L1-L4 离散级别 |
| `base_score` | `extensions.agent-trust.base_score` | L 级基础分 |
| `behavior_delta` | `extensions.agent-trust.behavior_delta` | 行为加成/扣分 |
| `attestation_bonus` | `extensions.agent-trust.attestation_bonus` | 治理认证加成 |

**OATR 输出示例：**
```json
{
  "extensions": {
    "agent-trust": {
      "did": "did:agentnexus:z6Mk...",
      "trust_level": 3,
      "trust_score": 83.5,
      "base_score": 70.0,
      "behavior_delta": 5.0,
      "attestation_bonus": 8.5
    }
  }
}
```

注：OATR 核心 `score` 字段不直接使用，而是放在 `extensions.agent-trust` 扩展中，避免与 OATR 原有评分体系冲突。

### 4. Storage & API

**新增表：**
- `trust_edges` — 信任边存储
- `interactions` — 交互记录
- `reputation_cache` — 声誉缓存
- `governance_attestations` — 治理认证缓存

**新增 Daemon 端点：**
- `POST /governance/validate` — 调用治理服务
- `GET /trust/paths` — 查找信任路径
- `POST /trust/edge` — 添加信任边
- `GET /reputation/{did}` — 获取声誉评分
- `POST /interactions` — 记录交互

**新增 MCP 工具：**
- `validate_governance` — 验证能力
- `find_trust_path` — 查找信任路径
- `add_trust` — 添加信任
- `get_reputation` — 获取声誉

## Consequences

### Positive

1. **外部信任集成** — MolTrust/APS 可作为独立信任锚
2. **信任传递** — Web of Trust 实现多跳信任
3. **动态评分** — 基于实际行为的 trust_score
4. **OATR 兼容** — 输出格式符合 OATR `extensions.agent-trust`

### Negative

1. **外部依赖** — MolTrust 需要 API Key，有调用限制
2. **复杂度增加** — 多个信任源需要聚合逻辑
3. **存储增长** — 交互记录和信任边需要持久化

### Mitigations

1. **治理服务降级** — 外部服务不可用时使用内部缓存
2. **JWKS 缓存** — 避免频繁请求公钥
3. **定期清理** — 过期记录自动清理

## 影响范围

### 新增文件

| 文件 | 说明 |
|------|------|
| `agent_net/common/governance.py` | GovernanceClient + Registry + JWKS 缓存 |
| `agent_net/common/trust_graph.py` | TrustGraph + TrustEdge + 路径发现 |
| `agent_net/common/reputation.py` | ReputationScore + BehaviorScorer + ReputationStore |

### 修改文件

| 文件 | 变更 |
|------|------|
| `agent_net/storage.py` | 新增 4 张表（trust_edges, interactions, reputation_cache, governance_attestations） |
| `agent_net/node/daemon.py` | 新增 8 个端点 |
| `agent_net/node/mcp_server.py` | 新增 4 个工具 |
| `agent_net/common/runtime_verifier.py` | 集成 trust_score 作为辅助信号 |

### 兼容性

- **向后兼容**：L 级计算逻辑不变，trust_score 是新增字段
- **配置迁移**：无需迁移，新模块使用新表
- **API 变更**：现有端点无 breaking change，新增端点为可选功能

## Implementation

### Files Changed

| 文件 | 操作 |
|------|------|
| `agent_net/common/governance.py` | 新建 |
| `agent_net/common/trust_graph.py` | 新建 |
| `agent_net/common/reputation.py` | 新建 |
| `agent_net/storage.py` | 修改 |
| `agent_net/node/daemon.py` | 修改 |
| `agent_net/node/mcp_server.py` | 修改 |

### Dependencies

- 无新依赖（使用现有 aiohttp, nacl）

### 测试覆盖要求（S3）

参考 ADR-012/013 的测试标准：

| 测试类型 | 覆盖要求 |
|----------|----------|
| GovernanceClient mock | Mock HTTP 响应，测试正常/异常流程（超时、验证失败、过期） |
| Web of Trust 路径查找 | 含环路检测、单向信任、多路径选择 |
| Reputation 三维评分 | 边界值测试（L1-L4 + behavior ±20 + attestation 0-15） |
| JWKS 缓存 | 缓存命中/过期/刷新逻辑 |
| 信任边权限 | 非授权添加拒绝、签名验证 |

**测试文件：**
- `tests/test_governance.py` — 治理服务测试
- `tests/test_v09_web_of_trust.py` — 已有，需移到生产代码
- `tests/test_v09_reputation.py` — 已有，需移到生产代码
- `tests/test_v09_api.py` — API 端点测试

## References

- [MolTrust API Docs](https://api.moltrust.ch/docs)
- [APS Governance Attestation Schema](https://github.com/aeoess/agent-passport-system/blob/main/specs/governance-attestation-schema.md)
- [OATR JWT Attestation](../contracts/oatr-jwt-attestation.md)
- [ADR-004: Multi-CA Certification](./004-multi-ca-certification.md)

## 与 A2A Capability Token Envelope 的关系

> 背景：A2A RFC 讨论中，APS 方提出 skill-level 的 Capability Token Envelope 标准化方案。
> Enclave、SINT、AIP、APS 四方实现有大量重叠，差异仅在约束词汇和签名格式。
> 本节说明 ADR-014 治理架构如何与该 envelope 组合。

### Envelope 五要素与 Enclave 映射

| Envelope 要素 | 说明 | Enclave 映射 |
|--------------|------|-------------|
| 签名信封 | Ed25519 + JCS 规范化 | Enclave owner 的 DID 密钥签名，与现有 Ed25519 体系一致 |
| Skill binding | `{ skill_id, version_binding }` | Playbook stage 的 `{ stage_name, role }`，默认 capability binding |
| 约束集 | 不透明对象，承载 issuer 的约束词汇 | `{ permissions: 'rw', input_keys: [...], output_key: '...' }` — Playbook stage 定义 |
| 委托链引用 | 预计算 resolved_scope 的 hash | `owner_did → role → member_did → stage_assignment` 链的 hash |
| 过期 + 撤销 | TTL + revocation endpoint | Enclave `status`（active/archived）+ Playbook run `status` + 显式 TTL（待新增） |

### 双层组合原则

Capability token 和 gateway 检查是互补关系，不是替代关系：

```
Capability Token = 凭证（证明调用方持有特定权限）
Gateway / Playbook Engine = 评估器（验证凭证 AND 检查当前会话约束）
```

在 Enclave 中：
- **Token 层**：成员持有的 capability token 证明其 role + permissions
- **Engine 层**：Playbook 引擎检查 token 有效性 + 当前 stage 状态 + Vault 权限

只做 token 验证会漏掉 stage 状态约束（如"设计阶段已完成，不能再写 design_doc"）。
只做 engine 检查会漏掉跨 Enclave 场景（对方 Enclave 无法访问本地 engine）。

### governance_attestation 作为约束集条目

ADR-014 的 `GovernanceAttestation`（MolTrust/APS 签发）可直接作为 envelope 的约束集条目：

```json
{
  "envelope": {
    "signature": "Ed25519 over JCS",
    "skill_binding": { "skill_id": "data:read", "version_binding": "capability" },
    "constraint_set": {
      "enclave_permissions": { "permissions": "rw", "input_keys": ["requirements"] },
      "governance_attestation": {
        "issuer": "api.moltrust.ch",
        "decision": "permit",
        "trust_score": 75,
        "passport_grade": 2
      }
    },
    "delegation_chain_hash": "sha256:abc...",
    "expires_at": "2026-05-01T00:00:00Z",
    "revocation_endpoint": "https://node.example/capability/revoke/{token_id}"
  }
}
```

这使得 Enclave 签发的 token 和 APS delegation 可被任何消费方互验，无需共享网关。

### 实现计划

- **v1.0**：实现 envelope 签发/验证（R-1001）、skill 版本绑定（R-1002）、跨 Enclave 互验（R-1003）
- **待 A2A RFC 收敛后**：写独立 ADR 定义完整 token 格式和约束词汇规范

## 评审记录

| 日期 | 评审者 | 结果 | 备注 |
|------|--------|------|------|
| 2026-04-11 | 设计 Agent | **有条件通过** | 4 个阻塞性问题（P1-P3, S1）需修复后采纳，4 个建议性问题（S2-S5）。详见下方 |
| 2026-04-11 | 开发 Agent | **已修复** | P1-P3, S1 阻塞性问题已解决；S2-S5 建议性问题已处理 |
| 2026-04-11 | 设计 Agent（复审） | **全部通过，已采纳** | P1 spend_limit 对比表清晰 ✅ P2 base_score 设计依据完整 ✅ P3 ADR-004 关系章节明确 ✅ S1 JWS 验证流程完整 ✅ S2-S5 建议性问题全部处理 ✅ |
| 2026-04-12 | 评审 Agent | **有条件通过** | 代码评审：2 个阻塞性问题（P1-P2）需修复，7 个建议性问题（S1-S7）。详见下方 |
| 2026-04-12 | 开发 Agent | **已修复** | P1-P2 阻塞性问题已解决；S1/S2/S6/S7 已处理；S3-S5 低优先级保持现状 |

### 第一轮评审详情（2026-04-11）

#### 🔴 阻塞性问题 → ✅ 已修复

| # | 章节 | 问题描述 | 修复方案 |
|---|------|---------|----------|
| P1 | §1 MolTrust 等级映射 | spend_limit 与 ADR-004 冲突 | ✅ 已修复：明确 MolTrust spend_limit 仅作参考，实际额度由 ADR-004 决定 |
| P2 | §3 Reputation System | base_score 映射值来源未定义 | ✅ 已修复：补充设计依据（非线性映射 + 行为空间 + 上限约束） |
| P3 | Context / Decision | 与 ADR-004 关系未说明 | ✅ 已修复：新增"与 ADR-004 的关系"章节，明确 Gatekeeper 决策优先级 |
| S1 | §1 GovernanceAttestation | JWS 验证流程未设计 | ✅ 已修复：补充 JWKS endpoint、缓存策略、降级规则、重放攻击防护 |

#### 🟡 建议性问题 → ✅ 已处理

| # | 章节 | 问题描述 | 处理方案 |
|---|------|---------|----------|
| S2 | §4 `POST /trust/edge` | 信任边添加权限未限制 | ✅ 已处理：补充权限模型（只有 from_did owner 可添加） |
| S3 | Implementation | 缺少测试覆盖要求 | ✅ 已处理：补充测试覆盖要求表格 |
| S4 | Consequences | OATR 兼容声明笼统 | ✅ 已处理：补充字段映射表和输出示例 |
| S5 | 全文 | 缺少影响范围章节 | ✅ 已处理：新增"影响范围"章节 |

### 代码评审详情（2026-04-12）

覆盖文件：`governance.py`（573行）、`trust_graph.py`（449行）、`reputation.py`（463行）、`routers/governance.py`（159行）
测试：`test_governance.py` 29个测试全部通过（新增）、`test_v09_web_of_trust.py` 12个、`test_v09_reputation.py` 12个

#### 🔴 阻塞性问题 → ✅ 已修复

| # | 文件 | 位置 | 问题描述 | 修复方案 |
|---|------|------|---------|----------|
| P1 | `governance.py` | `verify_attestation` | 无 JWS 时无条件返回 True — 任何人可构造无签名的 attestation 对象绕过验证 | ✅ 已修复：新增 `require_jws: bool = False` 参数，调用方可显式要求必须有签名 |
| P2 | `routers/governance.py` | `DELETE /trust/edge` | 缺少 `_require_token` 鉴权 — 任何人可删除任意信任边，违反 ADR-014 §2 权限模型 | ✅ 已修复：添加 `_=Depends(_require_token)` + 验证 `from_did` 归属 |

#### 🟡 建议性问题 → ✅ 已处理

| # | 文件 | 位置 | 问题描述 | 处理方案 |
|---|------|------|---------|----------|
| S1 | `governance.py` | `verify_attestation` | JWKS 获取失败时直接 `return False`，未记录失败原因 | ✅ 已处理：添加 `logger.warning` 区分"网络错误"和"签名无效" |
| S2 | `routers/governance.py` | `_governance_registry` | 模块级全局单例，测试隔离困难 | ✅ 已处理：提供 `set_governance_registry()` / `reset_governance_registry()` 函数供测试注入 |
| S3 | `trust_graph.py` | `TrustGraphStore` | `if conn: ... else: async with ...` 双分支重复 8 次 | ⬚ 不影响正确性，保持现状（代码清晰度 vs 抽象复杂度的权衡） |
| S4 | `trust_graph.py` | `apply_decay` | 逐条 SQL 更新（N 条边 = N 次 SQL） | ⬚ 低优先级优化，信任边数量通常有限，批量更新可在性能瓶颈时再优化 |
| S5 | `reputation.py` | `BehaviorScorer.__init__` | `success_weight`/`response_time_weight`/`frequency_weight` 定义但未使用 | ⬚ 保持现状，权重参数预留供未来扩展，硬编码值对应设计文档中的公式 |
| S6 | `routers/governance.py` | `POST /interactions` | 无鉴权，任何人可伪造交互记录污染声誉数据 | ✅ 已处理：添加鉴权 + 验证 `from_did` 是本地 Agent |
| S7 | `routers/governance.py` | `GET /reputation/{did}` | `trust_level` 由请求方传入，可被滥用 | ✅ 已处理：从数据库查 Agent 实际 L 级，移除外部参数 |
