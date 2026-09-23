"""Profile 校验层与状态翻译责任层（§15.2、§6.3、§15.4 映射、RC2 §6）。

本模块是 §15.2 所要求的**唯一翻译点**：Profile-aware 适配器必须在 AgentNexus 的
通用状态语义（runner 重试分支、自动签发收据、Loop Engine 状态映射）生效**之前**调用它；
Daemon 入口必须再次调用（不能相信客户端已校验）。

明确禁止（对应评审 P1 与 CP-09/CP-17）：

- 把合法域报告里的 findings 当作"执行失败"触发重跑；
- 让普通文本 stdout 包装出的 ``completed`` 通过（``artifact_type`` 必须是 ``CodeReviewReport``）；
- 接受未知 ``status``（结构不符不得降级为告警，必须硬拒绝）。

本模块不依赖 jsonschema：规范包 ``specs/profiles/code-review/v1/schemas`` 是结构权威，
这里实现的是冻结 schema 中与 CP 直接相关的 MUST 不变式，并在 :data:`INVARIANT_SOURCE`
中登记出处，避免"两套结构定义悄悄漂移"。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .errors import ProfileError

PROFILE_VERSION = "agentnexus.code-review/1.0-draft.2"
REPORT_SCHEMA_VERSION = "code_review.report.v1"
RECEIPT_SCHEMA_VERSION = "code_review.receipt.v1"
ARTIFACT_REF_SCHEMA_VERSION = "code_review.artifact_ref.v1"

#: 冻结 schema 的出处（规范包内）
INVARIANT_SOURCE = "specs/profiles/code-review/v1/schemas/*.schema.json"

#: 消息类型登记表（envelope.schema.json 的 type enum）
MESSAGE_TYPES = (
    "review_request",
    "assignment",
    "assignment_acceptance",
    "delivery",
    "receipt",
    "feedback",
    "publication_request",
    "cancel_request",
    "cancel_acknowledgement",
    "error",
)

#: 本实现支持的 critical extension（当前为空：任何关键扩展都必须拒绝，§3）
SUPPORTED_CRITICAL_EXTENSIONS: frozenset = frozenset()

#: 各类型必须携带的信封 ID 字段
REQUIRED_ENVELOPE_IDS: Dict[str, Tuple[str, ...]] = {
    "review_request": ("request_id",),
    "assignment": ("run_id", "attempt_id", "assignment_epoch"),
    "assignment_acceptance": ("run_id", "attempt_id", "assignment_epoch"),
    "delivery": ("run_id", "attempt_id", "assignment_epoch"),
    "receipt": ("run_id",),
    "feedback": ("run_id",),
    "publication_request": ("run_id",),
    "cancel_request": ("run_id", "assignment_epoch"),
    "cancel_acknowledgement": ("run_id", "attempt_id", "assignment_epoch"),
    "error": (),
}

_ENVELOPE_REQUIRED = (
    "profile",
    "message_id",
    "type",
    "sender_id",
    "receiver_id",
    "session_id",
    "correlation_id",
    "causation_id",
    "created_at",
    "payload",
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

# 严重度映射已迁至 provider_adapter（各评审方自声明词表）：
#   agent_net.code_review.provider_adapter.priority_to_severity

REPORT_REQUIRED = (
    "schema_version",
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
    "coverage",
    "outcome",
    "findings",
    "limitations",
    "execution_metadata",
    "usage",
)

COVERAGE_REQUIRED = (
    "status",
    "planned_files",
    "reviewed_files",
    "omitted_files",
    "gap_reasons",
    "inherited_gaps",
)

OUTCOMES = ("issues_found", "no_findings", "inconclusive")
SEVERITIES = ("critical", "high", "medium", "low")


@dataclass(frozen=True)
class ValidationIssue:
    """一条结构或不变式违规；调用方据此生成 ``invalid_output``。"""

    path: str
    rule: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - 展示用
        return f"{self.path} [{self.rule}] {self.message}"


# ── 信封解析 ──────────────────────────────────────────────────────────


def _no_duplicate_keys(pairs, scope: str = "envelope"):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ProfileError(
                "invalid_output",
                f"JSON 对象含重复键：{key}（§3 要求拒绝重复键）",
                scope=scope,
            )
        seen[key] = value
    return seen

def _reject_constant(name: str, scope: str = "envelope"):
    raise ProfileError(
        "invalid_output",
        f"JSON 含非有限数 {name}（§3 要求拒绝 NaN/Infinity）",
        scope=scope,
    )


def parse_strict_json(raw: Any, *, scope: str = "payload") -> Any:
    """按 §3 严格解析 JSON 载荷（**非**信封也适用）。

    与 :func:`parse_envelope` 共用同一套严格规则，避免"信封严格、其他端点宽松"的
    wire 不一致（复审遗留 P2：上传接口此前用裸 ``json.loads``，重复键与非有限数都放行）：

    - 严格 UTF-8 解码，不做字符替换；
    - **拒绝 BOM**（§1：请求/响应 UTF-8 无 BOM）；
    - 拒绝重复键；
    - 拒绝 ``NaN`` / ``Infinity`` / ``-Infinity``。
    """
    if isinstance(raw, (bytes, bytearray)):
        data = bytes(raw)
        if data.startswith(b"\xef\xbb\xbf"):
            raise ProfileError(
                "invalid_output", "请求体不得带 UTF-8 BOM（§1）", scope=scope
            )
        try:
            raw = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ProfileError(
                "invalid_output",
                f"请求体不是合法 UTF-8：{exc.reason}（§3 要求严格解码，不得替换字符）",
                scope=scope,
            ) from exc

    if isinstance(raw, str):
        try:
            return json.loads(
                raw,
                object_pairs_hook=lambda pairs: _no_duplicate_keys(pairs, scope),
                parse_constant=lambda name: _reject_constant(name, scope),
            )
        except json.JSONDecodeError as exc:
            raise ProfileError(
                "invalid_output", f"请求体不是合法 JSON：{exc.msg}", scope=scope
            ) from exc
    return raw


def parse_envelope(raw: Any) -> Dict[str, Any]:
    """解析并校验协作信封（§3）。返回信封 dict，失败抛 :class:`ProfileError`。

    校验项：严格 UTF-8 解码、拒绝 BOM、拒绝重复键、拒绝 NaN/Infinity、profile 版本、
    消息类型登记表、关键扩展、信封必填字段与按类型必需的 ID 字段。

    解码与"严格 JSON"部分直接复用 :func:`parse_strict_json`，保证信封与其它端点
    （如产物上传）遵守**完全相同**的 §3 规则，不会一个严格一个宽松。
    """
    envelope = parse_strict_json(raw, scope="envelope")

    if not isinstance(envelope, dict):
        raise ProfileError("invalid_output", "信封必须是 JSON 对象", scope="envelope")

    missing = [k for k in _ENVELOPE_REQUIRED if k not in envelope]
    if missing:
        raise ProfileError(
            "invalid_output", f"信封缺少必填字段：{','.join(missing)}", scope="envelope"
        )

    if envelope["profile"] != PROFILE_VERSION:
        raise ProfileError(
            "unsupported_profile",
            f"不支持的 profile 版本：{envelope['profile']}（本部署为 {PROFILE_VERSION}）",
            scope="envelope",
        )

    msg_type = envelope["type"]
    if msg_type not in MESSAGE_TYPES:
        raise ProfileError(
            "invalid_output",
            f"未登记的消息类型：{msg_type}（§3 登记表；不得静默降级）",
            scope="envelope",
        )

    critical = envelope.get("critical_extensions") or []
    unsupported = [c for c in critical if c not in SUPPORTED_CRITICAL_EXTENSIONS]
    if unsupported:
        raise ProfileError(
            "unsupported_critical_extension",
            f"不支持的关键扩展：{','.join(map(str, unsupported))}（§3/§15.8）",
            scope="envelope",
        )

    for key in REQUIRED_ENVELOPE_IDS.get(msg_type, ()):
        if envelope.get(key) in (None, ""):
            raise ProfileError(
                "invalid_output",
                f"{msg_type} 信封缺少 {key}（§3：任务消息必须携带）",
                scope="envelope",
            )

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ProfileError("invalid_output", "信封 payload 必须是 JSON 对象", scope="envelope")
    return envelope


# ── ReviewReport 结构校验（冻结 schema 的关键不变式） ──────────────────


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_review_report(report: Any) -> List[ValidationIssue]:
    """校验 ``code_review.report.v1``；返回违规列表（空列表表示通过）。

    覆盖冻结 schema 中的必填、类型、枚举与 5 条跨字段不变式，以及
    §15.8 的 inherited_gap / usage 规则。**不**做事实正确性判断。
    """
    issues: List[ValidationIssue] = []

    if not isinstance(report, dict):
        return [ValidationIssue("$", "type", "报告必须是 JSON 对象")]

    for key in REPORT_REQUIRED:
        if key not in report:
            issues.append(ValidationIssue(f"$.{key}", "required", "缺少必填字段"))
    if issues:
        return issues

    if report["schema_version"] != REPORT_SCHEMA_VERSION:
        issues.append(
            ValidationIssue("$.schema_version", "const", f"必须是 {REPORT_SCHEMA_VERSION}")
        )

    for key, pattern in (
        ("input_manifest_digest", _DIGEST_RE),
        ("review_policy_sha256", _SHA256_RE),
    ):
        if not isinstance(report[key], str) or not pattern.match(report[key]):
            issues.append(ValidationIssue(f"$.{key}", "format", "格式不符（§3/§15.3）"))

    for key in ("base_sha", "head_sha", "target_sha"):
        if not isinstance(report[key], str) or not _GIT_SHA_RE.match(report[key]):
            issues.append(ValidationIssue(f"$.{key}", "format", "必须是 40/64 位 Git SHA"))

    for key in ("review_revision", "generation", "execution_revision"):
        if not _is_int(report[key]) or report[key] < 1:
            issues.append(ValidationIssue(f"$.{key}", "minimum", "必须是正整数"))

    coverage = report["coverage"]
    if not isinstance(coverage, dict):
        issues.append(ValidationIssue("$.coverage", "type", "必须是对象"))
        coverage = {}
    else:
        for key in COVERAGE_REQUIRED:
            if key not in coverage:
                issues.append(ValidationIssue(f"$.coverage.{key}", "required", "缺少必填字段"))
        status = coverage.get("status")
        if status not in ("complete", "partial"):
            issues.append(
                ValidationIssue("$.coverage.status", "enum", "必须是 complete 或 partial")
            )
        inherited = coverage.get("inherited_gaps")
        if isinstance(inherited, list) and inherited and status != "partial":
            issues.append(
                ValidationIssue(
                    "$.coverage.status",
                    "§15.8/inherited_gap",
                    "存在 inherited_gap 时 coverage 上限为 partial",
                )
            )

    outcome = report["outcome"]
    if outcome not in OUTCOMES:
        issues.append(ValidationIssue("$.outcome", "enum", f"必须是 {'/'.join(OUTCOMES)}"))

    findings = report["findings"]
    if not isinstance(findings, list):
        issues.append(ValidationIssue("$.findings", "type", "必须是数组"))
        findings = []
    else:
        for index, finding in enumerate(findings):
            path = f"$.findings[{index}]"
            if not isinstance(finding, dict):
                issues.append(ValidationIssue(path, "type", "必须是对象"))
                continue
            for key in (
                "finding_id",
                "severity",
                "title",
                "trigger",
                "impact",
                "location",
                "evidence_refs",
                "suggested_validation",
            ):
                if key not in finding:
                    issues.append(ValidationIssue(f"{path}.{key}", "required", "缺少必填字段"))
            if finding.get("severity") not in SEVERITIES:
                issues.append(
                    ValidationIssue(f"{path}.severity", "enum", f"必须是 {'/'.join(SEVERITIES)}")
                )
            refs = finding.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                issues.append(
                    ValidationIssue(f"{path}.evidence_refs", "minItems", "finding 必须带证据引用")
                )

    if findings and outcome != "issues_found":
        issues.append(
            ValidationIssue("$.outcome", "§6.3", "findings 非空必须 issues_found")
        )

    coverage_status = coverage.get("status") if isinstance(coverage, dict) else None
    if outcome == "no_findings":
        if findings:
            issues.append(ValidationIssue("$.findings", "§6.3", "no_findings 要求 findings 为空"))
        if coverage_status != "complete":
            issues.append(
                ValidationIssue("$.coverage.status", "§6.3", "no_findings 要求 coverage=complete")
            )
    if not findings and coverage_status == "partial" and outcome != "inconclusive":
        issues.append(
            ValidationIssue(
                "$.outcome", "§6.3", "无 findings 且 partial 必须 inconclusive（不得显示通过）"
            )
        )

    usage = report["usage"]
    if not isinstance(usage, dict):
        issues.append(ValidationIssue("$.usage", "type", "必须是对象"))
    else:
        measurement = usage.get("measurement")
        if measurement not in ("known", "unknown", "partial"):
            issues.append(
                ValidationIssue("$.usage.measurement", "enum", "必须是 known/unknown/partial")
            )
        if measurement == "unknown":
            for key in ("input_tokens", "output_tokens", "cost"):
                if usage.get(key) is not None:
                    issues.append(
                        ValidationIssue(
                            f"$.usage.{key}",
                            "§6.3",
                            "measurement=unknown 时不得给出用量或成本（不得当作零成本）",
                        )
                    )
        elif measurement == "known":
            for key in ("input_tokens", "output_tokens"):
                if not _is_int(usage.get(key)) or usage.get(key) < 0:
                    issues.append(
                        ValidationIssue(f"$.usage.{key}", "§6.3", "measurement=known 时必须给出用量")
                    )

    impact = report["impact_artifact"]
    if not isinstance(impact, dict):
        issues.append(ValidationIssue("$.impact_artifact", "type", "必须是 ArtifactRef"))
    else:
        for key in (
            "artifact_id",
            "producer_id",
            "media_type",
            "schema_version",
            "digest_algorithm",
            "digest",
            "byte_length",
            "locator",
            "access_scope",
            "retention_until",
        ):
            if key not in impact:
                issues.append(ValidationIssue(f"$.impact_artifact.{key}", "required", "缺少必填字段"))
        if impact.get("digest_algorithm") != "sha256-bytes-v1":
            issues.append(
                ValidationIssue(
                    "$.impact_artifact.digest_algorithm", "enum", "必须是 sha256-bytes-v1"
                )
            )
        if isinstance(impact.get("digest"), str) and not _DIGEST_RE.match(impact["digest"]):
            issues.append(
                ValidationIssue("$.impact_artifact.digest", "format", "必须是 sha256:<64 hex>")
            )
        locator = impact.get("locator")
        if isinstance(locator, str) and re.match(r"^https?://", locator):
            issues.append(
                ValidationIssue(
                    "$.impact_artifact.locator", "§6.1", "locator 不得是任意 http(s) URL"
                )
            )

    return issues


# ── 状态翻译责任层（§15.2） ────────────────────────────────────────────


@dataclass
class TranslationResult:
    """翻译结果。``profile_run_state`` 是 AgentNexus 可写入的状态。"""

    profile_run_state: str
    domain_status: str
    outcome: Optional[str] = None
    requires_human: bool = False
    action_required: bool = False
    issues: List[ValidationIssue] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def translate_agentnexus_result(
    status: str,
    *,
    artifact_type: str = "",
    artifact_body: Optional[str] = None,
    report: Optional[Dict[str, Any]] = None,
    scope: str = "delivery",
) -> TranslationResult:
    """把 ``agentnexus_json_v1`` 结果翻译为 Profile 语义（§15.2 映射表）。

    规则：

    - 未知 ``status`` → ``invalid_output`` 硬拒绝（不得告警后放行）；
    - ``completed``：``artifact_type`` 必须是 ``CodeReviewReport`` 且报告结构通过，
      否则 ``invalid_output``（CP-17：普通文本包装的 completed 不得完成 Run）；
    - ``changes_requested``：**只在**携带合法域报告时归一为 ``completed + issues_found``；
      否则 ``invalid_output``。任何情况下都不得作为"重跑评审"的信号（CP-09）；
    - ``failed``：镜像失败，由 Coordinator 按错误码决定后续；
    - ``blocked``：映射为 ``failed`` + ``requires_human``（可生成 DecisionGate），
      不新增 Profile 状态，人工同意也不复活原 Run。
    """
    if status not in ("completed", "changes_requested", "failed", "blocked"):
        raise ProfileError(
            "invalid_output",
            f"未知 status：{status!r}（§15.2：硬拒绝，不得告警后放行）",
            scope=scope,
        )

    if status in ("completed", "changes_requested"):
        if artifact_type != "CodeReviewReport":
            raise ProfileError(
                "invalid_output",
                f"artifact_type 必须是 CodeReviewReport（实际 {artifact_type or '空'}）；"
                "普通文本或 wrapper 包装的 completed 不得完成 Run（CP-17）",
                scope=scope,
            )
        if report is None:
            raise ProfileError(
                "invalid_output",
                "缺少 ReviewReport 本体；适配成功不等于通过本 Profile 校验（§6.4）",
                scope=scope,
            )
        issues = validate_review_report(report)
        if issues:
            first = issues[0]
            raise ProfileError(
                "invalid_output",
                f"ReviewReport 结构不合法：{first}",
                scope=scope,
                extra={"violations": [str(i) for i in issues]},
            )
        outcome = report["outcome"]
        return TranslationResult(
            profile_run_state="completed",
            domain_status="completed" if status == "completed" else "changes_requested",
            outcome=outcome,
            notes=[
                "changes_requested 已归一为 completed+域内结论，不触发评审重跑（§15.2）"
            ]
            if status == "changes_requested"
            else [],
        )

    if status == "failed":
        return TranslationResult(profile_run_state="failed", domain_status="failed")

    return TranslationResult(
        profile_run_state="failed",
        domain_status="blocked",
        requires_human=True,
        action_required=True,
        notes=["blocked 映射为 failed + 人工介入；人工同意不复活原 Run（§15.2）"],
    )
