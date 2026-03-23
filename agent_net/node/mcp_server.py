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
    return [
        Tool(name="register_agent",
             description="注册本地Agent，自动生成DID、持久化私钥、生成签名名片",
             inputSchema={"type": "object",
                          "properties": {
                              "name": {"type": "string"},
                              "type": {"type": "string"},
                              "capabilities": {"type": "array", "items": {"type": "string"}},
                              "location": {"type": "string"},
                              "is_public": {"type": "boolean", "description": "是否向联邦种子站公开"},
                              "description": {"type": "string", "description": "名片描述"},
                              "tags": {"type": "array", "items": {"type": "string"}, "description": "名片标签"},
                          }, "required": ["name"]}),
        Tool(name="list_local_agents",
             description="列出本节点所有已注册Agent",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="send_message",
             description="向目标DID发送消息（自动路由）",
             inputSchema={"type": "object",
                          "properties": {
                              "from_did": {"type": "string"},
                              "to_did": {"type": "string"},
                              "content": {"type": "string"},
                          }, "required": ["from_did", "to_did", "content"]}),
        Tool(name="fetch_inbox",
             description="获取离线消息收件箱",
             inputSchema={"type": "object",
                          "properties": {"did": {"type": "string"}},
                          "required": ["did"]}),
        Tool(name="search_agents",
             description="按能力关键词搜索Agent",
             inputSchema={"type": "object",
                          "properties": {"keyword": {"type": "string"}},
                          "required": ["keyword"]}),
        Tool(name="add_contact",
             description="添加远程Agent通讯录条目",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string"},
                              "endpoint": {"type": "string"},
                              "relay": {"type": "string"},
                          }, "required": ["did", "endpoint"]}),
        Tool(name="get_stun_endpoint",
             description="获取本节点公网IP和端口",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_pending_requests",
             description="查看待审批的握手请求列表",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="resolve_request",
             description="审批握手请求，批准后自动恢复握手流程",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string", "description": "待审批的DID"},
                              "action": {"type": "string", "enum": ["allow", "deny"],
                                         "description": "allow=批准 / deny=拒绝"},
                          }, "required": ["did", "action"]}),
        Tool(name="get_card",
             description="获取指定Agent的NexusProfile签名名片（含Ed25519签名，可验签）",
             inputSchema={"type": "object",
                          "properties": {"did": {"type": "string"}},
                          "required": ["did"]}),
        Tool(name="update_card",
             description="更新Agent名片字段（name/description/tags），签名在daemon内完成，私钥不出户",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string"},
                              "name": {"type": "string"},
                              "description": {"type": "string"},
                              "tags": {"type": "array", "items": {"type": "string"}},
                          }, "required": ["did"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        match name:
            case "register_agent":
                result = await _call("post", "/agents/register", json=arguments)
            case "list_local_agents":
                result = await _call("get", "/agents/local")
            case "send_message":
                result = await _call("post", "/messages/send", json=arguments)
            case "fetch_inbox":
                result = await _call("get", f"/messages/inbox/{arguments['did']}")
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
                result = await _call("get", f"/agents/{arguments['did']}/profile")
            case "update_card":
                did = arguments.pop("did")
                result = await _call("patch", f"/agents/{did}/card", json=arguments)
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
