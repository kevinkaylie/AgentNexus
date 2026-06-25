#!/usr/bin/env python
"""AgentNexus CLI compatibility entry point."""
from agent_net.cli.common import *  # noqa: F401,F403
from agent_net.cli import node as _node_cli
from agent_net.cli.node import *  # noqa: F401,F403
from agent_net.cli.agent import *  # noqa: F401,F403
from agent_net.cli.relay import *  # noqa: F401,F403
from agent_net.cli.runner import *  # noqa: F401,F403
from agent_net.cli.worker import *  # noqa: F401,F403
from agent_net.cli.coordination import *  # noqa: F401,F403


def node_mcp(
    name: str | None = None,
    did: str | None = None,
    caps: list | None = None,
    desc: str = "",
    tags: list | None = None,
    public: bool = False,
):
    """Compatibility wrapper preserving monkeypatchable CLI dependencies."""
    _node_cli._mcp_bind_agent = _mcp_bind_agent
    return _node_cli.node_mcp(name, did, caps, desc, tags, public)

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
        elif sub == "local-runner":
            asyncio.run(node_local_runner_cmd(args[2:]))
        elif sub == "objective":
            asyncio.run(node_objective_cmd(args[2:]))
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
