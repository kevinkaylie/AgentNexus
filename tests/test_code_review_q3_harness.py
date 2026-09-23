"""q3 行为用例的可执行 harness。

执行对象：`specs/profiles/code-review/v1/fixtures/binding/q3-outcome-coverage.md`
的四组用例（q3-found-partial / -replay / -reject / q3-empty-partial），
实现方为 `agent_net/code_review/`（厂商无关管线在 `provider_adapter.py`，
HCZJ 词表在 `hczj_adapter.py`，呈现规则在 `presentation.py`）。

覆盖范围与**明确不覆盖**：

- ✅ HCZJ 报告+覆盖 → Profile 报告的转换语义（outcome/coverage 推导、原义保留、溯源）
- ✅ 呈现规则（同一摘要同时呈现 outcome+coverage、缺口警示、禁止表述）与发布前拒绝（422）
- ✅ 交付重放幂等（不新建报告/回执）
- ❌ “同 operation_id 发布重放不得新增 GitLab 评论”**不在本仓库验证**：Publisher 位于
  HCZJ 应用边界（RC2 §5），本仓库没有 GitLab 写入路径，该半场以 skip 显式标记，
  最终执行记录中会体现为 skipped，而不是被悄悄省略。
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

from agent_net.code_review import (
    ProfileError,
    build_hczj_profile_report,
    render_review_summary,
    validate_publish_body,
    validate_review_report,
)

PACKAGE = Path(__file__).resolve().parents[1] / "specs" / "profiles" / "code-review" / "v1"
FROZEN_VALID_09 = "09_review_report_issues_found_with_inherited_gap.artifact_body.json"
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


# ── q3 用例的前置数据（Given） ────────────────────────────────────────


def _evidence(path: str = "src/main/java/com/example/OrderService.java") -> dict:
    return {
        "provider_id": "did:agentnexus:z6MkNexusScanner00000000000000000000000000000",
        "report_id": "R1",
        "side": "after",
        "snapshot_id": "snap_after_g3",
        "project": "proj_7788",
        "commit_sha": "2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c",
        "path": path,
        "blob_sha": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
        "start_line": 120,
        "end_line": 128,
        "content_sha256": "5e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f",
    }


def _hczj_finding() -> dict:
    return {
        "finding_id": "F7",
        "severity": "P2",
        "title": "库存校验失败路径未释放预留额度",
        "trigger": "库存校验返回 false 后未回滚预留记录",
        "impact": "失败订单长期占用库存额度",
        "location": {
            "side": "after",
            "commit_sha": "2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c",
            "path": "src/main/java/com/example/OrderService.java",
            "start_line": 120,
            "end_line": 128,
        },
        "evidence_refs": [_evidence()],
        "suggested_validation": "补充库存校验失败后的预留回滚断言",
    }


def _hczj_report(outcome: str = "findings_present", findings: list | None = None) -> dict:
    return {
        "schema_version": "hczj.review_report.v1",
        "report_id": "R1",
        "outcome": outcome,
        "findings": [_hczj_finding()] if findings is None else findings,
        "limitations": [],
    }


def _hczj_coverage(status: str = "partial") -> dict:
    return {
        "schema_version": "hczj.review_coverage.v1",
        "status": status,
        "planned_files": [
            "src/main/java/com/example/OrderService.java",
            "src/main/java/com/example/OrderRepository.java",
        ],
        "reviewed_files": ["src/main/java/com/example/OrderService.java"],
        "omitted_files": [
            {
                "path": "src/main/java/com/example/OrderRepository.java",
                "reason": "inherited_gap_impact_graph_truncated",
            }
        ],
        "gap_reasons": ["继承输入证据缺口：依赖图谱在 200 节点处截断"],
        "inherited_gaps": [
            {"source": "art_impact_R1", "reason": "依赖图谱在 200 节点处截断（truncated=true）"}
        ],
    }


def _identity() -> dict:
    return {
        "run_id": "RUN-ID-2026-09-14",
        "attempt_id": "A3",
        "input_manifest_digest": MANIFEST_DIGEST,
        "impact_artifact": {
            "artifact_id": "art_impact_R1",
            "producer_id": "did:agentnexus:z6MkNexusScanner00000000000000000000000000000",
            "media_type": "application/json",
            "schema_version": "nexus.review_impact.v1",
            "digest_algorithm": "sha256-bytes-v1",
            "digest": "sha256:" + "0" * 64,
            "byte_length": 18456,
            "locator": "nexus-report:did:agentnexus:z6MkNexusScanner00000000000000000000000000000:R1",
            "access_scope": "service_private",
            "retention_until": "2027-03-18T00:00:00Z",
            "replaces": None,
        },
        "review_policy_sha256": "a" * 64,
        "review_revision": 1,
        "base_sha": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
        "head_sha": "2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c",
        "target_sha": "3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d",
        "generation": 3,
        "execution_revision": 1,
        "reviewer_id": "did:agentnexus:z6MkReviewerWorker00000000000000000000000000000",
    }


def _execution_metadata() -> dict:
    return {
        "provider": "hczj-model-gateway",
        "model": "code-review-model",
        "model_version": None,
        "skill_version": "code-review-skill/0.1.0",
        "tool_versions": ["nexus-mcp/1.0"],
        "started_at": "2026-09-20T02:00:00Z",
        "completed_at": "2026-09-20T02:09:00Z",
    }


def _usage() -> dict:
    return {
        "measurement": "partial",
        "input_tokens": 96000,
        "output_tokens": 11000,
        "cost": None,
        "note": "成本未计量；不得视为零成本",
    }


def _convert(report: dict, coverage: dict, **overrides) -> dict:
    kwargs = dict(
        hczj_report=report,
        hczj_coverage=coverage,
        identity=_identity(),
        execution_metadata=_execution_metadata(),
        usage=_usage(),
    )
    kwargs.update(overrides)
    return build_hczj_profile_report(**kwargs)


# ── q3-found-partial：正常转换 ────────────────────────────────────────


@pytest.mark.parametrize("source_outcome", ["findings_present", "inconclusive"])
def test_cr_q3_found_partial_conversion(source_outcome):
    """两种 HCZJ 原 outcome 都必须得到相同的 Profile 语义，且各自保留溯源。"""
    report = _hczj_report(outcome=source_outcome)
    coverage = _hczj_coverage()
    before = copy.deepcopy((report, coverage))

    target = _convert(report, coverage)

    # 原始产物字节/内容不变
    assert (report, coverage) == before
    # 目标语义：findings 保留、severity 映射、outcome=issues_found、coverage=partial
    assert target["outcome"] == "issues_found"
    assert target["coverage"]["status"] == "partial"
    assert [f["finding_id"] for f in target["findings"]] == ["F7"]
    assert target["findings"][0]["severity"] == "medium"  # P2 → medium
    # 缺口信息原义保留
    assert target["coverage"]["omitted_files"][0]["path"].endswith("OrderRepository.java")
    assert target["coverage"]["gap_reasons"] == coverage["gap_reasons"]
    assert target["coverage"]["inherited_gaps"] == coverage["inherited_gaps"]
    # 身份/来源未被换成实时版本
    assert target["input_manifest_digest"] == MANIFEST_DIGEST
    assert target["impact_artifact"]["artifact_id"] == "art_impact_R1"
    assert target["extensions"]["hczj.provenance"]["source_outcome"] == source_outcome
    # 目标完整报告必须通过结构校验
    assert validate_review_report(target) == []


def test_cr_q3_found_partial_matches_frozen_fixture_invariants():
    """与冻结 fixture valid/09 的关键不变式一致（不要求逐字节相同）。"""
    frozen = json.loads(
        (PACKAGE / "fixtures" / "valid" / FROZEN_VALID_09).read_text(encoding="utf-8")
    )
    target = _convert(_hczj_report(), _hczj_coverage())
    for key in ("outcome", "schema_version"):
        assert target[key] == frozen[key]
    assert target["coverage"]["status"] == frozen["coverage"]["status"]
    assert target["findings"][0]["severity"] == frozen["findings"][0]["severity"]


def test_cr_q3_found_partial_presentation_requires_both_dimensions():
    """UI 与 Publisher 摘要必须同时呈现 outcome 与 coverage，并带缺口警示。"""
    target = _convert(_hczj_report(), _hczj_coverage())
    body = render_review_summary(target)

    assert "发现问题" in body and "覆盖：部分" in body
    assert "缺口警示" in body
    assert "OrderRepository.java" in body  # 遗漏范围
    assert "art_impact_R1" in body  # 继承缺口
    assert "F7" not in body  # 摘要不暴露内部 finding_id，但必须呈现内容
    assert "库存校验失败路径未释放预留额度" in body
    assert "触发" in body and "影响" in body and "证据" in body
    # 同一摘要通过发布前校验
    validate_publish_body(body, target)


# ── q3-found-partial-replay：重复交付 ─────────────────────────────────


async def _profile_bound_execution():
    from agent_net.storage import (
        bind_execution_assignment,
        create_coordination_session,
        create_objective_execution,
        create_profile_session,
        register_owner,
    )

    owner = await register_owner("Q3Owner")
    cs_id = _uid("cs")
    await create_coordination_session(
        coordination_session_id=cs_id,
        owner_did=owner["did"],
        controller_did=owner["did"],
        objective="q3 replay",
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
    )
    await bind_execution_assignment(
        execution_id,
        profile_session_id=profile["profile_session_id"],
        external_coordinator_id=profile["coordinator_id"],
        external_run_id=profile["external_run_id"],
        external_attempt_id="A3",
        assignment_epoch=1,
        input_manifest_digest=MANIFEST_DIGEST,
        output_schema="code_review.report.v1",
    )
    return {"profile": profile, "execution_id": execution_id, "owner": owner}


@pytest.mark.asyncio
async def test_cr_q3_found_partial_replay_does_not_duplicate():
    """重复交付返回原结果，不新建报告/回执、不改 findings/coverage。"""
    from agent_net.storage import (
        commit_profile_delivery,
        list_deliveries,
        list_profile_receipts,
    )

    ctx = await _profile_bound_execution()
    target = _convert(_hczj_report(), _hczj_coverage())
    body = json.dumps(target, ensure_ascii=False)
    kwargs = dict(
        actor_did="did:agentnexus:worker",
        artifact_type="CodeReviewReport",
        artifact_body=body,
        media_type="application/json",
        schema_version="code_review.report.v1",
        summary="q3 replay",
        run_state="completed",
        outcome=target["outcome"],
        domain_status="completed",
        enforcement="declared_only",
        report_input_manifest_digest=MANIFEST_DIGEST,
    )

    first = await commit_profile_delivery(ctx["execution_id"], **kwargs)
    deliveries_before = len(await list_deliveries(ctx["profile"]["profile_session_id"]))
    receipts_before = len(await list_profile_receipts(ctx["profile"]["profile_session_id"]))

    replay = await commit_profile_delivery(ctx["execution_id"], **kwargs)

    assert replay["replayed"] is True
    assert replay["artifact_id"] == first["artifact_id"]
    assert len(await list_deliveries(ctx["profile"]["profile_session_id"])) == deliveries_before
    assert len(await list_profile_receipts(ctx["profile"]["profile_session_id"])) == receipts_before
    # 重复渲染仍保留缺口警示
    assert "缺口警示" in render_review_summary(target)


def test_cr_q3_publication_replay_not_verifiable_here():
    """发布重放半场属 HCZJ 边界（RC2 §5），本仓库无 GitLab 写入路径。"""
    pytest.skip("Publisher/GitLab 写入属 HCZJ 应用边界；本仓库无法验证发布重放")


# ── q3-found-partial-reject：错误转换与呈现 ───────────────────────────


def test_cr_q3_reject_a_findings_with_inconclusive():
    """A：非空 findings 却 outcome=inconclusive → 结构校验拒绝，不产生回执。"""
    from agent_net.code_review import translate_agentnexus_result

    target = _convert(_hczj_report(), _hczj_coverage())
    target["outcome"] = "inconclusive"

    from agent_net.code_review import validate_review_report as _validate

    assert _validate(target)  # 结构不合法
    with pytest.raises(ProfileError) as excinfo:
        translate_agentnexus_result(
            "completed", artifact_type="CodeReviewReport", report=target
        )
    assert excinfo.value.code == "invalid_output"


def test_cr_q3_reject_b_inherited_gap_with_complete_coverage():
    """B：inherited_gaps 非空却 coverage=complete → 结构校验拒绝（§15.8）。

    转换本身**不可能**产出这种报告（见 never_upgrades_complete），因此这里校验的是
    "若上游/适配器给出这种报告，必须在结构校验阶段被拒"，并确认经翻译层同样拒绝。
    """
    from agent_net.code_review import translate_agentnexus_result

    target = _convert(_hczj_report(), _hczj_coverage())
    target["coverage"]["status"] = "complete"

    issues = validate_review_report(target)
    assert any(i.rule.startswith("§15.8") for i in issues), [str(i) for i in issues]

    with pytest.raises(ProfileError) as excinfo:
        translate_agentnexus_result("completed", artifact_type="CodeReviewReport", report=target)
    assert excinfo.value.code == "invalid_output"


def test_cr_q3_reject_c_and_d_presentation():
    """C：只呈现 outcome；D：遗漏范围为空 → 发布前拒绝（422），即使 schema 已通过。"""
    target = _convert(_hczj_report(), _hczj_coverage())
    assert validate_review_report(target) == []  # 结构合法

    # C：模板只呈现 outcome（不含 coverage 与缺口信息）
    only_outcome = "发现问题"
    with pytest.raises(ProfileError) as excinfo:
        validate_publish_body(only_outcome, target)
    assert excinfo.value.code == "invalid_output"
    assert excinfo.value.http_status == 422
    assert "coverage.status" in excinfo.value.safe_message

    # D：呈现缺了遗漏范围
    full = render_review_summary(target)
    missing_scope = full.replace("src/main/java/com/example/OrderRepository.java", "")
    with pytest.raises(ProfileError) as excinfo:
        validate_publish_body(missing_scope, target)
    assert "遗漏范围未呈现" in excinfo.value.safe_message


# ── q3-empty-partial：无发现不等于无问题 ─────────────────────────────


def test_cr_q3_empty_partial_conversion_and_presentation():
    report = _hczj_report(outcome="no_findings", findings=[])
    coverage = _hczj_coverage(status="partial")

    target = _convert(report, coverage)

    assert target["findings"] == []
    assert target["outcome"] == "inconclusive"  # 不得因无 findings 而“通过”
    assert target["coverage"]["status"] == "partial"

    body = render_review_summary(target)
    assert "结论不充分" in body and "覆盖：部分" in body
    assert "缺口警示" in body
    assert "无问题" not in body
    validate_publish_body(body, target)

    # 禁止“无问题”表述
    with pytest.raises(ProfileError) as excinfo:
        validate_publish_body("结论不充分；覆盖：部分\n问题：无问题", target)
    assert "禁止表述" in excinfo.value.safe_message


def test_cr_q3_empty_partial_cannot_reuse_issues_fixture():
    """该用例不能套用 valid/09（非空 findings）——用它反而应产生 issues_found。"""
    frozen = json.loads(
        (PACKAGE / "fixtures" / "valid" / FROZEN_VALID_09).read_text(encoding="utf-8")
    )
    assert frozen["findings"], "valid/09 必须是非空 findings 的用例"
    assert frozen["outcome"] == "issues_found"


# ── 拒绝：未登记的 HCZJ severity / outcome ────────────────────────────


def test_cr_q3_rejects_unknown_severity_and_outcome():
    bad_severity = _hczj_report()
    bad_severity["findings"][0]["severity"] = "P9"
    with pytest.raises(ProfileError) as excinfo:
        _convert(bad_severity, _hczj_coverage())
    assert excinfo.value.code == "invalid_output"

    bad_outcome = _hczj_report(outcome="approved")
    with pytest.raises(ProfileError) as excinfo:
        _convert(bad_outcome, _hczj_coverage())
    assert excinfo.value.code == "invalid_output"


def test_cr_q3_never_upgrades_coverage_to_complete():
    """即使 HCZJ 声称 complete，只要有遗漏/缺口就不得提升为 complete。"""
    coverage = _hczj_coverage(status="complete")  # 声明 complete 但仍有 omitted/gaps
    target = _convert(_hczj_report(), coverage)
    assert target["coverage"]["status"] == "partial"
    assert target["extensions"]["hczj.provenance"]["source_coverage_status"] == "complete"
