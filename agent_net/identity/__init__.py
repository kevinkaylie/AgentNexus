# 向后兼容重导出
from agent_net.common.did import DIDGenerator, AgentDID, AgentProfile
from agent_net.common.did import DIDGenerator as _gen

def generate_did(name: str = "") -> str:
    return _gen.create_new(name).did

__all__ = ["generate_did", "AgentProfile", "DIDGenerator", "AgentDID"]
