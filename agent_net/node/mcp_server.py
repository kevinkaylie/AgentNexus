"""
agent_net.node.mcp_server
MCP stdio 接口 —— 代理所有工具调用至 Node Daemon (localhost:8765)
"""
import asyncio
import json
import os
import aiohttp
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

DAEMON_URL = "http://localhost:8765"
app = Server("agent-net-node-mcp")

# 启动时从环境变量读取绑定 DID（由 node mcp --name/--did 注入）
_MY_DID: str = os.environ.get("AGENTNEXUS_MY_DID", "")


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

            case _:
                result = {"error": f"Unknown tool: {name}"}

    except Exception as e:
        result = {"error": str(e)}
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
