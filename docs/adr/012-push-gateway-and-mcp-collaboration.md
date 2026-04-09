# ADR-012: AgentNexus Communication Protocol (ACP)

## 状态

提议

## 日期

2026-04-06

## 背景

AgentNexus 从 v0.7 到 v0.8 逐步积累了一系列通信机制：DID 身份（ADR-001）、四步握手（ADR-002）、Gatekeeper 访问控制（ADR-005）、智能路由（router.py）、信封消息格式（ADR-007）、Action Layer 协作（ADR-007）、Discussion 讨论（ADR-011）、Emergency 熔断。

这些机制各自有效，但缺少一个统一的协议视角来描述它们之间的关系。同时存在两个关键缺口：

1. **MCP 协作工具缺失** — SDK 已实现 Action Layer + Discussion，但 MCP Server 只有基础消息工具，Kiro / Claude Code / OpenClaw 无法使用结构化协作功能
2. **Agent 无法被主动唤醒** — 消息投递是"邮箱模式"，缺少注册/在线管理和消息到达通知机制

本 ADR 将现有机制和新增设计统一为 **AgentNexus Communication Protocol (ACP)**——一个完整的 Agent 通信协议栈。

## 决策

### §1 协议分层模型

ACP 是一个九层协议栈，融合三种行业模型的优势：

```
┌─────────────────────────────────────────────────────────────┐
│ L8  适配层   Platform Adapters                    Matrix AS │
│     OpenClaw / Webhook / Dify / Coze 各平台对接桥梁         │
├─────────────────────────────────────────────────────────────┤
│ L7  协作层   Collaboration                                  │
│     Action Layer（4 种）+ Discussion（4 种）+ Emergency      │
├─────────────────────────────────────────────────────────────┤
│ L6  消息层   Messaging                                      │
│     信封模式：content + message_type + protocol + session_id │
├─────────────────────────────────────────────────────────────┤
│ L5  推送层   Push & Wake                            APNs    │
│     消息到达 → 精准敲门 → 唤醒 Agent session                 │
├─────────────────────────────────────────────────────────────┤
│ L4  传输层   Transport & Routing                            │
│     local → P2P → Relay → 离线存储，四级降级                 │
├─────────────────────────────────────────────────────────────┤
│ L3  注册层   Registration & Presence              SIP REG   │
│     Agent 报到 + 唤醒方式注册 + TTL 续约 + 在线状态          │
├─────────────────────────────────────────────────────────────┤
│ L2  访问层   Access Control                                 │
│     Gatekeeper 三模式（Public / Ask / Private）              │
├─────────────────────────────────────────────────────────────┤
│ L1  安全层   Security                                       │
│     AHP 四步握手 + X25519 ECDH + AES-256-GCM E2EE           │
├─────────────────────────────────────────────────────────────┤
│ L0  身份层   Identity                                       │
│     DID（did:agentnexus / did:web / did:key / did:meeet）    │
└─────────────────────────────────────────────────────────────┘
```

#### 与行业协议的融合关系

| ACP 层 | 借鉴来源 | 借鉴了什么 | 没有借鉴什么 |
|--------|---------|-----------|-------------|
| L3 注册层 | SIP REGISTER | Agent 报到 + TTL 续约 + 过期自动下线 | SIP 的实时会话建立（INVITE/BYE） |
| L5 推送层 | APNs / FCM | 消息到达后按注册 URI 精准推送 | 中心化推送网关（改为可插拔 Webhook）；离线队列（复用 L4 现有离线存储） |
| L8 适配层 | Matrix Application Service | 平台桥接抽象 + 双向消息转换 | Matrix 的 Room DAG / Megolm E2EE |

#### 各层实现状态

| 层 | 状态 | 对应 ADR / 代码 |
|----|------|----------------|
| L0 身份 | ✅ 已实现 | ADR-001, `common/did.py` |
| L1 安全 | ✅ 已实现 | ADR-002, `common/handshake.py` |
| L2 访问 | ✅ 已实现 | ADR-005, `node/gatekeeper.py` |
| L3 注册 | ⬚ v0.9 新增 | 本 ADR §3 |
| L4 传输 | ✅ 已实现 | `router.py` |
| L5 推送 | ⬚ v0.9 新增 | 本 ADR §4 |
| L6 消息 | ✅ 已实现 | ADR-007, `storage.py` |
| L7 协作 | ✅ SDK 已实现，⬚ MCP 待补 | ADR-007/011, 本 ADR §5 |
| L8 适配 | ✅ 已实现 | ADR-010, `adapters/` |

### §2 一条消息的完整生命周期

```
① L3 注册报到（SIP REGISTER 风格）
   Agent 启动 → "我是 DID:xxx，webhook 唤醒，有效期 1 小时"

② L6 消息发送
   Agent A → send_message(to=B, content, message_type) → Daemon

③ L4 传输路由
   Daemon → local / P2P / Relay / 离线存储

④ L5 精准敲门（APNs 风格）
   消息落地 → 查 B 的注册信息 → POST callback_url 通知

⑤ L8 平台适配（Matrix AS 风格）
   各平台收到敲门 → 自行唤醒 Agent session

⑥ L7 协作处理
   Agent B 收到消息 → 根据 message_type 分发到对应处理逻辑
```

### §3 L3 注册层设计（v0.9）

借鉴 SIP REGISTER，Agent 启动时向 Daemon 注册自己的在线状态和唤醒方式。

#### 注册模型

```
Agent 启动 → REGISTER(did, callback_url, callback_type, expires=3600)
Agent 运行中 → 每 expires/2 自动续约 REFRESH
Agent 正常关闭 → UNREGISTER（主动注销）
Agent 异常退出 → TTL 到期 → Daemon 自动清理 → 回退到离线存储模式
```

#### 数据模型

