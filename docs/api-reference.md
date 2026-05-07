# API Reference | API 参考

> **状态说明**：本文档反映当前已实现的接口。鉴权矩阵 v3 已落地 v1.0 阶段性边界（token + actor DID 校验、读接口私有化、/deliver soft-enforce 签名验证）；per-agent token、hard-enforce `/deliver`、Strict JCS 属于 v1.5 安全收紧范围。已设计但未实现的变更跟踪见 `docs/wip.md`。

**[中文](#-中文) | [English](#-english)**

---

## 🇨🇳 中文

### Relay Server API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/announce` | POST | 注册/心跳（TTL=120s，需 Ed25519 签名 + TOFU） |
| `/lookup/{did}` | GET | DID 查询（本地 + 1 跳联邦代理） |
| `/resolve/{did}` | GET | W3C DID Resolution（返回 DID Document + service 数组） |
| `/agents` | GET | 列出本地注册 Agent |
| `/relay` | POST | 消息中转 |
| `/federation/join` | POST | Relay 加入联邦（回调验证） |
| `/federation/announce` | POST | 公告公开 Agent 到 PeerDirectory（需签名 NexusProfile） |
| `/federation/peers` | GET | 列出已知 peer relay |
| `/federation/directory` | GET | 列出 PeerDirectory 条目 |
| `/health` | GET | 健康检查（含联邦统计） |

### Node Daemon API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/agents/register` | POST | 注册 Agent（需 Token，默认 did:agentnexus 格式） |
| `/agents/local` | GET | 列出本地 Agent |
| `/agents/search/{keyword}` | GET | 按能力搜索 Agent |
| `/agents/{did}` | GET | 获取 Agent 详情 |
| `/agents/{did}/profile` | GET | 获取签名 NexusProfile（含 certifications） |
| `/agents/{did}/card` | PATCH | 更新名片字段并重签（需 Token，body 必须含 `actor_did`） |
| `/agents/{did}/certify` | POST | 为 Agent 签发认证（需 Token） |
| `/agents/{did}/certifications` | GET | 获取 Agent 的所有认证 |
| `/agents/{did}/export` | GET | 导出 Agent 身份包（加密，需 Token + ?password=） |
| `/agents/import` | POST | 导入 Agent 身份包（解密恢复，需 Token） |
| `/resolve/{did}` | GET | W3C DID Resolution（本地优先，回落到 relay） |
| `/messages/send` | POST | 发送消息（需 Token；`from_did` 即 actor；支持 `session_id`、`reply_to`、`message_id`） |
| `/messages/inbox/{did}` | GET | 获取未读消息（需 Token + `actor_did`） |
| `/messages/all/{did}` | GET | 获取完整消息列表（需 Token + `actor_did`） |
| `/messages/session/{session_id}` | GET | 按会话 ID 查询完整对话历史（需 Token + `actor_did`） |
| `/owner/messages/inbox` | GET | Owner 聚合未读消息（需 Token + `owner_did` + `actor_did`） |
| `/owner/messages/all` | GET | Owner 聚合完整消息（需 Token + `owner_did` + `actor_did`） |
| `/owner/messages/stats` | GET | Owner 消息统计（需 Token + `owner_did` + `actor_did`） |
| `/deliver` | POST | Worker 结果回传（v1.0 soft-enforce 签名；签名缺失记录 warning） |
| `/contacts/add` | POST | 添加通讯录（需 Token） |
| `/stun/endpoint` | GET | 获取公网 IP:Port |
| `/gate/pending` | GET | 查看待审批请求 |
| `/gate/resolve` | POST | 审批请求（需 Token） |
| `/gate/mode` | GET/POST | 获取/设置访问控制模式 |
| `/node/config/*` | GET/POST | Relay 配置管理 |
| `/skills` | GET | 查询注册的 Skills（?agent_did=&capability=） |
| `/push/register` | POST | 注册 Push 唤醒方式（需 Token）⚡ *v0.9* |
| `/push/refresh` | POST | 续约 Push 注册 TTL（需 Token）⚡ *v0.9* |
| `/push/{did}` | DELETE | 主动注销 Push 注册（需 Token）⚡ *v0.9* |
| `/push/{did}` | GET | 查询 Push 注册状态（公开，不返回 secret）⚡ *v0.9* |
| `/owner/register` | POST | 注册 Owner DID（需 Token） |
| `/owner/bind` | POST | 绑定子 Agent 到 Owner（需 Token） |
| `/owner/unbind` | DELETE | 解除子 Agent 绑定（需 Token + `actor_did`） |
| `/owner/agents/{owner_did}` | GET | 列出 Owner 下属 Agent（需 Token + `actor_did`） |
| `/owner/profile/{owner_did}` | GET | 获取 Owner profile（需 Token + `actor_did`） |
| `/owner/workers/{owner_did}` | GET | Worker Registry v1（需 Token + `actor_did`） |
| `/owner/workers/v2/{owner_did}` | GET | Worker Registry v2 + presence/load/filter（需 Token + `actor_did`） |
| `/workers/{did}/presence` | GET | 查询 Worker presence（需 Token + `actor_did`） |
| `/workers/{did}/blocked` | PATCH | 设置 Worker blocked 状态（需 Token + `actor_did`） |
| `/agents/{did}/worker-type` | PATCH | 设置 Worker 类型（需 Token + `actor_did`） |
| `/secretary/intake` | POST | 创建秘书 intake（需 Token，`actor_did` 必须是 Secretary） |
| `/secretary/intake/{session_id}` | GET | 查询 intake（需 Token + `actor_did`） |
| `/secretary/intakes/{owner_did}` | GET | 列出 Owner intake（需 Token + `actor_did`） |
| `/secretary/dispatch` | POST | 秘书/绑定 Agent dispatch，创建 Enclave + Playbook Run（需 Token） |
| `/secretary/intake/{session_id}/confirm` | POST | Owner 确认 intake 并触发 dispatch（需 Token） |
| `/secretary/intake/{session_id}/abort` | POST | Owner abort 接管（需 Token） |
| `/adapters/{platform}/invoke` | POST | Adapter Contract 统一入口（OpenClaw/Webhook/SDK/CLI intake） |
| `/adapters/{platform}/register` | POST | 注册平台 Adapter（需 Token） |
| `/enclaves` | POST/GET | 创建/查询 Enclave（需 Token + `actor_did`；创建 body 含 `owner_did`） |
| `/enclaves/{enclave_id}` | GET/PATCH/DELETE | Enclave 详情、更新、归档（需 Token + `actor_did`） |
| `/enclaves/{enclave_id}/members` | POST | 添加成员（需 Token + owner `actor_did`） |
| `/enclaves/{enclave_id}/members/{did}` | PATCH/DELETE | 更新/移除成员（需 Token + owner `actor_did`） |
| `/enclaves/{enclave_id}/vault` | GET | 列出 Vault（需 Token + member `actor_did`） |
| `/enclaves/{enclave_id}/vault/{key}` | GET/PUT/DELETE | 读写 Vault key（需 Token + member `actor_did` / `author_did`） |
| `/enclaves/{enclave_id}/runs` | POST/GET | 创建或查询 Playbook Run（需 Token + member `actor_did`） |
| `/enclaves/{enclave_id}/runs/{run_id}` | GET | 查询 Playbook Run 状态与 StageExecution（需 Token + member `actor_did`） |
| `/capability-tokens/issue` | POST | 签发 Capability Token（需 Token） |
| `/capability-tokens/{token_id}` | GET | 查询 Capability Token（需 Token） |
| `/capability-tokens/{token_id}/verify` | POST | 验证 Capability Token（需 Token） |
| `/capability-tokens/{token_id}/revoke` | POST | 撤销 Capability Token（需 Token） |
| `/capability-tokens/by-did/{did}` | GET | 查询 DID 相关 Capability Token（需 Token） |
| `/health` | GET | 健康检查 |

### 密码学实现

| 用途 | 算法 |
|------|------|
| DID 生成 | Ed25519 非对称密钥对（pynacl） |
| NexusProfile 签名 | Ed25519（RawEncoder），canonical JSON |
| 握手身份验证 | Ed25519 Challenge-Response |
| 密钥协商 | X25519 ECDH |
| 消息加密 | AES-256-GCM（nonce 12B） |
| 私钥持久化 | SQLite agents 表（hex 存储），签名不出 Daemon |
| Challenge TTL | 30 秒 |
| 写接口鉴权 | secrets.token_hex(32)，存于 data/daemon_token.txt |
| Relay 签名验证 | Ed25519 签名 + TOFU 公钥绑定 + 时间戳防重放（60s） |
| 速率限制 | 30 req/min per DID（内存计数器） |

### 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 异步运行时 | Python asyncio |
| 本地存储 | aiosqlite（SQLite） |
| HTTP 客户端 | aiohttp |
| 密码学 | pynacl + cryptography |
| MCP 协议 | mcp >= 1.0.0 |
| Python 版本 | 3.10+ |

### 数据库结构

| 表名 | 说明 |
|------|------|
| `agents` | DID、Profile、is_local、last_seen、private_key_hex、owner_did、worker_type |
| `messages` | 离线消息，`delivered=1` 防重复投递，`session_id`、`reply_to`、`message_id`、`run_id`、`stage_name` |
| `contacts` | 远程 Agent 通讯录（endpoint/relay） |
| `pending_requests` | Gatekeeper PENDING 状态握手请求 |
| `owners` | Owner DID 与 profile |
| `secretary_intakes` | 秘书 intake、dispatch、selected_workers、run_id 状态 |
| `enclaves` / `enclave_members` | 项目组及成员权限 |
| `enclave_vault` / `enclave_vault_history` | Vault 当前值和历史版本 |
| `playbooks` / `playbook_runs` / `stage_executions` | Playbook、Run、阶段执行、manifest/checkpoint/context budget |
| `capability_tokens` | Capability Token、委托链、撤销状态 |

### NexusProfile 名片结构

```json
{
  "header": {
    "did": "did:agent:a1b2c3d4e5f60001",
    "pubkey": "ed25519_pub_key_hex",
    "version": "1.0"
  },
  "content": {
    "schema_version": "1.0",
    "name": "TranslateBot",
    "description": "多语言翻译服务，支持中英日韩等50种语言",
    "tags": ["translate", "multilingual", "official"],
    "endpoints": {
      "relay": "http://your-relay.com:9000",
      "direct": null
    },
    "updated_at": 1700000000.0
  },
  "signature": "<Ed25519 签名，覆盖 canonical JSON(content)>"
}
```

- **签名在 Daemon 内完成**，私钥永不离开本地进程
- `schema_version` 和 `updated_at` 包含在签名内，防止篡改和重放攻击
- 任何人持有名片即可离线验签

### Relay Redis Key Schema

| Key 模式 | 类型 | TTL | 说明 |
|----------|------|-----|------|
| `relay:reg:{did}` | JSON | 120s | announce/heartbeat 注册信息 |
| `relay:peers` | SET | 无 | peer relay URL 集合 |
| `relay:peerdir:{did}` | JSON | 无 | 公开 Agent 目录条目 |
| `relay:pk:{did}` | string | 无 | Ed25519 公钥 hex（TOFU 绑定） |

---

## 🇬🇧 English

### Relay Server API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/announce` | POST | Register/heartbeat (TTL=120s, requires Ed25519 signature + TOFU) |
| `/lookup/{did}` | GET | DID lookup (local + 1-hop federation proxy) |
| `/resolve/{did}` | GET | W3C DID Resolution (returns DID Document + service array) |
| `/agents` | GET | List locally registered agents |
| `/relay` | POST | Message relay |
| `/federation/join` | POST | Relay joins federation (callback verification) |
| `/federation/announce` | POST | Announce public agent to PeerDirectory (requires signed NexusProfile) |
| `/federation/peers` | GET | List known peer relays |
| `/federation/directory` | GET | List PeerDirectory entries |
| `/health` | GET | Health check (includes federation stats) |

### Node Daemon API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agents/register` | POST | Register an Agent (Token required; default DID method is `did:agentnexus`) |
| `/agents/local` | GET | List local Agents |
| `/agents/{did}/card` | PATCH | Update and re-sign profile card (Token + body `actor_did`) |
| `/messages/send` | POST | Send message (Token required; `from_did` is the actor; supports `session_id`, `reply_to`, `message_id`) |
| `/messages/inbox/{did}` | GET | Fetch inbox (Token + `actor_did`) |
| `/owner/register` | POST | Register Owner DID (Token required) |
| `/owner/bind` | POST | Bind child Agent to Owner (Token required) |
| `/owner/workers/v2/{owner_did}` | GET | Worker Registry with presence/load/filter (Token + `actor_did`) |
| `/workers/{did}/presence` | GET | Query Worker presence (Token + `actor_did`) |
| `/secretary/intake` | POST | Create Secretary intake (Token; `actor_did` must be Secretary) |
| `/secretary/dispatch` | POST | Dispatch task and create Enclave + Playbook Run (Token required) |
| `/secretary/intake/{session_id}/abort` | POST | Owner abort takeover (Token required) |
| `/adapters/{platform}/invoke` | POST | Unified Adapter Contract intake for OpenClaw/Webhook/SDK/CLI |
| `/enclaves` | POST/GET | Create/list Enclaves (Token + `actor_did`) |
| `/enclaves/{enclave_id}/vault/{key}` | GET/PUT/DELETE | Vault read/write/delete (Token + member actor) |
| `/enclaves/{enclave_id}/runs` | POST/GET | Create/query Playbook Runs (Token + member actor) |
| `/capability-tokens/issue` | POST | Issue Capability Token (Token required) |
| `/capability-tokens/{token_id}/verify` | POST | Verify Capability Token (Token required) |

### Cryptography

| Purpose | Algorithm |
|---------|-----------|
| DID generation | Ed25519 key pair (pynacl) |
| NexusProfile signing | Ed25519 (RawEncoder), canonical JSON |
| Handshake auth | Ed25519 Challenge-Response |
| Key agreement | X25519 ECDH |
| Message encryption | AES-256-GCM (12B nonce) |
| Key persistence | SQLite hex storage — signing never leaves Daemon |
| Challenge TTL | 30 seconds |
| Write auth | secrets.token_hex(32) in data/daemon_token.txt |
| Relay signature | Ed25519 signed announce + TOFU pubkey binding + timestamp replay protection (60s) |
| Rate limiting | 30 req/min per DID (in-memory counter) |

### Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI + Uvicorn |
| Async runtime | Python asyncio |
| Storage | aiosqlite (SQLite) |
| HTTP client | aiohttp |
| Cryptography | pynacl + cryptography |
| MCP protocol | mcp >= 1.0.0 |
| Python | 3.10+ |

### Database Schema

| Table | Description |
|-------|-------------|
| `agents` | DID, Profile, is_local, last_seen, private_key_hex, owner_did, worker_type |
| `messages` | Offline messages with `session_id`, `reply_to`, `message_id`, `run_id`, `stage_name` |
| `contacts` | Remote Agent contacts (endpoint/relay) |
| `pending_requests` | Gatekeeper PENDING handshake requests |
| `owners` | Owner DID and profile |
| `secretary_intakes` | Secretary intake, dispatch, selected_workers, run_id status |
| `enclaves` / `enclave_members` | Team workspace and member permissions |
| `enclave_vault` / `enclave_vault_history` | Vault current values and version history |
| `playbooks` / `playbook_runs` / `stage_executions` | Playbooks, runs, stage execution, manifests/checkpoints/context budget |
| `capability_tokens` | Capability tokens, delegation chain and revocation state |

### NexusProfile Card Structure

```json
{
  "header": {
    "did": "did:agent:a1b2c3d4e5f60001",
    "pubkey": "ed25519_pub_key_hex",
    "version": "1.0"
  },
  "content": {
    "schema_version": "1.0",
    "name": "TranslateBot",
    "description": "Multilingual translation, 50 languages",
    "tags": ["translate", "multilingual", "official"],
    "endpoints": {
      "relay": "http://your-relay.com:9000",
      "direct": null
    },
    "updated_at": 1700000000.0
  },
  "signature": "<Ed25519 signature over canonical JSON(content)>"
}
```

- **Signing happens inside Daemon** — private key never leaves the local process
- `schema_version` and `updated_at` are included in the signature, preventing tampering and replay attacks
- Anyone holding the card can verify the signature offline

### Relay Redis Key Schema

| Key Pattern | Type | TTL | Description |
|-------------|------|-----|-------------|
| `relay:reg:{did}` | JSON | 120s | announce/heartbeat registration |
| `relay:peers` | SET | none | peer relay URL set |
| `relay:peerdir:{did}` | JSON | none | public agent directory entry |
| `relay:pk:{did}` | string | none | Ed25519 pubkey hex (TOFU binding) |
