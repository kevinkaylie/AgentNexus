"""L0 服务接口的 **HTTP 契约矩阵**（binding RC2 §1/§4/§7/§10.1）。

为什么单独建这一个文件
----------------------
前三轮评审反复出现同一类缺陷（B3、R2-2、R2-3，以及复审遗留的 P2 列表），根因是
既有测试断言的是"实现里有哪些字段"，而不是**冻结契约在 wire 上的行为**。于是
"字段存在但 wire 不一致"每次都留给评审去发现。

本文件把契约本身当成被测对象：**每个端点 × 每个声明的失败条件**组成一张矩阵，
逐行发起**真实 HTTP 请求**，并对**实际响应**做三重校验：

1. HTTP 状态码与 ``code_review.error.v1`` 的错误码/``scope``；
2. 错误响应体**真正通过冻结 ``error.schema.json``**（类型、const、additionalProperties、
   allOf 不变式）；
3. 成功响应体通过其冻结 schema（``artifact_ref.schema.json``），或与契约文本规定的
   字段集合**完全一致**（TransportAck / MessageView 是 binding DTO，不是 Profile schema）。

矩阵之外另有两组横切断言：传输层头（``Cache-Control: no-store``、``charset=utf-8``）
与读取上限（413）。

「矩阵行」是数据，不是散落的测试函数：新增一条契约行为 = 新增一行。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import jsonschema
import pytest
import pytest_asyncio
from referencing import Registry, Resource

PACKAGE = Path(__file__).resolve().parents[1] / "specs" / "profiles" / "code-review" / "v1"
PREFIX = "/coordination/code-review/v1"
MESSAGES = f"{PREFIX}/messages"
ARTIFACTS = f"{PREFIX}/artifacts"

COORDINATOR = "urn:code-review:coordinator:test"
WORKER = "did:agentnexus:worker"
CORRELATION = "corr-contract-1"


# ── 冻结 schema 的加载（矩阵用它校验**实际响应**） ─────────────────────


def _frozen_validator(schema_name: str) -> jsonschema.Draft202012Validator:
    schemas: Dict[str, dict] = {}
    for path in sorted((PACKAGE / "schemas").glob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        schemas[path.name] = doc
    registry = Registry().with_resources(
        [(doc["$id"], Resource.from_contents(doc)) for doc in schemas.values()]
    )
    return jsonschema.Draft202012Validator(
        schemas[schema_name], registry=registry, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )


def assert_error_envelope(response) -> dict:
    """错误响应必须是合法的 ``code_review.error.v1``（真正跑冻结 schema）。"""
    body = response.json()
    errors = sorted(_frozen_validator("error.schema.json").iter_errors(body), key=lambda e: list(e.path))
    assert not errors, [f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors]
    return body


# ── 世界（world）：一次建立全部前置资源 ────────────────────────────────


class World:
    """矩阵行的执行上下文：凭据、会话、分配、已上传产物。"""

    def __init__(self) -> None:
        self.sessions: Dict[str, dict] = {}
        self.headers: Dict[str, dict] = {}
        self.messages: Dict[str, str] = {}
        self.artifacts: Dict[str, str] = {}

    def client(self, who: str):
        from fastapi.testclient import TestClient

        from agent_net.node.daemon import app

        return TestClient(app, headers=self.headers[who])

    def path(self, key: str) -> str:
        if key == "messages":
            return MESSAGES
        if key == "message":
            return f"{MESSAGES}/{self.messages['assignment']}"
        if key == "message_receipt":
            return f"{MESSAGES}/{self.messages['receipt']}"
        if key == "artifacts":
            return ARTIFACTS
        if key == "raw":
            return f"{ARTIFACTS}/{self.artifacts['report']}/raw"
        raise KeyError(key)


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


async def _credential(principal_id: str, roles, dids, sessions=()) -> dict:
    from agent_net.storage import register_service_principal

    credential = f"cred_{uuid.uuid4().hex}"
    await register_service_principal(
        credential,
        principal_id=principal_id,
        roles=list(roles),
        dids=list(dids),
        sessions=list(sessions),
    )
    return {"Authorization": f"Bearer {credential}"}


def _assignment_payload(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "attempt_id": "A1",
        "assignment_epoch": 1,
        "coordinator_id": COORDINATOR,
        "input_manifest_digest": "sha256:" + "b" * 64,
        "output_schema": "code_review.report.v1",
        "policy_ref": "policy:code-review:1",
        "authority_ref": "authz://hczj/review/deliver/RUN-1",
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


def _envelope(msg_type: str, *, session_id: str, sender: str, run_id: str, payload: dict) -> dict:
    envelope = {
        "profile": "agentnexus.code-review/1.0-draft.2",
        "message_id": _uid("msg"),
        "type": msg_type,
        "sender_id": sender,
        "receiver_id": "did:agentnexus:adapter",
        "session_id": session_id,
        "correlation_id": CORRELATION,
        "causation_id": None,
        "created_at": "2026-09-20T00:00:00Z",
        "payload": payload,
    }
    # receipt / cancel_request 在冻结 envelope schema 里也要求 run_id（不要求 attempt_id）
    if msg_type in ("assignment", "delivery", "assignment_acceptance", "cancel_acknowledgement"):
        envelope.update({"run_id": run_id, "attempt_id": "A1", "assignment_epoch": 1})
    elif msg_type in ("receipt", "cancel_request", "feedback", "publication_request"):
        envelope.update({"run_id": run_id, "assignment_epoch": 1})
    return envelope


def _receipt_payload(run_id: str, *, kind: str, issuer_id: str) -> dict:
    return {
        "schema": "code_review.receipt.v1",
        "receipt_id": _uid("rcpt"),
        "kind": kind,
        "issuer_id": issuer_id,
        "subject_ref": {"kind": "delivery", "id": "del_1"},
        "run_id": run_id,
        "attempt_id": "A1",
        "decision": "confirmed",
        "created_at": "2026-09-20T00:00:00Z",
        "authority_ref": "authz://hczj/review/deliver/RUN-1",
        "evidence_refs": [],
    }


def _report_body() -> str:
    return (
        PACKAGE / "fixtures" / "valid" / "05_review_report_partial_inconclusive.artifact_body.json"
    ).read_text(encoding="utf-8")


def _artifact_request(run_id: str, **extra) -> dict:
    request = {
        "run_id": run_id,
        "attempt_id": "A1",
        "assignment_epoch": 1,
        "artifact_body": _report_body(),
        "media_type": "application/json",
        "schema_version": "code_review.report.v1",
        "retention_until": "2026-12-31T00:00:00Z",
    }
    request.update(extra)
    return request


@pytest_asyncio.fixture
async def world() -> World:
    from agent_net.storage import (
        bind_execution_assignment,
        create_coordination_session,
        create_objective_execution,
        create_profile_session,
        grant_role,
        register_owner,
        set_enforcement,
    )

    w = World()
    # 合成注册项只测试 HTTP 门禁，不构成 local_cli 网络隔离或 CP-25 实证。
    await set_enforcement("provider_outbound_data", "enforced", "synthetic-test-enforcer")

    owner = await register_owner("ContractOwner")
    cs_id = _uid("cs")
    await create_coordination_session(
        coordination_session_id=cs_id,
        owner_did=owner["did"],
        controller_did=owner["did"],
        objective="http contract matrix",
    )
    profile = await create_profile_session(
        _uid("psess"),
        coordination_session_id=cs_id,
        coordinator_id=COORDINATOR,
        external_run_id=_uid("RUN"),
        review_policy_sha256="a" * 64,
    )
    w.sessions["profile"] = profile

    execution_id = _uid("exec")
    await create_objective_execution(
        execution_id=execution_id,
        coordination_session_id=cs_id,
        run_id=profile["external_run_id"],
        stage="code_review",
        worker_did=WORKER,
        backend_kind="local_cli",
        lease_expires_at=time.time() + 3600,
    )
    await bind_execution_assignment(
        execution_id,
        profile_session_id=profile["profile_session_id"],
        external_coordinator_id=COORDINATOR,
        external_run_id=profile["external_run_id"],
        external_attempt_id="A1",
        assignment_epoch=1,
        input_manifest_digest="sha256:" + "b" * 64,
        output_schema="code_review.report.v1",
    )

    # 角色登记表：本矩阵用于验证"启用严格角色表后分工仍能工作"
    for principal, role in ((COORDINATOR, "coordinator"), (WORKER, "worker")):
        await grant_role(principal, role)

    scope = [profile["profile_session_id"]]
    w.headers["coordinator"] = await _credential(COORDINATOR, ["coordinator"], [COORDINATOR], scope)
    w.headers["worker"] = await _credential(WORKER, ["worker"], [WORKER], scope)
    w.headers["other_worker"] = await _credential(
        "did:agentnexus:other-worker", ["worker"], ["did:agentnexus:other-worker"], scope
    )
    w.headers["outsider"] = await _credential(
        "did:agentnexus:outsider", ["coordinator"], ["did:agentnexus:outsider"], ["psess_elsewhere"]
    )
    w.headers["party"] = await _credential(
        "did:agentnexus:adapter", ["evidence_reader"], ["did:agentnexus:adapter"], scope
    )

    # 预置一条 assignment 消息与一份产物，供 GET 类用例使用
    assignment = _envelope(
        "assignment",
        session_id=cs_id,
        sender=COORDINATOR,
        run_id=profile["external_run_id"],
        payload=_assignment_payload(profile["external_run_id"]),
    )
    created = w.client("coordinator").post(
        MESSAGES,
        json=assignment,
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": assignment["message_id"]},
    )
    assert created.status_code == 202, created.text
    w.messages["assignment"] = assignment["message_id"]

    uploaded = w.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(profile["external_run_id"]),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem")},
    )
    assert uploaded.status_code == 201, uploaded.text
    w.artifacts["report"] = uploaded.json()["artifact_id"]
    return w


# ═══════════════════════════════════════════════════════════════════════
# 矩阵定义：每个端点 × 每个声明的失败条件
# ═══════════════════════════════════════════════════════════════════════

OMIT = object()  # 该行显式省略某个头


def _row(id, method, path, who, *, status, code=None, scope=None, headers=None, body=None,
         raw_body=None, schema=None, note="", path_override=None) -> dict:
    return {
        "id": id, "method": method, "path": path, "who": who, "status": status,
        "code": code, "scope": scope, "headers": headers or {}, "body": body,
        "raw_body": raw_body, "schema": schema, "note": note, "path_override": path_override,
    }


def _assignment_body(world: World) -> dict:
    profile = world.sessions["profile"]
    return _envelope(
        "assignment",
        session_id=profile["coordination_session_id"],
        sender=COORDINATOR,
        run_id=profile["external_run_id"],
        payload=_assignment_payload(profile["external_run_id"]),
    )


def _artifact_body(world: World) -> dict:
    return _artifact_request(world.sessions["profile"]["external_run_id"])


MATRIX: List[dict] = [
    # ── POST A/messages ───────────────────────────────────────────────
    _row("messages.ok", "POST", "messages", "coordinator", status=202,
         headers={"X-Correlation-Id": CORRELATION},
         body=_assignment_body,
         note="TransportAck 恰好三字段；Idempotency-Key 由 _materialize 按 message_id 注入"),
    _row("messages.correlation_missing", "POST", "messages", "coordinator", status=422,
         code="invalid_output", scope="envelope", headers={}, body=_assignment_body,
         note="RC2 §1：新增接口必带 X-Correlation-Id"),
    _row("messages.correlation_mismatch", "POST", "messages", "coordinator", status=422,
         code="invalid_output", scope="envelope",
         headers={"X-Correlation-Id": "corr-other"}, body=_assignment_body),
    _row("messages.duplicate_key", "POST", "messages", "coordinator", status=422,
         code="invalid_output", scope="envelope",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "msg_dup_1"},
         raw_body=b'{"message_id":"msg_dup_1","message_id":"msg_dup_1"}',
         note="RC2 §1/§3：拒绝重复键"),
    _row("messages.nan", "POST", "messages", "coordinator", status=422,
         code="invalid_output", scope="envelope",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "msg_nan_1"},
         raw_body=b'{"message_id":"msg_nan_1","x":NaN}', note="RC2 §1/§3：拒绝非有限数"),
    _row("messages.bom", "POST", "messages", "coordinator", status=422,
         code="invalid_output", scope="envelope",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "msg_bom_1"},
         raw_body=b'\xef\xbb\xbf{"message_id":"msg_bom_1"}', note="RC2 §1：请求 UTF-8 无 BOM"),
    _row("messages.idempotency_missing", "POST", "messages", "coordinator", status=422,
         code="input_mismatch", scope="message", headers={"X-Correlation-Id": CORRELATION},
         body=_assignment_body,
         note="2026-09-22 裁决：§1 规定传输位置（头），§4 规定取值（= message_id）；缺头即拒"),
    _row("messages.idempotency_key_mismatch", "POST", "messages", "coordinator", status=409,
         code="idempotency_conflict", scope="message",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "not-the-message-id"},
         body=_assignment_body, note="同一逻辑幂等键：头值必须等于 envelope.message_id"),
    _row("messages.unknown_type", "POST", "messages", "coordinator", status=422,
         code="unsupported_capability", scope="message_routing",
         headers={"X-Correlation-Id": CORRELATION},
         body=lambda w: dict(_assignment_body(w), type="delivery", payload={"x": 1})),
    _row("messages.empty_payload", "POST", "messages", "coordinator", status=422,
         code="invalid_output", scope="envelope", headers={"X-Correlation-Id": CORRELATION},
         body=lambda w: dict(_assignment_body(w), payload={})),
    _row("messages.sender_not_bound", "POST", "messages", "coordinator", status=403,
         code="authority_denied", scope="authorization", headers={"X-Correlation-Id": CORRELATION},
         body=lambda w: dict(_assignment_body(w), sender_id="urn:code-review:coordinator:other")),
    _row("messages.worker_forges_accepted", "POST", "messages", "worker", status=403,
         code="authority_denied", scope="authorization", headers={"X-Correlation-Id": CORRELATION},
         body=lambda w: dict(
             _envelope(
                 "receipt",
                 session_id=w.sessions["profile"]["coordination_session_id"],
                 sender=WORKER,
                 run_id=w.sessions["profile"]["external_run_id"],
                 payload=_receipt_payload(
                     w.sessions["profile"]["external_run_id"], kind="accepted", issuer_id=WORKER
                 ),
             ),
             run_id=w.sessions["profile"]["external_run_id"],
             attempt_id="A1",
         )),
    _row("messages.oversize", "POST", "messages", "coordinator", status=413,
         code="data_policy_denied", scope="read_limit",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "msg_pad"},
         raw_body=b'{"pad":"' + b"x" * (4 * 1024 * 1024 + 16) + b'"}',
         note="§10.1：JSON 响应上限 4 MiB；长度在解析前判定，故头只需存在"),

    # ── GET A/messages/{message_id} ───────────────────────────────────
    _row("message.ok", "GET", "message", "party", status=200,
         headers={"X-Correlation-Id": CORRELATION}, note="MessageView 恰好四字段"),
    _row("message.correlation_missing", "GET", "message", "party", status=422,
         code="invalid_output", scope="envelope", headers={}),
    _row("message.not_found", "GET", "message", "party", status=422,
         code="input_mismatch", scope="message",
         headers={"X-Correlation-Id": CORRELATION},
         path_override=f"{MESSAGES}/msg_does_not_exist",
         note='§7 把 input_mismatch 归在 400/422；404/410 只对应 evidence_unavailable/artifact_expired，'
              '而"消息不存在"不属于固定证据缺失，故取 422'),
    _row("message.cross_session", "GET", "message", "outsider", status=403,
         code="authority_denied", scope="authorization", headers={"X-Correlation-Id": CORRELATION}),

    # ── POST A/artifacts ─────────────────────────────────────────────
    _row("artifacts.ok", "POST", "artifacts", "worker", status=201,
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "idem-ok"},
         body=_artifact_body, schema="artifact_ref.schema.json"),
    _row("artifacts.correlation_missing", "POST", "artifacts", "worker", status=422,
         code="invalid_output", scope="envelope", headers={"Idempotency-Key": "idem-x"},
         body=_artifact_body),
    _row("artifacts.idempotency_missing", "POST", "artifacts", "worker", status=422,
         code="input_mismatch", scope="artifact", headers={"X-Correlation-Id": CORRELATION},
         body=_artifact_body, note="RC2 §4：上传必须带 Idempotency-Key"),
    _row("artifacts.duplicate_key", "POST", "artifacts", "worker", status=422,
         code="invalid_output", scope="artifact",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "idem-dup"},
         raw_body=b'{"run_id":"a","run_id":"b"}'),
    _row("artifacts.nan", "POST", "artifacts", "worker", status=422,
         code="invalid_output", scope="artifact",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "idem-nan"},
         raw_body=b'{"run_id":NaN}'),
    _row("artifacts.bom", "POST", "artifacts", "worker", status=422,
         code="invalid_output", scope="artifact",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "idem-bom"},
         raw_body=b"\xef\xbb\xbf{}"),
    _row("artifacts.unknown_field", "POST", "artifacts", "worker", status=422,
         code="invalid_output", scope="artifact",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "idem-unknown"},
         body=lambda w: dict(_artifact_body(w), producer_id=WORKER),
         note="B3：只接受契约七字段"),
    _row("artifacts.retention_beyond_commitment", "POST", "artifacts", "worker", status=422,
         code="data_policy_denied", scope="retention",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "idem-ret"},
         body=lambda w: dict(_artifact_body(w), retention_until="2099-01-01T00:00:00Z")),
    _row("artifacts.unknown_run", "POST", "artifacts", "worker", status=422,
         code="input_mismatch", scope="artifact",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "idem-run"},
         body=lambda w: dict(_artifact_body(w), run_id="RUN-never-registered")),
    _row("artifacts.unassigned_attempt", "POST", "artifacts", "worker", status=409,
         code="stale_assignment", scope="artifact",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "idem-att"},
         body=lambda w: dict(_artifact_body(w), attempt_id="A-never-assigned")),
    _row("artifacts.wrong_epoch", "POST", "artifacts", "worker", status=409,
         code="stale_assignment", scope="artifact",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "idem-epoch"},
         body=lambda w: dict(_artifact_body(w), assignment_epoch=999)),
    _row("artifacts.wrong_worker", "POST", "artifacts", "other_worker", status=403,
         code="authority_denied", scope="authorization",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "idem-other"},
         body=_artifact_body),
    _row("artifacts.oversize", "POST", "artifacts", "worker", status=413,
         code="data_policy_denied", scope="read_limit",
         headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "idem-big"},
         raw_body=b'{"pad":"' + b"x" * (16 * 1024 * 1024 + 16) + b'"}'),

    # ── GET A/artifacts/{id}/raw ─────────────────────────────────────
    _row("raw.ok", "GET", "raw", "party", status=200,
         headers={"X-Correlation-Id": CORRELATION},
         note="原始字节 + ETag + Content-Length"),
    _row("raw.correlation_missing", "GET", "raw", "party", status=422,
         code="invalid_output", scope="envelope", headers={}),
    _row("raw.if_match_mismatch", "GET", "raw", "party", status=412,
         code="evidence_digest_mismatch", scope="artifact_read",
         headers={"X-Correlation-Id": CORRELATION, "If-Match": '"sha256:' + "0" * 64 + '"'},
         note="RC2 §2：If-Match 不匹配返回 412（不是 409）"),
    _row("raw.range_not_supported", "GET", "raw", "party", status=422,
         code="invalid_output", scope="artifact_read",
         headers={"X-Correlation-Id": CORRELATION, "Range": "bytes=0-10"},
         note="未声明 Range 支持，必须显式拒绝而非静默返回全量"),
    _row("raw.not_found", "GET", "raw", "party", status=404,
         code="evidence_unavailable", scope="artifact_read",
         headers={"X-Correlation-Id": CORRELATION},
         path_override=f"{ARTIFACTS}/art_does_not_exist/raw"),
    _row("raw.cross_session", "GET", "raw", "outsider", status=403,
         code="authority_denied", scope="authorization", headers={"X-Correlation-Id": CORRELATION}),
]


#: 这两行**故意**不带 Idempotency-Key（规则 1/2 的被测对象），其余消息行由
#: `_materialize` 按信封 message_id 自动补齐该头。
OMIT_IDEMPOTENCY_KEY_ROWS = {"messages.idempotency_missing", "messages.idempotency_key_mismatch"}


def _materialize(world: World, row: dict):
    path = row.get("path_override") or world.path(row["path"])
    headers = dict(row["headers"])
    body = row["body"](world) if callable(row["body"]) else row["body"]
    raw_body = row["raw_body"]
    if body is not None and raw_body is None:
        raw_body = json.dumps(body).encode("utf-8")

    if row["method"] == "POST" and row["path"] == "messages":
        if row["id"] not in OMIT_IDEMPOTENCY_KEY_ROWS and "Idempotency-Key" not in headers:
            if isinstance(body, dict) and "message_id" in body:
                headers["Idempotency-Key"] = body["message_id"]
            # 原始字节行（重复键/NaN/BOM/超限）自行在 headers 里声明该头；
            # 超限在解析前就被 413 拦下，其余行的原始体里嵌了对应的 message_id。
    return path, headers, raw_body


@pytest.mark.asyncio
@pytest.mark.parametrize("row", MATRIX, ids=[r["id"] for r in MATRIX])
async def test_http_contract_matrix(world, row, capsys):
    """矩阵执行器：真实 HTTP 请求 → 状态码 + 错误码/scope + 冻结 schema 三重校验。"""
    path, headers, raw_body = _materialize(world, row)
    client = world.client(row["who"])

    if row["method"] == "GET":
        response = client.get(path, headers=headers)
    else:
        response = client.post(
            path, content=raw_body, headers={**headers, "Content-Type": "application/json"}
        )

    assert response.status_code == row["status"], (
        f"{row['id']}: 期望 {row['status']}，实际 {response.status_code}；{response.text[:300]}"
    )

    if row["status"] >= 400:
        body = assert_error_envelope(response)
        if row["code"]:
            assert body["code"] == row["code"], f"{row['id']}: code={body['code']!r}"
        if row["scope"]:
            assert body["scope"] == row["scope"], f"{row['id']}: scope={body['scope']!r}"
    elif row["schema"]:
        payload = response.json()
        errors = sorted(
            _frozen_validator(row["schema"]).iter_errors(payload), key=lambda e: list(e.path)
        )
        assert not errors, [f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors]

    # 传输层头对**任何**响应都必须成立（RC2 §1）
    assert response.headers.get("Cache-Control") == "no-store", row["id"]


# ── 成功 DTO 的字段集合必须与契约文本完全一致 ─────────────────────────


@pytest.mark.asyncio
async def test_transport_ack_is_exactly_three_fields(world):
    body = {"payload": _assignment_payload(world.sessions["profile"]["external_run_id"])}
    envelope = _envelope(
        "assignment",
        session_id=world.sessions["profile"]["coordination_session_id"],
        sender=COORDINATOR,
        run_id=world.sessions["profile"]["external_run_id"],
        payload=body["payload"],
    )
    response = world.client("coordinator").post(
        MESSAGES,
        json=envelope,
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": envelope["message_id"]},
    )
    assert response.status_code == 202
    assert set(response.json()) == {"message_id", "status", "status_url"}
    assert response.json()["status"] == "stored"
    assert response.headers["Content-Type"].startswith("application/json")
    assert "charset=utf-8" in response.headers["Content-Type"].lower()


@pytest.mark.asyncio
async def test_message_view_is_exactly_four_fields(world):
    response = world.client("party").get(
        f"{MESSAGES}/{world.messages['assignment']}", headers={"X-Correlation-Id": CORRELATION}
    )
    assert response.status_code == 200
    assert set(response.json()) == {"message_id", "state", "receipts", "error"}


@pytest.mark.asyncio
async def test_raw_response_headers_are_byte_exact(world):
    response = world.client("party").get(
        f"{ARTIFACTS}/{world.artifacts['report']}/raw", headers={"X-Correlation-Id": CORRELATION}
    )
    assert response.status_code == 200
    assert int(response.headers["Content-Length"]) == len(response.content)
    assert response.headers["ETag"].startswith('"sha256:')
    assert response.headers["Content-Type"] in ("application/json", "application/octet-stream")


@pytest.mark.asyncio
async def test_raw_media_type_is_the_registered_one(world):
    """raw 的 Content-Type 必须取已登记 media_type（RC2 §4）。"""
    response = world.client("party").get(
        f"{ARTIFACTS}/{world.artifacts['report']}/raw", headers={"X-Correlation-Id": CORRELATION}
    )
    assert response.headers["Content-Type"] == "application/json"


# ── 认证失败的优先级：先于资源详情（RC2 §1） ──────────────────────────


@pytest.mark.asyncio
async def test_authentication_precedes_resource_detail(world):
    """未认证请求不得泄露资源是否存在（404 与 403 对未认证方都应是 401）。"""
    from fastapi.testclient import TestClient

    from agent_net.node.daemon import app

    anonymous = TestClient(app, headers={"Authorization": "Bearer not-registered"})
    missing = anonymous.get(f"{MESSAGES}/msg_missing", headers={"X-Correlation-Id": CORRELATION})
    existing = anonymous.get(
        f"{MESSAGES}/{world.messages['assignment']}", headers={"X-Correlation-Id": CORRELATION}
    )
    assert missing.status_code == existing.status_code == 401
    assert missing.json()["code"] == existing.json()["code"] == "authority_denied"


@pytest.mark.asyncio
async def test_unconfigured_deployment_refuses_with_401(tmp_path):
    """RC2 §1：未登记任何服务凭据时必须拒绝，不得"未配置则放行"。"""
    from fastapi.testclient import TestClient

    from agent_net.node.daemon import app

    client = TestClient(app, headers={"Authorization": "Bearer anything"})
    for method, url in (
        ("post", MESSAGES),
        ("get", f"{MESSAGES}/x"),
        ("post", ARTIFACTS),
        ("get", f"{ARTIFACTS}/x/raw"),
    ):
        response = getattr(client, method)(url, headers={"X-Correlation-Id": CORRELATION})
        assert response.status_code == 401, f"{method} {url}: {response.status_code}"
        assert assert_error_envelope(response)["code"] == "authority_denied"


# ── 消息幂等键的四条执行规则（2026-09-22 裁决） ────────────────────────


def _message_pair(world: World, *, payload_variant: str = "a") -> tuple:
    """同一 message_id + 同头；`payload_variant` 只改业务投影。"""
    profile = world.sessions["profile"]
    payload = _assignment_payload(profile["external_run_id"])
    payload["policy_ref"] = f"policy:code-review:{payload_variant}"
    envelope = _envelope(
        "assignment",
        session_id=profile["coordination_session_id"],
        sender=COORDINATOR,
        run_id=profile["external_run_id"],
        payload=payload,
    )
    headers = {"X-Correlation-Id": CORRELATION, "Idempotency-Key": envelope["message_id"]}
    return envelope, headers


@pytest.mark.asyncio
async def test_idempotency_rule_1_missing_or_empty_header(world):
    """规则 1：缺少或空头 → 422 input_mismatch，且**不写入**。"""
    from agent_net.persistence.context import connect

    envelope, headers = _message_pair(world)
    client = world.client("coordinator")

    async def message_count() -> int:
        async with connect() as db:
            async with db.execute("SELECT COUNT(*) FROM code_review_messages") as cur:
                (count,) = await cur.fetchone()
        return count

    before = await message_count()
    # None 表示"不发该头"；空串与纯空白也要拒绝
    for variant in (None, "", "   "):
        request_headers = {"X-Correlation-Id": CORRELATION}
        if variant is not None:
            request_headers["Idempotency-Key"] = variant
        response = client.post(MESSAGES, json=envelope, headers=request_headers)
        assert response.status_code == 422, f"variant={variant!r}: {response.text}"
        assert assert_error_envelope(response)["code"] == "input_mismatch"
    assert await message_count() == before, "缺头/空头的请求产生了写入"


@pytest.mark.asyncio
async def test_idempotency_rule_2_header_must_equal_message_id(world):
    """规则 2：头与取值不一致 → 409 idempotency_conflict，且不写入。"""
    from agent_net.persistence.context import connect

    envelope, headers = _message_pair(world)
    client = world.client("coordinator")

    async def message_count() -> int:
        async with connect() as db:
            async with db.execute("SELECT COUNT(*) FROM code_review_messages") as cur:
                (count,) = await cur.fetchone()
        return count

    before = await message_count()
    response = client.post(
        MESSAGES, json=envelope, headers={**headers, "Idempotency-Key": _uid("other")}
    )
    assert response.status_code == 409, response.text
    assert assert_error_envelope(response)["code"] == "idempotency_conflict"
    assert await message_count() == before


@pytest.mark.asyncio
async def test_idempotency_rule_3_same_key_same_projection_replays(world):
    """规则 3：一致且同业务投影 → 返回原处理结果（不新建记录、不重复签发）。"""
    from agent_net.persistence.context import connect

    envelope, headers = _message_pair(world)
    client = world.client("coordinator")

    async def message_count() -> int:
        async with connect() as db:
            async with db.execute(
                "SELECT COUNT(*) FROM code_review_messages WHERE message_id=?", (envelope["message_id"],)
            ) as cur:
                (count,) = await cur.fetchone()
        return count

    first = client.post(MESSAGES, json=envelope, headers=headers)
    assert first.status_code == 202, first.text
    second = client.post(MESSAGES, json=envelope, headers=headers)
    assert second.status_code == 202, second.text
    assert second.json() == first.json()
    assert await message_count() == 1


@pytest.mark.asyncio
async def test_idempotency_rule_4_same_key_different_projection_conflicts_without_side_effect(world):
    """规则 4：一致但业务投影不同 → 409 idempotency_conflict，无副作用。"""
    from agent_net.persistence.context import connect

    envelope_a, headers_a = _message_pair(world, payload_variant="a")
    envelope_b, headers_b = _message_pair(world, payload_variant="b")
    envelope_b["message_id"] = envelope_a["message_id"]
    headers_b["Idempotency-Key"] = envelope_a["message_id"]
    client = world.client("coordinator")

    first = client.post(MESSAGES, json=envelope_a, headers=headers_a)
    assert first.status_code == 202, first.text

    async def total_count() -> int:
        async with connect() as db:
            async with db.execute("SELECT COUNT(*) FROM code_review_messages") as cur:
                (count,) = await cur.fetchone()
        return count

    async def stored_envelope() -> str:
        async with connect() as db:
            async with db.execute(
                "SELECT envelope_json FROM code_review_messages WHERE message_id=?",
                (envelope_a["message_id"],),
            ) as cur:
                (stored,) = await cur.fetchone()
        return stored

    before_total = await total_count()
    before_envelope = await stored_envelope()

    conflict = client.post(MESSAGES, json=envelope_b, headers=headers_b)
    assert conflict.status_code == 409, conflict.text
    assert assert_error_envelope(conflict)["code"] == "idempotency_conflict"

    assert await stored_envelope() == before_envelope, "冲突请求改写了已存储信封"
    assert await total_count() == before_total, "冲突请求新建了记录"


@pytest.mark.asyncio
async def test_artifacts_idempotency_key_is_independent_of_message_id(world):
    """上传的 Idempotency-Key 是自有键，取值不由 message_id 规定（§4）。"""
    response = world.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(world.sessions["profile"]["external_run_id"]),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": "any-opaque-value"},
    )
    assert response.status_code == 201, response.text


# ═══════════════════════════════════════════════════════════════════════
# 2026-09-22 第三轮复审 R3-1～R3-4 的回归测试
# ═══════════════════════════════════════════════════════════════════════


async def _table_counts() -> dict:
    """**业务**记录计数（消息 / 回执 / 产物）。

    不含 `code_review_artifact_idempotency`：被拒的上传可能留下一条 ``pending`` 预留，
    那是"可恢复的幂等状态"而不是业务记录（契约 §4 要求被拒请求不得留下**消息、回执或
    产物记录**）。pending 的恢复语义由 R2-1/R3-3 的用例单独断言。
    """
    from agent_net.persistence.context import connect

    counts = {}
    async with connect() as db:
        for table in ("code_review_messages", "code_review_receipts", "artifacts"):
            async with db.execute(f"SELECT COUNT(*) FROM {table}") as cur:
                (value,) = await cur.fetchone()
            counts[table] = value
    return counts


# ── R3-1：未知 / 歧义 session 不得被当成放行条件 ───────────────────────


@pytest.mark.asyncio
async def test_r31_unknown_session_is_rejected_without_side_effects(world):
    """复审 R3-1 复现：capacity 只授权 session S，却拿未授权 session 发回执 → 曾 202 并落库。"""
    from agent_net.persistence.context import connect

    envelope = _envelope(
        "receipt",
        session_id="never-authorized-session",
        sender=COORDINATOR,
        run_id="unregistered-run",
        payload=_receipt_payload("unregistered-run", kind="accepted", issuer_id=COORDINATOR),
    )
    envelope.update({"run_id": "unregistered-run", "assignment_epoch": 1})
    headers = {"X-Correlation-Id": CORRELATION, "Idempotency-Key": envelope["message_id"]}

    before = await _table_counts()
    response = world.client("coordinator").post(MESSAGES, json=envelope, headers=headers)
    assert response.status_code == 409, response.text
    assert assert_error_envelope(response)["code"] == "stale_assignment"
    assert await _table_counts() == before, "被拒的未知 session 产生了副作用"

    async with connect() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM code_review_messages WHERE message_id=?",
            (envelope["message_id"],),
        ) as cur:
            (count,) = await cur.fetchone()
    assert count == 0


@pytest.mark.asyncio
async def test_r31_session_must_match_the_run_it_claims(world):
    """真实 session 但配错 Run：payload/信封的 run 必须与该 session 的绑定一致。"""
    other = await _second_profile_session(world, run_id=_uid("RUN-other"))
    envelope = _envelope(
        "receipt",
        session_id=world.sessions["profile"]["coordination_session_id"],
        sender=COORDINATOR,
        run_id=other["external_run_id"],
        payload=_receipt_payload(other["external_run_id"], kind="accepted", issuer_id=COORDINATOR),
    )
    envelope.update({"run_id": other["external_run_id"], "assignment_epoch": 1})
    headers = {"X-Correlation-Id": CORRELATION, "Idempotency-Key": envelope["message_id"]}
    before = await _table_counts()
    response = world.client("coordinator").post(MESSAGES, json=envelope, headers=headers)
    # 该回执声明的 Run 不属于它使用的 session → 必须拒绝，且不得写入
    assert response.status_code == 409, response.text
    assert await _table_counts() == before


async def _second_profile_session(world: World, *, run_id: str) -> dict:
    from agent_net.storage import create_coordination_session, create_profile_session, register_owner

    owner = await register_owner(_uid("Owner"))
    cs_id = _uid("cs")
    await create_coordination_session(
        coordination_session_id=cs_id,
        owner_did=owner["did"],
        controller_did=owner["did"],
        objective="second",
    )
    return await create_profile_session(
        _uid("psess"),
        coordination_session_id=cs_id,
        coordinator_id=COORDINATOR,
        external_run_id=run_id,
        review_policy_sha256="a" * 64,
    )


@pytest.mark.asyncio
async def test_r31_same_identity_across_sessions_still_scoped(world):
    """同一身份在不同 session 之间仍受凭据资源范围限制（角色许可不替代资源许可）。"""
    other = await _second_profile_session(world, run_id=_uid("RUN-other2"))
    envelope = _envelope(
        "receipt",
        session_id=other["coordination_session_id"],
        sender=COORDINATOR,
        run_id=other["external_run_id"],
        payload=_receipt_payload(other["external_run_id"], kind="accepted", issuer_id=COORDINATOR),
    )
    envelope.update({"run_id": other["external_run_id"], "assignment_epoch": 1})
    headers = {"X-Correlation-Id": CORRELATION, "Idempotency-Key": envelope["message_id"]}
    before = await _table_counts()
    response = world.client("coordinator").post(MESSAGES, json=envelope, headers=headers)
    assert response.status_code == 403, response.text
    assert assert_error_envelope(response)["code"] == "authority_denied"
    assert await _table_counts() == before


# ── R3-2：租约参与校验；分配有效性在提交事务内复检 ──────────────────────


async def _set_execution(world: World, **fields) -> None:
    from agent_net.persistence.context import connect

    assignments = ", ".join(f"{key}=?" for key in fields)
    async with connect() as db:
        await db.execute(
            f"UPDATE objective_executions SET {assignments} WHERE profile_session_id=?",
            (*fields.values(), world.sessions["profile"]["profile_session_id"]),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_r32_expired_lease_is_rejected(world):
    """复审 R3-2 复现：把租约设为过去，上传仍 201。"""
    await _set_execution(world, lease_expires_at=time.time() - 60)
    before = await _table_counts()
    response = world.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(world.sessions["profile"]["external_run_id"]),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem-lease")},
    )
    assert response.status_code == 409, response.text
    assert assert_error_envelope(response)["code"] == "stale_assignment"
    assert await _table_counts() == before


@pytest.mark.asyncio
async def test_r32_cancel_after_binding_read_is_caught_in_commit_transaction(world, monkeypatch):
    """复审 R3-2 复现：读取绑定后、提交前把执行改成 cancelled，上传仍 201。

    这里在 Vault 写入阶段（提交事务之前）注入取消，确定性复现那个窗口。
    """
    from agent_net.node.routers import code_review as router_module
    from agent_net.persistence import enclave

    real_vault_put = enclave.vault_put

    async def cancelling_vault_put(*args, **kwargs):
        result = await real_vault_put(*args, **kwargs)
        await _set_execution(world, status="cancelled")
        return result

    monkeypatch.setattr(router_module, "vault_put", cancelling_vault_put)

    before = await _table_counts()
    response = world.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(world.sessions["profile"]["external_run_id"]),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem-cancel")},
    )
    assert response.status_code == 409, response.text
    assert assert_error_envelope(response)["code"] == "stale_assignment"
    assert await _table_counts() == before, "提交事务未复检分配，产物仍被登记"


@pytest.mark.asyncio
async def test_r32_epoch_change_after_binding_read_is_caught(world, monkeypatch):
    """同上，但窗口内改的是 assignment_epoch。"""
    from agent_net.node.routers import code_review as router_module
    from agent_net.persistence import enclave

    real_vault_put = enclave.vault_put

    async def epoch_bumping_vault_put(*args, **kwargs):
        result = await real_vault_put(*args, **kwargs)
        await _set_execution(world, assignment_epoch=99)
        return result

    monkeypatch.setattr(router_module, "vault_put", epoch_bumping_vault_put)
    before = await _table_counts()
    response = world.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(world.sessions["profile"]["external_run_id"]),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem-epoch")},
    )
    assert response.status_code == 409, response.text
    assert await _table_counts() == before


@pytest.mark.asyncio
async def test_r32_deadline_pass_after_binding_read_is_caught(world, monkeypatch):
    """同上，但窗口内让 deadline 过期。"""
    from agent_net.node.routers import code_review as router_module
    from agent_net.persistence import enclave

    real_vault_put = enclave.vault_put

    async def expiring_vault_put(*args, **kwargs):
        result = await real_vault_put(*args, **kwargs)
        await _set_execution(world, deadline=time.time() - 1)
        return result

    monkeypatch.setattr(router_module, "vault_put", expiring_vault_put)
    before = await _table_counts()
    response = world.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(world.sessions["profile"]["external_run_id"]),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem-deadline")},
    )
    assert response.status_code == 409, response.text
    assert assert_error_envelope(response)["code"] == "deadline_exceeded"
    assert await _table_counts() == before


# ── R3-2 补：身份元组改绑（Attempt / Coordinator）与写锁等待期间过期 ──────


@pytest.mark.asyncio
async def test_r32_attempt_rebinding_after_binding_read_is_caught(world, monkeypatch):
    """第三轮复审 P1：上传期间改绑 **Attempt**，旧请求仍 201 —— 必须被事务内复检拦下。"""
    from agent_net.node.routers import code_review as router_module
    from agent_net.persistence import enclave

    real_vault_put = enclave.vault_put

    async def rebinding_vault_put(*args, **kwargs):
        result = await real_vault_put(*args, **kwargs)
        await _set_execution(world, external_attempt_id="A-REBOUND")
        return result

    monkeypatch.setattr(router_module, "vault_put", rebinding_vault_put)
    before = await _table_counts()
    response = world.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(world.sessions["profile"]["external_run_id"]),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem-attempt")},
    )
    assert response.status_code == 409, response.text
    assert assert_error_envelope(response)["code"] == "stale_assignment"
    assert "Attempt" in response.json()["safe_message"]
    assert await _table_counts() == before, "Attempt 改绑后仍登记了产物"


@pytest.mark.asyncio
async def test_r32_coordinator_rebinding_after_binding_read_is_caught(world, monkeypatch):
    """第三轮复审 P1：上传期间改绑 **Coordinator**，旧请求仍 201 —— 必须被拦下。"""
    from agent_net.node.routers import code_review as router_module
    from agent_net.persistence import enclave

    real_vault_put = enclave.vault_put

    async def rebinding_vault_put(*args, **kwargs):
        result = await real_vault_put(*args, **kwargs)
        await _set_execution(world, external_coordinator_id="urn:code-review:coordinator:other")
        return result

    monkeypatch.setattr(router_module, "vault_put", rebinding_vault_put)
    before = await _table_counts()
    response = world.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(world.sessions["profile"]["external_run_id"]),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem-coord")},
    )
    assert response.status_code == 409, response.text
    assert assert_error_envelope(response)["code"] == "stale_assignment"
    assert "Coordinator" in response.json()["safe_message"]
    assert await _table_counts() == before, "Coordinator 改绑后仍登记了产物"


@pytest.mark.asyncio
async def test_r32_empty_coordinator_is_refused_at_entry(world):
    """第四/五轮复审场景：分配以**空** Coordinator 绑定时，入口即拒绝。

    空 Coordinator 是"不可围栏的分配"——无法证明该 Attempt 属于哪个 Coordinator，
    因此不得提交产物。修复前的复现路径是"空 ID → 上传中途改绑另一 Coordinator → 仍 201"。
    """
    await _set_execution(world, external_coordinator_id="")
    before = await _table_counts()
    response = world.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(world.sessions["profile"]["external_run_id"]),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem-unbound")},
    )
    assert response.status_code == 409, response.text
    assert assert_error_envelope(response)["code"] == "stale_assignment"
    assert "Coordinator" in response.json()["safe_message"]
    assert await _table_counts() == before


@pytest.mark.asyncio
async def test_r51_binding_entry_rejects_empty_coordinator(world):
    """第五轮复审 R5-1 的建议一：**绑定入口**必须拒绝空 Coordinator ID。

    非法/不完整的受信任绑定记录是空值缺口的源头；在上传时兜底不够，必须在写入绑定处拒绝。
    """
    from agent_net.code_review import ProfileError
    from agent_net.persistence.code_review_store import bind_execution_assignment

    profile = world.sessions["profile"]
    binding = await _current_binding(world)
    for field, kwargs in (
        ("external_coordinator_id", {"external_coordinator_id": ""}),
        ("external_coordinator_id", {"external_coordinator_id": "   "}),
        ("external_run_id", {"external_run_id": ""}),
        ("external_attempt_id", {"external_attempt_id": ""}),
    ):
        payload = {
            "profile_session_id": profile["profile_session_id"],
            "external_coordinator_id": binding["external_coordinator_id"],
            "external_run_id": profile["external_run_id"],
            "external_attempt_id": "A1",
            "assignment_epoch": 1,
        }
        payload.update(kwargs)
        with pytest.raises(ProfileError) as excinfo:
            await bind_execution_assignment(binding["execution_id"], **payload)
        assert excinfo.value.code == "input_mismatch", field
        assert field in excinfo.value.safe_message


async def _current_binding(world: World) -> dict:
    from agent_net.persistence.code_review_store import resolve_assignment_binding

    profile = world.sessions["profile"]
    state, binding = await resolve_assignment_binding(
        profile_session_id=profile["profile_session_id"],
        external_run_id=profile["external_run_id"],
        external_attempt_id="A1",
    )
    assert state == "ok" and binding is not None
    return binding


@pytest.mark.asyncio
async def test_r32_in_transaction_comparison_has_no_truthiness_guard(world):
    """第四轮复审的根因：复检里的真值守卫让**空** expected 直接跳过比较。

    直接驱动事务内校验函数，断言"expected 为空、存储非空"也会被判失败——这正是
    `if expected_coordinator_id and ...` 会漏掉的情形。HTTP 侧另由入口拒绝覆盖。
    """
    from agent_net.code_review import ProfileError
    from agent_net.persistence.code_review_store import _verify_assignment_in_transaction
    from agent_net.persistence.context import connect

    profile = world.sessions["profile"]
    binding = await _current_binding(world)

    cases = (
        # (expected_coordinator_id, expected_worker_did, 说明)
        ("", WORKER, "expected Coordinator 为空"),
        ("urn:code-review:coordinator:test", "", "expected worker 为空"),
    )
    for expected_coordinator, expected_worker, label in cases:
        async with connect() as db:
            with pytest.raises(ProfileError) as excinfo:
                await _verify_assignment_in_transaction(
                    db,
                    execution_id=binding["execution_id"],
                    profile_session_id=profile["profile_session_id"],
                    external_run_id=profile["external_run_id"],
                    expected_attempt_id="A1",
                    expected_coordinator_id=expected_coordinator,
                    expected_epoch=1,
                    expected_worker_did=expected_worker,
                )
            await db.rollback()
        assert excinfo.value.code in ("stale_assignment", "authority_denied"), label


@pytest.mark.asyncio
async def test_r32_in_transaction_comparison_accepts_matching_identity(world):
    """对照面：身份完全一致时事务内复检必须通过（避免把校验写成恒真拒绝）。"""
    from agent_net.persistence.code_review_store import _verify_assignment_in_transaction
    from agent_net.persistence.context import connect

    profile = world.sessions["profile"]
    binding = await _current_binding(world)
    async with connect() as db:
        await _verify_assignment_in_transaction(
            db,
            execution_id=binding["execution_id"],
            profile_session_id=profile["profile_session_id"],
            external_run_id=profile["external_run_id"],
            expected_attempt_id="A1",
            expected_coordinator_id=binding["external_coordinator_id"],
            expected_epoch=1,
            expected_worker_did=WORKER,
        )
        await db.rollback()


@pytest.mark.asyncio
async def test_r32_lease_expiring_while_waiting_for_write_lock_is_caught(world, monkeypatch):
    """第三轮复审 P2：事务在**写锁上等待**期间租约过期，旧时间会放行 —— 必须用取锁后的时间。

    构造方式（确定性）：注入的 ``vault_put`` 在真实写入后，用**另一条连接**持有
    ``BEGIN IMMEDIATE`` 写锁，并由后台任务在租约过期之后才释放；于是提交事务的
    ``BEGIN IMMEDIATE`` 会在锁上一直等到租约过期之后。
    """
    import asyncio

    import aiosqlite

    from agent_net.node.routers import code_review as router_module
    from agent_net.persistence import enclave
    from agent_net.persistence.context import get_db_path

    # 租约很快过期；入口的快速检查此刻仍然通过（这正是被测的时间窗口）
    await _set_execution(world, lease_expires_at=time.time() + 0.3)

    real_vault_put = enclave.vault_put
    blocker_ready = asyncio.Event()

    async def lock_holding_vault_put(*args, **kwargs):
        result = await real_vault_put(*args, **kwargs)
        blocker = await aiosqlite.connect(get_db_path())
        await blocker.execute("BEGIN IMMEDIATE")  # 持有写锁，提交事务在此等待
        blocker_ready.set()

        async def release_after_expiry():
            try:
                await asyncio.sleep(0.9)  # 让租约在这段等待中过期
                await blocker.commit()
            finally:
                await blocker.close()

        asyncio.create_task(release_after_expiry())
        return result

    monkeypatch.setattr(router_module, "vault_put", lock_holding_vault_put)

    before = await _table_counts()
    response = world.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(world.sessions["profile"]["external_run_id"]),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem-lockwait")},
    )
    assert blocker_ready.is_set(), "未进入写锁等待阶段，测试前提不成立"
    assert response.status_code == 409, response.text
    assert assert_error_envelope(response)["code"] == "stale_assignment"
    assert "租约" in response.json()["safe_message"]
    assert await _table_counts() == before, "等待写锁期间过期的租约仍放行了产物"


# ── R3-3：同 key 并发上传 ─────────────────────────────────────────────


async def _concurrent_upload(world, requests: List[tuple], *, barrier: int):
    """用进程内 ASGI 请求并发发起上传；`barrier` 个请求都到达 Vault 阶段后再一起放行。"""
    import asyncio

    import httpx

    from agent_net.node.daemon import app
    from agent_net.node.routers import code_review as router_module
    from agent_net.persistence import enclave

    real_vault_put = enclave.vault_put
    gate = asyncio.Event()
    arrived = {"n": 0}

    async def gated_vault_put(*args, **kwargs):
        arrived["n"] += 1
        if arrived["n"] >= barrier:
            gate.set()
        await asyncio.wait_for(gate.wait(), timeout=10)
        return await real_vault_put(*args, **kwargs)

    router_module.vault_put = gated_vault_put
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://contract") as client:
            async def one(payload, headers, who):
                return await client.post(
                    ARTIFACTS,
                    json=payload,
                    headers={**world.headers[who], **headers},
                )

            return await asyncio.gather(*[one(p, h, w) for p, h, w in requests])
    finally:
        router_module.vault_put = real_vault_put


@pytest.mark.asyncio
async def test_r33_concurrent_same_key_same_projection(world):
    """复审 R3-3 复现：两个同 key 请求并发 → 曾 [201, 500]（主键冲突）。"""
    request = _artifact_request(world.sessions["profile"]["external_run_id"])
    key = _uid("idem-concurrent")
    responses = await _concurrent_upload(
        world,
        [(request, {"X-Correlation-Id": CORRELATION, "Idempotency-Key": key}, "worker")] * 2,
        barrier=2,
    )
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201, 201], [(r.status_code, r.text[:200]) for r in responses]
    ids = {r.json()["artifact_id"] for r in responses}
    assert len(ids) == 1, "并发同 key 应复用同一 artifact"
    # 只登记一份产物
    from agent_net.persistence.context import connect

    async with connect() as db:
        async with db.execute("SELECT COUNT(*) FROM artifacts") as cur:
            (count,) = await cur.fetchone()
    assert count == 2  # world 预置 1 份 + 本次 1 份


@pytest.mark.asyncio
async def test_r33_concurrent_same_key_different_projection(world):
    """同 key 不同业务投影并发：一个成功，另一个 409（不得 500）。"""
    run_id = world.sessions["profile"]["external_run_id"]
    key = _uid("idem-concurrent-diff")
    other = _artifact_request(run_id)
    other["retention_until"] = "2026-11-30T00:00:00Z"  # 业务投影不同（仍在承诺期内）
    responses = await _concurrent_upload(
        world,
        [
            (_artifact_request(run_id), {"X-Correlation-Id": CORRELATION, "Idempotency-Key": key}, "worker"),
            (other, {"X-Correlation-Id": CORRELATION, "Idempotency-Key": key}, "worker"),
        ],
        barrier=1,
    )
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201, 409], [(r.status_code, r.text[:200]) for r in responses]
    assert next(r for r in responses if r.status_code == 409).json()["code"] == "delivery_conflict"


# ── R3-4：幂等比较用业务投影，不是原始字节 / 完整信封 ──────────────────


@pytest.mark.asyncio
async def test_r34_upload_dto_reformatting_is_a_replay(world):
    """复审 R3-4 复现：相同 DTO 仅改变排版（键序/空白）曾返回 409。"""
    request = _artifact_request(world.sessions["profile"]["external_run_id"])
    key = _uid("idem-reformat")
    headers = {"X-Correlation-Id": CORRELATION, "Idempotency-Key": key}
    client = world.client("worker")

    first = client.post(ARTIFACTS, json=request, headers=headers)
    assert first.status_code == 201, first.text

    # 同样的业务字段，但键序相反、带大量空白
    reordered = dict(reversed(list(request.items())))
    body = json.dumps(reordered, ensure_ascii=False, indent=4, sort_keys=False).encode("utf-8")
    second = client.post(
        ARTIFACTS, content=body, headers={**headers, "Content-Type": "application/json"}
    )
    assert second.status_code == 201, second.text
    assert second.json()["artifact_id"] == first.json()["artifact_id"]


@pytest.mark.asyncio
async def test_r34_message_tracking_field_change_is_a_replay(world):
    """复审 R3-4 复现：同 message_id、仅改 created_at 曾返回 409。"""
    profile = world.sessions["profile"]
    envelope = _envelope(
        "assignment",
        session_id=profile["coordination_session_id"],
        sender=COORDINATOR,
        run_id=profile["external_run_id"],
        payload=_assignment_payload(profile["external_run_id"]),
    )
    headers = {"X-Correlation-Id": CORRELATION, "Idempotency-Key": envelope["message_id"]}
    client = world.client("coordinator")

    first = client.post(MESSAGES, json=envelope, headers=headers)
    assert first.status_code == 202, first.text

    # 只改追踪字段（created_at / causation_id / correlation_id——correlation_id 头必须同步）
    replay = dict(
        envelope,
        created_at="2027-01-01T00:00:00Z",
        causation_id=_uid("cause"),
        correlation_id="corr-contract-2",
    )
    second = client.post(
        MESSAGES, json=replay, headers={**headers, "X-Correlation-Id": "corr-contract-2"}
    )
    assert second.status_code == 202, second.text
    assert second.json() == first.json()


@pytest.mark.asyncio
async def test_r34_message_business_change_is_a_conflict(world):
    """payload 变化 → 409；且不覆盖已存信封、不新增记录。"""
    from agent_net.persistence.context import connect

    profile = world.sessions["profile"]
    envelope = _envelope(
        "assignment",
        session_id=profile["coordination_session_id"],
        sender=COORDINATOR,
        run_id=profile["external_run_id"],
        payload=_assignment_payload(profile["external_run_id"]),
    )
    headers = {"X-Correlation-Id": CORRELATION, "Idempotency-Key": envelope["message_id"]}
    client = world.client("coordinator")
    assert client.post(MESSAGES, json=envelope, headers=headers).status_code == 202

    changed = _assignment_payload(profile["external_run_id"])
    changed["policy_ref"] = "policy:changed"
    conflict = dict(envelope, payload=changed)
    before = await _table_counts()
    response = client.post(MESSAGES, json=conflict, headers=headers)
    assert response.status_code == 409, response.text
    assert assert_error_envelope(response)["code"] == "idempotency_conflict"
    assert await _table_counts() == before

    # 已存信封未被改写
    async with connect() as db:
        async with db.execute(
            "SELECT envelope_json FROM code_review_messages WHERE message_id=?",
            (envelope["message_id"],),
        ) as cur:
            (stored,) = await cur.fetchone()
    assert json.loads(stored)["payload"]["policy_ref"] == "policy:code-review:1"


@pytest.mark.asyncio
async def test_r34_receipt_replay_keeps_original_receipt_and_timestamps(world):
    """同键重放必须返回**原**回执，不重新生成业务时间。"""
    from agent_net.persistence.context import connect

    profile = world.sessions["profile"]
    payload = _receipt_payload(profile["external_run_id"], kind="accepted", issuer_id=COORDINATOR)
    envelope = _envelope(
        "receipt",
        session_id=profile["coordination_session_id"],
        sender=COORDINATOR,
        run_id=profile["external_run_id"],
        payload=payload,
    )
    envelope.update({"run_id": profile["external_run_id"], "assignment_epoch": 1})
    headers = {"X-Correlation-Id": CORRELATION, "Idempotency-Key": envelope["message_id"]}
    client = world.client("coordinator")

    assert client.post(MESSAGES, json=envelope, headers=headers).status_code == 202
    async with connect() as db:
        async with db.execute(
            "SELECT created_at, receipts_json FROM code_review_messages WHERE message_id=?",
            (envelope["message_id"],),
        ) as cur:
            first_created, first_receipts = await cur.fetchone()

    replay = dict(envelope, created_at="2027-02-02T00:00:00Z")
    assert client.post(MESSAGES, json=replay, headers=headers).status_code == 202

    async with connect() as db:
        async with db.execute(
            "SELECT created_at, receipts_json FROM code_review_messages WHERE message_id=?",
            (envelope["message_id"],),
        ) as cur:
            second_created, second_receipts = await cur.fetchone()
    assert second_created == first_created, "重放重建了业务时间"
    assert second_receipts == first_receipts, "重放重新生成了回执"


# ── 保留建议：retention 原文必须落库 + epoch 严格整数 ──────────────────


@pytest.mark.asyncio
async def test_retention_text_is_persisted_in_database(world):
    """保留建议：`retention_until_text` 不能只靠内存赋值回显，必须写库。"""
    from agent_net.persistence.context import connect

    requested = "2026-12-31T00:00:00.123456Z"
    response = world.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(world.sessions["profile"]["external_run_id"], retention_until=requested),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem-text")},
    )
    assert response.status_code == 201, response.text
    artifact_id = response.json()["artifact_id"]

    async with connect() as db:
        async with db.execute(
            "SELECT retention_until_text FROM artifacts WHERE artifact_id=?", (artifact_id,)
        ) as cur:
            (stored,) = await cur.fetchone()
    assert stored == requested, "原始保留期文本没有落库"

    # 重放同样返回原文（不再依赖内存）
    replay = world.client("worker").post(
        ARTIFACTS,
        json=_artifact_request(world.sessions["profile"]["external_run_id"], retention_until=requested),
        headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem-text2")},
    )
    assert replay.status_code == 201
    assert replay.json()["retention_until"] == requested


@pytest.mark.asyncio
async def test_assignment_epoch_must_be_strict_positive_integer(world):
    """保留建议：epoch 不得用 int() 悄悄接受 bool / 小数 / 字符串。"""
    run_id = world.sessions["profile"]["external_run_id"]
    client = world.client("worker")
    for value in (True, 1.0, "1"):
        request = _artifact_request(run_id)
        request["assignment_epoch"] = value
        response = client.post(
            ARTIFACTS,
            json=request,
            headers={"X-Correlation-Id": CORRELATION, "Idempotency-Key": _uid("idem-epoch")},
        )
        assert response.status_code == 422, f"{value!r}: {response.text}"
        assert assert_error_envelope(response)["code"] == "invalid_output"