```sql
CREATE TABLE push_registrations (
    registration_id TEXT PRIMARY KEY,        -- UUID，唯一标识
    did TEXT NOT NULL,
    callback_url TEXT NOT NULL,
    callback_type TEXT DEFAULT 'webhook',    -- webhook / sse / platform
    callback_secret TEXT NOT NULL,           -- HMAC 签名密钥（注册时生成）
    push_key TEXT,                            -- 平台侧标识符
    expires_at REAL NOT NULL,                 -- Unix timestamp，过期自动失效
    created_at REAL NOT NULL,
    UNIQUE(did, callback_url, callback_type)  -- 同一 DID 同一 URL 同类型只能一条
);
CREATE INDEX idx_push_registrations_did ON push_registrations(did);
CREATE INDEX idx_push_registrations_expires ON push_registrations(expires_at);
```

一个 DID 可注册多个 callback（同一 Agent 在多个平台有 session），每个独立 TTL。

#### 安全约束

1. **DID-Token 绑定**：`/push/register` 的 `did` 参数必须与 Bearer Token 绑定的 DID 一致，不允许为其他 DID 注册回调
2. **SSRF 防护**：`callback_url` 默认仅允许 `127.0.0.1` / `localhost`；如需注册外部地址，需在 Daemon 配置中显式开启 `push.allow_external_callback = true` 并配置允许的 CIDR 白名单
3. **推送超时**：单次推送 HTTP 请求超时 5 秒，失败静默跳过（消息已安全存储）`callback_secret` 在注册时由 Daemon 生成，用于推送时的 HMAC 签名验证。

#### Daemon 端点

```
POST   /push/register   注册唤醒方式（需 Bearer Token）
POST   /push/refresh    续约 TTL（需 Bearer Token）
DELETE /push/{did}       主动注销（需 Bearer Token）
GET    /push/{did}       查询注册状态（公开）
```

**Bearer Token 来源**：复用现有 Daemon Token 机制（`data/daemon_token.txt` 或 `~/.agentnexus/daemon_token.txt`），与 MCP Server 鉴权机制一致。

注册请求：

```json
{
  "did": "did:agentnexus:z6Mk...designer",
  "callback_url": "http://localhost:3001/notify",
  "callback_type": "webhook",
  "expires": 3600
}
```

响应：

```json
{
  "status": "ok",
  "expires_at": 1712403600.0,
  "registration_id": "reg_a1b2c3d4",
  "callback_secret": "sk_x7y8z9w0..."  // 仅注册时返回一次，需妥善保存
}
```

### §4 L5 推送层设计（v0.9）

借鉴 APNs 的精准推送，消息到达后主动通知目标 Agent。

#### 推送流程

```python
import hmac
import hashlib

# 在 route_message() 完成消息投递/存储后触发
async def _push_notify(to_did, from_did, session_id, message_type, content):
    registrations = await get_active_registrations(to_did)  # expires_at > now()
    if not registrations:
        return  # 无注册，静默（消息已存储，等 fetch_inbox）

    preview = content[:200] if isinstance(content, str) else json.dumps(content)[:200]
    timestamp = time.time()

    for reg in registrations:
        try:
            body = {
                "event": "new_message",
                "to_did": to_did,
                "from_did": from_did,
                "session_id": session_id,
                "message_type": message_type,
                "preview": preview,
                "timestamp": timestamp,  # 防重放
            }
            body_json = json.dumps(body, separators=(',', ':'))
            signature = hmac.new(
                reg["callback_secret"].encode(),
                body_json.encode(),
                hashlib.sha256
            ).hexdigest()

            await aiohttp.post(reg["callback_url"],
                json=body,
                headers={
                    "X-Nexus-Signature": f"sha256={signature}",
                    "X-Nexus-Timestamp": str(timestamp),
                },
                timeout=aiohttp.ClientTimeout(total=5))
        except Exception as e:
            logger.warning(f"Push notify failed for {reg['registration_id']}: {e}")
            # 推送失败不影响消息投递，消息已安全存储
```

#### 签名验证（接收方）

```python
import hmac
import hashlib

def verify_push_signature(body_json: str, signature_header: str, secret: str,
                          timestamp: float, max_age_seconds: int = 300) -> bool:
    """验证推送签名和时效性"""
    # 1. 检查时效性（防重放）
    if abs(time.time() - timestamp) > max_age_seconds:
        return False

    # 2. 验证签名
    if not signature_header.startswith("sha256="):
        return False
    expected_sig = signature_header[7:]

    actual_sig = hmac.new(
        secret.encode(),
        body_json.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_sig, actual_sig)
```

#### 各平台对接方式

| 平台 | callback_type | 收到推送后 |
|------|--------------|-----------|
| OpenClaw（有渠道） | `platform` | 唤醒 Agent session → 推飞书/钉钉通知给人类 |
| OpenClaw（无渠道） | `webhook` | 触发 Agent Skill 执行（如果支持） |
| Kiro CLI | `webhook` | MCP 进程本地 HTTP server → 终端提示 "📬 新消息" |
| Claude Code | `webhook` | 同上 |
| Python SDK | `webhook` | SDK 直接触发 `on_message` 回调 |
| v1.0 SSE | `sse` | 不走 HTTP POST，走 SSE 长连接实时推 |

### §5 三阶段演进路线

```
v0.8 ─── L7 协作层补全 ──────────────────────────────────────
         MCP 新增 10 个协作工具
         人工切换 session 驱动，拉模式（fetch_inbox）
         协议栈：L0-L2 + L4 + L6-L8 完整可用

v0.9 ─── L3 注册层 + L5 推送层 ──────────────────────────────
         Agent 启动报到（SIP REGISTER 风格）
         消息到达精准敲门（APNs 风格）
         协议栈：L0-L8 全部就位，ACP v1.0 协议完整

v1.0 ─── L5 推送层增强（SSE 长连接）─────────────────────────
         在线时 SSE 实时推送（< 100ms）
         离线时 Webhook 通知（< 5s）
         无注册时静默存储（兼容 v0.8）
```

