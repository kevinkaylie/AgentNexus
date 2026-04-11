"""
AgentNexus Python SDK

3 lines to connect your AI Agent to the decentralized network.

Usage:
    import agentnexus

    # Register new identity
    nexus = await agentnexus.connect("MyAgent", caps=["Chat", "Search"])

    # Or use existing identity
    nexus = await agentnexus.connect(did="did:agentnexus:z6Mk...")

    # Send message
    await nexus.send(to_did="did:agentnexus:z6Mk...", content="Hello!")

    # Receive messages
    @nexus.on_message
    async def handle(msg):
        print(f"From {msg.from_did}: {msg.content}")

    # Create Enclave (project team)
    enclave = await nexus.create_enclave(
        name="Login Feature Dev",
        members={
            "architect": {"did": "did:agentnexus:...", "handbook": "Design"},
            "developer": {"did": "did:agentnexus:...", "handbook": "Code"},
        },
    )

    # Vault operations
    await enclave.vault.put("requirements", "...")
    doc = await enclave.vault.get("requirements")

    # Close connection
    await nexus.close()
"""

from .client import AgentNexusClient, connect
from .exceptions import (
    AgentNexusError,
    DaemonNotFoundError,
    AuthenticationError,
    AgentNotFoundError,
    MessageDeliveryError,
    InvalidActionError,
    DIDNotFoundError,
)
from .models import Message, VerificationResult, Certification
from .actions import (
    TaskPropose,
    TaskClaim,
    ResourceSync,
    StateNotify,
)
from .discussion import (
    DiscussionStart,
    DiscussionReply,
    DiscussionVote,
    DiscussionConclude,
    Consensus,
    ActionItem,
    ConsensusMode,
    TimeoutAction,
    ConclusionType,
    DiscussionStateMachine,
    DiscussionManager,
)
from .emergency import (
    EmergencyConfig,
    EmergencyController,
    create_emergency_controller,
)
from .enclave import (
    VaultEntry,
    EnclaveInfo,
    PlaybookRunInfo,
    VaultProxy,
    PlaybookRunProxy,
    EnclaveProxy,
    EnclaveManager,
)

__all__ = [
    # Core
    "connect",
    "AgentNexusClient",
    # Exceptions
    "AgentNexusError",
    "DaemonNotFoundError",
    "AuthenticationError",
    "AgentNotFoundError",
    "MessageDeliveryError",
    "InvalidActionError",
    "DIDNotFoundError",
    # Models
    "Message",
    "VerificationResult",
    "Certification",
    # Actions
    "TaskPropose",
    "TaskClaim",
    "ResourceSync",
    "StateNotify",
    # Discussion
    "DiscussionStart",
    "DiscussionReply",
    "DiscussionVote",
    "DiscussionConclude",
    "Consensus",
    "ActionItem",
    "ConsensusMode",
    "TimeoutAction",
    "ConclusionType",
    "DiscussionStateMachine",
    "DiscussionManager",
    # Emergency
    "EmergencyConfig",
    "EmergencyController",
    "create_emergency_controller",
    # Enclave
    "VaultEntry",
    "EnclaveInfo",
    "PlaybookRunInfo",
    "VaultProxy",
    "PlaybookRunProxy",
    "EnclaveProxy",
    "EnclaveManager",
]

__version__ = "0.9.6"
