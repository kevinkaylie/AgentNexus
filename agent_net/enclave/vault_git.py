"""
GitVaultBackend 实现

基于 Git 仓库的 Vault 实现，支持跨机器协作和完整版本历史。

文件布局：{repo_path}/{vault_dir}/{key}
key 中的 / 映射为目录层级。

配置：
    repo_path: 本地仓库路径（必填）
    remote: 远程仓库 URL（可选，用于跨机器同步）
    branch: 分支名（默认 main）
    vault_dir: Vault 文件存放子目录（默认 .vault/）
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Optional

from agent_net.enclave.vault import (
    VaultBackend,
    VaultEntry,
    VaultKeyNotFoundError,
    VaultBackendError,
)


class GitVaultBackend(VaultBackend):
    """
    基于 Git 仓库的 Vault 实现。

    特点：
    - 天然支持版本历史（commit hash 作为 version）
    - 支持跨机器同步（通过 git push/pull）
    - 与 AI 编程工具（Claude Code / Kiro / Cursor）的工作方式一致
    """

    def __init__(
        self,
        repo_path: str | Path,
        remote: str = "",
        branch: str = "main",
        vault_dir: str = ".vault",
    ):
        self.repo_path = Path(repo_path).resolve()
        self.remote = remote
        self.branch = branch
        self.vault_dir = vault_dir
        self._vault_path = self.repo_path / self.vault_dir

        # 验证仓库存在
        if not (self.repo_path / ".git").exists():
            raise VaultBackendError(f"Not a git repository: {self.repo_path}")

    def _key_to_path(self, key: str) -> Path:
        """将 key 转换为文件路径"""
        # 安全检查：防止路径遍历攻击
        if ".." in key or key.startswith("/"):
            raise VaultBackendError(f"Invalid key: {key}")
        return self._vault_path / key

    def _git_path(self, path: Path) -> str:
        """Git pathspecs use POSIX separators even on Windows."""
        return path.relative_to(self.repo_path).as_posix()

    async def _run_git(self, *args: str, check: bool = True) -> tuple[int, str, str]:
        """
        异步执行 git 命令。

        Returns:
            (return_code, stdout, stderr)
        """
        cmd = ["git"] + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode(), stderr.decode()

    async def _ensure_vault_dir(self) -> None:
        """确保 vault 目录存在"""
        self._vault_path.mkdir(parents=True, exist_ok=True)

    async def _git_add_commit(
        self,
        file_path: Path,
        author_did: str,
        message: str,
    ) -> str:
        """
        执行 git add + git commit，返回 commit hash。
        """
        # git add
        rel_path = self._git_path(file_path)
        returncode, _, stderr = await self._run_git("add", rel_path)
        if returncode != 0:
            raise VaultBackendError(f"git add failed: {stderr}")

        # git commit
        # 使用 --author 参数设置作者（DID 作为名字）
        commit_message = message or f"Update {rel_path}"
        returncode, stdout, stderr = await self._run_git(
            "commit",
            "-m", commit_message,
            "--author", f"{author_did} <agent@agentnexus>",
        )
        if returncode != 0:
            # 可能是没有变更（内容相同）
            if "nothing to commit" in stdout or "nothing to commit" in stderr:
                # 获取当前 commit hash
                returncode, stdout, stderr = await self._run_git("rev-parse", "HEAD")
                if returncode == 0:
                    return stdout.strip()
            raise VaultBackendError(f"git commit failed: {stderr}")

        # 获取最新 commit hash
        returncode, stdout, stderr = await self._run_git("rev-parse", "HEAD")
        if returncode != 0:
            raise VaultBackendError(f"git rev-parse failed: {stderr}")

        return stdout.strip()

    async def _git_push(self) -> None:
        """推送到远程仓库（如果配置了 remote）"""
        if not self.remote:
            return

        returncode, _, stderr = await self._run_git(
            "push", self.remote, self.branch,
            check=False,
        )
        if returncode != 0:
            # push 失败不阻塞，只记录警告
            import logging
            logging.warning(f"Git push failed: {stderr}")

    async def _git_pull(self) -> None:
        """从远程仓库拉取更新（如果配置了 remote）"""
        if not self.remote:
            return

        returncode, _, stderr = await self._run_git(
            "pull", self.remote, self.branch,
            check=False,
        )
        if returncode != 0:
            import logging
            logging.warning(f"Git pull failed: {stderr}")

    async def get(self, key: str, version: Optional[str] = None) -> VaultEntry:
        """读取文档"""
        await self._git_pull()  # 先拉取最新

        file_path = self._key_to_path(key)

        if version:
            # 读取指定版本
            rel_path = self._git_path(file_path)
            returncode, stdout, stderr = await self._run_git(
                "show", f"{version}:{rel_path}",
            )
            if returncode != 0:
                if "does not exist" in stderr or "not found" in stderr:
                    raise VaultKeyNotFoundError(f"Key not found: {key} (version: {version})")
                raise VaultBackendError(f"git show failed: {stderr}")

            content = stdout
            # 获取该 commit 的元数据
            returncode, stdout_meta, _ = await self._run_git(
                "log", "-1", "--format=%ct%n%an%n%s", version,
            )
            if returncode == 0:
                lines = stdout_meta.strip().split("\n")
                updated_at = float(lines[0]) if lines else 0.0
                updated_by = lines[1] if len(lines) > 1 else ""
                message = lines[2] if len(lines) > 2 else ""
            else:
                updated_at = 0.0
                updated_by = ""
                message = ""

            return VaultEntry(
                key=key,
                value=content,
                version=version,
                updated_by=updated_by,
                updated_at=updated_at,
                message=message,
                action="update",
            )
        else:
            # 读取最新版本
            if not file_path.exists():
                raise VaultKeyNotFoundError(f"Key not found: {key}")

            content = file_path.read_text()

            # 获取文件最后修改的 commit 信息
            rel_path = self._git_path(file_path)
            returncode, stdout, _ = await self._run_git(
                "log", "-1", "--format=%H%n%ct%n%an%n%s", "--", rel_path,
            )

            if returncode == 0 and stdout.strip():
                lines = stdout.strip().split("\n")
                commit_hash = lines[0]
                updated_at = float(lines[1]) if len(lines) > 1 else 0.0
                updated_by = lines[2] if len(lines) > 2 else ""
                message = lines[3] if len(lines) > 3 else ""
            else:
                # 文件可能是新创建的，还没有 commit
                commit_hash = "uncommitted"
                updated_at = file_path.stat().st_mtime
                updated_by = ""
                message = ""

            return VaultEntry(
                key=key,
                value=content,
                version=commit_hash,
                updated_by=updated_by,
                updated_at=updated_at,
                message=message,
                action="update",
            )

    async def put(
        self,
        key: str,
        value: str,
        author_did: str,
        message: str = "",
    ) -> VaultEntry:
        """写入文档"""
        await self._ensure_vault_dir()
        await self._git_pull()  # 先拉取最新

        file_path = self._key_to_path(key)

        # 判断是创建还是更新
        action = "update" if file_path.exists() else "create"

        # 创建父目录
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        file_path.write_text(value)

        # git add + commit
        commit_hash = await self._git_add_commit(file_path, author_did, message)

        # 推送到远程
        await self._git_push()

        return VaultEntry(
            key=key,
            value="",  # 返回时省略 value
            version=commit_hash,
            updated_by=author_did,
            updated_at=time.time(),
            message=message,
            action=action,
        )

    async def list(self, prefix: str = "") -> list[VaultEntry]:
        """列出文档"""
        await self._git_pull()  # 先拉取最新

        if not self._vault_path.exists():
            return []

        entries = []
        prefix_path = self._vault_path / prefix if prefix else self._vault_path

        if not prefix_path.exists():
            return []

        # 递归遍历所有文件
        for file_path in prefix_path.rglob("*"):
            if not file_path.is_file():
                continue

            # 计算相对 key
            rel_key = file_path.relative_to(self._vault_path).as_posix()

            # 获取文件元数据
            rel_path = self._git_path(file_path)
            returncode, stdout, _ = await self._run_git(
                "log", "-1", "--format=%H%n%ct%n%an", "--", rel_path,
            )

            if returncode == 0 and stdout.strip():
                lines = stdout.strip().split("\n")
                commit_hash = lines[0]
                updated_at = float(lines[1]) if len(lines) > 1 else 0.0
                updated_by = lines[2] if len(lines) > 2 else ""
            else:
                commit_hash = "uncommitted"
                updated_at = file_path.stat().st_mtime
                updated_by = ""

            entries.append(VaultEntry(
                key=rel_key,
                value="",
                version=commit_hash,
                updated_by=updated_by,
                updated_at=updated_at,
                message="",
                action="update",
            ))

        # 按 key 字母序排序
        entries.sort(key=lambda e: e.key)
        return entries

    async def history(self, key: str, limit: int = 10) -> list[VaultEntry]:
        """查看变更历史"""
        await self._git_pull()  # 先拉取最新

        file_path = self._key_to_path(key)
        if not file_path.exists():
            # 检查文件是否曾经存在（被删除）
            rel_path = self._git_path(file_path)
            returncode, stdout, _ = await self._run_git(
                "log", "--follow", "-1", "--format=%H", "--", rel_path,
            )
            if returncode != 0 or not stdout.strip():
                raise VaultKeyNotFoundError(f"Key not found: {key}")

        rel_path = self._git_path(file_path)
        returncode, stdout, stderr = await self._run_git(
            "log", "--follow",
            f"-n", str(limit),
            "--format=%H%n%ct%n%an%n%s",
            "--", rel_path,
        )

        if returncode != 0:
            raise VaultBackendError(f"git log failed: {stderr}")

        entries = []
        lines = stdout.strip().split("\n")
        for i in range(0, len(lines), 4):
            if i + 3 >= len(lines):
                break
            commit_hash = lines[i]
            updated_at = float(lines[i + 1])
            updated_by = lines[i + 2]
            message = lines[i + 3]

            entries.append(VaultEntry(
                key=key,
                value="",
                version=commit_hash,
                updated_by=updated_by,
                updated_at=updated_at,
                message=message,
                action="update",
            ))

        return entries

    async def delete(self, key: str, author_did: str) -> bool:
        """删除文档"""
        await self._git_pull()  # 先拉取最新

        file_path = self._key_to_path(key)
        if not file_path.exists():
            return False

        # git rm（已经 stage 了删除操作）
        rel_path = self._git_path(file_path)
        returncode, _, stderr = await self._run_git("rm", rel_path)
        if returncode != 0:
            raise VaultBackendError(f"git rm failed: {stderr}")

        # git commit（直接提交，不需要 git add）
        commit_message = f"Delete {key}"
        returncode, stdout, stderr = await self._run_git(
            "commit",
            "-m", commit_message,
            "--author", f"{author_did} <agent@agentnexus>",
        )
        if returncode != 0:
            raise VaultBackendError(f"git commit failed: {stderr}")

        # 获取 commit hash
        returncode, stdout, _ = await self._run_git("rev-parse", "HEAD")
        commit_hash = stdout.strip() if returncode == 0 else ""

        # 推送到远程
        await self._git_push()

        return True
