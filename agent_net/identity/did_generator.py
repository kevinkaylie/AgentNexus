"""@deprecated — 向后兼容重导出，请改用 agent_net.common.did"""
from agent_net.common.did import AgentDID, DIDGenerator

__all__ = ["AgentDID", "DIDGenerator"]
