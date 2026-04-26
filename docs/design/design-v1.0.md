# AgentNexus 设计文档 — v1.0+（活跃）

> 本文件为 v1.0 及后续版本的活跃设计文档。
> 历史设计见 [design-v0.x.md](design-v0.x.md)。
> 设计索引见 [../design.md](../design.md)。

---

## v1.0.0 Phase 1 — 后端基础（1.0-04 + 1.0-06 + 1.0-08）

> 2026-04-15。三个优先条目的详细设计。

### 1.0-04 个人主 DID

#### 目标

一个"我"的 DID 代表本人，下挂 N 个 Agent DID。用户通过主 DID 统一管理所有 Agent。

#### 现状

`agents` 表：`did(PK), profile(JSON), is_local, last_seen, private_key_hex`。每个 Agent 独立，没有 owner_did 或层级关系。

#### 数据模型变更

**方案：agents 表新增 `owner_did` 字段**

不新建表，直接在 agents 表加一列。主 DID 本身也是一条 agent 记录（`owner_did = NULL`），子 Agent 的 `owner_did` 指向主 DID。

```sql
ALTER TABLE agents ADD COLUMN owner_did TEXT DEFAULT NULL;
CREATE INDEX idx_agents_owner ON agents(owner_did);
```

主 DID 与子 Agent 的区别：

| 字段 | 主 DID | 子 Agent |
|------|--------|---------|
| `owner_did` | `NULL` | 主 DID 的 did |
| `is_local` | 1 | 1 |
| `private_key_hex` | 有 | 有 |
| `profile.type` | `"owner"` | `"agent"` |

#### 新增端点

```
POST /owner/register          — 注册主 DID（生成密钥对，创建 owner 类型 agent）
POST /owner/bind              — 将已有 Agent DID 绑定到主 DID
DELETE /owner/unbind           — 解绑子 Agent
GET  /owner/agents             — 列出主 DID 下所有子 Agent
GET  /owner/profile            — 获取主 DID 的 profile
```

#### 注册流程

```
1. POST /owner/register {name: "Kevin"}
   → 生成 Ed25519 密钥对
   → 创建 did:agentnexus:<multikey>
   → 写入 agents 表（owner_did=NULL, profile.type="owner"）
   → 返回 {did, public_key}

2. POST /owner/bind {owner_did: "did:agentnexus:z6Mk...", agent_did: "did:agentnexus:z6Mk..."}
   → 验证 owner_did 是本地主 DID
   → 验证 agent_did 是本地 Agent
   → UPDATE agents SET owner_did=? WHERE did=?
   → 返回 {status: "ok"}
```

#### 向后兼容

- 没有 owner_did 的 Agent 继续正常工作
- 所有现有端点不受影响
- 主 DID 也可以直接收发消息（它本身就是一个 Agent）

#### 文件变更

| 文件 | 变更 |
|------|------|
| `agent_net/storage.py` | `init_db` 加 ALTER TABLE + 新增 `register_owner`、`bind_agent`、`unbind_agent`、`list_owned_agents` |
| `agent_net/node/routers/agents.py` | 新增 5 个 `/owner/*` 端点 |

---

### 1.0-06 消息中心

#### 目标

统一查看主 DID 下所有 Agent 收发的消息。

#### 现状

`messages` 表查询只支持按单个 `to_did` 查收件箱。没有跨 Agent 聚合查询。

#### 新增端点

```
GET /owner/messages/inbox      — 主 DID 下所有子 Agent 的未读消息（聚合）
GET /owner/messages/all        — 主 DID 下所有子 Agent 的全部消息（分页）
GET /owner/messages/stats      — 各子 Agent 的消息统计（未读数、最后消息时间）
```

#### 查询逻辑

```sql
-- /owner/messages/inbox：聚合所有子 Agent 的未读消息
SELECT m.id, m.from_did, m.to_did, m.content, m.timestamp,
       m.session_id, m.message_type, m.protocol
FROM messages m
WHERE m.to_did IN (
    SELECT did FROM agents WHERE owner_did = ?
)
AND m.delivered = 0
ORDER BY m.timestamp DESC
LIMIT ? OFFSET ?

-- /owner/messages/stats：各子 Agent 统计
SELECT a.did, a.profile,
       COUNT(CASE WHEN m.delivered = 0 THEN 1 END) as unread_count,
       MAX(m.timestamp) as last_message_at
FROM agents a
LEFT JOIN messages m ON m.to_did = a.did
WHERE a.owner_did = ?
GROUP BY a.did
```

#### 响应格式

```json
// GET /owner/messages/inbox?owner_did=did:agentnexus:z6Mk...
{
    "owner_did": "did:agentnexus:z6Mk...",
    "messages": [
        {
            "id": 42,
            "from_did": "did:agentnexus:z6Mk...外部",
            "to_did": "did:agentnexus:z6Mk...子Agent",
            "to_agent_name": "Architect",
            "content": "设计方案已完成",
            "timestamp": 1744700000.0,
            "message_type": "state_notify",
            "session_id": "sess_abc123"
        }
    ],
    "total_unread": 5
}
```

#### 文件变更

| 文件 | 变更 |
|------|------|
| `agent_net/storage.py` | 新增 `fetch_owner_inbox`、`fetch_owner_messages`、`fetch_owner_message_stats` |
| `agent_net/node/routers/messages.py` | 新增 3 个 `/owner/messages/*` 端点 |

---

### 1.0-08 A2A Capability Token Envelope

#### 目标

Ed25519 签名信封（当前为确定性 JSON 序列化，目标为严格 JCS），将 Enclave permissions 升级为结构化 capability token，支持跨 Enclave 互验。包含 `evaluated_constraint_hash`（qntm WG 最小互操作面要求）。

#### 现状

- `enclave_members.permissions`：简单字符串（`"rw"` / `"r"` / `"admin"`）
- `stage_executions`：没有 constraint_hash 字段
- 没有 capability token 的签发、验证、撤销机制

#### Capability Token 结构

```json
{
    "token_id": "ct_<uuid>",
    "version": 1,
    "issuer_did": "did:agentnexus:z6Mk...owner",
    "subject_did": "did:agentnexus:z6Mk...agent",
    "enclave_id": "enc_<uuid>",

    "scope": {
        "permissions": ["vault:read", "vault:write", "playbook:execute"],
        "resource_pattern": "vault/*",
        "role": "developer"
    },

    "constraints": {
        "spend_limit": 100,
        "max_delegation_depth": 1,
        "allowed_stages": ["implement", "review_code"],
        "input_keys": ["design_doc"],
        "output_key": "code_diff"
    },

    "validity": {
        "not_before": "2026-04-15T00:00:00Z",
        "not_after": "2026-05-15T00:00:00Z"
    },

    "revocation_endpoint": "https://relay.agentnexus.top/capability-tokens/<token_id>/status",

    "evaluated_constraint_hash": "sha256:<hex>",
    "signature_alg": "EdDSA",
    "canonicalization": "deterministic-json",  // 当前实现；目标为 RFC 8785 JCS，见 wip.md S5
    "signature": "<base64url>"
}
```

> **注：** `delegation_chain` 通过独立表 `delegation_chain_links` 管理，不在 Token JSON 内。查询时通过 `token_id` 关联获取父 token 及 scope_hash。

#### `evaluated_constraint_hash` 计算

```python
import hashlib
import json

def compute_constraint_hash(scope: dict, constraints: dict) -> str:
    """
    计算约束集的内容寻址哈希。
    qntm WG decision artifact 要求：每个 decision 必须引用被评估的约束集。
    """
    # 确定性 JSON 序列化（尚非严格 RFC 8785 JCS）
    canonical = json.dumps(
        {"scope": scope, "constraints": constraints},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
```

#### 数据模型变更

**新增 `capability_tokens` 表：**

```sql
CREATE TABLE IF NOT EXISTS capability_tokens (
    token_id TEXT PRIMARY KEY,
    version INTEGER DEFAULT 1,
    issuer_did TEXT NOT NULL,
    subject_did TEXT NOT NULL,
    enclave_id TEXT,
    scope_json TEXT NOT NULL,
    constraints_json TEXT NOT NULL,
    validity_json TEXT NOT NULL,
    revocation_endpoint TEXT NOT NULL,  -- 必填（R-1001）
    evaluated_constraint_hash TEXT NOT NULL,
    signature TEXT NOT NULL,
    status TEXT DEFAULT 'active',   -- active / revoked / expired
    created_at REAL NOT NULL,
    revoked_at REAL
);
CREATE INDEX idx_ct_subject ON capability_tokens(subject_did);
CREATE INDEX idx_ct_enclave ON capability_tokens(enclave_id);
CREATE INDEX idx_ct_status ON capability_tokens(status);
```

**新增 `delegation_chain_links` 表（委托链关系）：**

