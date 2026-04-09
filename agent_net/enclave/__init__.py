"""
agent_net.enclave 模块

Enclave 协作架构（ADR-013）：
- Enclave：项目组，成员 + 角色 + 权限
- VaultBackend：可插拔文档存储（Git / Local / Notion / S3）
- Playbook：流程编排引擎

子模块：
- models.py：数据模型（Enclave, Member, Playbook, Stage 等）
- vault.py：VaultBackend 抽象接口 + 注册表
- vault_local.py：LocalVaultBackend（SQLite 存储）
- vault_git.py：GitVaultBackend（Git 仓库存储）
- playbook.py：Playbook 引擎
"""
from agent_net.enclave.models import (
    Enclave,
    Member,
    Stage,
    Playbook,
    PlaybookRun,
    StageExecution,
)
from agent_net.enclave.vault import (
    VaultBackend,
    VaultEntry,
    VaultError,
    VaultKeyNotFoundError,
    VaultPermissionError,
    VaultBackendError,
    register_vault_backend,
    create_vault_backend,
)
from agent_net.enclave.vault_local import LocalVaultBackend
from agent_net.enclave.vault_git import GitVaultBackend

# 注册内置 Backend
register_vault_backend("local", LocalVaultBackend)
register_vault_backend("git", GitVaultBackend)

__all__ = [
    # Models
    "Enclave",
    "Member",
    "Stage",
    "Playbook",
    "PlaybookRun",
    "StageExecution",
    # Vault
    "VaultBackend",
    "VaultEntry",
    "VaultError",
    "VaultKeyNotFoundError",
    "VaultPermissionError",
    "VaultBackendError",
    "register_vault_backend",
    "create_vault_backend",
    "LocalVaultBackend",
    "GitVaultBackend",
]