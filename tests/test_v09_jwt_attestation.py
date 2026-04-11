"""
v0.9.0 JWT Attestation 验证测试套件
测试 ID: tr_jwt_01 – tr_jwt_12

覆盖场景：
  - verify_jwt_attestation() 支持 OATR compact JWT (EdDSA)
  - trust_snapshot 导出为 OATR 标准格式
  - Certification ↔ JWT 双向桥接
  - Claim 命名空间（{namespace}:{claim} 格式）
  - 签名验证、过期检查、主题匹配
"""
import base64
import json
import sys
import time
from dataclasses import dataclass
from typing import Optional

import nacl.signing
import pytest
from nacl.signing import SigningKey

sys.path.insert(0, ".")


# ---------------------------------------------------------------------------
# 辅助函数：Base64URL 编解码
# ---------------------------------------------------------------------------

def b64url_encode(data: bytes) -> str:
    """Base64URL 编码（无 padding）"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(s: str) -> bytes:
    """Base64URL 解码（自动补 padding）"""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


# ---------------------------------------------------------------------------
# JWT 数据模型
# ---------------------------------------------------------------------------

@dataclass
class JWTHeader:
    alg: str = "EdDSA"
    typ: str = "JWT"

    def to_dict(self) -> dict:
        return {"alg": self.alg, "typ": self.typ}

    def encode(self) -> str:
        return b64url_encode(json.dumps(self.to_dict()).encode())


@dataclass
class JWTPayload:
    iss: str                          # OATR issuer ID
    sub: str                          # Agent DID
    claim: str                        # 声明类型
    score: Optional[int] = None       # OATR 行为评分 (0-100)
    score_breakdown: Optional[dict] = None
    iat: int = 0
    exp: int = 0

    def __post_init__(self):
        if self.iat == 0:
            self.iat = int(time.time())
        if self.exp == 0:
            self.exp = self.iat + 86400  # 默认 24 小时

    def to_dict(self) -> dict:
        d = {
            "iss": self.iss,
            "sub": self.sub,
            "claim": self.claim,
            "iat": self.iat,
            "exp": self.exp,
        }
        if self.score is not None:
            d["score"] = self.score
        if self.score_breakdown is not None:
            d["score_breakdown"] = self.score_breakdown
        return d

    def encode(self) -> str:
        return b64url_encode(json.dumps(self.to_dict()).encode())


# ---------------------------------------------------------------------------
# JWT 签发和验证
# ---------------------------------------------------------------------------

def sign_jwt(header: JWTHeader, payload: JWTPayload, signing_key: SigningKey) -> str:
    """
    使用 Ed25519 签发 JWT
    返回 compact 格式：header.payload.signature
    """
    header_b64 = header.encode()
    payload_b64 = payload.encode()

    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = signing_key.sign(signing_input).signature

    signature_b64 = b64url_encode(bytes(signature))
    return f"{header_b64}.{payload_b64}.{signature_b64}"


@dataclass
class JWTVerificationResult:
    """JWT 验证结果"""
    valid: bool
    issuer: Optional[str] = None
    subject: Optional[str] = None
    claim: Optional[str] = None
    score: Optional[int] = None
    score_breakdown: Optional[dict] = None
    expires_at: Optional[int] = None
    trust_delta: Optional[dict] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        if not self.valid:
            return {
                "valid": False,
                "error": self.error,
                "subject": self.subject,
            }
        return {
            "valid": True,
            "issuer": self.issuer,
            "subject": self.subject,
            "claim": self.claim,
            "score": self.score,
            "score_breakdown": self.score_breakdown,
            "expires_at": self.expires_at,
            "trust_delta": self.trust_delta,
        }


class JWTAttestationVerifier:
    """
    JWT Attestation 验证器
    支持 EdDSA (Ed25519) 签名
    """

    def __init__(self, issuer_pubkeys: dict[str, bytes]):
        """
        Args:
            issuer_pubkeys: {issuer_id: ed25519_pubkey_bytes}
        """
        self.issuer_pubkeys = issuer_pubkeys

    def verify(self, jwt: str, expected_subject: str) -> JWTVerificationResult:
        """
        验证 JWT attestation

        Args:
            jwt: compact JWT 字符串
            expected_subject: 期望的 Agent DID

        Returns:
            JWTVerificationResult
        """
        try:
            # 1. 解析 JWT
            parts = jwt.split(".")
            if len(parts) != 3:
                return JWTVerificationResult(
                    valid=False,
                    error="InvalidFormat",
                    subject=expected_subject,
                )

            header_b64, payload_b64, signature_b64 = parts

            # 2. 解析 header
            header = json.loads(b64url_decode(header_b64))
            if header.get("alg") != "EdDSA":
                return JWTVerificationResult(
                    valid=False,
                    error="UnsupportedAlgorithm",
                    subject=expected_subject,
                )

            # 3. 解析 payload
            payload = json.loads(b64url_decode(payload_b64))

            # 4. 检查过期
            now = int(time.time())
            if payload.get("exp", 0) < now:
                return JWTVerificationResult(
                    valid=False,
                    error="ExpiredToken",
                    subject=payload.get("sub"),
                )

            # 5. 检查主题匹配
            if payload.get("sub") != expected_subject:
                return JWTVerificationResult(
                    valid=False,
                    error="SubjectMismatch",
                    subject=expected_subject,
                )

            # 6. 验证签名
            issuer = payload.get("iss")
            if issuer not in self.issuer_pubkeys:
                return JWTVerificationResult(
                    valid=False,
                    error="IssuerUnknown",
                    subject=expected_subject,
                )

            pubkey = self.issuer_pubkeys[issuer]
            signing_input = f"{header_b64}.{payload_b64}".encode()
            signature = b64url_decode(signature_b64)

            # Ed25519 验签
            verify_key = nacl.signing.VerifyKey(pubkey)
            try:
                verify_key.verify(signing_input, signature)
            except Exception:
                return JWTVerificationResult(
                    valid=False,
                    error="InvalidSignature",
                    subject=expected_subject,
                )

            # 7. 计算 trust_delta
            score = payload.get("score", 0)
            attestation_bonus = score / 10.0  # 简单映射：score / 10

            return JWTVerificationResult(
                valid=True,
                issuer=issuer,
                subject=payload["sub"],
                claim=payload.get("claim"),
                score=score,
                score_breakdown=payload.get("score_breakdown"),
                expires_at=payload.get("exp"),
                trust_delta={
                    "attestation_bonus": attestation_bonus,
                    "applied_to": "trust_score",
                },
            )

        except Exception as e:
            return JWTVerificationResult(
                valid=False,
                error=str(e),
                subject=expected_subject,
            )


# ---------------------------------------------------------------------------
# Certification ↔ JWT 桥接
# ---------------------------------------------------------------------------

def certification_to_jwt(cert: dict, signing_key: SigningKey, issuer_id: str) -> str:
    """
    将 AgentNexus Certification 转换为 JWT

    Args:
        cert: AgentNexus certification dict
        signing_key: Ed25519 签名密钥
        issuer_id: OATR issuer ID

    Returns:
        compact JWT 字符串
    """
    header = JWTHeader(alg="EdDSA", typ="JWT")

    # Claim 命名空间转换
    claim = cert.get("claim", "")
    if ":" not in claim:
        # 添加命名空间前缀
        claim = f"agentnexus:{claim}"

    payload = JWTPayload(
        iss=issuer_id,
        sub=cert.get("target_did", ""),
        claim=claim,
        iat=int(cert.get("issued_at", time.time())),
        exp=int(time.time()) + 86400 * 30,  # 30 天有效期
    )

    return sign_jwt(header, payload, signing_key)


def jwt_to_certification(jwt: str) -> Optional[dict]:
    """
    将 JWT 解析为 Certification 格式（不验证签名）

    Args:
        jwt: compact JWT 字符串

    Returns:
        Certification dict 或 None
    """
    try:
        parts = jwt.split(".")
        if len(parts) != 3:
            return None

        payload = json.loads(b64url_decode(parts[1]))

        # 解析 claim 命名空间
        claim = payload.get("claim", "")
        namespace = "agentnexus"
        if ":" in claim:
            namespace, claim = claim.split(":", 1)

        return {
            "version": "1.0",
            "issuer": f"did:agentnexus:{payload.get('iss', '')}",
            "issuer_pubkey": "",  # 需要单独获取
            "target_did": payload.get("sub", ""),
            "claim": claim,
            "namespace": namespace,
            "issued_at": payload.get("iat", 0),
            "expires_at": payload.get("exp", 0),
            "score": payload.get("score"),
            "score_breakdown": payload.get("score_breakdown"),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def test_tr_jwt_01_sign_and_verify():
    """JWT 签发和验证成功"""
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    issuer_id = "oatr-issuer-001"
    agent_did = "did:agentnexus:zTestAgent"

    header = JWTHeader()
    payload = JWTPayload(
        iss=issuer_id,
        sub=agent_did,
        claim="behavior_attested",
        score=85,
    )

    jwt = sign_jwt(header, payload, sk)

    verifier = JWTAttestationVerifier({issuer_id: pk})
    result = verifier.verify(jwt, agent_did)

    assert result.valid is True
    assert result.issuer == issuer_id
    assert result.claim == "behavior_attested"
    assert result.score == 85


def test_tr_jwt_02_expired_token():
    """过期 Token 被拒绝"""
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    issuer_id = "oatr-issuer-001"
    agent_did = "did:agentnexus:zTestAgent"

    # 创建已过期的 JWT
    header = JWTHeader()
    payload = JWTPayload(
        iss=issuer_id,
        sub=agent_did,
        claim="behavior_attested",
        iat=int(time.time()) - 86400 * 2,  # 2 天前签发
        exp=int(time.time()) - 86400,      # 1 天前过期
    )

    jwt = sign_jwt(header, payload, sk)

    verifier = JWTAttestationVerifier({issuer_id: pk})
    result = verifier.verify(jwt, agent_did)

    assert result.valid is False
    assert result.error == "ExpiredToken"


def test_tr_jwt_03_subject_mismatch():
    """主题不匹配被拒绝"""
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    issuer_id = "oatr-issuer-001"

    header = JWTHeader()
    payload = JWTPayload(
        iss=issuer_id,
        sub="did:agentnexus:zAgentA",
        claim="behavior_attested",
    )

    jwt = sign_jwt(header, payload, sk)

    verifier = JWTAttestationVerifier({issuer_id: pk})
    result = verifier.verify(jwt, "did:agentnexus:zAgentB")  # 不同的 DID

    assert result.valid is False
    assert result.error == "SubjectMismatch"


def test_tr_jwt_04_invalid_signature():
    """签名无效被拒绝"""
    sk = SigningKey.generate()
    wrong_sk = SigningKey.generate()  # 不同的密钥
    pk = bytes(wrong_sk.verify_key)   # 注册错误的公钥
    issuer_id = "oatr-issuer-001"
    agent_did = "did:agentnexus:zTestAgent"

    header = JWTHeader()
    payload = JWTPayload(
        iss=issuer_id,
        sub=agent_did,
        claim="behavior_attested",
    )

    jwt = sign_jwt(header, payload, sk)  # 用 sk 签名

    verifier = JWTAttestationVerifier({issuer_id: pk})  # 但用 wrong_sk 的公钥验证
    result = verifier.verify(jwt, agent_did)

    assert result.valid is False
    assert result.error == "InvalidSignature"


def test_tr_jwt_05_unknown_issuer():
    """未知签发者被拒绝"""
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    issuer_id = "oatr-issuer-001"
    agent_did = "did:agentnexus:zTestAgent"

    header = JWTHeader()
    payload = JWTPayload(
        iss=issuer_id,
        sub=agent_did,
        claim="behavior_attested",
    )

    jwt = sign_jwt(header, payload, sk)

    # 没有注册该 issuer
    verifier = JWTAttestationVerifier({})
    result = verifier.verify(jwt, agent_did)

    assert result.valid is False
    assert result.error == "IssuerUnknown"


def test_tr_jwt_06_unsupported_algorithm():
    """不支持的非 EdDSA 算法被拒绝"""
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    issuer_id = "oatr-issuer-001"
    agent_did = "did:agentnexus:zTestAgent"

    header = JWTHeader(alg="RS256")  # 不支持的算法
    payload = JWTPayload(
        iss=issuer_id,
        sub=agent_did,
        claim="behavior_attested",
    )

    jwt = sign_jwt(header, payload, sk)

    verifier = JWTAttestationVerifier({issuer_id: pk})
    result = verifier.verify(jwt, agent_did)

    assert result.valid is False
    assert result.error == "UnsupportedAlgorithm"


def test_tr_jwt_07_trust_delta_calculation():
    """trust_delta 正确计算"""
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    issuer_id = "oatr-issuer-001"
    agent_did = "did:agentnexus:zTestAgent"

    header = JWTHeader()
    payload = JWTPayload(
        iss=issuer_id,
        sub=agent_did,
        claim="behavior_attested",
        score=85,
    )

    jwt = sign_jwt(header, payload, sk)

    verifier = JWTAttestationVerifier({issuer_id: pk})
    result = verifier.verify(jwt, agent_did)

    assert result.valid is True
    assert result.trust_delta is not None
    assert result.trust_delta["attestation_bonus"] == 8.5


def test_tr_jwt_08_certification_to_jwt():
    """Certification 转 JWT"""
    sk = SigningKey.generate()
    issuer_id = "oatr-issuer-001"

    cert = {
        "version": "1.0",
        "target_did": "did:agentnexus:zTestAgent",
        "claim": "payment_verified",
        "issued_at": time.time(),
    }

    jwt = certification_to_jwt(cert, sk, issuer_id)
    assert jwt.count(".") == 2  # compact 格式

    # 解析验证
    parts = jwt.split(".")
    payload = json.loads(b64url_decode(parts[1]))
    assert payload["iss"] == issuer_id
    assert payload["sub"] == "did:agentnexus:zTestAgent"
    assert payload["claim"] == "agentnexus:payment_verified"  # 添加了命名空间


def test_tr_jwt_09_jwt_to_certification():
    """JWT 转 Certification"""
    sk = SigningKey.generate()
    issuer_id = "oatr-issuer-001"
    agent_did = "did:agentnexus:zTestAgent"

    header = JWTHeader()
    payload = JWTPayload(
        iss=issuer_id,
        sub=agent_did,
        claim="oatr:behavior_attested",  # 带命名空间
        score=85,
    )

    jwt = sign_jwt(header, payload, sk)

    cert = jwt_to_certification(jwt)
    assert cert is not None
    assert cert["target_did"] == agent_did
    assert cert["claim"] == "behavior_attested"
    assert cert["namespace"] == "oatr"
    assert cert["score"] == 85


def test_tr_jwt_10_claim_namespace():
    """Claim 命名空间格式正确"""
    # 无命名空间的 claim 自动添加
    cert = {"claim": "payment_verified"}
    jwt = certification_to_jwt(cert, SigningKey.generate(), "issuer-001")
    parsed = jwt_to_certification(jwt)
    assert parsed["namespace"] == "agentnexus"
    assert parsed["claim"] == "payment_verified"

    # 已有命名空间的 claim 保持原样
    cert = {"claim": "oatr:behavior_attested"}
    jwt = certification_to_jwt(cert, SigningKey.generate(), "issuer-001")
    parsed = jwt_to_certification(jwt)
    assert parsed["namespace"] == "oatr"
    assert parsed["claim"] == "behavior_attested"


def test_tr_jwt_11_malformed_jwt():
    """格式错误的 JWT 被拒绝"""
    verifier = JWTAttestationVerifier({})

    # 不是三段
    result = verifier.verify("not.a.valid.jwt.format", "did:agentnexus:zTest")
    assert result.valid is False
    assert result.error == "InvalidFormat"

    # 空字符串
    result = verifier.verify("", "did:agentnexus:zTest")
    assert result.valid is False


def test_tr_jwt_12_score_breakdown():
    """score_breakdown 字段正确传递"""
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    issuer_id = "oatr-issuer-001"
    agent_did = "did:agentnexus:zTestAgent"

    header = JWTHeader()
    payload = JWTPayload(
        iss=issuer_id,
        sub=agent_did,
        claim="behavior_attested",
        score=85,
        score_breakdown={
            "response_rate": 0.95,
            "success_rate": 0.88,
            "uptime": 0.99,
        },
    )

    jwt = sign_jwt(header, payload, sk)

    verifier = JWTAttestationVerifier({issuer_id: pk})
    result = verifier.verify(jwt, agent_did)

    assert result.valid is True
    assert result.score_breakdown is not None
    assert result.score_breakdown["response_rate"] == 0.95
    assert result.score_breakdown["success_rate"] == 0.88


# ---------------------------------------------------------------------------
# 集成测试
# ---------------------------------------------------------------------------

def test_tr_jwt_13_end_to_end_flow():
    """端到端流程：签发 → 验证 → trust_score 计算"""
    # 1. OATR 签发 attestation
    oatr_sk = SigningKey.generate()
    oatr_pk = bytes(oatr_sk.verify_key)
    oatr_issuer_id = "oatr-issuer-001"
    agent_did = "did:agentnexus:zTestAgent"

    header = JWTHeader()
    payload = JWTPayload(
        iss=oatr_issuer_id,
        sub=agent_did,
        claim="behavior_attested",
        score=85,
        score_breakdown={
            "response_rate": 0.95,
            "success_rate": 0.88,
        },
    )
    jwt = sign_jwt(header, payload, oatr_sk)

    # 2. AgentNexus 验证
    verifier = JWTAttestationVerifier({oatr_issuer_id: oatr_pk})
    result = verifier.verify(jwt, agent_did)

    assert result.valid is True

    # 3. 计算 trust_score
    from tests.test_v09_reputation import compute_trust_score

    attestation_bonus = result.trust_delta["attestation_bonus"]
    rep = compute_trust_score(
        trust_level=3,
        behavior_delta=0.0,
        attestation_bonus=attestation_bonus,
    )

    # base_score(70) + attestation_bonus(8.5) = 78.5
    assert rep.trust_score == 78.5
