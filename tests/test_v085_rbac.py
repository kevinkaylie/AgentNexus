"""
v0.8.5 基于 DID 的 RBAC 测试套件
测试 ID: tr_rbac_01 – tr_rbac_15

覆盖场景：
  - 角色定义（architect/developer/reviewer）
  - 不同角色对 Vault 的读写权限
  - 权限检查在 Relay 层执行
  - 权限变更需要管理者 DID 签名授权
"""
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest
from nacl.signing import SigningKey

sys.path.insert(0, ".")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class RoleDefinition:
    """角色定义"""
    name: str
    permissions: list[str]  # ["vault:read", "vault:write", "task:propose", ...]
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "permissions": self.permissions,
            "description": self.description,
        }


@dataclass
class RoleAssignment:
    """角色分配"""
    enclave_id: str
    did: str
    role: str
    assigned_by: str          # 分配者 DID
    assigned_at: float
    signature: str = ""       # 管理者签名

    def to_dict(self) -> dict:
        return {
            "enclave_id": self.enclave_id,
            "did": self.did,
            "role": self.role,
            "assigned_by": self.assigned_by,
            "assigned_at": self.assigned_at,
            "signature": self.signature,
        }


@dataclass
class PermissionChange:
    """权限变更请求"""
    enclave_id: str
    target_did: str
    new_role: str
    requester_did: str
    timestamp: float
    signature: str = ""       # 管理者签名（授权）

    def signing_payload(self) -> str:
        return f"{self.enclave_id}:{self.target_did}:{self.new_role}:{self.timestamp}"


# ---------------------------------------------------------------------------
# 预定义角色
# ---------------------------------------------------------------------------

DEFAULT_ROLES: dict[str, RoleDefinition] = {
    "architect": RoleDefinition(
        name="architect",
        permissions=[
            "vault:read", "vault:write", "vault:delete",
            "task:propose", "task:assign", "task:approve",
            "member:invite", "member:remove",
            "role:assign",
        ],
        description="架构师：最高权限，可以管理成员和分配角色",
    ),
    "developer": RoleDefinition(
        name="developer",
        permissions=[
            "vault:read", "vault:write",
            "task:claim", "task:complete",
            "state:notify",
        ],
        description="开发者：可以读写 Vault、认领和完成任务",
    ),
    "reviewer": RoleDefinition(
        name="reviewer",
        permissions=[
            "vault:read",
            "task:review", "task:approve",
            "state:notify",
        ],
        description="评审者：可以读取 Vault、审核任务",
    ),
    "observer": RoleDefinition(
        name="observer",
        permissions=[
            "vault:read",
        ],
        description="观察者：只读权限",
    ),
}


# ---------------------------------------------------------------------------
# RBAC 存储引擎
# ---------------------------------------------------------------------------

