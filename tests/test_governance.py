"""
tests/test_governance.py
ADR-014 GovernanceClient 测试套件

覆盖：
  - MolTrustClient / APSClient 正常流程（mock HTTP）
  - 超时降级（fail-open）
  - API 错误响应
  - GovernanceRegistry 聚合 + get_highest_trust
  - JWS 验证（verify_jws / extract_jwk_public_key / get_jws_kid）
  - JWKS 缓存（命中 / 过期 / 刷新）
  - verify_attestation（过期拒绝 / 签名验证）
  - create_default_registry
"""
import asyncio
import base64
import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nacl.signing import SigningKey

from agent_net.common.governance import (
    APSClient,
    CapabilityRequest,
    GovernanceAttestation,
    GovernanceRegistry,
    MolTrustClient,
    create_default_registry,
    extract_jwk_public_key,
    get_jws_kid,
    verify_jws,
)

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

TEST_DID = "did:agentnexus:z6MkTestAgent"


def _make_moltrust_response(decision="permit", trust_score=75, passport_grade=2):
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    return {
        "signal_type": "governance_attestation",
        "iss": "api.moltrust.ch",
        "sub": TEST_DID,
        "decision": decision,
        "trust_score": trust_score,
        "expires_at": future,
        "active_constraints": {
            "scope": ["data:read", "commerce:checkout"],
            "spend_limit": 500,
            "passport_grade": passport_grade,
            "validity_window": {},
        },
        "jws": "",
    }


def _make_aps_response(decision="permit", trust_score=60):
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    return {
        "signal_type": "governance_attestation",
        "iss": "gateway.aeoess.com",
        "sub": TEST_DID,
        "decision": decision,
        "trust_score": trust_score,
        "passport_grade": 1,
        "expires_at": future,
        "active_constraints": {
            "scope": ["data:read"],
            "spend_limit": 100,
            "validity_window": {},
        },
        "sig": "",
    }


def _make_mock_response(data: dict, status: int = 200):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=data)
    mock_resp.text = AsyncMock(return_value=json.dumps(data))
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    return mock_resp


