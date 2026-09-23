"""§15.7 角色授权（AgentNexus 侧唯一实现点）。

规则（Profile §15.7 + RC2 §1）：

- 凭据主体必须在**服务端**登记角色；正文里的 ``issuer_id``/``signature`` 不赋权；
- 部署**未登记任何角色**时降级为"部署约定"：允许写入，但返回 ``declared_only``，
  调用方与运维不得据此声称强制隔离，也不得运行符合性授权测试（CP-24）；
- 部署已登记角色时必须命中，否则 ``authority_denied``。

回执 kind → 角色：``accepted``→coordinator、``published``→publisher、
``received``/``validated``→validator（角色表无独立 storage 角色，接收存储服务与
验证服务统一登记为 validator）。

与 Profile §15.7 的能力名对应关系（RC2 §1 的凭据角色即其实现载体）：

| Profile 能力 | 本实现的强制点 | 凭据角色 |
|---|---|---|
| ``review:candidate_submit`` | `POST A/artifacts`、Profile 交付入口（仅候选） | ``worker`` |
| ``review:deliver`` | 签发 ``accepted`` 回执（经 CAS） | ``coordinator`` |
| （验证服务） | 签发 ``validated`` 回执 | ``validator`` |
| ``publication:write`` | 签发 ``published`` 回执 | ``publisher`` |
"""

from __future__ import annotations

from typing import Dict

from .errors import ProfileError

#: RC2 §1 的角色表
PROFILE_ROLES = (
    "requester",
    "coordinator",
    "worker",
    "validator",
    "publisher",
    "policy_admin",
    "evidence_reader",
)

#: 回执 kind → 所需角色
ROLE_BY_RECEIPT_KIND: Dict[str, str] = {
    "received": "validator",
    "validated": "validator",
    "accepted": "coordinator",
    "published": "publisher",
}

ENFORCED = "enforced"
DECLARED_ONLY = "declared_only"


async def authorize(
    actor_did: str,
    *,
    role: str,
    instance_id: str = "",
    project_id: str = "",
    profile_session_id: str = "",
    scope: str = "authorization",
) -> str:
    """返回本次写入的强制级别：``enforced`` 或 ``declared_only``。"""
    from agent_net.persistence.code_review_store import (
        resolve_roles,
        roles_configured,
    )

    if not actor_did:
        raise ProfileError("authority_denied", "缺少认证主体（actor_did）", scope=scope)
    if role not in PROFILE_ROLES:
        raise ValueError(f"未登记的角色：{role}")
    if not await roles_configured():
        return DECLARED_ONLY
    roles = await resolve_roles(
        actor_did,
        instance_id=instance_id,
        project_id=project_id,
        profile_session_id=profile_session_id,
    )
    if role not in roles:
        raise ProfileError(
            "authority_denied", f"主体不具备所需角色 {role}", scope=scope
        )
    return ENFORCED


async def authorize_receipt_kind(
    actor_did: str, kind: str, *, profile_session_id: str = ""
) -> str:
    """按回执 kind 校验签发角色（RC2 §4）。"""
    role = ROLE_BY_RECEIPT_KIND.get(kind)
    if role is None:
        raise ProfileError(
            "invalid_output",
            f"未知 receipt kind：{kind}（只接受 {'/'.join(ROLE_BY_RECEIPT_KIND)}）",
            scope="receipt",
        )
    return await authorize(
        actor_did, role=role, profile_session_id=profile_session_id, scope="receipt"
    )
