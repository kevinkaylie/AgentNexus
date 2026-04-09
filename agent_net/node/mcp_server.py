"""
agent_net.node.mcp_server
MCP stdio 接口 —— 代理所有工具调用至 Node Daemon (localhost:8765)
"""
import asyncio
import json
import logging
import os
import uuid
import aiohttp
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logger = logging.getLogger(__name__)

DAEMON_URL = "http://localhost:8765"
app = Server("agent-net-node-mcp")

# 启动时从环境变量读取绑定 DID（由 node mcp --name/--did 注入）
_MY_DID: str = os.environ.get("AGENTNEXUS_MY_DID", "")

# Push registration state
_push_registration: dict = {}
_push_refresh_task: asyncio.Task | None = None


def _read_token() -> str:
    """从 data/daemon_token.txt 读取鉴权 Token（若文件不存在返回空串）"""
    try:
        from agent_net.common.constants import DAEMON_TOKEN_FILE
        if os.path.exists(DAEMON_TOKEN_FILE):
            with open(DAEMON_TOKEN_FILE, "r") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


def _auth_headers() -> dict:
    token = _read_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def _call(method: str, path: str, **kwargs) -> dict:
    headers = kwargs.pop("headers", {})
    if method in ("post", "patch", "put", "delete"):
        headers.update(_auth_headers())
    async with aiohttp.ClientSession() as session:
        fn = getattr(session, method)
        async with fn(f"{DAEMON_URL}{path}", headers=headers, **kwargs) as resp:
            return await resp.json()


