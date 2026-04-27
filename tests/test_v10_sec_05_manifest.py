"""D-SEC-05: Delivery Manifest 稳定版测试"""
import json
import asyncio
import pytest
import pytest_asyncio

from agent_net.storage import (
    init_db, register_owner,
    create_enclave, add_enclave_member,
    create_playbook, create_playbook_run, update_playbook_run,
    create_stage_execution, get_stage_execution, get_stage_executions_for_run,
    get_playbook_run, get_enclave,
    store_stage_manifest, store_final_manifest, vault_get, vault_put,
)
from agent_net.node._auth import _TOKEN_DID_BINDINGS

FAKE_TOKEN = "test_sec05_token"


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
# D-SEC-05: Stage Delivery Manifest
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_05_store_stage_manifest():
    """生成并存储 Stage Delivery Manifest。"""
    owner = await register_owner("TestOwner")
    await create_enclave(enclave_id="enc_manifest_001", name="test", owner_did=owner["did"])
    await create_playbook_run(
        run_id="run_manifest_001", enclave_id="enc_manifest_001",
        playbook_id="pb_1", playbook_name="test",
    )
    await create_stage_execution("run_manifest_001", "design", "did:agentnexus:arch")

    manifest = await store_stage_manifest(
        run_id="run_manifest_001",
        stage_name="design",
        status="completed",
        artifacts=[
            {
                "kind": "design_doc",
                "ref": {"enclave_id": "enc_manifest_001", "key": "design/spec.md"},
                "produced_by": "did:agentnexus:arch",
                "summary": "Architecture design",
                "checksum": "sha256:abc123",
            }
        ],
        required_outputs=["design_doc"],
        produced_by="did:agentnexus:arch",
    )

    assert manifest["manifest_id"] == "manifest_design_run_manifest_001"
    assert manifest["run_id"] == "run_manifest_001"
    assert manifest["stage_name"] == "design"
    assert manifest["status"] == "completed"
    assert len(manifest["artifacts"]) == 1
    assert manifest["artifacts"][0]["kind"] == "design_doc"
    assert manifest["missing_outputs"] == []
    assert manifest["produced_by"] == "did:agentnexus:arch"
    assert "created_at" in manifest


@pytest.mark.asyncio
async def test_v10_sec_05_store_stage_manifest_missing_outputs():
    """Stage Manifest 正确计算 missing_outputs。"""
    owner = await register_owner("TestOwner")
    await create_enclave(enclave_id="enc_missing", name="test", owner_did=owner["did"])
    await create_playbook_run(
        run_id="run_missing", enclave_id="enc_missing",
        playbook_id="pb_1", playbook_name="test",
    )

    manifest = await store_stage_manifest(
        run_id="run_missing",
        stage_name="review",
        status="completed",
        artifacts=[],  # 没有产出
        required_outputs=["review_report", "code_review"],
        produced_by="did:agentnexus:rev",
    )

    assert len(manifest["missing_outputs"]) == 2
    assert "review_report" in manifest["missing_outputs"]
    assert "code_review" in manifest["missing_outputs"]


@pytest.mark.asyncio
async def test_v10_sec_05_store_stage_manifest_vault_write():
    """Stage Manifest 写入 Vault。"""
    owner = await register_owner("TestOwner")
    await create_enclave(enclave_id="enc_vault_manifest", name="test", owner_did=owner["did"])
    await create_playbook_run(
        run_id="run_vault_manifest", enclave_id="enc_vault_manifest",
        playbook_id="pb_1", playbook_name="test",
    )

    await store_stage_manifest(
        run_id="run_vault_manifest",
        stage_name="impl",
        status="completed",
        artifacts=[{"kind": "code", "ref": "test"}],
        required_outputs=["code"],
        produced_by="did:agentnexus:dev",
    )

    # 验证 Vault 写入
    vault_key = "manifests/run_vault_manifest/impl"
    result = await vault_get("enc_vault_manifest", vault_key)
    assert result is not None
    stored = json.loads(result["value"])
    assert stored["manifest_id"] == "manifest_impl_run_vault_manifest"
    assert stored["stage_name"] == "impl"


