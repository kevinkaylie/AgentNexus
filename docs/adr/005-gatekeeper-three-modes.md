# ADR-005: Gatekeeper 三模式设计

## 状态

已采纳

## 日期

2025-03-22

## 背景

AgentNexus 的 Agent 节点需要控制哪些外部 Agent 可以与自己建立连接。在开放的去中心化网络中，任何持有有效 DID 的 Agent 都可以尝试发起握手请求。如果没有访问控制机制，节点将面临以下风险：

1. **垃圾连接**：恶意 Agent 大量发起无意义的握手请求，消耗资源。
2. **隐私泄露**：不希望被发现的 Agent 可能被未授权方连接。
3. **安全威胁**：未经验证的 Agent 可能尝试利用协议漏洞。

不同使用场景对访问控制的需求不同：公开服务需要开放接入，企业内部节点需要严格控制，个人节点需要审批机制。

## 决策

实现三模式语义门禁（Gatekeeper），在握手协议之前执行访问控制：

| 模式 | 行为 | 类比 |
|------|------|------|
| **public（开放）** | 任何 DID 验证通过即可建联，黑名单仍生效 | 微信"所有人可加我" |
| **ask（审批）** | 未知 DID 进入 PENDING 队列，等待审批 | 微信"需要验证" |
| **private（白名单）** | 仅白名单中的 DID 可接入 | 微信"不让任何人加我" |

核心规则：
- **黑名单优先级最高**：无论处于哪种模式，黑名单中的 DID 一律拒绝，即使在 public 模式下也不例外。
- **配置热加载**：白名单（`data/whitelist.json`）、黑名单（`data/blacklist.json`）、模式（`data/mode.json`）支持运行时修改，无需重启 Daemon。
- **PENDING 队列**：ask 模式下，未知 DID 的握手请求存入 SQLite `pending_requests` 表，通过 `asyncio.Future` 挂起协程，等待审批结果。
- **前置执行**：Gatekeeper 在握手协议步骤 ① 之后、步骤 ② 之前执行，先检查访问权限再发送 challenge。

推荐生产环境使用 `ask` 模式，配合 AI 自动审批策略：
- 名片含 `official/verified/partner` 标签 + `updated_at` 新鲜 → 自动批准
- 描述含 `spam/ad/promotion` → 自动拒绝
- 意图模糊 → 上报主人等待决策

## 理由

三模式设计覆盖了从完全开放到完全封闭的所有访问控制需求：

- **灵活性**：三种模式对应三种典型使用场景（公开服务、个人节点、企业内部），用户可根据需求切换。
- **黑名单优先**：确保已知恶意 DID 在任何模式下都无法接入，提供最基本的安全保障。
- **异步审批**：ask 模式下的 PENDING 队列使用 `asyncio.Future` 实现非阻塞等待，不影响其他连接的处理。
- **热加载**：配置文件修改即时生效，运维人员可以在不中断服务的情况下调整访问策略。
- **AI 友好**：ask 模式天然适合 AI 自动审批，可以基于 NexusProfile 名片内容做智能决策。

### 考虑的替代方案

1. **仅白名单模式** — 最安全，但对公开服务场景不友好，每个新连接都需要手动添加白名单。
2. **基于 IP 的访问控制** — 传统方案，但在去中心化网络中 Agent 的 IP 地址不固定，且无法与 DID 身份关联。
3. **基于信任分的自动决策** — 结合 RuntimeVerifier 的信任级别自动放行/拒绝，更智能但实现复杂，且信任分计算依赖外部认证，冷启动时无法工作。
4. **无访问控制（全开放）** — 最简单，但在生产环境中不可接受，无法防御恶意连接。

## 影响范围

- `agent_net/node/gatekeeper.py`：`Gatekeeper` 类，三模式逻辑、黑白名单管理、PENDING 队列
- `agent_net/node/daemon.py`：`POST /handshake/init` 中集成 Gatekeeper 检查点；`/gate/pending`、`/gate/resolve`、`/gate/whitelist`、`/gate/blacklist`、`/gate/mode` 管理接口
- `agent_net/storage.py`：`pending_requests` 表，`add_pending()`、`list_pending()`、`resolve_pending()` 方法
- `data/whitelist.json`、`data/blacklist.json`、`data/mode.json`：配置文件，支持热加载

## 相关 ADR

- ADR-002: 四步握手协议设计（Gatekeeper 在握手步骤 ① 之后前置执行）
- ADR-003: Sidecar 架构（Gatekeeper 在 Daemon 内运行，MCP 通过 HTTP 管理接口操作）
- ADR-004: 多 CA 认证架构（ask 模式的 AI 自动审批可结合认证信息做决策）
