import asyncio
import os
import sys

from .common import _usage

# ── node 子命令 ───────────────────────────────────────────

def node_start():
    from agent_net.node.daemon import run
    print("[AgentNet] Starting Node Daemon on :8765 ...")
    run()


async def _mcp_bind_agent(name: str | None, did: str | None,
                           caps: list, desc: str, tags: list, public: bool) -> str:
    """
    注册或查找 Agent，返回绑定的 DID。
    - 指定 --did：验证存在后直接绑定
    - 指定 --name：同名已有则复用，否则注册新 Agent（幂等）
    所有输出写 stderr，不污染 MCP stdio 协议通道。
    """
    import aiohttp
    from agent_net.common.constants import DAEMON_TOKEN_FILE

    token = ""
    if os.path.exists(DAEMON_TOKEN_FILE):
        with open(DAEMON_TOKEN_FILE) as f:
            token = f.read().strip()
    auth = {"Authorization": f"Bearer {token}"} if token else {}
    base = "http://localhost:8765"

    try:
        async with aiohttp.ClientSession() as s:

            # ── 按 DID 绑定 ──────────────────────────────
            if did:
                async with s.get(f"{base}/agents/{did}/profile") as r:
                    if r.status == 200:
                        print(f"[AgentNexus MCP] Bound existing DID: {did}", file=sys.stderr)
                        return did
                    print(f"[AgentNexus MCP] Error: DID not found {did} (status {r.status})",
                          file=sys.stderr)
                    sys.exit(1)

            # ── 按名称查找或注册 ─────────────────────────
            if name:
                # 先查找同名已有 Agent
                async with s.get(f"{base}/agents/local") as r:
                    if r.status == 200:
                        data = await r.json()
                        for a in data.get("agents", []):
                            if a.get("profile", {}).get("name") == name:
                                existing = a["did"]
                                print(f"[AgentNexus MCP] Reusing existing agent '{name}' -> {existing}",
                                      file=sys.stderr)
                                return existing

                # 未找到，注册新 Agent
                payload = {
                    "name": name,
                    "capabilities": caps,
                    "description": desc,
                    "tags": tags,
                    "is_public": public,
                }
                async with s.post(f"{base}/agents/register", json=payload, headers=auth) as r:
                    if r.status == 200:
                        new_did = (await r.json())["did"]
                        print(f"[AgentNexus MCP] Registered '{name}' -> {new_did}", file=sys.stderr)
                        return new_did
                    text = await r.text()
                    print(f"[AgentNexus MCP] Registration failed {r.status}: {text}", file=sys.stderr)
                    sys.exit(1)

    except aiohttp.ClientConnectorError:
        print("[AgentNexus MCP] Error: cannot connect to Node Daemon. Run: python main.py node start",
              file=sys.stderr)
        sys.exit(1)

    print("[AgentNexus MCP] Error: --name or --did is required", file=sys.stderr)
    sys.exit(1)


def node_mcp(name: str | None = None, did: str | None = None,
             caps: list | None = None, desc: str = "",
             tags: list | None = None, public: bool = False):
    """启动 MCP Server，可选绑定 Agent 身份（--name 自动注册/复用，--did 绑定已有）"""
    if name or did:
        bound_did = asyncio.run(
            _mcp_bind_agent(name, did, caps or [], desc, tags or [], public)
        )
        os.environ["AGENTNEXUS_MY_DID"] = bound_did
        print(f"[AgentNexus MCP] Bound DID: {bound_did}", file=sys.stderr)

    from agent_net.node.mcp_server import main as mcp_main
    asyncio.run(mcp_main())


async def node_demo():
    from agent_net.storage import init_db, fetch_inbox
    from agent_net.common.did import DIDGenerator, AgentProfile
    from agent_net.router import router

    await init_db()

    alice = DIDGenerator.create_new("demo_alice")
    bob = DIDGenerator.create_new("demo_bob")

    from agent_net.storage import register_agent
    await register_agent(alice.did, AgentProfile(
        id=alice.did, name="Demo Alice", capabilities=["Chat"]).to_dict(), is_local=True)
    await register_agent(bob.did, AgentProfile(
        id=bob.did, name="Demo Bob", capabilities=["ETC_Settlement"]).to_dict(), is_local=True)

    router.register_local_session(alice.did)
    router.register_local_session(bob.did)

    print(f"[Demo] Alice: {alice.did}")
    print(f"[Demo] Bob  : {bob.did}")

    result = await router.route_message(alice.did, bob.did, "Hello Bob!")
    print(f"[Demo] Alice->Bob: {result}")

    msg = await router.receive(bob.did)
    print(f"[Demo] Bob received: {msg}")

    router.unregister_local_session(bob.did)
    result2 = await router.route_message(alice.did, bob.did, "Bob is offline, this is an offline message.")
    print(f"[Demo] Alice->Bob(offline): {result2}")

    inbox = await fetch_inbox(bob.did)
    print(f"[Demo] Bob inbox: {inbox}")


