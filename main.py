#!/usr/bin/env python
"""
AgentNexus CLI

用法:
  agent-nexus node start                      启动本地节点 Daemon (:8765)
  agent-nexus node mcp                        启动节点 MCP Server (stdio，无身份绑定)
  agent-nexus node mcp --name <name>          启动 MCP 并自动注册/绑定 Agent（推荐）
    --caps <cap1,cap2,...>                       能力标签（逗号分隔）
    --desc <description>                        名片描述
    --tags <tag1,tag2,...>                       名片标签
    --public                                     公开注册到联邦种子站
  agent-nexus node mcp --did <did>            启动 MCP 并绑定到已有 DID
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

  agent-nexus node relay list                 查看已配置的 relay
  agent-nexus node relay add <url>            加入种子 relay（写配置并触发 federation/join）
  agent-nexus node relay remove <url>         移除种子 relay
  agent-nexus node relay set-local <url>      设置本地 relay 地址

  agent-nexus relay start [--host <domain>]    启动公网信令/中转服务器 (:9000)
                                                 --host: 设置 Relay 域名（用于 did:web）

  agent-nexus agent list                列出所有本地 Agent
  agent-nexus agent get   <did>         查看指定 Agent 详情
  agent-nexus agent add   <name> [opts] 新建 Agent
    --type <type>                         类型，默认 GeneralAgent
    --caps <cap1,cap2,...>                能力标签（逗号分隔）
    --location <loc>                      地理位置
    --public                              公开注册到联邦种子站
    --desc <description>                  名片描述
    --tags <tag1,tag2,...>               名片标签
  agent-nexus agent update <did> [opts] 更新 Agent 字段
    --name <name>
    --type <type>
    --caps <cap1,cap2,...>               覆盖能力标签
    --location <loc>
  agent-nexus agent delete <did>        删除指定 Agent
  agent-nexus agent search <keyword>    按能力关键词搜索
  agent-nexus agent profile <did>       查看 Agent 的 NexusProfile 名片

  agent-nexus node worker init <name> [--type <type>] [--owner <owner_did>] [--caps c1,c2]
                                        注册 Worker Agent（默认 interactive_cli）
  agent-nexus node worker status <did>  查看 Worker 状态（owner、worker_type、presence）

  agent-nexus test                      运行全部测试用例
"""
import sys
import asyncio
import os


def _read_token() -> str:
    """从 data/daemon_token.txt 读取 daemon Token（写接口鉴权用）"""
    from agent_net.common.constants import DAEMON_TOKEN_FILE
    if os.path.exists(DAEMON_TOKEN_FILE):
        with open(DAEMON_TOKEN_FILE) as f:
            return f.read().strip()
    return ""


def _usage():
    print(__doc__)
    sys.exit(1)


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
        elif tok == "--public":
            opts["is_public"] = True
        elif tok == "--desc":
            opts["description"] = next(it)
        elif tok == "--tags":
            opts["tags"] = [t.strip() for t in next(it).split(",") if t.strip()]
    return opts


