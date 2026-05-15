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


# ── Coordination Request Models ─────────────────────────────────

class CreateCoordinationSessionRequest(BaseModel):
    owner_did: str
    controller_did: str
    objective: str
    workflow_id: str = "coding.v1"
    intake_session_id: Optional[str] = None
    parent_session_id: Optional[str] = None
    coordination_session_id: Optional[str] = None
    policy: Optional[dict] = None
    context_snapshot: Optional[dict] = None


class ForkSessionRequest(BaseModel):
    coordination_session_id: str
    actor_did: str = ""
    link_type: str = "review_fork"
    reason: str = ""


class CreateDelegationRequest(BaseModel):
    role: str
    delegator_did: str = ""
    delegatee_did: str
    capability_token_id: Optional[str] = None
    runtime_kind: str = "native_worker"
    protocol: str = "agentnexus-native"
    session_id: str = ""


class AcceptDelegationRequest(BaseModel):
    actor_did: str


class RejectDelegationRequest(BaseModel):
    actor_did: str
    reason: str = ""


class SubmitArtifactRequest(BaseModel):
    coordination_session_id: str
    stage: str
    artifact_type: str
    producer_did: str
    content_ref: str
    artifact_id: Optional[str] = None
    schema_version: str = "1"


class SubmitReceiptRequest(BaseModel):
    coordination_session_id: str
    stage: str
    receipt_type: str
    issuer_did: str
    decision: str
    subject_artifact_id: Optional[str] = ""
    evidence_refs: Optional[list[str]] = None
    signature: str = ""
    receipt_id: Optional[str] = None


class CreateRuntimeEventRequest(BaseModel):
    coordination_session_id: str
    event_type: str
    event_id: Optional[str] = None
    stage: str = ""
    actor_did: str = ""
    session_id: str = ""
    run_id: str = ""
    delegation_id: str = ""
    artifact_id: str = ""
    receipt_id: str = ""
    payload: Optional[dict] = None


class CodingIntakeRequest(BaseModel):
    owner_did: str
    actor_did: str
    objective: str
    complexity: str = "medium"
    risk_level: str = "normal"
    cost_policy: str = "balanced"
    data_sensitivity: str = "internal"
    requires_human_approval: bool = False
    session_id: Optional[str] = None
    preferred_playbook: Optional[str] = None
    source: dict = {}


class CodingClarifyRequest(BaseModel):
    actor_did: str
    requirement_spec: dict = {}
    content_ref: Optional[str] = None


class CodingAdvanceRequest(BaseModel):
    actor_did: str