#### v0.8 — L7 协作层补全（拉模式，人工驱动）

| # | 功能 | 说明 |
|---|------|------|
| 0.8-14 | MCP Action Layer 工具（4 个） | propose_task / claim_task / sync_resource / notify_state |
| 0.8-15 | MCP Discussion 工具（4 个） | start_discussion / reply_discussion / vote_discussion / conclude_discussion |
| 0.8-16 | MCP Emergency + Skill 工具（2 个） | emergency_halt / list_skills |
| 0.8-17 | 跨平台配置文档 | Kiro CLI / Claude Code / OpenClaw MCP 配置示例 |

#### v0.9 — L3 + L5 注册与推送（推模式，自动通知）

| # | 功能 | 说明 |
|---|------|------|
| 0.9-14 | push_registrations 表 + CRUD | SQLite 存储注册信息 |
| 0.9-15 | /push/register + /push/refresh 端点 | Agent 报到和续约 |
| 0.9-16 | 消息到达推送回调 | route_message 后触发 _push_notify |
| 0.9-17 | MCP 自动注册 | MCP 启动时注册本地 callback + 后台续约 |
| 0.9-18 | SDK 自动注册 | connect() 时注册 + 后台续约 + 断线清理 |
| 0.9-19 | TTL 过期清理 | 定时任务清理过期注册 |

#### v1.0 — L5 推送层增强（双模式）

| # | 功能 | 说明 |
|---|------|------|
| 1.0-08 | SSE 长连接端点 | GET /push/stream/{did} |
| 1.0-09 | SDK SSE 自动连接 | connect() 优先 SSE，断线回退 Webhook |
| 1.0-10 | MCP SSE 监听（可选） | MCP 进程可选启动 SSE 监听 |

##### v1.0 SSE 设计要点

**认证**：`GET /push/stream/{did}` 通过 query parameter `?token=<bearer_token>` 认证（SSE 不支持自定义 Header），Token 与 Daemon Token 机制一致。

**重连策略**：
- SSE 标准 `retry:` 字段设为 5000ms
- 客户端断线后指数退避重连：5s → 10s → 20s → 30s（上限）
- 重连时携带 `Last-Event-ID` header，Daemon 从该 ID 之后的消息开始推送（防丢消息）

**双模式切换**：
- Agent 同时注册 SSE + Webhook 时，SSE 在线则优先走 SSE，Webhook 作为备份
- Daemon 维护 SSE 连接状态：连接存活 → 走 SSE；连接断开 → 立即回退到 Webhook
- 切换逻辑在 `_push_notify()` 中实现，对消息发送方完全透明

### §6 v0.8 详细设计：MCP 协作工具（L7 补全）

#### 设计原则

1. **不新增 Daemon 端点** — 复用 `POST /messages/send`，通过 `message_type` + `protocol=nexus_v1` 区分
2. **与 SDK 语义对齐** — MCP 工具参数和行为与 SDK 的 `propose_task()` 等方法一一对应
3. **绑定 DID 自动填充** — `from_did` 在绑定模式下自动填充
4. **AI 友好** — 独立工具名比让 AI 手动填 `message_type` 更可靠

#### 实现方式

每个协作工具 = 调用 `/messages/send` + 自动设置 `message_type` + 构造结构化 `content`。

```python
# 以 propose_task 为例
case "propose_task":
    task_id = f"task_{uuid.uuid4().hex}"
    content = {"task_id": task_id, "title": arguments["title"]}
    for key in ("description", "deadline", "required_caps"):
        if arguments.get(key):
            content[key] = arguments[key]
    result = await _call("post", "/messages/send", json={
        "from_did": _MY_DID,
        "to_did": arguments["to_did"],
        "content": content,
        "message_type": "task_propose",
        "protocol": "nexus_v1",
    })
    result["task_id"] = task_id
```

#### 返回值格式

所有工具返回 JSON，统一包含 `status` 字段。生成 ID 的工具额外返回对应 ID：

| 工具 | 返回值 |
|------|--------|
| `propose_task` | `{"status": "ok", "task_id": "task_a1b2c3d4"}` |
| `claim_task` | `{"status": "ok"}` |
| `sync_resource` | `{"status": "ok"}` |
| `notify_state` | `{"status": "ok"}` |
| `start_discussion` | `{"status": "ok", "topic_id": "topic_x7y8z9", "notified": ["did:...", "did:..."]}` |
| `reply_discussion` | `{"status": "ok"}` |
| `vote_discussion` | `{"status": "ok"}` |
| `conclude_discussion` | `{"status": "ok"}` |
| `emergency_halt` | `{"status": "ok", "halted": "did:agentnexus:z6Mk..."}` |
| `list_skills` | `{"skills": [{"agent_did": "...", "name": "...", "capabilities": [...]}]}` |

错误时返回：`{"status": "error", "message": "描述信息"}`

#### 命名约定

工具名和 message_type 有意采用不同命名风格：

- **工具名**（MCP Tool name）：动词前缀，面向 AI 调用者，如 `reply_discussion`、`propose_task`
- **message_type**（信封字段）：名词前缀，面向协议解析，如 `discussion_reply`、`task_propose`

这样 AI 看到工具名就知道"要做什么动作"，Daemon 看到 message_type 就知道"这是什么类型的消息"。

#### 10 个新增工具完整定义

##### 1. propose_task — 派发任务

message_type: `task_propose` | content: `{task_id, title, description?, deadline?, required_caps?}`

```python
Tool(name="propose_task",
     description="Propose/delegate a task to another Agent. Returns generated task_id for tracking."
                 f" Sender auto-filled as {_MY_DID}." if _MY_DID else "",
     inputSchema={"type": "object",
                  "properties": {
                      "to_did": {"type": "string", "description": "Target Agent DID"},
                      "title": {"type": "string", "description": "Task title"},
                      "description": {"type": "string", "description": "Detailed task description"},
                      "deadline": {"type": "string", "description": "Deadline (ISO date, e.g. 2026-04-10)"},
                      "required_caps": {"type": "array", "items": {"type": "string"},
                                        "description": "Required capabilities (e.g. ['Code', 'Review'])"},
                  }, "required": ["to_did", "title"]}),
```

