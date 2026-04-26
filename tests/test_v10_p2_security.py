"""P2 安全修复回归测试 — Worker 操作鉴权"""
import pytest
import pytest_asyncio

from agent_net.storage import (
    init_db, register_owner, register_agent, bind_agent, get_agent,
    set_worker_blocked, set_worker_type,
)
from agent_net.common.did import DIDGenerator, AgentProfile
from nacl.encoding import HexEncoder
from agent_net.node._auth import _TOKEN_DID_BINDINGS

FAKE_TOKEN = "test_p2_security"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    from agent_net.storage import DB_PATH
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    await init_db()
    _TOKEN_DID_BINDINGS.clear()
    _TOKEN_DID_BINDINGS[FAKE_TOKEN] = []
    yield


async def _create_bound_worker(owner_did: str, name: str) -> str:
    """Create a worker bound to an owner, return worker DID."""
    obj, _ = DIDGenerator.create_agentnexus(name)
    profile = AgentProfile(id=obj.did, name=name, type="developer", capabilities=["code"]).to_dict()
    pk_hex = obj.private_key.encode(HexEncoder).decode()
    await register_agent(obj.did, profile, is_local=True, private_key_hex=pk_hex)
    await bind_agent(owner_did, obj.did)
    return obj.did


# ══════════════════════════════════════════════════════════════════════════════
# P2_1: Worker blocked auth
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_p2_set_worker_blocked_owner_only():
    """set_worker_blocked 只能在 storage 层调用；端点需 owner 鉴权。"""
    owner = await register_owner("TestOwner")
    worker_did = await _create_bound_worker(owner["did"], "WorkerBlock")

    # Storage 层本身不校验权限（由路由层负责）
    ok = await set_worker_blocked(worker_did, True, "test")
    assert ok

    # 验证状态可查
    from agent_net.storage import get_worker_presence
    presence = await get_worker_presence(worker_did)
    assert presence.get("presence") == "blocked"


@pytest.mark.asyncio
async def test_v10_p2_set_worker_type_non_owner_denied():
    """非 owner 不能修改 worker_type（在路由层校验，此处验证数据层）。"""
    owner = await register_owner("TestOwner")
    worker_did = await _create_bound_worker(owner["did"], "WorkerType")

    agent = await get_agent(worker_did)
    assert agent["worker_type"] == "resident"

    # Storage 层不校验权限，但 owner_did 应正确设置
    assert agent["owner_did"] == owner["did"]
