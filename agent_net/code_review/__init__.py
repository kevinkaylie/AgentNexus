"""Code Review Collaboration Profile v1 —— AgentNexus 侧实现。

模块边界（对应 Profile 与 binding RC2）：

- ``digest``             §15.3 字节口径与摘要（artifact_body 严格 UTF-8、行区间原始字节）
- ``errors``             ``code_review.error.v1`` 错误信封与 HTTP 映射（RC2 §7）
- ``validation``         Profile 校验层（信封、ReviewReport 不变式）与 §15.2 状态翻译责任层
- ``authz``              §15.7 角色判定与回执 kind→角色映射
- ``provider_adapter``   **厂商无关**的「评审方报告 → Profile 报告」管线与注册表
- ``presentation``       评审结论的呈现与发布前校验（任何评审方一致）
- ``service_auth``        服务接口的凭据 → principal → 角色/资源授权（RC2 §1；评审 B1/B2）
- ``frozen``              冻结规范包的加载与接收前 schema 校验（评审 B3/B5）
- ``hczj_adapter``       评审方实现之一（``provider_id="hczj"``）；新增评审方照此新增模块

可插拔性：接入另一个评审方 = 新增一个 :class:`~agent_net.code_review.provider_adapter.ReviewProviderAdapter`
子类并用 ``register_provider()`` 注册，**无需改动** AgentNexus 核心或既有 provider。
厂商无关入口是 :func:`build_profile_report`（可 ``provider_id`` 显式指定或按 schema 自动识别）。

设计约束：
- 本包不复制通用调度器，不绕过 Daemon 直接操作存储；
- 纯逻辑模块不依赖 FastAPI 与 jsonschema，便于单测与跨仓库复用；
- 所有"必须新增"的能力以显式声明为准，未实现的能力不得静默通过。
"""

from .digest import (
    DigestError,
    artifact_body_bytes,
    line_range_bytes,
    line_range_sha256,
    report_digest,
)
from .errors import (
    CODE_TABLE,
    READ_LIMITS,
    ProfileError,
    error_envelope,
)
from .presentation import (
    OUTCOME_LABEL,
    render_review_summary,
    validate_publish_body,
)
from .provider_adapter import (
    DEFAULT_PRIORITY_SEVERITY_MAP,
    PROFILE_OUTCOMES,
    ReviewProviderAdapter,
    build_profile_report,
    detect_provider,
    get_provider,
    list_providers,
    priority_to_severity,
    register_provider,
)
from .service_auth import (
    PROFILE_ROLES,
    READ_ROLES,
    RECEIPT_KIND_ROLE,
    ServicePrincipal,
    hash_token,
    require_receipt_authority,
)
from .projection import (
    ARTIFACT_BUSINESS_FIELDS,
    MESSAGE_TRACKING_FIELDS,
    artifact_projection,
    canonical_json,
    message_projection,
    projection_digest,
)
from .validation import (
    PROFILE_VERSION,
    REPORT_SCHEMA_VERSION,
    ValidationIssue,
    parse_envelope,
    parse_strict_json,
    translate_agentnexus_result,
    validate_review_report,
)

# HCZJ 专用便捷入口（导入即注册 provider "hczj"）
from .hczj_adapter import (
    HCZJ_OUTCOMES,
    HczjReviewProvider,
    build_profile_report as build_hczj_profile_report,
)

__all__ = [
    # 字节口径
    "DigestError",
    "artifact_body_bytes",
    "report_digest",
    "line_range_bytes",
    "line_range_sha256",
    # 错误
    "CODE_TABLE",
    "READ_LIMITS",
    "ProfileError",
    "error_envelope",
    # 校验与翻译
    "PROFILE_VERSION",
    "REPORT_SCHEMA_VERSION",
    "ValidationIssue",
    "parse_envelope",
    "parse_strict_json",
    "validate_review_report",
    "translate_agentnexus_result",
    # 评审方适配器（可插拔）
    "ReviewProviderAdapter",
    "register_provider",
    "get_provider",
    "list_providers",
    "detect_provider",
    "build_profile_report",
    "priority_to_severity",
    "DEFAULT_PRIORITY_SEVERITY_MAP",
    "PROFILE_OUTCOMES",
    # 呈现
    "OUTCOME_LABEL",
    "render_review_summary",
    "validate_publish_body",
    # 服务接口凭据与授权（RC2 §1）
    "PROFILE_ROLES",
    "READ_ROLES",
    "RECEIPT_KIND_ROLE",
    "ServicePrincipal",
    "require_receipt_authority",
    "hash_token",
    # 幂等业务投影（RC2 §7）
    "message_projection",
    "artifact_projection",
    "projection_digest",
    "canonical_json",
    "MESSAGE_TRACKING_FIELDS",
    "ARTIFACT_BUSINESS_FIELDS",
    # HCZJ provider
    "HczjReviewProvider",
    "HCZJ_OUTCOMES",
    "build_hczj_profile_report",
]