def _fmt_agent(entry: dict) -> str:
    import datetime
    p = entry.get("profile", {})
    ts = entry.get("last_seen", 0)
    dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "-"
    caps = ", ".join(p.get("capabilities", [])) or "-"
    lines = [
        f"  DID          : {entry['did']}",
        f"  Name         : {p.get('name', '-')}",
        f"  Type         : {p.get('type', '-')}",
        f"  Capabilities : {caps}",
        f"  Location     : {p.get('location', '-') or '-'}",
        f"  Last seen    : {dt}",
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
            print("(no local agents)")
            return
        print(f"Local agents: {len(agents)}\n")
        for a in agents:
            print(_fmt_agent(a))
            print()

    # ── get ───────────────────────────────────────────────
    elif sub == "get":
        if not args:
            print("Usage: agent get <did>"); return
        did = args[0]
        entry = await get_agent(did)
        if not entry:
            print(f"DID not found: {did}"); return
        print(_fmt_agent(entry))

    # ── add ───────────────────────────────────────────────
    elif sub == "add":
        if not args:
            print("Usage: agent add <name> [--type T] [--caps c1,c2] [--location L] [--public] [--desc D] [--tags t1,t2]"); return
        name = args[0]
        opts = _parse_agent_opts(args[1:])
        agent_did = DIDGenerator.create_new(name)
        is_public = opts.pop("is_public", False)
        description = opts.pop("description", "")
        tags = opts.pop("tags", [])
        profile = AgentProfile(
            id=agent_did.did,
            name=name,
            type=opts.get("type", "GeneralAgent"),
            capabilities=opts.get("capabilities", []),
            location=opts.get("location", ""),
        )
        from nacl.encoding import HexEncoder
        pk_hex = agent_did.private_key.encode(HexEncoder).decode()
        await register_agent(agent_did.did, profile.to_dict(), is_local=True, private_key_hex=pk_hex)

        # 生成并显示 NexusProfile
        nexus_info = ""
        try:
            from agent_net.common.profile import NexusProfile
            nexus = NexusProfile.create(
                did=agent_did.did,
                signing_key=agent_did.private_key,
                name=name,
                description=description,
                tags=tags or profile.capabilities,
            )
            nexus_info = f"\n  Card signed: OK (tags={nexus.tags})"
        except Exception:
            pass

        print(f"Agent created:")
        print(f"  DID          : {agent_did.did}")
        print(f"  Name         : {name}")
        print(f"  Capabilities : {', '.join(profile.capabilities) or '-'}")
        print(f"  Public       : {'yes (will announce to seed relays)' if is_public else 'no (local only)'}{nexus_info}")

    # ── update ────────────────────────────────────────────
    elif sub == "update":
        if not args:
            print("Usage: agent update <did> [--name N] [--type T] [--caps c1,c2] [--location L]"); return
        did = args[0]
        opts = _parse_agent_opts(args[1:])
        if not opts:
            print("No fields provided to update"); return
        ok = await update_agent_profile(did, opts)
        if not ok:
            print(f"DID not found: {did}"); return
        entry = await get_agent(did)
        print(f"Updated:")
        print(_fmt_agent(entry))

    # ── delete ────────────────────────────────────────────
    elif sub == "delete":
        if not args:
            print("Usage: agent delete <did>"); return
        did = args[0]
        confirm = input(f"Confirm delete {did}? [y/N] ").strip().lower()
        if confirm != "y":
            print("Cancelled"); return
        ok = await delete_agent(did)
        print("Deleted" if ok else f"DID not found: {did}")

    # ── search ────────────────────────────────────────────
    elif sub == "search":
        if not args:
            print("Usage: agent search <keyword>"); return
        keyword = args[0]
        results = await search_agents_by_capability(keyword)
        if not results:
            print(f"No agents found matching '{keyword}'"); return
        print(f"Search '{keyword}': {len(results)} result(s)\n")
        for r in results:
            print(_fmt_agent({"did": r["did"], "profile": r["profile"]}))
            print()

    # ── profile ───────────────────────────────────────────
    elif sub == "profile":
        if not args:
            print("Usage: agent profile <did>"); return
        did = args[0]
        import json as _json
        import aiohttp as _aiohttp
        try:
            async with _aiohttp.ClientSession() as s:
                async with s.get(
                    f"http://localhost:8765/agents/{did}/profile",
                    timeout=_aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(_json.dumps(data, ensure_ascii=False, indent=2))
                    elif resp.status == 404:
                        print(f"DID not found: {did}")
                    elif resp.status == 409:
                        print("No persistent private key for this agent; cannot generate signed card")
                    else:
                        text = await resp.text()
                        print(f"Daemon returned {resp.status}: {text}")
        except _aiohttp.ClientConnectorError:
            print("Cannot connect to Node Daemon (run: python main.py node start)")

    # ── export ────────────────────────────────────────────
    elif sub == "export":
        import argparse as _ap
        _p = _ap.ArgumentParser(prog="agent export")
        _p.add_argument("did")
        _p.add_argument("--output", "-o", required=True, help="Output file path")
        _p.add_argument("--password", "-p", required=True, help="Encryption password")
        _ns = _p.parse_args(args)
        import json as _json
        import aiohttp as _aiohttp
        token = _read_token()
        try:
            async with _aiohttp.ClientSession() as s:
                async with s.get(
                    f"http://localhost:8765/agents/{_ns.did}/export",
                    params={"password": _ns.password},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=_aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        with open(_ns.output, "w", encoding="utf-8") as f:
                            f.write(data["data"])
                        print(f"Agent exported to {_ns.output}")
                    elif resp.status == 404:
                        print(f"DID not found: {_ns.did}")
                    else:
                        text = await resp.text()
                        print(f"Daemon returned {resp.status}: {text}")
        except _aiohttp.ClientConnectorError:
            print("Cannot connect to Node Daemon (run: python main.py node start)")

    # ── import ────────────────────────────────────────────
    elif sub == "import":
        import argparse as _ap
        _p = _ap.ArgumentParser(prog="agent import")
        _p.add_argument("file", help="Identity bundle file to import")
        _p.add_argument("--password", "-p", required=True, help="Decryption password")
        _ns = _p.parse_args(args)
        import aiohttp as _aiohttp
        token = _read_token()
        try:
            with open(_ns.file, "r", encoding="utf-8") as f:
                bundle_data = f.read()
            async with _aiohttp.ClientSession() as s:
                async with s.post(
                    "http://localhost:8765/agents/import",
                    json={"data": bundle_data, "password": _ns.password},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=_aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"Agent imported: {data['did']}")
                        print(f"Certifications restored: {data['certifications_restored']}")
                    else:
                        text = await resp.text()
                        print(f"Daemon returned {resp.status}: {text}")
        except FileNotFoundError:
            print(f"File not found: {_ns.file}")
        except _aiohttp.ClientConnectorError:
            print("Cannot connect to Node Daemon (run: python main.py node start)")

    else:
        print(f"Unknown agent subcommand: '{sub}'")
        _usage()


# ── relay 子命令 ──────────────────────────────────────────

def relay_start(host: str | None = None):
    """
    启动 Relay Server

    Args:
        host: Relay 域名（用于生成 did:web），优先级高于环境变量
    """
    import uvicorn
    from agent_net.relay.server import app, init_relay_identity

    # 设置 Relay 域名（优先级: --host > RELAY_HOST 环境变量 > 默认值）
    if host:
        import os
        os.environ["RELAY_HOST"] = host

    # 初始化 Relay 身份（在 uvicorn 启动前）
    init_relay_identity()

    print("[AgentNet] Starting Relay Server on :9000 ...")
    uvicorn.run(app, host="0.0.0.0", port=9000, log_level="info")


# ── node relay 配置子命令 ─────────────────────────────────

async def node_relay_cmd(args: list[str]):
    """node relay list/add/remove/set-local 子命令"""
    import aiohttp
    from agent_net.common.constants import NODE_CONFIG_FILE, DATA_DIR
    import json, os

    def _load():
        if os.path.exists(NODE_CONFIG_FILE):
            try:
                with open(NODE_CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"local_relay": "http://localhost:9000", "seed_relays": []}

    def _save(cfg):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(NODE_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    if not args:
        print("Usage: node relay <list|add|remove|set-local> [url]"); return

    sub = args[0]

    if sub == "list":
        cfg = _load()
        print(f"Local relay  : {cfg['local_relay']}")
        seeds = cfg.get("seed_relays", [])
        print(f"Seed relays ({len(seeds)}):")
        for s in seeds:
            print(f"  {s}")
        if not seeds:
            print("  (none)")

    elif sub == "set-local":
        if len(args) < 2:
            print("Usage: node relay set-local <url>"); return
        url = args[1]
        cfg = _load()
        cfg["local_relay"] = url
        _save(cfg)
        print(f"Local relay set to: {url}")

    elif sub == "add":
        if len(args) < 2:
            print("Usage: node relay add <url>"); return
        url = args[1]
        cfg = _load()
        seeds = cfg.setdefault("seed_relays", [])
        if url in seeds:
            print(f"Already exists: {url}"); return
        seeds.append(url)
        _save(cfg)
        print(f"Seed relay added: {url}")
        # 向种子站注册本 relay
        local_relay = cfg["local_relay"]
        try:
            async with aiohttp.ClientSession() as s:
                resp = await s.post(
                    f"{url}/federation/join",
                    json={"relay_url": local_relay},
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                if resp.status == 200:
                    print(f"federation/join sent to {url} [ok]")
                else:
                    print(f"federation/join returned {resp.status}; config saved but handshake failed")
        except Exception as e:
            print(f"federation/join failed (network unreachable): {e}; config saved")

    elif sub == "remove":
        if len(args) < 2:
            print("Usage: node relay remove <url>"); return
        url = args[1]
        cfg = _load()
        seeds = cfg.get("seed_relays", [])
        if url not in seeds:
            print(f"Not found: {url}"); return
        seeds.remove(url)
        _save(cfg)
        print(f"Seed relay removed: {url}")

    else:
        print(f"Unknown node relay subcommand: '{sub}'")


# ── node worker 子命令 ──────────────────────────────────

async def node_worker_cmd(args: list[str]):
    """
    D-SEC-08: CLI Worker profile 管理。
    注册 Agent、设置 worker_type、绑定 owner_did。
    """
    if not args:
        print("Usage: node worker init <name> [--type <worker_type>] [--owner <owner_did>] [--caps cap1,cap2]")
        print("       node worker status <did>    查看 Worker 状态（owner_did, worker_type, presence）")
        return

    sub = args[0]
    token = _read_token()
    base = "http://localhost:8765"
    auth = {"Authorization": f"Bearer {token}"} if token else {}

    if sub == "init":
        name = args[1] if len(args) > 1 else ""
        if not name:
            print("Error: worker name is required"); return

        worker_type = "interactive_cli"
        owner_did = ""
        caps = []
        it = iter(args[2:])
        for tok in it:
            if tok == "--type": worker_type = next(it, "interactive_cli")
            elif tok == "--owner": owner_did = next(it, "")
            elif tok == "--caps": caps = [c.strip() for c in next(it, "").split(",") if c.strip()]

        if worker_type not in ("resident", "interactive_cli", "service_worker"):
            print(f"Error: invalid worker_type '{worker_type}'"); return

        import aiohttp
        async with aiohttp.ClientSession() as s:
            # 1. 注册 Agent（带 worker_type）
            payload = {"name": name, "capabilities": caps, "worker_type": worker_type}
            async with s.post(f"{base}/agents/register", json=payload, headers=auth) as r:
                if r.status != 200:
                    print(f"Registration failed {r.status}: {await r.text()}"); return
                data = await r.json()
                agent_did = data["did"]

            print(f"Registered worker '{name}' -> {agent_did}")

            # 2. 绑定到 owner（如提供）
            if owner_did:
                async with s.post(
                    f"{base}/owner/bind",
                    json={"owner_did": owner_did, "agent_did": agent_did},
                    headers=auth,
                ) as r:
                    if r.status == 200:
                        print(f"Bound to owner: {owner_did}")
                    else:
                        print(f"Warning: bind failed {r.status}: {await r.text()}")

    elif sub == "status":
        did = args[1] if len(args) > 1 else ""
        if not did:
            print("Error: did is required"); return

        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base}/agents/{did}") as r:
                if r.status != 200:
                    print(f"Agent not found: {did}"); return
                agent = await r.json()
                owner_did = agent.get("owner_did", "")
                worker_type = agent.get("worker_type", "")
                profile = agent.get("profile", {})
                print(f"DID:         {did}")
                print(f"Name:        {profile.get('name', '')}")
                print(f"Owner:       {owner_did or '(not bound)'}")
                print(f"Worker Type: {worker_type or '(not set)'}")
                print(f"Caps:        {profile.get('capabilities', [])}")

            # 查询 presence
            async with s.get(
                f"{base}/workers/{did}/presence",
                params={"actor_did": did},
                headers=auth,
            ) as r:
                if r.status == 200:
                    pres = await r.json()
                    print(f"Presence:    {pres.get('presence', 'unknown')}")
                else:
                    print(f"Presence:    (unavailable)")
    else:
        print(f"Unknown worker subcommand: '{sub}'")


# ── node coordination 子命令 ──────────────────────────────

# ── node coordination 子命令 ──────────────────────────────

def _check_sdk_available():
    """Return True if agentnexus SDK coordination facade is importable."""
    try:
        import agentnexus
        from agentnexus.coordination import CoordinationClient
        return True
    except ImportError:
        return False


async def _get_coordination_client():
    """Create a lightweight SDK client connected to local daemon."""
    import aiohttp
    from agentnexus.client import AgentNexusClient, AgentInfo

    token = _read_token()
    client = AgentNexusClient(
        daemon_url="http://localhost:8765",
        token=token,
        agent_info=AgentInfo(did="", name="CLI-Coordination", capabilities=["Admin"], owner_did=""),
    )
    client._session = aiohttp.ClientSession()
    return client


async def _close_coordination_client(client):
    """Close the SDK client session cleanly."""
    if client and client._session:
        await client._session.close()
        client._session = None


async def _run_coordination_demo():
    """Run the full coding coordination demo via SDK facades. Returns result dict."""
    import asyncio, time, json as _json
    from agentnexus.client import AgentNexusClient, AgentInfo
    from agentnexus.owner import OwnerClient
    from agentnexus.enclave import EnclaveManager
    import aiohttp

    token = _read_token()
    base = "http://localhost:8765"
    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    # Create a proper connected client for the demo
    client = AgentNexusClient(
        daemon_url=base,
        token=token,
        agent_info=AgentInfo(did="", name="CLI-Coordination-Demo", capabilities=["Admin"], owner_did=""),
    )
    client._session = aiohttp.ClientSession()
    owner = OwnerClient(client)
    result = {"steps": [], "session_id": None, "closure_id": None}

    try:
        # Step 0: check daemon health
        try:
            async with client._session.get(f"{base}/health") as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Daemon not healthy: {resp.status}")
        except aiohttp.ClientConnectorError:
            print("[Error] Cannot connect to Node Daemon. Run: python main.py node start")
            return result

        # Step 1: create/find Demo Owner via proper owner API
        print("Setting up demo identities...")
        demo_dids = {}

        # Create owner via /owner/register (writes owner table, required for coding_intake)
        owner_did = None
        try:
            existing_agents = await owner.list_agents(owner_did="", actor_did="")
        except Exception:
            existing_agents = []

        # Try to find existing Demo Owner by checking all local agents
        async with client._session.get(f"{base}/agents/local") as r:
            if r.status == 200:
                data = await r.json()
                for a in data.get("agents", []):
                    if a.get("profile", {}).get("name") == "Demo Owner":
                        owner_did = a["did"]
                        break

        if not owner_did:
            try:
                owner_info = await owner.register("Demo Owner")
                owner_did = owner_info.did
            except Exception:
                # Fallback: register-agent path for backwards compat
                async with client._session.post(
                    f"{base}/agents/register",
                    json={"name": "Demo Owner", "capabilities": ["Admin"], "worker_type": "resident"},
                    headers=auth_headers,
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        owner_did = data["did"]
                    else:
                        raise RuntimeError(f"Failed to create Demo Owner: {await r.text()}")

        demo_dids["owner"] = owner_did
        print(f"  Owner: {owner_did}")

        # Create non-owner agents (Secretary, Designer, etc.)
        async def _find_or_create_agent(name, caps, worker_type="resident"):
            async with client._session.get(f"{base}/agents/local") as r:
                if r.status == 200:
                    data = await r.json()
                    for a in data.get("agents", []):
                        if a.get("profile", {}).get("name") == name:
                            return a["did"]
            async with client._session.post(
                f"{base}/agents/register",
                json={"name": name, "capabilities": caps, "worker_type": worker_type},
                headers=auth_headers,
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return data["did"]
                raise RuntimeError(f"Failed to create agent {name}: {await r.text()}")

        secretary_did = await _find_or_create_agent("Demo Secretary", ["orchestrate", "intake", "dispatch"], "resident")
        demo_dids["secretary"] = secretary_did
        print(f"  Secretary: {secretary_did}")

        designer_did = await _find_or_create_agent("Demo Designer", ["design"], "resident")
        demo_dids["designer"] = designer_did

        developer_did = await _find_or_create_agent("Demo Developer", ["coding"], "resident")
        demo_dids["developer"] = developer_did

        reviewer_did = await _find_or_create_agent("Demo Reviewer", ["review"], "resident")
        demo_dids["reviewer"] = reviewer_did

        tester_did = await _find_or_create_agent("Demo Tester", ["testing"], "resident")
        demo_dids["tester"] = tester_did

        # Bind agents to owner via SDK facade
        for role, did in demo_dids.items():
            if role != "owner":
                try:
                    await owner.bind(owner_did, did)
                except Exception:
                    pass

        # Step 2: create demo enclave + vault content via SDK facades
        print("Creating demo enclave and vault content...")
        enclave_id = "demo_coordination_enclave"

        enclaves = EnclaveManager(client)
        try:
            enclave = await enclaves.create(
                name="Demo Coordination Enclave",
                owner_did=owner_did,
                members={
                    "designer": {"did": designer_did, "role": "designer", "permissions": "rw"},
                    "developer": {"did": developer_did, "role": "developer", "permissions": "rw"},
                    "reviewer": {"did": reviewer_did, "role": "reviewer", "permissions": "rw"},
                    "tester": {"did": tester_did, "role": "tester", "permissions": "rw"},
                },
            )
            enclave_id = enclave.enclave_id
        except Exception:
            # Fallback: raw HTTP for enclave creation
            try:
                async with client._session.post(
                    f"{base}/enclaves",
                    json={
                        "name": "Demo Coordination Enclave",
                        "owner_did": owner_did,
                        "actor_did": owner_did,
                        "members": {
                            "designer": {"did": designer_did, "role": "designer", "permissions": "rw"},
                            "developer": {"did": developer_did, "role": "developer", "permissions": "rw"},
                            "reviewer": {"did": reviewer_did, "role": "reviewer", "permissions": "rw"},
                            "tester": {"did": tester_did, "role": "tester", "permissions": "rw"},
                        },
                    },
                    headers=auth_headers,
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        enclave_id = data.get("enclave_id", enclave_id)
            except Exception:
                pass

        # Write vault content for each stage
        vault_contents = {
            "clarify.md": "# Requirement Spec\n\nLogin module with email/password.\n\n## Acceptance Criteria\n- Email validation\n- Password hashing\n- Session management",
            "design.md": "# Design Spec\n\n## Architecture\n- Login API endpoint\n- Password hasher service\n- Session token manager",
            "implement.py": "# Implementation\n\ndef login(email, password):\n    user = find_user(email)\n    if user and verify_password(password, user.hash):\n        return create_session(user.id)\n    raise AuthError()",
            "code_review.md": "# Code Review\n\nAll acceptance criteria met. Code follows style guide. Tests pass.",
            "test_report.md": "# Test Report\n\n## Results\n- Unit tests: 12/12 passed\n- Integration tests: 4/4 passed\n- Coverage: 87%",
        }
        vault = None
        try:
            enclave_proxy = await enclaves.get(enclave_id, actor_did=owner_did)
            vault = enclave_proxy.vault
        except Exception:
            pass

        for key, value in vault_contents.items():
            try:
                if vault:
                    await vault.put(key, value, author_did=owner_did)
                else:
                    async with client._session.post(
                        f"{base}/enclaves/{enclave_id}/vault/{key}",
                        json={"value": value, "author_did": owner_did},
                        headers=auth_headers,
                    ) as r:
                        pass
            except Exception:
                pass

        # Step 3: coding intake
        print("Running coding coordination workflow...")
        session = await client.coordination.coding_intake(
            owner_did=owner_did,
            actor_did=secretary_did,
            objective="Implement demo login module",
            complexity="medium",
        )
        session_id = session["coordination_session_id"]
        result["session_id"] = session_id
        print(f"  Session: {session_id}")

        # Full 7-stage workflow: clarify -> design -> design_review -> implement -> code_review -> test -> final
        workflow_definition = [
            # (stage, artifact_type, producer_did, receipt_type, issuer_did, vault_key)
            ("clarify", "RequirementSpec", designer_did, "ClarifyReceipt", reviewer_did, "clarify.md"),
            ("design", "DesignArtifact", designer_did, "DesignReceipt", reviewer_did, "design.md"),
            ("design_review", "DesignReviewArtifact", reviewer_did, "DesignReviewReceipt", reviewer_did, None),
            ("implement", "ImplementationArtifact", developer_did, "ImplementationReceipt", reviewer_did, "implement.py"),
            ("code_review", "CodeReviewArtifact", reviewer_did, "CodeReviewReceipt", reviewer_did, "code_review.md"),
            ("test", "TestResultArtifact", tester_did, "TestReceipt", reviewer_did, "test_report.md"),
            ("final", None, None, None, None, None),  # final auto-closes on advance
        ]

        for stage, atype, producer, rtype, issuer, vkey in workflow_definition:
            # Submit artifact (skip for final — it auto-generates)
            if atype and producer:
                try:
                    content_ref = f"vault://{enclave_id}/{vkey}" if vkey else f"vault://{enclave_id}/design.md"
                    art = await client.coordination.submit_artifact(
                        coordination_session_id=session_id,
                        stage=stage,
                        artifact_type=atype,
                        producer_did=producer,
                        content_ref=content_ref,
                    )
                    print(f"  Artifact: {art['artifact_id']} ({stage})")
                except Exception as e:
                    print(f"  [Warn] Artifact {stage}: {e}")

            # Submit receipt (skip for final — advance auto-generates FinalResultReceipt)
            if rtype and issuer:
                try:
                    rcpt = await client.coordination.submit_receipt(
                        coordination_session_id=session_id,
                        stage=stage,
                        receipt_type=rtype,
                        issuer_did=issuer,
                        decision="approved",
                    )
                    print(f"  Receipt: {rcpt['receipt_id']} ({stage})")
                except Exception as e:
                    print(f"  [Warn] Receipt {stage}: {e}")

            # Advance to next stage
            try:
                state = await client.coordination.advance(
                    coordination_session_id=session_id,
                    actor_did=secretary_did,
                )
                status = state.get("status", "")
                cs = state.get("current_stage", "?")
                closure = state.get("closure")
                if closure and closure.get("closure"):
                    result["closure_id"] = closure["closure"].get("closure_id")
                stage_label = "completed" if status == "completed" else cs
                print(f"  Advance: -> {stage_label}")
                if status == "completed":
                    break
            except Exception as e:
                print(f"  [Warn] advance {stage}: {e}")

        # Step 4: timeline and closure
        timeline_data = await client.coordination.timeline(
            coordination_session_id=session_id,
            actor_did=secretary_did,
        )
        closures_data = await client.coordination.closures(
            coordination_session_id=session_id,
            actor_did=secretary_did,
        )
        try:
            session_detail = await client.coordination.get_session(
                coordination_session_id=session_id,
                actor_did=secretary_did,
            )
        except Exception:
            session_detail = {}

        result["timeline"] = timeline_data.get("timeline", [])
        closures = closures_data.get("closures", [])
        if closures and not result["closure_id"]:
            result["closure_id"] = closures[0].get("closure_id")

        # Print summary
        print(f"\nCoding Coordination demo completed\n")
        print(f"Session: {session_id}")
        final_status = session_detail.get("status") or ("completed" if result["closure_id"] else "unknown")
        print(f"Status : {final_status}")
        print(f"Events : {len(result['timeline'])} timeline entries")
        if result["closure_id"]:
            print(f"Closure: {result['closure_id']}")
        print(f"\nOpen:  http://127.0.0.1:8765/ui/coordination/{session_id}")

    finally:
        await _close_coordination_client(client)

    return result


async def node_coordination_cmd(args: list[str]):
    """node coordination — Coding Coordination V1 CLI (via SDK facade)."""
    import json as _json

    if not args:
        print("Usage: node coordination <subcommand> [...]")
        print("Primary:  demo | show <session_id> | timeline <session_id>")
        print("Low-level: coding-intake | get | list | fork | artifact | receipt | advance | delegate | accept | reject | closures")
        return

    if not _check_sdk_available():
        print("Error: AgentNexus SDK is not installed.")
        print("Please install: pip install -e agentnexus-sdk")
        return

    sub = args[0]
    base = "http://localhost:8765"

    # ── demo ────────────────────────────────────────────────
    if sub == "demo":
        await _run_coordination_demo()
        return

    # ── show ────────────────────────────────────────────────
    if sub == "show":
        if len(args) < 2:
            print("Usage: node coordination show <session_id> [--actor <did>]"); return
        session_id = args[1]
        actor_did = ""
        it = iter(args[2:])
        for tok in it:
            if tok == "--actor": actor_did = next(it, "")
        if not actor_did:
            print("Error: --actor <did> is required"); return

        nexus = await _get_coordination_client()
        try:
            sess = await nexus.coordination.get_session(session_id, actor_did=actor_did)
            timeline = await nexus.coordination.timeline(session_id, actor_did=actor_did)
            artifacts = await nexus.coordination.list_artifacts(session_id, actor_did=actor_did)
            receipts = await nexus.coordination.list_receipts(session_id, actor_did=actor_did)
            closures = await nexus.coordination.closures(session_id, actor_did=actor_did)

            print(f"Session: {sess.get('coordination_session_id')}")
            print(f"Objective: {sess.get('objective')}")
            print(f"Status: {sess.get('status')}")
            print(f"Workflow: {sess.get('workflow_id')}")
            print(f"Owner: {sess.get('owner_did')}")
            print(f"Controller: {sess.get('controller_did')}")
            print()
            print(f"Timeline ({len(timeline.get('timeline', []))} entries):")
            for evt in timeline.get("timeline", []):
                print(f"  [{evt.get('event_type')}] {evt.get('stage', '')}")
            print(f"Artifacts ({len(artifacts)}):")
            for art in artifacts:
                print(f"  {art.get('artifact_id')} [{art.get('stage')}] {art.get('artifact_type')}")
            print(f"Receipts ({len(receipts)}):")
            for rcpt in receipts:
                print(f"  {rcpt.get('receipt_id')} [{rcpt.get('stage')}] {rcpt.get('decision')}")
            closures_list = closures.get("closures", [])
            print(f"Closures ({len(closures_list)}):")
            for clo in closures_list:
                print(f"  {clo.get('closure_id')} [{clo.get('sla_status', '')}]")
        finally:
            await _close_coordination_client(nexus)
        return

    # ── Low-level commands via SDK facade ────────────────────
    # All remaining subcommands need an SDK client
    nexus = await _get_coordination_client()
    try:
        def _pp(data):
            print(_json.dumps(data, ensure_ascii=False, indent=2))

        # ── coding-intake ──────────────────────────────────
        if sub == "coding-intake":
            if len(args) < 4:
                print("Usage: node coordination coding-intake <owner_did> <actor_did> <objective> [--complexity medium] [--risk normal] [--cost balanced] [--sensitivity internal] [--approval]")
                return
            opts = {"complexity": "medium", "risk_level": "normal", "cost_policy": "balanced", "data_sensitivity": "internal", "requires_human_approval": False}
            it = iter(args[4:])
            for tok in it:
                if tok == "--complexity": opts["complexity"] = next(it, "medium")
                elif tok == "--risk": opts["risk_level"] = next(it, "normal")
                elif tok == "--cost": opts["cost_policy"] = next(it, "balanced")
                elif tok == "--sensitivity": opts["data_sensitivity"] = next(it, "internal")
                elif tok == "--approval": opts["requires_human_approval"] = True
            session = await nexus.coordination.coding_intake(
                owner_did=args[1], actor_did=args[2], objective=args[3],
                **opts,
            )
            print(f"Session: {session['coordination_session_id']}")
            _pp(session)

        # ── get ────────────────────────────────────────────
        elif sub == "get":
            if len(args) < 2:
                print("Usage: node coordination get <session_id> --actor <did>"); return
            actor_did = ""
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": actor_did = next(it, "")
            sess = await nexus.coordination.get_session(args[1], actor_did=actor_did)
            print(f"Session: {sess.get('coordination_session_id')}")
            print(f"Objective: {sess.get('objective')}")
            print(f"Status: {sess.get('status')}")
            _pp(sess)

        # ── list ───────────────────────────────────────────
        elif sub == "list":
            params = {}
            it = iter(args[1:])
            for tok in it:
                if tok == "--owner": params["owner_did"] = next(it, "")
                elif tok == "--actor": params["actor_did"] = next(it, "")
                elif tok == "--status": params["status"] = next(it, "")
                elif tok == "--workflow": params["workflow_id"] = next(it, "")
            sessions = await nexus.coordination.list_sessions(**params)
            print(f"Sessions: {len(sessions)}")
            for s in sessions:
                print(f"  {s.get('coordination_session_id')} — {s.get('objective', '')} [{s.get('status', '')}]")

        # ── fork ───────────────────────────────────────────
        elif sub == "fork":
            if len(args) < 2:
                print("Usage: node coordination fork <session_id> --actor <did> [--link-type <t>] [--reason <r>]"); return
            body = {"coordination_session_id": args[1], "actor_did": "", "link_type": "review_fork", "reason": ""}
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": body["actor_did"] = next(it, "")
                elif tok == "--link-type": body["link_type"] = next(it, "review_fork")
                elif tok == "--reason": body["reason"] = next(it, "")
            child = await nexus.coordination.fork_session(**body)
            print(f"Forked: {child.get('coordination_session_id')}")
            _pp(child)

        # ── artifact ───────────────────────────────────────
        elif sub == "artifact":
            action = args[1] if len(args) > 1 else ""
            if action == "submit":
                if len(args) < 7:
                    print("Usage: node coordination artifact submit <session_id> <stage> <type> <producer_did> <content_ref>"); return
                art = await nexus.coordination.submit_artifact(
                    coordination_session_id=args[2], stage=args[3],
                    artifact_type=args[4], producer_did=args[5], content_ref=args[6],
                )
                print(f"Artifact: {art.get('artifact_id')}")
                _pp(art)
            elif action == "list":
                params = {"actor_did": ""}
                it = iter(args[2:])
                for tok in it:
                    if tok == "--actor": params["actor_did"] = next(it, "")
                    elif tok == "--stage": params["stage"] = next(it, "")
                session_id = args[2] if len(args) > 2 and not args[2].startswith("--") else ""
                if session_id:
                    arts = await nexus.coordination.list_artifacts(session_id, **params)
                    _pp(arts)
                else:
                    print("Usage: node coordination artifact list <session_id> --actor <did>")
            else:
                print("Usage: node coordination artifact <submit|list> [...]")

        # ── receipt ────────────────────────────────────────
        elif sub == "receipt":
            action = args[1] if len(args) > 1 else ""
            if action == "submit":
                if len(args) < 7:
                    print("Usage: node coordination receipt submit <session_id> <stage> <type> <issuer_did> <decision> [--subject-artifact <id>]"); return
                opts = {}
                it = iter(args[7:])
                for tok in it:
                    if tok == "--subject-artifact": opts["subject_artifact_id"] = next(it, "")
                rcpt = await nexus.coordination.submit_receipt(
                    coordination_session_id=args[2], stage=args[3],
                    receipt_type=args[4], issuer_did=args[5], decision=args[6],
                    **opts,
                )
                print(f"Receipt: {rcpt.get('receipt_id')}")
                _pp(rcpt)
            elif action == "list":
                params = {"actor_did": ""}
                it = iter(args[2:])
                for tok in it:
                    if tok == "--actor": params["actor_did"] = next(it, "")
                    elif tok == "--stage": params["stage"] = next(it, "")
                session_id = args[2] if len(args) > 2 and not args[2].startswith("--") else ""
                if session_id:
                    receipts = await nexus.coordination.list_receipts(session_id, **params)
                    _pp(receipts)
                else:
                    print("Usage: node coordination receipt list <session_id> --actor <did>")
            else:
                print("Usage: node coordination receipt <submit|list> [...]")

        # ── advance ────────────────────────────────────────
        elif sub == "advance":
            if len(args) < 2:
                print("Usage: node coordination advance <session_id> --actor <did>"); return
            actor_did = ""
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": actor_did = next(it, "")
            state = await nexus.coordination.advance(args[1], actor_did=actor_did)
            print(f"Status: {state.get('status')}")
            print(f"Stage:  {state.get('current_stage', state.get('previous_stage', ''))}")
            _pp(state)

        # ── timeline ───────────────────────────────────────
        elif sub == "timeline":
            if len(args) < 2:
                print("Usage: node coordination timeline <session_id> --actor <did>"); return
            actor_did = ""
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": actor_did = next(it, "")
            data = await nexus.coordination.timeline(args[1], actor_did=actor_did)
            tl = data.get("timeline", [])
            print(f"Events: {len(tl)}")
            for evt in tl:
                print(f"  [{evt.get('event_type')}] {evt.get('stage', '')}")
            _pp(data)

        # ── closures ───────────────────────────────────────
        elif sub == "closures":
            if len(args) < 2:
                print("Usage: node coordination closures <session_id> --actor <did> [--status <s>]"); return
            params = {}
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": params["actor_did"] = next(it, "")
                elif tok == "--status": params["status"] = next(it, "")
            data = await nexus.coordination.closures(args[1], **params)
            cls = data.get("closures", [])
            print(f"Closures: {len(cls)}")
            for clo in cls:
                print(f"  {clo.get('closure_id')} [{clo.get('status')}]")
            _pp(data)

        # ── delegate ───────────────────────────────────────
        elif sub == "delegate":
            if len(args) < 4:
                print("Usage: node coordination delegate <session_id> <stage> <delegatee_did> --delegator <did> [--role <r>]"); return
            body = {"coordination_session_id": args[1], "stage": args[2], "delegatee_did": args[3], "delegator_did": "", "role": args[2]}
            it = iter(args[4:])
            for tok in it:
                if tok == "--delegator": body["delegator_did"] = next(it, "")
                elif tok == "--role": body["role"] = next(it, args[2])
            result = await nexus.coordination.delegate_stage(**body)
            delegation = result.get("delegation", {})
            print(f"Delegation: {delegation.get('delegation_id')}")
            print(f"Status: {delegation.get('status')}")
            _pp(result)

        # ── accept ─────────────────────────────────────────
        elif sub == "accept":
            if len(args) < 2:
                print("Usage: node coordination accept <delegation_id> --actor <did>"); return
            actor_did = ""
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": actor_did = next(it, "")
            result = await nexus.coordination.accept_delegation(args[1], actor_did=actor_did)
            print(f"Status: {result.get('status')}")
            _pp(result)

        # ── reject ─────────────────────────────────────────
        elif sub == "reject":
            if len(args) < 2:
                print("Usage: node coordination reject <delegation_id> --actor <did> [--reason <r>]"); return
            body = {"actor_did": "", "reason": ""}
            it = iter(args[2:])
            for tok in it:
                if tok == "--actor": body["actor_did"] = next(it, "")
                elif tok == "--reason": body["reason"] = next(it, "")
            result = await nexus.coordination.reject_delegation(args[1], **body)
            print(f"Status: {result.get('status')}")
            _pp(result)

        else:
            print(f"Unknown coordination subcommand: '{sub}'")
            print("Primary:  demo | show <session_id> | timeline <session_id>")
            print("Low-level: coding-intake | get | list | fork | artifact submit/list | receipt submit/list | advance | delegate | accept | reject | closures")

    finally:
        await _close_coordination_client(nexus)


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
            # 解析 node mcp 的可选参数
            mcp_name = mcp_did = mcp_desc = ""
            mcp_caps: list = []
            mcp_tags: list = []
            mcp_public = False
            it = iter(args[2:])
            for tok in it:
                if tok == "--name":    mcp_name   = next(it, "")
                elif tok == "--did":   mcp_did    = next(it, "")
                elif tok == "--caps":  mcp_caps   = [c.strip() for c in next(it, "").split(",") if c.strip()]
                elif tok == "--desc":  mcp_desc   = next(it, "")
                elif tok == "--tags":  mcp_tags   = [t.strip() for t in next(it, "").split(",") if t.strip()]
                elif tok == "--public": mcp_public = True
            node_mcp(
                name=mcp_name or None,
                did=mcp_did or None,
                caps=mcp_caps,
                desc=mcp_desc,
                tags=mcp_tags,
                public=mcp_public,
            )
        elif sub == "demo":
            asyncio.run(node_demo())
        elif sub in ("status", "mode", "whitelist", "blacklist", "resolve"):
            asyncio.run(node_gate_cmd([sub] + args[2:]))
        elif sub == "relay":
            asyncio.run(node_relay_cmd(args[2:]))
        elif sub == "worker":
            asyncio.run(node_worker_cmd(args[2:]))
        elif sub == "coordination":
            asyncio.run(node_coordination_cmd(args[2:]))
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
            # 解析 --host 参数
            relay_host = None
            it = iter(args[2:])
            for tok in it:
                if tok == "--host":
                    relay_host = next(it, None)
            relay_start(host=relay_host)
        else:
            print(f"Unknown relay subcommand: '{sub}'")
            _usage()

    else:
        print(f"Unknown command: '{args[0]}'")
        _usage()


if __name__ == "__main__":
    main()
