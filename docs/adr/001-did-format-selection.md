# ADR-001: DID 格式选择

## 状态

已采纳

## 日期

2026-03-26

## 背景

AgentNexus 需要为每个 Agent 分配全局唯一的去中心化标识符（DID）。随着项目从初始原型演进到符合 W3C 标准的实现，DID 格式经历了三次迭代：

1. **v0.1（初始版本）**：使用 `did:agent:<hex>` 格式，基于 `name + uuid` 的 SHA-256 哈希截取 16 字符十六进制字符串，简单易用但不具备密码学自证性。
2. **v0.6（标准化）**：引入 `did:agentnexus:<multikey>` 格式，multikey 编码为 `z` + base58btc(0xED01 || ed25519_pubkey)，符合 W3C DID 规范和 QNTM Working Group 的 DID Resolution 标准。
3. **v0.7.1（Relay 身份）**：新增 `did:web:<domain>` 格式，用于 Relay 服务器身份标识，通过 `/.well-known/did.json` 端点解析 DID Document。

项目需要在保持向后兼容的同时，选择一个默认的 DID 格式用于新 Agent 注册。

## 决策

同时支持三种 DID 格式，默认使用 `did:agentnexus` 作为新 Agent 的 DID 格式：

- **`did:agent:<hex>`**：保留向后兼容，`RegisterRequest` 中 `did_format="agent"` 可继续使用旧格式。
- **`did:agentnexus:<multikey>`**：默认格式（`did_format="agentnexus"`），所有新注册 Agent 自动获得此格式 DID。multikey 编码方式为 `z` + base58btc(0xED01 || ed25519_pubkey)，具备密码学自证性。
- **`did:web:<domain>`**：仅用于 Relay 服务器身份，通过 HTTPS 域名解析，DID Document 存放在 `/.well-known/did.json`。

`DIDResolver` 统一支持四种解析方法：本地注册表查询、Relay 查询、纯密码学解析（did:agentnexus）、HTTPS 解析（did:web）。

## 理由

`did:agentnexus` 作为默认格式的核心优势：

- **自证性（Self-Certifying）**：DID 本身包含公钥信息，无需网络查询即可验证身份，适合去中心化场景。
- **WG 合规**：符合 QNTM Working Group 的 DID Resolution 规范，便于与生态系统中其他项目互操作。
- **密码学安全**：基于 Ed25519 公钥编码，提供强身份绑定。

保留 `did:agent` 确保已部署节点的平滑迁移；引入 `did:web` 满足 Relay 服务器需要基于域名的可发现性需求。

### 考虑的替代方案

1. **仅使用 `did:agent`** — 实现简单，但缺乏密码学自证性，不符合 W3C 标准，无法与外部生态互操作。
2. **仅使用 `did:key`** — W3C 标准方法，但 `did:key` 是通用格式，无法体现 AgentNexus 的 Agent 语义，且与 QNTM WG 的 `did:agentnexus` 规范不一致。
3. **强制迁移到 `did:agentnexus`，废弃 `did:agent`** — 破坏向后兼容性，已部署节点需要全部重新注册。

## 影响范围

- `agent_net/common/did.py`：`DIDGenerator` 新增 `create_agentnexus()` 方法，`DIDResolver` 支持多格式解析
- `agent_net/node/daemon.py`：`RegisterRequest` 默认 `did_format="agentnexus"`
- `agent_net/relay/server.py`：新增 `/.well-known/did.json` 端点和 `/resolve/{did}` 端点
- `agent_net/common/crypto.py`：Base58BTC 编码、multikey Ed25519/X25519 工具函数
- 现有 `did:agent` 格式的 Agent 数据无需迁移，保持兼容

## 相关 ADR

- ADR-002: 四步握手协议设计（握手协议中使用 DID 进行身份标识）
- ADR-004: 多 CA 认证架构（认证中的 issuer 字段使用 DID 格式）
