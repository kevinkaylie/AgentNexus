# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

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
