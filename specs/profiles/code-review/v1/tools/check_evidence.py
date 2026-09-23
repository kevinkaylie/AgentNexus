#!/usr/bin/env python3
"""T1–T6 关闭证据校验（Code Review Collaboration Profile v1 / L0 binding RC2）。

用法（任意目录）：
    python specs/profiles/code-review/v1/tools/check_evidence.py

本脚本只做一件事：把「T1–T6 关了没有」从自述变成可重算的事实。

  * 模板完整性：closure-checklist.json 里每条证据都要有模板文件与对应 record key；
  * 摘要重算：任何 base64 原始字节都重算 sha256 与 byte_length，与声明值比对；
  * 虚假关闭拒绝：声明 closed 的 T 项若缺required 字段、残留 __TODO__、缺部署版本或
    缺拒绝例，直接失败——不允许改声明迁就实际；
  * 提前放行拒绝：T1–T6 未全部关闭时，compatibility.json 必须保持默认拒绝、
    operative_allowlist=false、artifact_access_scope=[]。

退出码：0=清单自洽（开放是合法状态）；1=不一致、虚假关闭或提前放行；
2=清单/模板本身缺失或损坏。本脚本不判断证据内容的业务正确性，也不声明 wire conformance。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parent.parent
# BASE == <repo>/specs/profiles/code-review/v1，因此仓库根目录是它的第 4 级父目录。
# 独立成模块级常量，便于测试在临时目录里替换整个根。
REPO_ROOT = BASE.parents[3]
EVIDENCE = BASE / "bindings" / "evidence"
CHECKLIST = EVIDENCE / "closure-checklist.json"
TEMPLATES = EVIDENCE / "templates"
RECEIVED = EVIDENCE / "received"
COMPATIBILITY = BASE / "compatibility.json"

PLACEHOLDER = "__TODO__"
RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
METHOD_PREFIX_RE = re.compile(r"^(get|post|put|patch|delete)\s+", re.IGNORECASE)
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "[::1]", "localhost"}

# 已知的检查名；清单里出现未登记的名字必须失败，避免拼写错误被静默放过。
KNOWN_CHECKS = {
    "no_placeholder",
    "sample_bytes",
    "loopback_url",
    "rfc3339",
    "scan_succeeded_fields",
    "unknown_behavior_must_refuse",
    "covers_endpoints",
    "artifact_digest_matches_raw",
    "etag_matches_digest",
    "content_length_matches",
    "report_digest_matches_manifest",
    "media_type_is_json",
    "divergence_stated",
    "line_vector_bytes",
    "locator_shape",
    "must_refuse_when_unconfigured",
    "not_admin_session",
    "conflict_samples_present",
    "covers_labels",
    "restart_stability_evidenced",
    "transport_ack_shape",
    "covers_receipt_kinds",
    "forged_receipt_refused",
    "worker_refusal_evidenced",
    "unique_key_declared",
    "covers_publication_states",
    "summary_text_not_executed",
    "note_id_recorded",
    "no_forbidden_operations",
    "note_count_unchanged",
    "vocabulary_has_service_private",
    "three_party_attested",
    "allowlist_only_after_closure",
    "severity_covers_p0_p3_and_unknown",
    "outcome_quadrants_present",
    "unknown_severity_refused",
}

SAMPLE_LIST_KEYS = ("samples", "replay_samples", "fixtures", "vectors")

# B9：拒绝事实必须来自样例，而不是布尔或文字。契约 §7：401/403 → authority_denied /
# data_policy_denied（后者带 scope=policy）。允许的拒绝码在此集中声明。
REFUSAL_STATUSES = frozenset({401, 403})
REFUSAL_CODES = frozenset({"authority_denied", "data_policy_denied"})

#: 评审 R2-6：每个拒绝用例必须绑定**具体场景**——谁被拒、对哪个方法/端点、期望何种拒绝。
#: 上一版只要求"有样例 + 401/403 + 码在枚举里"，无关的 403 也能伪造通过（复现：
#: subject=unrelated-admin、endpoint=GET /unrelated/health、正文 schema=not-an-error-schema
#: 且 retryable="yes"、scope=123、retry_after_seconds=-99，仍判"通过、failures=[]"）。
REFUSAL_EXPECTATIONS = {
    "unconfigured_refused": {
        "subject_roles": ("unconfigured", "anonymous"),
        "endpoints": (),
        "codes": ("authority_denied",),
    },
    "role_violation_refused": {
        "subject_roles": ("worker", "requester"),
        "endpoints": (),
        "codes": ("authority_denied", "data_policy_denied"),
    },
    "admin_session_refused": {
        "subject_roles": ("admin", "operator"),
        "endpoints": (),
        "codes": ("authority_denied",),
    },
    "forged_receipt_rejected": {
        "subject_roles": ("worker",),
        "endpoints": ("POST A/messages", "POST H/messages"),
        "codes": ("authority_denied", "data_policy_denied"),
    },
    "worker_publish_refused": {
        "subject_roles": ("worker",),
        "endpoints": ("POST H/publications",),
        "codes": ("authority_denied", "data_policy_denied"),
    },
}

ERROR_SCHEMA = None  # 懒加载缓存：(path, codes, required_fields, validator)


class Fatal(Exception):
    """清单或模板本身损坏，无法校验。"""


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Fatal(f"缺少文件：{path}")
    except json.JSONDecodeError as exc:
        raise Fatal(f"{path} 不是合法 JSON：{exc}")


def is_placeholder(value) -> bool:
    return isinstance(value, str) and PLACEHOLDER in value


def has_placeholder(value) -> bool:
    if isinstance(value, str):
        return PLACEHOLDER in value
    if isinstance(value, dict):
        return any(has_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(has_placeholder(v) for v in value)
    return False


def placeholder_paths(value, prefix: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        if PLACEHOLDER in value:
            out.append(prefix or "<root>")
    elif isinstance(value, dict):
        for key, item in value.items():
            out.extend(placeholder_paths(item, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            out.extend(placeholder_paths(item, f"{prefix}[{index}]"))
    return out


def sample_list(record: dict):
    for key in SAMPLE_LIST_KEYS:
        if isinstance(record.get(key), list):
            return key, record[key]
    return None, []


def normalize_endpoint(value) -> str:
    if not isinstance(value, str):
        return ""
    return METHOD_PREFIX_RE.sub("", value.strip()).strip()


def decode_b64(value, where: str, failures: list[str]):
    if not isinstance(value, str) or is_placeholder(value):
        failures.append(f"{where}: 缺少可校验的 base64 原始字节")
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        failures.append(f"{where}: base64 解码失败（{exc}）")
        return None


def verify_payload(container: dict, b64_key: str, where: str, failures: list[str], digest) -> None:
    """重算 *_bytes_b64 的 sha256 与 byte_length，与同名前缀的声明值比对。"""
    raw = decode_b64(container.get(b64_key), f"{where}.{b64_key}", failures)
    if raw is None:
        return
    prefix = b64_key[: -len("_bytes_b64")]
    sha_key = f"{prefix}_sha256" if f"{prefix}_sha256" in container else "sha256"
    len_key = f"{prefix}_byte_length" if f"{prefix}_byte_length" in container else "byte_length"
    actual_sha = "sha256:" + digest(raw).hexdigest()
    declared_sha = container.get(sha_key)
    if not isinstance(declared_sha, str) or not SHA256_RE.match(declared_sha):
        failures.append(f"{where}.{sha_key}: 不是 sha256:<64 位小写十六进制>")
    elif declared_sha != actual_sha:
        failures.append(f"{where}.{b64_key}: 摘要不符，声明 {declared_sha}，实际 {actual_sha}")
    if len_key in container:
        declared_len = container.get(len_key)
        if declared_len != len(raw):
            failures.append(f"{where}.{len_key}: 长度不符，声明 {declared_len}，实际 {len(raw)}")


def scan_b64_payloads(value, where: str, failures: list[str], digest) -> None:
    """递归校验记录中所有 *_bytes_b64 字段（含 samples 内的 raw_bytes_b64）。"""
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{where}.{key}"
            if key.endswith("_bytes_b64"):
                verify_payload(value, key, where, failures, digest)
            else:
                scan_b64_payloads(item, child, failures, digest)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_b64_payloads(item, f"{where}[{index}]", failures, digest)


# --------------------------------------------------------------------------- 检查项


def check_loopback_url(record, spec, where, failures, actuals):
    url = record.get("endpoint_base_url")
    if not isinstance(url, str) or is_placeholder(url):
        failures.append(f"{where}.endpoint_base_url: 缺少部署 base URL")
        return
    host = urlsplit(url).hostname
    if host not in LOOPBACK_HOSTS:
        failures.append(f"{where}.endpoint_base_url: 不是 loopback（host={host!r}）；0.0.0.0 不能自动认定 L0")


def check_rfc3339(record, spec, where, failures, actuals):
    for key in ("captured_at", "decided_at", "freeze_date", "attested_at", "observed_at"):
        if key not in record:
            continue
        value = record.get(key)
        if not isinstance(value, str) or not RFC3339_RE.match(value):
            failures.append(f"{where}.{key}: 期望 RFC3339 Z，实际 {value!r}")


def check_scan_succeeded_fields(record, spec, where, failures, actuals):
    _, samples = sample_list(record)
    candidate = next((s for s in samples if s.get("case") == "scan_succeeded_event"), None)
    if candidate is None:
        failures.append(f"{where}: 缺 scan_succeeded_event 样例")
        return
    if candidate.get("event_schema") != "nexus.review_event.v1":
        failures.append(f"{where}.scan_succeeded_event: event_schema 应为 nexus.review_event.v1")
    for key in ("job_id", "report_id", "generation", "execution_revision"):
        if not candidate.get(key) or is_placeholder(candidate.get(key)):
            failures.append(f"{where}.scan_succeeded_event: 缺 {key}（scan.succeeded 必备字段）")


def check_unknown_behavior_must_refuse(record, spec, where, failures, actuals):
    allowed = record.get("allowed_values")
    if not isinstance(allowed, list) or not allowed:
        failures.append(f"{where}.allowed_values: 必须是显式的非空允许值清单")
    behavior = record.get("unknown_value_behavior")
    if not isinstance(behavior, str) or is_placeholder(behavior):
        failures.append(f"{where}.unknown_value_behavior: 必须写明未知值处理方式")
    elif not any(token in behavior for token in ("拒绝", "unsupported_contract", "reject")):
        failures.append(f"{where}.unknown_value_behavior: 必须明确拒绝，不得猜测字段兼容")


def check_covers_endpoints(record, spec, where, failures, actuals):
    required = spec.get("required_endpoint_coverage") or []
    if not required:
        return
    _, samples = sample_list(record)
    present = {normalize_endpoint(s.get("endpoint")) for s in samples}
    for endpoint in required:
        if normalize_endpoint(endpoint) not in present:
            failures.append(f"{where}: 未覆盖端点 {endpoint}")


def check_artifact_digest_matches_raw(record, spec, where, failures, actuals):
    _, samples = sample_list(record)
    artifact = next((s for s in samples if s.get("case") == "artifact_ref"), None)
    raw = next((s for s in samples if s.get("case") == "raw_report_bytes"), None)
    if artifact is None or raw is None:
        failures.append(f"{where}: 需要 artifact_ref 与 raw_report_bytes 两个样例")
        return
    if artifact.get("artifact_ref_digest") != raw.get("sha256"):
        failures.append(f"{where}: ArtifactRef.digest 与 /raw 的 sha256 不一致")
    if artifact.get("artifact_ref_byte_length") != raw.get("byte_length"):
        failures.append(f"{where}: ArtifactRef.byte_length 与 /raw 的 byte_length 不一致")


def check_etag_matches_digest(record, spec, where, failures, actuals):
    _, samples = sample_list(record)
    raw = next((s for s in samples if s.get("case") == "raw_report_bytes"), None)
    if raw is None:
        return
    etag = raw.get("etag")
    expected = raw.get("sha256")
    if not isinstance(etag, str) or etag.strip('"') != expected:
        failures.append(f"{where}: ETag 必须等于 \"{expected}\"，实际 {etag!r}")


def check_content_length_matches(record, spec, where, failures, actuals):
    _, samples = sample_list(record)
    raw = next((s for s in samples if s.get("case") == "raw_report_bytes"), None)
    if raw is None:
        return
    if raw.get("content_length") != raw.get("byte_length"):
        failures.append(f"{where}: Content-Length 必须精确等于 byte_length")


def check_report_digest_matches_manifest(record, spec, where, failures, actuals):
    if record.get("sha256") != record.get("manifest_report_sha256"):
        failures.append(f"{where}: 持久化报告摘要与 manifest.report_sha256 不一致")
    payload = decode_b64(record.get("manifest_sample_raw_bytes_b64"), f"{where}.manifest_sample", failures)
    if payload is None:
        return
    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        failures.append(f"{where}.manifest_sample_raw_bytes_b64: 不是合法 UTF-8 JSON（{exc}）")
        return
    values = {v for v in manifest.values() if isinstance(v, str)} if isinstance(manifest, dict) else set()
    if record.get("manifest_report_sha256") not in values:
        failures.append(f"{where}: manifest 样例中找不到 report_sha256 的观测值")


def check_media_type_is_json(record, spec, where, failures, actuals):
    if record.get("media_type") != "application/json":
        failures.append(f"{where}.media_type: 期望 application/json，实际 {record.get('media_type')!r}")


def check_divergence_stated(record, spec, where, failures, actuals):
    if not isinstance(record.get("same_caliber"), bool):
        failures.append(f"{where}.same_caliber: 必须显式声明 GET 字节与持久化字节是否同一口径")
    explanation = record.get("explanation")
    if not isinstance(explanation, str) or is_placeholder(explanation) or not explanation.strip():
        failures.append(f"{where}.explanation: 必须给出差异或相同口径的说明")


def check_line_vector_bytes(record, spec, where, failures, actuals):
    vectors = record.get("vectors")
    if not isinstance(vectors, list) or not vectors:
        failures.append(f"{where}.vectors: 缺行边界向量")
        return
    for vector in vectors:
        case = vector.get("case")
        if case == "out_of_range":
            payload = decode_b64(vector.get("response_bytes_b64"), f"{where}.{case}.response", failures)
            if payload is None:
                continue
            if vector.get("expected_status") != 422:
                failures.append(f"{where}.{case}: 越界必须返回 422")
            if vector.get("expected_error_code") != "input_mismatch":
                failures.append(f"{where}.{case}: 期望错误码 input_mismatch")
            continue
        payload = decode_b64(vector.get("expected_bytes_b64"), f"{where}.{case}.expected", failures)
        if payload is None:
            continue
        expected_sha = vector.get("expected_sha256")
        actual_sha = "sha256:" + hashlib.sha256(payload).hexdigest()
        if expected_sha != actual_sha:
            failures.append(f"{where}.{case}: 期待字节摘要不符，声明 {expected_sha}，实际 {actual_sha}")
        if vector.get("expected_byte_length") != len(payload):
            failures.append(f"{where}.{case}: 期待字节长度不符")


def check_locator_shape(record, spec, where, failures, actuals):
    template = record.get("locator_template")
    if not isinstance(template, str) or not template.startswith("nexus-report:") or "<provider_id>" not in template or "<report_id>" not in template:
        failures.append(f"{where}.locator_template: 期望 nexus-report:<provider_id>:<report_id> 形态")
    if record.get("access_scope") != "service_private":
        failures.append(f"{where}.access_scope: 当前仅候选值 service_private 可用")


def check_must_refuse_when_unconfigured(record, spec, where, failures, actuals):
    """缺配置必须拒绝：文本只是说明，**拒绝事实必须有样例**（B9）。

    评审确认过反例：`unconfigured_behavior` 写 "does not reject; allows requests"
    因含 "reject" 字样而通过——因此这里不再以文字为判据。
    """
    behavior = record.get("unconfigured_behavior")
    if not isinstance(behavior, str) or is_placeholder(behavior) or not behavior.strip():
        failures.append(f"{where}.unconfigured_behavior: 必须写明未配置凭据时的拒绝行为（说明性字段）")
    require_refusal_cases(record, ["unconfigured_refused"], where, failures)


def check_not_admin_session(record, spec, where, failures, actuals):
    value = record.get("admin_session_separation")
    if not isinstance(value, str) or is_placeholder(value) or not value.strip():
        failures.append(f"{where}.admin_session_separation: 必须给出 Admin Cookie/CSRF 无法调用服务接口的实证")


def check_conflict_samples_present(record, spec, where, failures, actuals):
    _, samples = sample_list(record)
    if not any(isinstance(s.get("response_status"), int) and s.get("response_status") >= 400 for s in samples):
        failures.append(f"{where}: 缺冲突/拒绝样例（至少一个 4xx）")


def check_covers_labels(record, spec, where, failures, actuals):
    fixtures = record.get("fixtures")
    if not isinstance(fixtures, list):
        failures.append(f"{where}.fixtures: 缺标签映射 fixture")
        return
    labels = {f.get("label") for f in fixtures}
    for label in ("offered", "accepted", "running", "completed", "rejected", "cancelled"):
        if label not in labels:
            failures.append(f"{where}: 缺标签 {label}")
    expired = {f.get("case") for f in fixtures if str(f.get("label", "")).startswith("expired")}
    if len(expired) < 3:
        failures.append(f"{where}: expired 至少需要 deadline/lease_only/superseded 三种差异化去向")


def check_restart_stability_evidenced(record, spec, where, failures, actuals):
    samples = record.get("restart_stability_samples")
    if not isinstance(samples, list) or len(samples) < 2:
        failures.append(f"{where}.restart_stability_samples: 需要重启前后两次采样")
        return
    ids = {s.get("coordinator_id") for s in samples}
    if len(ids) != 1 or None in ids:
        failures.append(f"{where}: 重启前后 coordinator_id 必须相同，实际 {ids}")


def load_error_contract():
    """读取冻结的 error.schema.json：枚举、必填字段**与可执行 validator**（评审 R2-6）。

    上一版只读 ``enum``/``required`` 并手写"键是否存在"的检查，于是
    ``schema=not-an-error-schema``、``retryable="yes"``、``scope=123``、
    ``retry_after_seconds=-99`` 全都漏过。这里必须真正跑 schema（含类型、const、
    additionalProperties 与 allOf 不变式）。

    以路径为键缓存，避免测试重定向 BASE 后拿到上一个包的契约。
    """
    global ERROR_SCHEMA
    path = BASE / "schemas" / "error.schema.json"
    if ERROR_SCHEMA is not None and ERROR_SCHEMA[0] == path:
        return ERROR_SCHEMA[1], ERROR_SCHEMA[2], ERROR_SCHEMA[3]

    codes, required, validator = frozenset(), (), None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        codes = frozenset(doc["properties"]["code"]["enum"])
        required = tuple(doc["required"])
    except (OSError, KeyError, json.JSONDecodeError):
        ERROR_SCHEMA = (path, codes, required, None)
        return codes, required, None

    try:  # pragma: no cover - 依赖缺失时退化为"无法验证"，由调用方判失败
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource

        resources = []
        for schema_path in sorted((BASE / "schemas").glob("*.schema.json")):
            try:
                other = json.loads(schema_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if other.get("$id"):
                resources.append((other["$id"], Resource.from_contents(other)))
        registry = Registry().with_resources(resources)
        validator = Draft202012Validator(
            doc, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER
        )
    except ImportError:
        validator = None

    ERROR_SCHEMA = (path, codes, required, validator)
    return codes, required, validator


def decoded_json(container: dict, b64_key: str, where: str, failures: list[str]):
    payload = decode_b64(container.get(b64_key), f"{where}.{b64_key}", failures)
    if payload is None:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        failures.append(f"{where}.{b64_key}: 不是合法 UTF-8 JSON（{exc}）")
        return None


def verify_refusal_sample(sample: dict, case: str, where: str, failures: list[str]) -> bool:
    """样例级校验一条拒绝事实（B9 + 评审 R2-6）。

    必须同时满足：

    1. 记录了被拒**主体**与**方法+端点**，且与该拒绝场景的期望一致
       （``REFUSAL_EXPECTATIONS``；未登记期望的用例直接失败，避免出现无法验证的检查）；
    2. ``response_status`` ∈ {401,403}；
    3. 原始字节能解码，且**真正通过冻结 ``error.schema.json``**（类型、const、
       additionalProperties、allOf 不变式都会检查）；
    4. 错误码在冻结枚举内且属于该场景允许的码。
    """
    before = len(failures)
    if not isinstance(sample, dict):
        failures.append(f"{where}: 拒绝样例必须是对象")
        return False

    expectation = REFUSAL_EXPECTATIONS.get(case)
    if expectation is None:
        failures.append(f"{where}: 拒绝用例 {case!r} 未登记场景期望，无法验证拒绝事实")
        return False

    subject = sample.get("subject")
    if not isinstance(subject, str) or not subject.strip() or is_placeholder(subject):
        failures.append(f"{where}.subject: 拒绝样例必须记录被拒主体")
    else:
        lowered = subject.lower()
        if not any(role in lowered for role in expectation["subject_roles"]):
            failures.append(
                f"{where}.subject: 主体与拒绝场景不符（期望涉及 "
                f"{list(expectation['subject_roles'])}，实际 {subject!r}）"
            )

    endpoint = sample.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip() or is_placeholder(endpoint):
        failures.append(f"{where}.endpoint: 拒绝样例必须记录方法+端点")
    elif expectation["endpoints"]:
        actual = normalize_endpoint(endpoint)
        allowed = {normalize_endpoint(e) for e in expectation["endpoints"]}
        if actual not in allowed:
            failures.append(
                f"{where}.endpoint: 端点与拒绝场景不符（期望 {sorted(allowed)}，实际 {actual!r}）"
            )

    status = sample.get("response_status")
    if status not in REFUSAL_STATUSES:
        failures.append(f"{where}.response_status: 拒绝样例必须是 401/403，实际 {status!r}")

    doc = decoded_json(sample, "raw_bytes_b64", where, failures)
    if doc is None:
        return False

    codes, required, validator = load_error_contract()
    if validator is None:
        failures.append(
            f"{where}: 无法加载冻结 error.schema.json 的 validator，拒绝证据不可验证"
        )
        return False

    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(
            f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors[:5]
        )
        failures.append(f"{where}: 拒绝响应未通过冻结 error.schema.json —— {detail}")
    if not isinstance(doc, dict):
        return False

    missing = [key for key in required if key not in doc]
    if missing:
        failures.append(f"{where}: 拒绝响应不是冻结错误信封，缺字段 {missing}")
    code = doc.get("code")
    if codes and code not in codes:
        failures.append(f"{where}: 错误码 {code!r} 不在冻结 error.schema.json 枚举内")
    elif code not in expectation["codes"]:
        failures.append(
            f"{where}: 该场景的错误码应为 {list(expectation['codes'])}，实际 {code!r}"
        )
    declared = sample.get("expected_error_code")
    if declared is not None and not is_placeholder(declared) and declared != code:
        failures.append(f"{where}: 声明的错误码 {declared!r} 与实际 {code!r} 不一致")
    return len(failures) == before


def require_refusal_cases(record: dict, cases, where: str, failures: list[str]) -> None:
    """要求 record 的 refusal_samples（或 samples）中存在并实际证成指定的拒绝用例。"""
    pools = []
    for key in ("refusal_samples", "samples"):
        if isinstance(record.get(key), list):
            pools.append((key, record[key]))
    if not pools:
        failures.append(f"{where}: 缺 refusal_samples（拒绝事实必须有样例，不能只写布尔或文字）")
        return
    for case in cases:
        found = None
        for key, entries in pools:
            found = next((s for s in entries if isinstance(s, dict) and s.get("case") == case), None)
            if found is not None:
                break
        if found is None:
            failures.append(f"{where}: 缺拒绝用例 {case}")
            continue
        verify_refusal_sample(found, case, f"{where}.{case}", failures)


def check_transport_ack_shape(record, spec, where, failures, actuals):
    _, samples = sample_list(record)
    checked = 0
    for sample in samples:
        if sample.get("response_status") != 202:
            continue
        payload = sample.get("raw_bytes_b64")
        if not isinstance(payload, str) or is_placeholder(payload):
            continue
        try:
            doc = json.loads(base64.b64decode(payload, validate=True).decode("utf-8"))
        except Exception:
            failures.append(f"{where}.{sample.get('case')}: 202 样例不是合法 UTF-8 JSON")
            continue
        if isinstance(doc, dict):
            missing = [k for k in ("message_id", "status", "status_url") if k not in doc]
            if missing:
                failures.append(f"{where}.{sample.get('case')}: TransportAck 缺字段 {missing}")
            elif doc.get("status") != "stored":
                failures.append(f"{where}.{sample.get('case')}: TransportAck.status 应为 stored")
            checked += 1
    if checked == 0:
        failures.append(f"{where}: 缺可解析的 202 TransportAck 样例")


def check_covers_receipt_kinds(record, spec, where, failures, actuals):
    kinds = record.get("covers_receipt_kinds")
    required = {"received", "validated", "accepted", "published"}
    if not isinstance(kinds, list) or not required.issubset(set(kinds)):
        failures.append(f"{where}.covers_receipt_kinds: 必须覆盖 {sorted(required)}")
    if "receipt_kind_to_role" not in record or has_placeholder(record.get("receipt_kind_to_role")):
        failures.append(f"{where}.receipt_kind_to_role: 缺签发主体与角色路由说明")


def check_forged_receipt_refused(record, spec, where, failures, actuals):
    """worker 自带 receipt/issuer_did/signature 不赋权：必须以拒绝样例证明（B9）。"""
    require_refusal_cases(record, ["forged_receipt_rejected"], where, failures)


def check_worker_refusal_evidenced(record, spec, where, failures, actuals):
    """worker 无发布权限：必须以拒绝样例证明（B9）。"""
    require_refusal_cases(record, ["worker_publish_refused"], where, failures)


def check_unique_key_declared(record, spec, where, failures, actuals):
    if record.get("unique_key_declared") is not True:
        failures.append(f"{where}.unique_key_declared: 必须逐表声明唯一键")
    for key in ("same_transaction_proof", "crash_recovery_sample"):
        value = record.get(key)
        if not isinstance(value, str) or is_placeholder(value) or not value.strip():
            failures.append(f"{where}.{key}: 缺同事务/崩溃恢复证据")


def check_covers_publication_states(record, spec, where, failures, actuals):
    _, samples = sample_list(record)
    cases = {s.get("case") for s in samples}
    for case in ("published", "unknown", "obsolete"):
        if case not in cases:
            failures.append(f"{where}: 缺 {case} 状态样例")


def check_summary_text_not_executed(record, spec, where, failures, actuals):
    value = record.get("summary_text_not_executed")
    if not isinstance(value, str) or is_placeholder(value) or not value.strip():
        failures.append(f"{where}.summary_text_not_executed: 必须说明正文由服务端生成、不一致的 summary_text 被拒")


def check_note_id_recorded(record, spec, where, failures, actuals):
    _, samples = sample_list(record)
    create = next((s for s in samples if s.get("case") == "create_note"), None)
    if create is None:
        failures.append(f"{where}: 缺 create_note 样例")
        return
    note_id = create.get("note_id")
    if not isinstance(note_id, int) or note_id <= 0:
        failures.append(f"{where}.create_note.note_id: 必须记录正整数响应 id")


def check_no_forbidden_operations(record, spec, where, failures, actuals):
    if record.get("no_forbidden_operations") is not True:
        failures.append(f"{where}.no_forbidden_operations: 必须为 true（不得出现 approve/merge/执行正文命令）")


def check_note_count_unchanged(record, spec, where, failures, actuals):
    before, after = record.get("note_count_before"), record.get("note_count_after")
    if not isinstance(before, int) or not isinstance(after, int) or before != after:
        failures.append(f"{where}: 重放前后评论数必须相同（before={before!r}, after={after!r}）")


def check_vocabulary_has_service_private(record, spec, where, failures, actuals):
    vocabulary = record.get("vocabulary")
    if not isinstance(vocabulary, list):
        failures.append(f"{where}.vocabulary: 必须是列表")
    elif vocabulary and "service_private" not in vocabulary:
        failures.append(f"{where}.vocabulary: 非空词表必须包含已评审的 service_private")
    if record.get("vocabulary_has_service_private") is not True:
        failures.append(f"{where}.vocabulary_has_service_private: 必须为 true")


def check_three_party_attested(record, spec, where, failures, actuals):
    if record.get("three_party_attested") is not True:
        failures.append(f"{where}.three_party_attested: 冻结必须三方签署")
    attestations = record.get("attestations")
    if not isinstance(attestations, list):
        failures.append(f"{where}.attestations: 缺签署记录")
        return
    parties = {a.get("party") for a in attestations}
    for party in ("AgentNexus", "Nexus_Agent", "Hczj_Assistant_Agent"):
        if party not in parties:
            failures.append(f"{where}.attestations: 缺 {party} 签署")
    for attestation in attestations:
        if not attestation.get("attested_by") or has_placeholder(attestation.get("attested_by")):
            failures.append(f"{where}.attestations[{attestation.get('party')}]: 缺签署主体")


def check_allowlist_only_after_closure(record, spec, where, failures, actuals):
    if record.get("allowlist_only_after_closure") is not True:
        failures.append(f"{where}.allowlist_only_after_closure: 必须确认放行发生在 T1–T6 全部关闭之后")


def check_severity_covers_p0_p3_and_unknown(record, spec, where, failures, actuals):
    fixtures = record.get("severity_fixtures")
    if not isinstance(fixtures, list):
        failures.append(f"{where}.severity_fixtures: 缺 severity 映射 fixture")
        return
    pairs = {(f.get("native"), f.get("profile")) for f in fixtures}
    for native, profile in (("P0", "critical"), ("P1", "high"), ("P2", "medium"), ("P3", "low")):
        if (native, profile) not in pairs:
            failures.append(f"{where}: 缺映射 {native}->{profile}")
    if not any(f.get("profile") is None for f in fixtures):
        failures.append(f"{where}: 缺未知值（profile 必须为 null 并被拒绝）的 fixture")
    if record.get("severity_covers_p0_p3_and_unknown") is not True:
        failures.append(f"{where}.severity_covers_p0_p3_and_unknown: 必须为 true")


def check_unknown_severity_refused(record, spec, where, failures, actuals):
    if record.get("unknown_severity_refused") is not True:
        failures.append(f"{where}.unknown_severity_refused: 未知 severity 必须拒绝，不得降为 low")
    value = record.get("unknown_value_refusal")
    if not isinstance(value, str) or is_placeholder(value) or not value.strip():
        failures.append(f"{where}.unknown_value_refusal: 缺未知值拒绝证据")
    fixtures = record.get("severity_fixtures") or []
    unknown = next((f for f in fixtures if f.get("profile") is None), None)
    if unknown is not None and unknown.get("expected_error_code") != "invalid_output":
        failures.append(f"{where}: 未知 severity 的期望错误码应为 invalid_output")


def check_outcome_quadrants_present(record, spec, where, failures, actuals):
    fixtures = record.get("outcome_coverage_fixtures")
    if not isinstance(fixtures, list):
        failures.append(f"{where}.outcome_coverage_fixtures: 缺 outcome/coverage 四象限 fixture")
        return
    cases = {f.get("case") for f in fixtures}
    for case in (
        "findings_present_with_full_coverage",
        "no_findings_full_coverage",
        "no_findings_partial_coverage",
        "findings_with_coverage_gap",
        "inherited_gap_caps_coverage",
    ):
        if case not in cases:
            failures.append(f"{where}: 缺用例 {case}")
    if record.get("outcome_quadrants_present") is not True:
        failures.append(f"{where}.outcome_quadrants_present: 必须为 true")


CHECKS = {
    "loopback_url": check_loopback_url,
    "rfc3339": check_rfc3339,
    "scan_succeeded_fields": check_scan_succeeded_fields,
    "unknown_behavior_must_refuse": check_unknown_behavior_must_refuse,
    "covers_endpoints": check_covers_endpoints,
    "artifact_digest_matches_raw": check_artifact_digest_matches_raw,
    "etag_matches_digest": check_etag_matches_digest,
    "content_length_matches": check_content_length_matches,
    "report_digest_matches_manifest": check_report_digest_matches_manifest,
    "media_type_is_json": check_media_type_is_json,
    "divergence_stated": check_divergence_stated,
    "line_vector_bytes": check_line_vector_bytes,
    "locator_shape": check_locator_shape,
    "must_refuse_when_unconfigured": check_must_refuse_when_unconfigured,
    "not_admin_session": check_not_admin_session,
    "conflict_samples_present": check_conflict_samples_present,
    "covers_labels": check_covers_labels,
    "restart_stability_evidenced": check_restart_stability_evidenced,
    "transport_ack_shape": check_transport_ack_shape,
    "covers_receipt_kinds": check_covers_receipt_kinds,
    "forged_receipt_refused": check_forged_receipt_refused,
    "worker_refusal_evidenced": check_worker_refusal_evidenced,
    "unique_key_declared": check_unique_key_declared,
    "covers_publication_states": check_covers_publication_states,
    "summary_text_not_executed": check_summary_text_not_executed,
    "note_id_recorded": check_note_id_recorded,
    "no_forbidden_operations": check_no_forbidden_operations,
    "note_count_unchanged": check_note_count_unchanged,
    "vocabulary_has_service_private": check_vocabulary_has_service_private,
    "three_party_attested": check_three_party_attested,
    "allowlist_only_after_closure": check_allowlist_only_after_closure,
    "severity_covers_p0_p3_and_unknown": check_severity_covers_p0_p3_and_unknown,
    "unknown_severity_refused": check_unknown_severity_refused,
    "outcome_quadrants_present": check_outcome_quadrants_present,
}


# --------------------------------------------------------------------------- 记录校验


def coverage_values(entries, field: str) -> set:
    return {e.get(field) for e in entries if isinstance(e, dict)}


def check_record(record: dict, spec: dict, where: str, failures: list[str]) -> bool:
    """校验一条声明 closed 的证据记录。返回是否通过（不计入 failures 数量的纯判定用）。"""
    before = len(failures)
    if not isinstance(record, dict):
        failures.append(f"{where}: 记录必须是对象")
        return False

    if has_placeholder(record):
        failures.append(f"{where}: 声明 closed 但仍残留占位符 {placeholder_paths(record)[:5]}")
        return False

    for field in spec.get("required_fields", []):
        value = record.get(field)
        if value is None or (isinstance(value, (str, list, dict)) and not value):
            failures.append(f"{where}.{field}: closed 记录缺必需字段")

    checks = spec.get("checks", [])
    for name in checks:
        if name in ("no_placeholder", "sample_bytes"):
            continue  # 由上面的通用规则与摘要重算覆盖
        fn = CHECKS.get(name)
        if fn is None:
            failures.append(f"{where}: 清单声明了未登记的检查名 {name!r}")
            continue
        fn(record, spec, where, failures, {})

    # 通用结构规则：不论是否声明 sample_bytes，所有 base64 载荷都必须可重算。
    scan_b64_payloads(record, where, failures, hashlib.sha256)

    key, entries = sample_list(record)
    min_samples = spec.get("min_samples")
    if min_samples and len(entries) < min_samples:
        failures.append(f"{where}.{key}: 至少需要 {min_samples} 条，实际 {len(entries)}")
    for case in spec.get("required_case_coverage", []):
        if case not in coverage_values(entries, "case"):
            failures.append(f"{where}.{key}: 缺用例 {case}")
    return len(failures) == before


def item_status_from_received(item: dict, received_doc, failures: list[str]) -> str:
    """依据收到的记录计算 T 项实际状态；同时拒绝声明与实际不一致。"""
    declared = item.get("status")
    if received_doc is None:
        return "open"
    total = 0
    closed = 0
    for spec in item.get("evidence", []):
        if not spec.get("blocking", False):
            continue
        record = (received_doc.get("records") or {}).get(spec["record_key"])
        if not isinstance(record, dict):
            failures.append(f"{item['id']}.{spec['record_key']}: received 记录缺该 record")
            total += 1
            continue
        total += 1
        if record.get("status") != "closed":
            continue
        if check_record(record, spec, f"{item['id']}.{spec['record_key']}", failures):
            closed += 1
    return "closed" if total and closed == total else "open"


def check_templates(checklist: dict, failures: list[str]) -> int:
    checked = 0
    for item in checklist["items"]:
        template_path = EVIDENCE / item["template"]
        if not template_path.exists():
            failures.append(f"{item['id']}: 缺模板 {item['template']}")
            continue
        try:
            template = json.loads(template_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{item['id']}: 模板不是合法 JSON（{exc}）")
            continue
        records = template.get("records") or {}
        for spec in item.get("evidence", []):
            if spec["record_key"] not in records:
                failures.append(f"{item['id']}: 模板缺 record_key {spec['record_key']}")
            for name in spec.get("checks", []):
                if name not in KNOWN_CHECKS:
                    failures.append(f"{item['id']}.{spec['record_key']}: 未登记检查名 {name!r}")
            checked += 1
    return checked


def check_no_premature_enablement(any_open: bool, failures: list[str]) -> None:
    if not COMPATIBILITY.exists():
        failures.append("缺 compatibility.json")
        return
    doc = json.loads(COMPATIBILITY.read_text(encoding="utf-8"))
    allowlists = [
        ("nexus.observed_contract.operative_allowlist", doc.get("nexus", {}).get("observed_contract", {}).get("operative_allowlist")),
        ("externally_owned_vocabularies.operative_allowlist", doc.get("externally_owned_vocabularies", {}).get("operative_allowlist")),
    ]
    if any_open:
        for name, value in allowlists:
            if value is not False:
                failures.append(f"T1–T6 未全部关闭，{name} 必须为 false，实际 {value!r}")
        if doc.get("externally_owned_vocabularies", {}).get("artifact_access_scope") != []:
            failures.append("T1–T6 未全部关闭，artifact_access_scope 必须为空列表")
        if doc.get("default_decision") != "reject":
            failures.append("T1–T6 未全部关闭，compatibility.json default_decision 必须为 reject")


def check_local_evidence_package(
    checklist: dict,
    repo_root: Path,
    failures: list[str],
    warnings: list[str],
    require_host: bool = False,
) -> tuple[int, bool]:
    """宿主仓库证据审计：只适用于保存该证据包的中央仓库（B10 / S3）。

    规范包必须能独立交付：因此本函数**只在宿主标记齐备时执行**，否则返回
    `(0, skipped=True)` 并由调用方打印 `[SKIP]`。这样把包复制到任意目录后
    `validate.py` 仍能通过，同时中央仓库里证据缺失或摘要漂移仍是**失败**而非告警。

    保证三件事：
      1. 快照记录的 artifacts 摘要与磁盘一致（引用不是陈旧的）；
      2. 样例仍声明 production=false（禁止复核时改标签把它变成生产证据）；
      3. 清单引用的 artifact 确实存在于快照中，且每项被标为 non_closing。

    S3：`profile_manifest_sha256` 是**采集时 pin，不得改写**。当它不再等于当前
    包摘要时，必须另有 `profile_manifest_rechecks` 复核记录（检查时间晚于采集时间、
    `checked_against_sha256` 指向当前包、附命令与结果，并显式说明是否重跑过旧样例）。
    缺复核记录即失败——版本漂移不能只退化成告警。
    """
    package = checklist.get("local_evidence_package") or {}
    rel = package.get("path")
    if not rel:
        failures.append("清单缺 local_evidence_package.path")
        return 0, False

    markers = package.get("host_markers")
    if isinstance(markers, list) and markers:
        absent = [m for m in markers if not (repo_root / m).exists()]
        if absent:
            if require_host:
                failures.append(
                    f"要求宿主审计但缺少宿主标记 {absent}（--require-host-audit）；"
                    "若不是中央仓库请勿加该参数"
                )
                return 0, False
            return 0, True

    base = repo_root / rel
    if not base.exists():
        failures.append(f"本地证据包不存在：{rel}（宿主标记齐备，说明该仓库应当包含它）")
        return 0, False

    snapshot_path = base / package.get("snapshot", "source-snapshot.json")
    if not snapshot_path.exists():
        failures.append(f"本地证据包缺快照：{rel}/{package.get('snapshot')}")
        return 0, False
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    if snapshot.get("production") is not False:
        failures.append(f"{rel}: 本地证据包必须声明 production=false")
    if package.get("closing") is not False:
        failures.append("local_evidence_package.closing 必须为 false（本地样例不能关闭 T1–T6）")

    registered = {a.get("path"): a.get("sha256") for a in snapshot.get("artifacts", [])}
    verified = 0
    for name, expected in sorted(registered.items()):
        path = base / name
        if not path.exists():
            failures.append(f"{rel}/{name}: 快照登记但文件缺失")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected != actual:
            failures.append(f"{rel}/{name}: 与快照摘要不符（快照 {expected} / 实际 {actual}）")
        else:
            verified += 1

    for name in sorted(registered):
        if not name.endswith("-http-samples.json"):
            continue
        doc = json.loads((base / name).read_text(encoding="utf-8"))
        if doc.get("production") is not False:
            failures.append(f"{rel}/{name}: 合成样例必须声明 production=false，不得改写标签")

    for item in checklist.get("items", []):
        local = item.get("local_evidence")
        if local is None:
            continue
        if local.get("status") != "non_closing":
            failures.append(f"{item['id']}.local_evidence.status 必须是 non_closing")
        for name in local.get("artifacts", []):
            if name not in registered:
                failures.append(f"{item['id']}.local_evidence 引用了快照中不存在的 artifact：{name}")

    check_capture_pin(snapshot, rel, failures)
    return verified, False


def check_capture_pin(snapshot: dict, rel: str, failures: list[str]) -> None:
    """S3：采集时 pin 不得改写；版本漂移必须另有复核记录，不能只是告警。

    pin 是否"被改写"是可判定的：快照同时记录采集时的包版本
    （`capture_package_version`）。若该版本与当前包版本不同，pin **必须**仍是旧摘要
    ——等于当前摘要即说明有人把 pin 改成了新值，正是评审 S3 指出的错误做法。
    """
    pin = snapshot.get("profile_manifest_sha256")
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{64}", pin):
        failures.append(f"{rel}/source-snapshot.json: profile_manifest_sha256 必须是采集时的 64 位十六进制 pin")
        return

    capture_version = snapshot.get("capture_package_version")
    if not isinstance(capture_version, str) or not capture_version.strip() or is_placeholder(capture_version):
        failures.append(
            f"{rel}/source-snapshot.json: 必须记录 capture_package_version（采集时的包版本），"
            "否则无法判定 pin 是否被改写为当前版本"
        )
        return

    manifest_path = BASE / "manifest.json"
    if not manifest_path.exists():
        return
    current = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    try:
        current_version = json.loads(manifest_path.read_text(encoding="utf-8")).get("package_version")
    except json.JSONDecodeError:
        current_version = None

    if capture_version == current_version:
        if pin != current:
            failures.append(
                f"{rel}/source-snapshot.json: 采集版本与当前包版本相同（{capture_version}），"
                "但 pin 与当前包摘要不一致——同版本下 pin 必须等于当前摘要"
            )
        return

    if pin == current:
        failures.append(
            f"{rel}/source-snapshot.json: 采集 pin 被改写为当前包摘要（pin 属于 {capture_version}，"
            f"当前已是 {current_version}）——应保留原 pin 并另记 profile_manifest_rechecks，不得替换 pin"
        )
        return

    rechecks = snapshot.get("profile_manifest_rechecks")
    if not isinstance(rechecks, list) or not rechecks:
        failures.append(
            f"{rel}/source-snapshot.json: 采集 pin 与当前包摘要不一致（pin {pin[:16]}… / 当前 {current[:16]}…），"
            "但缺 profile_manifest_rechecks 复核记录——保留原 pin 并另记复核证据，不得只改 pin 或只告警"
        )
        return

    captured_at = snapshot.get("captured_at")
    pointing_at_current = 0
    for index, record in enumerate(rechecks):
        where = f"{rel}/source-snapshot.json.profile_manifest_rechecks[{index}]"
        if not isinstance(record, dict):
            failures.append(f"{where}: 复核记录必须是对象")
            continue
        for field in ("checked_at", "checked_against_sha256", "command", "scope", "result"):
            value = record.get(field)
            if not isinstance(value, str) or not value.strip() or is_placeholder(value):
                failures.append(f"{where}.{field}: 复核记录缺 {field}")
        checked_at = record.get("checked_at")
        if isinstance(checked_at, str) and not RFC3339_RE.match(checked_at):
            failures.append(f"{where}.checked_at: 期望 RFC3339 Z")
        elif isinstance(captured_at, str) and isinstance(checked_at, str) and checked_at <= captured_at:
            failures.append(f"{where}.checked_at: 复核时间必须晚于采集时间（{captured_at}）")
        target = record.get("checked_against_sha256")
        # 复核记录是**时点**证据：历史条目可以指向当时的包摘要，
        # 但格式必须合法，且至少要有一条指向**当前**摘要（见下）。
        if not isinstance(target, str) or not re.fullmatch(r"[0-9a-f]{64}", target):
            failures.append(f"{where}.checked_against_sha256: 必须是 64 位十六进制包摘要")
        elif target == current:
            pointing_at_current += 1
        if not isinstance(record.get("reexecuted"), bool):
            failures.append(f"{where}.reexecuted: 必须显式声明是否重跑过旧样例（布尔）")
        elif record["reexecuted"] is True and not record.get("reexecuted_artifacts"):
            failures.append(f"{where}.reexecuted_artifacts: reexecuted=true 时必须列出重跑过的 artifact")
    if pointing_at_current == 0:
        failures.append(
            f"{rel}/source-snapshot.json: 没有一条复核记录指向当前包摘要 {current[:16]}…"
            "（历史 pin 可保留，但必须有一次针对当前包的复核）"
        )




def main(argv: list[str] | None = None) -> int:
    """程序入口。`argv=None` 表示"无参数"（便于测试与 importlib 调用），
    命令行调用由 `__main__` 显式传入 `sys.argv[1:]`，避免把宿主进程的参数当成本脚本参数。
    """
    argv = list(argv) if argv is not None else []
    require_host_audit = "--require-host-audit" in argv
    unknown = [a for a in argv if a != "--require-host-audit"]
    if unknown:
        print(f"[FATAL] 未知参数 {unknown}；可用：--require-host-audit")
        return 2

    failures: list[str] = []
    warnings: list[str] = []
    try:
        checklist = load_json(CHECKLIST)
    except Fatal as exc:
        print(f"[FATAL] {exc}")
        return 2

    if checklist.get("tracker") != "T1-T6-closure-checklist":
        print("[FATAL] closure-checklist.json 不是预期的追踪器文件")
        return 2

    ids = [item.get("id") for item in checklist.get("items", [])]
    expected_ids = ["T1", "T2", "T3", "T4", "T5", "T6"]
    if ids != expected_ids:
        print(f"[FATAL] items 必须恰好为 {expected_ids}，实际 {ids}")
        return 2

    evidence_count = check_templates(checklist, failures)
    print(f"[{'OK' if not failures else 'FAIL'}] 清单与模板对应：{evidence_count} 条证据要求")

    computed_closed: list[str] = []
    for item in checklist["items"]:
        received_path = RECEIVED / f"{item['id']}.json"
        received_doc = None
        if received_path.exists():
            try:
                received_doc = json.loads(received_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                failures.append(f"{item['id']}: received 记录不是合法 JSON（{exc}）")
                continue
            if received_doc.get("t_item") != item["id"]:
                failures.append(f"{item['id']}: received 记录 t_item 不匹配（{received_doc.get('t_item')!r}）")
            if received_doc.get("item_status") == "closed" and has_placeholder(received_doc.get("item_status_reason", "")):
                failures.append(f"{item['id']}: item_status=closed 但 item_status_reason 仍是占位符")

        computed = item_status_from_received(item, received_doc, failures)
        declared = item.get("status")
        if declared not in ("open", "closed"):
            failures.append(f"{item['id']}: status 必须是 open/closed，实际 {declared!r}")
        if declared != computed:
            failures.append(
                f"{item['id']}: 声明 {declared} 与实际 {computed} 不一致"
                "（不得直接改声明迁就实际；补齐证据或修正记录）"
            )
        if received_doc is not None and received_doc.get("item_status") not in (None, computed):
            failures.append(
                f"{item['id']}: received.item_status={received_doc.get('item_status')!r} 与计算值 {computed!r} 不一致"
            )
        if computed == "closed":
            computed_closed.append(item["id"])
        mark = "closed" if computed == "closed" else "open  "
        print(f"      - {item['id']} [{mark}] {item['title']}（{item['owner']}）")

    any_open = len(computed_closed) != len(checklist["items"])
    check_no_premature_enablement(any_open, failures)
    print(f"[OK] 提前放行检查：operative_allowlist 与 artifact_access_scope {'保持锁定' if any_open else '已可放行'}")

    before_local = len(failures)
    local_verified, host_skipped = check_local_evidence_package(
        checklist, REPO_ROOT, failures, warnings, require_host=require_host_audit
    )
    if host_skipped:
        print(
            "[SKIP] 宿主证据审计：当前目录不是保存该证据包的中央仓库（缺宿主标记）——"
            "规范包可独立交付，此步跳过；收到的关闭证据仍在上方逐条严格校验"
        )
    else:
        print(
            f"[{'OK' if len(failures) == before_local else 'FAIL'}] 本地证据包自洽："
            f"{local_verified} 个 artifact（非关闭，采集 pin 未改写）"
        )
    for warning in warnings:
        print(f"[WARN] {warning}")

    gate_status = (checklist.get("gate") or {}).get("status")
    gate_expected = "closed" if any_open else "open"
    if gate_status not in ("open", "closed"):
        failures.append(f"gate.status 必须是 open/closed，实际 {gate_status!r}")
    elif gate_status != gate_expected:
        failures.append(
            f"gate.status 声明 {gate_status}，按证据计算应为 {gate_expected}"
            "（BINDING-GATE-1 只能在 T1–T6 全部关闭后开启）"
        )
    print(f"[{'OK' if gate_status == gate_expected else 'FAIL'}] BINDING-GATE-1：{gate_status}（应为 {gate_expected}）")

    if failures:
        print("\n[FAILURES]")
        for failure in failures:
            print(" -", failure)
        for warning in warnings:
            print("[WARN]", warning)
        return 1

    if any_open:
        print(
            f"\n[PASS] T1–T6 收口清单自洽：{len(computed_closed)}/{len(checklist['items'])} 已关闭，"
            "其余保持开放。开放是合法状态；本结果不声明 wire conformance，也不开启 BINDING-GATE-1。"
        )
    else:
        print("\n[PASS] T1–T6 全部关闭且清单自洽。下一步按 T6 冻结 compatibility.json 并执行 CP-01～26。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))