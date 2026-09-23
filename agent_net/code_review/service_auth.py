"""Profile 服务接口的凭据 → principal → 角色/资源授权（RC2 §1；评审 B1/B2）。

**为什么不能复用 Daemon token**：Daemon token 是单机管理凭据，只证明"能访问本
Daemon"。原来的实现因此只能拿信封里的 ``sender_id`` 去查角色——于是同一 token 只要把
sender 从 worker 改成已登记 coordinator，403 就变成 202 且标记 ``enforced``
（评审 B1 复现）。同理，读取接口没有"谁能读哪个 Run"的资源边界（评审 B2）。

本模块把三件事分开：

1. **认证**：Bearer token → 登记在册的 principal（含角色、可代表的 DID、允许的
   instance/project/session）。未配置任何凭据时一律拒绝，不沿用"未配置则放行"。
2. **角色授权**：principal 必须真具备所需角色。
3. **资源授权**：principal 的资源范围必须覆盖目标 session/instance/project。

``sender_id`` / ``issuer_id`` / ``producer_id`` 必须落在 principal 可代表的 DID 内，
不得自报。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, Optional, Sequence, Tuple

from .errors import ProfileError

#: Profile 服务角色（RC2 §1）
PROFILE_ROLES: Tuple[str, ...] = (
    "requester",
    "coordinator",
    "worker",
    "validator",
    "publisher",
    "policy_admin",
    "evidence_reader",
)

#: 只读角色（可用于读取消息/产物）
READ_ROLES: FrozenSet[str] = frozenset({"coordinator", "validator", "publisher", "evidence_reader"})


def hash_token(token: str) -> str:
    """凭据只以摘要落库，不保存明文。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_bearer(authorization: Optional[str]) -> str:
    """从 ``Authorization`` 头取出 Bearer 凭据；格式不符抛 401。

    契约 §7 中 401/403 共用 ``authority_denied``：本函数只处理"凭据缺失/格式错误"，
    因此固定 401；角色与资源拒绝由 :class:`ServicePrincipal` 抛 403。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise ProfileError(
            "authority_denied", "缺少 Bearer 服务凭据", scope="authorization", http_status=401
        )
    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise ProfileError(
            "authority_denied", "Bearer 服务凭据为空", scope="authorization", http_status=401
        )
    return token


@dataclass(frozen=True)
class ServicePrincipal:
    """已认证的服务主体。"""

    principal_id: str
    roles: FrozenSet[str] = frozenset()
    dids: Tuple[str, ...] = ()
    instances: Tuple[str, ...] = ()
    projects: Tuple[str, ...] = ()
    sessions: Tuple[str, ...] = ()

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "ServicePrincipal":
        def as_tuple(key: str) -> Tuple[str, ...]:
            value = row.get(key) or []
            if isinstance(value, str):
                return tuple(v for v in (value,) if v)
            return tuple(str(v) for v in value if v)

        roles = as_tuple("roles")
        unknown = [r for r in roles if r not in PROFILE_ROLES]
        if unknown:
            raise ProfileError(
                "authority_denied",
                f"凭据登记了未定义角色：{','.join(unknown)}",
                scope="authorization",
            )
        return cls(
            principal_id=str(row["principal_id"]),
            roles=frozenset(roles),
            dids=as_tuple("dids"),
            instances=as_tuple("instances"),
            projects=as_tuple("projects"),
            sessions=as_tuple("sessions"),
        )

    # ── 角色授权 ─────────────────────────────────────────────────────
    def require_role(self, role: str) -> None:
        if role not in self.roles:
            raise ProfileError(
                "authority_denied",
                f"主体 {self.principal_id} 不具备所需角色 {role}",
                scope="authorization",
            )

    def require_any_role(self, roles: Iterable[str]) -> None:
        wanted = set(roles)
        if not (self.roles & wanted):
            raise ProfileError(
                "authority_denied",
                f"主体 {self.principal_id} 不具备所需角色之一 {sorted(wanted)}",
                scope="authorization",
            )

    # ── 资源授权（B2） ───────────────────────────────────────────────
    def require_resource(
        self,
        *,
        profile_session_id: str = "",
        instance_id: str = "",
        project_id: str = "",
    ) -> None:
        """principal 的资源范围必须覆盖目标；空范围不等于"全部允许"。"""
        if profile_session_id:
            if profile_session_id not in self.sessions:
                raise ProfileError(
                    "authority_denied",
                    f"主体 {self.principal_id} 未获授权访问该 session",
                    scope="authorization",
                )
        elif not self.sessions and not self.instances and not self.projects:
            # 没有任何资源范围却要求资源授权 → 不能当成"通配"
            raise ProfileError(
                "authority_denied",
                f"主体 {self.principal_id} 未登记任何资源范围，拒绝资源级访问",
                scope="authorization",
            )
        if instance_id and self.instances and instance_id not in self.instances:
            raise ProfileError(
                "authority_denied",
                f"主体 {self.principal_id} 未获授权访问该 instance",
                scope="authorization",
            )
        if project_id and self.projects and project_id not in self.projects:
            raise ProfileError(
                "authority_denied",
                f"主体 {self.principal_id} 未获授权访问该 project",
                scope="authorization",
            )

    def require_session(self, profile_session_id: str) -> None:
        """读取产物/消息必须落在同一 session（RC2 §4）。"""
        if not profile_session_id:
            raise ProfileError(
                "data_policy_denied",
                "该资源未绑定 Profile session，服务私有范围无法证明，拒绝读取",
                scope="policy",
            )
        if profile_session_id not in self.sessions:
            raise ProfileError(
                "authority_denied",
                f"主体 {self.principal_id} 未获授权访问该 session",
                scope="authorization",
            )

    # ── 身份绑定（B1） ───────────────────────────────────────────────
    def acting_did(self, requested: Optional[str] = None) -> str:
        """确定本次操作代表哪个 DID：必须在登记范围内。"""
        if requested:
            if requested not in self.dids:
                raise ProfileError(
                    "authority_denied",
                    f"主体 {self.principal_id} 不得代表 DID {requested}",
                    scope="authorization",
                )
            return requested
        if len(self.dids) == 1:
            return self.dids[0]
        raise ProfileError(
            "authority_denied",
            f"主体 {self.principal_id} 绑定了 {len(self.dids)} 个 DID，必须显式指定代表身份",
            scope="authorization",
        )

    def require_bound_did(self, did: str, *, what: str) -> str:
        """``sender_id`` / ``issuer_id`` 等自报字段必须与登记主体一致。"""
        if not did:
            raise ProfileError(
                "authority_denied", f"缺少{what}（不得自报，必须与认证主体一致）", scope="authorization"
            )
        if did not in self.dids:
            raise ProfileError(
                "authority_denied",
                f"{what} {did} 与认证主体 {self.principal_id} 不一致，且不在登记委托范围内",
                scope="authorization",
            )
        return did


#: 回执 kind → 所需角色（与 RC2 §4 一致）
RECEIPT_KIND_ROLE: Dict[str, str] = {
    "received": "validator",
    "validated": "validator",
    "accepted": "coordinator",
    "published": "publisher",
}


def require_receipt_authority(principal: ServicePrincipal, kind: str, issuer_id: str) -> str:
    """回执 kind 的角色路由 + issuer 身份绑定（评审 B1；R2-4 要求**返回**该角色）。

    返回该 kind 唯一对应的角色，供调用方做强制级别判定——不得再另行假定 coordinator，
    否则合法的 validator / publisher 会被错误要求 coordinator 角色（评审 R2-4）。
    """
    role = RECEIPT_KIND_ROLE.get(kind)
    if role is None:
        raise ProfileError(
            "invalid_output",
            f"未知 receipt kind：{kind}（只接受 {'/'.join(RECEIPT_KIND_ROLE)}）",
            scope="receipt",
        )
    principal.require_role(role)
    principal.require_bound_did(issuer_id, what="回执签发主体 issuer_id")
    return role
