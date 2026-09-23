"""评审方适配器接口与注册表 —— 「任一评审方 → Profile 报告」的通用管线。

设计目标（对应"多业务可接入"）：把 **厂商无关** 的部分（§6.3 outcome 推导、覆盖上限、
缺口原义保留、溯源、结构校验、严重度映射）收敛到本模块，具体评审方只声明自己的
**词表与字段形状**。新增一个评审方 = 新增一个 :class:`ReviewProviderAdapter` 子类并注册，
**不需要改动** AgentNexus 核心、无需改动既有 provider。

厂商无关的硬规则（任何 provider 都必须满足，由基类统一执行）：

- 目标 outcome 按 Profile §6.3 **重新推导**，不沿用评审方原 outcome：
  非空 findings ⇒ ``issues_found``；无 findings 且覆盖非完整 ⇒ ``inconclusive``；
  无 findings 且覆盖完整 ⇒ ``no_findings``；
- 任一缺口信号（遗漏文件 / 缺口原因 / 继承缺口 / 原状态非"完整"）⇒ coverage 上限 ``partial``，
  **不得**提升为 complete（§15.8）；
- 原始 outcome、来源 schema、来源 report_id 与推导结果保留在 ``extensions`` 作为溯源，
  不得"丢掉信息后宣称两者等价"；
- 严重度按 provider 声明的映射表转换，**未知值拒绝**（不降级为 low，RC2 §6）；
- 转换结果必须通过 :func:`validate_review_report`，否则 ``invalid_output`` 并附违规明细。
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .errors import ProfileError
from .validation import (
    REPORT_SCHEMA_VERSION,
    ValidationIssue,
    validate_review_report,
)

#: 默认的"优先级 → Profile severity"映射。
#:
#: 该口径来自 binding RC2 §6，但**不归属任何单一厂商**：provider 可用
#: :attr:`ReviewProviderAdapter.severity_map` 覆盖为自己的词表（如 S1–S4）。
DEFAULT_PRIORITY_SEVERITY_MAP: Dict[str, str] = {
    "P0": "critical",
    "P1": "high",
    "P2": "medium",
    "P3": "low",
}

#: 转换后必须由 identity 提供的 Profile 身份/版本字段（§6.3）
REQUIRED_IDENTITY_FIELDS = (
    "run_id",
    "attempt_id",
    "input_manifest_digest",
    "impact_artifact",
    "review_policy_sha256",
    "review_revision",
    "base_sha",
    "head_sha",
    "target_sha",
    "generation",
    "execution_revision",
    "reviewer_id",
)

#: 目标 outcome 词表（Profile §6.3，与 provider 无关）
PROFILE_OUTCOMES = ("issues_found", "no_findings", "inconclusive")


def priority_to_severity(
    priority: Any,
    *,
    mapping: Optional[Mapping[str, str]] = None,
    scope: str = "severity_mapping",
) -> str:
    """把评审方的优先级/严重度词元映射为 Profile severity。

    ``mapping`` 缺省用 :data:`DEFAULT_PRIORITY_SEVERITY_MAP`；**未知词元一律拒绝**
    （``invalid_output``），不降级为 low —— 降级会让严重问题被静默弱化（RC2 §6）。
    """
    table = dict(DEFAULT_PRIORITY_SEVERITY_MAP if mapping is None else mapping)
    table = {str(k).upper(): str(v) for k, v in table.items()}
    mapped = table.get(str(priority).upper())
    if mapped is None:
        raise ProfileError(
            "invalid_output",
            f"未登记的严重度词元：{priority!r}（provider 映射表：{sorted(table)}）",
            scope=scope,
        )
    if mapped not in ("critical", "high", "medium", "low"):
        raise ProfileError(
            "invalid_output",
            f"严重度映射结果不合法：{mapped!r} → 必须是 critical/high/medium/low",
            scope=scope,
        )
    return mapped


def _require(condition: bool, message: str, *, scope: str, code: str = "invalid_output") -> None:
    if not condition:
        raise ProfileError(code, message, scope=scope)


class ReviewProviderAdapter:
    """评审方适配器基类。

    子类至少声明：``provider_id``、``source_report_schemas``；按需覆写
    ``source_outcomes`` / ``source_coverage_schemas`` / ``coverage_complete_token`` /
    ``severity_map`` / ``provenance_key``，以及字段级映射（``normalize_findings``）。
    """

    provider_id: str = ""
    display_name: str = ""
    #: 该 provider 可接受的原始报告 schema（用于自动识别）
    source_report_schemas: Tuple[str, ...] = ()
    source_coverage_schemas: Tuple[str, ...] = ()
    #: 该 provider 的 outcome 词表（仅用于校验与溯源，不参与目标 outcome 推导）
    source_outcomes: Tuple[str, ...] = ()
    #: 该 provider 表示"覆盖完整"的取值；其余一律视为不完整（上限 partial）
    coverage_complete_token: str = "complete"
    #: 原生报告里表示 outcome 的字段名（不同评审方可能不同，如 ``result``）
    native_outcome_key: str = "outcome"
    #: 原生覆盖里表示状态的字段名（如 ACME 用 ``verdict``）
    native_status_key: str = "status"
    #: 溯源键名；留空则用 ``<provider_id>.provenance``
    provenance_key: str = ""
    #: 严重度映射表（可覆盖为自家词表）
    severity_map: Mapping[str, str] = DEFAULT_PRIORITY_SEVERITY_MAP
    #: 错误 scope 前缀，便于定位是哪家 provider 的转换失败
    error_scope: str = "provider_conversion"

    # ── 识别 ──────────────────────────────────────────────────────────
    def accepts_schema(self, schema_version: Any) -> bool:
        return str(schema_version or "") in self.source_report_schemas

    # ── 输入严格校验（B7：格式错误必须报错，**不得过滤后推导结论**） ──
    def _require_native_schemas(
        self,
        native_report: Mapping[str, Any],
        native_coverage: Mapping[str, Any],
    ) -> None:
        """声明过的原生 schema 必须**强制**核对，而不是只写在类属性里（评审 B7）。

        缺少 ``schema_version`` 或不在白名单内 ⇒ ``unsupported_contract``（不是静默继续）。
        """
        if self.source_report_schemas:
            declared = str(native_report.get("schema_version") or "")
            _require(
                declared in self.source_report_schemas,
                f"{self.provider_id}: 原生报告 schema 不受支持：{declared or '未声明'}"
                f"（只接受 {'/'.join(self.source_report_schemas)}）",
                scope=self.error_scope,
                code="unsupported_contract",
            )
        if self.source_coverage_schemas:
            declared = str(native_coverage.get("schema_version") or "")
            _require(
                declared in self.source_coverage_schemas,
                f"{self.provider_id}: 原生覆盖 schema 不受支持：{declared or '未声明'}"
                f"（只接受 {'/'.join(self.source_coverage_schemas)}）",
                scope=self.error_scope,
                code="unsupported_contract",
            )

    def _strict_list(
        self,
        container: Mapping[str, Any],
        key: str,
        *,
        require_mapping: bool,
        required: bool = False,
    ) -> List[Any]:
        """取一个必须为数组的原生字段；元素类型不符立即 ``invalid_output``。

        旧实现在这里做 ``if isinstance(item, Mapping)`` 过滤，导致非法 finding 被静默
        丢弃、进而把"有发现"错报成 ``no_findings``（评审 B7 复现：HCZJ
        outcome=findings_present + findings=["malformed-finding"] → no_findings）。

        评审 R2-5：``raw is None`` **不得**直接返回 ``[]``——显式 ``null`` 与"字段不存在"
        是两件事。原生契约里必填的集合（findings / omitted_files / inherited_gaps）缺失或
        为 null 都必须报错，否则 ``outcome=findings_present`` + ``findings=null`` 仍会被
        静默转换成 ``no_findings``。
        """
        if key not in container:
            _require(
                not required,
                f"{self.provider_id}: 缺少必填集合字段 {key}（不得按空集合处理）",
                scope=self.error_scope,
            )
            return []
        raw = container[key]
        _require(
            raw is not None,
            f"{self.provider_id}: {key} 不得为 null——缺失与显式 null 必须区分，"
            "null 不得静默当作空集合",
            scope=self.error_scope,
        )
        _require(
            isinstance(raw, list),
            f"{self.provider_id}: 原生字段 {key} 必须是数组",
            scope=self.error_scope,
        )
        if require_mapping:
            bad = [i for i, item in enumerate(raw) if not isinstance(item, Mapping)]
            _require(
                not bad,
                f"{self.provider_id}: {key} 的第 {bad[:5]} 项不是对象——"
                "格式错误必须报错，不得过滤后改变结论",
                scope=self.error_scope,
            )
        else:
            bad = [i for i, item in enumerate(raw) if not isinstance(item, str) or not item]
            _require(
                not bad,
                f"{self.provider_id}: {key} 的第 {bad[:5]} 项必须是非空字符串",
                scope=self.error_scope,
            )
        return list(raw)

    # ── 字段级映射（子类钩子，**只负责映射，不负责规则**） ──────────────
    def _map_findings(self, native_report: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """钩子：把原生 finding 映射为 Profile 字段名（severity 可仍用原生词元）。

        默认假设字段名与 Profile 一致。**不要**在这里做严重度换算或跳过校验——
        基类的 :meth:`_finalize_findings` 会统一施加必填/证据/严重度规则。
        元素类型校验由 :meth:`_strict_list` 统一负责，这里**不做过滤**。
        """
        return [
            dict(finding)
            for finding in self._strict_list(
                native_report, "findings", require_mapping=True, required=True
            )
        ]

    def _map_coverage(
        self,
        native_coverage: Mapping[str, Any],
        native_report: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """钩子：把原生覆盖映射为 Profile 字段名，并在 ``_declared_status`` 里报告原状态。

        默认假设字段名与 Profile 一致。**不要**在这里决定最终 ``status``——
        基类的 :meth:`_finalize_coverage` 会统一施加"覆盖不得提升"上限。
        缺口信号（omitted_files / inherited_gaps）逐项严格校验，**不得丢弃**：
        丢弃它们会直接把"覆盖不足"提升为 complete（评审 B7）。
        """
        coverage = native_coverage or {}
        # R2-5：缺口集合是必填的——显式 null / 缺失都不得被当成"没有缺口"。
        omitted = [
            {"path": item.get("path", ""), "reason": item.get("reason", "")}
            for item in self._strict_list(
                coverage, "omitted_files", require_mapping=True, required=True
            )
        ]
        inherited = [
            {"source": item.get("source", ""), "reason": item.get("reason", "")}
            for item in self._strict_list(
                coverage, "inherited_gaps", require_mapping=True, required=True
            )
        ]
        return {
            "_declared_status": str(coverage.get(self.native_status_key) or ""),
            "planned_files": list(self._strict_list(coverage, "planned_files", require_mapping=False)),
            "reviewed_files": list(self._strict_list(coverage, "reviewed_files", require_mapping=False)),
            "omitted_files": omitted,
            "gap_reasons": list(self._strict_list(coverage, "gap_reasons", require_mapping=False)),
            "inherited_gaps": inherited,
        }

    # ── 最终收敛（基类执行，provider 不可绕过） ──────────────────────
    def _finalize_findings(self, mapped: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        for index, finding in enumerate(mapped):
            _require(
                isinstance(finding, Mapping),
                f"findings[{index}] 必须是对象",
                scope=self.error_scope,
            )
            for key in ("finding_id", "severity", "title", "trigger", "impact", "location"):
                _require(key in finding, f"findings[{index}] 缺少 {key}", scope=self.error_scope)
            evidence = finding.get("evidence_refs") or []
            _require(
                isinstance(evidence, list) and len(evidence) > 0,
                f"findings[{index}] 必须带证据引用（§6.3）",
                scope=self.error_scope,
            )
            findings.append(
                {
                    "finding_id": finding["finding_id"],
                    "severity": priority_to_severity(
                        finding["severity"], mapping=self.severity_map, scope=self.error_scope
                    ),
                    "title": finding["title"],
                    "trigger": finding["trigger"],
                    "impact": finding["impact"],
                    "location": finding["location"],
                    "evidence_refs": list(evidence),
                    "suggested_validation": finding.get(
                        "suggested_validation", "待补充验证方式"
                    ),
                }
            )
        return findings

    def _finalize_coverage(self, mapped: Mapping[str, Any]) -> Dict[str, Any]:
        """收敛覆盖：任一缺口信号或原状态非"完整" ⇒ ``partial``，**不得提升**（§15.8）。"""
        declared = str(mapped.get("_declared_status") or "")
        omitted = list(mapped.get("omitted_files") or [])
        gap_reasons = list(mapped.get("gap_reasons") or [])
        inherited = list(mapped.get("inherited_gaps") or [])
        has_gap = (
            bool(omitted)
            or bool(gap_reasons)
            or bool(inherited)
            or declared != self.coverage_complete_token
        )
        return {
            "status": "partial" if has_gap else "complete",
            "planned_files": list(mapped.get("planned_files") or []),
            "reviewed_files": list(mapped.get("reviewed_files") or []),
            "omitted_files": omitted,
            "gap_reasons": gap_reasons,
            "inherited_gaps": inherited,
        }

    # ── 厂商无关管线 ─────────────────────────────────────────────────
    def derive_outcome(self, findings: Sequence[Any], coverage: Mapping[str, Any]) -> str:
        """按 Profile §6.3 推导目标 outcome（**不使用**评审方原 outcome）。"""
        if findings:
            return "issues_found"
        if coverage.get("status") == "partial":
            return "inconclusive"
        return "no_findings"

    def provenance(
        self,
        native_report: Mapping[str, Any],
        native_coverage: Mapping[str, Any],
        outcome: str,
        coverage: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """构造 ``extensions`` 溯源块（默认含原 outcome、来源 schema 与推导结果）。"""
        key = self.provenance_key or f"{self.provider_id}.provenance"
        return {
            key: {
                "provider_id": self.provider_id,
                "source_schema": native_report.get("schema_version", ""),
                "source_coverage_schema": native_coverage.get("schema_version", ""),
                "source_report_id": native_report.get("report_id", ""),
                "source_outcome": str(native_report.get(self.native_outcome_key) or ""),
                "source_coverage_status": native_coverage.get(self.native_status_key),
                "derived_outcome": outcome,
                "derived_coverage_status": coverage["status"],
                "note": "Profile outcome 按 §6.3 不变式重新推导，原值保留于 source_outcome",
            }
        }

    def build_report(
        self,
        *,
        native_report: Mapping[str, Any],
        native_coverage: Mapping[str, Any],
        identity: Mapping[str, Any],
        execution_metadata: Mapping[str, Any],
        usage: Mapping[str, Any],
        limitations: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """把某评审方的原生报告+覆盖转换为 ``code_review.report.v1``。"""
        _require(
            isinstance(native_report, Mapping),
            f"{self.provider_id}: native_report 必须是对象",
            scope=self.error_scope,
        )
        _require(
            isinstance(native_coverage, Mapping),
            f"{self.provider_id}: native_coverage 必须是对象",
            scope=self.error_scope,
        )
        missing = [field for field in REQUIRED_IDENTITY_FIELDS if field not in identity]
        _require(
            not missing,
            f"{self.provider_id}: identity 缺少字段：{','.join(missing)}",
            scope=self.error_scope,
        )

        # B7：声明过的原生 schema 必须强制核对，不能在声明后放行任意输入。
        self._require_native_schemas(native_report, native_coverage)

        raw_outcome = str(native_report.get(self.native_outcome_key) or "")
        if self.source_outcomes:
            _require(
                raw_outcome in self.source_outcomes,
                f"{self.provider_id}: 未知的原 outcome：{raw_outcome or '空'}"
                f"（只接受 {'/'.join(self.source_outcomes)}）",
                scope=self.error_scope,
            )

        findings = self._finalize_findings(self._map_findings(native_report))
        coverage = self._finalize_coverage(self._map_coverage(native_coverage, native_report))
        outcome = self.derive_outcome(findings, coverage)

        report: Dict[str, Any] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            **{field: identity[field] for field in REQUIRED_IDENTITY_FIELDS},
            "coverage": coverage,
            "outcome": outcome,
            "findings": findings,
            "limitations": list(limitations or native_report.get("limitations") or []),
            "execution_metadata": dict(execution_metadata),
            "usage": dict(usage),
            "extensions": self.provenance(native_report, native_coverage, outcome, coverage),
        }

        issues: List[ValidationIssue] = validate_review_report(report)
        if issues:
            raise ProfileError(
                "invalid_output",
                f"{self.provider_id}: 转换后的 Profile 报告未通过结构校验：{issues[0]}",
                scope=self.error_scope,
                extra={"violations": [str(i) for i in issues]},
            )
        return report


# ── 注册表 ────────────────────────────────────────────────────────────

_REGISTRY: Dict[str, ReviewProviderAdapter] = {}


def register_provider(adapter: ReviewProviderAdapter) -> ReviewProviderAdapter:
    """注册/替换一个 provider（同 ``provider_id`` 覆盖注册，便于测试与部署扩展）。"""
    if not getattr(adapter, "provider_id", ""):
        raise ValueError("provider 必须声明 provider_id")
    _REGISTRY[adapter.provider_id] = adapter
    return adapter


def get_provider(provider_id: str) -> ReviewProviderAdapter:
    """按 id 取 provider；未注册返回 ``unsupported_contract``。"""
    adapter = _REGISTRY.get(str(provider_id))
    if adapter is None:
        raise ProfileError(
            "unsupported_contract",
            f"未注册的评审方 provider：{provider_id}（已注册：{sorted(_REGISTRY)}）",
            scope="provider_registry",
        )
    return adapter


def list_providers() -> List[str]:
    return sorted(_REGISTRY)


def detect_provider(schema_version: Any) -> Optional[ReviewProviderAdapter]:
    """按原生报告 schema 自动识别 provider；无匹配返回 None。"""
    for adapter in _REGISTRY.values():
        if adapter.accepts_schema(schema_version):
            return adapter
    return None


def build_profile_report(
    *,
    native_report: Mapping[str, Any],
    native_coverage: Mapping[str, Any],
    identity: Mapping[str, Any],
    execution_metadata: Mapping[str, Any],
    usage: Mapping[str, Any],
    provider_id: Optional[str] = None,
    limitations: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """**厂商无关**入口：可指定 ``provider_id``，或按原生报告 schema 自动识别。

    自动识别失败（未注册的 schema）返回 ``unsupported_contract``；显式指定未注册的
    ``provider_id`` 返回 ``unsupported_contract``（均不静默降级为别的 provider）。
    """
    if provider_id:
        adapter = get_provider(provider_id)
    else:
        adapter = detect_provider(native_report.get("schema_version"))
        if adapter is None:
            raise ProfileError(
                "unsupported_contract",
                "无法按报告 schema 识别评审方 provider："
                f"{native_report.get('schema_version')!r}（已注册 schema："
                f"{sorted(s for a in _REGISTRY.values() for s in a.source_report_schemas)}）",
                scope="provider_registry",
            )
    return adapter.build_report(
        native_report=native_report,
        native_coverage=native_coverage,
        identity=identity,
        execution_metadata=execution_metadata,
        usage=usage,
        limitations=limitations,
    )
