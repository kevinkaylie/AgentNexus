from .common import _read_token, _usage

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



__all__ = [name for name in globals() if not name.startswith("__")]
