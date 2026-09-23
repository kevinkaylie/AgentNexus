"""``code_review.error.v1`` 错误信封与 HTTP 映射（binding RC2 §7 与 §10.1）。

规范要点：

- 所有新增接口直接返回 ``code_review.error.v1``，**不是** FastAPI 的 ``{"detail": "字符串"}``；
- 信封必须携带 ``correlation_id``；``retry_after_seconds`` 遵守冻结 schema 的不变式：
  ``retryable=false`` 时必须为 ``null``，``retryable=true`` 时只能为 ``null`` 或正整数，429 必须为整数；
- ``action_required`` 表示需要人工修正或介入，不表示必须再发一次请求；
- HTTP 状态只是承载，不得据状态码本身驱动无限重试（Profile §9）。

READ_LIMITS 是 RC2 §10.1 的读取上限；超限在发送成功头部前拒绝，返回
``413 data_policy_denied``。``data_policy_denied`` 承载多种成因，按 RC2 §7（评审 R2-2）
固定用 ``scope`` 区分，调用方与运维**不得仅凭 code 判断原因**：

| scope | HTTP | 含义 |
|---|---|---|
| ``read_limit`` | 413 | 读取/载荷超限（本模块 :func:`read_limit_error`） |
| ``retention`` | 422 | 无法承诺所请求的保留期（上传/注册产物） |
| ``policy`` | 403 | 披露或权限策略拒绝（provider/数据出境等，当前实现保留为声明位） |
"""

from __future__ import annotations

from typing import Any, Dict, Optional

ERROR_SCHEMA = "code_review.error.v1"

#: 读取上限（RC2 §10.1，binding 加严，非 Profile 通用要求）
READ_LIMITS: Dict[str, Any] = {
    "raw_report_max_bytes": 16 * 1024 * 1024,
    "artifact_max_bytes": 16 * 1024 * 1024,
    "source_bytes_max_bytes": 1 * 1024 * 1024,
    "source_bytes_max_lines": 2000,
    "json_response_max_bytes": 4 * 1024 * 1024,
}

#: code → (HTTP 状态, retryable, action_required)；``coordinator_unavailable`` 有变体，见 build。
CODE_TABLE: Dict[str, tuple] = {
    "unsupported_profile": (422, False, True),
    "unsupported_contract": (422, False, True),
    "unsupported_capability": (422, False, True),
    "unsupported_critical_extension": (422, False, True),
    "enforcement_unavailable": (422, False, True),
    "invalid_output": (422, False, True),
    "input_mismatch": (422, False, True),
    "authority_denied": (403, False, True),
    "data_policy_denied": (403, False, True),
    "evidence_unavailable": (404, False, True),
    "artifact_expired": (410, False, True),
    "evidence_digest_mismatch": (409, False, True),
    "delivery_conflict": (409, False, True),
    "idempotency_conflict": (409, False, True),
    "publication_unknown": (409, False, True),
    "stale_assignment": (409, False, False),
    "superseded_input": (409, False, False),
    "policy_changed": (409, False, False),
    "budget_exhausted": (409, False, False),
    "deadline_exceeded": (409, False, False),
    "rate_limited": (429, True, False),
    "temporarily_unavailable": (503, True, False),
    "freshness_unknown": (503, True, False),
    # coordinator_unavailable 的两个变体在 _build 中特判
    "coordinator_unavailable": (503, None, None),
}


class ProfileError(Exception):
    """携带 ``code_review.error.v1`` 语义的异常；由路由层转换为响应。"""

    __slots__ = ("code", "scope", "safe_message", "correlation_id", "retryable",
                 "action_required", "retry_after_seconds", "http_status", "extra")

    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        scope: str,
        correlation_id: str = "",
        retryable: Optional[bool] = None,
        action_required: Optional[bool] = None,
        retry_after_seconds: Optional[int] = None,
        http_status: Optional[int] = None,
        variant: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ):
        if code not in CODE_TABLE:
            raise ValueError(f"未登记的错误码：{code}（必须先扩展 CODE_TABLE）")
        if not scope:
            raise ValueError("错误必须给出 scope，用于区分同码不同因（RC2 §7）")
        default_status, default_retryable, default_action = CODE_TABLE[code]

        if code == "coordinator_unavailable":
            # §15.8：未配置 → retryable=false/action_required=true；暂不可达 → true/false
            if variant == "unreachable":
                default_retryable, default_action = True, False
            else:
                default_retryable, default_action = False, True

        self.code = code
        self.scope = scope
        self.safe_message = safe_message
        self.correlation_id = correlation_id
        self.retryable = default_retryable if retryable is None else retryable
        self.action_required = default_action if action_required is None else action_required
        self.http_status = default_status if http_status is None else http_status
        self.extra = extra or {}

        if self.retryable is False:
            if retry_after_seconds is not None:
                raise ValueError("retryable=false 时 retry_after_seconds 必须为 null（冻结 schema 不变式）")
            self.retry_after_seconds = None
        else:
            if retry_after_seconds is not None and retry_after_seconds <= 0:
                raise ValueError("retry_after_seconds 必须为正整数或 null")
            self.retry_after_seconds = retry_after_seconds

        if code == "rate_limited" and not self.retry_after_seconds:
            raise ValueError("429 rate_limited 必须给出正整数 retry_after_seconds（RC2 §7）")
        super().__init__(f"{code}: {safe_message}")


def read_limit_error(limit_name: str, observed: int, correlation_id: str = "") -> ProfileError:
    """RC2 §10.1：超限 → ``413 data_policy_denied``，并用 scope 标明是读取上限。

    细节（哪个上限、上限值、实际值）必须放进 ``extensions``：冻结
    ``error.schema.json`` 是 ``additionalProperties: false``，把 ``limit`` /
    ``limit_value`` / ``observed`` 放在顶层会让响应**不是**合法的
    ``code_review.error.v1``（HTTP 契约矩阵抓到的真实 wire 不一致）。
    """
    limit = READ_LIMITS.get(limit_name)
    return ProfileError(
        "data_policy_denied",
        f"请求超出 binding 读取上限（{limit_name}={limit}，实际={observed}）；不返回截断正文。",
        scope="read_limit",
        correlation_id=correlation_id,
        http_status=413,
        extra={
            "extensions": {
                "read_limit": {
                    "limit_name": limit_name,
                    "limit_value": limit,
                    "observed": observed,
                }
            }
        },
    )


def error_envelope(err: ProfileError) -> Dict[str, Any]:
    """构造 ``code_review.error.v1`` 信封（字段与冻结 schema 一致）。

    ``err.extra`` 只允许放 schema 声明过的键（``extensions`` / ``critical_extensions``）；
    放别的键会让响应不合法，因此这里显式拒绝而不是静默拼进去。
    """
    allowed_extra = {"extensions", "critical_extensions"}
    unexpected = sorted(set(err.extra) - allowed_extra)
    if unexpected:
        raise ValueError(
            f"错误信封不支持顶层扩展字段 {unexpected}；schema 为 additionalProperties:false，"
            "请放进 extensions"
        )
    payload: Dict[str, Any] = {
        "schema": ERROR_SCHEMA,
        "code": err.code,
        "retryable": bool(err.retryable),
        "action_required": bool(err.action_required),
        "scope": err.scope,
        "correlation_id": err.correlation_id,
        "safe_message": err.safe_message,
        "retry_after_seconds": err.retry_after_seconds,
    }
    payload.update(err.extra)
    return payload
