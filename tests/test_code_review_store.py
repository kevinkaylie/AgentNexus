"""Code Review Profile 存储层测试（§15.4/§15.5/§15.6/§15.7/§15.8）。

覆盖：Profile 会话唯一键（含 coordinator_id）、epoch 单调、执行绑定、
交付幂等与冲突、纠正规则、Profile 回执、消息 inbox、角色授权与范围解析、
强制能力注册与 fail-closed 判定。

DB 隔离沿用既有模式：``tmp_path`` + 直接替换 ``agent_net.storage.DB_PATH``。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from agent_net.code_review.errors import ProfileError


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


async def _profile_session(**overrides):
    from agent_net.storage import create_profile_session

    kwargs = {
        "coordination_session_id": _uid("cs"),
        "coordinator_id": "urn:code-review:coordinator:test",
        "external_run_id": _uid("RUN"),
        "review_policy_sha256": "a" * 64,
    }
    kwargs.update(overrides)
    return await create_profile_session(_uid("psess"), **kwargs)


def _envelope(msg_type: str = "assignment", message_id: str | None = None, **extra) -> dict:
    envelope = {
        "profile": "agentnexus.code-review/1.0-draft.2",
        "message_id": message_id or _uid("msg"),
        "type": msg_type,
        "sender_id": "did:agentnexus:coordinator",
        "receiver_id": "did:agentnexus:adapter",
        "session_id": "sess_1",
        "correlation_id": "corr_1",
        "causation_id": None,
        "created_at": "2026-09-20T00:00:00Z",
        "payload": {},
    }
    if msg_type in ("assignment", "delivery", "assignment_acceptance"):
        envelope.update({"run_id": "RUN-1", "attempt_id": "A1", "assignment_epoch": 1})
    envelope.update(extra)
    return envelope


# ── §15.6 Profile 会话与关联键 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_session_create_and_lookup_by_keys():
    from agent_net.storage import get_profile_session

    session = await _profile_session()
    by_key = await get_profile_session(
        coordinator_id=session["coordinator_id"], external_run_id=session["external_run_id"]
    )
    by_local = await get_profile_session(
        coordination_session_id=session["coordination_session_id"]
    )
    assert by_key["profile_session_id"] == session["profile_session_id"]
    assert by_local["profile_session_id"] == session["profile_session_id"]
    assert by_local["role_enforcement"] == "unenforced"


@pytest.mark.asyncio
async def test_cr_session_idempotent_replay_and_conflict():
    from agent_net.storage import create_profile_session

    session = await _profile_session()
    replay = await create_profile_session(
        _uid("psess_other"),
        coordination_session_id=session["coordination_session_id"],
        coordinator_id=session["coordinator_id"],
        external_run_id=session["external_run_id"],
        review_policy_sha256=session["review_policy_sha256"],
    )
    assert replay["profile_session_id"] == session["profile_session_id"]

    with pytest.raises(ProfileError) as excinfo:
        await create_profile_session(
            _uid("psess"),
            coordination_session_id=_uid("cs_other"),
            coordinator_id=session["coordinator_id"],
            external_run_id=session["external_run_id"],
            review_policy_sha256="b" * 64,
        )
    assert excinfo.value.code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_cr_session_key_includes_coordinator_id():
    """§15.6：不同 Coordinator 的同名 run_id 不得碰撞。"""
    first = await _profile_session(external_run_id="RUN-SAME")
    second = await _profile_session(
        coordinator_id="urn:code-review:coordinator:other", external_run_id="RUN-SAME"
    )
    assert first["profile_session_id"] != second["profile_session_id"]
    assert first["external_run_id"] == second["external_run_id"]


# ── §15.6 epoch 与执行绑定 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_assignment_epoch_is_monotonic():
    from agent_net.storage import bind_execution_assignment, create_objective_execution, next_assignment_epoch

    session = await _profile_session()
    execution_id = _uid("exec")
    await create_objective_execution(
        execution_id=execution_id,
        coordination_session_id=session["coordination_session_id"],
        run_id="local-run",
        stage="code_review",
        worker_did="did:agentnexus:worker",
        backend_kind="local_cli",
    )
    assert await next_assignment_epoch(session["profile_session_id"], "RUN-1") == 1

    bound = await bind_execution_assignment(
        execution_id,
        profile_session_id=session["profile_session_id"],
        external_coordinator_id=session["coordinator_id"],
        external_run_id="RUN-1",
        external_attempt_id="A1",
        assignment_epoch=1,
        input_manifest_digest="sha256:" + "1" * 64,
        output_schema="code_review.report.v1",
        deadline=4_000_000_000.0,
        enforcement={"token_cost_budget": {"level": "enforced", "component": "ledger"}},
    )
    assert bound is True
    assert await next_assignment_epoch(session["profile_session_id"], "RUN-1") == 2


@pytest.mark.asyncio
async def test_cr_bind_execution_persists_profile_fields():
    from agent_net.storage import (
        bind_execution_assignment,
        create_objective_execution,
        get_objective_execution,
    )

    session = await _profile_session()
    execution_id = _uid("exec")
    await create_objective_execution(
        execution_id=execution_id,
        coordination_session_id=session["coordination_session_id"],
        run_id="local-run",
        stage="code_review",
        worker_did="did:agentnexus:worker",
        backend_kind="local_cli",
    )
    await bind_execution_assignment(
        execution_id,
        profile_session_id=session["profile_session_id"],
        external_coordinator_id=session["coordinator_id"],
        external_run_id="RUN-7",
        external_attempt_id="A3",
        assignment_epoch=8,
        input_manifest_digest="sha256:" + "2" * 64,
        output_schema="code_review.report.v1",
    )
    record = await get_objective_execution(execution_id)
    assert record["external_coordinator_id"] == session["coordinator_id"]
    assert record["external_run_id"] == "RUN-7"
    assert record["external_attempt_id"] == "A3"
    assert record["assignment_epoch"] == 8
    assert record["output_schema"] == "code_review.report.v1"
    assert record["profile_session_id"] == session["profile_session_id"]
    # 既有字段不受影响
    assert record["status"] == "pending"


# ── 交付幂等与冲突（§7/§15.8） ────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_delivery_create_then_replay():
    from agent_net.storage import create_delivery, list_deliveries

    session = await _profile_session()
    delivery_id = _uid("del")
    kwargs = {
        "profile_session_id": session["profile_session_id"],
        "external_run_id": "RUN-1",
        "external_attempt_id": "A1",
        "assignment_epoch": 1,
        "input_manifest_digest": "sha256:" + "3" * 64,
        "artifact_id": "art_1",
        "artifact_digest": "sha256:" + "4" * 64,
        "byte_length": 2704,
        "schema_version": "code_review.report.v1",
    }
    first, first_state = await create_delivery(delivery_id, **kwargs)
    second, second_state = await create_delivery(delivery_id, **kwargs)
    assert (first_state, second_state) == ("created", "replayed")
    assert first["delivery_id"] == second["delivery_id"]
    assert first["created_at"] == second["created_at"]
    assert len(await list_deliveries(session["profile_session_id"], "RUN-1", "A1")) == 1


@pytest.mark.asyncio
async def test_cr_delivery_conflicts_on_digest_and_binding():
    from agent_net.storage import create_delivery

    session = await _profile_session()
    delivery_id = _uid("del")
    base = {
        "profile_session_id": session["profile_session_id"],
        "external_run_id": "RUN-1",
        "external_attempt_id": "A1",
        "assignment_epoch": 1,
        "input_manifest_digest": "sha256:" + "3" * 64,
        "artifact_id": "art_1",
        "artifact_digest": "sha256:" + "4" * 64,
        "byte_length": 10,
        "schema_version": "code_review.report.v1",
    }
    await create_delivery(delivery_id, **base)

    with pytest.raises(ProfileError) as excinfo:
        await create_delivery(delivery_id, **{**base, "artifact_digest": "sha256:" + "5" * 64})
    assert excinfo.value.code == "delivery_conflict"

    with pytest.raises(ProfileError) as excinfo:
        await create_delivery(delivery_id, **{**base, "assignment_epoch": 2})
    assert excinfo.value.code == "delivery_conflict"

    with pytest.raises(ProfileError) as excinfo:
        await create_delivery(delivery_id, **{**base, "external_attempt_id": "A2"})
    assert excinfo.value.code == "delivery_conflict"


@pytest.mark.asyncio
async def test_cr_delivery_correction_rules_and_status():
    from agent_net.storage import create_delivery, get_delivery, update_delivery_status

    session = await _profile_session()
    base = {
        "profile_session_id": session["profile_session_id"],
        "external_run_id": "RUN-1",
        "external_attempt_id": "A1",
        "assignment_epoch": 1,
        "input_manifest_digest": "sha256:" + "3" * 64,
        "artifact_id": "art_2",
        "artifact_digest": "sha256:" + "6" * 64,
        "byte_length": 20,
        "schema_version": "code_review.report.v1",
    }
    with pytest.raises(ProfileError) as excinfo:
        await create_delivery(_uid("del"), correction_no=1, **base)
    assert excinfo.value.code == "invalid_output"

    with pytest.raises(ProfileError):
        await create_delivery(_uid("del"), correction_no=2, replaces_delivery_id="del_x", **base)

    corrected_id = _uid("del")
    corrected, _ = await create_delivery(
        corrected_id, correction_no=1, replaces_delivery_id="del_0", **base
    )
    assert corrected["correction_no"] == 1
    assert corrected["replaces_delivery_id"] == "del_0"

    assert await update_delivery_status(corrected_id, "rejected", "invalid_output") is True
    record = await get_delivery(corrected_id)
    assert record["status"] == "rejected"
    assert record["reason_code"] == "invalid_output"


# ── Profile 回执（§7/§15.4） ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_profile_receipt_kinds_and_rejected_reason():
    from agent_net.storage import create_profile_receipt

    session = await _profile_session()
    with pytest.raises(ProfileError):
        await create_profile_receipt(
            _uid("rcpt"),
            profile_session_id=session["profile_session_id"],
            kind="approved",  # 旧词表不得复用（§15.4）
            issuer_id="did:agentnexus:coordinator",
            subject_kind="delivery",
            subject_id="del_1",
        )
    with pytest.raises(ProfileError) as excinfo:
        await create_profile_receipt(
            _uid("rcpt"),
            profile_session_id=session["profile_session_id"],
            kind="validated",
            decision="rejected",
            issuer_id="did:agentnexus:validator",
            subject_kind="delivery",
            subject_id="del_1",
        )
    assert excinfo.value.code == "invalid_output"


@pytest.mark.asyncio
async def test_cr_profile_receipt_is_idempotent_and_listable():
    from agent_net.storage import create_profile_receipt, list_profile_receipts

    session = await _profile_session()
    receipt_id = _uid("rcpt")
    kwargs = {
        "profile_session_id": session["profile_session_id"],
        "kind": "accepted",
        "issuer_id": "did:agentnexus:coordinator",
        "subject_kind": "delivery",
        "subject_id": "del_1",
        "external_run_id": "RUN-1",
        "external_attempt_id": "A1",
        "report_digest": "sha256:" + "7" * 64,
        "authority_ref": "authz://hczj/review/deliver/RUN-1",
        "enforcement": "declared_only",
    }
    first = await create_profile_receipt(receipt_id, **kwargs)
    second = await create_profile_receipt(receipt_id, **kwargs)
    assert first["created_at"] == second["created_at"]

    receipts = await list_profile_receipts(session["profile_session_id"], "RUN-1")
    assert [r["receipt_id"] for r in receipts] == [receipt_id]
    assert receipts[0]["subject_ref"] == {"kind": "delivery", "id": "del_1"}
    assert receipts[0]["enforcement"] == "declared_only"


# ── 消息 inbox（RC2 §4） ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_message_store_replay_and_conflict():
    from agent_net.storage import store_profile_message

    session = await _profile_session()
    envelope = _envelope("assignment")
    first, first_state = await store_profile_message(
        envelope["message_id"], envelope=envelope, profile_session_id=session["profile_session_id"]
    )
    second, second_state = await store_profile_message(
        envelope["message_id"], envelope=envelope, profile_session_id=session["profile_session_id"]
    )
    assert (first_state, second_state) == ("created", "replayed")
    assert first["state"] == "stored"
    assert first["run_id"] == "RUN-1" and first["attempt_id"] == "A1"

    changed = dict(envelope)
    changed["payload"] = {"tampered": True}
    with pytest.raises(ProfileError) as excinfo:
        await store_profile_message(
            envelope["message_id"],
            envelope=changed,
            profile_session_id=session["profile_session_id"],
        )
    assert excinfo.value.code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_cr_message_state_and_error_roundtrip():
    from agent_net.storage import get_message, set_message_state, store_profile_message

    envelope = _envelope("delivery")
    await store_profile_message(envelope["message_id"], envelope=envelope)
    error = {"schema": "code_review.error.v1", "code": "invalid_output"}
    assert await set_message_state(
        envelope["message_id"], "rejected", receipts=[{"receipt_id": "r1"}], error=error
    )
    record = await get_message(envelope["message_id"])
    assert record["state"] == "rejected"
    assert record["receipts"] == [{"receipt_id": "r1"}]
    assert record["error"]["code"] == "invalid_output"


@pytest.mark.asyncio
async def test_cr_message_rejects_unknown_state():
    from agent_net.storage import set_message_state, store_profile_message

    envelope = _envelope("feedback")
    await store_profile_message(envelope["message_id"], envelope=envelope)
    with pytest.raises(ValueError):
        await set_message_state(envelope["message_id"], "approved")


# ── §15.7 角色授权 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_role_grants_resolve_and_scope():
    from agent_net.storage import grant_role, resolve_roles, roles_configured

    assert await roles_configured() is False
    await grant_role("did:agentnexus:coordinator", "coordinator")
    await grant_role("did:agentnexus:validator", "validator", instance_id="gitlab-main")
    assert await roles_configured() is True

    assert await resolve_roles("did:agentnexus:coordinator") == {"coordinator"}
    assert await resolve_roles("did:agentnexus:validator", instance_id="gitlab-main") == {"validator"}
    # 范围不匹配时不授予
    assert await resolve_roles("did:agentnexus:validator", instance_id="other") == set()
    # worker 未被授予任何角色
    assert await resolve_roles("did:agentnexus:worker") == set()


@pytest.mark.asyncio
async def test_cr_grant_role_rejects_unknown_role():
    from agent_net.storage import grant_role

    with pytest.raises(ValueError):
        await grant_role("did:agentnexus:x", "approved")


# ── §15.5 强制能力注册（"无法支持的能力"） ────────────────────────────


@pytest.mark.asyncio
async def test_cr_enforcement_registry_fail_closed():
    from agent_net.storage import list_enforcement, set_enforcement, unsupported_requirements

    required = {"token_cost_budget": "enforced", "provider_outbound_data": "declared_only"}
    # 未注册任何能力 → 必需项全部不可用
    assert set(await unsupported_requirements(required)) == set(required)

    await set_enforcement("token_cost_budget", "enforced", "hczj-run-budget-ledger")
    # 只 enforced 的项通过；declared_only 仍不可用（fail-closed）
    assert await unsupported_requirements(required) == ["provider_outbound_data"]

    await set_enforcement("provider_outbound_data", "declared_only", "hczj-model-gateway")
    assert await unsupported_requirements(required) == ["provider_outbound_data"]

    # 任务不要求的能力（unsupported）不阻塞
    assert await unsupported_requirements({"source_scope": "unsupported"}) == []
    assert len(await list_enforcement()) == 2


@pytest.mark.asyncio
async def test_cr_enforcement_requires_component_and_valid_level():
    from agent_net.storage import set_enforcement

    with pytest.raises(ValueError):
        await set_enforcement("token_cost_budget", "enforced")
    with pytest.raises(ValueError):
        await set_enforcement("token_cost_budget", "enforcedish", "x")
