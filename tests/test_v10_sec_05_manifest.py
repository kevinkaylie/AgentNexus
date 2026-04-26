"""D-SEC-05: Delivery Manifest 稳定版测试"""
import json
import pytest
import pytest_asyncio

from agent_net.storage import (
    init_db, register_owner,
    create_enclave, add_enclave_member,
    create_playbook, create_playbook_run, update_playbook_run,
    create_stage_execution, get_stage_execution, get_stage_executions_for_run,
    get_playbook_run, get_enclave,
    store_stage_manifest, store_final_manifest, vault_get,
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
