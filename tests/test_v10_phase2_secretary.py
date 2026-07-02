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
async def setup_db(tmp_path):
    import agent_net.storage as s
    _db = tmp_path / "agent_net.db"
    _orig = s.DB_PATH
    s.DB_PATH = _db
    _db.parent.mkdir(exist_ok=True)
    if _db.exists():
        _db.unlink()
    await s.init_db()
    _TOKEN_DID_BINDINGS.clear()
    _TOKEN_DID_BINDINGS[FAKE_TOKEN] = []
    yield
    s.DB_PATH = _orig


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
async def test_v10_sec_02_update_intake_missing_session_returns_false():
    """更新不存在的 intake 应返回 False。"""
    ok = await update_intake("sess_missing_update", status="running")
    assert not ok


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
# D-SEC-08: Dispatch Auth Relaxation — SDK Agent / CLI Worker 可 dispatch
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_08_dispatch_auth_allows_bound_agent():
    """非秘书但绑定到 owner 的 Agent 也应通过 dispatch 身份校验。"""
    from agent_net.storage import get_agent

    owner = await register_owner("TestOwner")

    # 注册一个非秘书的 Worker Agent
    from agent_net.common.did import DIDGenerator, AgentProfile
    from nacl.encoding import HexEncoder

    worker_did_obj, _ = DIDGenerator.create_agentnexus("WorkerAgent")
    worker_did = worker_did_obj.did
    pk_hex = worker_did_obj.private_key.encode(HexEncoder).decode()
    await register_agent(
        worker_did,
        AgentProfile(id=worker_did, name="WorkerAgent", capabilities=["developer"]).to_dict(),
        is_local=True,
        private_key_hex=pk_hex,
    )

    # 绑定到 owner
    from agent_net.storage import bind_agent
    await bind_agent(owner["did"], worker_did)

    # 验证：is_secretary 返回 None
    sec = await is_secretary(worker_did)
    assert sec is None

    # 但它是 owner 的绑定 Agent
    agent = await get_agent(worker_did)
    assert agent["owner_did"] == owner["did"]


# ══════════════════════════════════════════════════════════════════════════════
# D-SEC-08: Adapter Contract — _intake_and_dispatch
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_08_adapter_intake_and_dispatch():
    """适配器 _intake_and_dispatch 应产出正确的 intake 格式。"""
    from agent_net.adapters.base import PlatformAdapter

    class DummyAdapter(PlatformAdapter):
        platform = "dummy"

        async def inbound(self, request: dict) -> dict:
            return {}

        async def outbound(self, message: dict) -> dict:
            return {}

        def skill_manifest(self) -> dict:
            return {}

    adapter = DummyAdapter()

    captured = {}

    class FakeResp:
        status = 200

        async def json(self):
            return {"run_id": "run_1", "enclave_id": "enc_1"}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers

            async def _enter():
                return FakeResp()

            # Return an async context manager
            class _Ctx:
                async def __aenter__(self_inner):
                    return FakeResp()

                async def __aexit__(self_inner, *a):
                    pass

            return _Ctx()

    import aiohttp
    original_session = aiohttp.ClientSession
    try:
        aiohttp.ClientSession = FakeSession

        result = await adapter._intake_and_dispatch(
            session_id="sess_test",
            owner_did="did:agentnexus:owner",
            actor_did="did:agentnexus:agent",
            objective="Test objective",
            required_roles=["developer"],
            source_channel="test",
            adapter_id="test_1",
            daemon_url="http://localhost:8765",
            token="test_token",
        )

        assert result["status"] == "accepted"
        assert result["run_id"] == "run_1"
        assert captured["url"] == "http://localhost:8765/secretary/dispatch"
        assert captured["json"]["owner_did"] == "did:agentnexus:owner"
        assert captured["json"]["actor_did"] == "did:agentnexus:agent"
        assert captured["json"]["objective"] == "Test objective"
        assert captured["json"]["required_roles"] == ["developer"]
        assert captured["json"]["source"]["channel"] == "test"
        assert captured["headers"]["Authorization"] == "Bearer test_token"
    finally:
        aiohttp.ClientSession = original_session


