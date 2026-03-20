#!/usr/bin/env python
"""
AgentNexus CLI

用法:
  agent-nexus node start                      启动本地节点 Daemon (:8765)
  agent-nexus node mcp                        启动节点 MCP Server (stdio)
  agent-nexus node demo                       本地功能演示
  agent-nexus node status [--pending]         查看节点状态（--pending 只看待审批请求）
  agent-nexus node mode set <public|ask|private>  设置访问控制模式
  agent-nexus node whitelist add    <did>     加入白名单
  agent-nexus node whitelist remove <did>     移出白名单
  agent-nexus node whitelist list             查看白名单
  agent-nexus node blacklist add    <did>     加入黑名单
  agent-nexus node blacklist remove <did>     移出黑名单
  agent-nexus node blacklist list             查看黑名单
  agent-nexus node resolve <did> <allow|deny> 审批 PENDING 握手请求

  agent-nexus relay start               启动公网信令/中转服务器 (:9000)

  agent-nexus agent list                列出所有本地 Agent
  agent-nexus agent get   <did>         查看指定 Agent 详情
  agent-nexus agent add   <name> [opts] 新建 Agent
    --type <type>                         类型，默认 GeneralAgent
    --caps <cap1,cap2,...>                能力标签（逗号分隔）
    --location <loc>                      地理位置
  agent-nexus agent update <did> [opts] 更新 Agent 字段
    --name <name>
    --type <type>
    --caps <cap1,cap2,...>               覆盖能力标签
    --location <loc>
  agent-nexus agent delete <did>        删除指定 Agent
  agent-nexus agent search <keyword>    按能力关键词搜索

  agent-nexus test                      运行全部测试用例
"""
import sys
import asyncio


def _usage():
    print(__doc__)
    sys.exit(1)


# ── node 子命令 ───────────────────────────────────────────

def node_start():
    from agent_net.node.daemon import run
    print("[AgentNet] Starting Node Daemon on :8765 ...")
    run()


def node_mcp():
    from agent_net.node.mcp_server import main
    print("[AgentNet] Starting Node MCP Server (stdio) ...")
    asyncio.run(main())


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
    result2 = await router.route_message(alice.did, bob.did, "Bob你离线了，这是离线消息。")
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
            print(f"待审批请求 ({len(items)} 条):")
            if not items:
                print("  (无)")
            for it in items:
                import datetime
                dt = datetime.datetime.fromtimestamp(it["requested_at"]).strftime("%Y-%m-%d %H:%M:%S")
                print(f"  DID: {it['did']}  时间: {dt}")
        if not pending_only:
            mode = load_mode()
            print(f"访问控制模式: {mode}")
            wl = gatekeeper.whitelist_all()
            bl = gatekeeper.blacklist_all()
            print(f"白名单: {wl or '(空)'}")
            print(f"黑名单: {bl or '(空)'}")

    # ── node mode set <mode> ───────────────────────────────
    elif sub == "mode":
        if len(args) < 3 or args[1] != "set":
            print("用法: node mode set <public|ask|private>"); return
        mode = args[2]
        if mode not in ("public", "ask", "private"):
            print("mode 必须是 public / ask / private"); return
        save_mode(mode)
        print(f"访问控制模式已设置为: {mode}")

    # ── node whitelist add/remove/list <did> ──────────────
    elif sub == "whitelist":
        action = args[1] if len(args) > 1 else ""
        if action == "add":
            did = args[2] if len(args) > 2 else ""
            if not did: print("用法: node whitelist add <did>"); return
            gatekeeper.whitelist_add(did)
            print(f"已加入白名单: {did}")
        elif action == "remove":
            did = args[2] if len(args) > 2 else ""
            if not did: print("用法: node whitelist remove <did>"); return
            gatekeeper.whitelist_remove(did)
            print(f"已移出白名单: {did}")
        elif action == "list":
            wl = gatekeeper.whitelist_all()
            print("白名单:" if wl else "白名单: (空)")
            for d in wl:
                print(f"  {d}")
        else:
            print("用法: node whitelist <add|remove|list> [did]")

    # ── node blacklist add/remove/list <did> ──────────────
    elif sub == "blacklist":
        action = args[1] if len(args) > 1 else ""
        if action == "add":
            did = args[2] if len(args) > 2 else ""
            if not did: print("用法: node blacklist add <did>"); return
            gatekeeper.blacklist_add(did)
            print(f"已加入黑名单: {did}")
        elif action == "remove":
            did = args[2] if len(args) > 2 else ""
            if not did: print("用法: node blacklist remove <did>"); return
            gatekeeper.blacklist_remove(did)
            print(f"已移出黑名单: {did}")
        elif action == "list":
            bl = gatekeeper.blacklist_all()
            print("黑名单:" if bl else "黑名单: (空)")
            for d in bl:
                print(f"  {d}")
        else:
            print("用法: node blacklist <add|remove|list> [did]")

    # ── node resolve <did> <allow|deny> ───────────────────
    elif sub == "resolve":
        if len(args) < 3:
            print("用法: node resolve <did> <allow|deny>"); return
        did, action = args[1], args[2]
        if action not in ("allow", "deny"):
            print("action 必须是 allow 或 deny"); return
        ok = await gatekeeper.resolve(did, action)
        if ok:
            print(f"已 {action}: {did}")
        else:
            print(f"未找到待审批请求: {did}")

    else:
        print(f"未知 node 子命令: '{sub}'")
        _usage()


# ── agent 子命令 ──────────────────────────────────────────

