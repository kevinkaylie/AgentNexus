"""评审结论的呈现与发布前校验（厂商无关）。

规则来自 Profile §6 + binding RC2 §6 与 q3 行为用例，对**任何**评审方一致：

- 摘要必须**同时**呈现 ``outcome`` 与 ``coverage.status``，不得只给一个维度；
- 覆盖非 ``complete`` 时必须给出缺口警示、遗漏范围与继承缺口，并禁止
  "评审充分 / 全部评审完成 / 无问题 / 全部评审"这类表述；
- findings 的严重度、触发条件、影响与证据仍要呈现；
- Publisher 写入外部系统前必须调用 :func:`validate_publish_body`，缺失必需覆盖信息时
  返回 **422** ``invalid_output``，并**一次列出全部问题**（避免作者反复试错）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from .errors import ProfileError

OUTCOME_LABEL = {
    "issues_found": "发现问题",
    "no_findings": "未发现问题",
    "inconclusive": "结论不充分",
}
COVERAGE_LABEL = {"complete": "完整", "partial": "部分"}

#: 覆盖非 complete 时禁止出现在呈现文本中的表述。
#:
#: 注意：这是**朴素子串**守卫，因此渲染方（含本模块的缺口警示文案）不得使用这些
#: 词元——即使是否定句（"不得据此认定…无问题"）也会被判定为违规。若需要更强的判别，
#: 应由发布模板改为结构化字段渲染，而不是依赖自然语言否定语气。
FORBIDDEN_WHEN_INCOMPLETE = ("评审充分", "全部评审完成", "无问题", "全部评审")


def render_review_summary(report: Mapping[str, Any]) -> str:
    """渲染评审摘要（UI/评论正文）。"""
    outcome = str(report.get("outcome") or "")
    coverage = report.get("coverage") or {}
    status = str(coverage.get("status") or "")
    if outcome not in OUTCOME_LABEL:
        raise ProfileError(
            "invalid_output", f"未知 outcome：{outcome}", scope="presentation"
        )

    lines = [f"{OUTCOME_LABEL[outcome]}；覆盖：{COVERAGE_LABEL.get(status, status)}"]

    if status != "complete":
        lines.append("缺口警示：本次评审未覆盖全部计划范围，结论不构成通过依据。")
        omitted = coverage.get("omitted_files") or []
        if omitted:
            lines.append(
                "遗漏范围："
                + "，".join(f"{item.get('path')}（{item.get('reason')}）" for item in omitted)
            )
        gaps = coverage.get("gap_reasons") or []
        if gaps:
            lines.append("缺口原因：" + "；".join(str(g) for g in gaps))
        inherited = coverage.get("inherited_gaps") or []
        if inherited:
            lines.append(
                "继承缺口："
                + "；".join(f"{item.get('source')}（{item.get('reason')}）" for item in inherited)
            )

    for finding in report.get("findings") or []:
        lines.append(f"[{finding.get('severity')}] {finding.get('title')}")
        lines.append(f"  触发：{finding.get('trigger')}")
        lines.append(f"  影响：{finding.get('impact')}")
        refs = finding.get("evidence_refs") or []
        lines.append(
            f"  证据：{len(refs)} 条（{refs[0].get('path', 'n/a')} 等）" if refs else "  证据：无"
        )

    for limitation in report.get("limitations") or []:
        lines.append(f"限制：{limitation}")

    return "\n".join(lines)


def validate_publish_body(body: str, report: Mapping[str, Any]) -> None:
    """Publisher 写外部系统前的呈现校验；不合规抛 422 ``invalid_output``。"""
    outcome = str(report.get("outcome") or "")
    coverage = report.get("coverage") or {}
    status = str(coverage.get("status") or "")

    problems: List[str] = []
    if OUTCOME_LABEL.get(outcome, "") not in body:
        problems.append("摘要未呈现 outcome")
    if COVERAGE_LABEL.get(status, status) not in body:
        problems.append("摘要未呈现 coverage.status")

    if status != "complete":
        if "缺口警示" not in body:
            problems.append("覆盖非 complete 时缺少缺口警示")
        for item in coverage.get("omitted_files") or []:
            if item.get("path") and item["path"] not in body:
                problems.append(f"遗漏范围未呈现：{item['path']}")
        for item in coverage.get("inherited_gaps") or []:
            if item.get("source") and item["source"] not in body:
                problems.append(f"继承缺口未呈现：{item['source']}")
        for phrase in FORBIDDEN_WHEN_INCOMPLETE:
            if phrase in body:
                problems.append(f"覆盖非 complete 时出现禁止表述：{phrase}")

    if problems:
        # 禁止表述最严重，排在前面；一次返回全部问题，避免作者反复试错
        problems.sort(
            key=lambda text: 0 if text.startswith("覆盖非 complete 时出现禁止表述") else 1
        )
        raise ProfileError(
            "invalid_output",
            "发布正文不满足呈现要求：" + "；".join(problems),
            scope="presentation",
            http_status=422,
            extra={"problems": problems},
        )


def presentation_requirements(report: Mapping[str, Any]) -> Dict[str, Any]:
    """给 UI/发布模板用的结构化要求（避免模板各自发明规则）。"""
    coverage = report.get("coverage") or {}
    status = str(coverage.get("status") or "")
    return {
        "outcome_label": OUTCOME_LABEL.get(str(report.get("outcome") or ""), ""),
        "coverage_label": COVERAGE_LABEL.get(status, status),
        "must_show_coverage": True,
        "must_show_gap_warning": status != "complete",
        "omitted_paths": [i.get("path") for i in coverage.get("omitted_files") or []],
        "inherited_gap_sources": [i.get("source") for i in coverage.get("inherited_gaps") or []],
        "forbidden_phrases_when_incomplete": list(FORBIDDEN_WHEN_INCOMPLETE),
    }
