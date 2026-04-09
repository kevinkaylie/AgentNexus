"""
GitVaultBackend 测试

使用临时 Git 仓库测试 Git Vault 操作。
"""
import asyncio
import os
import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture
def temp_git_repo():
    """创建临时 Git 仓库"""
    temp_dir = tempfile.mkdtemp()
    repo_path = Path(temp_dir) / "test_repo"
    repo_path.mkdir()

    # 初始化 Git 仓库
    os.system(f"cd {repo_path} && git init && git config user.email 'test@test.com' && git config user.name 'Test'")

    yield repo_path

    # 清理
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestGitVaultBackend:
    """GitVaultBackend 测试"""

    @pytest.mark.asyncio
    async def test_put_and_get(self, temp_git_repo):
        """测试写入和读取"""
        from agent_net.enclave import GitVaultBackend

        backend = GitVaultBackend(repo_path=temp_git_repo)

        # 写入
        entry = await backend.put("test_doc", "Hello, World!", "did:agentnexus:owner", "Initial commit")
        assert entry.key == "test_doc"
        assert entry.version != ""  # commit hash
        assert entry.action == "create"

        # 读取
        result = await backend.get("test_doc")
        assert result.value == "Hello, World!"
        assert result.version == entry.version

    @pytest.mark.asyncio
    async def test_update(self, temp_git_repo):
        """测试更新文档"""
        from agent_net.enclave import GitVaultBackend

        backend = GitVaultBackend(repo_path=temp_git_repo)

        # 第一次写入
        entry1 = await backend.put("doc", "v1", "did:agentnexus:owner", "First")
        assert entry1.action == "create"

        # 第二次写入（更新）
        entry2 = await backend.put("doc", "v2", "did:agentnexus:owner", "Second")
        assert entry2.action == "update"
        assert entry2.version != entry1.version

        # 读取最新版本
        result = await backend.get("doc")
        assert result.value == "v2"

    @pytest.mark.asyncio
    async def test_nested_keys(self, temp_git_repo):
        """测试嵌套 key（目录结构）"""
        from agent_net.enclave import GitVaultBackend

        backend = GitVaultBackend(repo_path=temp_git_repo)

        # 写入嵌套路径
        await backend.put("design/api-spec", "API 设计", "did:agentnexus:owner")
        await backend.put("design/db-schema", "数据库设计", "did:agentnexus:owner")

        # 读取
        result1 = await backend.get("design/api-spec")
        assert result1.value == "API 设计"

        result2 = await backend.get("design/db-schema")
        assert result2.value == "数据库设计"

        # 验证文件结构
        vault_path = temp_git_repo / ".vault"
        assert (vault_path / "design" / "api-spec").exists()
        assert (vault_path / "design" / "db-schema").exists()

    @pytest.mark.asyncio
    async def test_list(self, temp_git_repo):
        """测试列出文档"""
        from agent_net.enclave import GitVaultBackend

        backend = GitVaultBackend(repo_path=temp_git_repo)

        # 写入多个文档
        await backend.put("doc1", "content1", "did:agentnexus:owner")
        await backend.put("doc2", "content2", "did:agentnexus:owner")
        await backend.put("design/api", "api design", "did:agentnexus:owner")

        # 列出全部
        all_docs = await backend.list()
        assert len(all_docs) == 3

        # 按前缀过滤
        design_docs = await backend.list(prefix="design/")
        assert len(design_docs) == 1
        assert design_docs[0].key == "design/api"

    @pytest.mark.asyncio
    async def test_history(self, temp_git_repo):
        """测试历史版本"""
        from agent_net.enclave import GitVaultBackend

        backend = GitVaultBackend(repo_path=temp_git_repo)

        # 多次写入
        await backend.put("doc", "v1", "did:agentnexus:owner", "First")
        await backend.put("doc", "v2", "did:agentnexus:owner", "Second")
        await backend.put("doc", "v3", "did:agentnexus:owner", "Third")

        # 查询历史
        history = await backend.history("doc")
        assert len(history) == 3
        # 按时间倒序
        assert "Third" in history[0].message
        assert "First" in history[2].message

    @pytest.mark.asyncio
    async def test_get_specific_version(self, temp_git_repo):
        """测试读取特定版本"""
        from agent_net.enclave import GitVaultBackend

        backend = GitVaultBackend(repo_path=temp_git_repo)

        # 多次写入
        entry1 = await backend.put("doc", "v1", "did:agentnexus:owner")
        entry2 = await backend.put("doc", "v2", "did:agentnexus:owner")

        # 读取旧版本
        result = await backend.get("doc", version=entry1.version)
        assert result.value == "v1"

        # 读取新版本
        result = await backend.get("doc", version=entry2.version)
        assert result.value == "v2"

    @pytest.mark.asyncio
    async def test_delete(self, temp_git_repo):
        """测试删除文档"""
        from agent_net.enclave import GitVaultBackend, VaultKeyNotFoundError

        backend = GitVaultBackend(repo_path=temp_git_repo)

        # 写入
        await backend.put("doc", "content", "did:agentnexus:owner")

        # 删除
        ok = await backend.delete("doc", "did:agentnexus:owner")
        assert ok

        # 读取应抛异常
        with pytest.raises(VaultKeyNotFoundError):
            await backend.get("doc")

        # 删除不存在的文档
        ok = await backend.delete("nonexistent", "did:agentnexus:owner")
        assert not ok

    @pytest.mark.asyncio
    async def test_invalid_key(self, temp_git_repo):
        """测试无效 key（路径遍历攻击）"""
        from agent_net.enclave import GitVaultBackend, VaultBackendError

        backend = GitVaultBackend(repo_path=temp_git_repo)

        # 路径遍历攻击
        with pytest.raises(VaultBackendError):
            await backend.get("../../../etc/passwd")

        with pytest.raises(VaultBackendError):
            await backend.put("../../../tmp/malicious", "bad", "did:agentnexus:owner")