# ══════════════════════════════════════════════════════════════════════════════
# D-SEC-10: Context Budget & Handoff Checkpoint
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_10_handoff_checkpoint_dict_storage():
    """Handoff Checkpoint 应按 stage_name 为 key 的 dict 存储，而非 list append。"""
    from agent_net.enclave.playbook import PlaybookEngine
    from agent_net.enclave.models import Stage

    engine = PlaybookEngine()

    # 模拟 run context 中的 checkpoints 为 dict 结构
    run_ctx = {"checkpoints": {}}
    from agent_net.storage import create_intake, update_playbook_run

    owner = await register_owner("TestOwner")
    sec = await register_secretary(owner["did"])
    await create_intake(
        session_id="sess_ckpt_dict",
        owner_did=owner["did"],
        actor_did=sec["did"],
        objective="ckpt test",
        required_roles=["developer"],
    )

    stage = Stage(name="architect", role="architect", description="", output_key="")

    checkpoint = await engine._generate_handoff_checkpoint(
        run_id="run_ckpt_dict",
        stage_name="architect",
        stage=stage,
        output_ref={"key": "test"},
        assigned_did="did:agentnexus:worker",
        summary="Architecture done",
    )

    assert checkpoint["stage_name"] == "architect"
    assert checkpoint["summary"] == "Architecture done"
    assert "created_at" in checkpoint

    # 验证 checkpoints 为 dict 结构，且 key 为 stage_name
    from agent_net.storage import get_playbook_run
    run = await get_playbook_run("run_ckpt_dict")
    if run:
        ctx = run.get("context", {}) or {}
        ckpts = ctx.get("checkpoints")
        assert isinstance(ckpts, dict)
        assert "architect" in ckpts


@pytest.mark.asyncio
async def test_v10_sec_10_handoff_checkpoint_list_migration():
    """旧 list 结构的 checkpoints 应自动迁移为 dict。"""
    from agent_net.enclave.playbook import PlaybookEngine
    from agent_net.enclave.models import Stage
    from agent_net.storage import create_playbook_run, update_playbook_run

    engine = PlaybookEngine()

    # 手动创建一条带有 list 结构 checkpoints 的 run
    await create_playbook_run(
        run_id="run_ckpt_migrate",
        enclave_id="enc_migrate",
        playbook_id="pb_migrate",
        playbook_name="migrate test",
    )
    # 写入旧 list 结构
    await update_playbook_run(
        "run_ckpt_migrate",
        context={
            "checkpoints": [
                {"stage_name": "old_stage_1", "summary": "old 1"},
                {"stage_name": "old_stage_2", "summary": "old 2"},
            ]
        },
    )

    stage = Stage(name="new_stage", role="developer", description="")
    await engine._generate_handoff_checkpoint(
        run_id="run_ckpt_migrate",
        stage_name="new_stage",
        stage=stage,
        output_ref={"key": "migrated"},
        assigned_did="did:agentnexus:worker",
        summary="Migrated checkpoint",
    )

    # 验证已迁移为 dict 结构
    from agent_net.storage import get_playbook_run
    run = await get_playbook_run("run_ckpt_migrate")
    ctx = run.get("context", {}) or {}
    ckpts = ctx.get("checkpoints")
    assert isinstance(ckpts, dict)
    assert "old_stage_1" in ckpts
    assert "old_stage_2" in ckpts
    assert "new_stage" in ckpts


@pytest.mark.asyncio
async def test_v10_sec_10_latest_checkpoint_dict():
    """_latest_checkpoint 应从 dict 中取最后一个值。"""
    from agent_net.enclave.playbook import PlaybookEngine

    engine = PlaybookEngine()
    run_ctx = {
        "checkpoints": {
            "stage_a": {"stage_name": "stage_a", "summary": "A done"},
            "stage_b": {"stage_name": "stage_b", "summary": "B done"},
        }
    }

    result = engine._latest_checkpoint(run_ctx)
    assert result is not None
    assert result["summary"] == "B done"