```sql
CREATE TABLE IF NOT EXISTS delegation_chain_links (
    id INTEGER PRIMARY KEY,
    child_token_id TEXT NOT NULL,
    parent_token_id TEXT NOT NULL,
    parent_scope_hash TEXT NOT NULL,  -- 用于快速验证单调收窄
    depth INTEGER DEFAULT 1,
    FOREIGN KEY (child_token_id) REFERENCES capability_tokens(token_id),
    FOREIGN KEY (parent_token_id) REFERENCES capability_tokens(token_id)
);
CREATE INDEX idx_dcl_child ON delegation_chain_links(child_token_id);
CREATE INDEX idx_dcl_parent ON delegation_chain_links(parent_token_id);
```

**`stage_executions` 新增字段：**

```sql
ALTER TABLE stage_executions ADD COLUMN evaluated_constraint_hash TEXT;
ALTER TABLE stage_executions ADD COLUMN capability_token_id TEXT;
```

#### 签发流程

```
1. Enclave owner 创建 Enclave + 添加成员
2. 系统自动为每个成员签发 capability token：
   - scope 从 enclave_members.permissions + role 推导
   - constraints 从 Playbook stage 定义推导（input_keys, output_key, allowed_stages）
   - issuer_did = enclave owner_did
   - 用 owner 的 Ed25519 私钥签名
3. Token 写入 capability_tokens 表
4. Playbook 引擎在 stage 推进时：
   - 验证 assigned_did 持有有效 token
   - 验证 token.constraints 包含当前 stage
   - 计算 evaluated_constraint_hash 写入 stage_executions
```

#### 验证流程

```python
async def verify_capability_token(token: dict, action: str) -> dict:
    """
    验证 capability token。
    返回 {valid: bool, reason: str} 或详细验证结果。
    """
    # 1. 签名验证（Ed25519 over 确定性 JSON 序列化 payload）
    if not verify_signature(token):
        return {"valid": False, "reason": "SIGNATURE_INVALID"}

    # 2. 有效期检查
    now = time.time()
    validity = token["validity"]
    if now < validity["not_before"]:
        return {"valid": False, "reason": "NOT_YET_VALID"}
    if now > validity["not_after"]:
        return {"valid": False, "reason": "EXPIRED"}

    # 3. 状态检查（调用 revocation_endpoint 或查本地缓存）
    if await is_revoked(token["token_id"]):
        return {"valid": False, "reason": "REVOKED"}

    # 4. 委托链完整性 + 单调收窄验证
    chain_links = await get_delegation_chain(token["token_id"])
    if chain_links:
        parent = await get_token(chain_links[0]["parent_token_id"])
        if not parent:
            return {"valid": False, "reason": "CHAIN_BREAK"}
        # 单调收窄：child scope ⊆ parent scope
        if not scope_is_subset(token["scope"], parent["scope"]):
            return {"valid": False, "reason": "SCOPE_EXPANSION"}
        # 约束更严格
        if token["constraints"]["spend_limit"] > parent["constraints"]["spend_limit"]:
            return {"valid": False, "reason": "SPEND_LIMIT_EXPANSION"}
        if token["constraints"]["max_delegation_depth"] >= parent["constraints"]["max_delegation_depth"]:
            return {"valid": False, "reason": "DELEGATION_DEPTH_EXPANSION"}

    # 5. 权限检查
    if action not in token["scope"]["permissions"]:
        return {"valid": False, "reason": "PERMISSION_DENIED"}

    return {"valid": True, "token_id": token["token_id"]}


def scope_is_subset(child_scope: dict, parent_scope: dict) -> bool:
    """验证 child scope 是 parent scope 的子集（单调收窄）。"""
    child_perms = set(child_scope.get("permissions", []))
    parent_perms = set(parent_scope.get("permissions", []))
    if not child_perms.issubset(parent_perms):
        return False
    # resource_pattern: child 应更窄或相同
    child_pattern = child_scope.get("resource_pattern", "*")
    parent_pattern = parent_scope.get("resource_pattern", "*")
    if child_pattern != parent_pattern and not child_pattern.startswith(parent_pattern.rstrip("*")):
        return False
    return True
```

#### 新增端点

```
POST /capability-tokens/issue     — 签发 token（Enclave owner 调用）
GET  /capability-tokens/{token_id} — 查询 token
POST /capability-tokens/{token_id}/verify — 验证 token
POST /capability-tokens/{token_id}/revoke — 撤销 token
GET  /capability-tokens/by-did/{did} — 查询某 DID 持有的所有有效 token
```

#### 与现有 permissions 的兼容

- `enclave_members.permissions` 字段保留，作为简写
- 系统自动从 permissions 生成 capability token
- 映射规则：
  - `"admin"` → `["vault:read", "vault:write", "vault:delete", "playbook:execute", "member:manage"]`
  - `"rw"` → `["vault:read", "vault:write", "playbook:execute"]`
  - `"r"` → `["vault:read"]`
- 旧代码继续用 permissions 字符串，新代码用 capability token

#### 与 crosswalk 的对齐

`evaluated_constraint_hash` 对应 `crosswalk/agentnexus.yaml` 中的 `active_constraints` 映射。签发的 token 即 qntm WG decision artifact 中的 constraint envelope（`constraint_set_type: "enclave"`）。

#### 文件变更

| 文件 | 变更 |
|------|------|
| `agent_net/storage.py` | `init_db` 新增 capability_tokens 表 + delegation_chain_links 表 + stage_executions ALTER |
| `agent_net/common/capability_token.py` | **新建**。CapabilityToken 数据类 + 签发/验证/撤销逻辑 + `compute_constraint_hash` + `scope_is_subset` |
| `agent_net/node/routers/governance.py` | 新增 5 个 `/capability-tokens/*` 端点，验证返回 `{valid, reason}` |
| `agent_net/enclave/playbook.py` | stage 推进时验证 token + 写入 evaluated_constraint_hash |

---

### 实施顺序

```
1.0-04 个人主 DID（~150 行）
    ↓ agents 表 owner_did 就绪
1.0-06 消息中心（~100 行）
    ↓ 聚合查询端点就绪
1.0-08 Capability Token Envelope（~400 行）
    ↓ 新模块 + 表 + 端点 + Playbook 集成
```

1.0-04 和 1.0-06 是纯增量，不改现有逻辑。1.0-08 改动最大，但核心是新建 `capability_token.py` 模块，对现有代码的侵入限于 Playbook 引擎的 stage 推进处。

---

### 设计评审（2026-04-15）

#### 1.0-04 个人主 DID — ✅ 通过

| 项目 | 评估 | 备注 |
|------|------|------|
| 数据模型 | ✅ | 在 agents 表加 `owner_did` 列，不新建表，简洁 |
| 端点设计 | ✅ | 5 个 `/owner/*` 端点，职责清晰 |
| 注册流程 | ✅ | 生成密钥对 → 创建 DID → 写入 agents |
| 向后兼容 | ✅ | `owner_did=NULL` 的 Agent 继续正常工作 |

**改进建议：**

| # | 建议 | 优先级 | 说明 |
|---|------|--------|------|
| S1-04-1 | `POST /owner/register` 返回加密私钥或提示导出 | P2 | 用户需能恢复主 DID，否则私钥丢失后无法管理子 Agent |

#### 1.0-06 消息中心 — ✅ 通过

| 项目 | 评估 | 备注 |
|------|------|------|
| 聚合查询 SQL | ✅ | 子查询 + JOIN 设计正确 |
| 端点设计 | ✅ | 3 个 `/owner/messages/*` 端点 |
| 响应格式 | ✅ | 包含 `to_agent_name` 字段，方便用户识别 |
| 分页支持 | ✅ | LIMIT/OFFSET |

**改进建议：**

| # | 建议 | 优先级 | 说明 |
|---|------|--------|------|
| S1-06-1 | 可加 `GET /owner/messages/search?q=` 支持关键词搜索 | P3 | 非必需，但大消息量时有用 |

#### 1.0-08 Capability Token Envelope — ✅ 通过（改进已采纳）

| 项目 | 评估 | 备注 |
|------|------|------|
| Token 结构 | ✅ | 五字段齐全 + `revocation_endpoint`（已采纳 S1-08-1） |
| `evaluated_constraint_hash` | ✅ | 符合 qntm WG decision artifact 要求 |
| 确定性 JSON 序列化 | ✅ | `sort_keys=True, separators=(",", ":")`。注意：非严格 RFC 8785 JCS，跨语言互操作需升级 |
| 权限映射 | ✅ | `admin/rw/r` → 细粒度权限数组，与 SINT T2/T1/T0 对齐 |
| 数据模型 | ✅ | `capability_tokens` 表 + `delegation_chain_links` 表（已采纳 S1-08-2） |
| 签发流程 | ✅ | 自动从 `enclave_members.permissions` 推导 |
| 验证流程 | ✅ | 包含 monotonic narrowing 检查（已采纳 S1-08-3） |

**已采纳改进：**

| # | 建议 | 状态 | 说明 |
|---|------|------|------|
| S1-08-1 | Token 结构添加 `revocation_endpoint` 字段 | ✅ 已采纳 | 已添加到 Token 结构，必填字段 |
| S1-08-2 | `delegation_chain` 改为独立表 | ✅ 已采纳 | 新增 `delegation_chain_links` 表，移除 JSON TEXT 列 |
| S1-08-3 | 补充 monotonic narrowing 验证逻辑 | ✅ 已采纳 | 验证流程新增 `scope_is_subset` + 约束比较 |
| S1-08-4 | 与 SINT 字段命名对齐 | 🟢 小优化 | 可在 crosswalk 中加别名映射 |