async def node_gate_cmd(args: list[str]):
    """node whitelist/blacklist/mode/status/resolve 子命令处理"""
    from agent_net.storage import init_db, list_pending
    from agent_net.node.gatekeeper import gatekeeper, load_mode, save_mode

    await init_db()

    if not args:
        _usage()

    sub = args[0]

    # ── node status [--pending] ────────────────────────────
    if sub == "status":
        pending_only = "--pending" in args
        items = await list_pending()
        if pending_only or items:
            print(f"Pending requests ({len(items)}):")
            if not items:
                print("  (none)")
            for it in items:
                import datetime
                dt = datetime.datetime.fromtimestamp(it["requested_at"]).strftime("%Y-%m-%d %H:%M:%S")
                print(f"  DID: {it['did']}  time: {dt}")
        if not pending_only:
            mode = load_mode()
            print(f"Access control mode: {mode}")
            wl = gatekeeper.whitelist_all()
            bl = gatekeeper.blacklist_all()
            print(f"Whitelist: {wl or '(empty)'}")
            print(f"Blacklist: {bl or '(empty)'}")

    # ── node mode set <mode> ───────────────────────────────
    elif sub == "mode":
        if len(args) < 3 or args[1] != "set":
            print("Usage: node mode set <public|ask|private>"); return
        mode = args[2]
        if mode not in ("public", "ask", "private"):
            print("mode must be one of: public / ask / private"); return
        save_mode(mode)
        print(f"Access control mode set to: {mode}")

    # ── node whitelist add/remove/list <did> ──────────────
    elif sub == "whitelist":
        action = args[1] if len(args) > 1 else ""
        if action == "add":
            did = args[2] if len(args) > 2 else ""
            if not did: print("Usage: node whitelist add <did>"); return
            gatekeeper.whitelist_add(did)
            print(f"Added to whitelist: {did}")
        elif action == "remove":
            did = args[2] if len(args) > 2 else ""
            if not did: print("Usage: node whitelist remove <did>"); return
            gatekeeper.whitelist_remove(did)
            print(f"Removed from whitelist: {did}")
        elif action == "list":
            wl = gatekeeper.whitelist_all()
            print("Whitelist:" if wl else "Whitelist: (empty)")
            for d in wl:
                print(f"  {d}")
        else:
            print("Usage: node whitelist <add|remove|list> [did]")

    # ── node blacklist add/remove/list <did> ──────────────
    elif sub == "blacklist":
        action = args[1] if len(args) > 1 else ""
        if action == "add":
            did = args[2] if len(args) > 2 else ""
            if not did: print("Usage: node blacklist add <did>"); return
            gatekeeper.blacklist_add(did)
            print(f"Added to blacklist: {did}")
        elif action == "remove":
            did = args[2] if len(args) > 2 else ""
            if not did: print("Usage: node blacklist remove <did>"); return
            gatekeeper.blacklist_remove(did)
            print(f"Removed from blacklist: {did}")
        elif action == "list":
            bl = gatekeeper.blacklist_all()
            print("Blacklist:" if bl else "Blacklist: (empty)")
            for d in bl:
                print(f"  {d}")
        else:
            print("Usage: node blacklist <add|remove|list> [did]")

    # ── node resolve <did> <allow|deny> ───────────────────
    elif sub == "resolve":
        if len(args) < 3:
            print("Usage: node resolve <did> <allow|deny>"); return
        did, action = args[1], args[2]
        if action not in ("allow", "deny"):
            print("action must be 'allow' or 'deny'"); return
        ok = await gatekeeper.resolve(did, action)
        if ok:
            print(f"{action}: {did}")
        else:
            print(f"No pending request found for: {did}")

    else:
        print(f"Unknown node subcommand: '{sub}'")
        _usage()



__all__ = [name for name in globals() if not name.startswith("__")]
