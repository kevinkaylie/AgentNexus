"""
Communication MCP Server - 通过MCP协议向LLM暴露AgentNet工具集
"""
import asyncio
import json
import aiohttp
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

DAEMON_URL = "http://localhost:8765"

app = Server("agent-net-mcp")


async def _call(method: str, path: str, **kwargs) -> dict:
    async with aiohttp.ClientSession() as session:
        fn = getattr(session, method)
        async with fn(f"{DAEMON_URL}{path}", **kwargs) as resp:
            return await resp.json()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="register_agent",
            description="注册一个本地Agent，分配DID和Profile名片",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Agent名称"},
                    "type": {"type": "string", "description": "Agent类型，默认GeneralAgent"},
                    "capabilities": {"type": "array", "items": {"type": "string"}, "description": "能力标签列表"},
                    "location": {"type": "string", "description": "地理位置"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="list_local_agents",
            description="列出当前节点上所有已注册的本地Agent",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="send_message",
            description="向目标DID发送消息，自动选择本地/P2P/Relay/离线路由",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_did": {"type": "string", "description": "发送方DID"},
                    "to_did": {"type": "string", "description": "接收方DID"},
                    "content": {"type": "string", "description": "消息内容"},
                },
                "required": ["from_did", "to_did", "content"],
            },
        ),
        Tool(
            name="fetch_inbox",
            description="获取指定DID的离线消息收件箱",
            inputSchema={
                "type": "object",
                "properties": {
                    "did": {"type": "string", "description": "目标Agent的DID"},
                },
                "required": ["did"],
            },
        ),
        Tool(
            name="search_agents",
            description="通过能力关键词搜索匹配的Agent（如'Bank'、'ETC'）",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["keyword"],
            },
        ),
        Tool(
            name="get_stun_endpoint",
            description="获取当前节点的公网IP和端口（STUN探测结果）",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="add_contact",
            description="添加或更新通讯录中的远程Agent端点信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "did": {"type": "string", "description": "远程Agent的DID"},
                    "endpoint": {"type": "string", "description": "远程节点HTTP端点"},
                    "relay": {"type": "string", "description": "中转服务器地址（可选）"},
                },
                "required": ["did", "endpoint"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "register_agent":
            result = await _call("post", "/agents/register", json=arguments)
        elif name == "list_local_agents":
            result = await _call("get", "/agents/local")
        elif name == "send_message":
            result = await _call("post", "/messages/send", json=arguments)
        elif name == "fetch_inbox":
            did = arguments["did"]
            result = await _call("get", f"/messages/inbox/{did}")
        elif name == "search_agents":
            keyword = arguments["keyword"]
            result = await _call("get", f"/agents/search/{keyword}")
        elif name == "get_stun_endpoint":
            result = await _call("get", "/stun/endpoint")
        elif name == "add_contact":
            result = await _call("post", "/contacts/add", json=arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as e:
        result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
