# 向后兼容重导出，统一从 agent_net.common.did 导入
from agent_net.common.did import AgentDID, DIDGenerator

__all__ = ["AgentDID", "DIDGenerator"]
