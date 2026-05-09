"""@deprecated — 向后兼容重导出，请改用 agent_net.common.handshake"""
from agent_net.common.handshake import HandshakeManager, SessionKey

__all__ = ["HandshakeManager", "SessionKey"]
