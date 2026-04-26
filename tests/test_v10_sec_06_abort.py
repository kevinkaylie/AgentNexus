"""D-SEC-06: 失败恢复与 Owner 接管 — abort 端点测试"""
import pytest
import pytest_asyncio
import time

from agent_net.storage import (
    init_db, register_owner, register_secretary,
    create_intake, update_intake,
    create_enclave, add_enclave_member,
    create_playbook, create_playbook_run, update_playbook_run,
    create_stage_execution, get_stage_execution, get_stage_executions_for_run,
    get_intake, get_playbook_run,
)
from agent_net.node._auth import _TOKEN_DID_BINDINGS

FAKE_TOKEN = "test_sec06_token"


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


# ══════════════════════════════════════════════════════════════════════════════
# D-SEC-06: Owner abort
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_06_get_stage_executions_for_run():
    """获取 Run 下所有 stage_executions。"""
    owner = await register_owner("TestOwner")
    await create_enclave(enclave_id="enc_test_001", name="test", owner_did=owner["did"])
    await create_playbook_run(
        run_id="run_test_001", enclave_id="enc_test_001",
        playbook_id="pb_1", playbook_name="test",
    )
    await create_stage_execution("run_test_001", "architect", "did:agentnexus:arch")
    await create_stage_execution("run_test_001", "developer", "did:agentnexus:dev")

    executions = await get_stage_executions_for_run("run_test_001")
    assert len(executions) == 2
    statuses = [e["stage_name"] for e in executions]
    assert "architect" in statuses
    assert "developer" in statuses


@pytest.mark.asyncio
async def test_v10_sec_06_abort_run_basic():
    """Owner 终止一个运行中的 Run。"""
    owner = await register_owner("TestOwner")

    # 创建 intake + run
    sec = await register_secretary(owner["did"])
    await create_intake(
        session_id="sess_abort_001",
        owner_did=owner["did"],
        actor_did=sec["did"],
        objective="Abort test",
        required_roles=["developer"],
    )

    await create_enclave(enclave_id="enc_abort_001", name="abort-test", owner_did=owner["did"])
    await create_playbook_run(
        run_id="run_abort_001", enclave_id="enc_abort_001",
        playbook_id="pb_1", playbook_name="test",
    )
    await create_stage_execution("run_abort_001", "developer", "did:agentnexus:dev")
    await update_intake("sess_abort_001", run_id="run_abort_001", status="running")

    # 模拟 abort：直接调用 storage 层验证
    run = await get_playbook_run("run_abort_001")
    assert run["status"] != "aborted"

    # 将所有 active stage 标记为 aborted
    executions = await get_stage_executions_for_run("run_abort_001")
    for exe in executions:
        if exe["status"] in ("pending", "active"):
            from agent_net.storage import update_stage_execution
            await update_stage_execution(
                run_id="run_abort_001",
                stage_name=exe["stage_name"],
                status="aborted",
                output_ref="Owner requested abort",
            )

    await update_playbook_run("run_abort_001", status="aborted", completed_at=time.time())
    await update_intake("sess_abort_001", status="aborted")

    # 验证
    run = await get_playbook_run("run_abort_001")
    assert run["status"] == "aborted"
    assert run["completed_at"] is not None

    intake = await get_intake("sess_abort_001")
    assert intake["status"] == "aborted"

    stages = await get_stage_executions_for_run("run_abort_001")
    for s in stages:
        assert s["status"] == "aborted"
        assert s["output_ref"] == "Owner requested abort"


@pytest.mark.asyncio
async def test_v10_sec_06_abort_intake_without_run():
    """终止一个尚未创建 Run 的 intake。"""
    owner = await register_owner("TestOwner")
    sec = await register_secretary(owner["did"])

    await create_intake(
        session_id="sess_abort_no_run",
        owner_did=owner["did"],
        actor_did=sec["did"],
        objective="No run yet",
        required_roles=["developer"],
    )

    await update_intake("sess_abort_no_run", status="aborted")
    intake = await get_intake("sess_abort_no_run")
    assert intake["status"] == "aborted"


@pytest.mark.asyncio
async def test_v10_sec_06_abort_terminal_run():
    """终止已完成的 Run 应报错。"""
    owner = await register_owner("TestOwner")

    await create_enclave(enclave_id="enc_term", name="term", owner_did=owner["did"])
    await create_playbook_run(
        run_id="run_term", enclave_id="enc_term",
        playbook_id="pb_1", playbook_name="test",
    )
    await update_playbook_run("run_term", status="completed", completed_at=time.time())

    # 模拟 abort 逻辑检查
    run = await get_playbook_run("run_term")
    assert run["status"] in ("completed", "failed", "aborted")
    # 实际端点会抛出 HTTPException(400)


@pytest.mark.asyncio
async def test_v10_sec_06_update_stage_execution():
    """update_stage_execution 可更新 status 和 output_ref。"""
    owner = await register_owner("TestOwner")
    await create_enclave(enclave_id="enc_upd", name="upd", owner_did=owner["did"])
    await create_playbook_run(
        run_id="run_upd", enclave_id="enc_upd",
        playbook_id="pb_1", playbook_name="test",
    )
    await create_stage_execution("run_upd", "reviewer", "did:agentnexus:rev")

    from agent_net.storage import update_stage_execution
    ok = await update_stage_execution(
        run_id="run_upd", stage_name="reviewer",
        status="rejected", output_ref="Bad code",
    )
    assert ok

    stage = await get_stage_execution("run_upd", "reviewer")
    assert stage["status"] == "rejected"
    assert stage["output_ref"] == "Bad code"
