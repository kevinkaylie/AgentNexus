"""
Capability Token Envelope — v1.0-08

Ed25519 + JCS 签名信封，将 Enclave permissions 升级为结构化 capability token，
支持跨 Enclave 互验。

符合 qntm WG Authority Constraints 最小互操作面：
- evaluated_constraint_hash：约束集内容寻址哈希
- monotonic narrowing：委托链单调收窄验证
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


def compute_constraint_hash(scope: dict, constraints: dict) -> str:
    """
    计算约束集的内容寻址哈希（JCS 规范化 + SHA256）。
    qntm WG decision artifact 要求：每个 decision 必须引用被评估的约束集。
    """
    canonical = json.dumps(
        {"scope": scope, "constraints": constraints},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def scope_is_subset(child_scope: dict, parent_scope: dict) -> bool:
    """
    验证 child scope 是 parent scope 的子集（单调收窄）。
    """
    child_perms = set(child_scope.get("permissions", []))
    parent_perms = set(parent_scope.get("permissions", []))
    if not child_perms.issubset(parent_perms):
        return False
    # resource_pattern: child 应更窄或相同
    child_pattern = child_scope.get("resource_pattern", "*")
    parent_pattern = parent_scope.get("resource_pattern", "*")
    if child_pattern != parent_pattern and not child_pattern.startswith(parent_pattern.rstrip("*")):
        return False
    return True


@dataclass
class CapabilityToken:
    """Capability Token 数据结构"""
    token_id: str
    version: int = 1
    issuer_did: str = ""
    subject_did: str = ""
    enclave_id: Optional[str] = None

    scope: dict = field(default_factory=lambda: {
        "permissions": [],
        "resource_pattern": "*",
        "role": "",
    })
    constraints: dict = field(default_factory=lambda: {
        "spend_limit": 0,
        "max_delegation_depth": 1,
        "allowed_stages": [],
        "input_keys": [],
        "output_key": "",
    })
    validity: dict = field(default_factory=lambda: {
        "not_before": "",
        "not_after": "",
    })
    revocation_endpoint: str = ""

    evaluated_constraint_hash: str = ""
    signature_alg: str = "EdDSA"
    canonicalization: str = "JCS"
    signature: str = ""

    status: str = "active"  # active / revoked / expired
    created_at: float = 0.0
    revoked_at: Optional[float] = None

    def to_dict(self) -> dict:
        """转换为可序列化的字典"""
        return asdict(self)

    def to_json(self) -> str:
        """JCS 规范化 JSON（用于签名）"""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_revocation_endpoint(token_id: str, relay_url: str = "https://relay.agentnexus.top") -> str:
    """构建撤销端点 URL"""
    return f"{relay_url}/capability-tokens/{token_id}/status"


async def issue_token(
    issuer_did: str,
    subject_did: str,
    enclave_id: Optional[str] = None,
    scope: dict = None,
    constraints: dict = None,
    validity_days: int = 30,
    max_delegation_depth: int = 1,
    parent_token_id: Optional[str] = None,
    parent_scope_hash: Optional[str] = None,
    relay_url: str = "https://relay.agentnexus.top",
) -> CapabilityToken:
    """
    签发 Capability Token。

    Args:
        issuer_did: 签发者 DID（Enclave owner）
        subject_did: 接收者 DID（Agent）
        enclave_id: 所属 Enclave ID
        scope: 权限范围
        constraints: 约束条件
        validity_days: 有效天数
        max_delegation_depth: 最大委托深度
        parent_token_id: 父 Token ID（委托链）
        parent_scope_hash: 父 Token 的 scope hash
        relay_url: Relay URL（用于构建撤销端点）

    Returns:
        CapabilityToken 实例（未签名，需调用 sign_token()）
    """
    token_id = f"ct_{uuid.uuid4().hex[:16]}"
    now = time.time()
    not_before = now
    not_after = now + validity_days * 86400

    scope = scope or {"permissions": [], "resource_pattern": "*", "role": ""}
    constraints = constraints or {
        "spend_limit": 0,
        "max_delegation_depth": max_delegation_depth,
        "allowed_stages": [],
        "input_keys": [],
        "output_key": "",
    }

    evaluated_constraint_hash = compute_constraint_hash(scope, constraints)

    token = CapabilityToken(
        token_id=token_id,
        issuer_did=issuer_did,
        subject_did=subject_did,
        enclave_id=enclave_id,
        scope=scope,
        constraints=constraints,
        validity={
            "not_before": not_before,
            "not_after": not_after,
        },
        revocation_endpoint=build_revocation_endpoint(token_id, relay_url),
        evaluated_constraint_hash=evaluated_constraint_hash,
        created_at=now,
    )

    # 如果有父 Token，记录委托链信息（但不写入 token 本身）
    # 委托链信息写入 delegation_chain_links 表
    token._parent_token_id = parent_token_id
    token._parent_scope_hash = parent_scope_hash

    return token


def sign_token(token: CapabilityToken, private_key_hex: str) -> CapabilityToken:
    """
    使用 Ed25519 私钥签名 Token。

    Args:
        token: 未签名的 Token
        private_key_hex: 签发者私钥（hex）

    Returns:
        已签名的 Token
    """
    from nacl.signing import SigningKey
    from nacl.encoding import URLSafeBase64Encoder

    signing_key = SigningKey(bytes.fromhex(private_key_hex))

    # JCS 规范化 JSON（排除 signature 字段）
    token_dict = token.to_dict()
    # 移除签名相关字段
    for key in ["signature", "signature_alg", "canonicalization", "status", "revoked_at"]:
        token_dict.pop(key, None)
    canonical = json.dumps(token_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    # Ed25519 签名
    signed = signing_key.sign(canonical.encode())
    signature_bytes = signed.signature

    # Base64URL 编码
    token.signature = URLSafeBase64Encoder.encode(signature_bytes).decode()
    token.signature_alg = "EdDSA"
    token.canonicalization = "JCS"

    return token


async def verify_token(
    token: CapabilityToken,
    action: str,
    get_token_func=None,
    get_delegation_chain_func=None,
    is_revoked_func=None,
) -> dict:
    """
    验证 Capability Token。

    Args:
        token: 待验证的 Token
        action: 请求的操作
        get_token_func: 获取 Token 的函数（用于查询父 Token）
        get_delegation_chain_func: 获取委托链的函数
        is_revoked_func: 检查是否已撤销的函数

    Returns:
        {valid: bool, reason: str} 或详细验证结果
    """
    from nacl.signing import VerifyKey
    from nacl.encoding import URLSafeBase64Encoder
    from agent_net.storage import get_private_key

    # 1. 状态检查（先检查，避免对 revoked token 进行签名验证）
    if token.status != "active":
        return {"valid": False, "reason": "REVOKED"}

    # 通过外部函数检查撤销状态（可选）
    if is_revoked_func:
        try:
            if await is_revoked_func(token.token_id):
                return {"valid": False, "reason": "REVOKED"}
        except Exception:
            pass  # 撤销检查失败不阻塞验证

    # 2. 签名验证（Ed25519 over JCS-canonicalized payload）
    try:
        # 获取 issuer 公钥（先从 profile 获取，再从私钥推导）
        from agent_net.storage import get_agent
        agent = await get_agent(token.issuer_did)
        if not agent:
            return {"valid": False, "reason": "ISSUER_NOT_FOUND"}

        issuer_pk_hex = agent.get("profile", {}).get("public_key_hex")
        if not issuer_pk_hex:
            # 尝试从私钥推导公钥
            issuer_sk_hex = await get_private_key(token.issuer_did)
            if issuer_sk_hex:
                from nacl.signing import SigningKey
                sk = SigningKey(bytes.fromhex(issuer_sk_hex))
                issuer_pk_hex = sk.verify_key.encode().hex()
            else:
                return {"valid": False, "reason": "ISSUER_KEY_NOT_FOUND"}

        verify_key = VerifyKey(bytes.fromhex(issuer_pk_hex))

        # 验证签名
        # JCS 规范化 JSON（排除 signature 字段）
        token_dict = token.to_dict()
        for key in ["signature", "signature_alg", "canonicalization", "status", "revoked_at"]:
            token_dict.pop(key, None)
        canonical = json.dumps(token_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

        signature_bytes = URLSafeBase64Encoder.decode(token.signature.encode()) if token.signature else b""
        if not signature_bytes:
            return {"valid": False, "reason": "SIGNATURE_MISSING"}

        verify_key.verify(canonical.encode(), signature_bytes)
    except Exception as e:
        return {"valid": False, "reason": "SIGNATURE_INVALID", "detail": str(e)}

    # 3. 有效期检查
    now = time.time()
    validity = token.validity
    if isinstance(validity.get("not_before"), (int, float)):
        if now < validity["not_before"]:
            return {"valid": False, "reason": "NOT_YET_VALID"}
    if isinstance(validity.get("not_after"), (int, float)):
        if now > validity["not_after"]:
            return {"valid": False, "reason": "EXPIRED"}

    # 4. 委托链完整性 + 单调收窄验证
    if get_delegation_chain_func and token._parent_token_id:
        try:
            chain = await get_delegation_chain_func(token.token_id)
            if chain:
                parent_id = chain[0]["parent_token_id"]
                parent = await get_token_func(parent_id) if get_token_func else None
                if not parent:
                    return {"valid": False, "reason": "CHAIN_BREAK"}

                # 单调收窄：child scope ⊆ parent scope
                if not scope_is_subset(token.scope, parent.scope):
                    return {"valid": False, "reason": "SCOPE_EXPANSION"}

                # 约束更严格
                if token.constraints.get("spend_limit", 0) > parent.constraints.get("spend_limit", 0):
                    return {"valid": False, "reason": "SPEND_LIMIT_EXPANSION"}
                if token.constraints.get("max_delegation_depth", 1) >= parent.constraints.get("max_delegation_depth", 1):
                    return {"valid": False, "reason": "DELEGATION_DEPTH_EXPANSION"}
        except Exception as e:
            return {"valid": False, "reason": "CHAIN_CHECK_FAILED", "detail": str(e)}

    # 5. 权限检查
    if action not in token.scope.get("permissions", []):
        return {"valid": False, "reason": "PERMISSION_DENIED"}

    return {"valid": True, "token_id": token.token_id}


async def revoke_token(token_id: str, revoke_func=None) -> bool:
    """
    撤销 Token。

    Args:
        token_id: Token ID
        revoke_func: 撤销函数（更新数据库）

    Returns:
        True 表示成功，False 表示 Token 不存在
    """
    if revoke_func:
        return await revoke_func(token_id)
    return False


# 权限映射（从 Enclave permissions 字符串到细粒度权限数组）
PERMISSIONS_MAP = {
    "admin": ["vault:read", "vault:write", "vault:delete", "playbook:execute", "member:manage"],
    "rw": ["vault:read", "vault:write", "playbook:execute"],
    "r": ["vault:read"],
}


def permissions_to_scope(permissions: str, role: str = "") -> dict:
    """
    将 Enclave permissions 字符串转换为 scope dict。
    """
    perms = PERMISSIONS_MAP.get(permissions, [])
    return {
        "permissions": perms,
        "resource_pattern": "*",
        "role": role,
    }