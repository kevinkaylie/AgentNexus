# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [0.8.1] - 2026-04-04

### Changed

#### DID Resolver 架构重构（ADR-009）
- **DIDMethodHandler 注册表模式**：DIDResolver 改为注册表路由，不再硬编码 if/elif 链
- **新增 `agent_net/common/did_methods/` 目录**：
  - `base.py` — DIDMethodHandler 抽象基类
  - `utils.py` — 共用工具方法（build_did_document、extract_ed25519_key_from_doc）
  - `agentnexus.py` — AgentNexusHandler（纯密码学解析）
  - `agent_legacy.py` — AgentLegacyHandler（需 db_path，仅 Daemon 注册）
  - `key.py` — KeyHandler（纯密码学解析）
  - `web.py` — WebHandler（HTTPS 端点获取）
  - `meeet.py` — MeeetHandler（需 redis_client，仅 Relay 注册）
- **注册函数**：
  - `register_daemon_handlers(db_path)` — Daemon 侧注册
  - `register_relay_handlers(redis_client)` — Relay 侧注册
  - `reset_handlers()` — 测试隔离
- **向后兼容**：所有调用方（Gatekeeper、RuntimeVerifier、SDK）零改动

### Technical
- 测试结果：144 passed, 3 skipped ✅

---

## [0.8.0] - 2026-04-04

### Added

#### SDK (agentnexus-sdk)
- **Python SDK 包** — `agentnexus-sdk/` 独立包，3 行代码接入 AgentNexus 网络
  - `pip install agentnexus-sdk` (PyPI 发布准备)
  - 依赖：`aiohttp` + `pydantic`（最小依赖）
- **核心 API**：
  - `agentnexus.connect(name, caps)` — 注册新身份
  - `agentnexus.connect(did=...)` — 复用已注册身份
  - `nexus.send(to_did, content)` — 发送消息
  - `nexus.verify(did)` — 信任查询
  - `nexus.certify(target_did, claim, evidence)` — 签发认证
  - `@nexus.on_message` — 消息回调
- **Action Layer**（ADR-007）：
  - `nexus.propose_task()` — 发布任务
  - `nexus.claim_task()` — 认领任务
  - `nexus.sync_resource()` — 同步资源
  - `nexus.notify_state()` — 汇报状态
  - 四种回调：`on_task_propose` / `on_task_claim` / `on_resource_sync` / `on_state_notify`
- **同步包装器**：`agentnexus.sync.connect()` — 非异步场景支持
- **自动发现**：
  - Daemon URL 发现：显式参数 > 环境变量 > 默认 localhost:8765
  - Token 发现：显式参数 > 环境变量 > 用户目录 > 项目目录
  - Token 权限检查（非 0600 时警告）

#### Daemon 扩展
- **Token 写入用户目录**：`~/.agentnexus/daemon_token.txt`（跨项目共享）
- **messages 表扩展**：新增 `message_type` / `protocol` 列
- **`/messages/send` 支持 Action Layer**：`content: Union[str, dict]`
- **`fetch_inbox()` 返回新字段**：`message_type` / `protocol`

#### did:meeet 桥接（ADR-008）
- **`POST /meeet/admin/register`**：平台管理员注册
- **`POST /meeet/register`**：单个 MEEET Agent 注册
- **`POST /meeet/batch-register`**：批量注册（最大 100 条）
- **`GET /meeet/status`**：映射状态统计
- **`GET /resolve/did:meeet:...`**：解析 MEEET DID → did:agentnexus
- **x402 score 映射**：MEEET reputation → x402 score
- **Mock Solana API**：`MEEET_SOLANA_RPC_URL` 环境变量

### Changed
- `agent_net/router.py`：路由支持 `message_type` / `protocol` 参数
- `agent_net/storage.py`：`store_message()` 新增可选参数
- `agent_net/relay/server.py`：`/resolve/{did}` 支持 `did:meeet` 方法

### Technical
- SDK 包结构：`src/agentnexus/{__init__,client,actions,models,discovery,exceptions,sync}.py`
- 测试结果：144 passed, 3 skipped ✅

---

## [0.6.0] - 2026-03-26

### Added
- **W3C DID Method `did:agentnexus`** — new DID format based on Ed25519 multikey encoding
  - Format: `did:agentnexus:z<base58btc(0xED01 || pubkey)>`
  - New `DIDGenerator.create_agentnexus()` in `common/did.py`
  - `DIDResolver` supports resolution of `did:agentnexus` by pure crypto (no network)
- **W3C DID Document** — `_build_did_document()` now outputs full W3C-compliant DID Doc
  - `Ed25519VerificationKey2018` verification method with multibase encoding
  - `X25519KeyAgreementKey2019` derived from Ed25519 pubkey for ECDH
  - Optional `service` array (relay endpoint + agent endpoint)
- **`GET /resolve/{did}` on Relay** — returns W3C DID Document + source metadata
  - Checks local registry → PeerDirectory → pure crypto (did:agentnexus)
- **`GET /resolve/{did}` on Daemon** — returns W3C DID Document with service endpoints
  - Derives pubkey from stored private key for local agents
  - Falls back to relay for non-local DIDs
- **Key export/import** — `agent_net/common/keystore.py`
  - `export_agent()`: argon2id KDF + AES-256-GCM (nacl SecretBox) encryption
  - `import_agent()`: decrypt and restore DID + private key + profile + certifications
  - Daemon endpoints: `GET /agents/{did}/export`, `POST /agents/import` (token required)
  - CLI: `python main.py agent export <did> --output <file> --password <pw>`
  - CLI: `python main.py agent import <file> --password <pw>`
  - MCP tools: `export_agent` (16th) and `import_agent` (17th)