##### 2. claim_task — 认领任务

message_type: `task_claim` | content: `{task_id, eta?, message?}`

```python
Tool(name="claim_task",
     description="Claim a task proposed by another Agent.",
     inputSchema={"type": "object",
                  "properties": {
                      "to_did": {"type": "string", "description": "Task proposer's DID"},
                      "task_id": {"type": "string", "description": "Task ID to claim"},
                      "eta": {"type": "string", "description": "Estimated completion time (e.g. '2h', '30min')"},
                      "message": {"type": "string", "description": "Optional message to proposer"},
                  }, "required": ["to_did", "task_id"]}),
```

##### 3. sync_resource — 共享资源

message_type: `resource_sync` | content: `{key, value, version?}`

```python
Tool(name="sync_resource",
     description="Share key-value data with another Agent (e.g. design docs, config, glossary).",
     inputSchema={"type": "object",
                  "properties": {
                      "to_did": {"type": "string", "description": "Target Agent DID"},
                      "key": {"type": "string", "description": "Resource key identifier"},
                      "value": {"type": "string", "description": "Resource value (use JSON string for complex data)"},
                      "version": {"type": "string", "description": "Version identifier (e.g. 'v2', '2026-04-06')"},
                  }, "required": ["to_did", "key", "value"]}),
```

##### 4. notify_state — 汇报状态

message_type: `state_notify` | content: `{status, task_id?, progress?, error?}`

```python
Tool(name="notify_state",
     description="Report task progress or status to another Agent.",
     inputSchema={"type": "object",
                  "properties": {
                      "to_did": {"type": "string", "description": "Target Agent DID"},
                      "status": {"type": "string",
                                 "enum": ["pending", "in_progress", "completed", "failed", "blocked"],
                                 "description": "Current status"},
                      "task_id": {"type": "string", "description": "Associated task ID"},
                      "progress": {"type": "number", "description": "Progress percentage 0.0-1.0"},
                      "error": {"type": "string", "description": "Error message (when status is 'failed')"},
                  }, "required": ["to_did", "status"]}),
```

##### 5. start_discussion — 发起讨论

message_type: `discussion_start` | content: `{topic_id, title, participants, context?, consensus?, seq}`

> **注意**：`start_discussion` 向 `participants` 中每个 DID 分别发送邀请消息。回复/投票/结论工具的 `to_did` 应指向讨论发起方（即 `discussion_start` 的 `from_did`）。

```python
Tool(name="start_discussion",
     description="Start a multi-agent discussion with optional voting. "
                 "Sends invitation to all participants. Returns topic_id. "
                 "Note: reply/vote/conclude tools should use initiator's DID as to_did.",
     inputSchema={"type": "object",
                  "properties": {
                      "title": {"type": "string", "description": "Discussion title"},
                      "participants": {"type": "array", "items": {"type": "string"},
                                       "description": "List of participant DIDs to invite"},
                      "context": {"type": "string", "description": "Background context for the discussion"},
                      "consensus_mode": {"type": "string",
                                         "enum": ["majority", "unanimous", "leader_decides"],
                                         "description": "Voting mode (default: majority)"},
                      "timeout_seconds": {"type": "integer",
                                          "description": "Voting timeout in seconds"},
                  }, "required": ["title", "participants"]}),
```

##### 6. reply_discussion — 回复讨论

message_type: `discussion_reply` | content: `{topic_id, content}`

> **注意**：`to_did` 应指向讨论发起方的 DID（即 `discussion_start` 的 `from_did`）。

```python
Tool(name="reply_discussion",
     description="Reply to an ongoing discussion. "
                 "to_did should be the discussion initiator's DID.",
     inputSchema={"type": "object",
                  "properties": {
                      "to_did": {"type": "string", "description": "Discussion initiator's DID"},
                      "topic_id": {"type": "string", "description": "Discussion topic ID"},
                      "content": {"type": "string", "description": "Reply content"},
                  }, "required": ["to_did", "topic_id", "content"]}),
```

##### 7. vote_discussion — 投票

message_type: `discussion_vote` | content: `{topic_id, vote, reason?}`

> **注意**：`to_did` 应指向讨论发起方的 DID（即 `discussion_start` 的 `from_did`）。

```python
Tool(name="vote_discussion",
     description="Vote on a discussion topic. "
                 "to_did should be the discussion initiator's DID.",
     inputSchema={"type": "object",
                  "properties": {
                      "to_did": {"type": "string", "description": "Discussion initiator's DID"},
                      "topic_id": {"type": "string", "description": "Discussion topic ID"},
                      "vote": {"type": "string", "enum": ["approve", "reject", "abstain"],
                               "description": "Vote choice"},
                      "reason": {"type": "string", "description": "Reason for vote"},
                  }, "required": ["to_did", "topic_id", "vote"]}),
```

##### 8. conclude_discussion — 宣布结论

message_type: `discussion_conclude` | content: `{topic_id, conclusion, conclusion_type?}`

> **注意**：`to_did` 应指向讨论参与方的 DID（发起方宣布结论时发送给参与者）。

```python
Tool(name="conclude_discussion",
     description="Conclude a discussion with a final decision. Sends conclusion to target participant. "
                 "to_did should be a participant's DID (to notify them of the conclusion).",
     inputSchema={"type": "object",
                  "properties": {
                      "to_did": {"type": "string", "description": "Participant DID to send conclusion to"},
                      "topic_id": {"type": "string", "description": "Discussion topic ID"},
                      "conclusion": {"type": "string", "description": "Final conclusion text"},
                      "conclusion_type": {"type": "string",
                                          "enum": ["consensus", "no_consensus", "escalated"],
                                          "description": "Type of conclusion (default: consensus)"},
                  }, "required": ["to_did", "topic_id", "conclusion"]}),
```

