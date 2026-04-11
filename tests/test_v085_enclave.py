"""
v0.8.5 Enclave 群组测试套件
测试 ID: tr_enc_01 – tr_enc_15

覆盖场景：
  - 创建 Enclave（群组）
  - 成员 DID 列表管理
  - 共享 Vault 命名空间
  - Enclave 级别消息广播
  - 成员加入/退出权限验证
"""
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest

sys.path.insert(0, ".")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class EnclaveMember:
    """Enclave 成员"""
    did: str
    role: str  # "admin" / "member" / "observer"
    joined_at: float
    invited_by: str = ""

    def to_dict(self) -> dict:
        return {
            "did": self.did,
            "role": self.role,
            "joined_at": self.joined_at,
            "invited_by": self.invited_by,
        }


@dataclass
class Enclave:
    """Enclave 群组"""
    id: str                              # enclave_id
    name: str
    creator_did: str
    created_at: float
    members: list[EnclaveMember] = field(default_factory=list)
    vault_namespace: str = ""            # 关联的 Vault 命名空间
    status: str = "active"               # "active" / "archived"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "creator_did": self.creator_did,
            "created_at": self.created_at,
            "members": [m.to_dict() for m in self.members],
            "vault_namespace": self.vault_namespace,
            "status": self.status,
        }

    @property
    def admin_dids(self) -> list[str]:
        return [m.did for m in self.members if m.role == "admin"]

    @property
    def member_dids(self) -> list[str]:
        return [m.did for m in self.members if m.role in ("admin", "member")]

    @property
    def all_dids(self) -> list[str]:
        return [m.did for m in self.members]


# ---------------------------------------------------------------------------
# Enclave 存储引擎
# ---------------------------------------------------------------------------

