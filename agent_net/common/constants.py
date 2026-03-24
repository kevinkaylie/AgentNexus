"""
agent_net.common.constants
全局常量定义
"""
import os

# ── 版本 ───────────────────────────────────────────────────
NEXUS_VERSION = "1.0"

# ── 联邦种子站列表（可在此追加公网种子地址） ────────────────
DEFAULT_SEEDS: list[str] = [
    # "https://seed1.nexus-relay.io:9000",
]

# ── Redis ──────────────────────────────────────────────────
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── 路径 ───────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_BASE_DIR, "data")
NODE_CONFIG_FILE = os.path.join(DATA_DIR, "node_config.json")
DAEMON_TOKEN_FILE = os.path.join(DATA_DIR, "daemon_token.txt")

# ── NexusProfile ───────────────────────────────────────────────
NEXUS_CONTENT_SCHEMA_VERSION = "1.0"   # content 字段格式版本（已签名，防篡改）

# ── Relay 参数 ──────────────────────────────────────────────
RELAY_TTL = 120          # 注册条目存活时间（秒）
RELAY_CLEANUP_INTERVAL = 60  # 清理检查间隔（秒）
RELAY_HEARTBEAT_INTERVAL = 60  # 节点心跳间隔（秒）
FEDERATION_PROXY_TIMEOUT = 5   # 联邦代理查询超时（秒）

# ── 握手 ───────────────────────────────────────────────────
CHALLENGE_TTL = 30       # Challenge 有效期（秒）
HANDSHAKE_PENDING_TIMEOUT = 300  # 审批等待超时（秒）