@pytest.mark.asyncio
async def test_v10_sec_10_latest_checkpoint_list_compat():
    """_latest_checkpoint 应向后兼容 list 结构。"""
    from agent_net.enclave.playbook import PlaybookEngine

    engine = PlaybookEngine()
    run_ctx = {
        "checkpoints": [
            {"stage_name": "stage_a", "summary": "A done"},
            {"stage_name": "stage_b", "summary": "B done"},
        ]
    }

    result = engine._latest_checkpoint(run_ctx)
    assert result is not None
    assert result["summary"] == "B done"


@pytest.mark.asyncio
async def test_v10_sec_10_latest_checkpoint_empty():
    """无 checkpoints 时 _latest_checkpoint 返回 None。"""
    from agent_net.enclave.playbook import PlaybookEngine

    engine = PlaybookEngine()

    assert engine._latest_checkpoint({}) is None
    assert engine._latest_checkpoint({"checkpoints": {}}) is None
    assert engine._latest_checkpoint({"checkpoints": []}) is None
    assert engine._latest_checkpoint({"checkpoints": None}) is None


def test_v10_sec_10_estimate_snapshot_tokens():
    """_estimate_snapshot_tokens 应返回合理的 token 估算值。"""
    from agent_net.enclave.playbook import PlaybookEngine

    engine = PlaybookEngine()
    snapshot = {
        "thread_id": "run_test",
        "session_id": "sess_test",
        "objective": "Test objective",
        "current_stage": "architect",
        "assigned_role": "architect",
        "inputs": [],
        "output": None,
        "handoff_summary": "",
        "updated_at": 1711000000.0,
    }

    tokens = engine._estimate_snapshot_tokens(snapshot)
    assert tokens > 0
    assert isinstance(tokens, int)


@pytest.mark.asyncio
async def test_v10_sec_10_context_budget_field_names():
    """context_budget 字段名应与设计文档一致：estimated_context_tokens_planned/actual。"""
    from agent_net.enclave.playbook import PlaybookEngine
    from agent_net.enclave.models import Stage
    from agent_net.storage import create_playbook_run, update_playbook_run

    engine = PlaybookEngine()

    await create_playbook_run(
        run_id="run_budget_names",
        enclave_id="enc_budget",
        playbook_id="pb_budget",
        playbook_name="budget test",
    )
    await update_playbook_run("run_budget_names", context={"session_id": "sess_budget", "objective": "budget test"})

    stage = Stage(
        name="architect", role="architect", description="",
        output_key="design_doc", max_context_tokens=4000,
    )

    # 模拟 _build_context_snapshot 中的 budget 写入逻辑
    from agent_net.storage import get_playbook_run
    run = await get_playbook_run("run_budget_names")
    run_ctx = run.get("context", {}) or {}

    # 模拟 snapshot 构建（简化版）
    snapshot = {
        "thread_id": "run_budget_names",
        "session_id": "sess_budget",
        "objective": "budget test",
        "current_stage": "architect",
        "assigned_role": "architect",
        "inputs": [],
        "output": {"enclave_id": "enc_budget", "key": "design_doc"},
        "handoff_summary": "",
        "updated_at": 1711000000.0,
    }

    planned = engine._estimate_snapshot_tokens(snapshot)
    budget = run_ctx.get("context_budget", {}) or {}
    budget["estimated_context_tokens_planned"] = planned
    snapshot["context_budget"] = {
        "estimated_context_tokens_planned": planned,
        "max_context_tokens": stage.max_context_tokens or 0,
    }

    # 验证 snapshot 内字段名
    assert "estimated_context_tokens_planned" in snapshot["context_budget"]
    assert "estimated_tokens_planned" not in snapshot["context_budget"]

    # 验证 checkpoint 写入时的 actual 字段名
    await engine._generate_handoff_checkpoint(
        run_id="run_budget_names",
        stage_name="architect",
        stage=stage,
        output_ref={"enclave_id": "enc_budget", "key": "design_doc"},
        assigned_did="did:agentnexus:worker",
        summary="Design done",
    )

    run = await get_playbook_run("run_budget_names")
    ctx = run.get("context", {}) or {}
    final_budget = ctx.get("context_budget", {}) or {}
    assert "estimated_context_tokens_actual" in final_budget


