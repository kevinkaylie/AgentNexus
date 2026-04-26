"""
AgentNexus SDK Data Models
"""
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime


@dataclass
class Message:
    """A message received from another Agent."""
    id: int
    from_did: str
    content: str
    timestamp: float
    session_id: str = ""
    reply_to: Optional[int] = None
    message_type: Optional[str] = None
    protocol: Optional[str] = None
    message_id: Optional[str] = None

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)


@dataclass
class VerificationResult:
    """Result of trust verification for an Agent."""
    did: str
    trust_level: int  # 1-4
    permissions: list[str]
    spending_limit: float
    certifications: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class Certification:
    """A certification issued by a CA."""
    version: str
    issuer: str
    issuer_pubkey: str
    claim: str
    evidence: str
    issued_at: float
    signature: str

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "issuer": self.issuer,
            "issuer_pubkey": self.issuer_pubkey,
            "claim": self.claim,
            "evidence": self.evidence,
            "issued_at": self.issued_at,
            "signature": self.signature,
        }