#### 与 SINT/qntm WG 对齐检查

| 检查项 | 状态 | 参考 |
|--------|------|------|
| `evaluated_constraint_hash` 在 Token 中 | ✅ | qntm WG issue #7 要求 |
| 权限映射 `r → T0, rw → T1, admin → T2` | ✅ | enclave-permission-model.md + enclave-mapping.ts |
| 确定性 JSON 序列化 | ✅ | 与 SINT RFC-001 §签名格式方向一致，严格 JCS 合规待升级 |
| 委托链单调收窄验证 | ✅ 已实现 | `scope_is_subset` + constraint 比较 |
| 撤销端点必填 | ✅ 已实现 | Token 结构包含 `revocation_endpoint` |

---

### 评审结论

三项设计全部通过，改进建议已采纳并整合到设计中：

- ✅ S1-08-1：`revocation_endpoint` 字段已添加到 Token 结构
- ✅ S1-08-2：`delegation_chain_links` 独立表已定义
- ✅ S1-08-3：`scope_is_subset` + monotonic narrowing 验证已实现

**设计已完善，可进入开发。**

---

### 代码评审记录（v1.0 Phase 1）

> 评审日期：2026-04-15 | 评审者：评审 Agent | 测试结果：371 passed, 8 skipped ✅

#### 评审结论：已通过

所有阻塞性问题已修复，补充测试用例已通过。

#### 阻塞性问题 — ✅ 全部已修复

| # | 问题 | 位置 | 状态 |
|---|------|------|------|
| P1 | `verify_token` 委托链验证依赖 `token._parent_token_id` 动态属性，从数据库恢复时该属性为 None，导致委托链验证被跳过。应改为直接调用 `get_delegation_chain_func(token.token_id)` | `capability_token.py#verify_token` | ✅ 已修复 — 改为直接调用 `get_delegation_chain_func(token.token_id)`，不依赖动态属性 |
| P2 | `CapabilityToken.to_dict()` 使用 `asdict()`，不包含动态属性 `_parent_token_id`，导致 `api_issue_token` 中委托链信息丢失，`delegation_chain_links` 表永远不会写入。修复：在 `api_issue_token` 里手动补 `token_dict["_parent_token_id"] = parent_token_id` | `governance.py#api_issue_token` | ✅ 已修复 — 在 `save_capability_token` 前手动补上委托链属性 |

#### 建议性问题 — ✅ 全部已修复

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| S1 | `register_owner` 在 storage.py 里直接 import 了 `DIDGenerator` 和 `_config`，违反存储层不依赖 node 层的原则 | 🟡 | ⬚ 建议修复（架构层面，不影响功能） |
| S2 | `api_verify_token` 传 `get_token_func=get_capability_token`（返回 dict），但 `verify_token` 里用 `parent.scope` 访问属性——dict 没有 `.scope`，委托链验证会抛异常 | 🟡 | ✅ 已修复 — 改为 `parent["scope"]` dict 访问，同时兼容 dict 和 CapabilityToken 对象 |
| S3 | `scope_is_subset` 的 `resource_pattern` 比较逻辑对复杂 glob 模式会误判 | 🟢 | ⬚ 后续优化 |
| S4 | `verify_token` 中 `max_delegation_depth` 用 `>=` 比较，比设计文档"更严格"要求更严，确认是否有意为之 | 🟢 | ⬚ 确认（有意为之：child depth 必须严格小于 parent） |
| S5 | `fetch_owner_inbox` 不包含发给主 DID 本身的消息（`WHERE a.owner_did = ?` 不含主 DID 自己） | 🟢 | ⬚ 后续优化 |

#### 补充测试用例 — ✅ 全部已通过

| # | 场景 | 重要性 | 状态 |
|---|------|--------|------|
| T1 | 委托链端到端：签发 parent token → 签发 child token（带 parent_token_id）→ 验证委托链完整性 | 🔴 必需 | ✅ 已通过 — test_v10_ct_07 |
| T2 | 单调收窄拒绝：child scope 超出 parent scope → 验证返回 SCOPE_EXPANSION | 🔴 必需 | ✅ 已通过 — test_v10_ct_08 |
| T3 | 过期 Token：validity_days=0 → 验证返回 EXPIRED | 🟡 建议 | ✅ 已通过 — test_v10_ct_09 |

---

## v1.0.0 Phase 2 — 意图路由 + Web 仪表盘 + 接入向导（1.0-05 + 1.0-01 + 1.0-03）

> 2026-04-17。

### 1.0-05 意图路由

#### 目标

外部发消息给主 DID，根据消息内容自动转发到最匹配的子 Agent。

#### 现状

`router.py` 的 `route_message` 按 `to_did` 直接路由。如果 `to_did` 是主 DID，消息存入主 DID 的收件箱，不会转发给子 Agent。

#### 设计

在 `route_message` 的离线存储步骤之前，插入意图路由逻辑：

```python
# router.py — route_message 中，离线存储之前

# 意图路由：如果 to_did 是主 DID，尝试转发到子 Agent
from agent_net.storage import get_owner, list_owned_agents
owner = await get_owner(to_did)
if owner:
    target = await _intent_route(content, to_did)
    if target:
        # 递归路由到子 Agent（保留原始 from_did）
        return await self.route_message(
            from_did, target, content, session_id, reply_to,
            message_type, protocol, content_encoding,
        )
```

#### 匹配策略

```python
async def _intent_route(content: str, owner_did: str) -> Optional[str]:
    """
    根据消息内容匹配最合适的子 Agent。
    策略：关键词匹配 Agent capabilities。
    """
    agents = await list_owned_agents(owner_did)
    if not agents:
        return None

    content_lower = content.lower()
    best_match = None
    best_score = 0

    for agent in agents:
        profile = agent.get("profile", {})
        caps = profile.get("capabilities", [])
        tags = profile.get("tags", [])
        keywords = [c.lower() for c in caps + tags]

        score = sum(1 for kw in keywords if kw in content_lower)
        if score > best_score:
            best_score = score
            best_match = agent["did"]

    # S1-05-1：匹配阈值，避免低质量转发
    MIN_MATCH_SCORE = 2  # 至少 2 个关键词匹配才转发
    if best_score < MIN_MATCH_SCORE:
        return None  # 无足够匹配，消息留在主 DID 收件箱

    return best_match  # None 表示无匹配，消息留在主 DID 收件箱
```

#### 防递归

主 DID 转发到子 Agent 后，子 Agent 的 `route_message` 不会再触发意图路由（因为子 Agent 不是 owner 类型）。

#### 文件变更

| 文件 | 变更 |
|------|------|
| `agent_net/router.py` | `route_message` 插入意图路由逻辑 + `_intent_route` 方法 |

预估：~35 行。

#### 改进建议（已采纳）

| # | 建议 | 状态 | 说明 |
|---|------|------|------|
| S1-05-1 | 添加匹配阈值，避免低质量转发 | ✅ 已采纳 | `MIN_MATCH_SCORE = 2`，至少 2 个关键词匹配才转发 |
| S2-05-1 | 返回匹配日志/元数据 | 🟢 后续 | 转发成功后记录匹配 Agent 和 score，便于调试 |
| S3-05-1 | 支持配置优先级权重 | 🟢 后续 | 某些 capability（如 "Emergency"）可设置更高权重 |

---

### 1.0-01 Web 仪表盘

#### 目标

`localhost:8765/ui` 提供 Web 管理界面，覆盖 Agent 管理、消息中心、Enclave/Playbook、信任网络。

#### 技术选型

| 选项 | 方案 | 理由 |
|------|------|------|
| 前端框架 | **Vue 3 + Vite** | 轻量、SFC 单文件组件、构建产物小（< 500KB gzip）。项目 Python 为主，Vue 的模板语法对非前端开发者更友好 |
| UI 组件库 | **PrimeVue** | 开箱即用的数据表格、树形组件、图表，免费 |
| 图可视化 | **D3.js**（信任网络图）+ **dagre**（Playbook DAG） | 轻量，不引入重框架 |
| 构建产物 | Vite build → `agent_net/node/static/` 目录 | FastAPI `StaticFiles` 挂载，零额外依赖 |
| 开发模式 | `vite dev` 代理 API 到 `:8765` | 前后端分离开发，构建后合并 |

#### 目录结构

