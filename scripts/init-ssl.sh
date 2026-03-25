#!/bin/bash
# scripts/init-ssl.sh — 首次申请 Let's Encrypt 证书
#
# 用法：bash scripts/init-ssl.sh <域名> <邮箱>
# 示例：bash scripts/init-ssl.sh relay.example.com admin@example.com
#
# 前提：
#   - 域名 DNS 已解析到本服务器
#   - 服务器 80 端口已对外开放（安全组/防火墙放行）
#   - Docker 和 docker compose 已安装

set -e

DOMAIN=${1:?用法: $0 <域名> <邮箱>}
EMAIL=${2:?用法: $0 <域名> <邮箱>}

echo "[1/4] 替换 nginx 配置中的域名占位符..."
sed -i "s/YOUR_DOMAIN/${DOMAIN}/g" nginx/conf.d/relay.conf

echo "[2/4] 启动 redis 和 relay（nginx 暂不启动，释放 80 端口给 certbot）..."
docker compose up -d redis relay

echo "[3/4] 申请 SSL 证书（standalone 模式，certbot 自己监听 80 端口）..."
docker compose run --rm \
  --entrypoint certbot \
  -p 80:80 \
  certbot certonly \
    --standalone \
    --email "${EMAIL}" \
    --agree-tos \
    --no-eff-email \
    -d "${DOMAIN}"

echo "[4/4] 启动 nginx 和 certbot 续期服务..."
docker compose up -d

echo ""
echo "部署完成！"
echo "  Relay 地址：https://${DOMAIN}"
echo "  健康检查：curl https://${DOMAIN}/health"
echo "  加入联邦：在本地节点执行 python main.py node relay add https://${DOMAIN}"