class RBACStore:
    """RBAC 存储引擎"""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._roles: dict[str, RoleDefinition] = dict(DEFAULT_ROLES)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS role_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enclave_id TEXT NOT NULL,
                did TEXT NOT NULL,
                role TEXT NOT NULL,
                assigned_by TEXT NOT NULL,
                assigned_at REAL NOT NULL,
                signature TEXT,
                UNIQUE(enclave_id, did)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_roles (
                enclave_id TEXT NOT NULL,
                role_name TEXT NOT NULL,
                permissions TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (enclave_id, role_name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS permission_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enclave_id TEXT NOT NULL,
                target_did TEXT NOT NULL,
                old_role TEXT,
                new_role TEXT NOT NULL,
                requester_did TEXT NOT NULL,
                timestamp REAL NOT NULL,
                signature TEXT,
                verified INTEGER DEFAULT 0
            )
        """)

    # ── 角色管理 ─────────────────────────────────────────────────────

    def get_role(self, role_name: str, enclave_id: str = "") -> Optional[RoleDefinition]:
        """获取角色定义"""
        # 先检查自定义角色
        if enclave_id:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM custom_roles WHERE enclave_id = ? AND role_name = ?",
                (enclave_id, role_name),
            ).fetchone()
            if row:
                return RoleDefinition(
                    name=row["role_name"],
                    permissions=json.loads(row["permissions"]),
                )
        # 回退到默认角色
        return self._roles.get(role_name)

    def create_custom_role(
        self,
        enclave_id: str,
        role_name: str,
        permissions: list[str],
    ) -> RoleDefinition:
        """创建自定义角色"""
        conn = self._get_conn()
        now = time.time()

        conn.execute(
            """
            INSERT OR REPLACE INTO custom_roles
            (enclave_id, role_name, permissions, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (enclave_id, role_name, json.dumps(permissions), now),
        )
        conn.commit()

        return RoleDefinition(name=role_name, permissions=permissions)

    # ── 角色分配 ─────────────────────────────────────────────────────

    def assign_role(
        self,
        enclave_id: str,
        did: str,
        role: str,
        assigned_by: str,
        signature: str = "",
    ) -> RoleAssignment:
        """分配角色"""
        conn = self._get_conn()
        now = time.time()

        conn.execute(
            """
            INSERT OR REPLACE INTO role_assignments
            (enclave_id, did, role, assigned_by, assigned_at, signature)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (enclave_id, did, role, assigned_by, now, signature),
        )
        conn.commit()

        return RoleAssignment(
            enclave_id=enclave_id,
            did=did,
            role=role,
            assigned_by=assigned_by,
            assigned_at=now,
            signature=signature,
        )

    def get_role_assignment(self, enclave_id: str, did: str) -> Optional[RoleAssignment]:
        """获取角色分配"""
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT * FROM role_assignments
            WHERE enclave_id = ? AND did = ?
            """,
            (enclave_id, did),
        ).fetchone()

        if row is None:
            return None

        return RoleAssignment(
            enclave_id=row["enclave_id"],
            did=row["did"],
            role=row["role"],
            assigned_by=row["assigned_by"],
            assigned_at=row["assigned_at"],
            signature=row["signature"] or "",
        )

    def remove_role_assignment(self, enclave_id: str, did: str) -> bool:
        """移除角色分配"""
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM role_assignments WHERE enclave_id = ? AND did = ?",
            (enclave_id, did),
        )
        conn.commit()
        return cursor.rowcount > 0

    # ── 权限变更记录 ─────────────────────────────────────────────────

    def record_permission_change(
        self,
        change: PermissionChange,
        old_role: str | None = None,
    ) -> int:
        """记录权限变更"""
        conn = self._get_conn()
        cursor = conn.execute(
            """
            INSERT INTO permission_changes
            (enclave_id, target_did, old_role, new_role, requester_did, timestamp, signature, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                change.enclave_id,
                change.target_did,
                old_role,
                change.new_role,
                change.requester_did,
                change.timestamp,
                change.signature,
                1 if change.signature else 0,
            ),
        )
        conn.commit()
        return cursor.lastrowid


# ---------------------------------------------------------------------------
# RBAC 权限检查器
# ---------------------------------------------------------------------------

class RBACChecker:
    """RBAC 权限检查器"""

    def __init__(self, store: RBACStore):
        self.store = store

    def get_permissions(self, enclave_id: str, did: str) -> list[str]:
        """获取 DID 在指定 Enclave 的权限列表"""
        assignment = self.store.get_role_assignment(enclave_id, did)
        if assignment is None:
            return []

        role = self.store.get_role(assignment.role, enclave_id)
        return role.permissions if role else []

    def has_permission(self, enclave_id: str, did: str, permission: str) -> bool:
        """检查 DID 是否有特定权限"""
        permissions = self.get_permissions(enclave_id, did)
        return permission in permissions

    def can_read_vault(self, enclave_id: str, did: str) -> bool:
        return self.has_permission(enclave_id, did, "vault:read")

    def can_write_vault(self, enclave_id: str, did: str) -> bool:
        return self.has_permission(enclave_id, did, "vault:write")

    def can_delete_vault(self, enclave_id: str, did: str) -> bool:
        return self.has_permission(enclave_id, did, "vault:delete")

    def can_assign_roles(self, enclave_id: str, did: str) -> bool:
        return self.has_permission(enclave_id, did, "role:assign")

    def can_propose_task(self, enclave_id: str, did: str) -> bool:
        return self.has_permission(enclave_id, did, "task:propose")

    def can_claim_task(self, enclave_id: str, did: str) -> bool:
        return self.has_permission(enclave_id, did, "task:claim")


# ---------------------------------------------------------------------------
# 签名验证器
# ---------------------------------------------------------------------------

class PermissionChangeVerifier:
    """权限变更签名验证器"""

    def __init__(self, admin_pubkeys: dict[str, bytes]):
        """
        Args:
            admin_pubkeys: {admin_did: ed25519_pubkey_bytes}
        """
        self.admin_pubkeys = admin_pubkeys

    def verify_permission_change(
        self,
        change: PermissionChange,
        enclave_admins: list[str],
    ) -> bool:
        """
        验证权限变更签名

        签名验证流程：
        1. 签名者必须是 enclave 的管理员之一
        2. 使用签名者的公钥验证签名
        """
        if not change.signature:
            return False

        # 解析签名（格式：signer_did|signature_hex，用 | 分隔避免 DID 中 : 冲突）
        try:
            signer_did, sig_hex = change.signature.rsplit("|", 1)
        except ValueError:
            return False

        # 检查签名者是否是管理员
        if signer_did not in enclave_admins:
            return False

        # 获取签名者公钥
        pubkey = self.admin_pubkeys.get(signer_did)
        if pubkey is None:
            return False

        # 验证签名
        import nacl.signing
        verify_key = nacl.signing.VerifyKey(pubkey)
        payload = change.signing_payload().encode()

        try:
            verify_key.verify(payload, bytes.fromhex(sig_hex))
            return True
        except Exception:
            return False

    @staticmethod
    def sign_permission_change(
        change: PermissionChange,
        signer_did: str,
        signing_key: SigningKey,
    ) -> str:
        """为权限变更生成签名"""
        payload = change.signing_payload().encode()
        signature = signing_key.sign(payload).signature.hex()
        return f"{signer_did}|{signature}"


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestRoleDefinition:
    """角色定义测试"""

    def test_tr_rbac_01_default_roles_exist(self, tmp_path):
        """默认角色存在"""
        store = RBACStore(tmp_path / "rbac.db")

        assert store.get_role("architect") is not None
        assert store.get_role("developer") is not None
        assert store.get_role("reviewer") is not None
        assert store.get_role("observer") is not None

    def test_tr_rbac_02_architect_permissions(self, tmp_path):
        """架构师拥有最高权限"""
        store = RBACStore(tmp_path / "rbac.db")

        role = store.get_role("architect")
        assert "vault:read" in role.permissions
        assert "vault:write" in role.permissions
        assert "vault:delete" in role.permissions
        assert "role:assign" in role.permissions
        assert "member:invite" in role.permissions

    def test_tr_rbac_03_developer_permissions(self, tmp_path):
        """开发者权限：读写 Vault、认领任务"""
        store = RBACStore(tmp_path / "rbac.db")

        role = store.get_role("developer")
        assert "vault:read" in role.permissions
        assert "vault:write" in role.permissions
        assert "task:claim" in role.permissions
        assert "vault:delete" not in role.permissions

    def test_tr_rbac_04_reviewer_permissions(self, tmp_path):
        """评审者权限：只读 Vault、审核任务"""
        store = RBACStore(tmp_path / "rbac.db")

        role = store.get_role("reviewer")
        assert "vault:read" in role.permissions
        assert "task:review" in role.permissions
        assert "vault:write" not in role.permissions

    def test_tr_rbac_05_observer_permissions(self, tmp_path):
        """观察者权限：只读"""
        store = RBACStore(tmp_path / "rbac.db")

        role = store.get_role("observer")
        assert "vault:read" in role.permissions
        assert len(role.permissions) == 1


class TestRoleAssignment:
    """角色分配测试"""

    def test_tr_rbac_06_assign_role(self, tmp_path):
        """分配角色"""
        store = RBACStore(tmp_path / "rbac.db")

        assignment = store.assign_role(
            enclave_id="enclave_123",
            did="did:agentnexus:zUser",
            role="developer",
            assigned_by="did:agentnexus:zAdmin",
        )

        assert assignment.role == "developer"
        assert assignment.assigned_by == "did:agentnexus:zAdmin"

    def test_tr_rbac_07_get_role_assignment(self, tmp_path):
        """获取角色分配"""
        store = RBACStore(tmp_path / "rbac.db")

        store.assign_role(
            enclave_id="enclave_123",
            did="did:agentnexus:zUser",
            role="developer",
            assigned_by="did:agentnexus:zAdmin",
        )

        assignment = store.get_role_assignment("enclave_123", "did:agentnexus:zUser")
        assert assignment is not None
        assert assignment.role == "developer"

    def test_tr_rbac_08_update_role(self, tmp_path):
        """更新角色（重新分配）"""
        store = RBACStore(tmp_path / "rbac.db")

        # 初始分配
        store.assign_role(
            enclave_id="enclave_123",
            did="did:agentnexus:zUser",
            role="developer",
            assigned_by="did:agentnexus:zAdmin",
        )

        # 更新为 architect
        store.assign_role(
            enclave_id="enclave_123",
            did="did:agentnexus:zUser",
            role="architect",
            assigned_by="did:agentnexus:zAdmin",
        )

        assignment = store.get_role_assignment("enclave_123", "did:agentnexus:zUser")
        assert assignment.role == "architect"


class TestRBACChecker:
    """RBAC 权限检查测试"""

    def test_tr_rbac_09_check_vault_read_permission(self, tmp_path):
        """检查 Vault 读取权限"""
        store = RBACStore(tmp_path / "rbac.db")
        checker = RBACChecker(store)

        store.assign_role("enclave_1", "did:user_dev", "developer", "did:admin")
        store.assign_role("enclave_1", "did:user_obs", "observer", "did:admin")

        assert checker.can_read_vault("enclave_1", "did:user_dev")
        assert checker.can_read_vault("enclave_1", "did:user_obs")

    def test_tr_rbac_10_check_vault_write_permission(self, tmp_path):
        """检查 Vault 写入权限"""
        store = RBACStore(tmp_path / "rbac.db")
        checker = RBACChecker(store)

        store.assign_role("enclave_1", "did:user_dev", "developer", "did:admin")
        store.assign_role("enclave_1", "did:user_obs", "observer", "did:admin")

        assert checker.can_write_vault("enclave_1", "did:user_dev")
        assert not checker.can_write_vault("enclave_1", "did:user_obs")

    def test_tr_rbac_11_check_role_assign_permission(self, tmp_path):
        """检查角色分配权限"""
        store = RBACStore(tmp_path / "rbac.db")
        checker = RBACChecker(store)

        store.assign_role("enclave_1", "did:user_arch", "architect", "did:admin")
        store.assign_role("enclave_1", "did:user_dev", "developer", "did:admin")

        assert checker.can_assign_roles("enclave_1", "did:user_arch")
        assert not checker.can_assign_roles("enclave_1", "did:user_dev")

    def test_tr_rbac_12_no_role_no_permission(self, tmp_path):
        """无角色则无权限"""
        store = RBACStore(tmp_path / "rbac.db")
        checker = RBACChecker(store)

        assert not checker.can_read_vault("enclave_1", "did:unknown")
        assert not checker.can_write_vault("enclave_1", "did:unknown")


class TestPermissionChangeSignature:
    """权限变更签名测试"""

    def test_tr_rbac_13_sign_permission_change(self, tmp_path):
        """签名权限变更"""
        admin_sk = SigningKey.generate()
        admin_pk = bytes(admin_sk.verify_key)
        admin_did = "did:agentnexus:zAdmin"

        change = PermissionChange(
            enclave_id="enclave_123",
            target_did="did:agentnexus:zUser",
            new_role="developer",
            requester_did=admin_did,
            timestamp=time.time(),
        )

        signature = PermissionChangeVerifier.sign_permission_change(
            change, admin_did, admin_sk
        )

        assert signature.startswith(f"{admin_did}|")
        assert len(signature) > len(admin_did) + 1

    def test_tr_rbac_14_verify_valid_signature(self, tmp_path):
        """验证有效签名"""
        admin_sk = SigningKey.generate()
        admin_pk = bytes(admin_sk.verify_key)
        admin_did = "did:agentnexus:zAdmin"

        verifier = PermissionChangeVerifier({admin_did: admin_pk})

        change = PermissionChange(
            enclave_id="enclave_123",
            target_did="did:agentnexus:zUser",
            new_role="developer",
            requester_did=admin_did,
            timestamp=time.time(),
        )

        change.signature = PermissionChangeVerifier.sign_permission_change(
            change, admin_did, admin_sk
        )

        assert verifier.verify_permission_change(change, [admin_did])

    def test_tr_rbac_15_reject_invalid_signature(self, tmp_path):
        """拒绝无效签名"""
        admin_sk = SigningKey.generate()
        attacker_sk = SigningKey.generate()
        admin_pk = bytes(admin_sk.verify_key)
        attacker_pk = bytes(attacker_sk.verify_key)
        admin_did = "did:agentnexus:zAdmin"
        attacker_did = "did:agentnexus:zAttacker"

        verifier = PermissionChangeVerifier({admin_did: admin_pk})

        change = PermissionChange(
            enclave_id="enclave_123",
            target_did="did:agentnexus:zUser",
            new_role="architect",  # 尝试提权
            requester_did=attacker_did,
            timestamp=time.time(),
        )

        # 攻击者用自己的密钥签名
        change.signature = PermissionChangeVerifier.sign_permission_change(
            change, attacker_did, attacker_sk
        )

        # 签名者不是管理员，验证失败
        assert not verifier.verify_permission_change(change, [admin_did])


class TestCustomRole:
    """自定义角色测试"""

    def test_tr_rbac_16_create_custom_role(self, tmp_path):
        """创建自定义角色"""
        store = RBACStore(tmp_path / "rbac.db")

        role = store.create_custom_role(
            enclave_id="enclave_123",
            role_name="qa_engineer",
            permissions=["vault:read", "task:claim", "task:test"],
        )

        assert role.name == "qa_engineer"
        assert "vault:read" in role.permissions
        assert "task:test" in role.permissions

    def test_tr_rbac_17_assign_custom_role(self, tmp_path):
        """分配自定义角色"""
        store = RBACStore(tmp_path / "rbac.db")
        checker = RBACChecker(store)

        # 创建自定义角色
        store.create_custom_role(
            enclave_id="enclave_123",
            role_name="qa_engineer",
            permissions=["vault:read", "task:test"],
        )

        # 分配角色
        store.assign_role(
            enclave_id="enclave_123",
            did="did:agentnexus:zQA",
            role="qa_engineer",
            assigned_by="did:agentnexus:zAdmin",
        )

        # 验证权限
        assert checker.can_read_vault("enclave_123", "did:agentnexus:zQA")
        assert not checker.can_write_vault("enclave_123", "did:agentnexus:zQA")


class TestRBACIntegration:
    """RBAC 集成测试"""

    def test_tr_rbac_18_full_workflow(self, tmp_path):
        """完整工作流：定义角色 → 分配 → 权限检查 → 变更 → 签名验证"""
        store = RBACStore(tmp_path / "rbac.db")
        checker = RBACChecker(store)

        # 1. 设置管理员
        admin_sk = SigningKey.generate()
        admin_pk = bytes(admin_sk.verify_key)
        admin_did = "did:agentnexus:zAdmin"

        verifier = PermissionChangeVerifier({admin_did: admin_pk})

        # 2. 分配初始角色
        store.assign_role("enclave_1", admin_did, "architect", admin_did)
        store.assign_role("enclave_1", "did:user_dev", "developer", admin_did)

        # 3. 权限检查
        assert checker.can_write_vault("enclave_1", admin_did)
        assert checker.can_write_vault("enclave_1", "did:user_dev")
        assert not checker.can_delete_vault("enclave_1", "did:user_dev")

        # 4. 权限变更（提升为 architect）
        change = PermissionChange(
            enclave_id="enclave_1",
            target_did="did:user_dev",
            new_role="architect",
            requester_did=admin_did,
            timestamp=time.time(),
        )
        change.signature = PermissionChangeVerifier.sign_permission_change(
            change, admin_did, admin_sk
        )

        # 5. 验证签名
        assert verifier.verify_permission_change(change, [admin_did])

        # 6. 执行变更
        old_role = store.get_role_assignment("enclave_1", "did:user_dev").role
        store.record_permission_change(change, old_role)
        store.assign_role("enclave_1", "did:user_dev", "architect", admin_did)

        # 7. 验证新权限
        assert checker.can_delete_vault("enclave_1", "did:user_dev")
        assert checker.can_assign_roles("enclave_1", "did:user_dev")
