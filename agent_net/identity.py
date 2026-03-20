"""
Agent身份管理模块 - DID生成与Profile管理
"""
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


def generate_did(name: str = None) -> str:
    """生成唯一的去中心化身份标识"""
    unique = f"{name or ''}-{uuid.uuid4()}-{time.time()}"
    hash_val = hashlib.sha256(unique.encode()).hexdigest()[:16]
    return f"did:agent:{hash_val}"


@dataclass
class AgentProfile:
    id: str
    name: str
    type: str = "GeneralAgent"
    capabilities: list[str] = field(default_factory=list)
    location: str = ""
    endpoints: dict = field(default_factory=dict)
    context: str = "https://agent-net.io/v1"
    created_at: float = field(default_factory=time.time)

    def to_json_ld(self) -> dict:
        return {
            "@context": self.context,
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "capabilities": self.capabilities,
            "location": self.location,
            "endpoints": self.endpoints,
        }

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentProfile":
        data.pop("context", None)
        return cls(**data)
