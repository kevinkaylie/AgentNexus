"""Profile 交付路径测试：§15.2 适配器翻译 + §15.6 单事务 CAS + 交付入口（CP-04/09/17）。

覆盖三层：
1. ``_apply_profile_translation``（输出适配器，纯函数）——普通文本包装的 completed
   必须被拒，合法的 ``changes_requested`` 必须归一为 completed（不触发重跑）；
2. ``commit_profile_delivery``（存储层）——租约/截止/状态/摘要的 CAS 与幂等；
3. ``POST /coordination/executions/{id}/result``（HTTP）——Profile 绑定执行走专用路径，
   只签发 ``received`` 回执（**不得**出现旧 ``approved``），并回传错误信封。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

from agent_net.code_review import ProfileError, report_digest
from agent_net.node.execution_backends.base import ExecutionResult
from agent_net.node.execution_backends.local_cli import _apply_profile_translation

PACKAGE = Path(__file__).resolve().parents[1] / "specs" / "profiles" / "code-review" / "v1"
MANIFEST_DIGEST = "sha256:" + "1" * 64


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
    yield
    s.DB_PATH = _orig


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _report_body(name: str = "05_review_report_partial_inconclusive.artifact_body.json") -> str:
    text = (PACKAGE / "fixtures" / "valid" / name).read_text(encoding="utf-8")
    # 让报告声明的输入清单与测试分配一致（CP-04 校验）
    report = json.loads(text)
    report["input_manifest_digest"] = MANIFEST_DIGEST
    return json.dumps(report, ensure_ascii=False)


def _issues_report_body() -> str:
    return _report_body("08_review_report_issues_found.artifact_body.json")


# ── 1. 输出适配器翻译（§15.2 / CP-09 / CP-17） ────────────────────────


def _result(status: str, artifact_type: str, body: str) -> ExecutionResult:
    return ExecutionResult(
        execution_id="exec_x",
        status=status,
        artifact_type=artifact_type,
        artifact_body=body,
        summary="summary",
        evidence_refs=[],
        human_decision_request=None,
        raw_output_ref="raw",
    )


def test_cr_adapter_translates_changes_requested_to_completed():
    """CP-09：有有效 finding 的 changes_requested 不得成为重跑信号。"""
    out = _apply_profile_translation(
        _result("changes_requested", "CodeReviewReport", _issues_report_body())
    )
    assert out.status == "completed"
    assert out.artifact_body  # 报告体原样保留


def test_cr_adapter_keeps_valid_completed():
    out = _apply_profile_translation(
        _result("completed", "CodeReviewReport", _report_body())
    )
    assert out.status == "completed"


def test_cr_adapter_rejects_plain_text_completed():
    """CP-17：普通文本包装的 completed 不得完成 Run。"""
    out = _apply_profile_translation(_result("completed", "TextArtifact", "plain text"))
    assert out.status == "completed"  # 非 Profile 产物类型不受影响

    out = _apply_profile_translation(_result("completed", "CodeReviewReport", "plain text"))
    assert out.status == "failed"
    assert "invalid_output" in out.summary


def test_cr_adapter_rejects_structurally_invalid_report():
    broken = json.loads(_report_body())
    broken["coverage"]["status"] = "complete"  # 与 inherited_gaps 冲突
    out = _apply_profile_translation(
        _result("completed", "CodeReviewReport", json.dumps(broken, ensure_ascii=False))
    )
    assert out.status == "failed"
    assert "invalid_output" in out.summary


def test_cr_adapter_passes_through_failed_and_blocked():
    for status in ("failed", "blocked"):
        out = _apply_profile_translation(_result(status, "CodeReviewReport", ""))
        assert out.status == status


# ── 2/3. 交付提交（§15.6 CAS + 入口） ─────────────────────────────────


async def _profile_bound_execution(*, lease_delta: float = 600.0, deadline_delta: float = 600.0):
    from agent_net.storage import (
        bind_execution_assignment,
        create_coordination_session,
        create_objective_execution,
        create_profile_session,
        register_owner,
    )

    owner = await register_owner("CrDeliveryOwner")
    cs_id = _uid("cs")
    await create_coordination_session(
        coordination_session_id=cs_id,
        owner_did=owner["did"],
        controller_did=owner["did"],
        objective="profile delivery",
    )
    profile = await create_profile_session(
        _uid("psess"),
        coordination_session_id=cs_id,
        coordinator_id="urn:code-review:coordinator:test",
        external_run_id=_uid("RUN"),
        review_policy_sha256="a" * 64,
    )
    execution_id = _uid("exec")
    await create_objective_execution(
        execution_id=execution_id,
        coordination_session_id=cs_id,
        run_id="local-run",
        stage="code_review",
        worker_did="did:agentnexus:worker",
        backend_kind="local_cli",
        lease_expires_at=time.time() + lease_delta,
    )
    await bind_execution_assignment(
        execution_id,
        profile_session_id=profile["profile_session_id"],
        external_coordinator_id=profile["coordinator_id"],
        external_run_id=profile["external_run_id"],
        external_attempt_id="A1",
        assignment_epoch=1,
        input_manifest_digest=MANIFEST_DIGEST,
        output_schema="code_review.report.v1",
        deadline=time.time() + deadline_delta,
    )
    return {"owner": owner, "profile": profile, "execution_id": execution_id, "cs_id": cs_id}


def _auth_header():
    from agent_net.node._auth import init_daemon_token

    return {"Authorization": f"Bearer {init_daemon_token()}"}


@pytest.mark.asyncio
async def test_cr_delivery_commit_creates_received_receipt_and_metadata():
    from agent_net.storage import (
        commit_profile_delivery,
        get_artifact,
        get_objective_execution,
        list_profile_receipts,
    )

    ctx = await _profile_bound_execution()
    body = _report_body()
    expected_digest, expected_bytes = report_digest(body)
    result = await commit_profile_delivery(
        ctx["execution_id"],
        actor_did="did:agentnexus:worker",
        artifact_type="CodeReviewReport",
        artifact_body=body,
        media_type="application/json",
        schema_version="code_review.report.v1",
        summary="partial review",
        run_state="completed",
        outcome="inconclusive",
        domain_status="completed",
        enforcement="declared_only",
        receipt_issuer="did:agentnexus:worker",
        report_input_manifest_digest=MANIFEST_DIGEST,
    )
    assert result["replayed"] is False
    assert result["artifact_ref"]["digest"] == expected_digest
    assert result["artifact_ref"]["byte_length"] == expected_bytes

    artifact = await get_artifact(result["artifact_id"])
    assert artifact["content_hash"] == expected_digest
    assert artifact["byte_length"] == expected_bytes
    assert artifact["digest_algorithm"] == "sha256-bytes-v1"
    assert artifact["profile_session_id"] == ctx["profile"]["profile_session_id"]
    assert artifact["content_ref"].startswith("vault://")  # 不得是截断正文

    receipts = await list_profile_receipts(ctx["profile"]["profile_session_id"])
    assert [r["kind"] for r in receipts] == ["received"]  # 不得签发 accepted
    assert all(r["kind"] != "accepted" for r in receipts)

    execution = await get_objective_execution(ctx["execution_id"])
    assert execution["status"] == "completed"
    assert execution["result_hash"] == expected_digest
    assert execution["artifact_id"] == result["artifact_id"]


@pytest.mark.asyncio
async def test_cr_delivery_replay_and_conflict():
    from agent_net.storage import commit_profile_delivery

    ctx = await _profile_bound_execution()
    kwargs = dict(
        actor_did="did:agentnexus:worker",
        artifact_type="CodeReviewReport",
        artifact_body=_report_body(),
        media_type="application/json",
        schema_version="code_review.report.v1",
        summary="s",
        run_state="completed",
        outcome="inconclusive",
        domain_status="completed",
        enforcement="declared_only",
        report_input_manifest_digest=MANIFEST_DIGEST,
    )
    first = await commit_profile_delivery(ctx["execution_id"], **kwargs)
    replay = await commit_profile_delivery(ctx["execution_id"], **kwargs)
    assert replay["replayed"] is True
    assert replay["artifact_id"] == first["artifact_id"]
    assert len(replay["receipts"]) == 1

    with pytest.raises(ProfileError) as excinfo:
        await commit_profile_delivery(
            ctx["execution_id"], **{**kwargs, "artifact_body": _issues_report_body()}
        )
    assert excinfo.value.code == "delivery_conflict"


@pytest.mark.asyncio
async def test_cr_delivery_cas_rejects_stale_lease_deadline_and_state():
    from agent_net.storage import commit_profile_delivery, update_objective_execution

    base = dict(
        actor_did="did:agentnexus:worker",
        artifact_type="CodeReviewReport",
        artifact_body=_report_body(),
        media_type="application/json",
        schema_version="code_review.report.v1",
        summary="s",
        run_state="completed",
        outcome="inconclusive",
        domain_status="completed",
        enforcement="declared_only",
        report_input_manifest_digest=MANIFEST_DIGEST,
    )

    expired = await _profile_bound_execution(lease_delta=-10.0)
    with pytest.raises(ProfileError) as excinfo:
        await commit_profile_delivery(expired["execution_id"], **base)
    assert excinfo.value.code == "stale_assignment"

    past_deadline = await _profile_bound_execution(deadline_delta=-10.0)
    with pytest.raises(ProfileError) as excinfo:
        await commit_profile_delivery(past_deadline["execution_id"], **base)
    assert excinfo.value.code == "deadline_exceeded"

    finished = await _profile_bound_execution()
    await update_objective_execution(finished["execution_id"], status="superseded")
    with pytest.raises(ProfileError) as excinfo:
        await commit_profile_delivery(finished["execution_id"], **base)
    assert excinfo.value.code == "stale_assignment"

    # CP-04：输入清单不一致
    mismatch = await _profile_bound_execution()
    with pytest.raises(ProfileError) as excinfo:
        await commit_profile_delivery(
            mismatch["execution_id"], **{**base, "report_input_manifest_digest": "sha256:" + "9" * 64}
        )
    assert excinfo.value.code == "input_mismatch"


@pytest.mark.asyncio
async def test_cr_delivery_rejects_unbound_execution():
    from agent_net.storage import (
        commit_profile_delivery,
        create_coordination_session,
        create_objective_execution,
        register_owner,
    )

    owner = await register_owner("CrUnboundOwner")
    cs_id = _uid("cs")
    await create_coordination_session(
        coordination_session_id=cs_id,
        owner_did=owner["did"],
        controller_did=owner["did"],
        objective="unbound",
    )
    execution_id = _uid("exec")
    await create_objective_execution(
        execution_id=execution_id,
        coordination_session_id=cs_id,
        run_id="local-run",
        stage="code_review",
        worker_did="did:agentnexus:worker",
        backend_kind="local_cli",
    )
    with pytest.raises(ProfileError) as excinfo:
        await commit_profile_delivery(
            execution_id,
            actor_did="did:agentnexus:worker",
            artifact_type="CodeReviewReport",
            artifact_body=_report_body(),
            media_type="application/json",
            schema_version="code_review.report.v1",
            summary="s",
            run_state="completed",
            outcome="inconclusive",
            domain_status="completed",
            enforcement="declared_only",
        )
    assert excinfo.value.code == "input_mismatch"


@pytest.mark.asyncio
async def test_cr_delivery_endpoint_profile_path_and_error_envelope():
    from fastapi.testclient import TestClient

    from agent_net.node.daemon import app
    from agent_net.storage import get_objective_execution

    ctx = await _profile_bound_execution()
    client = TestClient(app, headers=_auth_header())

    # 合法报告 + changes_requested → completed，且只签发 received
    ok = client.post(
        f"/coordination/executions/{ctx['execution_id']}/result",
        json={
            "actor_did": ctx["owner"]["did"],
            "result": {
                "status": "changes_requested",
                "artifact_type": "CodeReviewReport",
                "artifact_body": _issues_report_body(),
                "summary": "found F7",
                "evidence_refs": [],
                "human_decision_request": None,
            },
        },
    )
    assert ok.status_code == 200, ok.text
    payload = ok.json()
    assert payload["status"] == "completed"
    assert payload["outcome"] == "issues_found"
    assert payload["domain_status"] == "changes_requested"
    assert payload["next_action_hint"] == "await_coordinator"
    assert [r["kind"] for r in payload["receipts"]] == ["received"]
    assert payload["artifact_ref"]["digest_algorithm"] == "sha256-bytes-v1"

    execution = await get_objective_execution(ctx["execution_id"])
    assert execution["status"] == "completed"

    # 普通文本 completed → 错误信封（CP-17）
    plain = await _profile_bound_execution()
    bad = client.post(
        f"/coordination/executions/{plain['execution_id']}/result",
        json={
            "actor_did": plain["owner"]["did"],
            "result": {
                "status": "completed",
                "artifact_type": "TextArtifact",
                "artifact_body": "plain stdout",
                "summary": "s",
                "evidence_refs": [],
            },
        },
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["schema"] == "code_review.error.v1"
    assert bad.json()["code"] == "invalid_output"

    # 旧 epoch/过期租约 → stale_assignment 信封
    stale = await _profile_bound_execution(lease_delta=-5.0)
    stale_resp = client.post(
        f"/coordination/executions/{stale['execution_id']}/result",
        json={
            "actor_did": stale["owner"]["did"],
            "result": {
                "status": "completed",
                "artifact_type": "CodeReviewReport",
                "artifact_body": _report_body(),
                "summary": "s",
                "evidence_refs": [],
            },
        },
    )
    assert stale_resp.status_code == 409, stale_resp.text
    assert stale_resp.json()["code"] == "stale_assignment"