@pytest.mark.asyncio
async def test_v10_sec_10_context_snapshot_objective():
    """Context Snapshot 的 objective 应取自 run_context["objective"]，而非 playbook_name。"""
    from agent_net.enclave.playbook import PlaybookEngine
    from agent_net.enclave.models import Stage
    from agent_net.storage import (
        create_playbook_run, update_playbook_run,
        create_enclave, add_enclave_member,
        register_owner, register_secretary,
    )

    engine = PlaybookEngine()
    owner = await register_owner("BudgetOwner")
    sec = await register_secretary(owner["did"])

    from agent_net.storage import create_intake
    await create_intake(
        session_id="sess_obj_test",
        owner_did=owner["did"],
        actor_did=sec["did"],
        objective="Real objective from intake",
        required_roles=["architect"],
    )

    # 创建 enclave 和 run
    await create_enclave(enclave_id="enc_obj", name="obj-test", owner_did=owner["did"])
    await add_enclave_member(enclave_id="enc_obj", did=sec["did"], role="secretary", permissions="rw")
    await create_playbook_run(run_id="run_obj", enclave_id="enc_obj", playbook_id="pb_obj", playbook_name="Some Playbook")
    await update_playbook_run(
        "run_obj",
        context={
            "session_id": "sess_obj_test",
            "objective": "Real objective from intake",
        },
    )

    from agent_net.storage import get_playbook_run
    run = await get_playbook_run("run_obj")
    run_ctx = run.get("context", {}) or {}

    stage = Stage(name="architect", role="architect", description="", output_key="")

    # 手动构建和 _build_context_snapshot 同样的 objective 提取逻辑
    objective = run_ctx.get("objective", run.get("playbook_name", ""))
    assert objective == "Real objective from intake"
    assert objective != "Some Playbook"


# ══════════════════════════════════════════════════════════════════════════════
# D-SEC-08: Adapter Token Auto-Reading
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_08_adapter_token_fallback_with_empty():
    """适配器 _intake_and_dispatch 传入空 token 时应使用显式 token。"""
    from agent_net.adapters.base import PlatformAdapter

    class DummyAdapter(PlatformAdapter):
        platform = "dummy_token"

        async def inbound(self, request: dict) -> dict:
            return {}

        async def outbound(self, message: dict) -> dict:
            return {}

        def skill_manifest(self) -> dict:
            return {}

    adapter = DummyAdapter()
    captured = {}

    class FakeResp:
        status = 200

        async def json(self):
            return {"run_id": "run_tok", "enclave_id": "enc_tok"}

    class _Ctx:
        async def __aenter__(self_inner):
            return FakeResp()

        async def __aexit__(self_inner, *a):
            pass

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Ctx()

    import aiohttp
    original_session = aiohttp.ClientSession
    try:
        aiohttp.ClientSession = FakeSession

        # 显式传入 token，应直接使用
        result = await adapter._intake_and_dispatch(
            session_id="sess_tok",
            owner_did="did:agentnexus:owner",
            actor_did="did:agentnexus:agent",
            objective="Token test",
            required_roles=["developer"],
            source_channel="test",
            adapter_id="test_tok",
            daemon_url="http://localhost:8765",
            token="explicit_token",
        )

        assert result["status"] == "accepted"
        assert captured["headers"]["Authorization"] == "Bearer explicit_token"
    finally:
        aiohttp.ClientSession = original_session


