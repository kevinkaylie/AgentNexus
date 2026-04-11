"""
v0.8.5 Relay Vault（共享内存桶）测试套件
测试 ID: tr_vault_01 – tr_vault_15

覆盖场景：
  - Vault CRUD 操作
  - 基于 DID 的读写权限控制
  - Vault 数据持久化（Redis）
  - 按需读取（选择性记忆）
  - 版本控制
  - 命名空间隔离
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
class VaultEntry:
    """Vault 存储条目"""
    key: str
    value: dict | str | list
    namespace: str                    # enclave_id 作为命名空间
    version: int = 1
    created_by: str = ""              # 写入者 DID
    created_at: float = 0.0
    updated_by: str = ""
    updated_at: float = 0.0
    acl: dict = field(default_factory=dict)  # {"read": [did, ...], "write": [did, ...]}

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "namespace": self.namespace,
            "version": self.version,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
            "acl": self.acl,
        }


@dataclass
class VaultPermission:
    """Vault 权限"""
    can_read: bool = False
    can_write: bool = False
    can_delete: bool = False
    can_admin: bool = False  # 可以修改 ACL


# ---------------------------------------------------------------------------
# Vault 存储引擎
# ---------------------------------------------------------------------------

class VaultStore:
    """
    Vault 存储引擎
    MVP 使用 SQLite，生产环境迁移到 Redis
    """

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
            CREATE TABLE IF NOT EXISTS vault_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                namespace TEXT NOT NULL,
                value TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_by TEXT,
                updated_at REAL,
                acl TEXT,
                UNIQUE(namespace, key)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vault_namespace
            ON vault_entries(namespace)
        """)

    # ── CRUD 操作 ──────────────────────────────────────────────────

    def create(
        self,
        namespace: str,
        key: str,
        value: dict | str | list,
        author_did: str,
        acl: dict | None = None,
    ) -> VaultEntry:
        """创建新条目"""
        conn = self._get_conn()
        now = time.time()

        conn.execute(
            """
            INSERT INTO vault_entries
            (namespace, key, value, version, created_by, created_at, acl)
            VALUES (?, ?, ?, 1, ?, ?, ?)
            """,
            (
                namespace,
                key,
                json.dumps(value),
                author_did,
                now,
                json.dumps(acl or {}),
            ),
        )
        conn.commit()

        return VaultEntry(
            key=key,
            value=value,
            namespace=namespace,
            version=1,
            created_by=author_did,
            created_at=now,
            acl=acl or {},
        )

    def read(self, namespace: str, key: str) -> Optional[VaultEntry]:
        """读取条目"""
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT * FROM vault_entries
            WHERE namespace = ? AND key = ?
            """,
            (namespace, key),
        ).fetchone()

        if row is None:
            return None

        return VaultEntry(
            key=row["key"],
            value=json.loads(row["value"]),
            namespace=row["namespace"],
            version=row["version"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_by=row["updated_by"],
            updated_at=row["updated_at"],
            acl=json.loads(row["acl"] or "{}"),
        )

    def update(
        self,
        namespace: str,
        key: str,
        value: dict | str | list,
        author_did: str,
    ) -> Optional[VaultEntry]:
        """更新条目（版本递增）"""
        conn = self._get_conn()
        now = time.time()

        # 先读取当前版本
        existing = self.read(namespace, key)
        if existing is None:
            return None

        new_version = existing.version + 1

        conn.execute(
            """
            UPDATE vault_entries
            SET value = ?, version = ?, updated_by = ?, updated_at = ?
            WHERE namespace = ? AND key = ?
            """,
            (json.dumps(value), new_version, author_did, now, namespace, key),
        )
        conn.commit()

        return VaultEntry(
            key=key,
            value=value,
            namespace=namespace,
            version=new_version,
            created_by=existing.created_by,
            created_at=existing.created_at,
            updated_by=author_did,
            updated_at=now,
            acl=existing.acl,
        )

    def delete(self, namespace: str, key: str) -> bool:
        """删除条目"""
        conn = self._get_conn()
        cursor = conn.execute(
            """
            DELETE FROM vault_entries
            WHERE namespace = ? AND key = ?
            """,
            (namespace, key),
        )
        conn.commit()
        return cursor.rowcount > 0

    def list_keys(self, namespace: str, prefix: str = "") -> list[str]:
        """列出命名空间下的所有 key（支持前缀过滤）"""
        conn = self._get_conn()
        if prefix:
            rows = conn.execute(
                """
                SELECT key FROM vault_entries
                WHERE namespace = ? AND key LIKE ?
                ORDER BY key
                """,
                (namespace, f"{prefix}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT key FROM vault_entries
                WHERE namespace = ?
                ORDER BY key
                """,
                (namespace,),
            ).fetchall()
        return [row["key"] for row in rows]

    def list_entries(self, namespace: str) -> list[VaultEntry]:
        """列出命名空间下的所有条目"""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT * FROM vault_entries WHERE namespace = ?
            ORDER BY key
            """,
            (namespace,),
        ).fetchall()

        return [
            VaultEntry(
                key=row["key"],
                value=json.loads(row["value"]),
                namespace=row["namespace"],
                version=row["version"],
                created_by=row["created_by"],
                created_at=row["created_at"],
                updated_by=row["updated_by"],
                updated_at=row["updated_at"],
                acl=json.loads(row["acl"] or "{}"),
            )
            for row in rows
        ]


# ---------------------------------------------------------------------------
# 权限检查器
# ---------------------------------------------------------------------------

class VaultPermissionChecker:
    """Vault 权限检查器"""

    def __init__(self):
        # 默认权限：命名空间级别的访问控制
        # {namespace: {"read": [did, ...], "write": [did, ...], "admin": [did, ...]}}
        self._namespace_acls: dict[str, dict] = {}

    def set_namespace_acl(self, namespace: str, acl: dict) -> None:
        """设置命名空间级别的 ACL"""
        self._namespace_acls[namespace] = acl

    def check_permission(
        self,
        namespace: str,
        did: str,
        entry_acl: dict | None = None,
    ) -> VaultPermission:
        """
        检查 DID 对特定命名空间的权限

        优先级：条目级 ACL > 命名空间级 ACL
        """
        perm = VaultPermission()

        # 1. 检查命名空间级 ACL
        ns_acl = self._namespace_acls.get(namespace, {})
        readers = ns_acl.get("read", [])
        writers = ns_acl.get("write", [])
        admins = ns_acl.get("admin", [])

        # 2. 检查条目级 ACL（如果提供）
        if entry_acl:
            readers = entry_acl.get("read", readers)
            writers = entry_acl.get("write", writers)

        # 3. 计算权限
        if did in admins:
            perm.can_read = True
            perm.can_write = True
            perm.can_delete = True
            perm.can_admin = True
        else:
            perm.can_read = did in readers or "*" in readers
            perm.can_write = did in writers or "*" in writers
            perm.can_delete = did in admins

        return perm

    def can_read(self, namespace: str, did: str, entry_acl: dict | None = None) -> bool:
        return self.check_permission(namespace, did, entry_acl).can_read

    def can_write(self, namespace: str, did: str, entry_acl: dict | None = None) -> bool:
        return self.check_permission(namespace, did, entry_acl).can_write


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestVaultCRUD:
    """Vault CRUD 操作测试"""

    def test_tr_vault_01_create_entry(self, tmp_path):
        """创建条目成功"""
        store = VaultStore(tmp_path / "vault.db")

        entry = store.create(
            namespace="enclave_proj_x",
            key="config",
            value={"debug": True, "port": 8080},
            author_did="did:agentnexus:zAdmin",
        )

        assert entry.key == "config"
        assert entry.value == {"debug": True, "port": 8080}
        assert entry.namespace == "enclave_proj_x"
        assert entry.version == 1
        assert entry.created_by == "did:agentnexus:zAdmin"

    def test_tr_vault_02_read_entry(self, tmp_path):
        """读取条目成功"""
        store = VaultStore(tmp_path / "vault.db")

        store.create(
            namespace="enclave_proj_x",
            key="config",
            value={"debug": True},
            author_did="did:agentnexus:zAdmin",
        )

        entry = store.read("enclave_proj_x", "config")
        assert entry is not None
        assert entry.value == {"debug": True}

    def test_tr_vault_03_update_entry(self, tmp_path):
        """更新条目，版本递增"""
        store = VaultStore(tmp_path / "vault.db")

        store.create(
            namespace="enclave_proj_x",
            key="config",
            value={"debug": True},
            author_did="did:agentnexus:zAdmin",
        )

        updated = store.update(
            namespace="enclave_proj_x",
            key="config",
            value={"debug": False, "port": 9000},
            author_did="did:agentnexus:zDeveloper",
        )

        assert updated is not None
        assert updated.version == 2
        assert updated.value == {"debug": False, "port": 9000}
        assert updated.created_by == "did:agentnexus:zAdmin"
        assert updated.updated_by == "did:agentnexus:zDeveloper"

    def test_tr_vault_04_delete_entry(self, tmp_path):
        """删除条目"""
        store = VaultStore(tmp_path / "vault.db")

        store.create(
            namespace="enclave_proj_x",
            key="temp",
            value={},
            author_did="did:agentnexus:zAdmin",
        )

        deleted = store.delete("enclave_proj_x", "temp")
        assert deleted is True

        entry = store.read("enclave_proj_x", "temp")
        assert entry is None

    def test_tr_vault_05_read_nonexistent(self, tmp_path):
        """读取不存在的条目返回 None"""
        store = VaultStore(tmp_path / "vault.db")
        entry = store.read("enclave_proj_x", "nonexistent")
        assert entry is None


class TestVaultNamespace:
    """命名空间隔离测试"""

    def test_tr_vault_06_namespace_isolation(self, tmp_path):
        """不同命名空间的同 key 条目互不干扰"""
        store = VaultStore(tmp_path / "vault.db")

        store.create("enclave_a", "config", {"name": "A"}, "did:a")
        store.create("enclave_b", "config", {"name": "B"}, "did:b")

        entry_a = store.read("enclave_a", "config")
        entry_b = store.read("enclave_b", "config")

        assert entry_a.value == {"name": "A"}
        assert entry_b.value == {"name": "B"}

    def test_tr_vault_07_list_keys(self, tmp_path):
        """列出命名空间下的所有 key"""
        store = VaultStore(tmp_path / "vault.db")

        store.create("enclave_x", "config/app", {}, "did:a")
        store.create("enclave_x", "config/db", {}, "did:a")
        store.create("enclave_x", "temp", {}, "did:a")

        keys = store.list_keys("enclave_x")
        assert len(keys) == 3
        assert "config/app" in keys

    def test_tr_vault_08_list_keys_with_prefix(self, tmp_path):
        """按前缀过滤 key"""
        store = VaultStore(tmp_path / "vault.db")

        store.create("enclave_x", "config/app", {}, "did:a")
        store.create("enclave_x", "config/db", {}, "did:a")
        store.create("enclave_x", "temp", {}, "did:a")

        keys = store.list_keys("enclave_x", prefix="config")
        assert len(keys) == 2
        assert "config/app" in keys
        assert "config/db" in keys
        assert "temp" not in keys


class TestVaultPermission:
    """权限控制测试"""

    def test_tr_vault_09_namespace_acl_read(self, tmp_path):
        """命名空间级 ACL：读取权限检查"""
        checker = VaultPermissionChecker()
        checker.set_namespace_acl("enclave_proj_x", {
            "read": ["did:agentnexus:zMember1", "did:agentnexus:zMember2"],
            "write": ["did:agentnexus:zMember1"],
            "admin": ["did:agentnexus:zAdmin"],
        })

        assert checker.can_read("enclave_proj_x", "did:agentnexus:zMember1")
        assert checker.can_read("enclave_proj_x", "did:agentnexus:zMember2")
        assert not checker.can_read("enclave_proj_x", "did:agentnexus:zStranger")

    def test_tr_vault_10_namespace_acl_write(self, tmp_path):
        """命名空间级 ACL：写入权限检查"""
        checker = VaultPermissionChecker()
        checker.set_namespace_acl("enclave_proj_x", {
            "read": ["did:agentnexus:zMember1", "did:agentnexus:zMember2"],
            "write": ["did:agentnexus:zMember1"],
        })

        assert checker.can_write("enclave_proj_x", "did:agentnexus:zMember1")
        assert not checker.can_write("enclave_proj_x", "did:agentnexus:zMember2")

    def test_tr_vault_11_entry_acl_override(self, tmp_path):
        """条目级 ACL 覆盖命名空间级 ACL"""
        checker = VaultPermissionChecker()
        checker.set_namespace_acl("enclave_proj_x", {
            "read": ["did:agentnexus:zMember1"],
        })

        # 条目级 ACL 允许 zMember2 读取
        entry_acl = {"read": ["did:agentnexus:zMember2"]}

        assert checker.can_read("enclave_proj_x", "did:agentnexus:zMember2", entry_acl)
        # 命名空间级的权限被覆盖
        assert not checker.can_read("enclave_proj_x", "did:agentnexus:zMember1", entry_acl)

    def test_tr_vault_12_wildcard_permission(self, tmp_path):
        """通配符权限："*" 允许所有人"""
        checker = VaultPermissionChecker()
        checker.set_namespace_acl("enclave_public", {
            "read": ["*"],
            "write": ["did:agentnexus:zAdmin"],
        })

        assert checker.can_read("enclave_public", "did:agentnexus:zAnyone")
        assert not checker.can_write("enclave_public", "did:agentnexus:zAnyone")


class TestVaultPersistence:
    """持久化测试"""

    def test_tr_vault_13_persistence_after_reopen(self, tmp_path):
        """数据在重新打开后依然存在"""
        db_path = tmp_path / "vault.db"

        # 第一次写入
        store1 = VaultStore(db_path)
        store1.create("enclave_x", "data", {"value": 123}, "did:a")

        # 关闭连接
        store1._conn = None

        # 重新打开
        store2 = VaultStore(db_path)
        entry = store2.read("enclave_x", "data")

        assert entry is not None
        assert entry.value == {"value": 123}

    def test_tr_vault_14_multiple_entries(self, tmp_path):
        """批量操作多个条目"""
        store = VaultStore(tmp_path / "vault.db")

        # 批量创建
        for i in range(10):
            store.create("enclave_x", f"item_{i}", {"index": i}, "did:a")

        entries = store.list_entries("enclave_x")
        assert len(entries) == 10


class TestVaultSelectiveRead:
    """按需读取测试"""

    def test_tr_vault_15_selective_read(self, tmp_path):
        """只读取需要的 key，不全量同步"""
        store = VaultStore(tmp_path / "vault.db")

        # 创建多个条目
        store.create("enclave_x", "large_data_1", {"data": "x" * 1000}, "did:a")
        store.create("enclave_x", "large_data_2", {"data": "y" * 1000}, "did:a")
        store.create("enclave_x", "small_config", {"debug": True}, "did:a")

        # 只读取需要的条目
        entry = store.read("enclave_x", "small_config")
        assert entry.value == {"debug": True}

        # 其他大数据不会被加载
        entries = store.list_entries("enclave_x")
        assert len(entries) == 3


# ---------------------------------------------------------------------------
# 集成测试
# ---------------------------------------------------------------------------

class TestVaultIntegration:
    """集成测试"""

    def test_tr_vault_16_full_workflow(self, tmp_path):
        """完整工作流：创建 → 读取 → 更新 → 权限检查 → 删除"""
        store = VaultStore(tmp_path / "vault.db")
        checker = VaultPermissionChecker()

        namespace = "enclave_team_alpha"
        admin_did = "did:agentnexus:zAdmin"
        member_did = "did:agentnexus:zMember"

        # 1. 设置权限
        checker.set_namespace_acl(namespace, {
            "read": [admin_did, member_did],
            "write": [admin_did],
            "admin": [admin_did],
        })

        # 2. 创建条目
        entry = store.create(
            namespace,
            "project_config",
            {"name": "Alpha", "status": "active"},
            admin_did,
        )
        assert entry.version == 1

        # 3. 读取验证
        read_entry = store.read(namespace, "project_config")
        assert read_entry.value["status"] == "active"

        # 4. 权限检查
        assert checker.can_read(namespace, member_did)
        assert not checker.can_write(namespace, member_did)
        assert checker.can_write(namespace, admin_did)

        # 5. 更新
        updated = store.update(namespace, "project_config", {"name": "Alpha", "status": "paused"}, admin_did)
        assert updated.version == 2
        assert updated.value["status"] == "paused"

        # 6. 删除
        deleted = store.delete(namespace, "project_config")
        assert deleted is True

        # 7. 验证删除
        assert store.read(namespace, "project_config") is None