##### 9. emergency_halt — 紧急熔断

使用独立 message_type: `emergency_halt` | content: `{scope, target?, reason?}`

接收方通过 `message_type == "emergency_halt"` 直接识别熔断消息，无需检查 content 内部字段。参见 SDK `agentnexus/emergency.py` 的 `EmergencyHandler` 实现。

> **注意**：此工具仅对已建立会话（已完成握手）的 Agent 生效。`scope=all` 会向发送方的所有活跃会话逐个发送。

```python
Tool(name="emergency_halt",
     description="Broadcast emergency halt to target Agent(s). Only works for Agents with active sessions. "
                 "Requires authorization via emergency_authorized_dids config (ADR-011 §9).",
     inputSchema={"type": "object",
                  "properties": {
                      "to_did": {"type": "string", "description": "Target Agent DID (required for scope='agent' or 'task')"},
                      "scope": {"type": "string",
                                "enum": ["agent", "task", "all"],
                                "description": "agent: halt target DID; task: halt task-related agents; all: halt all active sessions"},
                      "task_id": {"type": "string", "description": "Task ID when scope='task'"},
                      "reason": {"type": "string", "description": "Reason for emergency halt"},
                  }, "required": ["scope"]}),
```

**message_type 定义**（独立类型，不复用 state_notify）：

```json
{
  "message_type": "emergency_halt",
  "protocol": "nexus_v1",
  "content": {
    "scope": "agent | task | all",
    "target": "did:agentnexus:z6Mk...",  // scope=agent 或 task 时必填
    "task_id": "task_...",               // scope=task 时必填
    "reason": "API budget exceeded"
  }
}
```

**实现逻辑**：
- `scope=agent`：向 `to_did` 发送单条 emergency_halt 消息
- `scope=task`：向任务相关的所有 Agent 发送（需要任务状态追踪，v0.9 实现）
- `scope=all`：SDK 向本地维护的已握手 DID 列表逐个发送（ADR-011 §14）

##### 10. list_skills — 查询 Skill

调用 `GET /skills`，不走消息系统。

```python
Tool(name="list_skills",
     description="List registered Skills on this node. Filter by Agent or capability.",
     inputSchema={"type": "object",
                  "properties": {
                      "agent_did": {"type": "string", "description": "Filter by Agent DID"},
                      "capability": {"type": "string", "description": "Filter by capability keyword"},
                  }}),
```

#### start_discussion 特殊处理

`start_discussion` 需要向每个 participant 发送消息。

`seq` 字段由 MCP/SDK 自动维护，调用方无需填写：
- `start_discussion` → `seq: 1`
- `reply_discussion` / `vote_discussion` → MCP 内部按 `topic_id` 递增 seq（基于内存计数器，同一 MCP 进程内保证递增）
- `conclude_discussion` → 使用当前最大 seq + 1

```python
case "start_discussion":
    topic_id = f"topic_{uuid.uuid4().hex}"
    content = {
        "topic_id": topic_id,
        "title": arguments["title"],
        "participants": arguments["participants"],
        "seq": 1,
    }
    if arguments.get("context"):
        content["context"] = arguments["context"]
    if arguments.get("consensus_mode"):
        content["consensus"] = {"mode": arguments["consensus_mode"]}
        if arguments.get("timeout_seconds"):
            content["consensus"]["timeout_seconds"] = arguments["timeout_seconds"]

    # 向每个参与者发送
    for did in arguments["participants"]:
        await _call("post", "/messages/send", json={
            "from_did": _MY_DID,
            "to_did": did,
            "content": content,
            "message_type": "discussion_start",
            "protocol": "nexus_v1",
        })
    result = {"status": "ok", "topic_id": topic_id,
              "notified": arguments["participants"]}
```

#### 跨平台 MCP 配置示例

Kiro CLI（设计 Agent）— `.kiro/settings/mcp.json`：

```json
{
  "mcpServers": {
    "nexus-designer": {
      "command": "python",
      "args": ["/path/to/main.py", "node", "mcp",
               "--name", "Designer", "--caps", "Design,Architecture"]
    }
  }
}
```

Claude Code（开发 Agent）— `.mcp.json`：

```json
{
  "mcpServers": {
    "nexus-developer": {
      "command": "python",
      "args": ["/path/to/main.py", "node", "mcp",
               "--name", "Developer", "--caps", "Code,Debug"]
    }
  }
}
```

OpenClaw（秘书 + 评审）— OpenClaw MCP 配置：

```json
{
  "mcpServers": {
    "nexus-secretary": {
      "command": "python",
      "args": ["/path/to/main.py", "node", "mcp",
               "--name", "Secretary", "--caps", "Planning,Coordination"]
    },
    "nexus-reviewer": {
      "command": "python",
      "args": ["/path/to/main.py", "node", "mcp",
               "--name", "Reviewer", "--caps", "Review,QA"]
    }
  }
}
```

#### 协作流程示例

```
人类在飞书 → "安排开发登录功能"
  │
  ▼ OpenClaw 秘书 Agent
  search_agents(keyword="Design") → 找到 Designer
  propose_task(to_did=Designer, title="设计登录功能方案")
  → task_id: "task_a1b2c3d4"

  ... 人类切换到 Kiro CLI ...
  │
  ▼ Kiro 设计 Agent
  fetch_inbox() → [{ message_type: "task_propose", task_id: "task_a1b2c3d4" }]
  claim_task(to_did=Secretary, task_id="task_a1b2c3d4", eta="2h")
  ... 完成设计 ...
  propose_task(to_did=Developer, title="实现登录功能")
  notify_state(to_did=Secretary, task_id="task_a1b2c3d4", status="completed")

  ... 人类切换到 Claude Code ...
  │
  ▼ Claude Code 开发 Agent
  fetch_inbox() → [{ message_type: "task_propose", ... }]
  claim_task(...) → 写代码 → notify_state(..., status="completed")
```

