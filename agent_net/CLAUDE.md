# agent_net - CLAUDE.md

## 模块职责
AgentNexus核心包，按职责分为四个子包。

## 目录结构

```
agent_net/
├── common/           # 共享基础组件（node/relay均可导入）
│   ├── did.py        # DID生成、AgentProfile、DIDResolver（注册表路由）
│   ├── did_methods/  # DID Method Handlers（ADR-009）
│   │   ├── base.py       # DIDMethodHandler 抽象基类
│   │   ├── utils.py      # build_did_document 等工具函数
│   │   ├── agentnexus.py # did:agentnexus handler
│   │   ├── agent_legacy.py # did:agent handler（仅 Daemon）
│   │   ├── key.py        # did:key handler
│   │   ├── web.py        # did:web handler
│   │   └── meeet.py      # did:meeet handler（仅 Relay）
│   ├── handshake.py  # Ed25519签名 + X25519 ECDH + AES-256-GCM
│   ├── crypto.py     # Base58BTC、multikey Ed25519/X25519
│   ├── profile.py    # NexusProfile sign/verify
│   ├── keystore.py   # export/import（argon2id+SecretBox）
│   └── runtime_verifier.py  # L1-L4 信任体系
├── node/             # 本地节点
│   ├── daemon.py     # FastAPI HTTP服务 :8765
│   ├── mcp_server.py # MCP stdio服务
│   └── gatekeeper.py # 访问控制网关
├── relay/
│   └── server.py     # 公网信令+中转服务器 :9000 + MEEET桥接
├── identity.py       # 向后兼容重导出（→ common/did）
├── auth/handshake.py # 向后兼容重导出（→ common/handshake）
├── storage.py        # SQLite CRUD
├── router.py         # 消息路由（支持 Action Layer）
└── stun.py           # UDP STUN探测
```

## common/did.py
- `DIDGenerator.create_new(name)` → `AgentDID(did, private_key, verify_key)`
- `DIDGenerator.create_agentnexus(name)` → `(AgentDID, verify_key_bytes)` — W3C multikey 格式
- `DIDResolver` 注册表路由模式（ADR-009）：
  - 通过 `register(handler)` 注册 DID 方法处理器
  - `register_daemon_handlers(db_path)` — Daemon 侧注册
  - `register_relay_handlers(redis_client)` — Relay 侧注册
  - `reset_handlers()` — 测试隔离
- `AgentProfile` dataclass，`to_json_ld()` 输出JSON-LD格式名片

## common/did_methods/（ADR-009）
- `DIDMethodHandler` 抽象基类：`method` 属性 + `resolve()` 方法
- 各 Handler 实现：
  - `AgentNexusHandler` — 纯密码学解析，无依赖
  - `AgentLegacyHandler` — 需要 `db_path`，仅 Daemon 注册
  - `KeyHandler` — 纯密码学解析
  - `WebHandler` — HTTPS 端点获取
  - `MeeetHandler` — 需要 `redis_client`，仅 Relay 注册
- 工具函数：`build_did_document()`、`extract_ed25519_key_from_doc()`

## common/handshake.py
- 四步握手：`create_init_packet` → `process_init` → `process_challenge` → `verify_response`
- `SessionKey` 提供 `encrypt()/decrypt()`，格式 `nonce(12B) + ciphertext`
- Challenge TTL = 30s，过期抛 `ValueError`

## storage.py
- DB路径：`data/agent_net.db`（运行时自动创建）
- 四张表：`agents` / `messages` / `contacts` / `pending_requests`
- `pending_requests`：存储 Gatekeeper PENDING 状态的握手请求
  - `add_pending(did, init_packet)` / `list_pending()` / `resolve_pending(did, action)`
- 消息投递后 `delivered=1`，`fetch_inbox` 不重复返回
- messages 表字段（v0.8）：
  - 基础：`id`, `from_did`, `to_did`, `content`, `timestamp`, `delivered`
  - 扩展：`session_id`, `reply_to`, `message_type`, `protocol`

## router.py
- `Router` 类维护 `_local_sessions: dict[did, asyncio.Queue]`
- `route_message()` 按优先级：local → p2p → relay → offline存储
- 支持 Action Layer 参数：`message_type` / `protocol`
- 全局单例 `router = Router()` 供 daemon 导入使用

## stun.py
- 依次尝试 Google STUN、Cloudflare STUN，首个成功即返回
- 纯UDP实现，无第三方依赖

## node/daemon.py
- 监听 `0.0.0.0:8765`，启动时调用 `init_db()` + `get_public_endpoint()` + `_init_daemon_token()`
- Token 鉴权（v0.8 双路径写入）：
  - 项目目录：`data/daemon_token.txt`
  - 用户目录：`~/.agentnexus/daemon_token.txt`（SDK 全局使用）
  - 权限：`0600`
