"""
agent_net.node.daemon
本地节点后端服务入口 — 组装所有 Router 并管理生命周期。
监听: 0.0.0.0:8765
"""
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from agent_net.node._auth import init_daemon_token
from agent_net.node._config import (
    NODE_PORT, init_config, get_relay_url,
    set_public_endpoint, cleanup_expired_push_registrations_loop,
    _cleanup_push_task, _heartbeat_task,
)
from agent_net.node.routers import agents, messages, handshake, adapters, push, enclave, governance
from agent_net.storage import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    import agent_net.node._config as _cfg

    await init_db()
    init_daemon_token()
    init_config()

    from agent_net.stun import get_public_endpoint
    ep = await get_public_endpoint()
    set_public_endpoint(ep)

    # 注册 DID 方法 handlers（ADR-009）
    from agent_net.common.did_methods import register_daemon_handlers
    from agent_net.storage import DB_PATH
    register_daemon_handlers(str(DB_PATH))

    # 初始化 PlaybookEngine（ADR-013 §4）
    from agent_net.enclave.playbook import init_playbook_engine
    from agent_net.node._auth import get_token
    init_playbook_engine(daemon_url=f"http://localhost:{NODE_PORT}", token=get_token())

    # 启动 Push 注册过期清理任务
    _cfg._cleanup_push_task = asyncio.create_task(cleanup_expired_push_registrations_loop())

    print(f"[Node] Started. Public endpoint: {ep}")
    print(f"[Node] Local relay: {get_relay_url()}")

    yield

    if _cfg._heartbeat_task:
        _cfg._heartbeat_task.cancel()
    if _cfg._cleanup_push_task:
        _cfg._cleanup_push_task.cancel()


app = FastAPI(title="AgentNet Node Daemon", version="0.9.5", lifespan=lifespan)

app.include_router(agents.router)
app.include_router(messages.router)
app.include_router(handshake.router)
app.include_router(adapters.router)
app.include_router(push.router)
app.include_router(enclave.router)
app.include_router(governance.router)


def run(host: str = "0.0.0.0", port: int = NODE_PORT):
    uvicorn.run(app, host=host, port=port, log_level="info")