#### 实现位置

| 文件 | 修改内容 |
|------|---------|
| `agent_net/node/mcp_server.py` | 新增 10 个 Tool 定义 + call_tool case 分支 |
| `docs/mcp-setup.md` | 更新工具列表（17 → 27） |
| `docs/scenarios.md` | 新增跨平台组队场景 |
| `README.md` | Team 实战示例改为 MCP 配置 + 自然语言交互 |

不需要修改：Daemon / Router / Storage（已支持 message_type + protocol）。

## 理由

### 为什么定义为协议栈而不是功能列表

AgentNexus 的各模块（DID、握手、路由、消息、协作）不是独立功能，而是分层依赖的协议层。定义为协议栈后：
- 每一层的职责边界清晰（Daemon 管 L0-L5，SDK/MCP 管 L6-L7，适配器管 L8）
- 新功能可以明确归入某一层，避免职责混乱
- 外部开发者可以只实现部分层（比如只用 L0-L4 做基础通信，不用 L7 协作）

### 为什么融合三种模型而不是选一种

| 环节 | 如果只用 SIP | 如果只用 APNs | 如果只用 Matrix |
|------|------------|-------------|----------------|
| 注册报到 | ✅ 完美 | ❌ 无此概念 | △ 有但过重 |
| 离线消息 | ❌ SIP 假设在线 | ✅ 完美 | ✅ 完美 |
| 精准推送 | △ INVITE 太重 | ✅ 完美 | △ /sync 轮询 |
| 平台适配 | ❌ 无此概念 | ❌ 绑定 Apple/Google | ✅ AS 完美 |

三种模型各自解决不同环节的问题，融合后覆盖完整生命周期。

### 考虑的替代方案

1. **直接实现 Matrix 协议** — 完整但过重。Matrix 的 Room DAG、Megolm E2EE、state resolution 对 Agent 通信过度设计。AgentNexus 的优势是轻量（一个 SQLite + 一个 FastAPI）。
2. **只做 MCP 工具，不做推送** — v0.8 可行，但 v0.9+ 的自动化编排场景无法支撑。
3. **WebSocket 替代 SSE** — 双向通信能力更强，但 Agent 发消息走 HTTP POST 即可，只需要单向推送。SSE 实现更简单。
4. **在 send_message 上加 message_type 参数** — 让 AI 手动填枚举值，容易出错。独立工具语义更清晰。

## 影响范围

### v0.8（L7 协作层补全）

- **修改**：`agent_net/node/mcp_server.py` — 新增 10 个 Tool + call_tool 分支
- **修改**：`docs/mcp-setup.md`、`docs/scenarios.md`、`README.md`
- **修改**：`docs/architecture.md` — 架构图更新工具数量（12→27）、补充 Action Layer / Discussion / Adapters 层
- **新增**：`tests/test_mcp_collaboration.py` — 10 个工具的正常调用、必填参数缺失、start_discussion 多 participant 广播
- **不修改**：Daemon / Router / Storage

### v0.9（L3 注册层 + L5 推送层）

- **新增**：`agent_net/storage.py` — `push_registrations` 表 + CRUD
- **修改**：`agent_net/node/daemon.py` — `/push/*` 端点 + 投递后回调
- **修改**：`agent_net/router.py` — route_message 后触发推送
- **修改**：`agent_net/node/mcp_server.py` — 启动时自动注册 + 后台续约
- **修改**：`agentnexus-sdk/src/agentnexus/client.py` — connect() 自动注册

### v1.0（L5 SSE 增强）

- **新增**：`agent_net/node/daemon.py` — `/push/stream/{did}` SSE 端点
- **修改**：SDK client.py — SSE 自动连接 + 断线回退

## 相关 ADR

- ADR-001: DID 格式选择 — L0 身份层
- ADR-002: 四步握手协议 — L1 安全层
- ADR-005: Gatekeeper 三模式 — L2 访问层
- ADR-007: Action Layer 协作协议 — L6 消息层 + L7 协作层
- ADR-010: 平台适配器与 Skill 注册 — L8 适配层
- ADR-011: Discussion Protocol — L7 协作层

## 评审记录

| 日期 | 评审者 | 结果 | 备注 |
|------|--------|------|------|
| 2026-04-05 | 评审 Agent | 条件批准 | P1/P2 阻塞性问题需修复；P3/S1-S4 建议性问题后续迭代 |
| 2026-04-06 | 评审 Agent（锦衣卫指挥使 🦅） | 有条件通过 | 🔴 P4/P5 阻塞；🟡 S5-S8 建议；详见 §7.2 |
| 2026-04-05 | 评审 Agent | **批准** | P4 ✅ emergency_halt 改为独立 message_type；P5 ✅ 新增 callback_secret + HMAC 签名验证 |
| 2026-04-06 | 评审 Agent | **批准（第三轮）** | 重写为 ACP 协议栈后重新评审：(1) 影响范围补充 architecture.md ✅ (2) wip.md 补充 0.8-14~17 ✅ (3) §3 补充 SSRF 防护 + DID-Token 绑定 ✅ (4) emergency_halt 补充接收方识别约定 ✅ (5) 补充测试覆盖说明 ✅ |
| 2026-04-06 | 设计 Agent | **全部修复** | S5 命名约定 ✅ S6 L5描述修正 ✅ S7 PK已改 ✅ S8 SSE三要素 ✅ S1 日志已改 ✅ S3 返回值格式 ✅ C1 seq自动维护 ✅；S2/S4 延后处理 |
| 2026-04-07 | 设计 Agent（代码评审） | **通过** | v0.8 MCP 协作工具代码实现评审：10 个工具与 ADR-012 §6 设计高度一致，核心逻辑无问题。3 个建议性问题（详见 §7.3） |
| 2026-04-08 | 设计 Agent（代码复审） | **全部通过** | CP1-CP3 全部修复：日志 ✅ scenarios.md 场景 5 ✅ test_mcp_collaboration.py 10 tests passed ✅ |
| 2026-04-09 | 设计 Agent（v0.9 代码评审） | **有条件通过** | L3 注册层 + L5 推送层实现评审：设计一致性 ⭐⭐⭐⭐⭐，功能完整性 ⭐⭐⭐⭐。🔴 P1 DID-Token 绑定 TODO 未实现、P2 SSRF 防护 pass 空实现；🟡 S1 MCP 续约硬编码、S2 测试 10/10 ERROR。详见 §7.4 |
| 2026-04-09 | 设计 Agent（v0.9 复审） | **全部通过** | P1 DID-Token 绑定 ✅ P2 SSRF 防护 ✅ S1 expires//2 ✅ S2 测试 10/10 passed ✅ |

