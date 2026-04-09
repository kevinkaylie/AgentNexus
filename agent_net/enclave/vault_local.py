"""
LocalVaultBackend 实现

基于 Daemon SQLite 的 Vault 实现，零配置，适合单机简单场景。
数据存储在 enclave_vault 和 enclave_vault_history 表中。

注意：表结构由 storage.py 的 init_enclave_tables() 统一管理，
本模块不再独立创建表，避免 DDL 重复定义。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import aiosqlite

from agent_net.enclave.vault import (
    VaultBackend,
    VaultEntry,
    VaultKeyNotFoundError,
    VaultBackendError,
)


class LocalVaultBackend(VaultBackend):
    """
    基于 SQLite 的 Vault 实现（异步版本）。

    配置：
        enclave_id: Enclave ID（用于隔离不同 Enclave 的数据）
        db_path: SQLite 数据库路径（默认使用 storage.py 的 DB_PATH）

    注意：
        - 表结构由 storage.py 统一管理，本类不执行 DDL
        - 使用 aiosqlite 确保非阻塞 I/O
    """

    def __init__(self, enclave_id: str, db_path: str | Path | None = None):
        self.enclave_id = enclave_id
        self._db_path = db_path
        # 不再在 __init__ 中初始化表结构，由 storage.py 统一管理

    async def _get_db_path(self) -> Path:
        """获取数据库路径"""
        if self._db_path is None:
            from agent_net.storage import DB_PATH
            self._db_path = DB_PATH
        return Path(self._db_path)

    async def get(self, key: str, version: Optional[str] = None) -> VaultEntry:
        """读取文档"""
        db_path = await self._get_db_path()

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            if version:
                # 读取指定版本
                async with db.execute(
                    """SELECT * FROM enclave_vault_history
                       WHERE enclave_id = ? AND key = ? AND version = ?""",
                    (self.enclave_id, key, int(version)),
                ) as cursor:
                    row = await cursor.fetchone()
            else:
                # 读取最新版本
                async with db.execute(
                    """SELECT * FROM enclave_vault
                       WHERE enclave_id = ? AND key = ?""",
                    (self.enclave_id, key),
                ) as cursor:
                    row = await cursor.fetchone()

        if row is None:
            raise VaultKeyNotFoundError(f"Key not found: {key}")

        return VaultEntry(
            key=row["key"],
            value=row["value"],
            version=str(row["version"]),
            updated_by=row["updated_by"],
            updated_at=row["updated_at"],
            message=row["message"] or "",
            action=row["action"] if "action" in row.keys() else "update",
        )

    async def put(
        self,
        key: str,
        value: str,
        author_did: str,
        message: str = "",
    ) -> VaultEntry:
        """写入文档"""
        db_path = await self._get_db_path()
        now = time.time()

        async with aiosqlite.connect(db_path) as db:
            # 检查是否已存在
            async with db.execute(
                "SELECT version FROM enclave_vault WHERE enclave_id = ? AND key = ?",
                (self.enclave_id, key),
            ) as cursor:
                existing = await cursor.fetchone()

            if existing:
                # 更新
                new_version = existing[0] + 1
                action = "update"
                await db.execute(
                    """UPDATE enclave_vault
                       SET value = ?, version = ?, updated_by = ?, updated_at = ?, message = ?
                       WHERE enclave_id = ? AND key = ?""",
                    (value, new_version, author_did, now, message, self.enclave_id, key),
                )
            else:
                # 创建
                new_version = 1
                action = "create"
                await db.execute(
                    """INSERT INTO enclave_vault
                       (enclave_id, key, value, version, updated_by, updated_at, message)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (self.enclave_id, key, value, new_version, author_did, now, message),
                )

            # 写入历史（append-only）
            await db.execute(
                """INSERT INTO enclave_vault_history
                   (enclave_id, key, value, version, updated_by, updated_at, message, action)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.enclave_id, key, value, new_version, author_did, now, message, action),
            )

            await db.commit()

        return VaultEntry(
            key=key,
            value="",  # 返回时省略 value，节省带宽
            version=str(new_version),
            updated_by=author_did,
            updated_at=now,
            message=message,
            action=action,
        )

    async def list(self, prefix: str = "") -> list[VaultEntry]:
        """列出文档"""
        db_path = await self._get_db_path()

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            if prefix:
                async with db.execute(
                    """SELECT key, version, updated_by, updated_at, message
                       FROM enclave_vault
                       WHERE enclave_id = ? AND key LIKE ?
                       ORDER BY key""",
                    (self.enclave_id, f"{prefix}%"),
                ) as cursor:
                    rows = await cursor.fetchall()
            else:
                async with db.execute(
                    """SELECT key, version, updated_by, updated_at, message
                       FROM enclave_vault
                       WHERE enclave_id = ?
                       ORDER BY key""",
                    (self.enclave_id,),
                ) as cursor:
                    rows = await cursor.fetchall()

        return [
            VaultEntry(
                key=row["key"],
                value="",  # 仅元数据
                version=str(row["version"]),
                updated_by=row["updated_by"],
                updated_at=row["updated_at"],
                message=row["message"] or "",
                action="update",  # list 不返回 action
            )
            for row in rows
        ]

    async def history(self, key: str, limit: int = 10) -> list[VaultEntry]:
        """查看变更历史"""
        db_path = await self._get_db_path()

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # 先检查 key 是否存在
            async with db.execute(
                "SELECT 1 FROM enclave_vault WHERE enclave_id = ? AND key = ?",
                (self.enclave_id, key),
            ) as cursor:
                existing = await cursor.fetchone()

            if not existing:
                raise VaultKeyNotFoundError(f"Key not found: {key}")

            async with db.execute(
                """SELECT version, updated_by, updated_at, message, action
                   FROM enclave_vault_history
                   WHERE enclave_id = ? AND key = ?
                   ORDER BY version DESC
                   LIMIT ?""",
                (self.enclave_id, key, limit),
            ) as cursor:
                rows = await cursor.fetchall()

        return [
            VaultEntry(
                key=key,
                value="",  # 仅元数据
                version=str(row["version"]),
                updated_by=row["updated_by"],
                updated_at=row["updated_at"],
                message=row["message"] or "",
                action=row["action"] or "update",
            )
            for row in rows
        ]

    async def delete(self, key: str, author_did: str) -> bool:
        """删除文档"""
        db_path = await self._get_db_path()
        now = time.time()

        async with aiosqlite.connect(db_path) as db:
            # 检查是否存在
            async with db.execute(
                "SELECT version FROM enclave_vault WHERE enclave_id = ? AND key = ?",
                (self.enclave_id, key),
            ) as cursor:
                existing = await cursor.fetchone()

            if not existing:
                return False

            # 写入历史记录（标记删除）
            await db.execute(
                """INSERT INTO enclave_vault_history
                   (enclave_id, key, value, version, updated_by, updated_at, message, action)
                   VALUES (?, ?, '', ?, ?, ?, '', 'delete')""",
                (self.enclave_id, key, existing[0] + 1, author_did, now),
            )

            # 删除
            await db.execute(
                "DELETE FROM enclave_vault WHERE enclave_id = ? AND key = ?",
                (self.enclave_id, key),
            )

            await db.commit()
            return True