def _make_mock_session(response):
    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=response)
    mock_session.get = MagicMock(return_value=response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def _make_ed25519_jws(payload: dict) -> tuple[str, str]:
    """生成真实 Ed25519 JWS，返回 (jws, public_key_hex)"""
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key

    header = {"alg": "EdDSA", "kid": "test-key-1"}
    header_b64 = base64.urlsafe_b64encode(
        json.dumps(header).encode()
    ).rstrip(b"=").decode()
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()

    signing_input = f"{header_b64}.{payload_b64}".encode()
    signed = signing_key.sign(signing_input)
    sig_b64 = base64.urlsafe_b64encode(signed.signature).rstrip(b"=").decode()

    jws = f"{header_b64}.{payload_b64}.{sig_b64}"
    pubkey_hex = bytes(verify_key).hex()
    return jws, pubkey_hex


# ---------------------------------------------------------------------------
# MolTrustClient 测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gov_01_moltrust_permit():
    """MolTrustClient 正常 permit 响应"""
    client = MolTrustClient(api_key="test-key")
    resp_data = _make_moltrust_response("permit", trust_score=75, passport_grade=2)

    with patch("aiohttp.ClientSession", return_value=_make_mock_session(
        _make_mock_response(resp_data)
    )):
        att = await client.validate_capabilities(
            TEST_DID, [CapabilityRequest(scope="data:read")]
        )

    assert att.decision == "permit"
    assert att.trust_score == 75
    assert att.passport_grade == 2
    assert att.is_permitted is True
    assert "data:read" in att.scopes
    assert att.spend_limit == 500
    assert att.issuer == "api.moltrust.ch"


@pytest.mark.asyncio
async def test_gov_02_moltrust_deny():
    """MolTrustClient deny 响应"""
    client = MolTrustClient(api_key="test-key")
    resp_data = _make_moltrust_response("deny", trust_score=10, passport_grade=0)

    with patch("aiohttp.ClientSession", return_value=_make_mock_session(
        _make_mock_response(resp_data)
    )):
        att = await client.validate_capabilities(
            TEST_DID, [CapabilityRequest(scope="commerce:transact")]
        )

    assert att.decision == "deny"
    assert att.is_permitted is False


@pytest.mark.asyncio
async def test_gov_03_moltrust_api_error():
    """MolTrustClient API 错误时抛出 ValueError"""
    client = MolTrustClient(api_key="test-key")

    with patch("aiohttp.ClientSession", return_value=_make_mock_session(
        _make_mock_response({"error": "unauthorized"}, status=401)
    )):
        with pytest.raises(ValueError, match="MolTrust API error: 401"):
            await client.validate_capabilities(
                TEST_DID, [CapabilityRequest(scope="data:read")]
            )


@pytest.mark.asyncio
async def test_gov_04_moltrust_timeout():
    """MolTrustClient 超时时 Registry 降级为 deny（fail-open 由 Registry 处理）"""
    client = MolTrustClient(api_key="test-key", timeout=0.001)

    mock_session = MagicMock()
    mock_resp = AsyncMock()
    mock_resp.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(Exception):
            await client.validate_capabilities(
                TEST_DID, [CapabilityRequest(scope="data:read")]
            )


# ---------------------------------------------------------------------------
# APSClient 测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gov_05_aps_permit():
    """APSClient 正常 permit 响应"""
    client = APSClient()
    resp_data = _make_aps_response("permit", trust_score=60)

    with patch("aiohttp.ClientSession", return_value=_make_mock_session(
        _make_mock_response(resp_data)
    )):
        att = await client.validate_capabilities(
            TEST_DID, [CapabilityRequest(scope="data:read")]
        )

    assert att.decision == "permit"
    assert att.trust_score == 60
    assert att.issuer == "gateway.aeoess.com"
    assert att.is_permitted is True


@pytest.mark.asyncio
async def test_gov_06_aps_no_api_key():
    """APSClient 不需要 API Key"""
    client = APSClient()
    assert client.api_key is None


# ---------------------------------------------------------------------------
# GovernanceRegistry 测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gov_07_registry_aggregates_results():
    """Registry 聚合多个客户端结果"""
    registry = GovernanceRegistry()

    moltrust_att = GovernanceAttestation(
        signal_type="governance_attestation",
        issuer="api.moltrust.ch",
        subject=TEST_DID,
        decision="permit",
        trust_score=75,
    )
    aps_att = GovernanceAttestation(
        signal_type="governance_attestation",
        issuer="gateway.aeoess.com",
        subject=TEST_DID,
        decision="conditional",
        trust_score=50,
    )

    mock_moltrust = AsyncMock()
    mock_moltrust.validate_capabilities = AsyncMock(return_value=moltrust_att)
    mock_aps = AsyncMock()
    mock_aps.validate_capabilities = AsyncMock(return_value=aps_att)

    registry.clients["moltrust"] = mock_moltrust
    registry.clients["aps"] = mock_aps

    results = await registry.validate_capabilities(
        TEST_DID, [CapabilityRequest(scope="data:read")]
    )

    assert "moltrust" in results
    assert "aps" in results
    assert results["moltrust"].decision == "permit"
    assert results["aps"].decision == "conditional"


@pytest.mark.asyncio
async def test_gov_08_registry_client_failure_returns_deny():
    """Registry 中某个客户端失败时返回 deny attestation（不抛出异常）"""
    registry = GovernanceRegistry()

    mock_client = AsyncMock()
    mock_client.validate_capabilities = AsyncMock(
        side_effect=asyncio.TimeoutError("timeout")
    )
    registry.clients["failing"] = mock_client

    results = await registry.validate_capabilities(
        TEST_DID, [CapabilityRequest(scope="data:read")]
    )

    assert results["failing"].decision == "deny"
    assert "timeout" in results["failing"].raw_response.get("error", "")


@pytest.mark.asyncio
async def test_gov_09_registry_get_highest_trust():
    """get_highest_trust 返回最高信任级别"""
    registry = GovernanceRegistry()

    results = {
        "moltrust": GovernanceAttestation(
            signal_type="governance_attestation",
            issuer="api.moltrust.ch",
            subject=TEST_DID,
            decision="permit",
            trust_score=75,
        ),
        "aps": GovernanceAttestation(
            signal_type="governance_attestation",
            issuer="gateway.aeoess.com",
            subject=TEST_DID,
            decision="deny",
            trust_score=20,
        ),
    }

    best = registry.get_highest_trust(results)
    assert best.decision == "permit"
    assert best.trust_score == 75


def test_gov_10_get_highest_trust_empty():
    """get_highest_trust 空结果返回 deny"""
    registry = GovernanceRegistry()
    best = registry.get_highest_trust({})
    assert best.decision == "deny"


def test_gov_11_get_highest_trust_same_decision_picks_higher_score():
    """同 decision 时按 trust_score 排序"""
    registry = GovernanceRegistry()
    results = {
        "a": GovernanceAttestation(
            signal_type="governance_attestation",
            issuer="a",
            subject=TEST_DID,
            decision="permit",
            trust_score=60,
        ),
        "b": GovernanceAttestation(
            signal_type="governance_attestation",
            issuer="b",
            subject=TEST_DID,
            decision="permit",
            trust_score=90,
        ),
    }
    best = registry.get_highest_trust(results)
    assert best.trust_score == 90


@pytest.mark.asyncio
async def test_gov_12_registry_specific_clients():
    """Registry 支持指定客户端子集"""
    registry = GovernanceRegistry()

    att = GovernanceAttestation(
        signal_type="governance_attestation",
        issuer="api.moltrust.ch",
        subject=TEST_DID,
        decision="permit",
        trust_score=75,
    )
    mock_moltrust = AsyncMock()
    mock_moltrust.validate_capabilities = AsyncMock(return_value=att)
    mock_aps = AsyncMock()
    mock_aps.validate_capabilities = AsyncMock(return_value=att)

    registry.clients["moltrust"] = mock_moltrust
    registry.clients["aps"] = mock_aps

    results = await registry.validate_capabilities(
        TEST_DID, [CapabilityRequest(scope="data:read")], clients=["moltrust"]
    )

    assert "moltrust" in results
    assert "aps" not in results
    mock_aps.validate_capabilities.assert_not_called()


# ---------------------------------------------------------------------------
# JWS 验证测试
# ---------------------------------------------------------------------------

def test_gov_13_verify_jws_valid():
    """verify_jws 验证有效签名"""
    jws, pubkey_hex = _make_ed25519_jws({"sub": TEST_DID, "decision": "permit"})
    assert verify_jws(jws, pubkey_hex) is True


def test_gov_14_verify_jws_invalid_signature():
    """verify_jws 拒绝无效签名"""
    jws, _ = _make_ed25519_jws({"sub": TEST_DID})
    _, other_pubkey = _make_ed25519_jws({"sub": "other"})
    assert verify_jws(jws, other_pubkey) is False


def test_gov_15_verify_jws_malformed():
    """verify_jws 拒绝格式错误的 JWS"""
    assert verify_jws("not.a.valid.jws.format", "aabbcc") is False
    assert verify_jws("only.two", "aabbcc") is False


def test_gov_16_extract_jwk_public_key():
    """extract_jwk_public_key 从 JWKS 提取公钥"""
    signing_key = SigningKey.generate()
    pubkey_bytes = bytes(signing_key.verify_key)
    x_b64 = base64.urlsafe_b64encode(pubkey_bytes).rstrip(b"=").decode()

    jwks = {
        "keys": [
            {"kid": "key-1", "kty": "OKP", "crv": "Ed25519", "x": x_b64},
            {"kid": "key-2", "kty": "OKP", "crv": "Ed25519", "x": "other"},
        ]
    }

    result = extract_jwk_public_key(jwks, "key-1")
    assert result == pubkey_bytes.hex()

    assert extract_jwk_public_key(jwks, "nonexistent") is None


def test_gov_17_get_jws_kid():
    """get_jws_kid 从 JWS header 提取 kid"""
    jws, _ = _make_ed25519_jws({"sub": TEST_DID})
    kid = get_jws_kid(jws)
    assert kid == "test-key-1"


def test_gov_18_get_jws_kid_malformed():
    """get_jws_kid 格式错误时返回 None"""
    assert get_jws_kid("bad") is None
    assert get_jws_kid("a.b") is None


# ---------------------------------------------------------------------------
# JWKS 缓存测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gov_19_jwks_cache_hit():
    """JWKS 缓存命中时不重复请求"""
    registry = GovernanceRegistry()
    mock_client = MagicMock()
    mock_client.base_url = "https://api.moltrust.ch"
    mock_client.get_jwks_url = MagicMock(return_value="https://api.moltrust.ch/.well-known/jwks.json")
    mock_client.fetch_jwks = AsyncMock(return_value={"keys": []})
    registry.clients["moltrust"] = mock_client

    # 预填缓存
    registry.jwks_cache["https://api.moltrust.ch/.well-known/jwks.json"] = (
        {"keys": []}, time.time()
    )

    att = GovernanceAttestation(
        signal_type="governance_attestation",
        issuer="api.moltrust.ch",
        subject=TEST_DID,
        decision="permit",
        jws="bad.jws.format",  # 会在 verify_jws 前失败
    )

    await registry.verify_attestation(att, "moltrust")
    mock_client.fetch_jwks.assert_not_called()


@pytest.mark.asyncio
async def test_gov_20_jwks_cache_expired_refetch():
    """JWKS 缓存过期时重新请求"""
    registry = GovernanceRegistry()
    registry.jwks_ttl = 1  # 1 秒 TTL

    mock_client = MagicMock()
    mock_client.base_url = "https://api.moltrust.ch"
    mock_client.get_jwks_url = MagicMock(return_value="https://api.moltrust.ch/.well-known/jwks.json")
    mock_client.fetch_jwks = AsyncMock(return_value={"keys": []})
    registry.clients["moltrust"] = mock_client

    # 写入已过期的缓存
    registry.jwks_cache["https://api.moltrust.ch/.well-known/jwks.json"] = (
        {"keys": []}, time.time() - 10  # 10 秒前
    )

    att = GovernanceAttestation(
        signal_type="governance_attestation",
        issuer="api.moltrust.ch",
        subject=TEST_DID,
        decision="permit",
        jws="a.b.c",
    )

    await registry.verify_attestation(att, "moltrust")
    mock_client.fetch_jwks.assert_called_once()


# ---------------------------------------------------------------------------
# verify_attestation 测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gov_21_verify_attestation_expired():
    """verify_attestation 拒绝过期 attestation"""
    registry = GovernanceRegistry()

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    att = GovernanceAttestation(
        signal_type="governance_attestation",
        issuer="api.moltrust.ch",
        subject=TEST_DID,
        decision="permit",
        expires_at=past,
        jws="",
    )

    result = await registry.verify_attestation(att)
    assert result is False


@pytest.mark.asyncio
async def test_gov_22_verify_attestation_no_jws():
    """verify_attestation 无 JWS 时信任（过期检查通过）"""
    registry = GovernanceRegistry()

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    att = GovernanceAttestation(
        signal_type="governance_attestation",
        issuer="api.moltrust.ch",
        subject=TEST_DID,
        decision="permit",
        expires_at=future,
        jws="",
    )

    result = await registry.verify_attestation(att)
    assert result is True


@pytest.mark.asyncio
async def test_gov_23_verify_attestation_valid_jws():
    """verify_attestation 验证有效 JWS"""
    registry = GovernanceRegistry()

    payload = {"sub": TEST_DID, "decision": "permit"}
    jws, pubkey_hex = _make_ed25519_jws(payload)
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    x_b64 = base64.urlsafe_b64encode(pubkey_bytes).rstrip(b"=").decode()

    jwks = {"keys": [{"kid": "test-key-1", "kty": "OKP", "crv": "Ed25519", "x": x_b64}]}

    mock_client = MagicMock()
    mock_client.base_url = "https://api.moltrust.ch"
    mock_client.get_jwks_url = MagicMock(return_value="https://api.moltrust.ch/.well-known/jwks.json")
    mock_client.fetch_jwks = AsyncMock(return_value=jwks)
    registry.clients["moltrust"] = mock_client

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    att = GovernanceAttestation(
        signal_type="governance_attestation",
        issuer="api.moltrust.ch",
        subject=TEST_DID,
        decision="permit",
        expires_at=future,
        jws=jws,
    )

    result = await registry.verify_attestation(att, "moltrust")
    assert result is True


@pytest.mark.asyncio
async def test_gov_24_verify_attestation_invalid_jws():
    """verify_attestation 拒绝无效 JWS"""
    registry = GovernanceRegistry()

    _, pubkey_hex = _make_ed25519_jws({"sub": "other"})
    jws_tampered, _ = _make_ed25519_jws({"sub": TEST_DID})
    pubkey_bytes = bytes.fromhex(pubkey_hex)
    x_b64 = base64.urlsafe_b64encode(pubkey_bytes).rstrip(b"=").decode()

    jwks = {"keys": [{"kid": "test-key-1", "kty": "OKP", "crv": "Ed25519", "x": x_b64}]}

    mock_client = MagicMock()
    mock_client.base_url = "https://api.moltrust.ch"
    mock_client.get_jwks_url = MagicMock(return_value="https://api.moltrust.ch/.well-known/jwks.json")
    mock_client.fetch_jwks = AsyncMock(return_value=jwks)
    registry.clients["moltrust"] = mock_client

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    att = GovernanceAttestation(
        signal_type="governance_attestation",
        issuer="api.moltrust.ch",
        subject=TEST_DID,
        decision="permit",
        expires_at=future,
        jws=jws_tampered,  # 签名是另一个 key 的
    )

    result = await registry.verify_attestation(att, "moltrust")
    assert result is False


# ---------------------------------------------------------------------------
# GovernanceAttestation 辅助方法测试
# ---------------------------------------------------------------------------

def test_gov_25_attestation_grade_to_level():
    """grade_to_level 映射正确"""
    for grade, expected_level in [(0, 1), (1, 2), (2, 3), (3, 4)]:
        att = GovernanceAttestation(
            signal_type="governance_attestation",
            issuer="test",
            subject=TEST_DID,
            decision="permit",
            passport_grade=grade,
        )
        assert att.grade_to_level == expected_level


def test_gov_26_attestation_to_dict():
    """to_dict 包含所有必要字段"""
    att = GovernanceAttestation(
        signal_type="governance_attestation",
        issuer="api.moltrust.ch",
        subject=TEST_DID,
        decision="permit",
        trust_score=75,
        passport_grade=2,
    )
    d = att.to_dict()
    assert d["signal_type"] == "governance_attestation"
    assert d["decision"] == "permit"
    assert d["trust_score"] == 75
    assert "jws" in d


# ---------------------------------------------------------------------------
# create_default_registry 测试
# ---------------------------------------------------------------------------

def test_gov_27_create_default_registry_without_moltrust():
    """无 API Key 时只注册 APS"""
    registry = create_default_registry()
    assert "aps" in registry.clients
    assert "moltrust" not in registry.clients


def test_gov_28_create_default_registry_with_moltrust():
    """有 API Key 时同时注册 MolTrust 和 APS"""
    registry = create_default_registry(moltrust_api_key="test-key")
    assert "aps" in registry.clients
    assert "moltrust" in registry.clients


def test_gov_29_registry_unregister():
    """unregister 移除客户端"""
    registry = create_default_registry()
    assert registry.unregister("aps") is True
    assert "aps" not in registry.clients
    assert registry.unregister("nonexistent") is False
