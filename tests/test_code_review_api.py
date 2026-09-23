"""Code Review Profile L0 服务接口测试（binding RC2 §4/§7 + §15.7 + CP-24）。

2026-09-21 代码评审后重写。原测试**把缺陷当成期望行为**（空 payload 被 202、改
``sender_id`` 就能换角色、ACK 回显 ``replayed/enforcement/state``、MessageView 多包
一层 ``{status,message}``、无 actor 也能读产物），因此这里的期望值改为契约本身的
要求，并补齐评审要求的负例：

- B1 跨主体冒充、回执 issuer 自报、未登记凭据、worker 伪造 accepted/published；
- B2 跨 Run/session 读取、过期产物；
- B3 DTO 未声明字段、retention 严格解析与返回、ArtifactRef 过冻结 schema；
- B4 相同 Idempotency-Key 重放、失败上传不破坏已登记字节；
- B5 空 payload / 缺 enforcement_requirements 被拒；
- B6 崩溃窗口后由可重放路径补完回执。
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

PACKAGE = Path(__file__).resolve().parents[1] / "specs" / "profiles" / "code-review" / "v1"
FROZEN_REPORT_DIGEST = "sha256:6395a6edac10db12b303cccaa6cbedcb4a99e0f3721195de0312cf0d15766316"
FROZEN_REPORT_BYTES = 2704

MESSAGE_URL = "/coordination/code-review/v1/messages"
ARTIFACT_URL = "/coordination/code-review/v1/artifacts"


@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    import agent_net.storage as s
    from agent_net.code_review import frozen

    _db = tmp_path / "agent_net.db"
    _orig = s.DB_PATH
    s.DB_PATH = _db
    _db.parent.mkdir(exist_ok=True)
    if _db.exists():
        _db.unlink()
    await s.init_db()
    frozen.reset_cache()
    yield
    s.DB_PATH = _orig
    frozen.reset_cache()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


async def _provision(
    *,
    principal_id: str,
    roles,
    dids,
    sessions=(),
    instances=(),
    projects=(),
) -> dict:
    """登记一条服务凭据并返回可直接使用的请求头。"""
    from agent_net.storage import register_service_principal

    credential = f"cred_{uuid.uuid4().hex}"
    await register_service_principal(
        credential,
        principal_id=principal_id,
        roles=list(roles),
        dids=list(dids),
        sessions=list(sessions),
        instances=list(instances),
        projects=list(projects),
    )
    return {"Authorization": f"Bearer {credential}"}


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


def _authority_ref() -> str:
    return "authz://hczj/review/deliver/RUN-1"


def _assignment_payload(run_id: str, *, epoch: int = 1, **overrides) -> dict:
    payload = {
        "run_id": run_id,
        "attempt_id": "A1",
        "assignment_epoch": epoch,
        "coordinator_id": "urn:code-review:coordinator:test",
        "input_manifest_digest": "sha256:" + "b" * 64,
        "output_schema": "code_review.report.v1",
        "policy_ref": "policy:code-review:1",
        "authority_ref": _authority_ref(),
        "deadline": "2026-12-31T00:00:00Z",
        "limits": {
            "max_tool_rounds": 10,
            "max_input_tokens": 1000,
            "max_output_tokens": 1000,
            "max_wall_clock_sec": 600,
            "max_cost": None,
        },
        "required_capabilities": ["code_review"],
        "enforcement_requirements": [
            {"constraint": "provider_outbound_data", "level": "enforced", "component": "local-cli"},
        ],
    }
    payload.update(overrides)
    return payload


def _receipt_payload(run_id: str, *, kind: str = "accepted", issuer_id: str, **overrides) -> dict:
    payload = {
        "schema": "code_review.receipt.v1",
        "receipt_id": _uid("rcpt"),
        "kind": kind,
        "issuer_id": issuer_id,
        "subject_ref": {"kind": "delivery", "id": "del_1"},
        "run_id": run_id,
        "attempt_id": "A1",
        "decision": "confirmed",
        "created_at": "2026-09-20T00:00:00Z",
        "authority_ref": _authority_ref(),
        "evidence_refs": [],
    }
    payload.update(overrides)
    return payload


def _envelope(msg_type: str, *, session_id: str, sender: str, run_id: str = "", payload: dict | None = None) -> dict:
    envelope = {
        "profile": "agentnexus.code-review/1.0-draft.2",
        "message_id": _uid("msg"),
        "type": msg_type,
        "sender_id": sender,
        "receiver_id": "did:agentnexus:adapter",
        "session_id": session_id,
        "correlation_id": "corr_cr_1",
        "causation_id": None,
        "created_at": "2026-09-20T00:00:00Z",
        "payload": payload if payload is not None else {},
    }
    if msg_type == "assignment":
        envelope.update({"run_id": run_id, "attempt_id": "A1", "assignment_epoch": 1})
    elif msg_type in ("delivery", "assignment_acceptance", "cancel_acknowledgement"):
        envelope.update({"run_id": run_id, "attempt_id": "A1", "assignment_epoch": 1})
    elif msg_type in ("receipt", "cancel_request"):
        envelope.update({"run_id": run_id, "attempt_id": "A1", "assignment_epoch": 1})
    return envelope


def _client(headers: dict):
    """默认带上 ``X-Correlation-Id``；``POST A/messages`` 自动补 ``Idempotency-Key``。

    2026-09-22 裁决：消息类接口的幂等键经 ``Idempotency-Key`` 头传递，取值等于
    ``envelope.message_id``；缺头 → 422、不一致 → 409。本文件聚焦业务语义，因此由
    客户端按信封自动注入（显式传入的 headers 优先）；该头本身的契约行为由
    ``test_code_review_http_contract.py`` 的矩阵专门覆盖。
    """
    from fastapi.testclient import TestClient

    from agent_net.node.daemon import app

    merged = {"X-Correlation-Id": "corr_cr_1", **headers}

    class _ProfileTestClient(TestClient):
        def post(self, url, **kwargs):  # noqa: D102 - 见类与方法文档
            body = kwargs.get("json")
            if url == MESSAGE_URL and isinstance(body, dict) and "message_id" in body:
                extra = dict(kwargs.pop("headers", None) or {})
                extra.setdefault("Idempotency-Key", body["message_id"])
                kwargs["headers"] = extra
            return super().post(url, **kwargs)

    return _ProfileTestClient(app, headers=merged)


def _report_body() -> str:
    return (
        PACKAGE / "fixtures" / "valid" / "05_review_report_partial_inconclusive.artifact_body.json"
    ).read_text(encoding="utf-8")


def _artifact_request(run_id: str, *, retention: str = "2026-12-31T00:00:00Z", body: str | None = None, **extra) -> dict:
    request = {
        "run_id": run_id,
        "attempt_id": "A1",
        "assignment_epoch": 1,
        "artifact_body": body if body is not None else _report_body(),
        "media_type": "application/json",
        "schema_version": "code_review.report.v1",
        "retention_until": retention,
    }
    request.update(extra)
    return request


async def _coordinator(*, sessions=(), dids=("urn:code-review:coordinator:test",)):
    return await _provision(
        principal_id="urn:code-review:coordinator:test",
        roles=["coordinator", "validator", "publisher", "evidence_reader"],
        dids=list(dids),
        sessions=list(sessions),
    )


async def _worker(did: str, *, sessions=(), bind: dict | None = None):
    headers = await _provision(principal_id=did, roles=["worker"], dids=[did], sessions=list(sessions))
    if bind is not None:
        await _bind_assignment(bind, worker_did=did)
    return headers


async def _bind_assignment(
    session: dict,
    *,
    worker_did: str = "did:agentnexus:worker",
    attempt_id: str = "A1",
    epoch: int = 1,
    status: str = "running",
    deadline: float | None = None,
):
    """建立**真实**分配绑定（评审 R2-2 之后上传必须命中它，否则不得 201）。"""
    from agent_net.storage import (
        bind_execution_assignment,
        create_objective_execution,
        update_objective_execution,
    )

    execution_id = _uid("exec")
    await create_objective_execution(
        execution_id=execution_id,
        coordination_session_id=session["coordination_session_id"],
        run_id=session["external_run_id"],
        stage="code_review",
        worker_did=worker_did,
        backend_kind="local_cli",
        lease_expires_at=time.time() + 3600,
    )
    await bind_execution_assignment(
        execution_id,
        profile_session_id=session["profile_session_id"],
        external_coordinator_id="urn:code-review:coordinator:test",
        external_run_id=session["external_run_id"],
        external_attempt_id=attempt_id,
        assignment_epoch=epoch,
        input_manifest_digest="sha256:" + "b" * 64,
        output_schema="code_review.report.v1",
        deadline=deadline,
    )
    if status != "running":
        await update_objective_execution(execution_id, status=status)
    return execution_id


async def _register_enforced(*constraints: str) -> None:
    """在部署注册表里把约束登记为 enforced——§15.5 要求接单前必须能证明强制。"""
    from agent_net.storage import set_enforcement

    for constraint in constraints:
        await set_enforcement(constraint, "enforced", "local-cli")


# ── B1：认证与主体绑定 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_api_rejects_everything_when_no_credential_configured():
    """RC2 §1：未配置凭据必须拒绝，不得沿用"未配置则放行"。"""
    client = _client({"Authorization": "Bearer whatever"})
    resp = client.post(MESSAGE_URL, json=_envelope("assignment", session_id=_uid("cs"), sender="did:x"))
    assert resp.status_code == 401, resp.text
    assert resp.json()["code"] == "authority_denied"


@pytest.mark.asyncio
async def test_cr_api_rejects_unknown_credential():
    session = await _profile_session()
    await _coordinator(sessions=[session["profile_session_id"]])
    client = _client({"Authorization": "Bearer not-a-registered-credential"})
    resp = client.post(
        MESSAGE_URL,
        json=_envelope(
            "assignment",
            session_id=session["coordination_session_id"],
            sender="urn:code-review:coordinator:test",
            run_id=session["external_run_id"],
            payload=_assignment_payload(session["external_run_id"]),
        ),
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "authority_denied"


@pytest.mark.asyncio
async def test_cr_api_sender_must_be_bound_to_credential():
    """评审 B1 复现：同一凭据把 sender 改成别的已登记 coordinator，不得因此获得权限。"""
    session = await _profile_session()
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)

    spoofed = _envelope(
        "assignment",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:somebody-else",
        run_id=session["external_run_id"],
        payload=_assignment_payload(session["external_run_id"]),
    )
    resp = client.post(MESSAGE_URL, json=spoofed)
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "authority_denied"
    assert "不一致" in resp.json()["safe_message"]


@pytest.mark.asyncio
async def test_cr_api_worker_cannot_forge_accepted_receipt():
    """评审 B1：worker 凭据不得签发 accepted/published 回执。"""
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    client = _client(headers)

    forged = _envelope(
        "receipt",
        session_id=session["coordination_session_id"],
        sender=worker_did,
        run_id=session["external_run_id"],
        payload=_receipt_payload(session["external_run_id"], kind="accepted", issuer_id=worker_did),
    )
    resp = client.post(MESSAGE_URL, json=forged)
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "authority_denied"


@pytest.mark.asyncio
async def test_cr_api_receipt_issuer_must_be_bound():
    """回执 issuer_id 自报也必须落在认证主体可代表范围内。"""
    session = await _profile_session()
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)

    envelope = _envelope(
        "receipt",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:test",
        run_id=session["external_run_id"],
        payload=_receipt_payload(
            session["external_run_id"],
            kind="accepted",
            issuer_id="did:agentnexus:somebody-else",
        ),
    )
    resp = client.post(MESSAGE_URL, json=envelope)
    assert resp.status_code == 403, resp.text
    assert "issuer_id" in resp.json()["safe_message"]


# ── B1/B3：入站成功路径与严格 DTO ─────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_api_assignment_ack_is_exactly_three_fields():
    session = await _profile_session()
    await _register_enforced("provider_outbound_data")
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)
    envelope = _envelope(
        "assignment",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:test",
        run_id=session["external_run_id"],
        payload=_assignment_payload(session["external_run_id"]),
    )

    resp = client.post(MESSAGE_URL, json=envelope)
    assert resp.status_code == 202, resp.text
    # RC2 §4：TransportAck 恰好三字段，不再回显 replayed/enforcement/state。
    assert resp.json() == {
        "message_id": envelope["message_id"],
        "status": "stored",
        "status_url": f"{MESSAGE_URL}/{envelope['message_id']}",
    }

    replay = client.post(MESSAGE_URL, json=envelope)
    assert replay.status_code == 202
    assert replay.json() == resp.json()

    view = client.get(f"{MESSAGE_URL}/{envelope['message_id']}")
    assert view.status_code == 200
    # RC2 §4：MessageView 恰好四字段，不再包一层 {status,message}。
    assert set(view.json()) == {"message_id", "state", "receipts", "error"}
    assert view.json()["state"] == "stored"


@pytest.mark.asyncio
async def test_cr_api_rejects_empty_assignment_payload():
    """评审 B5 复现：assignment.payload={} 曾被 202 ACK。"""
    session = await _profile_session()
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)
    envelope = _envelope(
        "assignment",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:test",
        run_id=session["external_run_id"],
        payload={},
    )
    resp = client.post(MESSAGE_URL, json=envelope)
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "invalid_output"


@pytest.mark.asyncio
async def test_cr_api_rejects_assignment_without_enforcement_requirements():
    """缺 enforcement_requirements 不得被当成"无要求"从而放行未冻结的任务。"""
    session = await _profile_session()
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)
    payload = _assignment_payload(session["external_run_id"])
    payload.pop("enforcement_requirements")
    envelope = _envelope(
        "assignment",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:test",
        run_id=session["external_run_id"],
        payload=payload,
    )
    resp = client.post(MESSAGE_URL, json=envelope)
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_output"


@pytest.mark.asyncio
async def test_cr_api_rejects_assignment_with_unknown_payload_field():
    session = await _profile_session()
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)
    payload = _assignment_payload(session["external_run_id"], surprise="x")
    envelope = _envelope(
        "assignment",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:test",
        run_id=session["external_run_id"],
        payload=payload,
    )
    resp = client.post(MESSAGE_URL, json=envelope)
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_output"


@pytest.mark.asyncio
async def test_cr_api_rejects_unsupported_inbound_type():
    session = await _profile_session()
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)
    envelope = _envelope(
        "delivery",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:test",
        run_id=session["external_run_id"],
        payload={"run_id": session["external_run_id"]},
    )
    resp = client.post(MESSAGE_URL, json=envelope)
    assert resp.status_code == 422
    assert resp.json()["code"] == "unsupported_capability"


@pytest.mark.asyncio
async def test_cr_api_rejects_correlation_mismatch():
    session = await _profile_session()
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)
    envelope = _envelope(
        "assignment",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:test",
        run_id=session["external_run_id"],
        payload=_assignment_payload(session["external_run_id"]),
    )
    resp = client.post(
        MESSAGE_URL, json=envelope, headers={**headers, "X-Correlation-Id": "corr_other"}
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_output"


@pytest.mark.asyncio
async def test_cr_api_assignment_fails_closed_when_capability_not_registered():
    """§15.5：未登记 enforced 的必需约束一律拒绝接单（CP-25）。"""
    from agent_net.storage import set_enforcement

    session = await _profile_session()
    await set_enforcement("provider_outbound_data", "unsupported", "")
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)
    payload = _assignment_payload(session["external_run_id"])
    payload["enforcement_requirements"] = [
        {"constraint": "provider_outbound_data", "level": "enforced", "component": "x"}
    ]
    envelope = _envelope(
        "assignment",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:test",
        run_id=session["external_run_id"],
        payload=payload,
    )
    resp = client.post(MESSAGE_URL, json=envelope)
    assert resp.status_code == 422
    assert resp.json()["code"] == "enforcement_unavailable"


# ── B6：回执 + 崩溃补偿 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_api_receipt_processed_atomically_and_view_returns_envelopes():
    from agent_net.storage import list_profile_receipts

    session = await _profile_session()
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)
    payload = _receipt_payload(
        session["external_run_id"],
        kind="accepted",
        issuer_id="urn:code-review:coordinator:test",
    )
    envelope = _envelope(
        "receipt",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:test",
        run_id=session["external_run_id"],
        payload=payload,
    )
    resp = client.post(MESSAGE_URL, json=envelope)
    assert resp.status_code == 202, resp.text

    view = client.get(f"{MESSAGE_URL}/{envelope['message_id']}").json()
    assert view["state"] == "processed"
    assert len(view["receipts"]) == 1
    receipt_env = view["receipts"][0]
    # RC2 §4：receipts 是 Profile receipt **信封**（type=receipt + payload），
    # 不是内部记录。
    assert receipt_env["type"] == "receipt"
    assert receipt_env["payload"]["receipt_id"] == payload["receipt_id"]
    assert receipt_env["payload"]["kind"] == "accepted"
    assert set(receipt_env["payload"]) <= {
        "schema", "receipt_id", "kind", "issuer_id", "subject_ref", "run_id",
        "attempt_id", "decision", "created_at", "authority_ref", "evidence_refs",
        "report_digest", "reason_code",
    }

    assert len(await list_profile_receipts(session["profile_session_id"])) == 1


@pytest.mark.asyncio
async def test_cr_api_receipt_crash_window_is_recovered_on_read():
    """评审 B6：inbox 已提交而回执未写的崩溃窗口，必须能被重放路径补完。"""
    from agent_net.storage import get_message, set_message_state, store_profile_message

    session = await _profile_session()
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)
    payload = _receipt_payload(
        session["external_run_id"],
        kind="validated",
        issuer_id="urn:code-review:coordinator:test",
    )
    envelope = _envelope(
        "receipt",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:test",
        run_id=session["external_run_id"],
        payload=payload,
    )
    # 直接落消息但不写回执，模拟"提交后崩溃"。
    await store_profile_message(
        envelope["message_id"], envelope=envelope, profile_session_id=session["profile_session_id"]
    )
    stored = await get_message(envelope["message_id"])
    assert stored["state"] == "stored" and stored["receipts"] == []

    view = client.get(f"{MESSAGE_URL}/{envelope['message_id']}")
    assert view.status_code == 200
    body = view.json()
    assert body["state"] == "processed"
    assert len(body["receipts"]) == 1
    assert body["receipts"][0]["payload"]["kind"] == "validated"


# ── B2：读取资源授权 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_api_message_read_requires_party_or_session_scope():
    session = await _profile_session()
    await _register_enforced("provider_outbound_data")
    owner_headers = await _coordinator(sessions=[session["profile_session_id"]])
    owner_client = _client(owner_headers)
    envelope = _envelope(
        "assignment",
        session_id=session["coordination_session_id"],
        sender="urn:code-review:coordinator:test",
        run_id=session["external_run_id"],
        payload=_assignment_payload(session["external_run_id"]),
    )
    assert owner_client.post(MESSAGE_URL, json=envelope).status_code == 202

    # 另一个 Coordinator 凭据，但没有该 session 的授权 → 不得读取
    outsider = await _provision(
        principal_id="urn:code-review:coordinator:outsider",
        roles=["coordinator"],
        dids=["urn:code-review:coordinator:outsider"],
        sessions=["cs_somewhere_else"],
    )
    denied = _client(outsider).get(f"{MESSAGE_URL}/{envelope['message_id']}")
    assert denied.status_code == 403, denied.text
    assert denied.json()["code"] == "authority_denied"

    # 消息当事人可以读——但**仍须**落在凭据登记的资源范围内（评审 R2-2：
    # 上一版当事人分支绕过 require_session，同一 DID 跨 session 时限制形同虚设）。
    party = await _provision(
        principal_id="did:agentnexus:adapter",
        roles=["evidence_reader"],
        dids=["did:agentnexus:adapter"],
        sessions=[session["profile_session_id"]],
    )
    ok = _client(party).get(f"{MESSAGE_URL}/{envelope['message_id']}")
    assert ok.status_code == 200

    # 当事人但没有该 session 范围 → 拒绝
    party_no_scope = await _provision(
        principal_id="did:agentnexus:adapter",
        roles=["evidence_reader"],
        dids=["did:agentnexus:adapter"],
        sessions=["psess_elsewhere"],
    )
    denied_party = _client(party_no_scope).get(f"{MESSAGE_URL}/{envelope['message_id']}")
    assert denied_party.status_code == 403, denied_party.text


@pytest.mark.asyncio
async def test_cr_api_artifact_read_requires_session_scope_and_retention():
    from agent_net.storage import set_message_state  # noqa: F401  (保持导入面稳定)

    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    worker_headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    submitted = _client(worker_headers).post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"]),
        headers={**worker_headers, "Idempotency-Key": _uid("idem")},
    )
    assert submitted.status_code == 201, submitted.text
    artifact_id = submitted.json()["artifact_id"]

    # 同一凭据（有 session 范围）可以读
    ok = _client(worker_headers).get(f"{ARTIFACT_URL}/{artifact_id}/raw")
    assert ok.status_code == 200

    # 另一个有读取角色但没有该 session 的凭据 → 403
    outsider = await _provision(
        principal_id="urn:code-review:validator:outsider",
        roles=["validator"],
        dids=["urn:code-review:validator:outsider"],
        sessions=["cs_other"],
    )
    denied = _client(outsider).get(f"{ARTIFACT_URL}/{artifact_id}/raw")
    assert denied.status_code == 403, denied.text
    assert denied.json()["code"] == "authority_denied"


@pytest.mark.asyncio
async def test_cr_api_expired_artifact_returns_410():
    from agent_net.persistence.context import connect

    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    client = _client(headers)
    submitted = client.post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"]),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert submitted.status_code == 201, submitted.text
    artifact_id = submitted.json()["artifact_id"]

    # 直接把保留期改到过去，模拟读取已过期产物
    async with connect() as db:
        await db.execute(
            "UPDATE artifacts SET retention_until=? WHERE artifact_id=?",
            (time.time() - 3600, artifact_id),
        )
        await db.commit()
    resp = client.get(f"{ARTIFACT_URL}/{artifact_id}/raw")
    assert resp.status_code == 410
    assert resp.json()["code"] == "artifact_expired"


# ── B3：上传 DTO 与 ArtifactRef 契约 ──────────────────────────────────


@pytest.mark.asyncio
async def test_cr_api_upload_rejects_fields_outside_contract():
    """评审 B3：producer_id/actor_did/artifact_id 等非契约字段一律拒绝。"""
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    client = _client(headers)
    for extra in (
        {"producer_id": "did:agentnexus:someone-else"},
        {"actor_did": worker_did},
        {"artifact_id": "art_attacker_chosen"},
    ):
        resp = client.post(
            ARTIFACT_URL,
            json=_artifact_request(session["external_run_id"], **extra),
            headers={"Idempotency-Key": _uid("idem")},
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "invalid_output"


@pytest.mark.asyncio
async def test_cr_api_upload_retention_is_parsed_persisted_and_returned():
    """评审 B3 复现：retention_until 曾被静默改成 null。"""
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    requested = "2026-12-31T00:00:00Z"
    resp = _client(headers).post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"], retention=requested),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert resp.status_code == 201, resp.text
    ref = resp.json()
    assert ref["retention_until"] == requested
    assert ref["producer_id"] == worker_did


@pytest.mark.asyncio
async def test_cr_api_upload_rejects_numeric_retention():
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    resp = _client(headers).post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"], retention=int(time.time()) + 3600),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_output"


@pytest.mark.asyncio
async def test_cr_api_upload_rejects_retention_beyond_commitment():
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    resp = _client(headers).post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"], retention="2099-01-01T00:00:00Z"),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "data_policy_denied"
    assert resp.json()["scope"] == "retention"


@pytest.mark.asyncio
async def test_cr_api_artifact_ref_validates_against_frozen_schema():
    """以实际 HTTP 响应跑冻结 schema，而不是只断言几个字段（评审 B3）。"""
    import jsonschema
    from referencing import Registry, Resource

    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    resp = _client(headers).post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"]),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert resp.status_code == 201, resp.text
    ref = resp.json()

    schemas = {
        p.name: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((PACKAGE / "schemas").glob("*.schema.json"))
    }
    registry = Registry().with_resources(
        [(doc["$id"], Resource.from_contents(doc)) for doc in schemas.values()]
    )
    validator = jsonschema.Draft202012Validator(
        schemas["artifact_ref.schema.json"], registry=registry
    )
    errors = sorted(validator.iter_errors(ref), key=lambda e: list(e.path))
    assert not errors, [e.message for e in errors]
    # 冻结 schema 是 additionalProperties:false，多返回 enforcement 会被拒
    assert "enforcement" not in ref


@pytest.mark.asyncio
async def test_cr_api_upload_digest_matches_frozen_vector():
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    resp = _client(headers).post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"]),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["digest"] == FROZEN_REPORT_DIGEST
    assert resp.json()["byte_length"] == FROZEN_REPORT_BYTES


# ── B4：幂等与不可变 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_api_same_idempotency_key_returns_same_artifact():
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    client = _client(headers)
    key = _uid("idem")
    request = _artifact_request(session["external_run_id"])

    first = client.post(ARTIFACT_URL, json=request, headers={"Idempotency-Key": key})
    second = client.post(ARTIFACT_URL, json=request, headers={"Idempotency-Key": key})
    assert first.status_code == second.status_code == 201
    assert first.json()["artifact_id"] == second.json()["artifact_id"]


@pytest.mark.asyncio
async def test_cr_api_same_key_different_body_conflicts_without_corrupting():
    """评审 B4 复现：同 key 不同正文既不能新建，也不能破坏已登记字节。"""
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    client = _client(headers)
    key = _uid("idem")

    first = client.post(
        ARTIFACT_URL, json=_artifact_request(session["external_run_id"]), headers={"Idempotency-Key": key}
    )
    assert first.status_code == 201, first.text
    artifact_id = first.json()["artifact_id"]

    other = _report_body().replace("inconclusive", "issues_found", 1)
    conflict = client.post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"], body=other),
        headers={"Idempotency-Key": key},
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "delivery_conflict"

    # 原产物字节未被破坏，摘要仍一致
    still = client.get(f"{ARTIFACT_URL}/{artifact_id}/raw")
    assert still.status_code == 200
    assert still.headers["ETag"].strip('"') == FROZEN_REPORT_DIGEST


@pytest.mark.asyncio
async def test_cr_api_upload_requires_idempotency_key():
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    resp = _client(headers).post(ARTIFACT_URL, json=_artifact_request(session["external_run_id"]))
    assert resp.status_code == 422
    assert resp.json()["code"] == "input_mismatch"


@pytest.mark.asyncio
async def test_cr_api_vault_key_is_content_addressed():
    """不可变：同一内容重复上传落到同一 Vault key，不可能出现同 locator 不同字节。"""
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    client = _client(headers)
    first = client.post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"]),
        headers={"Idempotency-Key": _uid("idem")},
    )
    second = client.post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"]),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["artifact_id"] != second.json()["artifact_id"]
    # 两个 artifact 指向同一份内容（按摘要寻址）
    assert first.json()["digest"] == second.json()["digest"]


# ── raw 读取语义 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_api_raw_etag_and_if_match():
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    client = _client(headers)
    submitted = client.post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"]),
        headers={"Idempotency-Key": _uid("idem")},
    )
    artifact_id = submitted.json()["artifact_id"]

    ok = client.get(f"{ARTIFACT_URL}/{artifact_id}/raw")
    assert ok.status_code == 200
    assert ok.headers["ETag"].strip('"') == FROZEN_REPORT_DIGEST
    assert int(ok.headers["Content-Length"]) == FROZEN_REPORT_BYTES
    assert hashlib.sha256(ok.content).hexdigest() == FROZEN_REPORT_DIGEST.split(":", 1)[1]

    mismatch = client.get(
        f"{ARTIFACT_URL}/{artifact_id}/raw", headers={"If-Match": '"sha256:' + "0" * 64 + '"'}
    )
    # RC2 §2：If-Match 不匹配返回 412（409 留给"存储字节与登记摘要不一致"这类真实冲突）
    assert mismatch.status_code == 412
    assert mismatch.json()["code"] == "evidence_digest_mismatch"


@pytest.mark.asyncio
async def test_cr_api_raw_missing_artifact_is_404():
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    resp = _client(headers).get(f"{ARTIFACT_URL}/art_missing/raw")
    assert resp.status_code == 404
    assert resp.json()["code"] == "evidence_unavailable"


# ── CP-24：旧回执入口 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cp24_legacy_receipts_endpoint_rejects_profile_session():
    """旧通用 /coordination/receipts 不得写 Profile 权威回执（CP-24）。"""
    from fastapi.testclient import TestClient

    from agent_net.node.daemon import app
    from agent_net.node._auth import init_daemon_token
    from agent_net.storage import create_coordination_session, register_owner, create_profile_session

    owner = await register_owner("CrOwner")
    cs_id = _uid("cs")
    await create_coordination_session(
        coordination_session_id=cs_id,
        owner_did=owner["did"],
        controller_did=owner["did"],
        objective="cp24",
    )
    session = await create_profile_session(
        _uid("psess"),
        coordination_session_id=cs_id,
        coordinator_id="urn:code-review:coordinator:test",
        external_run_id=_uid("RUN"),
        review_policy_sha256="a" * 64,
    )
    client = TestClient(app, headers={"Authorization": f"Bearer {init_daemon_token()}"})
    resp = client.post(
        "/coordination/receipts",
        json={
            "coordination_session_id": session["coordination_session_id"],
            "receipt_id": _uid("rcpt"),
            "stage": "code_review",
            "decision": "approved",
            "actor_did": "did:agentnexus:worker",
        },
    )
    assert resp.status_code == 403, resp.text


# ═══════════════════════════════════════════════════════════════════════
# 2026-09-22 复审 R2-1～R2-4 的回归测试
# ═══════════════════════════════════════════════════════════════════════


# ── R2-1：幂等预留不得在失败后卡死恢复 ────────────────────────────────


@pytest.mark.asyncio
async def test_r21_vault_failure_then_same_key_retry_recovers(monkeypatch):
    """复审 R2-1 复现：Vault 失败一次后，同 key 重试曾被判 409 永久无法恢复。"""
    from agent_net.node.routers import code_review as router_module
    from agent_net.persistence import enclave

    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    client = _client(headers)
    key = _uid("idem")
    request = _artifact_request(session["external_run_id"])

    real_vault_put = enclave.vault_put
    calls = {"n": 0}

    async def flaky_vault_put(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("injected storage failure")
        return await real_vault_put(*args, **kwargs)

    monkeypatch.setattr(router_module, "vault_put", flaky_vault_put)

    first = client.post(ARTIFACT_URL, json=request, headers={"Idempotency-Key": key})
    assert first.status_code == 503, first.text
    assert first.json()["code"] == "temporarily_unavailable"

    # 相同 key、相同请求：必须可恢复，而不是 delivery_conflict
    second = client.post(ARTIFACT_URL, json=request, headers={"Idempotency-Key": key})
    assert second.status_code == 201, second.text
    assert second.json()["digest"] == FROZEN_REPORT_DIGEST

    # 再重放：此时已 committed，返回同一 artifact
    third = client.post(ARTIFACT_URL, json=request, headers={"Idempotency-Key": key})
    assert third.status_code == 201
    assert third.json()["artifact_id"] == second.json()["artifact_id"]


@pytest.mark.asyncio
async def test_r21_artifact_insert_failure_leaves_no_committed_mapping(monkeypatch):
    """产物登记失败不得留下 committed 映射（否则同 key 永远拿不到产物）。"""
    from agent_net.node.routers import code_review as router_module
    from agent_net.persistence import code_review_store

    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    client = _client(headers)
    key = _uid("idem")
    request = _artifact_request(session["external_run_id"])

    calls = {"n": 0}
    real_commit = code_review_store.commit_artifact_with_idempotency

    async def flaky_commit(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("injected insert failure")
        return await real_commit(**kwargs)

    monkeypatch.setattr(router_module, "commit_artifact_with_idempotency", flaky_commit)

    with pytest.raises(OSError):
        client.post(ARTIFACT_URL, json=request, headers={"Idempotency-Key": key})

    # 同 key 必须仍可成功（映射仍是 pending，不得被当成 committed 内容冲突）
    recovered = client.post(ARTIFACT_URL, json=request, headers={"Idempotency-Key": key})
    assert recovered.status_code == 201, recovered.text


# ── R2-2：上传必须绑定真实 Run/Attempt/epoch ─────────────────────────


@pytest.mark.asyncio
async def test_r22_unregistered_run_is_rejected():
    """复审 R2-2 复现：unregistered-run 曾被 201。"""
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    resp = _client(headers).post(
        ARTIFACT_URL,
        json=_artifact_request("RUN-never-registered"),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "input_mismatch"


@pytest.mark.asyncio
async def test_r22_unassigned_attempt_and_wrong_epoch_are_rejected():
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    client = _client(headers)

    unassigned = client.post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"], attempt_id="A-never-assigned"),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert unassigned.status_code == 409, unassigned.text
    assert unassigned.json()["code"] == "stale_assignment"

    wrong_epoch = client.post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"], assignment_epoch=999),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert wrong_epoch.status_code == 409, wrong_epoch.text
    assert wrong_epoch.json()["code"] == "stale_assignment"


@pytest.mark.asyncio
async def test_r22_other_worker_is_rejected():
    session = await _profile_session()
    assigned = "did:agentnexus:worker"
    await _bind_assignment(session, worker_did=assigned)
    intruder = "did:agentnexus:other-worker"
    headers = await _provision(
        principal_id=intruder,
        roles=["worker"],
        dids=[intruder],
        sessions=[session["profile_session_id"]],
    )
    resp = _client(headers).post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"]),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "authority_denied"


@pytest.mark.asyncio
async def test_r22_cancelled_assignment_is_rejected():
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]])
    await _bind_assignment(session, worker_did=worker_did, status="cancelled")
    resp = _client(headers).post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"]),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "stale_assignment"


# ── R2-3：被拒的冲突消息不得产生业务记录 ─────────────────────────────


async def _receipt_count() -> int:
    from agent_net.persistence.context import connect

    async with connect() as db:
        async with db.execute("SELECT COUNT(*) FROM code_review_receipts") as cur:
            (count,) = await cur.fetchone()
    return count


@pytest.mark.asyncio
async def test_r23_conflicting_message_has_no_receipt_side_effect():
    """复审 R2-3 复现：409 之后新 receipt 仍然出现在数据库。"""
    session = await _profile_session()
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)
    message_id = _uid("msg")

    def receipt_envelope(receipt_id: str) -> dict:
        envelope = _envelope(
            "receipt",
            session_id=session["coordination_session_id"],
            sender="urn:code-review:coordinator:test",
            run_id=session["external_run_id"],
            payload=_receipt_payload(
                session["external_run_id"],
                kind="accepted",
                issuer_id="urn:code-review:coordinator:test",
                receipt_id=receipt_id,
            ),
        )
        envelope["message_id"] = message_id
        return envelope

    first = client.post(MESSAGE_URL, json=receipt_envelope(_uid("rcpt")))
    assert first.status_code == 202, first.text

    before = await _receipt_count()
    conflict = client.post(MESSAGE_URL, json=receipt_envelope(_uid("rcpt")))
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "idempotency_conflict"
    assert await _receipt_count() == before, "被拒的冲突消息产生了业务记录"


@pytest.mark.asyncio
async def test_r23_receipt_id_reuse_with_different_projection_conflicts():
    """同一 receipt_id 不得被静默重放为旧回执（不同决定必须冲突且无副作用）。"""
    session = await _profile_session()
    headers = await _coordinator(sessions=[session["profile_session_id"]])
    client = _client(headers)
    receipt_id = _uid("rcpt")

    def envelope_for(message_id: str, report_digest: str) -> dict:
        envelope = _envelope(
            "receipt",
            session_id=session["coordination_session_id"],
            sender="urn:code-review:coordinator:test",
            run_id=session["external_run_id"],
            payload=_receipt_payload(
                session["external_run_id"],
                kind="accepted",
                issuer_id="urn:code-review:coordinator:test",
                receipt_id=receipt_id,
                report_digest=report_digest,
            ),
        )
        envelope["message_id"] = message_id
        return envelope

    first = client.post(MESSAGE_URL, json=envelope_for(_uid("msg"), "sha256:" + "1" * 64))
    assert first.status_code == 202, first.text
    before = await _receipt_count()

    conflict = client.post(MESSAGE_URL, json=envelope_for(_uid("msg"), "sha256:" + "2" * 64))
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "idempotency_conflict"
    assert await _receipt_count() == before


# ── R2-4：validator / publisher 不得被额外要求 coordinator ───────────


@pytest.mark.asyncio
async def test_r24_validator_and_publisher_roles_work_under_real_grants():
    """复审 R2-4 复现：启用 role_grants 后合法 validator 被要求 coordinator（403）。"""
    from agent_net.storage import grant_role

    session = await _profile_session()
    cases = (
        ("validator", "did:agentnexus:validator", "validated"),
        ("publisher", "did:agentnexus:publisher", "published"),
    )
    for role, did, _kind in cases:
        await grant_role(did, role)

    for role, did, kind in cases:
        headers = await _provision(
            principal_id=did,
            roles=[role],
            dids=[did],
            sessions=[session["profile_session_id"]],
        )
        envelope = _envelope(
            "receipt",
            session_id=session["coordination_session_id"],
            sender=did,
            run_id=session["external_run_id"],
            payload=_receipt_payload(session["external_run_id"], kind=kind, issuer_id=did),
        )
        resp = _client(headers).post(MESSAGE_URL, json=envelope)
        assert resp.status_code == 202, f"{kind}: {resp.text}"


@pytest.mark.asyncio
async def test_r24_role_grant_required_even_if_credential_declares_role():
    """凭据声明的角色不能替代服务端 role_grant（有 role_grants 时按登记表硬校验）。"""
    from agent_net.storage import grant_role

    session = await _profile_session()
    await grant_role("urn:code-review:coordinator:test", "coordinator")
    headers = await _provision(
        principal_id="did:agentnexus:validator",
        roles=["validator"],
        dids=["did:agentnexus:validator"],
        sessions=[session["profile_session_id"]],
    )
    envelope = _envelope(
        "receipt",
        session_id=session["coordination_session_id"],
        sender="did:agentnexus:validator",
        run_id=session["external_run_id"],
        payload=_receipt_payload(
            session["external_run_id"], kind="validated", issuer_id="did:agentnexus:validator"
        ),
    )
    resp = _client(headers).post(MESSAGE_URL, json=envelope)
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "authority_denied"


# ── 协议边界：retention 原样回显 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_cr_api_retention_is_echoed_verbatim():
    """复审「协议边界」：retention_until 必须原样回显，不得因 float 反格式化丢精度。"""
    session = await _profile_session()
    worker_did = "did:agentnexus:worker"
    headers = await _worker(worker_did, sessions=[session["profile_session_id"]], bind=session)
    requested = "2026-12-31T00:00:00.123456Z"
    resp = _client(headers).post(
        ARTIFACT_URL,
        json=_artifact_request(session["external_run_id"], retention=requested),
        headers={"Idempotency-Key": _uid("idem")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["retention_until"] == requested
