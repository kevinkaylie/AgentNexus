# ADR-003: Sidecar 架构（Daemon-MCP 解耦）

## 状态

已采纳

## 日期

2025-03-22

## 背景

AgentNexus 需要同时支持 AI 模型（通过 MCP 协议）和本地服务（通过 HTTP API）的接入。核心挑战在于：

1. **私钥安全**：Agent 的 Ed25519 私钥用于签名 NexusProfile、握手协议和 Relay 通告，必须严格保护，不能暴露给外部进程。
2. **MCP 协议限制**：MCP 使用 stdio 通信，运行在 AI 模型的进程空间中，不应直接访问数据库或持有私钥。
3. **多客户端支持**：同一台机器上可能有多个 MCP 客户端（不同 AI 模型）连接到同一个 Agent 节点。
4. **异步 I/O**：网络通信、数据库操作和握手协议都是 I/O 密集型操作，需要非阻塞执行。

需要一种架构将安全敏感操作与外部接口隔离，同时保持系统的可扩展性。

## 决策

采用 Sidecar 架构，将系统分为两个独立进程：

1. **Node Daemon（:8765）**：FastAPI HTTP 服务，负责所有安全敏感操作。
   - 持有所有 Agent 的私钥，签名操作只在此进程内完成。
   - 管理 SQLite 数据库（agents、messages、contacts、pending_requests）。
   - 运行 Gatekeeper 访问控制、握手协议、消息路由。
   - 启动时生成 Bearer Token（`data/daemon_token.txt`），所有写端点需要 Token 鉴权。

2. **MCP Server（stdio）**：轻量级代理层，通过 HTTP 调用 Daemon。
   - 不直接操作存储，不持有私钥。
   - 读操作直接转发，写操作自动附加 `Authorization: Bearer <token>` 头。
   - 通过环境变量 `AGENTNEXUS_MY_DID` 绑定当前 Agent 身份。

架构原则：
- **Daemon 与 MCP 解耦**：MCP 通过 HTTP（localhost:8765）调用 Daemon，不直接操作存储。
- **私钥不出户**：所有签名操作（NexusProfile、握手、Relay announce）只在 Daemon 内完成。
- **写接口鉴权**：Daemon 启动时生成 Token，所有写端点需 Bearer Token。
- **异步优先**：所有 I/O 使用 asyncio，禁止阻塞调用。
- **访问控制前置**：Gatekeeper 在握手协议之前执行，先检查再握手。

## 理由

Sidecar 架构的核心优势在于安全隔离和职责分离：

- **安全边界清晰**：私钥和数据库操作被限制在 Daemon 进程内，MCP 进程即使被攻破也无法直接获取私钥。
- **Token 鉴权**：写操作需要 Bearer Token，防止未授权的 MCP 客户端修改数据。
- **可扩展性**：多个 MCP 客户端可以同时连接同一个 Daemon，每个绑定不同的 Agent DID。
- **部署灵活**：Daemon 可以独立运行，不依赖 MCP；也可以通过 HTTP API 被其他工具调用。
- **异步性能**：asyncio 确保高并发场景下的性能，避免握手和消息路由阻塞。

### 考虑的替代方案

1. **单进程架构（MCP 直接操作数据库）** — 实现最简单，但 MCP 进程持有私钥，安全风险高；且 MCP stdio 进程生命周期由 AI 模型控制，不稳定。
2. **微服务架构（多个独立服务）** — 将 Gatekeeper、路由器、存储拆分为独立服务，过度设计，增加部署和运维复杂度。
3. **Unix Socket 通信** — 比 HTTP 更高效，但跨平台兼容性差（Windows 支持有限），且不便于调试和监控。

## 影响范围

- `agent_net/node/daemon.py`：FastAPI 服务，所有安全敏感操作的唯一入口
- `agent_net/node/mcp_server.py`：MCP stdio 代理层，通过 `_call()` 函数转发 HTTP 请求
- `agent_net/node/gatekeeper.py`：访问控制模块，在 Daemon 内运行
- `agent_net/storage.py`：SQLite CRUD，仅 Daemon 进程直接访问
- `data/daemon_token.txt`：Bearer Token 文件，MCP 读取用于鉴权

## 相关 ADR

- ADR-002: 四步握手协议设计（握手签名在 Daemon 内完成）
- ADR-005: Gatekeeper 三模式设计（Gatekeeper 在 Daemon 内运行，前置于握手）
