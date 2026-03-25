# Security Policy

**[中文](#中文) | [English](#english)**

---

## 中文

### 支持的版本

| 版本 | 支持状态 |
|------|----------|
| main 分支最新 | :white_check_mark: 安全更新 |
| 旧 commit | :x: 不再维护 |

### 报告漏洞

如果你发现了安全漏洞，**请不要**通过公开 Issue 提交。

请发送邮件至：**kevinkaylie@outlook.com**

邮件请包含：

- 漏洞描述（尽可能详细）
- 复现步骤
- 影响范围评估（哪些组件/端点受影响）
- 你的建议修复方案（可选）

### 响应流程

1. **48 小时内**确认收到报告
2. **7 天内**完成初步评估并回复处理计划
3. 修复后发布安全公告（GitHub Security Advisory）
4. 在 CHANGELOG 中记录修复内容

### 安全架构概述

AgentNexus 使用以下安全机制：

- **Ed25519** 签名验证（DID 身份、NexusProfile 名片、Relay announce）
- **X25519 ECDH** 密钥协商 + **AES-256-GCM** 消息加密
- **TOFU（Trust On First Use）** 公钥绑定防止 DID 劫持
- **Timestamp 防重放**（60 秒时钟偏差容忍）
- **Bearer Token** 写接口鉴权
- **Gatekeeper** 三级访问控制（Public / Ask / Private）
- **速率限制**（30 req/min per DID）

### 已知限制

- DID 不从公钥派生，依赖 TOFU 模型建立信任
- SQLite 数据库和 Redis 未加密存储
- 私钥以 hex 明文存于 SQLite（依赖文件系统权限保护）

---

## English

### Supported Versions

| Version | Status |
|---------|--------|
| Latest on main | :white_check_mark: Security updates |
| Older commits | :x: Not maintained |

### Reporting a Vulnerability

If you discover a security vulnerability, **DO NOT** open a public Issue.

Email: **kevinkaylie@outlook.com**

Please include:

- Detailed description of the vulnerability
- Steps to reproduce
- Impact assessment (which components/endpoints are affected)
- Suggested fix (optional)

### Response Process

1. Acknowledgment within **48 hours**
2. Initial assessment and response plan within **7 days**
3. Security advisory published after fix (GitHub Security Advisory)
4. Fix documented in CHANGELOG

### Security Architecture

AgentNexus employs the following security mechanisms:

- **Ed25519** signature verification (DID identity, NexusProfile cards, Relay announce)
- **X25519 ECDH** key agreement + **AES-256-GCM** message encryption
- **TOFU (Trust On First Use)** pubkey binding to prevent DID hijacking
- **Timestamp replay protection** (60-second clock skew tolerance)
- **Bearer Token** authentication for write endpoints
- **Gatekeeper** 3-tier access control (Public / Ask / Private)
- **Rate limiting** (30 req/min per DID)

### Known Limitations

- DIDs are not derived from public keys; trust relies on the TOFU model
- SQLite database and Redis store data unencrypted
- Private keys stored as hex plaintext in SQLite (protected by filesystem permissions)
