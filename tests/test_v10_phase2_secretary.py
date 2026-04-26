"""Phase 2 秘书编排测试 — D-SEC-01 / D-SEC-02"""
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from agent_net.storage import (
    init_db, register_owner, register_agent, register_secretary,
    list_workers, set_worker_type,
    create_intake, get_intake, update_intake, list_intakes,
    is_secretary,
)
from agent_net.node._auth import _TOKEN_DID_BINDINGS

FAKE_TOKEN = "test_phase2_token"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    import aiosqlite
    from agent_net.storage import DB_PATH
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    await init_db()
    _TOKEN_DID_BINDINGS.clear()
    _TOKEN_DID_BINDINGS[FAKE_TOKEN] = []
    yield


def _auth_header():
    return {"Authorization": f"Bearer {FAKE_TOKEN}"}


# ══════════════════════════════════════════════════════════════════════════════
# D-SEC-01: Worker Registry
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_01_register_owner_and_secretary():
    """注册 owner + secretary，验证秘书身份。"""
    owner = await register_owner("TestOwner")
    sec = await register_secretary(owner["did"], "MySecretary")

    assert sec["did"].startswith("did:agentnexus:")
    assert sec["profile"]["type"] == "secretary"

    sec_record = await is_secretary(sec["did"])
    assert sec_record is not None
    assert sec_record["profile"]["type"] == "secretary"
    assert sec_record["owner_did"] == owner["did"]


@pytest.mark.asyncio
async def test_v10_sec_01_worker_type_default():
    """Agent 注册默认 worker_type = resident。"""
    owner = await register_owner("TestOwner")
    from agent_net.common.did import DIDGenerator, AgentProfile
    from nacl.encoding import HexEncoder
    from agent_net.storage import bind_agent, get_agent
    obj, _ = DIDGenerator.create_agentnexus("Worker1")
    profile = AgentProfile(id=obj.did, name="Worker1", type="developer", capabilities=["code"]).to_dict()
    profile["tags"] = ["dev"]
    pk_hex = obj.private_key.encode(HexEncoder).decode()
    await register_agent(obj.did, profile, is_local=True, private_key_hex=pk_hex, worker_type="resident")
    await bind_agent(owner["did"], obj.did)

    agent = await get_agent(obj.did)
    assert agent["worker_type"] == "resident"


@pytest.mark.asyncio
async def test_v10_sec_01_set_worker_type():
    """设置 worker_type。"""
    owner = await register_owner("TestOwner")
    from agent_net.common.did import DIDGenerator, AgentProfile
    from nacl.encoding import HexEncoder
    from agent_net.storage import bind_agent, get_agent
    obj, _ = DIDGenerator.create_agentnexus("Worker2")
    profile = AgentProfile(id=obj.did, name="Worker2", type="developer", capabilities=["code"]).to_dict()
    profile["tags"] = ["dev"]
    pk_hex = obj.private_key.encode(HexEncoder).decode()
    await register_agent(obj.did, profile, is_local=True, private_key_hex=pk_hex)
    await bind_agent(owner["did"], obj.did)

    ok = await set_worker_type(obj.did, "interactive_cli")
    assert ok

    agent = await get_agent(obj.did)
    assert agent["worker_type"] == "interactive_cli"


@pytest.mark.asyncio
async def test_v10_sec_01_list_workers_excludes_secretary():
    """list_workers 不应包含秘书子 Agent。"""
    owner = await register_owner("TestOwner")
    await register_secretary(owner["did"])

    from agent_net.common.did import DIDGenerator, AgentProfile
    from nacl.encoding import HexEncoder
    from agent_net.storage import bind_agent
    workers_data = []
    for i in range(3):
        obj, _ = DIDGenerator.create_agentnexus(f"Worker{i}")
        profile = AgentProfile(
            id=obj.did, name=f"Worker{i}", type="developer",
            capabilities=["code", f"role{i}"]
        ).to_dict()
        profile["tags"] = [f"tag{i}"]
        pk_hex = obj.private_key.encode(HexEncoder).decode()
        await register_agent(obj.did, profile, is_local=True, private_key_hex=pk_hex)
        await bind_agent(owner["did"], obj.did)
        workers_data.append(obj.did)

    workers = await list_workers(owner["did"])
    assert len(workers) == 3
    for w in workers:
        assert w["profile_type"] != "secretary"


