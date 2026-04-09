"""
VaultBackend 抽象接口

ADR-013 §3 定义的可插拔文档存储接口。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────────────────────────────────────────
# 异常类型
# ─────────────────────────────────────────────────────────────────

class VaultError(Exception):
    """Vault 操作基础异常"""
    pass


class VaultKeyNotFoundError(VaultError):
    """文档不存在"""
    pass


class VaultPermissionError(VaultError):
    """权限不足"""
    pass


class VaultBackendError(VaultError):
    """后端操作失败（Git 命令失败、文件 I/O 错误等）"""
    pass


# ─────────────────────────────────────────────────────────────────
# 数据类
# ─────────────────────────────────────────────────────────────────

@dataclass
class VaultEntry:
    """Vault 文档条目"""
    key: str
    value: str = ""                    # 文本内容或 JSON（list 时为空串）
    version: str = ""                  # Git: commit hash / Local: 自增整数字符串
    updated_by: str = ""               # DID
    updated_at: float = 0.0            # Unix timestamp
    message: str = ""                  # 变更说明
    action: str = "update"             # create / update / delete（用于历史记录）

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "version": self.version,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
            "message": self.message,
            "action": self.action,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VaultEntry":
        return cls(
            key=d["key"],
            value=d.get("value", ""),
            version=d.get("version", ""),
            updated_by=d.get("updated_by", ""),
            updated_at=d.get("updated_at", 0.0),
            message=d.get("message", ""),
            action=d.get("action", "update"),
        )


# ─────────────────────────────────────────────────────────────────
# 抽象接口
# ─────────────────────────────────────────────────────────────────

class VaultBackend(ABC):
    """
    Enclave 文档存储抽象接口

    实现要求：
    - key 支持 / 分隔的路径（如 "design/api-spec"）
    - 写入时自动创建不存在的目录层级
    - 版本号格式由实现决定（Git 用 commit hash，Local 用自增整数）
    """

    @abstractmethod
    async def get(self, key: str, version: Optional[str] = None) -> VaultEntry:
        """
        读取文档。

        Args:
            key: 文档键名
            version: 指定版本（None=最新）

        Returns:
            VaultEntry（含 value）

        Raises:
            VaultKeyNotFoundError: key 不存在
            VaultBackendError: 后端操作失败
        """
        pass

    @abstractmethod
    async def put(
        self,
        key: str,
        value: str,
        author_did: str,
        message: str = "",
    ) -> VaultEntry:
        """
        写入文档（创建或更新）。

        Args:
            key: 文档键名（允许 / 分隔的路径，如 "design/api-spec"）
            value: 文档内容
            author_did: 作者 DID
            message: 变更说明（Git backend 用作 commit message）

        Returns:
            新版本的 VaultEntry（value 可为空串，节省带宽）

        Raises:
            VaultBackendError: 后端操作失败
        """
        pass

    @abstractmethod
    async def list(self, prefix: str = "") -> list[VaultEntry]:
        """
        列出文档（仅元数据，value 为空串）。

        Args:
            prefix: 键名前缀过滤

        Returns:
            VaultEntry 列表（按 key 字母序）
        """
        pass

    @abstractmethod
    async def history(self, key: str, limit: int = 10) -> list[VaultEntry]:
        """
        查看文档变更历史（按时间倒序）。

        Args:
            key: 文档键名
            limit: 最大返回条数

        Returns:
            VaultEntry 列表（value 为空串，仅元数据）

        Raises:
            VaultKeyNotFoundError: key 不存在
        """
        pass

    @abstractmethod
    async def delete(self, key: str, author_did: str) -> bool:
        """
        删除文档。

        Args:
            key: 文档键名
            author_did: 删除者 DID

        Returns:
            True=已删除，False=key 不存在
        """
        pass


# ─────────────────────────────────────────────────────────────────
# Backend 注册表
# ─────────────────────────────────────────────────────────────────

_VAULT_BACKENDS: dict[str, type[VaultBackend]] = {}


def register_vault_backend(name: str, cls: type[VaultBackend]) -> None:
    """注册 VaultBackend 实现类"""
    _VAULT_BACKENDS[name] = cls


def create_vault_backend(name: str, config: dict) -> VaultBackend:
    """创建 VaultBackend 实例"""
    cls = _VAULT_BACKENDS.get(name)
    if not cls:
        raise ValueError(f"Unknown vault backend: {name}")
    return cls(**config)


def list_vault_backends() -> list[str]:
    """列出已注册的 Backend 名称"""
    return list(_VAULT_BACKENDS.keys())
