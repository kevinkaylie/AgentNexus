"""
DID Method Handlers 注册

提供两个注册函数：
- register_daemon_handlers(): Daemon 侧使用
- register_relay_handlers(): Relay 侧使用
"""
from agent_net.common.did import DIDResolver
from .agentnexus import AgentNexusHandler
from .agent_legacy import AgentLegacyHandler
from .key import KeyHandler
from .web import WebHandler
from .meeet import MeeetHandler

__all__ = [
    "DIDMethodHandler",
    "AgentNexusHandler",
    "AgentLegacyHandler",
    "KeyHandler",
    "WebHandler",
    "MeeetHandler",
    "register_daemon_handlers",
    "register_relay_handlers",
    "reset_handlers",
]

from .base import DIDMethodHandler


def register_daemon_handlers(db_path: str):
    """
    Daemon 启动时调用，注册所有 Daemon 侧需要的 handler。

    包含: agentnexus, agent (legacy), key, web
    不包含: meeet（仅 Relay 需要）

    Args:
        db_path: SQLite 数据库路径（AgentLegacyHandler 需要）
    """
    DIDResolver.register(AgentNexusHandler())
    DIDResolver.register(AgentLegacyHandler(db_path=db_path))
    DIDResolver.register(KeyHandler())
    DIDResolver.register(WebHandler())


def register_relay_handlers(redis_client):
    """
    Relay 启动时调用，注册所有 Relay 侧需要的 handler。

    包含: agentnexus, key, web, meeet
    不包含: agent (legacy)（仅 Daemon 本地有意义）

    Args:
        redis_client: Redis 异步客户端（MeeetHandler 需要）
    """
    DIDResolver.register(AgentNexusHandler())
    DIDResolver.register(KeyHandler())
    DIDResolver.register(WebHandler())
    DIDResolver.register(MeeetHandler(redis_client=redis_client))


def reset_handlers():
    """
    清空所有已注册的 handler。

    仅用于测试：防止测试间状态污染。
    """
    DIDResolver.reset_handlers()
