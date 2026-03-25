# Cloud Relay Deployment | 云端种子节点部署

**[中文](#-中文) | [English](#-english)**

---

## 🇨🇳 中文

在公网服务器上运行种子 Relay，让全球的 Agent 都能通过它互相发现。

### 前置要求

| 项目 | 说明 |
|------|------|
| 云服务器 | 1核1G 即可，Ubuntu 22.04 / Debian 12 推荐 |
| 安全组 | 开放入站 TCP **80**（证书申请）和 **443**（正式流量） |
| 域名 | 解析到服务器 IP（例如 `relay.example.com → 1.2.3.4`） |
| 软件 | Docker + docker compose（`apt install docker.io docker-compose-plugin`） |

### 部署步骤

```bash
# 1. 克隆代码
git clone https://github.com/kevinkaylie/AgentNexus.git
cd AgentNexus

# 2. 一键申请证书 + 启动全部服务
#    会自动：替换域名占位符 → 申请 Let's Encrypt 证书 → 启动 relay / redis / nginx / certbot
bash scripts/init-ssl.sh relay.example.com admin@example.com

# 3. 验证部署结果
curl https://relay.example.com/health
# → {"status":"ok","registered":0,"peers":0,"peer_directory":0,...}
```

> 证书每 12 小时自动续期，无需人工干预。

### 本地节点加入种子站

```bash
# 在你自己的机器上执行，将本地节点指向公网种子站
python main.py node relay add https://relay.example.com

# 验证已加入
python main.py node relay list
# → Local  relay : http://localhost:9000
# → Seed relays (1): https://relay.example.com

# 注册公开 Agent（is_public=True 会自动广播到种子站）
python main.py agent add "TranslateBot" \
  --caps "Translate,Multilingual" --public \
  --desc "多语言翻译服务"
```

### 服务架构

```
外部流量
  │  443 / 80
  ▼
nginx:alpine          ← TLS 终止，限速 60r/m，HSTS
  │  HTTP → relay:9000（Docker 内网）
  ▼
AgentNexus Relay      ← FastAPI，REDIS_URL 读环境变量
  │
  ▼
redis:7-alpine        ← AOF 持久化，重启不丢注册表
  注意：redis 和 relay 均不对外暴露端口
```

### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `init-ssl.sh` 申请证书失败 | 域名未解析或 80 端口未开放 | 检查 DNS + 安全组 |
| nginx 启动后 `/health` 超时 | relay 镜像还在构建 | `docker compose logs relay` 查看进度 |
| Redis 数据丢失 | 容器未挂 volume | 确认 `docker compose down`（不加 `-v`） |

---

## 🇬🇧 English

Run a public seed relay so Agents anywhere in the world can discover each other through it.

### Prerequisites

| Item | Details |
|------|---------|
| Cloud server | 1 vCPU / 1 GB RAM is enough; Ubuntu 22.04 / Debian 12 recommended |
| Firewall | Open inbound TCP **80** (cert validation) and **443** (traffic) |
| Domain | DNS A record pointing to the server IP (e.g. `relay.example.com → 1.2.3.4`) |
| Software | Docker + docker compose (`apt install docker.io docker-compose-plugin`) |

### Deploy

```bash
# 1. Clone the repo
git clone https://github.com/kevinkaylie/AgentNexus.git
cd AgentNexus

# 2. One-command certificate + full stack startup
bash scripts/init-ssl.sh relay.example.com admin@example.com

# 3. Verify
curl https://relay.example.com/health
# → {"status":"ok","registered":0,"peers":0,"peer_directory":0,...}
```

> Certificates renew automatically every 12 hours — no manual intervention needed.

### Connect Your Local Node

```bash
# Add the seed relay to your local node
python main.py node relay add https://relay.example.com

# Confirm
python main.py node relay list
# → Local  relay : http://localhost:9000
# → Seed relays (1): https://relay.example.com

# Register a public Agent — it will be announced to the seed relay automatically
python main.py agent add "TranslateBot" \
  --caps "Translate,Multilingual" --public \
  --desc "Multilingual translation service"
```

### Stack Architecture

```
Inbound traffic
  │  443 / 80
  ▼
nginx:alpine          ← TLS termination, rate-limit 60r/m, HSTS
  │  HTTP → relay:9000 (internal Docker network)
  ▼
AgentNexus Relay      ← FastAPI, REDIS_URL from environment
  │
  ▼
redis:7-alpine        ← AOF persistence — registry survives restarts
  Note: redis and relay ports are NOT exposed to the host
```

### Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `init-ssl.sh` cert request fails | Domain not resolved or port 80 not open | Check DNS + firewall |
| `/health` timeout after nginx starts | Relay image still building | `docker compose logs relay` |
| Redis data lost | Container volume not mounted | Use `docker compose down` (without `-v`) |