### 评审问题详情

#### 阻塞性问题

| # | 章节 | 问题描述 | 状态 |
|---|------|---------|------|
| P1 | §6 | `start_discussion` 的 `participants` 已包含所有参与者，但 `reply_discussion` / `vote_discussion` / `conclude_discussion` 的 `to_did` 应指向谁未明确。应指向讨论发起方（`discussion_start` 的 `from_did`），需在工具描述中补充说明 | ✅ 已修复 |
| P2 | §3 | `/push/register` 等端点"需 Bearer Token"，但 Token 来源未明确。应复用现有 Daemon Token 机制（`data/daemon_token.txt`） | ✅ 已修复 |

#### 建议性问题

| # | 章节 | 问题描述 | 状态 |
|---|------|---------|------|
| P3 | §6 | `emergency_halt` 工具缺少 `scope` 参数（ADR-011 §9 定义了 `all / task_{id} / did:...`） | ✅ 已修复（第二轮 P4） |
| S1 | §4 | 推送失败时静默（`except Exception: pass`），建议至少记录 warning 日志 | ✅ 已修复 |
| S2 | §3 | `expires_at` 使用 Unix timestamp，建议同时返回 ISO 格式便于调试 | 延后（v0.9 实现时处理） |
| S3 | §6 | 10 个新工具的返回值格式未定义，建议补充示例 | ✅ 已修复 |
| S4 | §5 | v0.8-17 "跨平台配置文档" 建议移到独立文档 | 延后（v0.8 实现时决定） |

#### 协议一致性问题

| # | 相关 ADR | 问题描述 | 状态 |
|---|---------|---------|------|
| C1 | ADR-011 §3 | 讨论消息的 `seq` 字段由谁生成未明确。建议：SDK/MCP 自动维护，调用方无需填写 | ✅ 已修复 |

### §7.2 第二次评审意见（2026-04-06）

#### 🔴 阻塞性问题（合并前必须修复）

| # | 章节 | 问题描述 | 建议 | 状态 |
|---|------|---------|------|------|
| P4 | §6-9 | `emergency_halt` 复用 `state_notify` message_type，但 `status: "emergency_halt"` 和 `scope: "all"` 均不在 ADR-007 定义的 `state_notify` content 结构中，且 scope=all 要求广播而 Relay 不支持广播路由 | 改为独立 message_type `emergency_halt`，content 结构单独定义；或在 ADR-007 中扩展 `state_notify` 的 content schema | ✅ 已修复 |
| P5 | §4 | L5 推送的 webhook 没有任何签名验证机制，POST body 可被任意伪造。APNs 有 device token 校验，SIP NOTIFY 有 SIP Auth，这里是裸奔 | 在 `push_registrations` 表加 `callback_secret` 字段，POST 时带 `X-Nexus-Signature: HMAC-SHA256(secret, body)` header | ✅ 已修复 |

#### 🟡 建议性问题

| # | 章节 | 问题描述 | 建议 | 状态 |
|---|------|---------|------|------|
| S5 | §6 | 命名不一致：工具名是 `reply_discussion`，但 §5 路线图表格里写的是 `discussion_reply`，ADR-011 里也是 `discussion_reply` | 统一为 `reply_discussion`（工具名）或 `discussion_reply`（message_type），二选一 | ✅ 已修复（补充命名约定：工具名=动词前缀，message_type=名词前缀） |
| S6 | §1 表格 | L5 标注"借鉴 APNs / FCM 的消息到达精准敲门 + 离线队列"，但实际设计只有 HTTP POST callback，没有独立离线队列。离线走的是 L4 现有机制，并非 APNs 离线推送机制 | 将"+ 离线队列"删除，或改为"借鉴 APNs 精准按 URI 推送理念，WebSocket/SSE 处理实时，在线 webhook 处理异步" | ✅ 已修复 |
| S7 | §3 | `push_registrations` 表 PRIMARY KEY 为 `(did, callback_url)`，导致同一 DID 同一 URL 只能注册一条。实际场景中 MCP 进程和 SDK 进程可能共用同一个 callback_url（如同一个本地 Daemon），会互相覆盖 | 改 PK 为 `registration_id`（UUID），`callback_url` 允许重复，用 `did + push_key` 做活跃注册查询 | ✅ 已修复（第二轮 P5 一并处理） |
| S8 | §5 | v1.0 SSE 端点 `/push/stream/{did}` 无任何定义：认证方式、重连策略、与 Webhook 的双模式切换逻辑均缺失 | 在 v1.0 规划中补充这三点定义 | ✅ 已修复 |

#### 评分

| 维度 | 评分 |
|------|------|
| 完整性 | ⭐⭐⭐⭐ |
| 层设计 | ⭐⭐⭐⭐⭐ |
| 可执行性 | ⭐⭐⭐ |
| 安全性 | ⭐⭐ |
| 与现有 ADR 的衔接 | ⭐⭐⭐⭐ |