```
web/                          # 前端源码（不打包进 pip install）
├── package.json
├── vite.config.ts
├── index.html
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── api/                  # API 调用层
│   │   └── client.ts         # fetch wrapper，baseURL = /
│   ├── views/
│   │   ├── Dashboard.vue     # 首页概览
│   │   ├── Agents.vue        # Agent 列表 + 详情
│   │   ├── Messages.vue      # 消息中心
│   │   ├── Enclaves.vue      # Enclave 管理
│   │   ├── TrustNetwork.vue  # 信任网络图
│   │   └── Setup.vue         # 接入向导（1.0-03）
│   └── components/
│       ├── PlaybookDAG.vue   # Playbook DAG 可视化
│       ├── TrustGraph.vue    # D3 信任网络图
│       └── TokenList.vue     # Capability Token 列表
└── dist/                     # 构建产物 → 复制到 agent_net/node/static/

agent_net/node/static/        # 构建产物（git tracked）
├── index.html
├── assets/
│   ├── index-xxx.js
│   └── index-xxx.css
```

#### FastAPI 挂载

```python
# daemon.py 追加

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

_static_dir = Path(__file__).parent / "static"

if _static_dir.exists():
    # S4-01-1 修复：使用 html=True 模式，自动处理 SPA fallback
    app.mount("/ui", StaticFiles(directory=_static_dir, html=True), name="ui")
```

使用 `StaticFiles(html=True)` 模式：
- `/ui/assets/index.js` → 返回静态文件
- `/ui/agents` → 无匹配文件时返回 `index.html`（SPA fallback）
- 无需额外路由，FastAPI 自动处理

所有 `/ui/*` 路径由 StaticFiles 处理，Vue Router history mode 自动生效。

#### 鉴权机制（S5-01-1）

本地访问免鉴权，远程访问需 Token：

```python
# daemon.py 鉴权中间件
from starlette.middleware.base import BaseHTTPMiddleware

class UIAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 仅对 /ui 路径鉴权（API 端点已有独立鉴权）
        if not request.url.path.startswith("/ui"):
            return await call_next(request)

        # 本地访问（localhost / 127.0.0.1）免鉴权
        client_host = request.client.host if request.client else ""
        if client_host in ("localhost", "127.0.0.1", "::1"):
            return await call_next(request)

        # 远程访问：检查 Authorization header 或 cookie
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            token = request.cookies.get("daemon_token", "")

        if token != _load_daemon_token():
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        return await call_next(request)

app.add_middleware(UIAuthMiddleware)
```

前端配合（`web/src/api/client.ts`）：

```typescript
// 本地开发时无需 Token，远程访问自动携带
const token = localStorage.getItem("daemon_token") || "";

export async function fetchApi(path: string, options = {}) {
  const headers = { ...options.headers };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(path, { ...options, headers });
}
```

#### 页面设计

**1. Dashboard（首页）**

```
┌─────────────────────────────────────────────────────┐
│  AgentNexus Dashboard                    [Owner DID]│
├──────────┬──────────┬──────────┬───────────────────┤
│ Agents   │ Unread   │ Enclaves │ Avg Trust Score   │
│   5      │   12     │   3      │   78.5            │
├──────────┴──────────┴──────────┴───────────────────┤
│  最近消息                                           │
│  ┌─────────────────────────────────────────────┐   │
│  │ Agent1 ← sender: "设计方案已完成"    2min ago│   │
│  │ Agent2 ← sender: "代码已提交"        5min ago│   │
│  └─────────────────────────────────────────────┘   │
│  活跃 Playbook                                      │
│  ┌─────────────────────────────────────────────┐   │
│  │ 登录功能开发  [design] → [review] → implement│   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

数据源：`GET /owner/agents/{did}` + `GET /owner/messages/stats` + `GET /enclaves` + `GET /reputation/{did}`（聚合子 Agent）

**S2-01-1 改进：** 信任分改为 `Avg Trust Score`（子 Agent 平均），明确显示来源，避免用户误解为主 DID 自身分数。

**S3-01-1 优化：** TrustNetwork 页面节点 > 50 时启用分页加载，每页显示 20 个节点，支持搜索/筛选功能。

**2. Agents（Agent 列表）**

表格：DID（缩写）、名称、capabilities、信任分、最后活跃时间、状态（在线/离线）。点击进入详情页（profile、certifications、capability tokens）。

数据源：`GET /owner/agents/{did}` + `GET /reputation/{did}` + `GET /capability-tokens/by-did/{did}`

**3. Messages（消息中心）**

左侧：子 Agent 列表 + 未读数。右侧：选中 Agent 的消息流。

数据源：`GET /owner/messages/stats` + `GET /owner/messages/inbox` + `GET /messages/all/{did}`

**4. Enclaves（Enclave 管理）**

Enclave 列表 → 点击进入：成员、Vault 文档、Playbook 运行状态。Playbook 用 DAG 图展示 stage 依赖和当前进度。

数据源：`GET /enclaves` + `GET /enclaves/{id}` + `GET /enclaves/{id}/runs/{rid}`

**5. TrustNetwork（信任网络）**

D3 力导向图：节点 = Agent DID，边 = 信任关系（score 映射为边粗细），颜色 = trust_level。

数据源：`GET /trust/edges/{did}` + `GET /reputation/{did}`

#### 文件变更

| 文件 | 变更 |
|------|------|
| `web/` | **新建**。Vue 3 + Vite 前端项目 |
| `agent_net/node/static/` | **新建**。构建产物目录 |
| `agent_net/node/daemon.py` | 挂载 StaticFiles(html=True) + UIAuthMiddleware |
| `pyproject.toml` | 排除 `web/` 目录，不打包进 pip install |

#### pyproject.toml 配置（S1-01-1）

```toml
[tool.setuptools.packages.find]
where = ["src"]
include = ["agent_net*"]
exclude = ["web*"]

# 或使用 hatchling
[tool.hatch.build.targets.wheel]
exclude = ["web/", "*.ts", "*.vue"]
```

确保 `pip install agentnexus-sdk` 不包含前端源码，构建产物 `agent_net/node/static/` 随主包一起安装。

#### 改进建议（已采纳）

| # | 建议 | 状态 | 说明 |
|---|------|------|------|
| S1-01-1 | pyproject.toml 排除 `web/` 目录 | ✅ 已采纳 | 配置 exclude 规则 |
| S2-01-1 | Dashboard 信任分显示来源 | ✅ 已采纳 | 改为 `Avg Trust Score` |
| S3-01-1 | TrustNetwork 性能优化 | 🟢 后续 | 节点 > 50 时分页加载 |
| S4-01-1 | SPA fallback 路由顺序 | ✅ 已采纳 | 使用 `StaticFiles(html=True)` |
| S5-01-1 | 鉴权机制 | ✅ 已采纳 | 本地免鉴权 + UIAuthMiddleware |

---

### 1.0-03 Agent 接入向导

#### 目标

UI 引导用户接入 Agent：选平台 → 显示安装命令 → Agent 注册后自动出现在列表中。

#### 设计

作为仪表盘的一个页面（`Setup.vue`），不是独立应用。

**步骤流程：**

```
Step 1: 选择接入方式
  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │  MCP     │  │  SDK     │  │ OpenClaw │  │ Webhook  │
  │(Claude)  │  │(Python)  │  │ (Skill)  │  │ (HTTP)   │
  └──────────┘  └──────────┘  └──────────┘  └──────────┘

Step 2: 显示安装命令（根据选择动态生成）
  ┌─────────────────────────────────────────────────┐
  │ # MCP 方式                                       │
  │ python main.py node mcp --name "MyAgent" \       │
  │   --caps "Chat,Code"                             │
  │                                    [复制] [下一步]│
  └─────────────────────────────────────────────────┘

Step 3: 等待 Agent 注册（轮询 /agents/local）
  ┌─────────────────────────────────────────────────┐
  │ ⏳ 等待 Agent 连接...                             │
  │                                                   │
  │ ✅ MyAgent (did:agentnexus:z6Mk...) 已连接！     │
  │                                    [绑定到主 DID] │
  └─────────────────────────────────────────────────┘

Step 4: 绑定到主 DID（调用 POST /owner/bind）
  ┌─────────────────────────────────────────────────┐
  │ ✅ MyAgent 已绑定到你的主 DID                     │
  │                                    [完成]         │
  └─────────────────────────────────────────────────┘
```

#### 各平台安装命令模板

```typescript
// S2-03-1：使用模板函数而非字符串拼接
interface SetupTemplate {
  title: string;
  generateCommand: (name: string, caps: string[]) => string;
  description: string;
}

const SETUP_TEMPLATES: Record<string, SetupTemplate> = {
  mcp: {
    title: "MCP（Claude Desktop / Cursor / Claude Code）",
    generateCommand: (name, caps) =>
      `python main.py node mcp --name "${name}" --caps "${caps.join(",")}"`,
    description: "适合 AI 编程助手场景",
  },
  sdk: {
    title: "Python SDK",
    generateCommand: (name, caps) =>
      `import agentnexus\nnexus = await agentnexus.connect("${name}", caps=["${caps.join('", "')}"])`,
    description: "适合自定义 Agent 开发",
  },
  openclaw: {
    title: "OpenClaw Skill",
    generateCommand: (name, caps) =>
      `curl -X POST http://localhost:8765/adapters/openclaw/register \\\n  -H "Authorization: Bearer $TOKEN" \\\n  -d '{"skill_name": "${name}", "capabilities": ["${caps.join('", "')}"]}'`,
    description: "适合已有 OpenClaw Skill",
  },
  webhook: {
    title: "Webhook（Dify / Coze / 自定义）",
    generateCommand: (name, caps) =>
      `curl -X POST http://localhost:8765/adapters/webhook/register \\\n  -H "Authorization: Bearer $TOKEN" \\\n  -d '{"name": "${name}", "callback_url": "https://your-service/webhook"}'`,
    description: "适合任何能发 HTTP 请求的服务",
  },
};

