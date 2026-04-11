"""
AgentNexusRuntimeVerifier 测试套件
测试 ID: tr_rt_01 – tr_rt_12

覆盖场景：
  - L1 ~ L4 信任级别晋升
  - Giskard CA payment_verified (L3)
  - Giskard CA entity_verified (L4)
  - 多 CA 架构并列验证
  - DID 解析失败
  - 公钥不匹配（verified=False）
  - 篡改 cert 无法提升 trust_level
  - live vs cached resolution_status
  - trusted_cas 公钥错配（防冒充 CA）
  - trust_score 范围与 live 加成
  - to_dict() 序列化格式
  - daemon POST /runtime/verify 端点集成
"""
import asyncio
import importlib
import json
import sys
import time
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

sys.path.insert(0, ".")

from agent_net.common.did import DIDResolutionResult
from agent_net.common.profile import create_certification
from agent_net.common.runtime_verifier import (
    AgentNexusRuntimeVerifier,
    RuntimeVerification,
    TRUST_PERMISSIONS,
    TRUST_SPENDING_LIMITS,
    make_storage_cert_fetcher,
)


# ── 辅助 / 工厂 ──────────────────────────────────────────────

def _gen_key():
    """生成 (SigningKey, pubkey_hex) 对"""
    sk = SigningKey.generate()
    return sk, bytes(sk.verify_key).hex()


def _make_result(did: str, sk: SigningKey, source: str = "local_db") -> DIDResolutionResult:
    """构造 DIDResolutionResult（跳过真实网络）"""
    return DIDResolutionResult(
        did=did,
        method="agentnexus",
        public_key=bytes(sk.verify_key),
        did_document={},
        metadata={"source": source},
    )


class MockResolver:
    """可控 DIDResolver 替身"""

    def __init__(self, results: dict | None = None, fail: bool = False):
        self._results = results or {}
        self._fail = fail

    async def resolve(self, did: str):
        if self._fail:
            raise ConnectionError("simulated DID resolution failure")
        return self._results.get(did)


def _make_cert_fetcher(certs_by_did: dict):
    async def fetcher(did: str) -> list[dict]:
        return certs_by_did.get(did, [])
    return fetcher


def _no_certs():
    async def fetcher(_did: str) -> list[dict]:
        return []
    return fetcher


def run(coro):
    return asyncio.run(coro)


# ── 常量 ─────────────────────────────────────────────────────

GISKARD_CA_DID = "did:agent:giskard_ca"

AGENT_DID = "did:agentnexus:zTestAgent001"


# ── 测试用例 ──────────────────────────────────────────────────

def test_tr_rt_01_l1_no_certs():
    """L1: DID 解析成功，无 cert → trust_level=1, permissions=[discover,read]"""
    sk, pk_hex = _gen_key()
    resolver = MockResolver({AGENT_DID: _make_result(AGENT_DID, sk, "local_db")})
    verifier = AgentNexusRuntimeVerifier(resolver=resolver, cert_fetcher=_no_certs())

    result = run(verifier.verify(AGENT_DID, pk_hex))

    assert result.verified is True
    assert result.trust_level == 1
    assert result.did_resolution_status == "live"
    assert result.pinned_public_key == pk_hex
    assert result.permissions == TRUST_PERMISSIONS[1]
    assert result.spending_limit == TRUST_SPENDING_LIMITS[1] == 0
    assert result.entity_verified is False
    assert result.scope is None
    # 时间戳格式验证
    datetime.fromisoformat(result.execution_timestamp)


def test_tr_rt_02_l2_untrusted_cert():
    """L2: 持有第三方有效 cert（issuer 不在 trusted_cas）→ trust_level=2"""
    sk, pk_hex = _gen_key()
    ca_sk, _ = _gen_key()
    ca_did = "did:agent:random_ca"

    cert = create_certification(
        target_did=AGENT_DID,
        issuer_did=ca_did,
        issuer_signing_key=ca_sk,
        claim="some_claim",
        evidence="https://proof.example.com/123",
    )

    resolver = MockResolver({AGENT_DID: _make_result(AGENT_DID, sk, "relay")})
    verifier = AgentNexusRuntimeVerifier(
        resolver=resolver,
        trusted_cas={},   # 空 trusted_cas → ca 不被信任
        cert_fetcher=_make_cert_fetcher({AGENT_DID: [cert]}),
    )

    result = run(verifier.verify(AGENT_DID, pk_hex))

    assert result.verified is True
    assert result.trust_level == 2
    assert "message" in result.permissions
    assert "transact" not in result.permissions
    assert result.spending_limit == TRUST_SPENDING_LIMITS[2] == 10


