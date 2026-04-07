# ADR-006: SDK 架构与 Daemon 通信协议

## 状态

提议

## 日期

2026-04-04

## 背景

v0.7.x 完成了基础设施层（DID、握手、Relay、Gatekeeper、RuntimeVerifier），但开发者接入门槛高——需要理解 Daemon HTTP API、手动管理 Token、自行处理异步调用。v0.8.0 的核心目标是通过 Python SDK 将接入成本降到 3 行代码。

SDK 的定位是 Daemon HTTP API 的轻量客户端封装。根据 ADR-003 Sidecar 架构原则，SDK 不持有私钥、不直接操作存储，所有安全敏感操作委托给 Daemon。

关键设计问题：

1. **SDK 与 Daemon 的通信协议**：复用现有 HTTP API 还是引入新协议（WebSocket/gRPC）？
2. **认证机制**：SDK 如何获取和管理 Bearer Token？
3. **消息接收模型**：HTTP 是请求-响应模式，SDK 如何实现实时消息推送？
4. **连接生命周期**：SDK 如何处理 Daemon 重启、网络断开等异常？

## 决策

### 1. 通信协议：HTTP + 轮询（MVP），预留 WebSocket 升级路径

SDK 通过 HTTP 调用 Daemon 现有 API，消息接收采用轮询 `/messages/inbox/{did}`。

```
agentnexus-sdk (AgentNexusClient)
  │
  ├── send()        → POST /messages/send
  ├── verify()      → GET  /resolve/{did} + POST /runtime/verify
  ├── certify()     → POST /agents/{did}/certify
  ├── discover()    → GET  /agents/search/{keyword}
  └── _poll_loop()  → GET  /messages/inbox/{did}  (每 2 秒轮询)
```

理由：
- 复用 Daemon 现有全部端点，零改动即可支持 SDK
- HTTP 调试友好，curl 可直接测试
- 轮询间隔可配置（默认 2s），满足大多数场景
- v0.9+ 可新增 Daemon WebSocket 端点 `/ws/{did}`，SDK 自动升级

### 2. 认证机制：自动读取 Token 文件

```python
# Token 发现优先级：
# 1. 显式参数: connect(token="...")
# 2. 环境变量: AGENTNEXUS_TOKEN
# 3. 文件读取: ~/.agentnexus/daemon_token.txt（用户级，主路径）
# 4. 文件读取: ./data/daemon_token.txt（项目级，兼容本地开发）
```

Daemon 侧配套改动：启动时将 Token 同时写入项目目录 `data/daemon_token.txt`（现有行为）和用户目录 `~/.agentnexus/daemon_token.txt`（新增）。用户目录不存在时自动创建。

这样 SDK 通过 `pip install` 安装后，无论工作目录在哪，都能从 `~/.agentnexus/` 读到 Token。本地开发场景下项目目录的文件也继续可用。

SDK 在 `connect()` 时自动发现 Token，所有写请求附加 `Authorization: Bearer <token>`。读请求不需要 Token（与 Daemon 现有行为一致）。**Token 文件权限必须设为 `0600`（仅当前用户可读写）**，SDK 读取时检查权限，过宽则警告。

### 3. Daemon 自动发现

```python
# 发现优先级：
# 1. 显式参数: connect(daemon_url="http://...")
# 2. 环境变量: AGENTNEXUS_DAEMON_URL
# 3. 默认值: http://localhost:8765
#
# 发现流程：
# 1. GET /health → 成功则连接
# 2. 失败 → 抛出 DaemonNotFoundError，提示 "python main.py node start"
```

### 4. 连接生命周期

```
connect() → health check → register DID → start poll loop → ready
                                                              │
                                              on_message 回调 ←┘
                                                              │
close() ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ stop poll loop ←┘
```

- `connect()` 是幂等的：如果 DID 已注册，复用现有身份
- 轮询循环在后台 asyncio Task 中运行
- Daemon 不可达时，轮询自动退避（2s → 4s → 8s → 最大 30s），恢复后自动重连
- `close()` 停止轮询，释放 aiohttp session

### 5. 同步包装器

```python
# 异步（默认）
nexus = await agentnexus.connect("MyAgent")          # 注册新身份
nexus = await agentnexus.connect(did="did:agentnexus:z6Mk...")  # 复用已注册身份
await nexus.send(to_did, content)

# 同步（非异步场景）
nexus = agentnexus.sync.connect("MyAgent")
nexus.send(to_did, content)  # 内部 asyncio.run()
```

`connect(did=...)` 跳过注册步骤，直接 health check → start poll loop。若 DID 在 Daemon 中不存在则抛出 `DIDNotFoundError`。（Q2 答疑触发补充）

同步包装器在内部创建独立的 event loop，适用于脚本和非异步框架。

### 6. SDK 包结构

