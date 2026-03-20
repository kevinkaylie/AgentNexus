"""
agent_net.common.did
DID 生成与 AgentProfile 管理 —— node 和 relay 共用
"""
import hashlib
import time
import uuid
from dataclasses import dataclass, field, asdict

from nacl.signing import SigningKey, VerifyKey


# ── DID ──────────────────────────────────────────────────

@dataclass
class AgentDID:
    did: str
    private_key: SigningKey
    verify_key: VerifyKey


class DIDGenerator:
    @staticmethod
    def create_new(name: str = "") -> AgentDID:
        sk = SigningKey.generate()
        unique = f"{name}-{uuid.uuid4()}-{time.time()}"
        hash_val = hashlib.sha256(unique.encode()).hexdigest()[:16]
        did = f"did:agent:{hash_val}"
        return AgentDID(did=did, private_key=sk, verify_key=sk.verify_key)


# ── AgentProfile ─────────────────────────────────────────

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