def test_tr_rt_03_l3_giskard_payment_verified():
    """L3: Giskard CA 签发 payment_verified cert → trust_level=3, transact 权限"""
    sk, pk_hex = _gen_key()
    giskard_sk, giskard_pk_hex = _gen_key()

    cert = create_certification(
        target_did=AGENT_DID,
        issuer_did=GISKARD_CA_DID,
        issuer_signing_key=giskard_sk,
        claim="payment_verified",
        evidence="arb:0x" + "a" * 64,   # Giskard evidence 格式
    )

    resolver = MockResolver({AGENT_DID: _make_result(AGENT_DID, sk, "local_db")})
    verifier = AgentNexusRuntimeVerifier(
        resolver=resolver,
        trusted_cas={GISKARD_CA_DID: giskard_pk_hex},
        cert_fetcher=_make_cert_fetcher({AGENT_DID: [cert]}),
    )

    result = run(verifier.verify(AGENT_DID, pk_hex))

    assert result.verified is True
    assert result.trust_level == 3
    assert "transact" in result.permissions
    assert "delegate" not in result.permissions
    assert result.spending_limit == TRUST_SPENDING_LIMITS[3] == 100
    assert result.entity_verified is False


def test_tr_rt_04_l4_entity_verified():
    """L4: Giskard CA 签发 entity_verified cert → trust_level=4, 全权限"""
    sk, pk_hex = _gen_key()
    giskard_sk, giskard_pk_hex = _gen_key()

    cert_payment = create_certification(
        target_did=AGENT_DID,
        issuer_did=GISKARD_CA_DID,
        issuer_signing_key=giskard_sk,
        claim="payment_verified",
        evidence="arb:0x" + "b" * 64,
    )
    cert_entity = create_certification(
        target_did=AGENT_DID,
        issuer_did=GISKARD_CA_DID,
        issuer_signing_key=giskard_sk,
        claim="entity_verified",
        evidence="arb:0x" + "c" * 64,
    )

    resolver = MockResolver({AGENT_DID: _make_result(AGENT_DID, sk, "local_db")})
    verifier = AgentNexusRuntimeVerifier(
        resolver=resolver,
        trusted_cas={GISKARD_CA_DID: giskard_pk_hex},
        cert_fetcher=_make_cert_fetcher({AGENT_DID: [cert_payment, cert_entity]}),
    )

    result = run(verifier.verify(AGENT_DID, pk_hex))

    assert result.trust_level == 4
    assert result.entity_verified is True
    assert "delegate" in result.permissions
    assert result.spending_limit == TRUST_SPENDING_LIMITS[4] == 1000


def test_tr_rt_05_did_resolution_failed():
    """DID 解析失败 → verified=False, status=failed, trust_score=0.0"""
    _, pk_hex = _gen_key()
    resolver = MockResolver(fail=True)
    verifier = AgentNexusRuntimeVerifier(resolver=resolver)

    result = run(verifier.verify("did:agentnexus:zNonExistent", pk_hex))

    assert result.verified is False
    assert result.did_resolution_status == "failed"
    assert result.trust_score == 0.0
    assert result.permissions == []


def test_tr_rt_06_key_mismatch():
    """公钥不匹配 → verified=False，但 trust_level / resolution_status 仍正常计算"""
    sk, _ = _gen_key()
    _, wrong_pk_hex = _gen_key()   # 故意传错误公钥

    resolver = MockResolver({AGENT_DID: _make_result(AGENT_DID, sk, "local_db")})
    verifier = AgentNexusRuntimeVerifier(resolver=resolver, cert_fetcher=_no_certs())

    result = run(verifier.verify(AGENT_DID, wrong_pk_hex))

    assert result.verified is False
    assert result.did_resolution_status == "live"
    assert result.trust_level == 1          # cert 正常走，只是 key 错
    assert result.pinned_public_key == bytes(sk.verify_key).hex()  # 固定的是解析到的


def test_tr_rt_07_tampered_cert_ignored():
    """篡改 cert（signature 被改）→ 无效，不提升 trust_level"""
    sk, pk_hex = _gen_key()
    giskard_sk, giskard_pk_hex = _gen_key()

    cert = create_certification(
        target_did=AGENT_DID,
        issuer_did=GISKARD_CA_DID,
        issuer_signing_key=giskard_sk,
        claim="payment_verified",
        evidence="arb:0x" + "d" * 64,
    )
    # 篡改签名
    tampered = dict(cert)
    tampered["signature"] = "00" * 64

    resolver = MockResolver({AGENT_DID: _make_result(AGENT_DID, sk, "local_db")})
    verifier = AgentNexusRuntimeVerifier(
        resolver=resolver,
        trusted_cas={GISKARD_CA_DID: giskard_pk_hex},
        cert_fetcher=_make_cert_fetcher({AGENT_DID: [tampered]}),
    )

    result = run(verifier.verify(AGENT_DID, pk_hex))

    assert result.trust_level == 1          # 篡改 cert 被跳过
    assert result.entity_verified is False