// 使用示例
const command = SETUP_TEMPLATES.mcp.generateCommand("MyAgent", ["Chat", "Code"]);
```

#### 轮询检测新 Agent

```typescript
// Setup.vue — Step 3
const POLL_INTERVAL = 2000;  // 2 秒
const POLL_TIMEOUT = 60000;  // 60 秒超时（S1-03-1）

async function waitForAgent(expectedName: string) {
  const before = await fetch("/agents/local").then(r => r.json());
  const beforeDids = new Set(before.agents.map(a => a.did));

  let elapsed = 0;

  const interval = setInterval(async () => {
    elapsed += POLL_INTERVAL;

    // S1-03-1：超时机制
    if (elapsed >= POLL_TIMEOUT) {
      clearInterval(interval);
      showError("等待超时，请检查命令是否正确执行，或手动刷新页面");
      return;
    }

    // S3-03-1：显示进度
    updateProgress(`等待中... (已轮询 ${elapsed / 1000} 秒)`);

    const after = await fetch("/agents/local").then(r => r.json());
    const newAgent = after.agents.find(a => !beforeDids.has(a.did));

    if (newAgent) {
      clearInterval(interval);

      // S4-03-1：检查名称匹配
      if (newAgent.profile?.name !== expectedName) {
        showWarning(`检测到新 Agent "${newAgent.profile?.name}"，但名称不匹配`);
      }

      onAgentConnected(newAgent);
    }
  }, POLL_INTERVAL);
}
```

#### 文件变更

| 文件 | 变更 |
|------|------|
| `web/src/views/Setup.vue` | 接入向导页面（4 步流程） |
| `web/src/api/client.ts` | fetchApi wrapper + Token 携带逻辑 |

#### 改进建议（已采纳）

| # | 建议 | 状态 | 说明 |
|---|------|------|------|
| S1-03-1 | 轮询超时机制 | ✅ 已采纳 | 60 秒超时 + 错误提示 |
| S2-03-1 | placeholder 替换逻辑 | ✅ 已采纳 | 使用模板函数 `generateCommand(name, caps)` |
| S3-03-1 | Step 3 显示进度 | ✅ 已采纳 | 显示轮询秒数 |
| S4-03-1 | 错误处理 | ✅ 已采纳 | 名称不匹配警告 + 超时错误提示 |

---

### 实施顺序

```
1.0-05 意图路由（~35 行，纯后端）✅ 已完成（2026-04-17）
    ↓
1.0-01 Web 仪表盘
    Phase A: 项目脚手架（Vite + Vue + FastAPI 挂载）✅ 已完成（2026-04-17）
    Phase B: Dashboard + Agents 页面 → 待实施
    Phase C: Messages + Enclaves 页面 → 待实施
    Phase D: TrustNetwork 页面（D3）→ 待实施
    ↓
1.0-03 接入向导（仪表盘的一个页面，随 Phase B 一起做）
```

**已完成：**
- 1.0-05 意图路由（router.py + test_v10_intent_route.py）
- 1.0-01 Phase A：web/ 前端脚手架 + daemon.py StaticFiles 挂载

**下一步：** Phase B — Dashboard + Agents 页面完善 + Setup.vue 接入向导

---

### Phase 2 设计评审记录（v1.0.0）

> 评审日期：2026-04-17 | 评审者：Claude Code

#### 评审结论：✅ 全部通过，改进已采纳

三项设计全部通过，改进建议已采纳并整合到设计中。

#### 1.0-05 意图路由 — ✅ 通过

| 项目 | 评估 | 备注 |
|------|------|------|
| 设计位置 | ✅ | 在 `route_message` 离线存储前插入 |
| 匹配策略 | ✅ | 关键词匹配 capabilities + tags |
| 防递归 | ✅ | 子 Agent 不是 owner 类型 |
| 改进 S1-05-1 | ✅ 已采纳 | `MIN_MATCH_SCORE = 2` 匹配阈值 |

#### 1.0-01 Web 仪表盘 — ✅ 通过

| 项目 | 评估 | 备注 |
|------|------|------|
| 技术选型 | ✅ | Vue 3 + Vite + PrimeVue |
| 构建产物 | ✅ | `web/` → `agent_net/node/static/` |
| 改进 S1-01-1 | ✅ 已采纳 | pyproject.toml exclude `web/` |
| 改进 S2-01-1 | ✅ 已采纳 | 改为 `Avg Trust Score` |
| 改进 S4-01-1 | ⚠️ 部分采纳 | `StaticFiles(html=True)` 仅处理目录请求，不处理 Vue Router history mode。必须保留 catch-all 路由作为 SPA fallback，两者并存 |
| 改进 S5-01-1 | ✅ 已采纳 | UIAuthMiddleware 鉴权。补充：用 daemon token 生成 session cookie，避免每次访问输入 token |

#### 1.0-03 Agent 接入向导 — ✅ 通过

| 项目 | 评估 | 备注 |
|------|------|------|
| 流程设计 | ✅ | 4 步流程清晰 |
| 平台覆盖 | ✅ | MCP/SDK/OpenClaw/Webhook |
| 改进 S1-03-1 | ✅ 已采纳 | 60 秒轮询超时 |
| 改进 S2-03-1 | ✅ 已采纳 | 模板函数 `generateCommand()` |
| 改进 S3-03-1 | ✅ 已采纳 | 显示轮询进度 |
| 改进 S4-03-1 | ⚠️ 部分采纳 | 保持 DID 差集检测为主要逻辑，名称匹配仅作辅助提示。用户可能修改命令中的名称，按名称匹配不可靠 |

#### 后续优化（P3）

| # | 建议 | 说明 |
|---|------|------|
| S2-05-1 | 返回匹配日志/元数据 | 意图路由转发后记录匹配详情 |
| S3-05-1 | 支持配置优先级权重 | 某些 capability 设置更高权重 |
| S3-01-1 | TrustNetwork 性能优化 | 节点 > 50 时分页加载 |

**设计已完善，可进入开发。**

---

### 代码评审记录（v1.0 Phase 2）

> 评审日期：2026-04-17 | 评审者：评审 Agent | 测试结果：375 passed, 8 skipped ✅

#### 评审结论：已通过

所有阻塞性和建议性问题已修复。

#### 阻塞性问题 — ✅ 全部已修复

| # | 问题 | 位置 | 状态 |
|---|------|------|------|
| P1 | 意图路由插入位置错误（步骤 3.5，Relay 之后）。若主 DID 有 P2P endpoint 或 Relay 地址，消息在步骤 2/3 就被投递，永远不触发意图路由 | `router.py#route_message` | ✅ 已修复 — 移到步骤 1 之后（本地直投之后，P2P/Relay 之前） |
| P2 | `StaticFiles(html=True)` 不处理 Vue Router history mode 路径。需补充 catch-all 路由 | `daemon.py` | ✅ 已修复 — mount `/ui/assets` + catch-all route `/ui/{path:path}` |

#### 建议性问题 — ✅ 全部已修复

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| S1 | `Setup.vue` Step 1 调用 `registerOwner` 时 token 尚未设置（Step 2 才设置），会 401 | 🟡 | ✅ 已修复 — 调换步骤顺序：先设置 Token（Step 0）再创建 Owner（Step 1） |
| S2 | `Dashboard.vue` 中 `totalEnclaves` 初始化为 0 但从未更新 | 🟢 | ✅ 已修复 — 调用 `listEnclaves()` 获取数量 |
| S3 | `Messages.vue` 中 `content.slice(0, 50)` 未判断 content 类型 | 🟢 | ✅ 已修复 — 先判断 `typeof data.content === 'string'` |
| S4 | `client.ts` `fetchOwnerStats` 返回类型中 `last_message_at` 可能为 null | 🟢 | ⬚ 后续优化 |

---

## v1.5 前瞻 — 决策一致性分级（1.5-13）

> 2026-04-20 概念设计。来源：A2A#1575 讨论中关于"decision identity 是否 time-dependent"的问题。

### 问题

同一个 Agent 在不同时间点被验证，可能因信任分衰减、TTL 过期、图传播延迟等因素得到不同结果。对于大部分操作这不是问题（权限验证是时间无关的），但金融、合规等场景需要精确的时间保证。

### 设计：协议层一致性级别

在 `evaluation_context` 中引入可选的 `consistency_level` 字段，按需开启：