- **`build_services_from_profile()`** helper in `common/did.py` for DID Doc service extraction
- **44 new tests** in `tests/test_did_resolution.py` (new endpoint tests + async fixes) and `tests/test_keystore.py` (tk01–tk05)

### Changed
- `RegisterRequest` now defaults to `did_format="agentnexus"` — new agents get `did:agentnexus:z...` DIDs
  - `did_format="agent"` preserves legacy `did:agent:<hex>` behavior
  - `public_key_hex` saved to profile for DID resolution without private key
- Relay version: `0.3.0` → `0.6.0`
- Daemon version: `0.5.0` → `0.6.0`
- `requirements.txt`: added `httpx>=0.27.0` (for `did:web` resolution)

### Technical
- Total tests: 124 (up from 80 in v0.5)
- All existing tests pass unchanged

---

## [0.5.0] - 2026-03-26

### Added
- **Session management** — messages now carry `session_id` and `reply_to` fields for conversation continuity
  - Auto-generated `sess_<uuid>` when omitted; explicit session ID preserved when provided
  - New endpoint `GET /messages/session/{session_id}` for full conversation history
  - New MCP tool `get_session` (13th tool) for retrieving conversation context
- **Multi-party certification system** — NexusProfile supports third-party signed certifications
  - `certifications` top-level field (outside signed `content`, independently verifiable)
  - Each certification: `{issuer, issuer_pubkey, claim, evidence, issued_at, signature}`
  - New helper functions: `create_certification()`, `verify_certification()` in `profile.py`
  - New endpoint `POST /agents/{did}/certify` for issuing certifications (token required)
  - New endpoint `GET /agents/{did}/certifications` for listing certifications
  - New MCP tools: `certify_agent` (14th) and `get_certifications` (15th)
  - `GET /agents/{did}/profile` now includes certifications in response
- **Giskard integration proposal** — `docs/giskard-proposal.md` with technical alignment plan
- 12 new tests (tv01–tv12) in `tests/test_v05.py`

### Changed
- `SendMessageRequest` extended with `session_id` and `reply_to` fields
- `store_message()` and `fetch_inbox()` support session_id and reply_to
- `router.route_message()` passes session_id and reply_to through all routing paths
- Total MCP tools: 12 → 15
- Total test count: 68 → 80

## [0.4.0] - 2025-03-25

### Added
- **Relay announce signature verification** — `/announce` now requires Ed25519 signed payload with TOFU pubkey binding and timestamp replay protection (60s skew)
- **Federation announce signature verification** — `/federation/announce` verifies NexusProfile signature + DID consistency
- **Federation join callback verification** — `/federation/join` verifies the joining relay is reachable via health check callback
- **Rate limiting** — per-DID/per-URL rate limiter (30 req/min) on all three relay write endpoints
- **Daemon signed announce** — `_announce_to_relay()` now signs payloads with agent's Ed25519 private key
- New helper functions: `canonical_announce()`, `verify_signed_payload()` in `profile.py`
- 12 new security tests (ts01–ts12) in `test_federation.py`

### Changed
- `AnnounceRequest` model extended with `pubkey`, `timestamp`, `signature` fields
- 7 existing federation tests updated to send signed payloads
- Total test count: 56 → 68

## [0.3.0] - 2025-03-24

### Added
- **Redis storage for Relay** — migrated from in-memory registry to Redis with TTL-based auto-expiry
- **Docker deployment** — `Dockerfile`, `docker-compose.yml` (redis + relay + nginx + certbot)
- **TLS/SSL support** — nginx reverse proxy with Let's Encrypt auto-renewal via `scripts/init-ssl.sh`
- Cloud seed relay deployment documentation

### Changed
- Relay `_registry` replaced with Redis `SETEX`/`SET` operations
- `_create_redis()` factory function for test isolation (monkeypatch with fakeredis)

## [0.2.0] - 2025-03-23

### Added
- **MCP Agent binding** — `node mcp --name` / `--did` for automatic agent registration and identity binding
- `whoami` MCP tool (12th tool)
- 7 MCP binding tests (tm01–tm07)
- **14 new test cases** covering relay fault tolerance, NexusProfile signing sync, token auth edge cases

### Fixed
- Remove `register_local_session` from agent register handler
- Replace Unicode checkmark with ASCII to avoid GBK encoding errors on Windows
- Add `--entrypoint certbot` to `init-ssl.sh` certbot run command

## [0.1.0] - 2025-03-22

### Added
- **Federated Relay network** — `/federation/join`, `/federation/announce`, 1-hop proxy lookup
- **NexusProfile signed cards** — Ed25519 signed identity cards with `schema_version` in content
- **Token authentication** — `data/daemon_token.txt` Bearer token for all daemon write endpoints
- **Gatekeeper access control** — Public / Ask / Private modes with blacklist/whitelist
- **Four-step handshake** — Ed25519 challenge-response + X25519 ECDH + AES-256-GCM
- **Smart message routing** — local → P2P → relay → offline fallback
- **STUN NAT traversal** — UDP-based public IP:Port discovery
- **MCP stdio server** — 11 tools for AI agent integration
- **SQLite storage** — agents, messages, contacts, pending_requests tables
- **CLI** — `main.py` unified entry point for relay/node/agent/test commands

## [0.0.1] - 2025-03-21

### Added
- Initial commit: project structure, DID generator, basic agent profiles
- The Alien Antenna Duck mascot is born!