def _parse_agent_opts(args: list[str]) -> dict:
    """从参数列表中解析 --key value 选项"""
    opts = {}
    it = iter(args)
    for tok in it:
        if tok == "--name":
            opts["name"] = next(it)
        elif tok == "--type":
            opts["type"] = next(it)
        elif tok == "--caps":
            opts["capabilities"] = [c.strip() for c in next(it).split(",") if c.strip()]
        elif tok == "--location":
            opts["location"] = next(it)
    return opts


def _fmt_agent(entry: dict) -> str:
    import datetime
    p = entry.get("profile", {})
    ts = entry.get("last_seen", 0)
    dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "-"
    caps = ", ".join(p.get("capabilities", [])) or "-"
    lines = [
        f"  DID      : {entry['did']}",
        f"  名称     : {p.get('name', '-')}",
        f"  类型     : {p.get('type', '-')}",
        f"  能力     : {caps}",
        f"  位置     : {p.get('location', '-') or '-'}",
        f"  最后活跃 : {dt}",
    ]
    return "\n".join(lines)


async def agent_cmd(sub: str, args: list[str]):
    from agent_net.storage import (
        init_db, list_local_agents, get_agent,
        register_agent, update_agent_profile,
        delete_agent, search_agents_by_capability,
    )
    from agent_net.common.did import DIDGenerator, AgentProfile

    await init_db()

    # ── list ──────────────────────────────────────────────
    if sub == "list":
        agents = await list_local_agents()
        if not agents:
            print("(暂无本地 Agent)")
            return
        print(f"本地 Agent 共 {len(agents)} 个:\n")
        for a in agents:
            print(_fmt_agent(a))
            print()

    # ── get ───────────────────────────────────────────────
    elif sub == "get":
        if not args:
            print("用法: agent get <did>"); return
        did = args[0]
        entry = await get_agent(did)
        if not entry:
            print(f"未找到 DID: {did}"); return
        print(_fmt_agent(entry))

    # ── add ───────────────────────────────────────────────
    elif sub == "add":
        if not args:
            print("用法: agent add <name> [--type T] [--caps c1,c2] [--location L]"); return
        name = args[0]
        opts = _parse_agent_opts(args[1:])
        agent_did = DIDGenerator.create_new(name)
        profile = AgentProfile(
            id=agent_did.did,
            name=name,
            type=opts.get("type", "GeneralAgent"),
            capabilities=opts.get("capabilities", []),
            location=opts.get("location", ""),
        )
        await register_agent(agent_did.did, profile.to_dict(), is_local=True)
        print(f"Agent 创建成功:")
        print(f"  DID  : {agent_did.did}")
        print(f"  名称 : {name}")
        print(f"  能力 : {', '.join(profile.capabilities) or '-'}")

    # ── update ────────────────────────────────────────────
    elif sub == "update":
        if not args:
            print("用法: agent update <did> [--name N] [--type T] [--caps c1,c2] [--location L]"); return
        did = args[0]
        opts = _parse_agent_opts(args[1:])
        if not opts:
            print("未提供任何更新字段"); return
        ok = await update_agent_profile(did, opts)
        if not ok:
            print(f"未找到 DID: {did}"); return
        entry = await get_agent(did)
        print(f"更新成功:")
        print(_fmt_agent(entry))

    # ── delete ────────────────────────────────────────────
    elif sub == "delete":
        if not args:
            print("用法: agent delete <did>"); return
        did = args[0]
        # 二次确认
        confirm = input(f"确认删除 {did} ? [y/N] ").strip().lower()
        if confirm != "y":
            print("已取消"); return
        ok = await delete_agent(did)
        print("删除成功" if ok else f"未找到 DID: {did}")

    # ── search ────────────────────────────────────────────
    elif sub == "search":
        if not args:
            print("用法: agent search <keyword>"); return
        keyword = args[0]
        results = await search_agents_by_capability(keyword)
        if not results:
            print(f"未找到匹配 '{keyword}' 的 Agent"); return
        print(f"搜索 '{keyword}' 共 {len(results)} 个结果:\n")
        for r in results:
            print(_fmt_agent({"did": r["did"], "profile": r["profile"]}))
            print()

    else:
        print(f"未知 agent 子命令: '{sub}'")
        _usage()


# ── relay 子命令 ──────────────────────────────────────────

def relay_start():
    import uvicorn
    from agent_net.relay.server import app
    print("[AgentNet] Starting Relay Server on :9000 ...")
    uvicorn.run(app, host="0.0.0.0", port=9000, log_level="info")


# ── test ─────────────────────────────────────────────────

def run_tests():
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v"],
        capture_output=False,
    )
    sys.exit(result.returncode)


# ── 入口 ─────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args:
        _usage()

    if args[0] == "test":
        run_tests()

    elif args[0] == "node":
        sub = args[1] if len(args) > 1 else ""
        if sub == "start":
            node_start()
        elif sub == "mcp":
            node_mcp()
        elif sub == "demo":
            asyncio.run(node_demo())
        elif sub in ("status", "mode", "whitelist", "blacklist", "resolve"):
            asyncio.run(node_gate_cmd([sub] + args[2:]))
        else:
            print(f"Unknown node subcommand: '{sub}'")
            _usage()

    elif args[0] == "agent":
        sub = args[1] if len(args) > 1 else ""
        if not sub:
            _usage()
        asyncio.run(agent_cmd(sub, args[2:]))

    elif args[0] == "relay":
        sub = args[1] if len(args) > 1 else ""
        if sub == "start":
            relay_start()
        else:
            print(f"Unknown relay subcommand: '{sub}'")
            _usage()

    else:
        print(f"Unknown command: '{args[0]}'")
        _usage()


if __name__ == "__main__":
    main()