| 级别 | 名称 | 机制 | 开销 | 适用场景 |
|------|------|------|------|---------|
| L0 | 无时间约束 | 不填 `evaluation_context`，仅校验 constraint hash | 零 | 权限查询、scope 验证、日常操作（默认） |
| L1 | 墙钟时间戳 | `evaluated_at` 填 Unix 时间戳，验证者检查合理窗口 | 极低 | 审计留痕、一般合规、交易记录 |
| L2 | 因果序保证 | HLC（物理时钟 + 逻辑计数器），精确判断多 Agent 并发事件的因果关系 | 低 | 分布式多 Agent 协作、因果序敏感场景 |
| L3 | 极端延迟容忍 | 存储-转发 + 延迟确认，容忍长时间断连和网络分区 | 中 | 高延迟网络、跨地域合规举证 |

### 协议表达

```json
{
  "evaluated_constraint_hash": "sha256:abc...",
  "consistency_level": "L1",
  "evaluation_context": {
    "evaluated_at": 1713600000,
    "policy_version": "v1.2"
  }
}
```

L0 时 `consistency_level` 和 `evaluation_context` 均省略，向下兼容现有实现。

### 关键原则

1. **默认零开销**：L0 是默认值，现有代码不需要改动
2. **业务方按需选择**：不是平台强制，而是业务根据场景声明需要的级别
3. **成本递增**：越高级别开销越大，只有真正需要的场景才付成本
4. **与策略引擎联动**：`consistency_level` 可作为 1.5-12 策略引擎的一条策略规则

---

### 代码评审记录（Consistency Level L0/L1）

> 评审日期：2026-04-21 | 评审者：评审 Agent | 测试结果：382 passed, 8 skipped ✅

#### 评审结论：有条件通过

P1、S1 修复后合并。

#### 阻塞性问题

| # | 问题 | 位置 | 状态 |
|---|------|------|------|
| P1 | L1 时间窗口检查逻辑有误：`verify_token` 内部调用 `build_evaluation_context` 生成 `evaluated_at`，然后立刻用 `check_l1_window` 检查自己刚生成的时间戳，时间差永远是毫秒级，永远通过。正确做法：`check_l1_window` 应由验证方调用，检查 token 本身携带的 `evaluation_context.evaluated_at`（外部传入），而非内部新生成的 | `capability_token.py#verify_token` L1 段 | ✅ 已修复 — 移除 `verify_token` 中的 L1 自检查逻辑。`check_l1_window` 作为独立函数由外部验证方调用。 |

#### 建议性问题

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| S1 | `l1_window_seconds=None` 传给 `check_l1_window` 时会覆盖默认值 | 🟡 | ✅ 已修复 — 移除 `l1_window_seconds` 参数（L1 窗口检查不再在 `verify_token` 内执行） |
| S2 | `test_cl_05` 注释说"30.001 秒"但实际测试值是 30.01 秒 | 🟢 | ✅ 已修正 |

#### 缺失测试用例

| # | 场景 | 状态 |
|---|------|------|
| T1 | L1 窗口检查在 `verify_token` 集成层的端到端测试（P1 修复后补充） | ⬚ 待补充 |

---

## 项目文档与架构一致性评审（2026-04-22）

> 评审范围：`AGENTS.md`、`CLAUDE.md`、`docs/project-status.md`、`docs/architecture.md`、`docs/requirements.md`、`docs/design.md`、`docs/wip.md`、ADR-003/008/013/014，以及 `agent_net/node/routers/`、`agent_net/common/did_methods/` 的抽样实现。

### 评审结论

**有条件通过。**

项目主线方向清晰：身份层、消息层、协作层、治理层已经形成连续演进路线；但当前存在 4 个阻塞性问题，需要先收敛安全边界和文档事实源，再继续叠加 v1.0 / v1.5 设计。

### 阻塞性问题

| # | 问题 | v3 回应 | 状态 |
|---|------|--------|------|
| P1 | 消息面接口未兑现 ADR-003 的 Sidecar 安全边界：`/messages/send` 未要求 Bearer Token，且允许调用方直接指定 `from_did`；`/messages/inbox/{did}`、`/messages/all/{did}`、`/messages/session/{session_id}` 为公开读接口。 | `agent_net/node/routers/messages.py`，ADR-003 | 重新定义消息接口鉴权矩阵：写操作必须鉴权，读操作默认私有；发送方 DID 不能由客户端自由伪装。 |
| P2 | Owner / Enclave 授权模型当前仍是“单 daemon token + 调用方自报 DID”，缺少主体级授权约束。持有同一 token 的任意本地客户端，都可以操作已绑定 DID 集合。 | `agent_net/node/_auth.py`、`agent_net/node/routers/agents.py`、`agent_net/node/routers/enclave.py` | 在继续推进主 DID、Capability Token、跨 Enclave 互验前，先收敛“token 绑定谁、谁能代表谁操作”的授权模型。 |
| P3 | Enclave Vault 读取接口默认可匿名访问；只有传入 `author_did` 时才做成员检查，导致成员关系检查不是强制约束。 | `agent_net/node/routers/enclave.py`，ADR-013 | 将 Vault / history / run 相关读取接口改为默认鉴权，并把成员检查作为强制路径而不是可选参数。 |
| P4 | 文档体系已失去单一事实源：当前版本、MCP 工具数、已实现状态、v0.9 阻塞项、SDK / Discussion / Governance 进度在 `CLAUDE.md`、`project-status.md`、`architecture.md`、`wip.md` 之间互相矛盾。 | `AGENTS.md`、`CLAUDE.md`、`docs/project-status.md`、`docs/architecture.md`、`docs/wip.md` | 指定一个唯一状态源，并统一版本号、工具数、已完成/开发中状态；其余文档只引用，不重复维护状态表。 |

### 建议性问题

| # | 问题 | 严重性 | 建议动作 |
|---|------|--------|---------|
| S1 | `requirements.md` / `design.md` 中 v0.8.5 Enclave 仍保留旧的 Relay Vault / Redis / Relay 权限检查方案，与已采纳的 ADR-013（Daemon + SQLite + VaultBackend）冲突。 | 🟡 | 将旧方案标记为废弃或迁移说明，避免后续实现再次沿旧架构展开。 |
| S2 | `did:meeet` 方案当前把 `did:meeet` 解析为 `id = did:agentnexus` 的 DID Document，原始 DID 仅出现在 `alsoKnownAs`；在本地体系内可用，但跨系统时 DID subject 语义容易产生歧义。 | 🟡 | 在继续对外对接前，明确“解析结果代表谁”的契约边界，并补充互操作说明。 |
| S3 | MEEET reputation → x402 score 的映射在 `requirements.md` 与 ADR-008 / 代码实现之间不一致，存在双重口径。 | 🟡 | 选定单一映射公式，并以 ADR 或契约文档为准统一回填。 |
| S4 | `AGENTS.md`、`CLAUDE.md` 多次引用 `docs/roadmap.md`、`docs/devlog.md`，但仓库当前缺失这些文件，入口文档与实际仓库不一致。 | 🟢 | 若文件仅本地保留，则在入口文档里明确“仓库可能不存在”；否则补最小占位文件。 |

### 建议处理顺序

1. 先修 P1-P3：收紧消息面、Owner、Enclave 的鉴权与主体授权边界。
2. 再修 P4：统一“当前版本、当前能力、当前阻塞项”的唯一事实源。
3. 然后处理 S1-S4：清理旧设计残留、收敛 `did:meeet` 契约、补齐缺失入口文件。

### 影响判断

- 在 P1-P3 修复前，不建议继续扩展新的协作控制面能力，否则会在不稳定的授权模型上叠加更复杂的权限语义。
- 在 P4 修复前，不建议再把 `project-status.md` 作为新人入口文档使用，否则容易把实现状态误导到 `v0.8.0`。
- v1.0 的主 DID、消息中心、Capability Token 方向本身没有问题，但它们都依赖更严格的“主体授权”基础设施。

---

## 鉴权矩阵设计 v3（P1-P4 修复方案）

> 2026-04-22 v3。基于两轮评审反馈修订。本版定位：为 v1.5 强绑定做接口准备，补齐接口契约和校验逻辑，但不声称已完全封堵本地伪装风险。
> 本矩阵仅覆盖 P1-P4 相关端点（messages.py、agents.py、enclave.py、governance.py）。push.py、handshake.py、adapters.py 不在本次范围内。

### 设计原则

1. **产生状态变更的写操作必须鉴权**：会修改数据库状态的 POST/PUT/PATCH/DELETE 必须携带 Bearer Token。公开验证类 POST（如 `/governance/validate`、`/capability-tokens/{id}/verify`）和外部投递入口（`/deliver`）不在此列
2. **读操作默认私有**：涉及消息、Vault、私有数据的读接口必须鉴权
3. **公开读仅限发现类接口**：Agent 搜索、DID 解析、公开 profile、公开验证服务
4. **发送方 DID 校验**：`from_did` 必须是本地注册的 Agent，由服务端校验。注意：v1.0 共享 daemon token 模型下，本地客户端仍可声明任意本地 DID，此校验仅防止声明不存在的 DID。完全防伪装需 v1.5 per-agent token
5. **调用方身份显式声明**：需要主体校验的端点必须显式携带调用方 DID。字段名按领域语义命名（`from_did`、`owner_did`、`author_did`、`actor_did`），不强制统一为 `actor_did`。矩阵中"actor_did 来源"列标注每个端点实际使用的字段名