def test_tr_rt_08_cached_resolution_status():
    """cryptographic 来源 → did_resolution_status=cached，无 live 加成"""
    sk, pk_hex = _gen_key()
    resolver = MockResolver({AGENT_DID: _make_result(AGENT_DID, sk, "cryptographic")})
    verifier = AgentNexusRuntimeVerifier(resolver=resolver, cert_fetcher=_no_certs())

    result = run(verifier.verify(AGENT_DID, pk_hex))

    assert result.did_resolution_status == "cached"
    # L1 cached: 0.15，无加成
    assert abs(result.trust_score - 0.15) < 0.001


def test_tr_rt_09_wrong_ca_pubkey_rejected():
    """trusted_cas 中 CA DID 匹配但公钥错误 → 不信任该 cert，trust_level 不超过 L2"""
    sk, pk_hex = _gen_key()
    giskard_sk, giskard_pk_hex = _gen_key()
    _, fake_giskard_pk_hex = _gen_key()    # 注册了错误公钥

    cert = create_certification(
        target_did=AGENT_DID,
        issuer_did=GISKARD_CA_DID,
        issuer_signing_key=giskard_sk,
        claim="payment_verified",
        evidence="arb:0x" + "e" * 64,
    )

    resolver = MockResolver({AGENT_DID: _make_result(AGENT_DID, sk, "local_db")})
    verifier = AgentNexusRuntimeVerifier(
        resolver=resolver,
        trusted_cas={GISKARD_CA_DID: fake_giskard_pk_hex},  # 公钥故意错配
        cert_fetcher=_make_cert_fetcher({AGENT_DID: [cert]}),
    )

    result = run(verifier.verify(AGENT_DID, pk_hex))

    # cert 签名本身有效，所以 L2；但不被 trusted CA 承认，不到 L3
    assert result.trust_level == 2
    assert "transact" not in result.permissions


def test_tr_rt_10_multi_ca():
    """多 CA 场景：两个不同 CA 各签一条 cert，最高级别（L4）正确计算"""
    sk, pk_hex = _gen_key()
    ca1_sk, ca1_pk_hex = _gen_key()
    ca2_sk, ca2_pk_hex = _gen_key()
    ca1_did = "did:agent:giskard_ca"
    ca2_did = "did:agentnexus:zSomeOtherCA"

    cert1 = create_certification(
        target_did=AGENT_DID,
        issuer_did=ca1_did,
        issuer_signing_key=ca1_sk,
        claim="payment_verified",
        evidence="arb:0x" + "f" * 64,
    )
    cert2 = create_certification(
        target_did=AGENT_DID,
        issuer_did=ca2_did,
        issuer_signing_key=ca2_sk,
        claim="entity_verified",
        evidence="https://kyb.example.com/agent001",
    )

    resolver = MockResolver({AGENT_DID: _make_result(AGENT_DID, sk, "local_db")})
    verifier = AgentNexusRuntimeVerifier(
        resolver=resolver,
        trusted_cas={
            ca1_did: ca1_pk_hex,
            ca2_did: ca2_pk_hex,
        },
        cert_fetcher=_make_cert_fetcher({AGENT_DID: [cert1, cert2]}),
    )

    result = run(verifier.verify(AGENT_DID, pk_hex))

    assert result.trust_level == 4
    assert result.entity_verified is True


def test_tr_rt_11_trust_score_ranges():
    """trust_score 在各级别 × live/cached 下均在 [0, 1] 范围内"""
    sk, pk_hex = _gen_key()
    giskard_sk, giskard_pk_hex = _gen_key()
    did = AGENT_DID

    def _make_verifier(claim: str | None, source: str, num_certs: int):
        certs = []
        if claim:
            for _ in range(num_certs):
                certs.append(create_certification(
                    target_did=did,
                    issuer_did=GISKARD_CA_DID,
                    issuer_signing_key=giskard_sk,
                    claim=claim,
                    evidence="arb:0x" + "0" * 64,
                ))
        return AgentNexusRuntimeVerifier(
            resolver=MockResolver({did: _make_result(did, sk, source)}),
            trusted_cas={GISKARD_CA_DID: giskard_pk_hex},
            cert_fetcher=_make_cert_fetcher({did: certs}),
        )

    cases = [
        (None, "local_db"),            # L1 live
        (None, "cryptographic"),       # L1 cached
        ("payment_verified", "relay"), # L3 live
        ("entity_verified", "local_db"), # L4 live
    ]
    for claim, source in cases:
        v = _make_verifier(claim, source, 1)
        r = run(v.verify(did, pk_hex))
        assert 0.0 <= r.trust_score <= 1.0, f"out of range for {claim}/{source}: {r.trust_score}"

    # live 比 cached 分数高（L1 对比）
    v_live = _make_verifier(None, "local_db", 0)
    v_cached = _make_verifier(None, "cryptographic", 0)
    r_live = run(v_live.verify(did, pk_hex))
    r_cached = run(v_cached.verify(did, pk_hex))
    assert r_live.trust_score > r_cached.trust_score


