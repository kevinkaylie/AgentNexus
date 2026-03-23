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
    bound_hint = f"（当前绑定：{_MY_DID}）" if _MY_DID else "（未绑定，需显式提供 from_did）"
    inbox_hint = f"（当前绑定：{_MY_DID}）" if _MY_DID else "（未绑定，需显式提供 did）"
    card_hint  = f"（省略 did 则返回自身名片，当前：{_MY_DID}）" if _MY_DID else ""

    return [
        Tool(name="whoami",
             description="返回当前 MCP 实例绑定的 Agent DID 和名片信息。"
                         "启动时未绑定则返回空。",
             inputSchema={"type": "object", "properties": {}}),
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
             description=f"向目标DID发送消息（自动路由）{bound_hint}。"
                         "已绑定时 from_did 可省略，自动使用绑定 DID。",
             inputSchema={"type": "object",
                          "properties": {
                              "from_did": {"type": "string",
                                           "description": "发送方DID，绑定模式下可省略"},
                              "to_did": {"type": "string"},
                              "content": {"type": "string"},
                          }, "required": ["to_did", "content"]}),
        Tool(name="fetch_inbox",
             description=f"获取离线消息收件箱{inbox_hint}。已绑定时 did 可省略。",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string",
                                      "description": "要查询的DID，绑定模式下可省略"}
                          }}),
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
             description=f"获取Agent的NexusProfile签名名片（含Ed25519签名，可验签）{card_hint}",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string",
                                      "description": "目标DID，省略则返回自身名片（需已绑定）"}
                          }}),
        Tool(name="update_card",
             description="更新Agent名片字段（name/description/tags），签名在daemon内完成，私钥不出户。"
                         "已绑定时 did 可省略。",
             inputSchema={"type": "object",
                          "properties": {
                              "did": {"type": "string",
                                      "description": "目标DID，绑定模式下可省略"},
                              "name": {"type": "string"},
                              "description": {"type": "string"},
                              "tags": {"type": "array", "items": {"type": "string"}},
                          }}),
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
                              "hint": "未绑定 DID。使用 'python main.py node mcp --name <name>' 启动可自动绑定。"}

            case "register_agent":
                result = await _call("post", "/agents/register", json=arguments)

            case "list_local_agents":
                result = await _call("get", "/agents/local")

            case "send_message":
                if "from_did" not in arguments and not _MY_DID:
                    result = {"error": "未绑定 DID，请提供 from_did 参数，或使用 --name 启动 MCP"}
                else:
                    if "from_did" not in arguments:
                        arguments["from_did"] = _MY_DID
                    result = await _call("post", "/messages/send", json=arguments)

            case "fetch_inbox":
                did = arguments.get("did") or _MY_DID
                if not did:
                    result = {"error": "未绑定 DID，请提供 did 参数，或使用 --name 启动 MCP"}
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
                    result = {"error": "未绑定 DID，请提供 did 参数"}
                else:
                    result = await _call("get", f"/agents/{did}/profile")

            case "update_card":
                did = arguments.pop("did", None) or _MY_DID
                if not did:
                    result = {"error": "未绑定 DID，请提供 did 参数，或使用 --name 启动 MCP"}
                else:
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