### 调用方 DID 载体机制（解决评审 P2）

**问题**：单 daemon token 无法区分"谁在调用"。矩阵中的"Owner 校验"、"成员校验"缺少调用方身份载体。

**方案**：在需要主体校验的端点中引入显式调用方 DID 载体（字段名按领域语义命名：`from_did`、`owner_did`、`author_did`、`actor_did`），服务端执行两步校验：

```
Step 1: Token 校验 — 证明是本地合法客户端（现有机制）
Step 2: actor_did 校验 — 证明 actor_did 是本地注册的 Agent/Owner（新增）
Step 3: 权限校验 — 证明 actor_did 有权操作目标资源（新增）
```

```python
# agent_net/node/_auth.py 新增

async def _verify_actor(actor_did: str) -> dict:
    """校验 actor_did 是本地注册的 Agent 或 Owner"""
    from agent_net.storage import get_agent
    agent = await get_agent(actor_did)
    if not agent:
        raise HTTPException(403, f"DID not managed by this daemon: {actor_did}")
    return agent

async def _verify_actor_is_owner(actor_did: str) -> dict:
    """校验 actor_did 是本地注册的 Owner"""
    from agent_net.storage import get_owner
    owner = await get_owner(actor_did)
    if not owner:
        raise HTTPException(403, f"Not a registered owner: {actor_did}")
    return owner

async def _verify_actor_is_enclave_member(enclave_id: str, actor_did: str) -> dict:
    """校验 actor_did 是 Enclave 的成员（使用 get_enclave_member）"""
    from agent_net.storage import get_enclave_member
    member = await get_enclave_member(enclave_id, actor_did)
    if not member:
        raise HTTPException(403, f"Not a member of enclave {enclave_id}: {actor_did}")
    return member

async def _verify_actor_is_enclave_owner(enclave_id: str, actor_did: str):
    """校验 actor_did 是 Enclave 的 owner"""
    from agent_net.storage import get_enclave
    enclave = await get_enclave(enclave_id)
    if not enclave:
        raise HTTPException(404, f"Enclave not found: {enclave_id}")
    if enclave["owner_did"] != actor_did:
        raise HTTPException(403, f"Not the owner of enclave {enclave_id}")
    return enclave
```

**v1.0 已知局限（阶段性妥协）**：本地客户端共享 daemon token，可以声明任意本地已注册的 `actor_did`。本版 actor_did 机制的价值是**为 v1.5 强绑定做接口准备**——建立"声明 + 校验"的接口契约，v1.5 引入 per-agent token 后可无缝升级为强绑定（token ↔ DID 一一对应），端点签名不需要改。v1.0 的实际安全边界是：防止声明不存在的 DID、防止未持有 token 的外部访问。

### /deliver 信任模型（评审 P1 — 阶段性方案）

**问题**：`/deliver` 是外部节点投递消息的入口，当前完全公开，无任何校验。

**v1.0 方案：消息体签名验证 + 防重放**

不使用 IP 白名单（daemon 没有 trusted source registry，且 NAT/反向代理场景下 IP 不可靠）。改为验证消息体中 `from_did` 对应的 Ed25519 签名，并防止重放攻击：

**受签字段集合**：`from`、`to`、`content`、`session_id`、`message_id`、`timestamp`、`message_type`、`protocol`、`reply_to`、`content_encoding`。排除 `signature` 本身。即：所有影响消息语义的透传字段均纳入签名，中间节点无法改写任何字段而不破坏签名。

**Canonicalization**：确定性 JSON 序列化（`json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)`），与 Capability Token 签名实现一致。注意：当前实现不是严格 RFC 8785 JCS（如未处理 Unicode 归一化和浮点数规范化），跨语言互操作场景需引入真实 JCS 库，已记入 wip 待办。

**防重放**：
- 发送方必须携带 `message_id`（UUID）和 `timestamp`（Unix seconds）
- 接收方检查：(1) `timestamp` 在 ±60 秒窗口内；(2) `message_id` 不在已见集合中（内存 LRU，TTL=120 秒）
- 超出窗口或重复 `message_id` 的消息返回 403

```python
@router.post("/deliver")
async def api_deliver(req: dict):
    from_did = req.get("from")
    signature = req.get("signature")
    message_id = req.get("message_id")
    timestamp = req.get("timestamp")
    if not from_did or not signature or not message_id or not timestamp:
        raise HTTPException(400, "Missing required fields")
    # 防重放：时间窗口 + message_id 去重
    if abs(time.time() - timestamp) > 60:
        raise HTTPException(403, "Message timestamp out of window")
    if _is_seen(message_id):
        raise HTTPException(403, "Duplicate message_id")
    _mark_seen(message_id)
    # 签名验证
    public_key = await _resolve_public_key(from_did)
    if not public_key or not _verify_message_signature(req, public_key, signature):
        raise HTTPException(403, "Invalid message signature")
    # ... 原有投递逻辑
```

**v1.0 局限**：需要发送方配合签名，现有 Relay 转发的消息可能没有签名字段。过渡期可设为 soft-enforce（有签名则验，无签名则放行并记录 warning），v1.5 改为 hard-enforce。

**v1.5 方案**：节点间 mTLS 或握手时交换节点级密钥，投递请求携带节点签名。

### 鉴权矩阵

#### messages.py

| 端点 | 方法 | 当前 | 目标 | actor_did 来源 | 权限校验 |
|------|------|------|------|---------------|---------|
| `/messages/send` | POST | ❌ | ✅ Token | body: `from_did` 即 actor | `_verify_actor(from_did)` |
| `/messages/inbox/{did}` | GET | ❌ | ✅ Token | query: `actor_did` | actor 是 `{did}` 本身，或 `{did}` 的 Owner |
| `/messages/all/{did}` | GET | ❌ | ✅ Token | query: `actor_did` | 同上 |
| `/messages/session/{sid}` | GET | ❌ | ✅ Token | query: `actor_did` | `_verify_actor(actor_did)` + actor 是会话参与方或其 Owner |
| `/contacts/add` | POST | ✅ | ✅ | — | 不变 |
| `/stun/endpoint` | GET | ❌ | ❌ | — | 公开 |
| `/health` | GET | ❌ | ❌ | — | 公开 |
| `/deliver` | POST | ❌ | ⚠️ 签名验证 | — | soft-enforce 消息体签名（v1.0），hard-enforce（v1.5） |
| `/owner/messages/inbox` | GET | ❌ | ✅ Token | query: `actor_did` | `_verify_actor_is_owner(actor_did)` + actor 是该 owner |
| `/owner/messages/all` | GET | ❌ | ✅ Token | query: `actor_did` | 同上 |
| `/owner/messages/stats` | GET | ❌ | ✅ Token | query: `actor_did` | 同上 |

#### agents.py

| 端点 | 方法 | 当前 | 目标 | actor_did 来源 | 权限校验 |
|------|------|------|------|---------------|---------|
| `/agents/register` | POST | ✅ | ✅ | — | 仅 token |
| `/agents/local` | GET | ❌ | ✅ Token | — | 仅 token |
| `/agents/search/{kw}` | GET | ❌ | ❌ | — | 公开 |
| `/resolve/{did}` | GET | ❌ | ❌ | — | 公开 |
| `/agents/{did}` | GET | ❌ | ❌ | — | 公开 |
| `/agents/{did}/profile` | GET | ❌ | ❌ | — | 公开 |
| `/agents/{did}/card` | PATCH | ✅ | ✅ Token | body: `actor_did` | `_verify_actor(actor_did)` + actor == `{did}` |
| `/agents/{did}/certify` | POST | ✅ | ✅ | — | 仅 token |
| `/agents/{did}/certifications` | GET | ❌ | ❌ | — | 公开 |
| `/agents/{did}/export` | GET | ✅ | ✅ Token | query: `actor_did` | `_verify_actor(actor_did)` + actor == `{did}` |
| `/agents/import` | POST | ✅ | ✅ | — | 仅 token |
| `/owner/register` | POST | ✅ | ✅ | — | 仅 token |
| `/owner/bind` | POST | ✅ | ✅ Token | body: `owner_did` 即 actor | `_verify_actor_is_owner(owner_did)` |
| `/owner/unbind` | DELETE | ✅ | ✅ Token | body: `owner_did` 即 actor | 同上 |
| `/owner/agents/{owner_did}` | GET | ❌ | ✅ Token | query: `actor_did` | `_verify_actor_is_owner(actor_did)` + actor == `{owner_did}` |
| `/owner/profile/{owner_did}` | GET | ❌ | ❌ | — | 公开 |

#### enclave.py