# ══════════════════════════════════════════════════════════════════════════════
# D-SEC-05: Final Delivery Manifest
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_05_store_final_manifest():
    """生成并存储 Final Delivery Manifest。"""
    owner = await register_owner("TestOwner")
    await create_enclave(enclave_id="enc_final", name="test", owner_did=owner["did"])
    await create_playbook_run(
        run_id="run_final", enclave_id="enc_final",
        playbook_id="pb_1", playbook_name="test",
    )

    manifest = await store_final_manifest(
        run_id="run_final",
        status="completed",
        summary="All stages completed successfully",
        stage_manifest_ids=[
            "manifest_design_run_final",
            "manifest_review_run_final",
            "manifest_impl_run_final",
        ],
        final_artifacts=[
            {"kind": "summary", "ref": {"enclave_id": "enc_final", "key": "final/summary.md"}},
            {"kind": "design_doc", "ref": {"enclave_id": "enc_final", "key": "design/spec.md"}},
        ],
        produced_by="did:agentnexus:secretary",
    )

    assert manifest["manifest_id"] == "manifest_final_run_final"
    assert manifest["run_id"] == "run_final"
    assert manifest["status"] == "completed"
    assert manifest["summary"] == "All stages completed successfully"
    assert len(manifest["stage_manifests"]) == 3
    assert len(manifest["final_artifacts"]) == 2
    assert manifest["final_status"] == "completed"
    assert manifest["produced_by"] == "did:agentnexus:secretary"


@pytest.mark.asyncio
async def test_v10_sec_05_store_final_manifest_vault_write():
    """Final Manifest 写入 Vault。"""
    owner = await register_owner("TestOwner")
    await create_enclave(enclave_id="enc_final_vault", name="test", owner_did=owner["did"])
    await create_playbook_run(
        run_id="run_final_vault", enclave_id="enc_final_vault",
        playbook_id="pb_1", playbook_name="test",
    )

    await store_final_manifest(
        run_id="run_final_vault",
        status="completed",
        summary="Final result",
        stage_manifest_ids=["manifest_design_run_final_vault"],
        final_artifacts=[{"kind": "summary", "ref": "final/summary"}],
        produced_by="did:agentnexus:secretary",
    )

    vault_key = "manifests/run_final_vault/final"
    result = await vault_get("enc_final_vault", vault_key)
    assert result is not None
    stored = json.loads(result["value"])
    assert stored["manifest_id"] == "manifest_final_run_final_vault"


@pytest.mark.asyncio
async def test_v10_sec_05_final_manifest_partial_status():
    """Final Manifest 支持 partial 状态。"""
    owner = await register_owner("TestOwner")
    await create_enclave(enclave_id="enc_partial", name="test", owner_did=owner["did"])
    await create_playbook_run(
        run_id="run_partial", enclave_id="enc_partial",
        playbook_id="pb_1", playbook_name="test",
    )

    manifest = await store_final_manifest(
        run_id="run_partial",
        status="partial",
        summary="Some stages failed",
        stage_manifest_ids=["manifest_design_run_partial"],
        final_artifacts=[{"kind": "summary", "ref": "final/summary"}],
        produced_by="did:agentnexus:secretary",
    )

    assert manifest["final_status"] == "partial"
    assert manifest["status"] == "partial"


