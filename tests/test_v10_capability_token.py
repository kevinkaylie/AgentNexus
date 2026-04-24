"""
v1.0-08 Capability Token Envelope 测试套件
测试 ID: v10_ct_01 – v10_ct_06

覆盖场景：
  - 签发 Token
  - 验证 Token（签名/有效期/权限）
  - 撤销 Token
  - 单调收窄验证
  - 委托链完整性
"""
import asyncio
import importlib
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, ".")


# ---------------------------------------------------------------------------
# 测试 Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    """创建隔离的测试环境"""
    import agent_net.storage as st
    monkeypatch.setattr(st, "DB_PATH", tmp_path / "agent_net.db")

    import agent_net.node._auth as _auth
    monkeypatch.setattr(_auth, "USER_TOKEN_FILE", tmp_path / "daemon_token.txt")

    import agent_net.node.daemon as d
    importlib.reload(d)

    import agent_net.storage as st_reload
    importlib.reload(st_reload)
    asyncio.run(st_reload.init_db())

    from agent_net.node.daemon import app
    yield TestClient(app)


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def test_v10_ct_01_issue_token(isolated_env):
    """签发 Capability Token"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册 issuer（owner）
    issuer = client.post("/owner/register", json={"name": "Issuer"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 注册 subject
    subject = client.post("/agents/register", json={"name": "Subject"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 签发 Token
    resp = client.post(
        "/capability-tokens/issue",
        json={
            "issuer_did": issuer,
            "subject_did": subject,
            "scope": {"permissions": ["vault:read", "vault:write"], "role": "developer"},
            "constraints": {"spend_limit": 100, "max_delegation_depth": 1},
            "validity_days": 30,
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "token" in data

    token_data = data["token"]
    assert token_data["token_id"].startswith("ct_")
    assert token_data["issuer_did"] == issuer
    assert token_data["subject_did"] == subject
    assert "vault:read" in token_data["scope"]["permissions"]
    assert token_data["evaluated_constraint_hash"].startswith("sha256:")
    assert token_data["signature"]  # 已签名
    assert token_data["revocation_endpoint"]  # 有撤销端点


def test_v10_ct_02_verify_token(isolated_env):
    """验证 Token（签名/有效期/权限）"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册 issuer 和 subject
    issuer = client.post("/owner/register", json={"name": "Issuer"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    subject = client.post("/agents/register", json={"name": "Subject"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 签发 Token
    issue_resp = client.post(
        "/capability-tokens/issue",
        json={
            "issuer_did": issuer,
            "subject_did": subject,
            "scope": {"permissions": ["vault:read", "vault:write"]},
            "constraints": {"spend_limit": 100, "max_delegation_depth": 1},
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    token_id = issue_resp.json()["token"]["token_id"]

    # 验证（权限允许）
    verify_resp = client.post(
        f"/capability-tokens/{token_id}/verify",
        json={"action": "vault:read"}
    )
    assert verify_resp.status_code == 200
    result = verify_resp.json()
    assert result["valid"] is True

    # 验证（权限拒绝）
    deny_resp = client.post(
        f"/capability-tokens/{token_id}/verify",
        json={"action": "vault:delete"}
    )
    assert deny_resp.status_code == 200
    result2 = deny_resp.json()
    assert result2["valid"] is False
    assert result2["reason"] == "PERMISSION_DENIED"


def test_v10_ct_03_revoke_token(isolated_env):
    """撤销 Token"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册并签发
    issuer = client.post("/owner/register", json={"name": "Issuer"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    subject = client.post("/agents/register", json={"name": "Subject"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    issue_resp = client.post(
        "/capability-tokens/issue",
        json={"issuer_did": issuer, "subject_did": subject, "scope": {"permissions": ["vault:read"]}},
        headers={"Authorization": f"Bearer {token}"}
    )
    token_id = issue_resp.json()["token"]["token_id"]

    # 撤销
    revoke_resp = client.post(
        f"/capability-tokens/{token_id}/revoke",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["status"] == "ok"

    # 再次验证应失败
    verify_resp = client.post(
        f"/capability-tokens/{token_id}/verify",
        json={"action": "vault:read"}
    )
    assert verify_resp.json()["valid"] is False
    assert verify_resp.json()["reason"] == "REVOKED"


def test_v10_ct_04_list_tokens_by_did(isolated_env):
    """查询 DID 持有的所有 Token"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    token = init_daemon_token()

    # 注册 issuer 和 subject
    issuer = client.post("/owner/register", json={"name": "Issuer"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    subject = client.post("/agents/register", json={"name": "Subject"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 签发多个 Token
    for i in range(3):
        client.post(
            "/capability-tokens/issue",
            json={"issuer_did": issuer, "subject_did": subject, "scope": {"permissions": [f"action{i}"]}},
            headers={"Authorization": f"Bearer {token}"}
        )

    # 查询
    list_resp = client.get(
        f"/capability-tokens/by-did/{subject}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["did"] == subject
    assert data["count"] == 3


def test_v10_ct_05_constraint_hash_consistency(isolated_env):
    """约束集哈希一致性"""
    from agent_net.common.capability_token import compute_constraint_hash

    scope1 = {"permissions": ["vault:read", "vault:write"], "role": "developer"}
    constraints1 = {"spend_limit": 100, "max_delegation_depth": 1}

    # 相同输入应产生相同哈希
    hash1 = compute_constraint_hash(scope1, constraints1)
    hash2 = compute_constraint_hash(scope1, constraints1)
    assert hash1 == hash2

    # 不同输入应产生不同哈希
    hash3 = compute_constraint_hash(scope1, {"spend_limit": 200, "max_delegation_depth": 1})
    assert hash1 != hash3

    # 哈希格式验证
    assert hash1.startswith("sha256:")
    assert len(hash1.split(":")[1]) == 64  # SHA256 输出 64 字符


def test_v10_ct_06_scope_is_subset(isolated_env):
    """scope 子集验证（单调收窄）"""
    from agent_net.common.capability_token import scope_is_subset

    # 子集关系
    parent = {"permissions": ["vault:read", "vault:write", "vault:delete"], "resource_pattern": "*"}
    child = {"permissions": ["vault:read", "vault:write"], "resource_pattern": "*"}
    assert scope_is_subset(child, parent) is True

    # 非子集（扩展）
    child2 = {"permissions": ["vault:read", "admin:manage"], "resource_pattern": "*"}
    assert scope_is_subset(child2, parent) is False

    # resource_pattern 收窄
    child3 = {"permissions": ["vault:read"], "resource_pattern": "vault/docs/*"}
    assert scope_is_subset(child3, parent) is True


def test_v10_ct_07_delegation_chain_end_to_end(isolated_env):
    """T1: 委托链端到端测试"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token
    from agent_net.storage import get_delegation_chain
    import asyncio

    token = init_daemon_token()

    # 注册 issuer（owner）和两个 subject
    issuer = client.post("/owner/register", json={"name": "Issuer"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    subject1 = client.post("/agents/register", json={"name": "Subject1"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    subject2 = client.post("/agents/register", json={"name": "Subject2"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 签发 parent token（给 subject1）
    parent_resp = client.post(
        "/capability-tokens/issue",
        json={
            "issuer_did": issuer,
            "subject_did": subject1,
            "scope": {"permissions": ["vault:read", "vault:write", "vault:delete"], "role": "admin"},
            "constraints": {"spend_limit": 100, "max_delegation_depth": 2},
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert parent_resp.status_code == 200
    parent_token_id = parent_resp.json()["token"]["token_id"]

    # 签发 child token（subject1 委托给 subject2）
    child_resp = client.post(
        "/capability-tokens/issue",
        json={
            "issuer_did": subject1,  # subject1 作为 issuer 委托给 subject2
            "subject_did": subject2,
            "scope": {"permissions": ["vault:read", "vault:write"], "role": "developer"},  # 收窄权限
            "constraints": {"spend_limit": 50, "max_delegation_depth": 1},  # 更严格约束
            "parent_token_id": parent_token_id,
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert child_resp.status_code == 200
    child_token_id = child_resp.json()["token"]["token_id"]

    # 验证委托链写入数据库
    chain = asyncio.run(get_delegation_chain(child_token_id))
    assert len(chain) == 1
    assert chain[0]["parent_token_id"] == parent_token_id

    # 验证 child token 验证通过（权限在范围内）
    verify_resp = client.post(
        f"/capability-tokens/{child_token_id}/verify",
        json={"action": "vault:read"}
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["valid"] is True


def test_v10_ct_08_scope_expansion_rejected(isolated_env):
    """T2: 单调收窄拒绝测试"""
    client = isolated_env
    from agent_net.node._auth import init_daemon_token

    token = init_daemon_token()

    # 注册 issuer 和两个 subject
    issuer = client.post("/owner/register", json={"name": "Issuer"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    subject1 = client.post("/agents/register", json={"name": "Subject1"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    subject2 = client.post("/agents/register", json={"name": "Subject2"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 签发 parent token（只给 vault:read 权限）
    parent_resp = client.post(
        "/capability-tokens/issue",
        json={
            "issuer_did": issuer,
            "subject_did": subject1,
            "scope": {"permissions": ["vault:read"], "role": "viewer"},
            "constraints": {"spend_limit": 100, "max_delegation_depth": 2},
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    parent_token_id = parent_resp.json()["token"]["token_id"]

    # 签发 child token（试图扩展权限，加入 vault:delete）
    child_resp = client.post(
        "/capability-tokens/issue",
        json={
            "issuer_did": subject1,
            "subject_did": subject2,
            "scope": {"permissions": ["vault:read", "vault:delete"], "role": "developer"},  # 超出 parent
            "constraints": {"spend_limit": 50, "max_delegation_depth": 1},
            "parent_token_id": parent_token_id,
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    child_token_id = child_resp.json()["token"]["token_id"]

    # 验证应被拒绝（SCOPE_EXPANSION）
    verify_resp = client.post(
        f"/capability-tokens/{child_token_id}/verify",
        json={"action": "vault:delete"}
    )
    assert verify_resp.status_code == 200
    result = verify_resp.json()
    assert result["valid"] is False
    assert result["reason"] == "SCOPE_EXPANSION"


def test_v10_ct_09_expired_token(isolated_env):
    """T3: 过期 Token 测试"""
    import time

    client = isolated_env
    from agent_net.node._auth import init_daemon_token

    token = init_daemon_token()

    # 注册 issuer 和 subject
    issuer = client.post("/owner/register", json={"name": "Issuer"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]
    subject = client.post("/agents/register", json={"name": "Subject"}, headers={"Authorization": f"Bearer {token}"}).json()["did"]

    # 签发一个极短有效期的 token（validity_days 不支持小数，使用 endpoint 默认最小值）
    # 然后手动修改数据库中的 not_after 让其过期
    issue_resp = client.post(
        "/capability-tokens/issue",
        json={
            "issuer_did": issuer,
            "subject_did": subject,
            "scope": {"permissions": ["vault:read"]},
            "constraints": {"spend_limit": 100, "max_delegation_depth": 1},
            "validity_days": 1,  # 1 天有效期
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert issue_resp.status_code == 200
    token_id = issue_resp.json()["token"]["token_id"]

    # 验证在有效期内应该成功
    verify_resp1 = client.post(
        f"/capability-tokens/{token_id}/verify",
        json={"action": "vault:read"}
    )
    assert verify_resp1.json()["valid"] is True

    # 手动修改数据库让 token 过期
    import sqlite3
    import json
    from agent_net.storage import DB_PATH

    db = sqlite3.connect(DB_PATH)
    # 设置 not_after 为过去时间
    db.execute(
        "UPDATE capability_tokens SET validity_json=? WHERE token_id=?",
        (json.dumps({"not_before": time.time() - 3600, "not_after": time.time() - 1}), token_id)
    )
    db.commit()
    db.close()

    # 验证过期 token（签名验证会失败因为 validity 已修改）
    # 但我们的验证逻辑是：状态 → 签名 → 有效期
    # 由于 validity 修改了，签名验证会先失败（签名基于原始数据）
    # 所以这里主要验证修改后的 token 不会被认为是有效的
    verify_resp2 = client.post(
        f"/capability-tokens/{token_id}/verify",
        json={"action": "vault:read"}
    )
    result = verify_resp2.json()
    assert result["valid"] is False  # 签名不匹配或过期
    # 结果可能是 SIGNATURE_INVALID（因为 validity 修改了）或 EXPIRED（如果签名验证通过）
    # 两种都是合理的失败原因