- `/messages/send` 支持 Action Layer：`content: Union[str, dict]`，新增 `message_type` / `protocol` 参数
- `/messages/inbox/{did}` 返回消息包含 `message_type` / `protocol` 字段
- NexusProfile 签名在 daemon 内完成（`GET /agents/{did}/profile`，`PATCH /agents/{did}/card`），私钥不出户
- 握手入口 `POST /handshake/init` 内置 Gatekeeper 检查点
- Gatekeeper 管理接口：`/gate/pending`、`/gate/resolve`、`/gate/whitelist`、`/gate/blacklist`、`/gate/mode`
- Relay 配置接口：`/node/config/*`（local-relay/relay/add/remove）
- RuntimeVerifier：`POST /runtime/verify`

## node/gatekeeper.py
- 三种模式：`public`（全放行）/ `private`（仅白名单）/ `ask`（未知DID进PENDING队列）
- 黑名单优先级高于一切，即使 public 模式也拒绝
- 配置文件：`data/whitelist.json`、`data/blacklist.json`、`data/mode.json`，热加载
- `resolve(did, action)` 更新SQLite并通过 `asyncio.Future` 唤醒挂起的握手协程
- 全局单例 `gatekeeper = Gatekeeper()`

## node/mcp_server.py
- stdio模式，所有工具调用转发至 Daemon HTTP API
- `_MY_DID`：模块级，`os.environ.get("AGENTNEXUS_MY_DID", "")` 读入，由 `node mcp --name/--did` 注入
- `_read_token()` 从 `data/daemon_token.txt` 或 `~/.agentnexus/daemon_token.txt` 读取 Token
- `_call()` 对写方法（post/patch/put/delete）自动附加 `Authorization: Bearer <token>` 头
- 工具列表（17个）：`whoami`, `register_agent`, `list_local_agents`, `send_message`, `fetch_inbox`,
  `search_agents`, `add_contact`, `get_stun_endpoint`,
  `get_pending_requests`, `resolve_request`, `get_card`, `update_card`,
  `export_agent`, `import_agent`, `get_agent`, `delete_agent`, `list_contacts`
- 绑定后可省略参数：`send_message.from_did`、`fetch_inbox.did`、`get_card.did`、`update_card.did`

## relay/server.py
- 监听 `0.0.0.0:9000`，注册表存于 Redis，TTL=120s
- 核心接口：`POST /announce` / `GET /lookup/{did}` / `POST /relay`（中转转发）/ `GET /health`
- did:web 身份：`GET /.well-known/did.json` — Relay 自身 DID Document
- DID Resolution：`GET /resolve/{did}` — 支持 `did:agentnexus` / `did:agent` / `did:meeet`
- 联邦：`POST /federation/join` / `POST /federation/announce`
- ANPN：`POST /relay/anpn-register` / `GET /relay/anpn-lookup/{did}/{protocol}` / `GET /relay/anpn-discover/{did}`

### MEEET 桥接端点（v0.8）
- `POST /meeet/admin/register` — 注册平台管理员密钥（需 Relay identity key 签名）
- `GET /meeet/admin/status` — 查询已注册管理员列表
- `POST /meeet/register` — 单个 MEEET Agent 注册（Agent 自签名）
- `POST /meeet/batch-register` — 批量注册（需管理员签名 + 每条 Agent 签名，最大 100 条）
- `GET /meeet/status` — 映射状态统计
- Redis 键空间：
  - `meeet:admins` — 管理员公钥集合
  - `meeet:mapping:{did:meeet:...}` — Agent 映射数据（TTL 24h）
- x402 score 映射公式：`min(100, 10 + (reputation / 850) * 82)`

## agentnexus-sdk/（v0.8 新增）

独立 Python 包，位于 `agentnexus-sdk/`，PyPI 发布准备。

### 包结构
```
agentnexus-sdk/
├── pyproject.toml
├── src/agentnexus/
│   ├── __init__.py      # 导出 connect() 和核心类
│   ├── client.py        # AgentNexusClient
│   ├── actions.py       # Action Layer（四种协作动作）
│   ├── models.py        # Message, VerificationResult, Certification
│   ├── discovery.py     # Daemon/Token 自动发现
│   ├── exceptions.py    # 异常层次
│   └── sync.py          # 同步包装器
├── examples/
└── tests/
```

### 核心 API
```python
import agentnexus

# 注册新身份
nexus = await agentnexus.connect("MyAgent", caps=["Chat", "Search"])

# 或复用已注册身份
nexus = await agentnexus.connect(did="did:agentnexus:z6Mk...")

# 发送消息
await nexus.send(to_did="...", content="Hello!")

# Action Layer
task_id = await nexus.propose_task(to_did="...", title="实现登录模块")
await nexus.claim_task(to_did="...", task_id=task_id)
await nexus.sync_resource(to_did="...", key="config", value={...})
await nexus.notify_state(to_did="...", status="completed")

# 接收消息
@nexus.on_message
async def handle(msg):
    print(f"From {msg.from_did}: {msg.content}")

# 信任查询
result = await nexus.verify("did:agentnexus:...")
```

### 同步包装器
```python
import agentnexus.sync

nexus = agentnexus.sync.connect("MyAgent")
nexus.send(to_did="...", content="Hello!")
nexus.close()
```
