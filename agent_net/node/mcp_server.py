"""
agent_net.node.mcp_server
MCP stdio 接口 —— 代理所有工具调用至 Node Daemon (localhost:8765)
"""
import asyncio
import json
import aiohttp
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

DAEMON_URL = "http://localhost:8765"
app = Server("agent-net-node-mcp")


async def _call(method: str, path: str, **kwargs) -> dict:
    async with aiohttp.ClientSession() as session:
        fn = getattr(session, method)
        async with fn(f"{DAEMON_URL}{path}", **kwargs) as resp:
            return await resp.json()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="register_agent",
             description="注册本地Agent，分配DID和Profile",
             inputSchema={"type": "object",
                          "properties": {
                              "name": {"type": "string"},
                              "type": {"type": "string"},
                              "capabilities": {"type": "array", "items": {"type": "string"}},
                              "location": {"type": "string"},
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