@app.list_tools()
async def list_tools() -> list[Tool]:
    # 根据是否绑定 DID 动态调整描述，帮助 Claude 理解上下文
    bound_hint = f" (bound: {_MY_DID})" if _MY_DID else " (unbound — from_did required)"
    inbox_hint = f" (bound: {_MY_DID})" if _MY_DID else " (unbound — did required)"
    card_hint  = f" (omit did to return own card; bound: {_MY_DID})" if _MY_DID else ""

    return [
        Tool(name="whoami",
             description="Return the Agent DID and profile bound to this MCP instance. "
                         "Returns empty if not bound at startup.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="register_agent",
             description="Register a local Agent: auto-generate DID, persist private key, create signed card.",
             inputSchema={"type": "object",
                          "properties": {
                              "name": {"type": "string"},
                              "type": {"type": "string"},
                              "capabilities": {"type": "array", "items": {"type": "string"}},
                              "location": {"type": "string"},
                              "is_public": {"type": "boolean", "description": "Announce to federation seed relays"},
                              "description": {"type": "string", "description": "Card description"},
                              "tags": {"type": "array", "items": {"type": "string"}, "description": "Card tags"},
                          }, "required": ["name"]}),
        Tool(name="list_local_agents",
             description="List all Agents registered on this node.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="send_message",
             description=f"Send a message to a target DID (auto-routed){bound_hint}. "
                         "from_did can be omitted when bound. "
                         "session_id can be omitted for a new conversation (auto-generated). "
                         "reply_to is the message id this replies to.",
             inputSchema={"type": "object",
                          "properties": {
                              "from_did": {"type": "string",
                                           "description": "Sender DID; omit when bound"},
                              "to_did": {"type": "string"},
                              "content": {"type": "string"},
                              "session_id": {"type": "string",
                                             "description": "Conversation ID; omit to start new conversation"},
                              "reply_to": {"type": "integer",
                                           "description": "Message ID this replies to"},
                          }, "required": ["to_did", "content"]}),
        Tool(name="fetch_inbox",
             description=f"Fetch offline message inbox{inbox_hint}. did can be omitted when bound.",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string",
                                      "description": "DID to query; omit when bound"}
                          }}),
        Tool(name="search_agents",
             description="Search Agents by capability keyword.",
             inputSchema={"type": "object",
                          "properties": {"keyword": {"type": "string"}},
                          "required": ["keyword"]}),
        Tool(name="add_contact",
             description="Add a remote Agent to the local address book.",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string"},
                              "endpoint": {"type": "string"},
                              "relay": {"type": "string"},
                          }, "required": ["did", "endpoint"]}),
        Tool(name="get_stun_endpoint",
             description="Get the public IP and port of this node.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_pending_requests",
             description="List pending handshake requests awaiting approval.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="resolve_request",
             description="Approve or deny a pending handshake request; resumes the handshake on allow.",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string", "description": "DID of the pending request"},
                              "action": {"type": "string", "enum": ["allow", "deny"],
                                         "description": "allow = approve / deny = reject"},
                          }, "required": ["did", "action"]}),
        Tool(name="get_card",
             description=f"Get an Agent's signed NexusProfile card (Ed25519 signature, verifiable){card_hint}",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string",
                                      "description": "Target DID; omit to return own card (requires binding)"}
                          }}),
        Tool(name="update_card",
             description="Update Agent card fields (name/description/tags); signing done inside daemon, key never leaves. "
                         "did can be omitted when bound.",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string",
                                      "description": "Target DID; omit when bound"},
                              "name": {"type": "string"},
                              "description": {"type": "string"},
                              "tags": {"type": "array", "items": {"type": "string"}},
                          }}),
        Tool(name="get_session",
             description="Retrieve full conversation history for a session_id (includes all messages, both read and unread).",
             inputSchema={"type": "object",
                          "properties": {
                              "session_id": {"type": "string",
                                             "description": "The conversation session ID"},
                          }, "required": ["session_id"]}),
        Tool(name="certify_agent",
             description="Issue a certification for a target Agent. The issuer (this agent when bound) signs the claim with its private key. "
                         "issuer_did can be omitted when bound.",
             inputSchema={"type": "object",
                          "properties": {
                              "target_did": {"type": "string", "description": "DID of the agent to certify"},
                              "issuer_did": {"type": "string", "description": "DID of the issuer; omit when bound"},
                              "claim": {"type": "string", "description": "Certification claim (e.g. 'payment_verified', 'service_quality_A')"},
                              "evidence": {"type": "string", "description": "Supporting evidence (e.g. transaction hash, interaction count)"},
                          }, "required": ["target_did", "claim"]}),
        Tool(name="get_certifications",
             description="Get all certifications for an Agent. Each certification is independently signed by its issuer.",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string", "description": "Target DID; omit when bound to get own certifications"},
                          }}),
        Tool(name="export_agent",
             description="Export an Agent's identity (DID + private key + profile + certifications) as an encrypted bundle. "
                         "did can be omitted when bound.",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string", "description": "Agent DID; omit when bound"},
                              "password": {"type": "string", "description": "Password to encrypt the export bundle"},
                          }, "required": ["password"]}),
        Tool(name="import_agent",
             description="Import an Agent identity from an encrypted bundle (created by export_agent). "
                         "Restores DID, private key, profile and certifications.",
             inputSchema={"type": "object",
                          "properties": {
                              "data": {"type": "string", "description": "The encrypted bundle (JSON string from export_agent)"},
                              "password": {"type": "string", "description": "Password to decrypt the bundle"},
                          }, "required": ["data", "password"]}),
        # ========== v0.8 L7 协作层工具 ==========
        # Action Layer (4)
        Tool(name="propose_task",
             description=f"Propose/delegate a task to another Agent. Returns generated task_id for tracking."
                         f" Sender auto-filled as {_MY_DID}." if _MY_DID else "Propose/delegate a task to another Agent. Returns generated task_id for tracking.",
             inputSchema={"type": "object",
                          "properties": {
                              "to_did": {"type": "string", "description": "Target Agent DID"},
                              "title": {"type": "string", "description": "Task title"},
                              "description": {"type": "string", "description": "Detailed task description"},
                              "deadline": {"type": "string", "description": "Deadline (ISO date, e.g. 2026-04-10)"},
                              "required_caps": {"type": "array", "items": {"type": "string"},
                                                "description": "Required capabilities (e.g. ['Code', 'Review'])"},
                          }, "required": ["to_did", "title"]}),
        Tool(name="claim_task",
             description="Claim a task proposed by another Agent.",
             inputSchema={"type": "object",
                          "properties": {
                              "to_did": {"type": "string", "description": "Task proposer's DID"},
                              "task_id": {"type": "string", "description": "Task ID to claim"},
                              "eta": {"type": "string", "description": "Estimated completion time (e.g. '2h', '30min')"},
                              "message": {"type": "string", "description": "Optional message to proposer"},
                          }, "required": ["to_did", "task_id"]}),
        Tool(name="sync_resource",
             description="Share key-value data with another Agent (e.g. design docs, config, glossary).",
             inputSchema={"type": "object",
                          "properties": {
                              "to_did": {"type": "string", "description": "Target Agent DID"},
                              "key": {"type": "string", "description": "Resource key identifier"},
                              "value": {"type": "string", "description": "Resource value (use JSON string for complex data)"},
                              "version": {"type": "string", "description": "Version identifier (e.g. 'v2', '2026-04-06')"},
                          }, "required": ["to_did", "key", "value"]}),
        Tool(name="notify_state",
             description="Report task progress or status to another Agent.",
             inputSchema={"type": "object",
                          "properties": {
                              "to_did": {"type": "string", "description": "Target Agent DID"},
                              "status": {"type": "string",
                                         "enum": ["pending", "in_progress", "completed", "failed", "blocked"],
                                         "description": "Current status"},
                              "task_id": {"type": "string", "description": "Associated task ID"},
                              "progress": {"type": "number", "description": "Progress percentage 0.0-1.0"},
                              "error": {"type": "string", "description": "Error message (when status is 'failed')"},
                          }, "required": ["to_did", "status"]}),
        # Discussion (4)
        Tool(name="start_discussion",
             description="Start a multi-agent discussion with optional voting. "
                         "Sends invitation to all participants. Returns topic_id. "
                         "Note: reply/vote/conclude tools should use initiator's DID as to_did.",
             inputSchema={"type": "object",
                          "properties": {
                              "title": {"type": "string", "description": "Discussion title"},
                              "participants": {"type": "array", "items": {"type": "string"},
                                               "description": "List of participant DIDs to invite"},
                              "context": {"type": "string", "description": "Background context for the discussion"},
                              "consensus_mode": {"type": "string",
                                                 "enum": ["majority", "unanimous", "leader_decides"],
                                                 "description": "Voting mode (default: majority)"},
                              "timeout_seconds": {"type": "integer",
                                                  "description": "Voting timeout in seconds"},
                          }, "required": ["title", "participants"]}),
        Tool(name="reply_discussion",
             description="Reply to an ongoing discussion. to_did should be the discussion initiator's DID.",
             inputSchema={"type": "object",
                          "properties": {
                              "to_did": {"type": "string", "description": "Discussion initiator's DID"},
                              "topic_id": {"type": "string", "description": "Discussion topic ID"},
                              "content": {"type": "string", "description": "Reply content"},
                          }, "required": ["to_did", "topic_id", "content"]}),
        Tool(name="vote_discussion",
             description="Vote on a discussion topic. to_did should be the discussion initiator's DID.",
             inputSchema={"type": "object",
                          "properties": {
                              "to_did": {"type": "string", "description": "Discussion initiator's DID"},
                              "topic_id": {"type": "string", "description": "Discussion topic ID"},
                              "vote": {"type": "string", "enum": ["approve", "reject", "abstain"],
                                       "description": "Vote choice"},
                              "reason": {"type": "string", "description": "Reason for vote"},
                          }, "required": ["to_did", "topic_id", "vote"]}),
        Tool(name="conclude_discussion",
             description="Conclude a discussion with a final decision. Sends conclusion to target participant. "
                         "to_did should be a participant's DID (to notify them of the conclusion).",
             inputSchema={"type": "object",
                          "properties": {
                              "to_did": {"type": "string", "description": "Participant DID to send conclusion to"},
                              "topic_id": {"type": "string", "description": "Discussion topic ID"},
                              "conclusion": {"type": "string", "description": "Final conclusion text"},
                              "conclusion_type": {"type": "string",
                                                  "enum": ["consensus", "no_consensus", "escalated"],
                                                  "description": "Type of conclusion (default: consensus)"},
                          }, "required": ["to_did", "topic_id", "conclusion"]}),
        # Emergency + Skill (2)
        Tool(name="emergency_halt",
             description="Broadcast emergency halt to target Agent(s). Only works for Agents with active sessions. "
                         "Requires authorization via emergency_authorized_dids config.",
             inputSchema={"type": "object",
                          "properties": {
                              "to_did": {"type": "string", "description": "Target Agent DID (required for scope='agent' or 'task')"},
                              "scope": {"type": "string",
                                        "enum": ["agent", "task", "all"],
                                        "description": "agent: halt target DID; task: halt task-related agents; all: halt all active sessions"},
                              "task_id": {"type": "string", "description": "Task ID when scope='task'"},
                              "reason": {"type": "string", "description": "Reason for emergency halt"},
                          }, "required": ["scope"]}),
        Tool(name="list_skills",
             description="List registered Skills on this node. Filter by Agent or capability.",
             inputSchema={"type": "object",
                          "properties": {
                              "agent_did": {"type": "string", "description": "Filter by Agent DID"},
                              "capability": {"type": "string", "description": "Filter by capability keyword"},
                          }}),
        # Enclave (ADR-013) - 6 tools
        Tool(name="create_enclave",
             description="Create an Enclave (project team) with members, roles, and shared Vault.",
             inputSchema={"type": "object",
                          "properties": {
                              "name": {"type": "string", "description": "Enclave name (e.g. 'Login Feature Dev')"},
                              "members": {
                                  "type": "object",
                                  "description": "Role-to-DID mapping. Key=role name, value=object with did and optional handbook",
                                  "additionalProperties": {
                                      "type": "object",
                                      "properties": {
                                          "did": {"type": "string", "description": "Agent DID for this role"},
                                          "handbook": {"type": "string", "description": "Role responsibilities"},
                                          "permissions": {"type": "string", "enum": ["r", "rw", "admin"],
                                                          "description": "Default: rw"},
                                      },
                                      "required": ["did"],
                                  },
                              },
                              "vault_backend": {"type": "string", "enum": ["git", "local"],
                                                "description": "Vault storage backend (default: local)"},
                              "vault_config": {"type": "object",
                                               "description": "Backend-specific config. git: {repo_path, branch}. local: {}"},
                          }, "required": ["name", "members"]}),
        Tool(name="vault_get",
             description="Read a document from Enclave Vault. Returns content and version.",
             inputSchema={"type": "object",
                          "properties": {
                              "enclave_id": {"type": "string", "description": "Enclave ID"},
                              "key": {"type": "string", "description": "Document key (e.g. 'requirements', 'design_doc')"},
                              "version": {"type": "string", "description": "Specific version (omit for latest)"},
                              "author_did": {"type": "string", "description": "Requester DID (for permission check)"},
                          }, "required": ["enclave_id", "key"]}),
        Tool(name="vault_put",
             description="Write a document to Enclave Vault. Creates new or updates existing.",
             inputSchema={"type": "object",
                          "properties": {
                              "enclave_id": {"type": "string", "description": "Enclave ID"},
                              "key": {"type": "string", "description": "Document key"},
                              "value": {"type": "string", "description": "Document content (text or JSON string)"},
                              "message": {"type": "string",
                                          "description": "Change description (used as commit message for git backend)"},
                          }, "required": ["enclave_id", "key", "value"]}),
        Tool(name="vault_list",
             description="List documents in Enclave Vault.",
             inputSchema={"type": "object",
                          "properties": {
                              "enclave_id": {"type": "string", "description": "Enclave ID"},
                              "prefix": {"type": "string", "description": "Filter by key prefix (e.g. 'design_')"},
                              "author_did": {"type": "string", "description": "Requester DID (for permission check)"},
                          }, "required": ["enclave_id"]}),
        Tool(name="run_playbook",
             description="Start a Playbook in an Enclave. Automatically assigns tasks to role-bound Agents.",
             inputSchema={"type": "object",
                          "properties": {
                              "enclave_id": {"type": "string", "description": "Enclave ID"},
                              "playbook": {
                                  "type": "object",
                                  "description": "Playbook definition (inline) or playbook_id reference",
                                  "properties": {
                                      "playbook_id": {"type": "string",
                                                      "description": "Existing playbook ID (mutually exclusive with stages)"},
                                      "name": {"type": "string", "description": "Playbook name (for inline definition)"},
                                      "stages": {
                                          "type": "array",
                                          "description": "Stage definitions (for inline definition)",
                                          "items": {
                                              "type": "object",
                                              "properties": {
                                                  "name": {"type": "string"},
                                                  "role": {"type": "string"},
                                                  "description": {"type": "string"},
                                                  "input_keys": {"type": "array", "items": {"type": "string"}},
                                                  "output_key": {"type": "string"},
                                                  "next": {"type": "string"},
                                                  "on_reject": {"type": "string"},
                                                  "timeout_seconds": {"type": "integer"},
                                              },
                                              "required": ["name", "role"],
                                          },
                                      },
                                  },
                              },
                          }, "required": ["enclave_id", "playbook"]}),
        Tool(name="get_run_status",
             description="Get Playbook execution status for an Enclave.",
             inputSchema={"type": "object",
                          "properties": {
                              "enclave_id": {"type": "string", "description": "Enclave ID"},
                              "run_id": {"type": "string", "description": "Run ID (omit to get latest run)"},
                          }, "required": ["enclave_id"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        match name:
            case "whoami":
                if _MY_DID:
                    # 顺便拉一下名片，让 Claude 知道自己的完整信息
                    try:
                        card = await _call("get", f"/agents/{_MY_DID}/profile")
                        result = {"did": _MY_DID, "bound": True, "profile": card}
                    except Exception:
                        result = {"did": _MY_DID, "bound": True}
                else:
                    result = {"did": "", "bound": False,
                              "hint": "No DID bound. Start with 'python main.py node mcp --name <name>' to auto-bind."}

            case "register_agent":
                result = await _call("post", "/agents/register", json=arguments)

            case "list_local_agents":
                result = await _call("get", "/agents/local")

            case "send_message":
                if "from_did" not in arguments and not _MY_DID:
                    result = {"error": "No DID bound — provide from_did or start with --name"}
                else:
                    if "from_did" not in arguments:
                        arguments["from_did"] = _MY_DID
                    result = await _call("post", "/messages/send", json=arguments)

            case "fetch_inbox":
                did = arguments.get("did") or _MY_DID
                if not did:
                    result = {"error": "No DID bound — provide did or start with --name"}
                else:
                    result = await _call("get", f"/messages/inbox/{did}")

            case "search_agents":
                result = await _call("get", f"/agents/search/{arguments['keyword']}")

            case "add_contact":
                result = await _call("post", "/contacts/add", json=arguments)

            case "get_stun_endpoint":
                result = await _call("get", "/stun/endpoint")

            case "get_pending_requests":
                result = await _call("get", "/gate/pending")

            case "resolve_request":
                result = await _call("post", "/gate/resolve", json=arguments)

            case "get_card":
                did = arguments.get("did") or _MY_DID
                if not did:
                    result = {"error": "No DID bound — provide did parameter"}
                else:
                    result = await _call("get", f"/agents/{did}/profile")

            case "update_card":
                did = arguments.pop("did", None) or _MY_DID
                if not did:
                    result = {"error": "No DID bound — provide did or start with --name"}
                else:
                    result = await _call("patch", f"/agents/{did}/card", json=arguments)

            case "get_session":
                sid = arguments.get("session_id", "")
                if not sid:
                    result = {"error": "session_id is required"}
                else:
                    result = await _call("get", f"/messages/session/{sid}")

            case "certify_agent":
                issuer = arguments.get("issuer_did") or _MY_DID
                if not issuer:
                    result = {"error": "No DID bound — provide issuer_did or start with --name"}
                else:
                    target = arguments["target_did"]
                    result = await _call("post", f"/agents/{target}/certify", json={
                        "issuer_did": issuer,
                        "claim": arguments["claim"],
                        "evidence": arguments.get("evidence", ""),
                    })

            case "get_certifications":
                did = arguments.get("did") or _MY_DID
                if not did:
                    result = {"error": "No DID bound — provide did or start with --name"}
                else:
                    result = await _call("get", f"/agents/{did}/certifications")

            case "export_agent":
                did = arguments.get("did") or _MY_DID
                if not did:
                    result = {"error": "No DID bound — provide did or start with --name"}
                else:
                    password = arguments.get("password", "")
                    if not password:
                        result = {"error": "password is required for export_agent"}
                    else:
                        result = await _call("get", f"/agents/{did}/export",
                                             params={"password": password})

            case "import_agent":
                data = arguments.get("data", "")
                password = arguments.get("password", "")
                if not data or not password:
                    result = {"error": "data and password are required for import_agent"}
                else:
                    result = await _call("post", "/agents/import",
                                         json={"data": data, "password": password})

            # ========== v0.8 L7 协作层工具 ==========
            # Action Layer (4)
            case "propose_task":
                if not _MY_DID:
                    result = {"error": "No DID bound — start with --name"}
                else:
                    task_id = f"task_{uuid.uuid4().hex}"
                    content = {"task_id": task_id, "title": arguments["title"]}
                    for key in ("description", "deadline", "required_caps"):
                        if arguments.get(key):
                            content[key] = arguments[key]
                    await _call("post", "/messages/send", json={
                        "from_did": _MY_DID,
                        "to_did": arguments["to_did"],
                        "content": content,
                        "message_type": "task_propose",
                        "protocol": "nexus_v1",
                    })
                    result = {"status": "ok", "task_id": task_id}

            case "claim_task":
                if not _MY_DID:
                    result = {"error": "No DID bound — start with --name"}
                else:
                    content = {"task_id": arguments["task_id"]}
                    for key in ("eta", "message"):
                        if arguments.get(key):
                            content[key] = arguments[key]
                    await _call("post", "/messages/send", json={
                        "from_did": _MY_DID,
                        "to_did": arguments["to_did"],
                        "content": content,
                        "message_type": "task_claim",
                        "protocol": "nexus_v1",
                    })
                    result = {"status": "ok", "task_id": arguments["task_id"]}

            case "sync_resource":
                if not _MY_DID:
                    result = {"error": "No DID bound — start with --name"}
                else:
                    content = {"key": arguments["key"], "value": arguments["value"]}
                    if arguments.get("version"):
                        content["version"] = arguments["version"]
                    await _call("post", "/messages/send", json={
                        "from_did": _MY_DID,
                        "to_did": arguments["to_did"],
                        "content": content,
                        "message_type": "resource_sync",
                        "protocol": "nexus_v1",
                    })
                    result = {"status": "ok", "key": arguments["key"]}

            case "notify_state":
                if not _MY_DID:
                    result = {"error": "No DID bound — start with --name"}
                else:
                    content = {"status": arguments["status"]}
                    for key in ("task_id", "progress", "error"):
                        if arguments.get(key):
                            content[key] = arguments[key]
                    await _call("post", "/messages/send", json={
                        "from_did": _MY_DID,
                        "to_did": arguments["to_did"],
                        "content": content,
                        "message_type": "state_notify",
                        "protocol": "nexus_v1",
                    })
                    result = {"status": "ok"}

            # Discussion (4)
            case "start_discussion":
                if not _MY_DID:
                    result = {"error": "No DID bound — start with --name"}
                else:
                    topic_id = f"topic_{uuid.uuid4().hex}"
                    participants = arguments["participants"]
                    content = {
                        "topic_id": topic_id,
                        "title": arguments["title"],
                        "participants": participants,
                        "seq": 1,
                    }
                    if arguments.get("context"):
                        content["context"] = arguments["context"]
                    if arguments.get("consensus_mode"):
                        content["consensus"] = {"mode": arguments["consensus_mode"]}
                        if arguments.get("timeout_seconds"):
                            content["consensus"]["timeout_seconds"] = arguments["timeout_seconds"]
                    # 向每个参与者发送
                    notified = []
                    for did in participants:
                        try:
                            await _call("post", "/messages/send", json={
                                "from_did": _MY_DID,
                                "to_did": did,
                                "content": content,
                                "message_type": "discussion_start",
                                "protocol": "nexus_v1",
                            })
                            notified.append(did)
                        except Exception as e:
                            logger.warning(f"Failed to notify {did}: {e}")
                    result = {"status": "ok", "topic_id": topic_id, "notified": notified}

            case "reply_discussion":
                if not _MY_DID:
                    result = {"error": "No DID bound — start with --name"}
                else:
                    content = {
                        "topic_id": arguments["topic_id"],
                        "content": arguments["content"],
                    }
                    await _call("post", "/messages/send", json={
                        "from_did": _MY_DID,
                        "to_did": arguments["to_did"],
                        "content": content,
                        "message_type": "discussion_reply",
                        "protocol": "nexus_v1",
                    })
                    result = {"status": "ok", "topic_id": arguments["topic_id"]}

            case "vote_discussion":
                if not _MY_DID:
                    result = {"error": "No DID bound — start with --name"}
                else:
                    content = {
                        "topic_id": arguments["topic_id"],
                        "vote": arguments["vote"],
                    }
                    if arguments.get("reason"):
                        content["reason"] = arguments["reason"]
                    await _call("post", "/messages/send", json={
                        "from_did": _MY_DID,
                        "to_did": arguments["to_did"],
                        "content": content,
                        "message_type": "discussion_vote",
                        "protocol": "nexus_v1",
                    })
                    result = {"status": "ok", "topic_id": arguments["topic_id"], "vote": arguments["vote"]}

            case "conclude_discussion":
                if not _MY_DID:
                    result = {"error": "No DID bound — start with --name"}
                else:
                    content = {
                        "topic_id": arguments["topic_id"],
                        "conclusion": arguments["conclusion"],
                    }
                    if arguments.get("conclusion_type"):
                        content["conclusion_type"] = arguments["conclusion_type"]
                    await _call("post", "/messages/send", json={
                        "from_did": _MY_DID,
                        "to_did": arguments["to_did"],
                        "content": content,
                        "message_type": "discussion_conclude",
                        "protocol": "nexus_v1",
                    })
                    result = {"status": "ok", "topic_id": arguments["topic_id"]}

            # Emergency + Skill (2)
            case "emergency_halt":
                if not _MY_DID:
                    result = {"error": "No DID bound — start with --name"}
                else:
                    scope = arguments.get("scope", "agent")
                    content = {
                        "scope": scope,
                        "reason": arguments.get("reason", ""),
                    }
                    if scope == "agent" and arguments.get("to_did"):
                        content["target"] = arguments["to_did"]
                    if scope == "task" and arguments.get("task_id"):
                        content["task_id"] = arguments["task_id"]
                    await _call("post", "/messages/send", json={
                        "from_did": _MY_DID,
                        "to_did": arguments.get("to_did", _MY_DID),  # scope=all 时发给自己
                        "content": content,
                        "message_type": "emergency_halt",
                        "protocol": "nexus_v1",
                    })
                    result = {"status": "ok", "scope": scope}

            case "list_skills":
                params = {}
                if arguments.get("agent_did"):
                    params["agent_did"] = arguments["agent_did"]
                if arguments.get("capability"):
                    params["capability"] = arguments["capability"]
                result = await _call("get", "/skills", params=params if params else None)

            # Enclave (ADR-013) - 6 tools
            case "create_enclave":
                if not _MY_DID:
                    result = {"error": "No DID bound — start with --name"}
                else:
                    result = await _call("post", "/enclaves", json={
                        "owner_did": _MY_DID,
                        **arguments,
                    })

            case "vault_get":
                enclave_id = arguments["enclave_id"]
                key = arguments["key"]
                params = {}
                if arguments.get("version"):
                    params["version"] = arguments["version"]
                if arguments.get("author_did"):
                    params["author_did"] = arguments["author_did"]
                elif _MY_DID:
                    params["author_did"] = _MY_DID
                result = await _call("get", f"/enclaves/{enclave_id}/vault/{key}",
                                     params=params if params else None)

            case "vault_put":
                if not _MY_DID:
                    result = {"error": "No DID bound — start with --name"}
                else:
                    enclave_id = arguments["enclave_id"]
                    key = arguments["key"]
                    result = await _call("put", f"/enclaves/{enclave_id}/vault/{key}", json={
                        "value": arguments["value"],
                        "author_did": _MY_DID,
                        "message": arguments.get("message", ""),
                    })

            case "vault_list":
                enclave_id = arguments["enclave_id"]
                params = {}
                if arguments.get("prefix"):
                    params["prefix"] = arguments["prefix"]
                if arguments.get("author_did"):
                    params["author_did"] = arguments["author_did"]
                elif _MY_DID:
                    params["author_did"] = _MY_DID
                result = await _call("get", f"/enclaves/{enclave_id}/vault",
                                     params=params if params else None)

            case "run_playbook":
                enclave_id = arguments["enclave_id"]
                result = await _call("post", f"/enclaves/{enclave_id}/runs", json={
                    "playbook": arguments.get("playbook"),
                    "playbook_id": arguments.get("playbook_id"),
                })

            case "get_run_status":
                enclave_id = arguments["enclave_id"]
                run_id = arguments.get("run_id")
                if run_id:
                    result = await _call("get", f"/enclaves/{enclave_id}/runs/{run_id}")
                else:
                    # 省略 run_id 时获取最新 run
                    result = await _call("get", f"/enclaves/{enclave_id}/runs")

            case _:
                result = {"error": f"Unknown tool: {name}"}

    except Exception as e:
        result = {"error": str(e)}
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


# ── Push Registration (v0.9) ─────────────────────────────────────

async def _register_push():
    """Register push callback for this MCP instance."""
    global _push_registration, _push_refresh_task

    if not _MY_DID:
        logger.warning("No DID bound, skipping push registration")
        return

    try:
        # Use a local callback URL (MCP process can listen on this port)
        callback_url = "http://127.0.0.1:18765/push/callback"

        result = await _call("post", "/push/register", json={
            "did": _MY_DID,
            "callback_url": callback_url,
            "callback_type": "webhook",
            "expires": 3600,
        })

        if result.get("status") == "ok":
            _push_registration = {
                "registration_id": result["registration_id"],
                "callback_secret": result["callback_secret"],
                "expires_at": result["expires_at"],
            }
            logger.info(f"Push registered: {result['registration_id']}")

            # Start refresh task (refresh every 30 minutes)
            if _push_refresh_task:
                _push_refresh_task.cancel()
            _push_refresh_task = asyncio.create_task(_push_refresh_loop())
    except Exception as e:
        logger.warning(f"Push registration failed: {e}")


async def _push_refresh_loop():
    """Background task to refresh push registration."""
    # 续约间隔 = expires // 2（推荐做法）
    expires_seconds = 3600
    refresh_interval = expires_seconds // 2  # 1800 秒 = 30 分钟

    while _MY_DID:
        await asyncio.sleep(refresh_interval)
        try:
            result = await _call("post", "/push/refresh", json={
                "did": _MY_DID,
                "callback_url": "http://127.0.0.1:18765/push/callback",
                "callback_type": "webhook",
                "expires": expires_seconds,
            })
            if result.get("status") == "ok":
                logger.debug("Push registration refreshed")
        except Exception as e:
            logger.warning(f"Push refresh failed: {e}")


async def _unregister_push():
    """Unregister push callback."""
    global _push_registration, _push_refresh_task

    if _push_refresh_task:
        _push_refresh_task.cancel()
        _push_refresh_task = None

    if _MY_DID:
        try:
            await _call("delete", f"/push/{_MY_DID}")
            logger.info("Push unregistered")
        except Exception as e:
            logger.warning(f"Push unregister failed: {e}")

    _push_registration = {}


async def main():
    # Register push on startup if DID is bound
    if _MY_DID:
        asyncio.create_task(_register_push())

    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        # Cleanup on exit
        if _MY_DID:
            await _unregister_push()


if __name__ == "__main__":
    asyncio.run(main())
