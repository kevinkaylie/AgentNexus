"""Code Review Collaboration Profile v1 —— 纯逻辑层测试（§15.2/§15.3/§15.6 辅助）。

这些测试把实现**绑定到冻结规范包**：直接读取
``specs/profiles/code-review/v1/fixtures`` 的正例、反例与摘要向量，
因此实现与规范一旦漂移就会在这里失败（而不是等到集成）。

纯逻辑，无 DB、无 HTTP，故不需要 asyncio fixture。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_net.code_review import (
    DEFAULT_PRIORITY_SEVERITY_MAP,
    DigestError,
    ProfileError,
    artifact_body_bytes,
    error_envelope,
    line_range_bytes,
    line_range_sha256,
    parse_envelope,
    priority_to_severity,
    report_digest,
    translate_agentnexus_result,
    validate_review_report,
)
from agent_net.code_review.errors import read_limit_error

PACKAGE = Path(__file__).resolve().parents[1] / "specs" / "profiles" / "code-review" / "v1"
FIXTURES = PACKAGE / "fixtures"


def _fixture(relative: str) -> str:
    return (FIXTURES / relative).read_text(encoding="utf-8")


def _fixture_json(relative: str) -> dict:
    return json.loads(_fixture(relative))


# ── §15.3 字节口径与摘要 ─────────────────────────────────────────────


def test_cr_digest_matches_frozen_cp23_vector():
    """实现必须复现规范包 CP-23 的权威摘要（禁止重序列化口径）。"""
    body = _fixture("valid/05_review_report_partial_inconclusive.artifact_body.json")
    digest, length = report_digest(body)
    assert digest == "sha256:6395a6edac10db12b303cccaa6cbedcb4a99e0f3721195de0312cf0d15766316"
    assert length == 2704


def test_cr_digest_vectors_transform_expectations():
    """CP-23-c/d/e：内层字节变化与"重序列化"都必须改变摘要。"""
    body = _fixture("valid/05_review_report_partial_inconclusive.artifact_body.json")
    vectors = _fixture_json("digest_vectors.json")
    index = {v["id"]: v for v in vectors["vectors"]}

    # 追加换行 → 新摘要
    assert report_digest(body + "\n")[0] == index["CP-23-c"]["expected"]["digest"]
    # 解析后重序列化 → 不得与原摘要相同（这正是旧 result_hash 的错误口径）
    reserialized = json.dumps(json.loads(body), ensure_ascii=False, separators=(",", ":"))
    assert report_digest(reserialized)[0] == index["CP-23-d"]["expected"]["digest"]
    assert report_digest(reserialized)[0] != report_digest(body)[0]


def test_cr_digest_outer_escaping_does_not_matter():
    """§15.3：外层 JSON 转义不参与摘要——同一字符串在两种外层承载下摘要相同。"""
    body = _fixture("valid/05_review_report_partial_inconclusive.artifact_body.json")
    outer_a = json.dumps({"artifact_body": body}, ensure_ascii=False)
    outer_b = json.dumps({"artifact_body": body}, ensure_ascii=True, indent=2)
    decoded_a = json.loads(outer_a)["artifact_body"]
    decoded_b = json.loads(outer_b)["artifact_body"]
    assert report_digest(decoded_a) == report_digest(decoded_b)


@pytest.mark.parametrize(
    "bad",
    ["\ufeff{\"a\":1}", "text\ud800tail"],
)
def test_cr_digest_rejects_bom_and_lone_surrogate(bad):
    with pytest.raises(DigestError):
        artifact_body_bytes(bad)


def test_cr_digest_rejects_non_string():
    with pytest.raises(DigestError):
        artifact_body_bytes({"not": "a string"})


def test_cr_line_range_keeps_crlf_and_final_lf():
    """§15.3：LF 定界、保留 CR、保留末行是否有 LF，不做归一。"""
    text = "a\r\nb\nc"
    assert line_range_bytes(text, 1, 1) == b"a\r\n"
    assert line_range_bytes(text, 2, 2) == b"b\n"
    assert line_range_bytes(text, 3, 3) == b"c"
    assert line_range_bytes(text, 1, 3) == text.encode("utf-8")

    with_lf = "x\n"
    assert line_range_bytes(with_lf, 1, 1) == b"x\n"
    assert line_range_sha256(with_lf, 1, 1) == line_range_sha256("x\n", 1, 1)


def test_cr_line_range_rejects_out_of_range_and_empty():
    with pytest.raises(DigestError):
        line_range_bytes("", 1, 1)
    with pytest.raises(DigestError):
        line_range_bytes("only one line", 1, 2)
    with pytest.raises(DigestError):
        line_range_bytes("a\nb", 3, 2)


# ── code_review.error.v1 ──────────────────────────────────────────────


def test_cr_error_envelope_has_frozen_fields():
    err = ProfileError("stale_assignment", "旧分配无提交权", scope="delivery", correlation_id="corr_1")
    payload = error_envelope(err)
    assert payload["schema"] == "code_review.error.v1"
    assert payload["code"] == "stale_assignment"
    assert payload["retryable"] is False
    assert payload["action_required"] is False
    assert payload["retry_after_seconds"] is None
    assert payload["correlation_id"] == "corr_1"
    assert set(payload) >= {
        "schema",
        "code",
        "retryable",
        "action_required",
        "scope",
        "correlation_id",
        "safe_message",
        "retry_after_seconds",
    }


def test_cr_error_rejects_retry_after_when_not_retryable():
    with pytest.raises(ValueError):
        ProfileError(
            "invalid_output",
            "x",
            scope="validation",
            retryable=False,
            retry_after_seconds=30,
        )


def test_cr_error_rate_limited_requires_retry_after():
    with pytest.raises(ValueError):
        ProfileError("rate_limited", "限流", scope="transport")
    err = ProfileError("rate_limited", "限流", scope="transport", retry_after_seconds=5)
    assert error_envelope(err)["retry_after_seconds"] == 5


def test_cr_coordinator_unavailable_variants():
    unconfigured = ProfileError("coordinator_unavailable", "未配置", scope="deployment")
    assert (unconfigured.retryable, unconfigured.action_required) == (False, True)
    unreachable = ProfileError(
        "coordinator_unavailable", "暂时不可达", scope="deployment", variant="unreachable"
    )
    assert (unreachable.retryable, unreachable.action_required) == (True, False)


def test_cr_read_limit_is_413_data_policy_denied_with_scope():
    """RC2 §10.1 + 评审 R2-2：超限用 413 data_policy_denied，并用 scope 区分原因。

    HTTP 契约矩阵要求错误响应**真正通过**冻结 ``error.schema.json``（
    ``additionalProperties: false``），因此上限细节必须在 ``extensions`` 里，
    不能放在顶层。
    """
    err = read_limit_error("source_bytes_max_bytes", observed=2_000_000, correlation_id="c9")
    payload = error_envelope(err)
    assert err.http_status == 413
    assert payload["code"] == "data_policy_denied"
    assert payload["scope"] == "read_limit"
    assert payload["retryable"] is False and payload["action_required"] is True
    detail = payload["extensions"]["read_limit"]
    assert detail["observed"] == 2_000_000 and detail["limit_value"] == 1 * 1024 * 1024
    assert "observed" not in payload and "limit_value" not in payload


def test_cr_data_policy_denied_scopes_are_distinguishable():
    """R2-2：同一 code 的不同成因必须能用 scope + HTTP 状态区分（不得只看 code）。

    契约 §7 固定三类：``read_limit``（413 超限）、``retention``（422 保留期）、
    ``policy``（403 披露/权限策略，当前实现保留为声明位）。
    """
    read_limit = read_limit_error("raw_report_max_bytes", observed=99)
    retention = ProfileError(
        "data_policy_denied", "无法承诺所请求的保留期", scope="retention", http_status=422
    )
    policy = ProfileError(
        "data_policy_denied", "未批准的 provider", scope="policy", http_status=403
    )

    assert {(e.scope, e.http_status) for e in (read_limit, retention, policy)} == {
        ("read_limit", 413),
        ("retention", 422),
        ("policy", 403),
    }
    # 三条共用同一 code，因此**必须**靠 scope 区分
    assert {e.code for e in (read_limit, retention, policy)} == {"data_policy_denied"}


# ── 信封解析（§3） ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "relative",
    [
        "valid/01_review_request.json",
        "valid/02_assignment.json",
        "valid/03_assignment_acceptance.json",
        "valid/04_delivery.json",
        "valid/06_receipt_accepted.json",
        "valid/07_error_freshness_unknown.json",
    ],
)
def test_cr_parse_accepts_frozen_valid_envelopes(relative):
    envelope = parse_envelope(_fixture(relative))
    assert envelope["profile"] == "agentnexus.code-review/1.0-draft.2"


def test_cr_parse_rejects_frozen_invalid_envelope():
    with pytest.raises(ProfileError) as excinfo:
        parse_envelope(_fixture("invalid/envelope_unregistered_message_type.json"))
    assert excinfo.value.code == "invalid_output"


def test_cr_parse_rejects_duplicate_keys_and_nan():
    dup = '{"profile":"agentnexus.code-review/1.0-draft.2","profile":"x"}'
    with pytest.raises(ProfileError) as excinfo:
        parse_envelope(dup)
    assert "重复键" in excinfo.value.safe_message

    with pytest.raises(ProfileError) as excinfo:
        parse_envelope('{"profile":"agentnexus.code-review/1.0-draft.2","payload":{"x":NaN}}')
    assert excinfo.value.code == "invalid_output"


def test_cr_parse_rejects_unsupported_profile_and_critical_extension():
    envelope = _fixture_json("valid/02_assignment.json")
    envelope["profile"] = "agentnexus.code-review/9.9"
    with pytest.raises(ProfileError) as excinfo:
        parse_envelope(envelope)
    assert excinfo.value.code == "unsupported_profile"

    envelope = _fixture_json("valid/02_assignment.json")
    envelope["critical_extensions"] = ["future-semantics"]
    with pytest.raises(ProfileError) as excinfo:
        parse_envelope(envelope)
    assert excinfo.value.code == "unsupported_critical_extension"


def test_cr_parse_requires_task_message_ids():
    envelope = _fixture_json("valid/02_assignment.json")
    envelope.pop("assignment_epoch")
    with pytest.raises(ProfileError) as excinfo:
        parse_envelope(envelope)
    assert "assignment_epoch" in excinfo.value.safe_message


# ── ReviewReport 校验（§6.3/§15.8） ───────────────────────────────────


@pytest.mark.parametrize(
    "relative",
    [
        "valid/05_review_report_partial_inconclusive.artifact_body.json",
        "valid/08_review_report_issues_found.artifact_body.json",
        "valid/09_review_report_issues_found_with_inherited_gap.artifact_body.json",
    ],
)
def test_cr_report_accepts_frozen_valid_reports(relative):
    assert validate_review_report(_fixture_json(relative)) == []


@pytest.mark.parametrize(
    "relative,expected_rule",
    [
        ("invalid/report_findings_without_issues_found.json", "§6.3"),
        ("invalid/report_no_findings_with_partial_coverage.json", "§6.3"),
        ("invalid/report_inherited_gap_with_complete_coverage.json", "§15.8"),
        ("invalid/report_usage_unknown_with_token_counts.json", "§6.3"),
    ],
)
def test_cr_report_rejects_frozen_invalid_reports_with_expected_rule(relative, expected_rule):
    issues = validate_review_report(_fixture_json(relative))
    assert issues, f"{relative} 应当被拒绝"
    assert any(i.rule.startswith(expected_rule) for i in issues), [str(i) for i in issues]


def test_cr_report_requires_findings_to_carry_evidence():
    report = _fixture_json("valid/08_review_report_issues_found.artifact_body.json")
    report["findings"][0]["evidence_refs"] = []
    issues = validate_review_report(report)
    assert any(i.rule == "minItems" for i in issues)


def test_cr_severity_mapping_is_provider_configurable_and_rejects_unknown():
    """严重度映射不再归属单一厂商：默认表 + 自定义表，未知词元一律拒绝（不降级）。"""
    assert priority_to_severity("P0") == "critical"
    assert priority_to_severity("p3") == "low"
    assert DEFAULT_PRIORITY_SEVERITY_MAP["P1"] == "high"

    # 自定义词表（如另一家评审方的 S1–S4）
    assert priority_to_severity("S1", mapping={"S1": "critical", "S4": "low"}) == "critical"
    assert priority_to_severity("s4", mapping={"S1": "critical", "S4": "low"}) == "low"

    with pytest.raises(ProfileError) as excinfo:
        priority_to_severity("P9")
    assert excinfo.value.code == "invalid_output"

    # 映射结果本身必须是合法 Profile severity，否则拒绝（防止把未知档位塞进来）
    with pytest.raises(ProfileError) as excinfo:
        priority_to_severity("X", mapping={"X": "blocker"})
    assert "严重度映射结果不合法" in excinfo.value.safe_message


# ── 状态翻译责任层（§15.2 / CP-09 / CP-17） ───────────────────────────


def test_cr_translate_completed_with_valid_report_preserves_outcome():
    report = _fixture_json("valid/08_review_report_issues_found.artifact_body.json")
    result = translate_agentnexus_result(
        "completed", artifact_type="CodeReviewReport", report=report
    )
    assert result.profile_run_state == "completed"
    assert result.outcome == "issues_found"


def test_cr_translate_changes_requested_becomes_completed_issues_found():
    """CP-09：有有效 finding 时不得映射为执行失败或重跑。"""
    report = _fixture_json("valid/08_review_report_issues_found.artifact_body.json")
    result = translate_agentnexus_result(
        "changes_requested", artifact_type="CodeReviewReport", report=report
    )
    assert result.profile_run_state == "completed"
    assert result.outcome == "issues_found"
    assert result.domain_status == "changes_requested"


def test_cr_translate_rejects_plain_text_completed():
    """CP-17：普通 stdout 包装的 completed 不得完成 Run。"""
    with pytest.raises(ProfileError) as excinfo:
        translate_agentnexus_result("completed", artifact_type="TextArtifact", report=None)
    assert excinfo.value.code == "invalid_output"


def test_cr_translate_rejects_unknown_status():
    with pytest.raises(ProfileError) as excinfo:
        translate_agentnexus_result("approved", artifact_type="CodeReviewReport", report={})
    assert excinfo.value.code == "invalid_output"


def test_cr_translate_rejects_structurally_invalid_report():
    report = _fixture_json("valid/05_review_report_partial_inconclusive.artifact_body.json")
    report["coverage"]["status"] = "complete"
    with pytest.raises(ProfileError) as excinfo:
        translate_agentnexus_result("completed", artifact_type="CodeReviewReport", report=report)
    assert excinfo.value.code == "invalid_output"
    assert "violations" in excinfo.value.extra


def test_cr_translate_blocked_maps_to_failed_with_human():
    result = translate_agentnexus_result("blocked", artifact_type="", report=None)
    assert result.profile_run_state == "failed"
    assert result.domain_status == "blocked"
    assert result.requires_human is True and result.action_required is True


def test_cr_translate_failed_passes_through():
    result = translate_agentnexus_result("failed", artifact_type="", report=None)
    assert result.profile_run_state == "failed"
    assert result.requires_human is False
