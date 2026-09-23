"""可插拔性证明：新增评审方只需一个适配器类 + 注册，不改 AgentNexus 核心。

本文件用一个**词表与字段形状都与 HCZJ 不同**的评审方（ACME：`acme.review.v2` /
`acme.coverage.v2`、outcome `defects|clean|unknown`、severity `S1–S4`、finding 字段
`id/level/summary/repro/consequence/span/proof`）走完整管线，验证：

1. 注册表与按 schema 自动识别可用；
2. 同一套厂商无关规则（§6.3 outcome 推导、覆盖上限、缺口原义保留、溯源、结构校验）
   对任何 provider 一致生效；
3. 未知 provider / 未知 schema 返回 ``unsupported_contract``，**不静默降级**；
4. HCZJ 的专用便捷入口与厂商无关入口语义一致（重构未改变行为）；
5. 呈现规则与发布前校验与 provider 无关。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pytest

from agent_net.code_review import (
    ProfileError,
    ReviewProviderAdapter,
    build_hczj_profile_report,
    build_profile_report,
    detect_provider,
    get_provider,
    list_providers,
    register_provider,
    render_review_summary,
    report_digest,
    validate_publish_body,
    validate_review_report,
)

MANIFEST_DIGEST = "sha256:" + "1" * 64


# ── 第二个评审方：ACME（词表/字段名都与 HCZJ 不同） ───────────────────


class AcmeReviewProvider(ReviewProviderAdapter):
    provider_id = "acme"
    display_name = "ACME 静态分析"
    source_report_schemas = ("acme.review.v2",)
    source_coverage_schemas = ("acme.coverage.v2",)
    source_outcomes = ("defects", "clean", "unknown")
    coverage_complete_token = "full"
    native_status_key = "verdict"
    provenance_key = "acme.provenance"
    severity_map = {"S1": "critical", "S2": "high", "S3": "medium", "S4": "low"}
    error_scope = "acme_conversion"

    def _map_findings(self, native_report: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """ACME 用 defects + 自有字段名，这里只做字段级映射（规则由基类收敛）。"""
        findings: List[Dict[str, Any]] = []
        for defect in native_report.get("defects") or []:
            findings.append(
                {
                    "finding_id": defect["id"],
                    "severity": defect["level"],  # 仍是 ACME 词元，由基类按 severity_map 换算
                    "title": defect["summary"],
                    "trigger": defect["repro"],
                    "impact": defect["consequence"],
                    "location": defect["span"],
                    "evidence_refs": list(defect.get("proof") or []),
                    "suggested_validation": defect.get("how_to_verify", "待补充验证方式"),
                }
            )
        return findings

    def _map_coverage(
        self, native_coverage: Mapping[str, Any], native_report: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """ACME 覆盖用 verdict/scanned/skipped/reasons/inherited；只报告原状态。"""
        cov = native_coverage or {}
        return {
            "_declared_status": str(cov.get("verdict") or ""),
            "planned_files": list(cov.get("planned") or []),
            "reviewed_files": list(cov.get("scanned") or []),
            "omitted_files": [
                {"path": item.get("file", ""), "reason": item.get("why", "")}
                for item in (cov.get("skipped") or [])
            ],
            "gap_reasons": list(cov.get("reasons") or []),
            "inherited_gaps": [
                {"source": item.get("from", ""), "reason": item.get("why", "")}
                for item in (cov.get("inherited") or [])
            ],
        }


register_provider(AcmeReviewProvider())


def _evidence(path: str = "svc/Order.java") -> dict:
    return {
        "provider_id": "acme-scanner",
        "report_id": "A-9",
        "side": "after",
        "snapshot_id": "snap_a",
        "project": "proj_x",
        "commit_sha": "2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c",
        "path": path,
        "blob_sha": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
        "start_line": 10,
        "end_line": 12,
        "content_sha256": "5e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f",
    }


def _acme_report(outcome: str = "defects", defects: Optional[list] = None) -> dict:
    return {
        "schema_version": "acme.review.v2",
        "report_id": "A-9",
        "outcome": outcome,
        "defects": [
            {
                "id": "D-1",
                "level": "S2",
                "summary": "NPE 风险",
                "repro": "并发下单",
                "consequence": "订单状态不一致",
                "span": {
                    "side": "after",
                    "commit_sha": "2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c",
                    "path": "svc/Order.java",
                    "start_line": 10,
                    "end_line": 12,
                },
                "proof": [_evidence()],
            }
        ]
        if defects is None
        else defects,
        "limitations": [],
    }


def _acme_coverage(verdict: str = "partial", with_skipped: bool = True) -> dict:
    return {
        "schema_version": "acme.coverage.v2",
        "verdict": verdict,
        "planned": ["svc/Order.java", "svc/Repo.java"],
        "scanned": ["svc/Order.java"],
        "skipped": [{"file": "svc/Repo.java", "why": "time_budget"}] if with_skipped else [],
        "reasons": ["时间预算耗尽"],
        "inherited": [{"from": "impact-A9", "why": "依赖图截断"}],
    }


def _identity() -> dict:
    return {
        "run_id": "RUN-ACME-1",
        "attempt_id": "A1",
        "input_manifest_digest": MANIFEST_DIGEST,
        "impact_artifact": {
            "artifact_id": "art_impact_A9",
            "producer_id": "acme-scanner",
            "media_type": "application/json",
            "schema_version": "acme.impact.v2",
            "digest_algorithm": "sha256-bytes-v1",
            "digest": "sha256:" + "0" * 64,
            "byte_length": 100,
            "locator": "acme-report:acme-scanner:A-9",
            "access_scope": "service_private",
            "retention_until": "2027-03-18T00:00:00Z",
            "replaces": None,
        },
        "review_policy_sha256": "b" * 64,
        "review_revision": 1,
        "base_sha": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
        "head_sha": "2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c",
        "target_sha": "3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d",
        "generation": 1,
        "execution_revision": 1,
        "reviewer_id": "acme-reviewer",
    }


def _metadata() -> dict:
    return {
        "provider": "acme",
        "model": "static-analyzer",
        "model_version": None,
        "skill_version": "acme/2.0",
        "tool_versions": [],
        "started_at": "2026-09-20T02:00:00Z",
        "completed_at": "2026-09-20T02:05:00Z",
    }


def _usage() -> dict:
    return {
        "measurement": "known",
        "input_tokens": 1000,
        "output_tokens": 200,
        "cost": None,
        "note": None,
    }


def _build(provider_id: Optional[str] = "acme", **overrides) -> dict:
    kwargs: Dict[str, Any] = dict(
        native_report=_acme_report(),
        native_coverage=_acme_coverage(),
        identity=_identity(),
        execution_metadata=_metadata(),
        usage=_usage(),
    )
    kwargs.update(overrides)
    if provider_id is not None:
        kwargs["provider_id"] = provider_id
    return build_profile_report(**kwargs)


# ── 1. 注册表与识别 ───────────────────────────────────────────────────


def test_provider_registry_and_detection():
    assert "hczj" in list_providers()
    assert "acme" in list_providers()
    assert get_provider("acme").display_name == "ACME 静态分析"
    assert detect_provider("acme.review.v2").provider_id == "acme"
    assert detect_provider("hczj.review_report.v1").provider_id == "hczj"
    assert detect_provider("nobody.review.v1") is None


def test_unknown_provider_and_schema_return_unsupported_contract():
    with pytest.raises(ProfileError) as excinfo:
        get_provider("nobody")
    assert excinfo.value.code == "unsupported_contract"

    # 自动识别失败同样拒绝，不静默降级到别的 provider
    with pytest.raises(ProfileError) as excinfo:
        _build(provider_id=None, native_report={**_acme_report(), "schema_version": "nobody.v1"})
    assert excinfo.value.code == "unsupported_contract"


# ── 2. 第二个 provider 走完整管线 ─────────────────────────────────────


def test_second_provider_converts_through_shared_pipeline():
    target = _build()

    assert validate_review_report(target) == []
    assert target["outcome"] == "issues_found"
    assert target["coverage"]["status"] == "partial"
    assert target["findings"][0]["finding_id"] == "D-1"
    assert target["findings"][0]["severity"] == "high"  # S2 → high（ACME 自有词表）
    assert target["coverage"]["omitted_files"][0]["path"] == "svc/Repo.java"
    assert target["coverage"]["inherited_gaps"][0]["source"] == "impact-A9"
    assert target["extensions"]["acme.provenance"]["source_outcome"] == "defects"
    assert "hczj.provenance" not in target["extensions"]


def test_auto_detection_matches_explicit_provider():
    explicit = _build(provider_id="acme")
    detected = _build(provider_id=None)
    assert report_digest(json.dumps(explicit, ensure_ascii=False)) == report_digest(
        json.dumps(detected, ensure_ascii=False)
    )


def test_shared_invariants_hold_for_second_provider():
    # 无 defect + 覆盖不完整 → inconclusive（不得因"无发现"而当通过）
    clean = _build(native_report=_acme_report(outcome="clean", defects=[]))
    assert clean["outcome"] == "inconclusive"
    assert clean["coverage"]["status"] == "partial"

    # 有 defect + 声明 full 但仍有 skipped → coverage 仍为 partial（不得提升）
    upgraded = _build(native_coverage=_acme_coverage(verdict="full", with_skipped=True))
    assert upgraded["coverage"]["status"] == "partial"
    assert upgraded["extensions"]["acme.provenance"]["source_coverage_status"] == "full"

    # 未知 severity 拒绝而非降级
    bad = _acme_report()
    bad["defects"][0]["level"] = "S9"
    with pytest.raises(ProfileError) as excinfo:
        _build(native_report=bad)
    assert excinfo.value.code == "invalid_output"


# ── 3. 重构未改变 HCZJ 行为 ───────────────────────────────────────────


def test_hczj_shortcut_equals_generic_entry():
    report = {
        "schema_version": "hczj.review_report.v1",
        "report_id": "R1",
        "outcome": "findings_present",
        "findings": [],
        "limitations": [],
    }
    coverage = {
        "schema_version": "hczj.review_coverage.v1",
        "status": "partial",
        "planned_files": [],
        "reviewed_files": [],
        "omitted_files": [],
        "gap_reasons": ["g"],
        "inherited_gaps": [],
    }
    identity = dict(_identity(), run_id="RUN-HCZJ-1")
    shortcut = build_hczj_profile_report(
        hczj_report=report,
        hczj_coverage=coverage,
        identity=identity,
        execution_metadata=_metadata(),
        usage=_usage(),
    )
    generic = build_profile_report(
        provider_id="hczj",
        native_report=report,
        native_coverage=coverage,
        identity=identity,
        execution_metadata=_metadata(),
        usage=_usage(),
    )
    assert json.dumps(shortcut, sort_keys=True, ensure_ascii=False) == json.dumps(
        generic, sort_keys=True, ensure_ascii=False
    )


# ── 4. 呈现规则与 provider 无关 ───────────────────────────────────────


def test_presentation_rules_are_provider_agnostic():
    target = _build()
    body = render_review_summary(target)
    assert "发现问题" in body and "覆盖：部分" in body
    assert "缺口警示" in body
    assert "svc/Repo.java" in body  # ACME 的遗漏范围
    assert "impact-A9" in body  # ACME 的继承缺口
    validate_publish_body(body, target)

    # 同一个发布前校验对 ACME 报告同样生效（缺遗漏范围 → 422）
    with pytest.raises(ProfileError) as excinfo:
        validate_publish_body(body.replace("svc/Repo.java", ""), target)
    assert excinfo.value.http_status == 422


# ── 5. B7：输入格式错误必须报错，不得过滤后改变结论 ───────────────────


def _hczj_shaped_report(findings: list, outcome: str = "findings_present") -> dict:
    """HCZJ 形状的原生报告（用真实注册的 hczj provider 走公共管线）。"""
    return {
        "schema_version": "hczj.review_report.v1",
        "report_id": "R-B7",
        "outcome": outcome,
        "findings": findings,
        "limitations": [],
    }


def _hczj_shaped_coverage(status: str = "complete", **overrides) -> dict:
    coverage = {
        "schema_version": "hczj.review_coverage.v1",
        "status": status,
        "planned_files": ["a.py"],
        "reviewed_files": ["a.py"],
        "omitted_files": [],
        "gap_reasons": [],
        "inherited_gaps": [],
    }
    coverage.update(overrides)
    return coverage


def _hczj_identity() -> dict:
    identity = _identity()
    identity["run_id"] = "RUN-B7"
    identity["attempt_id"] = "A1"
    return identity


def test_malformed_finding_is_rejected_not_silently_dropped():
    """评审 B7 复现：malformed finding 曾被过滤掉，把"有发现"错报成 no_findings。"""
    with pytest.raises(ProfileError) as excinfo:
        build_profile_report(
            provider_id="hczj",
            native_report=_hczj_shaped_report(["malformed-finding"]),
            native_coverage=_hczj_shaped_coverage(),
            identity=_hczj_identity(),
            execution_metadata=_metadata(),
            usage=_usage(),
        )
    assert excinfo.value.code == "invalid_output"
    assert "不是对象" in excinfo.value.safe_message
    assert "不得过滤" in excinfo.value.safe_message


def test_malformed_gap_signal_is_rejected_not_silently_dropped():
    """缺口条目被悄悄丢弃会把"覆盖不足"提升为 complete，必须报错。"""
    with pytest.raises(ProfileError) as excinfo:
        build_profile_report(
            provider_id="hczj",
            native_report=_hczj_shaped_report([]),
            native_coverage=_hczj_shaped_coverage(status="partial", omitted_files=["not-an-object"]),
            identity=_hczj_identity(),
            execution_metadata=_metadata(),
            usage=_usage(),
        )
    assert excinfo.value.code == "invalid_output"
    assert "omitted_files" in excinfo.value.safe_message


def test_unlisted_native_schema_is_unsupported_contract():
    """声明了 source_report_schemas 就必须强制核对，不能放行任意 schema。"""
    report = _hczj_shaped_report([])
    report["schema_version"] = "hczj.review_report.v99"
    with pytest.raises(ProfileError) as excinfo:
        build_profile_report(
            provider_id="hczj",
            native_report=report,
            native_coverage=_hczj_shaped_coverage(),
            identity=_hczj_identity(),
            execution_metadata=_metadata(),
            usage=_usage(),
        )
    assert excinfo.value.code == "unsupported_contract"
    assert "原生报告 schema 不受支持" in excinfo.value.safe_message


def test_unlisted_coverage_schema_is_unsupported_contract():
    coverage = _hczj_shaped_coverage()
    coverage["schema_version"] = "hczj.review_coverage.v99"
    with pytest.raises(ProfileError) as excinfo:
        build_profile_report(
            provider_id="hczj",
            native_report=_hczj_shaped_report([]),
            native_coverage=coverage,
            identity=_hczj_identity(),
            execution_metadata=_metadata(),
            usage=_usage(),
        )
    assert excinfo.value.code == "unsupported_contract"
    assert "原生覆盖 schema 不受支持" in excinfo.value.safe_message


def test_valid_hczj_report_still_converts_after_strictening():
    """收紧不能把正常输入也拒掉。"""
    report = build_profile_report(
        provider_id="hczj",
        native_report=_hczj_shaped_report([], outcome="no_findings"),
        native_coverage=_hczj_shaped_coverage(status="complete"),
        identity=_hczj_identity(),
        execution_metadata=_metadata(),
        usage=_usage(),
    )
    assert report["outcome"] == "no_findings"
    assert report["coverage"]["status"] == "complete"
    assert not validate_review_report(report)


# ── 6. R2-5：显式 null 不得被当成空集合 ───────────────────────────────


def test_null_findings_is_rejected_not_reported_as_no_findings():
    """复审 R2-5 复现：outcome=findings_present + findings=null 曾变成 no_findings。"""
    report = _hczj_shaped_report([])
    report["findings"] = None
    with pytest.raises(ProfileError) as excinfo:
        build_profile_report(
            provider_id="hczj",
            native_report=report,
            native_coverage=_hczj_shaped_coverage(status="complete"),
            identity=_hczj_identity(),
            execution_metadata=_metadata(),
            usage=_usage(),
        )
    assert excinfo.value.code == "invalid_output"
    assert "findings" in excinfo.value.safe_message
    assert "null" in excinfo.value.safe_message


def test_missing_findings_is_rejected():
    """缺失必填集合与显式 null 都不等于空集合。"""
    report = _hczj_shaped_report([])
    report.pop("findings")
    with pytest.raises(ProfileError) as excinfo:
        build_profile_report(
            provider_id="hczj",
            native_report=report,
            native_coverage=_hczj_shaped_coverage(status="complete"),
            identity=_hczj_identity(),
            execution_metadata=_metadata(),
            usage=_usage(),
        )
    assert excinfo.value.code == "invalid_output"
    assert "缺少必填集合字段" in excinfo.value.safe_message


def test_null_gap_collections_are_rejected():
    """缺口集合为 null 不得被静默当成"没有缺口"（那会把覆盖提升为 complete）。"""
    for key in ("omitted_files", "inherited_gaps"):
        coverage = _hczj_shaped_coverage(status="partial")
        coverage[key] = None
        with pytest.raises(ProfileError) as excinfo:
            build_profile_report(
                provider_id="hczj",
                native_report=_hczj_shaped_report([], outcome="no_findings"),
                native_coverage=coverage,
                identity=_hczj_identity(),
                execution_metadata=_metadata(),
                usage=_usage(),
            )
        assert excinfo.value.code == "invalid_output"
        assert key in excinfo.value.safe_message