```
agentnexus-sdk/
├── pyproject.toml           # 依赖：aiohttp, pydantic
├── src/agentnexus/
│   ├── __init__.py          # 导出 connect()
│   ├── client.py            # AgentNexusClient（核心类）
│   ├── actions.py           # Action Layer（ADR-007）
│   ├── models.py            # Pydantic 数据模型
│   ├── discovery.py         # Daemon 发现 + Token 发现
│   ├── exceptions.py        # 异常层次
│   └── sync.py              # 同步包装器
├── examples/
└── tests/
```

最小依赖：`aiohttp`（HTTP 客户端）+ `pydantic`（数据校验）。不依赖 `pynacl`——密码学操作全部委托给 Daemon。

## 理由

### 为什么选 HTTP 轮询而不是 WebSocket

| 维度 | HTTP 轮询 | WebSocket |
|------|----------|-----------|
| Daemon 改动 | 零 | 需新增 WS 端点 + 连接管理 |
| 调试 | curl 可测 | 需专用工具 |
| 防火墙 | 无问题 | 部分企业网络拦截 |
| 实时性 | 2s 延迟（可接受） | 毫秒级 |
| 复杂度 | 低 | 中（心跳、重连、多路复用） |

v0.8 目标是降低门槛，不是追求毫秒级实时。轮询足够，且 Daemon 零改动。

### 为什么 SDK 不依赖 pynacl

ADR-003 确立了"私钥不出户"原则。SDK 如果依赖 pynacl，开发者可能误以为 SDK 在做签名——实际上所有签名都在 Daemon 内完成。不引入 pynacl 从依赖层面强化了这个架构约束。

### 考虑的替代方案

1. **gRPC** — 性能好，但引入 protobuf 编译步骤，增加开发者安装门槛，与"3 行代码接入"目标冲突。
2. **WebSocket（直接采用）** — 实时性好，但需要改 Daemon，增加 v0.8 范围。作为 v0.9 升级路径保留。
3. **SDK 内嵌 Daemon** — SDK 自带轻量 Daemon，零配置。但违反 Sidecar 原则，且多 SDK 实例会冲突。

## 影响范围

- 新增 `agentnexus-sdk/` 独立包（不修改 `agent_net/` 现有代码）
- `agent_net/node/daemon.py`：启动时新增 Token 写入 `~/.agentnexus/daemon_token.txt`（权限 0600）
- Daemon 现有 HTTP API 无需改动
- `~/.agentnexus/daemon_token.txt` 为 SDK 和 MCP 共用的用户级 Token 路径
- PyPI 发布 `agentnexus-sdk` 包

## 测试要求

| 测试场景 | 类型 | 说明 |
|---------|------|------|
| Daemon 未启动时 `DaemonNotFoundError` | 单元 | 验证错误提示包含启动命令 |
| Token 发现四条路径 | 单元 | 显式参数 > 环境变量 > 用户目录 > 项目目录 |
| Token 文件权限不是 0600 时警告 | 单元 | 提示"Token 文件权限过宽，建议 chmod 600" |
| Token 文件不存在时写请求失败 | 单元 | 读请求正常，写请求返回 401 |
| Daemon 重启后轮询自动恢复 | 集成 | 退避 → 重连 → 消息不丢 |
| 同步包装器在非异步环境正常工作 | 单元 | `agentnexus.sync.connect()` 功能验证 |

## 相关 ADR

- ADR-003: Sidecar 架构（SDK 遵循相同的 Daemon-客户端解耦原则）
- ADR-007: Action Layer 协作协议（SDK 的 actions.py 实现此协议）

## 评审记录

| 日期 | 评审者 | 结果 | 备注 |
|------|--------|------|------|
| 2026-04-04 | 评审 Agent | 条件批准 | 需补充 Token 权限检查测试用例 |

## 答疑记录

| 日期 | 提问者 | 问题 | 回复 | 是否触发设计变更 |
|------|--------|------|------|----------------|
| 2026-04-04 | 开发 Agent | Q1: 轮询退避到最大 30s 后，Daemon 恢复时如何快速检测？是等下一次轮询触发，还是 SDK 需要主动探测？ | 等下一次轮询触发即可。最坏 30s 延迟，MVP 可接受。轮询本身就是探测，无需额外机制。v0.9 WebSocket 升级后此问题自然消失。 | 否 |
| 2026-04-04 | 开发 Agent | Q2: 如果用户已有 DID，是否应该支持 `connect(did="did:agentnexus:z...")` 直接连接现有身份？ | 应该支持。`connect(name=...)` 注册新身份，`connect(did=...)` 复用已注册身份（跳过注册，直接 health check + start poll）。 | **是** — 需在 SDK API 章节补充 `connect(did=...)` 签名 |
| 2026-04-04 | 开发 Agent | Q3: `certify()` 方法需要签名操作，是调用 Daemon 的 `/agents/{did}/certify` 端点吗？该端点目前是否存在？ | 是，调用 `POST /agents/{did}/certify`，该端点 v0.7.x 已存在（CA 认证请求），SDK 只是封装调用。 | 否 |