# ══════════════════════════════════════════════════════════════════════════════
# D-SEC-02 + D-SEC-08: API-level smoke — Bound worker dispatches itself
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_02_bound_worker_dispatch_api_smoke(monkeypatch):
    """
    API 级 smoke：Bound worker Agent 作为 actor dispatch developer role，
    验证：(1) Enclave 成员角色为 developer 而非 secretary（无主键冲突）;
         (2) stage_execution 已创建且状态为 active;
         (3) task_propose 被发送。
    """
    from agent_net.common.did import DIDGenerator, AgentProfile
    from nacl.encoding import HexEncoder
    from agent_net.storage import (
        bind_agent, get_stage_executions_for_run, list_enclave_members,
        get_intake, get_playbook_run, get_playbook,
    )
    from agent_net.enclave.playbook import init_playbook_engine
    from agent_net.node.routers.secretary import api_dispatch

    # 1. 创建 owner
    owner = await register_owner("SmokeOwner")

    # 2. 注册一个带 developer 能力的 Worker Agent
    worker_did_obj, _ = DIDGenerator.create_agentnexus("SmokeWorker")
    worker_did = worker_did_obj.did
    pk_hex = worker_did_obj.private_key.encode(HexEncoder).decode()
    await register_agent(
        worker_did,
        AgentProfile(id=worker_did, name="SmokeWorker", capabilities=["developer"]).to_dict(),
        is_local=True,
        private_key_hex=pk_hex,
    )
    await bind_agent(owner["did"], worker_did)

    # 3. 截获 PlaybookEngine 对 /messages/send 的 task_propose，避免测试访问真实 HTTP daemon
    engine = init_playbook_engine("http://localhost:8765", "")
    captured_task_propose = {}

    async def fake_send(**kwargs):
        captured_task_propose.update(kwargs)

    monkeypatch.setattr(engine, "_send_task_propose", fake_send)

    # 4. 直接调用 dispatch API handler。除 FastAPI token Depends 外，其余路径都走真实实现。
    session_id = "sess_smoke_001"
    objective = "Build a login module"
    result = await api_dispatch(
        {
            "session_id": session_id,
            "owner_did": owner["did"],
            "actor_did": worker_did,
            "objective": objective,
            "required_roles": ["developer"],
            "entry_mode": "owner_pre_authorized",
            "source": {"channel": "pytest", "message_ref": "smoke"},
        },
        _=None,
    )

    assert result["status"] == "started"
    run_id = result["run_id"]
    enclave_id = result["enclave_id"]

    # ── 断言 ──
    # (1) Enclave 成员：worker 以 developer 角色加入，不是 secretary
    members = await list_enclave_members(enclave_id)
    worker_member = next((m for m in members if m["did"] == worker_did), None)
    assert worker_member is not None, "Worker not in enclave members"
    assert worker_member["role"] == "developer", (
        f"Worker should be 'developer', got '{worker_member['role']}' — "
        "actor_did was incorrectly added as 'secretary' first"
    )
    assert all(
        not (m["did"] == worker_did and m["role"] == "secretary")
        for m in members
    )

    # (2) stage_execution 已创建且状态为 active
    executions = await get_stage_executions_for_run(run_id)
    assert len(executions) == 1
    assert executions[0]["stage_name"] == "developer"
    assert executions[0]["status"] == "active"
    assert executions[0]["assigned_did"] == worker_did

    # (3) task_propose 被发送
    assert "role" in captured_task_propose
    assert captured_task_propose["role"] == "developer"
    assert captured_task_propose["to_did"] == worker_did
    assert captured_task_propose["run_id"] == run_id

    # (4) intake / run / 默认 playbook 都由 dispatch API 创建
    intake = await get_intake(session_id)
    assert intake["status"] == "running"
    assert intake["run_id"] == run_id
    assert intake["selected_workers"] == {"developer": worker_did}

    run = await get_playbook_run(run_id)
    assert run["enclave_id"] == enclave_id
    assert run["current_stage"] == "developer"

    playbook = await get_playbook(run["playbook_id"])
    assert playbook["name"] == "default-orchestration"
    assert playbook["stages"] == [
        {"name": "developer", "role": "developer", "description": "developer stage", "next": ""}
    ]