def test_tr_rt_12_to_dict_format():
    """to_dict() 返回所有字段，类型和格式正确，可 JSON 序列化"""
    sk, pk_hex = _gen_key()
    giskard_sk, giskard_pk_hex = _gen_key()

    cert = create_certification(
        target_did=AGENT_DID,
        issuer_did=GISKARD_CA_DID,
        issuer_signing_key=giskard_sk,
        claim="payment_verified",
        evidence="arb:0x" + "a1" * 32,
    )

    resolver = MockResolver({AGENT_DID: _make_result(AGENT_DID, sk, "local_db")})
    verifier = AgentNexusRuntimeVerifier(
        resolver=resolver,
        trusted_cas={GISKARD_CA_DID: giskard_pk_hex},
        cert_fetcher=_make_cert_fetcher({AGENT_DID: [cert]}),
    )

    result = run(verifier.verify(AGENT_DID, pk_hex))
    d = result.to_dict()

    # 必需字段存在
    required_keys = {
        "verified", "trust_level", "trust_score", "permissions",
        "spending_limit", "did_resolution_status", "entity_verified",
        "execution_timestamp", "pinned_public_key", "scope",
    }
    assert required_keys == set(d.keys())

    # 类型检查
    assert isinstance(d["verified"], bool)
    assert isinstance(d["trust_level"], int)
    assert isinstance(d["trust_score"], float)
    assert isinstance(d["permissions"], list)
    assert isinstance(d["spending_limit"], int)
    assert d["did_resolution_status"] in ("live", "cached", "failed")
    assert isinstance(d["entity_verified"], bool)
    assert isinstance(d["execution_timestamp"], str)
    assert isinstance(d["pinned_public_key"], str)
    assert d["scope"] is None

    # 可 JSON 序列化（pipeline 需要）
    serialized = json.dumps(d)
    recovered = json.loads(serialized)
    assert recovered["trust_level"] == d["trust_level"]


# ── daemon 端点集成测试 ───────────────────────────────────────

@pytest.fixture()
def daemon_client(tmp_path, monkeypatch):
    """创建隔离的 daemon TestClient（复用现有测试模式）"""
    import agent_net.storage as st
    monkeypatch.setattr(st, "DB_PATH", tmp_path / "agent_net.db")

    import agent_net.node.daemon as d
    importlib.reload(d)

    import agent_net.node._auth as _auth; monkeypatch.setattr(_auth, "USER_TOKEN_FILE", tmp_path / "daemon_token.txt")

    with TestClient(d.app) as client:
        yield client, d


def test_tr_rt_daemon_01_runtime_verify_endpoint(daemon_client, tmp_path):
    """POST /runtime/verify 端点可通 HTTP 调用，返回 RuntimeVerification 结构"""
    client, d = daemon_client

    # 注册一个本地 agent，获取其 DID 和公钥
    from agent_net.node._auth import get_token as _get_token; token = _get_token()
    reg = client.post(
        "/agents/register",
        json={"name": "VerifyTestAgent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reg.status_code == 200
    agent_did = reg.json()["did"]

    # 通过 /profile 端点获取 NexusProfile（含 header.pubkey）
    profile_resp = client.get(f"/agents/{agent_did}/profile")
    assert profile_resp.status_code == 200

    pubkey_hex = profile_resp.json().get("header", {}).get("pubkey", "")
    assert pubkey_hex, "should have pubkey in NexusProfile header"

    resp = client.post(
        "/runtime/verify",
        json={"agent_did": agent_did, "agent_public_key": pubkey_hex},
    )
    assert resp.status_code == 200
    data = resp.json()

    # 验证字段完整性
    required_keys = {
        "verified", "trust_level", "trust_score", "permissions",
        "spending_limit", "did_resolution_status", "entity_verified",
        "execution_timestamp", "pinned_public_key", "scope",
    }
    assert required_keys.issubset(set(data.keys()))
    assert data["verified"] is True
    assert data["trust_level"] >= 1
    assert data["did_resolution_status"] in ("live", "cached", "failed")
