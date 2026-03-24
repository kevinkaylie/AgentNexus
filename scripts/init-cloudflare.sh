#!/bin/bash
# scripts/init-cloudflare.sh — Cloudflare Tunnel 初始化
#
# 用法：bash scripts/init-cloudflare.sh <域名>
# 示例：bash scripts/init-cloudflare.sh relay.example.com
#
# 前提：
#   - 域名已托管在 Cloudflare（NS 指向 Cloudflare）
#   - 已安装 cloudflared：https://github.com/cloudflare/cloudflared/releases
#     Ubuntu/Debian: apt install cloudflared
#     或直接下载：
#     curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
#          -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared

set -e

DOMAIN=${1:?用法: $0 <域名>}

echo "[1/4] 登录 Cloudflare（浏览器授权）..."
cloudflared tunnel login

echo "[2/4] 创建隧道 agentnexus-relay..."
cloudflared tunnel create agentnexus-relay

echo "[3/4] 绑定域名 ${DOMAIN} 到隧道..."
cloudflared tunnel route dns agentnexus-relay "${DOMAIN}"

echo "[4/4] 获取 Tunnel Token 并写入 .env ..."
# 获取 tunnel ID
TUNNEL_ID=$(cloudflared tunnel list --output json | python3 -c \
  "import json,sys; tunnels=json.load(sys.stdin); \
   print(next(t['id'] for t in tunnels if t['name']=='agentnexus-relay'))")

TOKEN=$(cloudflared tunnel token "${TUNNEL_ID}")

# 写入 .env（docker compose 自动读取）
cat > .env <<EOF
TUNNEL_TOKEN=${TOKEN}
EOF
chmod 600 .env

echo ""
echo "完成！执行以下命令启动服务："
echo "  docker compose up -d"
echo ""
echo "验证（约 30 秒后生效）："
echo "  curl https://${DOMAIN}/health"
echo ""
echo "本地节点加入种子站："
echo "  python main.py node relay add https://${DOMAIN}"
