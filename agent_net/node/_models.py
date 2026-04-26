"""所有 Pydantic 请求模型"""
from pydantic import BaseModel
from typing import Optional


class RegisterRequest(BaseModel):
    name: str
    type: str = "GeneralAgent"
    capabilities: list[str] = []
    location: str = ""
    did: Optional[str] = None
    is_public: bool = False
    description: str = ""
    tags: list[str] = []
    did_format: str = "agentnexus"
    worker_type: str = "resident"


class SendMessageRequest(BaseModel):
    from_did: str
    to_did: str
    content: str | dict
    session_id: str = ""
    reply_to: int | None = None
    message_type: Optional[str] = None
    protocol: Optional[str] = None
    message_id: Optional[str] = None  # D-SEC-09: 客户端可传入自定义 message_id；未传时服务端生成


class AddContactRequest(BaseModel):
    did: str
    endpoint: str
    relay: Optional[str] = None


class ResolveRequest(BaseModel):
    did: str
    action: str


class UpdateCardRequest(BaseModel):
    actor_did: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class CertifyRequest(BaseModel):
    issuer_did: str
    claim: str
    evidence: str = ""


class RuntimeVerifyRequest(BaseModel):
    agent_did: str
    agent_public_key: str
    trusted_cas: Optional[dict] = None


class ExportRequest(BaseModel):
    password: str


class ImportRequest(BaseModel):
    data: str
    password: str


class PushRegisterRequest(BaseModel):
    did: str
    callback_url: str
    callback_type: str = "webhook"
    push_key: Optional[str] = None
    expires: int = 3600


class PushRefreshRequest(BaseModel):
    did: str
    callback_url: str
    callback_type: str = "webhook"
    expires: int = 3600


class CreateEnclaveRequest(BaseModel):
    name: str
    owner_did: str
    actor_did: str | None = None
    vault_backend: str = "local"
    vault_config: dict = {}
    members: dict = {}


class UpdateEnclaveRequest(BaseModel):
    actor_did: str | None = None
    name: str | None = None
    status: str | None = None
    vault_backend: str | None = None
    vault_config: dict | None = None


class AddMemberRequest(BaseModel):
    actor_did: str
    did: str
    role: str
    permissions: str = "rw"
    handbook: str = ""


class UpdateMemberRequest(BaseModel):
    actor_did: str | None = None
    role: str | None = None
    permissions: str | None = None
    handbook: str | None = None


class VaultPutRequest(BaseModel):
    value: str
    author_did: str
    message: str = ""


class VaultDeleteRequest(BaseModel):
    author_did: str


class CreatePlaybookRunRequest(BaseModel):
    actor_did: str
    playbook_id: str | None = None
    playbook: dict | None = None


class GovernanceValidateRequest(BaseModel):
    agent_did: str
    requested_capabilities: list[dict] = []
    context: dict = {}
    clients: Optional[list[str]] = None


class TrustEdgeRequest(BaseModel):
    from_did: str
    to_did: str
    score: float
    evidence: Optional[str] = None
    signature: Optional[str] = None


class InteractionRequest(BaseModel):
    from_did: str
    to_did: str
    interaction_type: str
    success: bool
    response_time_ms: Optional[float] = None
