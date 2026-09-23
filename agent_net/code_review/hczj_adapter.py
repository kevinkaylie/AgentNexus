"""HCZJ 评审方适配器（三个 provider 之一，注册为 ``provider_id="hczj"``）。

本模块**只声明 HCZJ 的词表与字段形状**，全部转换规则由
:class:`agent_net.code_review.provider_adapter.ReviewProviderAdapter` 的商业无关管线执行。
替换或新增评审方时应新增同类模块，**不要**改本文件以外的核心代码。

- 原生报告：``hczj.review_report.v1``（outcome: findings_present / no_findings / inconclusive）
- 原生覆盖：``hczj.review_coverage.v1``（status: complete / partial / none）
- 溯源键：``extensions["hczj.provenance"]``

兼容入口：``build_profile_report(...)`` 与 ``HCZJ_OUTCOMES`` 保留为 HCZJ 专用便捷路径；
厂商无关入口是 :func:`agent_net.code_review.provider_adapter.build_profile_report`。
呈现函数（``render_review_summary`` / ``validate_publish_body``）已迁至
:mod:`agent_net.code_review.presentation`，此处仅做兼容性再导出。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from .presentation import (  # noqa: F401  （兼容性再导出）
    render_review_summary,
    validate_publish_body,
)
from .provider_adapter import (
    ReviewProviderAdapter,
    build_profile_report as _build_profile_report,
    register_provider,
)


class HczjReviewProvider(ReviewProviderAdapter):
    """HCZJ 评审应用服务提供的报告 + 覆盖。"""

    provider_id = "hczj"
    display_name = "HCZJ 评审应用服务"
    source_report_schemas = ("hczj.review_report.v1",)
    source_coverage_schemas = ("hczj.review_coverage.v1",)
    source_outcomes = ("findings_present", "no_findings", "inconclusive")
    coverage_complete_token = "complete"
    provenance_key = "hczj.provenance"
    error_scope = "hczj_conversion"


#: 注册（幂等）：同 id 重复注册会覆盖，便于测试与部署扩展
register_provider(HczjReviewProvider())

#: 兼容常量：HCZJ 的 outcome 词表
HCZJ_OUTCOMES = HczjReviewProvider.source_outcomes


def build_profile_report(
    *,
    hczj_report: Mapping[str, Any],
    hczj_coverage: Mapping[str, Any],
    identity: Mapping[str, Any],
    execution_metadata: Mapping[str, Any],
    usage: Mapping[str, Any],
    limitations: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """[HCZJ 专用便捷入口] 等价于 ``build_profile_report(provider_id="hczj", ...)``。"""
    return _build_profile_report(
        provider_id="hczj",
        native_report=hczj_report,
        native_coverage=hczj_coverage,
        identity=identity,
        execution_metadata=execution_metadata,
        usage=usage,
        limitations=limitations,
    )
