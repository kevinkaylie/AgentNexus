# ── relay 子命令 ──────────────────────────────────────────

def relay_start(host: str | None = None):
    """
    启动 Relay Server

    Args:
        host: Relay 域名（用于生成 did:web），优先级高于环境变量
    """
    # 设置 Relay 域名（优先级: --host > RELAY_HOST 环境变量 > 默认值）
    if host:
        import os
        os.environ["RELAY_HOST"] = host

    import uvicorn
    from agent_net.relay.server import app, init_relay_identity

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



__all__ = [name for name in globals() if not name.startswith("__")]