@pytest.mark.asyncio
async def test_v10_sec_05_playbook_completion_preserves_artifact_refs():
    """Worker output_ref 为 artifact ref 时，Stage/Final Manifest 应保留原始产物引用。"""
    owner = await register_owner("TestOwner")
    worker_did = "did:agentnexus:dev"
    await create_enclave(enclave_id="enc_engine_manifest", name="test", owner_did=owner["did"])
    await add_enclave_member("enc_engine_manifest", worker_did, "developer")
    await create_playbook(
        playbook_id="pb_engine_manifest",
        name="engine-manifest",
        stages=[{
            "name": "impl",
            "role": "developer",
            "description": "Implement",
            "input_keys": [],
            "output_key": "impl/diff.patch",
            "next": "",
        }],
        created_by=owner["did"],
    )
    await create_playbook_run(
        run_id="run_engine_manifest",
        enclave_id="enc_engine_manifest",
        playbook_id="pb_engine_manifest",
        playbook_name="engine-manifest",
    )
    await create_stage_execution(
        "run_engine_manifest",
        "impl",
        worker_did,
        task_id="task_engine_manifest",
    )

    artifact_ref = {"enclave_id": "enc_engine_manifest", "key": "impl/diff.patch"}
    await vault_put(
        "enc_engine_manifest",
        "impl/diff.patch",
        "patch content",
        author_did=worker_did,
    )

    from agent_net.enclave.playbook import PlaybookEngine
    engine = PlaybookEngine()
    await engine.on_stage_completed("run_engine_manifest", "impl", output_ref=artifact_ref)

    stage = await get_stage_execution("run_engine_manifest", "impl")
    stage_output_ref = json.loads(stage["output_ref"])
    assert stage_output_ref == {
        "enclave_id": "enc_engine_manifest",
        "key": "manifests/run_engine_manifest/impl",
    }

    stage_manifest_entry = await vault_get("enc_engine_manifest", "manifests/run_engine_manifest/impl")
    stage_manifest = json.loads(stage_manifest_entry["value"])
    assert stage_manifest["artifacts"][0]["ref"] == artifact_ref

    final_manifest_entry = await vault_get("enc_engine_manifest", "manifests/run_engine_manifest/final")
    final_manifest = json.loads(final_manifest_entry["value"])
    assert final_manifest["final_artifacts"][0]["ref"] == artifact_ref


@pytest.mark.asyncio
async def test_v10_sec_05_local_state_notify_advances_playbook():
    """本地在线收件人收到 state_notify 时也应触发 Playbook 推进。"""
    owner = await register_owner("TestOwner")
    worker_did = "did:agentnexus:dev"
    await create_enclave(enclave_id="enc_local_notify", name="test", owner_did=owner["did"])
    await add_enclave_member("enc_local_notify", worker_did, "developer")
    await create_playbook(
        playbook_id="pb_local_notify",
        name="local-notify",
        stages=[{"name": "impl", "role": "developer", "next": ""}],
        created_by=owner["did"],
    )
    await create_playbook_run(
        run_id="run_local_notify",
        enclave_id="enc_local_notify",
        playbook_id="pb_local_notify",
        playbook_name="local-notify",
    )
    await create_stage_execution(
        "run_local_notify",
        "impl",
        worker_did,
        task_id="task_local_notify",
    )

    from agent_net.router import Router
    router = Router()
    router.register_local_session(owner["did"])
    artifact_ref = {"enclave_id": "enc_local_notify", "key": "impl/result.md"}

    await router.route_message(
        from_did=worker_did,
        to_did=owner["did"],
        content=json.dumps({
            "task_id": "task_local_notify",
            "status": "completed",
            "output_ref": artifact_ref,
        }),
        message_type="state_notify",
    )
    await asyncio.sleep(0.1)

    run = await get_playbook_run("run_local_notify")
    stage = await get_stage_execution("run_local_notify", "impl")
    assert run["status"] == "completed"
    assert json.loads(stage["output_ref"]) == {
        "enclave_id": "enc_local_notify",
        "key": "manifests/run_local_notify/impl",
    }


@pytest.mark.asyncio
async def test_v10_sec_05_task_propose_includes_role_and_context_snapshot():
    """PlaybookEngine 发出的 task_propose 应包含 WorkerRuntime 所需 role/context_snapshot。"""
    owner = await register_owner("TestOwner")
    worker_did = "did:agentnexus:dev"
    await create_enclave(enclave_id="enc_task_propose", name="test", owner_did=owner["did"])
    await add_enclave_member("enc_task_propose", worker_did, "developer")

    from agent_net.enclave.models import Stage
    from agent_net.enclave.playbook import PlaybookEngine

    captured = {}
    engine = PlaybookEngine()

    async def capture_send(**kwargs):
        captured.update(kwargs)

    engine._send_task_propose = capture_send
    await engine._start_stage(
        "enc_task_propose",
        "run_task_propose",
        Stage(
            name="impl",
            role="developer",
            input_keys=["design/spec.md"],
            output_key="impl/diff.patch",
        ),
    )

    assert captured["role"] == "developer"
    assert captured["context_snapshot"] == {
        "inputs": [{"enclave_id": "enc_task_propose", "key": "design/spec.md"}],
        "output": {"enclave_id": "enc_task_propose", "key": "impl/diff.patch"},
    }