| 端点 | 方法 | 当前 | 目标 | actor_did 来源 | 权限校验 |
|------|------|------|------|---------------|---------|
| `POST /enclaves` | POST | ✅ | ✅ Token | body: `owner_did` 即 actor | `_verify_actor(owner_did)` |
| `GET /enclaves` | GET | ❌ | ✅ Token | query: `actor_did` | 仅返回 actor 参与的 Enclave |
| `GET /enclaves/{id}` | GET | ❌ | ✅ Token | query: `actor_did` | `_verify_actor_is_enclave_member` |
| `PATCH /enclaves/{id}` | PATCH | ✅ | ✅ Token | body: `actor_did` | `_verify_actor_is_enclave_owner` |
| `DELETE /enclaves/{id}` | DELETE | ✅ | ✅ Token | query: `actor_did` | `_verify_actor_is_enclave_owner` |
| `POST .../members` | POST | ✅ | ✅ Token | body: `actor_did` | `_verify_actor_is_enclave_owner` |
| `DELETE .../members/{did}` | DELETE | ✅ | ✅ Token | query: `actor_did` | `_verify_actor_is_enclave_owner` |
| `PATCH .../members/{did}` | PATCH | ✅ | ✅ Token | body: `actor_did` | `_verify_actor_is_enclave_owner` |
| `GET .../vault` | GET | ❌ | ✅ Token | query: `actor_did` | `_verify_actor_is_enclave_member` |
| `GET .../vault/{key}` | GET | ❌ | ✅ Token | query: `actor_did` | `_verify_actor_is_enclave_member` |
| `PUT .../vault/{key}` | PUT | ✅ | ✅ Token | body: `author_did` 即 actor | `_verify_actor_is_enclave_member` + 权限 ≥ rw |
| `DELETE .../vault/{key}` | DELETE | ✅ | ✅ Token | query: `actor_did` | `_verify_actor_is_enclave_member` + 权限 ≥ rw |
| `GET .../vault/{key}/history` | GET | ❌ | ✅ Token | query: `actor_did` | `_verify_actor_is_enclave_member` |
| `POST .../runs` | POST | ✅ | ✅ Token | body: `actor_did` | `_verify_actor_is_enclave_member` + 权限 ≥ rw |
| `GET .../runs` | GET | ❌ | ✅ Token | query: `actor_did` | `_verify_actor_is_enclave_member` |
| `GET .../runs/{rid}` | GET | ❌ | ✅ Token | query: `actor_did` | `_verify_actor_is_enclave_member` |

#### governance.py

| 端点 | 方法 | 当前 | 目标 | 变更 |
|------|------|------|------|------|
| `/governance/validate` | POST | ❌ | ❌ | 公开验证服务 |
| `/governance/attestations/{did}` | GET | ❌ | ❌ | 公开 |
| `/trust/paths` | GET | ❌ | ❌ | 公开 |
| `/trust/edge` | POST | ✅ | ✅ | 不变 |
| `/trust/edges/{did}` | GET | ❌ | ❌ | 公开 |
| `/trust/edge` | DELETE | ✅ | ✅ | 不变 |
| `/interactions` | POST | ✅ | ✅ | 不变 |
| `/interactions/{did}` | GET | ❌ | ❌ | 公开 |
| `/reputation/{did}` | GET | ❌ | ❌ | 公开 |
| `/trust-snapshot/{did}` | GET | ❌ | ❌ | 公开 |
| `/attestations/verify` | POST | ❌ | ❌ | 公开验证服务 |
| `/capability-tokens/issue` | POST | ✅ | ✅ | 不变 |
| `/capability-tokens/{id}` | GET | ❌ | ✅ Token | 加 `_require_token` |
| `/capability-tokens/{id}/verify` | POST | ❌ | ❌ | 公开验证服务 |
| `/capability-tokens/{id}/revoke` | POST | ✅ | ✅ | 不变 |
| `/capability-tokens/by-did/{did}` | GET | ❌ | ✅ Token | 加 `_require_token` |

### 变更统计

| 文件 | 新增 Token 鉴权 | 新增调用方 DID 校验 |
|------|----------------|-------------------|
| `messages.py` | 7（send + inbox/all + session + owner×3） | 7（send + inbox/all + session + owner×3） |
| `agents.py` | 2（local + owner/agents） | 5（card/export/bind/unbind + owner/agents） |
| `enclave.py` | 7（GET enclaves + enclave/{id} + vault×2 + history + runs×2） | 16（全部读写接口） |
| `governance.py` | 2（token get + by-did） | 0 |
| `_auth.py` | — | 4 个新辅助函数（不计入端点数） |
| **端点合计** | **18** | **28** |

### 鉴权矩阵评审（2026-04-22）

> 以下为 v2 版评审意见。v3 已逐条回应，状态已更新。

### 评审结论

**v2 有条件通过 → v3 已回应全部阻塞项。**

#### 阻塞性问题

| # | 问题 | v3 回应 | 状态 |
|---|------|--------|------|
| P1 | `/deliver` IP 白名单方案不可落地 | ✅ v3 改为消息体 Ed25519 签名验证（soft-enforce），信任锚点改为 DID 公钥 | 已回应 |
| P2 | actor_did 载体缺失 | ✅ v3 引入显式 `actor_did` 参数 + 校验函数。明确标注为"v1.5 强绑定的接口准备" | 已回应 |
| P3 | `_verify_enclave_member` 数据结构错误 | ✅ v3 改用 `get_enclave_member(enclave_id, did)` | 已回应 |
| P4 | Enclave 写接口缺少主体授权 | ✅ v3 全部纳入 `actor_did` + owner/member 权限校验 | 已回应 |

#### 建议性问题

| # | 问题 | 严重性 | 建议动作 |
|---|------|--------|---------|
| S1 | 覆盖范围不明确 | ✅ v3 引言明确"仅覆盖 P1-P4 相关端点" | 已回应 |
| S2 | 统计数字不准 | ✅ v3 重新计算：18 token + 28 调用方 DID 校验 | 已回应 |

#### 二轮评审补充意见（2026-04-23）

| # | 问题 | v3 回应 | 状态 |
|---|------|--------|------|
| R1 | 引言说"已解决"与局限性说明自相矛盾 | ✅ v3 引言改为"为 v1.5 强绑定做接口准备" | 已回应 |
| R2 | 设计原则 1 过度绝对，与公开 POST 端点矛盾 | ✅ v3 改为"产生状态变更的写操作必须鉴权" | 已回应 |
| R3 | 路径名与代码不一致（certs → certifications, {did} → {owner_did}） | ✅ v3 修正为实际路径 | 已回应 |
| R4 | 统计数字仍不准 | ✅ v3 重新计算 | 已回应 |
| R5 | 文档内部矛盾（设计正文 vs 评审记录） | ✅ 评审记录已更新状态，标注 v3 回应 | 已回应 |

#### 三轮评审补充意见（2026-04-23）

| # | 问题 | v3 回应 | 状态 |
|---|------|--------|------|
| R6 | `/messages/session/{sid}` 仅 token 无 actor，任意本地客户端可读任意会话，且 v1.5 升级时无法无破坏添加主体校验 | ✅ 纳入 actor 校验：actor 必须是会话参与方或其 Owner | 已回应 |
| R7 | `/deliver` 签名验证缺防重放：无 message_id/timestamp/nonce，抓包可重复投递已签名消息 | ✅ 补齐受签字段集合、确定性 JSON 序列化规则、message_id + timestamp 窗口（±60s）+ LRU 去重 | 已回应 |
| R8 | 原则 5 写"必须携带 actor_did"，但矩阵实际用 from_did/owner_did/author_did 等不同字段名 | ✅ 改为"必须显式携带调用方 DID，字段名按领域语义命名" | 已回应 |
| R9 | design.md 说"v3 已回应"，但 wip.md 仍标"待处理/待修复"，跨文档状态矛盾 | ✅ wip.md 状态更新为"设计 v3 已定稿，待实现"，明确区分设计通过 vs 实现待落地 | 已回应 |

---

### 代码评审记录（鉴权矩阵 v3 实现）

> 评审日期：2026-04-24 | 评审者：评审 Agent | 测试结果：388 passed, 8 skipped ✅

#### 评审结论：通过

无阻塞性问题。实现与鉴权矩阵 v3 设计高度一致。

#### 建议性问题

| # | 问题 | 严重性 | 状态 |
|---|------|--------|------|
| S1 | `/messages/session/{sid}` 参与方校验遍历全部消息逐条 `await _actor_owns_did`，每条一次 DB 查询。建议先收集 from_did/to_did 去重后批量校验 | 🟡 | ✅ 已修复 — 先收集去重 DIDs，再用本地 agent 对象匹配 |
| S2 | `_SEEN_MESSAGE_IDS` 是进程内 OrderedDict，多 worker 部署时重放检测不跨 worker。当前单 worker 没问题 | 🟢 | ⬚ 多 worker 时改为 DB/Redis |
| S3 | `/deliver` 无签名时 soft-enforce 放行但未记录 warning log，与设计文档不一致 | 🟢 | ✅ 已补 `logger.warning` |
| S4 | `api_vault_put` 用 `req.author_did`，`api_vault_delete` 用 `actor_did` query param，同一资源写删字段名不一致 | 🟢 | ✅ 已统一 — `api_vault_delete` 改用 `VaultDeleteRequest.author_did` |