class EnclaveStore:
    """Enclave 存储引擎"""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS enclaves (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                creator_did TEXT NOT NULL,
                created_at REAL NOT NULL,
                vault_namespace TEXT,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS enclave_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enclave_id TEXT NOT NULL,
                did TEXT NOT NULL,
                role TEXT NOT NULL,
                joined_at REAL NOT NULL,
                invited_by TEXT,
                UNIQUE(enclave_id, did),
                FOREIGN KEY (enclave_id) REFERENCES enclaves(id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_enclave_members_did
            ON enclave_members(did)
        """)

    # ── Enclave 操作 ────────────────────────────────────────────────

    def create_enclave(
        self,
        name: str,
        creator_did: str,
        initial_members: list[str] | None = None,
    ) -> Enclave:
        """创建 Enclave"""
        conn = self._get_conn()
        now = time.time()

        # 生成 enclave_id
        import hashlib
        enclave_id = f"enclave_{hashlib.md5(f'{name}{creator_did}{now}'.encode()).hexdigest()[:12]}"
        vault_namespace = f"vault_{enclave_id}"

        # 插入 enclave
        conn.execute(
            """
            INSERT INTO enclaves (id, name, creator_did, created_at, vault_namespace, status)
            VALUES (?, ?, ?, ?, ?, 'active')
            """,
            (enclave_id, name, creator_did, now, vault_namespace),
        )

        # 添加创建者为 admin
        conn.execute(
            """
            INSERT INTO enclave_members (enclave_id, did, role, joined_at, invited_by)
            VALUES (?, ?, 'admin', ?, ?)
            """,
            (enclave_id, creator_did, now, creator_did),
        )

        # 添加初始成员
        members = [EnclaveMember(did=creator_did, role="admin", joined_at=now, invited_by=creator_did)]
        if initial_members:
            for did in initial_members:
                if did != creator_did:
                    conn.execute(
                        """
                        INSERT INTO enclave_members (enclave_id, did, role, joined_at, invited_by)
                        VALUES (?, ?, 'member', ?, ?)
                        """,
                        (enclave_id, did, now, creator_did),
                    )
                    members.append(EnclaveMember(did=did, role="member", joined_at=now, invited_by=creator_did))

        conn.commit()

        return Enclave(
            id=enclave_id,
            name=name,
            creator_did=creator_did,
            created_at=now,
            members=members,
            vault_namespace=vault_namespace,
        )

    def get_enclave(self, enclave_id: str) -> Optional[Enclave]:
        """获取 Enclave"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM enclaves WHERE id = ?",
            (enclave_id,),
        ).fetchone()

        if row is None:
            return None

        # 获取成员
        member_rows = conn.execute(
            "SELECT * FROM enclave_members WHERE enclave_id = ?",
            (enclave_id,),
        ).fetchall()

        members = [
            EnclaveMember(
                did=m["did"],
                role=m["role"],
                joined_at=m["joined_at"],
                invited_by=m["invited_by"] or "",
            )
            for m in member_rows
        ]

        return Enclave(
            id=row["id"],
            name=row["name"],
            creator_did=row["creator_did"],
            created_at=row["created_at"],
            members=members,
            vault_namespace=row["vault_namespace"] or "",
            status=row["status"],
        )

    def list_enclaves(self, did: str) -> list[Enclave]:
        """列出 DID 所属的所有 Enclave"""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT e.* FROM enclaves e
            JOIN enclave_members em ON e.id = em.enclave_id
            WHERE em.did = ? AND e.status = 'active'
            """,
            (did,),
        ).fetchall()

        return [self.get_enclave(row["id"]) for row in rows]

    # ── 成员操作 ────────────────────────────────────────────────────

    def add_member(
        self,
        enclave_id: str,
        did: str,
        role: str,
        invited_by: str,
    ) -> Optional[EnclaveMember]:
        """添加成员"""
        conn = self._get_conn()

        # 检查是否已存在
        existing = conn.execute(
            "SELECT * FROM enclave_members WHERE enclave_id = ? AND did = ?",
            (enclave_id, did),
        ).fetchone()
        if existing:
            return None

        now = time.time()
        conn.execute(
            """
            INSERT INTO enclave_members (enclave_id, did, role, joined_at, invited_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (enclave_id, did, role, now, invited_by),
        )
        conn.commit()

        return EnclaveMember(did=did, role=role, joined_at=now, invited_by=invited_by)

    def remove_member(self, enclave_id: str, did: str) -> bool:
        """移除成员"""
        conn = self._get_conn()

        # 不能移除最后一个 admin
        enclave = self.get_enclave(enclave_id)
        if enclave and did in enclave.admin_dids and len(enclave.admin_dids) == 1:
            return False

        cursor = conn.execute(
            "DELETE FROM enclave_members WHERE enclave_id = ? AND did = ?",
            (enclave_id, did),
        )
        conn.commit()
        return cursor.rowcount > 0

    def update_member_role(self, enclave_id: str, did: str, new_role: str) -> bool:
        """更新成员角色"""
        conn = self._get_conn()

        # 不能移除最后一个 admin
        enclave = self.get_enclave(enclave_id)
        if enclave and did in enclave.admin_dids and new_role != "admin" and len(enclave.admin_dids) == 1:
            return False

        cursor = conn.execute(
            "UPDATE enclave_members SET role = ? WHERE enclave_id = ? AND did = ?",
            (new_role, enclave_id, did),
        )
        conn.commit()
        return cursor.rowcount > 0

    def archive_enclave(self, enclave_id: str) -> bool:
        """归档 Enclave"""
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE enclaves SET status = 'archived' WHERE id = ?",
            (enclave_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# 权限检查器
# ---------------------------------------------------------------------------

class EnclavePermissionChecker:
    """Enclave 权限检查器"""

    def is_member(self, enclave: Enclave, did: str) -> bool:
        """检查是否是成员"""
        return did in enclave.all_dids

    def is_admin(self, enclave: Enclave, did: str) -> bool:
        """检查是否是管理员"""
        return did in enclave.admin_dids

    def can_add_member(self, enclave: Enclave, actor_did: str) -> bool:
        """检查是否可以添加成员"""
        return self.is_admin(enclave, actor_did)

    def can_remove_member(self, enclave: Enclave, actor_did: str, target_did: str) -> bool:
        """检查是否可以移除成员"""
        if not self.is_admin(enclave, actor_did):
            return False
        # 不能移除自己（除非有其他 admin）
        if actor_did == target_did and len(enclave.admin_dids) == 1:
            return False
        return True

    def can_broadcast(self, enclave: Enclave, actor_did: str) -> bool:
        """检查是否可以广播消息"""
        return self.is_member(enclave, actor_did)


# ---------------------------------------------------------------------------
# 消息广播器
# ---------------------------------------------------------------------------

class EnclaveBroadcaster:
    """Enclave 消息广播器"""

    def __init__(self):
        self._sent_messages: list[dict] = []

    def broadcast(
        self,
        enclave: Enclave,
        from_did: str,
        content: dict,
        message_type: str = "enclave_broadcast",
    ) -> list[dict]:
        """向所有成员广播消息"""
        messages = []
        for member_did in enclave.all_dids:
            if member_did != from_did:  # 不发给自己
                msg = {
                    "from_did": from_did,
                    "to_did": member_did,
                    "content": content,
                    "message_type": message_type,
                    "enclave_id": enclave.id,
                    "timestamp": time.time(),
                }
                messages.append(msg)
                self._sent_messages.append(msg)
        return messages

    def get_sent_messages(self) -> list[dict]:
        return self._sent_messages

    def clear(self):
        self._sent_messages.clear()


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestEnclaveCreation:
    """Enclave 创建测试"""

    def test_tr_enc_01_create_enclave(self, tmp_path):
        """创建 Enclave 成功"""
        store = EnclaveStore(tmp_path / "enclave.db")

        enclave = store.create_enclave(
            name="Project Alpha",
            creator_did="did:agentnexus:zAdmin",
        )

        assert enclave.id.startswith("enclave_")
        assert enclave.name == "Project Alpha"
        assert enclave.creator_did == "did:agentnexus:zAdmin"
        assert enclave.status == "active"
        assert len(enclave.members) == 1
        assert enclave.members[0].role == "admin"

    def test_tr_enc_02_create_with_initial_members(self, tmp_path):
        """创建 Enclave 时添加初始成员"""
        store = EnclaveStore(tmp_path / "enclave.db")

        enclave = store.create_enclave(
            name="Team Beta",
            creator_did="did:agentnexus:zAdmin",
            initial_members=[
                "did:agentnexus:zMember1",
                "did:agentnexus:zMember2",
            ],
        )

        assert len(enclave.members) == 3
        assert "did:agentnexus:zMember1" in enclave.member_dids
        assert "did:agentnexus:zMember2" in enclave.member_dids

    def test_tr_enc_03_vault_namespace_auto_created(self, tmp_path):
        """创建 Enclave 时自动创建关联的 Vault 命名空间"""
        store = EnclaveStore(tmp_path / "enclave.db")

        enclave = store.create_enclave(
            name="Project Gamma",
            creator_did="did:agentnexus:zAdmin",
        )

        assert enclave.vault_namespace.startswith("vault_")
        assert enclave.vault_namespace != ""


class TestEnclaveMembership:
    """成员管理测试"""

    def test_tr_enc_04_add_member(self, tmp_path):
        """添加成员"""
        store = EnclaveStore(tmp_path / "enclave.db")

        enclave = store.create_enclave("Team", "did:agentnexus:zAdmin")
        new_member = store.add_member(
            enclave.id,
            "did:agentnexus:zNewMember",
            "member",
            "did:agentnexus:zAdmin",
        )

        assert new_member is not None
        assert new_member.role == "member"

        updated = store.get_enclave(enclave.id)
        assert len(updated.members) == 2

    def test_tr_enc_05_remove_member(self, tmp_path):
        """移除成员"""
        store = EnclaveStore(tmp_path / "enclave.db")

        enclave = store.create_enclave(
            "Team",
            "did:agentnexus:zAdmin",
            initial_members=["did:agentnexus:zMember"],
        )

        removed = store.remove_member(enclave.id, "did:agentnexus:zMember")
        assert removed is True

        updated = store.get_enclave(enclave.id)
        assert len(updated.members) == 1

    def test_tr_enc_06_cannot_remove_last_admin(self, tmp_path):
        """不能移除最后一个管理员"""
        store = EnclaveStore(tmp_path / "enclave.db")

        enclave = store.create_enclave("Team", "did:agentnexus:zAdmin")

        removed = store.remove_member(enclave.id, "did:agentnexus:zAdmin")
        assert removed is False  # 拒绝移除

    def test_tr_enc_07_update_member_role(self, tmp_path):
        """更新成员角色"""
        store = EnclaveStore(tmp_path / "enclave.db")

        enclave = store.create_enclave(
            "Team",
            "did:agentnexus:zAdmin",
            initial_members=["did:agentnexus:zMember"],
        )

        updated = store.update_member_role(enclave.id, "did:agentnexus:zMember", "admin")
        assert updated is True

        enc = store.get_enclave(enclave.id)
        assert "did:agentnexus:zMember" in enc.admin_dids


class TestEnclavePermission:
    """权限验证测试"""

    def test_tr_enc_08_is_member_check(self, tmp_path):
        """成员身份检查"""
        store = EnclaveStore(tmp_path / "enclave.db")
        checker = EnclavePermissionChecker()

        enclave = store.create_enclave(
            "Team",
            "did:agentnexus:zAdmin",
            initial_members=["did:agentnexus:zMember"],
        )

        assert checker.is_member(enclave, "did:agentnexus:zAdmin")
        assert checker.is_member(enclave, "did:agentnexus:zMember")
        assert not checker.is_member(enclave, "did:agentnexus:zStranger")

    def test_tr_enc_09_is_admin_check(self, tmp_path):
        """管理员身份检查"""
        store = EnclaveStore(tmp_path / "enclave.db")
        checker = EnclavePermissionChecker()

        enclave = store.create_enclave(
            "Team",
            "did:agentnexus:zAdmin",
            initial_members=["did:agentnexus:zMember"],
        )

        assert checker.is_admin(enclave, "did:agentnexus:zAdmin")
        assert not checker.is_admin(enclave, "did:agentnexus:zMember")

    def test_tr_enc_10_can_add_member(self, tmp_path):
        """添加成员权限检查"""
        store = EnclaveStore(tmp_path / "enclave.db")
        checker = EnclavePermissionChecker()

        enclave = store.create_enclave(
            "Team",
            "did:agentnexus:zAdmin",
            initial_members=["did:agentnexus:zMember"],
        )

        assert checker.can_add_member(enclave, "did:agentnexus:zAdmin")
        assert not checker.can_add_member(enclave, "did:agentnexus:zMember")


class TestEnclaveBroadcast:
    """消息广播测试"""

    def test_tr_enc_11_broadcast_to_all_members(self, tmp_path):
        """广播消息给所有成员"""
        store = EnclaveStore(tmp_path / "enclave.db")
        broadcaster = EnclaveBroadcaster()

        enclave = store.create_enclave(
            "Team",
            "did:agentnexus:zAdmin",
            initial_members=["did:agentnexus:zMember1", "did:agentnexus:zMember2"],
        )

        messages = broadcaster.broadcast(
            enclave,
            "did:agentnexus:zAdmin",
            {"type": "meeting", "time": "10:00"},
        )

        # 广播给 2 个成员（不包括发送者）
        assert len(messages) == 2
        for msg in messages:
            assert msg["message_type"] == "enclave_broadcast"
            assert msg["enclave_id"] == enclave.id
            assert msg["from_did"] == "did:agentnexus:zAdmin"

    def test_tr_enc_12_broadcast_permission_check(self, tmp_path):
        """只有成员可以广播"""
        store = EnclaveStore(tmp_path / "enclave.db")
        checker = EnclavePermissionChecker()
        broadcaster = EnclaveBroadcaster()

        enclave = store.create_enclave(
            "Team",
            "did:agentnexus:zAdmin",
        )

        # 非成员不能广播
        assert not checker.can_broadcast(enclave, "did:agentnexus:zStranger")

        # 成员可以广播
        assert checker.can_broadcast(enclave, "did:agentnexus:zAdmin")


class TestEnclaveVaultIntegration:
    """Enclave 与 Vault 集成测试"""

    def test_tr_enc_13_shared_vault_namespace(self, tmp_path):
        """成员共享同一个 Vault 命名空间"""
        from tests.test_v085_vault import VaultStore, VaultPermissionChecker

        enclave_store = EnclaveStore(tmp_path / "enclave.db")
        vault_store = VaultStore(tmp_path / "vault.db")
        vault_checker = VaultPermissionChecker()

        # 创建 Enclave
        enclave = enclave_store.create_enclave(
            "Team",
            "did:agentnexus:zAdmin",
            initial_members=["did:agentnexus:zMember"],
        )

        # 设置 Vault ACL
        vault_checker.set_namespace_acl(enclave.vault_namespace, {
            "read": enclave.all_dids,
            "write": enclave.admin_dids,
            "admin": enclave.admin_dids,
        })

        # Admin 写入数据
        vault_store.create(
            enclave.vault_namespace,
            "shared_config",
            {"mode": "production"},
            "did:agentnexus:zAdmin",
        )

        # 成员可以读取
        entry = vault_store.read(enclave.vault_namespace, "shared_config")
        assert entry.value == {"mode": "production"}

        # 成员可以读取（权限检查）
        assert vault_checker.can_read(enclave.vault_namespace, "did:agentnexus:zMember")
        # 成员不能写入
        assert not vault_checker.can_write(enclave.vault_namespace, "did:agentnexus:zMember")


class TestEnclaveLifecycle:
    """Enclave 生命周期测试"""

    def test_tr_enc_14_archive_enclave(self, tmp_path):
        """归档 Enclave"""
        store = EnclaveStore(tmp_path / "enclave.db")

        enclave = store.create_enclave("Team", "did:agentnexus:zAdmin")
        archived = store.archive_enclave(enclave.id)

        assert archived is True

        updated = store.get_enclave(enclave.id)
        assert updated.status == "archived"

    def test_tr_enc_15_list_user_enclaves(self, tmp_path):
        """列出用户所属的所有 Enclave"""
        store = EnclaveStore(tmp_path / "enclave.db")

        # 创建多个 Enclave
        e1 = store.create_enclave("Team A", "did:agentnexus:zUser")
        e2 = store.create_enclave("Team B", "did:agentnexus:zUser")
        store.create_enclave("Team C", "did:agentnexus:zOther")

        enclaves = store.list_enclaves("did:agentnexus:zUser")
        assert len(enclaves) == 2
        assert e1.id in [e.id for e in enclaves]
        assert e2.id in [e.id for e in enclaves]