### §7.3 代码评审（2026-04-07）

评审对象：`agent_net/node/mcp_server.py` v0.8 新增的 10 个协作工具实现。

#### ✅ 通过项

| # | 检查项 |
|---|--------|
| 1 | 10 个工具的 inputSchema（name、properties、required）与 ADR-012 §6 完全一致 |
| 2 | 所有协作工具设置 `message_type` + `protocol: "nexus_v1"`，与 ADR-007/011 一致 |
| 3 | 全部复用 `POST /messages/send`，不新增 Daemon 端点 |
| 4 | `_MY_DID` 自动填充 + 未绑定时返回明确错误信息 |
| 5 | `start_discussion` 循环广播 + 单个失败不阻塞 + 返回 `notified` 列表 |
| 6 | `emergency_halt` 使用独立 message_type，不复用 `state_notify` |
| 7 | `list_skills` 走 `GET /skills`，不走消息系统 |
| 8 | 返回值格式与 ADR-012 返回值格式表一致 |
| 9 | 工具名动词前缀 / message_type 名词前缀，符合命名约定 |
| 10 | `content` dict 经 Daemon `json.dumps()` 正确序列化为 str 存储 |
| 11 | `wip.md` 0.8-14~17 已标记完成 |
| 12 | `mcp-setup.md` 已更新（17→27 工具，中英文双语，分类清晰） |

#### 🟡 建议性问题

| # | 文件 | 问题 | 建议 |
|---|------|------|------|
| CP1 | `mcp_server.py` | `start_discussion` 广播失败时 `except Exception: pass` 无日志，调试困难 | 加 `logger.warning(f"Failed to notify {did}: {e}")` | ✅ 已修复 |
| CP2 | `docs/scenarios.md` | wip.md 0.8-17 标记完成且待同步 scenarios.md，但实际未新增跨平台组队场景 | 补充场景 5：OpenClaw + Kiro + Claude Code 跨平台 MCP 协作 | ✅ 已修复 |
| CP3 | `tests/` | ADR-012 影响范围要求 `tests/test_mcp_collaboration.py`，但未新增测试文件 | 参考 `test_mcp_bind.py` mock 模式，补充 10 个工具的测试覆盖 | ✅ 已修复（10 tests passed） |

### §7.4 v0.9 代码评审（2026-04-09）

评审对象：L3 注册层（ADR-012 §3）+ L5 推送层（ADR-012 §4）实现。

涉及文件：`agent_net/storage.py`、`agent_net/node/daemon.py`、`agent_net/router.py`、`agent_net/node/mcp_server.py`、`agentnexus-sdk/src/agentnexus/client.py`、`tests/test_push.py`

#### ✅ 通过项

| # | 检查项 | 文件 |
|---|--------|------|
| 1 | `push_registrations` 表结构与 §3 数据模型完全一致 | storage.py |
| 2 | Storage CRUD 完整（create/get_active/get_single/refresh/delete/cleanup） | storage.py |
| 3 | Daemon 4 个端点与 §3 一致（register/refresh/delete/status） | daemon.py |
| 4 | register/refresh/delete 需 Bearer Token，GET 公开 | daemon.py |
| 5 | `callback_secret` 仅注册时返回，GET 状态查询已过滤 | daemon.py |
| 6 | TTL 清理后台任务（每 5 分钟），lifespan 中启动 | daemon.py |
| 7 | 推送在 `route_message()` 离线存储后 `asyncio.create_task` 触发 | router.py |
| 8 | HMAC 签名：`X-Nexus-Signature: sha256=<HMAC>` + `X-Nexus-Timestamp`，与 §4 一致 | router.py |
| 9 | 推送超时 5s（`aiohttp.ClientTimeout(total=5)`） | router.py |
| 10 | 推送失败 `logger.warning`（HTTP ≥400 和 Exception） | router.py |
| 11 | MCP 启动自动注册 + finally 注销 + 后台续约 | mcp_server.py |
| 12 | SDK register_push / close 自动 unregister / 动态 expires//2 续约 | client.py |

#### 🔴 阻塞性问题

| # | 文件 | 问题 | 建议 |
|---|------|------|------|
| P1 | daemon.py:1135 | `# TODO: 验证 did 是否与 token 绑定的 DID 一致` — DID-Token 绑定未实现，任何持有 Daemon Token 的进程可为任意 DID 注册回调 | 短期：验证 `did` 是否为本节点已注册 Agent（`SELECT 1 FROM agents WHERE did=?`）；长期：per-DID token | ✅ 已修复（`_bind_token_to_did` + `_verify_token_did_binding`） |
| P2 | daemon.py:1142 | SSRF 防护 `pass` 空实现 — 外部 URL 不受限制 | 改为默认拒绝：`raise HTTPException(403, "External callback_url not allowed")`，配置机制就绪后再开放 | ✅ 已修复（严格模式 localhost-only + 白名单配置） |

#### 🟡 建议性问题

| # | 文件 | 问题 | 建议 |
|---|------|------|------|
| S1 | mcp_server.py:660 | 续约间隔硬编码 `1800`（30min），不随 expires 参数变化 | 改为 `expires // 2`，与 SDK 实现和 §3 注册模型一致 | ✅ 已修复 |
| S2 | tests/test_push.py | 10 个测试全部 ERROR（async fixture + pytest-asyncio strict mode 兼容性） | 修复 fixture 兼容性 | ✅ 已修复（10 passed） |

#### 评分

| 维度 | 评分 |
|------|------|
| 设计一致性 | ⭐⭐⭐⭐⭐ |
| 功能完整性 | ⭐⭐⭐⭐ |
| 安全性 | ⭐⭐ |
| 测试 | ⭐ |

## 答疑记录

| 日期 | 提问者 | 问题 | 回复 | 是否触发设计变更 |
|------|--------|------|------|----------------|
| | | | | |