@pytest.mark.asyncio
async def test_v10_sec_01_worker_registry_fields():
    """Worker Registry 返回字段完整性。"""
    owner = await register_owner("TestOwner")
    from agent_net.common.did import DIDGenerator, AgentProfile
    from nacl.encoding import HexEncoder
    from agent_net.storage import bind_agent
    obj, _ = DIDGenerator.create_agentnexus("WorkerFields")
    profile = AgentProfile(
        id=obj.did, name="WorkerFields", type="architect",
        capabilities=["design", "adr"]
    ).to_dict()
    profile["tags"] = ["python", "docs"]
    pk_hex = obj.private_key.encode(HexEncoder).decode()
    await register_agent(obj.did, profile, is_local=True, private_key_hex=pk_hex, worker_type="resident")
    await bind_agent(owner["did"], obj.did)

    workers = await list_workers(owner["did"])
    assert len(workers) == 1
    w = workers[0]
    assert w["did"] == obj.did
    assert w["worker_type"] == "resident"
    assert w["profile_type"] == "architect"
    assert "design" in w["capabilities"]
    assert "python" in w["tags"]
    assert "online" in w
    assert "last_seen" in w


# ══════════════════════════════════════════════════════════════════════════════
# D-SEC-02: Intake 流程
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_02_create_intake():
    """创建 intake 记录。"""
    owner = await register_owner("TestOwner")
    sec = await register_secretary(owner["did"])

    intake = await create_intake(
        session_id="sess_test_001",
        owner_did=owner["did"],
        actor_did=sec["did"],
        objective="Test objective",
        required_roles=["architect", "reviewer"],
        preferred_playbook="pb_default",
        source_channel="webhook",
        source_message_ref="msg_123",
    )
    assert intake["status"] == "intake"
    assert intake["session_id"] == "sess_test_001"
    assert intake["required_roles"] == ["architect", "reviewer"]


@pytest.mark.asyncio
async def test_v10_sec_02_get_intake():
    """获取 intake 记录。"""
    owner = await register_owner("TestOwner")
    sec = await register_secretary(owner["did"])

    await create_intake(
        session_id="sess_test_002",
        owner_did=owner["did"],
        actor_did=sec["did"],
        objective="Get test",
        required_roles=["developer"],
    )

    retrieved = await get_intake("sess_test_002")
    assert retrieved is not None
    assert retrieved["objective"] == "Get test"
    assert retrieved["status"] == "intake"


@pytest.mark.asyncio
async def test_v10_sec_02_update_intake_status():
    """更新 intake 状态。"""
    owner = await register_owner("TestOwner")
    sec = await register_secretary(owner["did"])

    await create_intake(
        session_id="sess_test_003",
        owner_did=owner["did"],
        actor_did=sec["did"],
        objective="Update test",
        required_roles=["developer"],
    )

    ok = await update_intake("sess_test_003", status="running", run_id="run_abc123")
    assert ok

    retrieved = await get_intake("sess_test_003")
    assert retrieved["status"] == "running"
    assert retrieved["run_id"] == "run_abc123"


@pytest.mark.asyncio
async def test_v10_sec_02_update_intake_selected_workers():
    """更新 intake 的 selected_workers。"""
    owner = await register_owner("TestOwner")
    sec = await register_secretary(owner["did"])

    await create_intake(
        session_id="sess_test_004",
        owner_did=owner["did"],
        actor_did=sec["did"],
        objective="Workers test",
        required_roles=["developer"],
    )

    ok = await update_intake(
        "sess_test_004",
        selected_workers={"developer": "did:agentnexus:worker1"},
    )
    assert ok

    retrieved = await get_intake("sess_test_004")
    assert retrieved["selected_workers"]["developer"] == "did:agentnexus:worker1"


@pytest.mark.asyncio
async def test_v10_sec_02_list_intakes():
    """列出 owner 的 intake 记录。"""
    owner = await register_owner("TestOwner")
    sec = await register_secretary(owner["did"])

    for i in range(3):
        await create_intake(
            session_id=f"sess_list_{i}",
            owner_did=owner["did"],
            actor_did=sec["did"],
            objective=f"List test {i}",
            required_roles=["developer"],
        )

    intakes = await list_intakes(owner["did"])
    assert len(intakes) == 3


@pytest.mark.asyncio
async def test_v10_sec_02_is_secretary_non_secretary():
    """非秘书 DID 的 is_secretary 返回 None。"""
    owner = await register_owner("TestOwner")
    result = await is_secretary(owner["did"])
    assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# HTTP 端点测试 — 需要 conftest.py http_client fixture，暂略
# ══════════════════════════════════════════════════════════════════════════════
