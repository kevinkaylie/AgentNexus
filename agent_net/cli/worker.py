from .common import _read_token

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



__all__ = [name for name in globals() if not name.startswith("__")]
