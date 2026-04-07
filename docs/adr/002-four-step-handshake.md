# ADR-002: 四步握手协议设计

## 状态

已采纳

## 日期

2025-03-22

## 背景

AgentNexus 中的 Agent 需要在不可信网络上建立安全的端到端加密通信。协议需要满足以下要求：

1. **身份验证**：双方需要验证对方的 DID 身份真实性。
2. **密钥协商**：需要在不传输密钥的情况下协商出共享会话密钥。
3. **前向安全**：即使长期密钥泄露，历史会话也不应被解密。
4. **防重放**：协议需要防止中间人重放旧的握手消息。

同时，协议需要足够轻量，适合在 HTTP 和 WebSocket 上运行，且不依赖 TLS 客户端证书等复杂基础设施。

## 决策

采用四步握手协议（Agent Handshake Protocol, AHP），流程如下：

```
A                           B
│  ① INIT(A_did, A_pubkey)  ──────────────►│
│  ② CHALLENGE(nonce)       ◄──────────────│
│  ③ VERIFY(sign(nonce), A_ecdh_pub) ─────►│
│  ④ CONFIRM(B_ecdh_pub)   ◄──────────────│
│                                          │
│  session_key = ECDH(A_priv, B_pub)       │
│  AES-256-GCM 加密通信开始               │
```

- **步骤 ①（INIT）**：发起方发送自己的 DID 和 Ed25519 公钥。
- **步骤 ②（CHALLENGE）**：接收方生成随机 nonce 作为挑战，TTL = 30 秒。
- **步骤 ③（VERIFY）**：发起方用 Ed25519 私钥签名 nonce，并附带 X25519 ECDH 临时公钥。
- **步骤 ④（CONFIRM）**：接收方验证签名后，返回自己的 X25519 ECDH 临时公钥。
- **会话密钥**：双方通过 X25519 ECDH 计算共享密钥，用于 AES-256-GCM 加密后续通信。

密码学组件选择：
- **身份验证**：Ed25519 签名（签名 challenge nonce）
- **密钥协商**：X25519 ECDH（临时密钥对，提供前向安全）
- **消息加密**：AES-256-GCM（nonce 12 字节 + 密文格式）
- **Challenge TTL**：30 秒，过期抛出 `ValueError`

## 理由

四步握手在安全性和实现复杂度之间取得了良好平衡：

- **Ed25519 + X25519 组合**：Ed25519 用于身份验证（签名），X25519 用于密钥协商（ECDH），两者基于同一条曲线（Curve25519），可以从 Ed25519 密钥推导出 X25519 密钥，减少密钥管理负担。
- **Challenge-Response 防重放**：随机 nonce + 30 秒 TTL 有效防止重放攻击。
- **临时 ECDH 密钥**：每次握手生成新的 X25519 密钥对，提供前向安全性。
- **AES-256-GCM**：AEAD 加密模式，同时提供机密性和完整性保护，是业界标准选择。

### 考虑的替代方案

1. **TLS 1.3 客户端证书** — 安全性最高，但需要 PKI 基础设施，与去中心化架构矛盾，且在 MCP stdio 场景下不适用。
2. **Noise Protocol Framework（XX 模式）** — 理论上更优雅，但引入额外依赖，且团队对 Noise 协议的实现经验有限。
3. **简单共享密钥** — 实现最简单，但无法提供前向安全性，密钥分发本身就是难题。
4. **三步握手（省略 CONFIRM）** — 减少一次往返，但接收方无法向发起方证明自己的身份，变成单向认证。

## 影响范围

- `agent_net/common/handshake.py`：`create_init_packet`、`process_init`、`process_challenge`、`verify_response`、`SessionKey` 类
- `agent_net/node/daemon.py`：`POST /handshake/init` 端点，握手入口
- `agent_net/node/gatekeeper.py`：Gatekeeper 在握手步骤 ① 之后、步骤 ② 之前执行访问控制检查
- `agent_net/router.py`：路由器在建立连接时触发握手流程

## 相关 ADR

- ADR-001: DID 格式选择（握手中使用 DID 标识身份）
- ADR-003: Sidecar 架构（握手签名在 Daemon 内完成，私钥不出户）
- ADR-005: Gatekeeper 三模式设计（Gatekeeper 在握手流程中前置执行）
