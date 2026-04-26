"""
Enclave 协作架构测试（ADR-013）

测试覆盖：
- Enclave CRUD
- Member 管理
- Vault 操作
- Playbook 执行
"""
import asyncio
import json
import pytest
import tempfile
import os
from pathlib import Path

# 使用临时数据库
TEST_DB_PATH = Path(tempfile.gettempdir()) / f"test_enclave_{os.getpid()}.db"


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """每个测试前重置数据库"""
    import agent_net.storage as storage
    monkeypatch.setattr(storage, "DB_PATH", TEST_DB_PATH)
    # 初始化数据库
    asyncio.run(storage.init_db())
    yield
    # 清理
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


class TestEnclaveCRUD:
    """Enclave CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_enclave(self):
        """测试创建 Enclave"""
        from agent_net.storage import create_enclave, get_enclave
        from agent_net.enclave.models import Enclave

        enclave_id = Enclave.gen_id()
        await create_enclave(
            enclave_id=enclave_id,
            name="测试项目",
            owner_did="did:agentnexus:z6Mk_test_owner",
            vault_backend="local",
            vault_config={},
        )

        enc = await get_enclave(enclave_id)
        assert enc is not None
        assert enc["name"] == "测试项目"
        assert enc["owner_did"] == "did:agentnexus:z6Mk_test_owner"
        assert enc["status"] == "active"
        assert enc["vault_backend"] == "local"

    @pytest.mark.asyncio
    async def test_list_enclaves(self):
        """测试列出 Enclave"""
        from agent_net.storage import create_enclave, list_enclaves, add_enclave_member
        from agent_net.enclave.models import Enclave

        # 创建两个 Enclave
        enc_id1 = Enclave.gen_id()
        enc_id2 = Enclave.gen_id()
        await create_enclave(enc_id1, "项目1", "did:agentnexus:owner1")
        await create_enclave(enc_id2, "项目2", "did:agentnexus:owner2")

        # 添加成员
        await add_enclave_member(enc_id1, "did:agentnexus:member1", "developer")
        await add_enclave_member(enc_id2, "did:agentnexus:member1", "reviewer")

        # 查询成员参与的 Enclave
        encs = await list_enclaves(did="did:agentnexus:member1")
        assert len(encs) == 2

        # 查询所有 Enclave
        all_encs = await list_enclaves()
        assert len(all_encs) == 2

    @pytest.mark.asyncio
    async def test_update_enclave(self):
        """测试更新 Enclave"""
        from agent_net.storage import create_enclave, update_enclave, get_enclave
        from agent_net.enclave.models import Enclave

        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "原名称", "did:agentnexus:owner")

        ok = await update_enclave(enclave_id, name="新名称", status="paused")
        assert ok

        enc = await get_enclave(enclave_id)
        assert enc["name"] == "新名称"
        assert enc["status"] == "paused"

    @pytest.mark.asyncio
    async def test_delete_enclave(self):
        """测试归档 Enclave（软删除）"""
        from agent_net.storage import create_enclave, delete_enclave, get_enclave
        from agent_net.enclave.models import Enclave

        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")

        ok = await delete_enclave(enclave_id)
        assert ok

        enc = await get_enclave(enclave_id)
        assert enc["status"] == "archived"


class TestMemberManagement:
    """成员管理测试"""

    @pytest.mark.asyncio
    async def test_add_member(self):
        """测试添加成员"""
        from agent_net.storage import (
            create_enclave, add_enclave_member, get_enclave_member, list_enclave_members
        )
        from agent_net.enclave.models import Enclave

        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")

        ok = await add_enclave_member(
            enclave_id=enclave_id,
            did="did:agentnexus:member1",
            role="developer",
            permissions="rw",
            handbook="写代码",
        )
        assert ok

        member = await get_enclave_member(enclave_id, "did:agentnexus:member1")
        assert member is not None
        assert member["role"] == "developer"
        assert member["permissions"] == "rw"
        assert member["handbook"] == "写代码"

        # 重复添加应失败
        ok2 = await add_enclave_member(
            enclave_id=enclave_id,
            did="did:agentnexus:member1",
            role="architect",
        )
        assert not ok2

    @pytest.mark.asyncio
    async def test_update_member(self):
        """测试更新成员"""
        from agent_net.storage import (
            create_enclave, add_enclave_member, update_enclave_member, get_enclave_member
        )
        from agent_net.enclave.models import Enclave

        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")
        await add_enclave_member(enclave_id, "did:agentnexus:member1", "developer")

        ok = await update_enclave_member(
            enclave_id=enclave_id,
            did="did:agentnexus:member1",
            role="senior_developer",
            permissions="admin",
        )
        assert ok

        member = await get_enclave_member(enclave_id, "did:agentnexus:member1")
        assert member["role"] == "senior_developer"
        assert member["permissions"] == "admin"

    @pytest.mark.asyncio
    async def test_remove_member(self):
        """测试移除成员"""
        from agent_net.storage import (
            create_enclave, add_enclave_member, remove_enclave_member, get_enclave_member
        )
        from agent_net.enclave.models import Enclave

        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")
        await add_enclave_member(enclave_id, "did:agentnexus:member1", "developer")

        ok = await remove_enclave_member(enclave_id, "did:agentnexus:member1")
        assert ok

        member = await get_enclave_member(enclave_id, "did:agentnexus:member1")
        assert member is None


class TestVaultOperations:
    """Vault 操作测试"""

    @pytest.mark.asyncio
    async def test_vault_put_and_get(self):
        """测试 Vault 写入和读取"""
        from agent_net.storage import create_enclave, vault_put, vault_get
        from agent_net.enclave.models import Enclave

        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")

        # 写入
        result = await vault_put(
            enclave_id=enclave_id,
            key="requirements",
            value="# 需求文档\n\n用户需要登录功能...",
            author_did="did:agentnexus:owner",
            message="初始需求",
        )
        assert result["key"] == "requirements"
        assert result["version"] == 1

        # 读取
        entry = await vault_get(enclave_id, "requirements")
        assert entry is not None
        assert entry["value"] == "# 需求文档\n\n用户需要登录功能..."
        assert entry["version"] == 1

    @pytest.mark.asyncio
    async def test_vault_update(self):
        """测试 Vault 更新（版本递增）"""
        from agent_net.storage import create_enclave, vault_put, vault_get
        from agent_net.enclave.models import Enclave

        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")

        # 第一次写入
        await vault_put(enclave_id, "doc", "v1", "did:agentnexus:owner")
        entry1 = await vault_get(enclave_id, "doc")
        assert entry1["version"] == 1

        # 第二次写入（更新）
        await vault_put(enclave_id, "doc", "v2", "did:agentnexus:owner", "更新")
        entry2 = await vault_get(enclave_id, "doc")
        assert entry2["version"] == 2
        assert entry2["value"] == "v2"

    @pytest.mark.asyncio
    async def test_vault_history(self):
        """测试 Vault 历史版本"""
        from agent_net.storage import create_enclave, vault_put, vault_history
        from agent_net.enclave.models import Enclave

        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")

        # 多次写入
        await vault_put(enclave_id, "doc", "v1", "did:agentnexus:owner", "第一次")
        await vault_put(enclave_id, "doc", "v2", "did:agentnexus:owner", "第二次")
        await vault_put(enclave_id, "doc", "v3", "did:agentnexus:owner", "第三次")

        # 查询历史
        history = await vault_history(enclave_id, "doc")
        assert len(history) == 3
        # 按版本倒序
        assert history[0]["version"] == 3
        assert history[1]["version"] == 2
        assert history[2]["version"] == 1
        # 验证 action 字段
        assert history[2]["action"] == "create"  # 第一次是 create
        assert history[1]["action"] == "update"  # 后续是 update
        assert history[0]["action"] == "update"

    @pytest.mark.asyncio
    async def test_vault_list(self):
        """测试列出 Vault 文档"""
        from agent_net.storage import create_enclave, vault_put, vault_list
        from agent_net.enclave.models import Enclave

        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")

        # 写入多个文档
        await vault_put(enclave_id, "design/api", "...", "did:agentnexus:owner")
        await vault_put(enclave_id, "design/db", "...", "did:agentnexus:owner")
        await vault_put(enclave_id, "requirements", "...", "did:agentnexus:owner")

        # 列出全部
        all_docs = await vault_list(enclave_id)
        assert len(all_docs) == 3

        # 按前缀过滤
        design_docs = await vault_list(enclave_id, prefix="design/")
        assert len(design_docs) == 2

    @pytest.mark.asyncio
    async def test_vault_delete(self):
        """测试删除 Vault 文档"""
        from agent_net.storage import create_enclave, vault_put, vault_get, vault_delete, vault_history
        from agent_net.enclave.models import Enclave

        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")

        await vault_put(enclave_id, "doc", "content", "did:agentnexus:owner")

        ok = await vault_delete(enclave_id, "doc", "did:agentnexus:owner")
        assert ok

        entry = await vault_get(enclave_id, "doc")
        assert entry is None

        # 验证删除记录在历史中，action='delete'
        history = await vault_history(enclave_id, "doc")
        # 历史应该包含 create + delete 两条记录
        assert len(history) == 2
        assert history[0]["action"] == "delete"
        assert history[1]["action"] == "create"

        # 删除不存在的文档
        ok2 = await vault_delete(enclave_id, "nonexistent", "did:agentnexus:owner")
        assert not ok2


class TestPlaybookOperations:
    """Playbook 操作测试"""

    @pytest.mark.asyncio
    async def test_create_playbook(self):
        """测试创建 Playbook"""
        from agent_net.storage import create_playbook, get_playbook
        from agent_net.enclave.models import Playbook, Stage

        playbook_id = Playbook.gen_id()
        stages = [
            Stage(name="design", role="architect", description="输出设计方案"),
            Stage(name="review", role="reviewer", description="评审设计"),
        ]

        await create_playbook(
            playbook_id=playbook_id,
            name="标准开发流程",
            stages=[s.to_dict() for s in stages],
            description="标准流程",
            created_by="did:agentnexus:owner",
        )

        pb = await get_playbook(playbook_id)
        assert pb is not None
        assert pb["name"] == "标准开发流程"
        assert len(pb["stages"]) == 2

    @pytest.mark.asyncio
    async def test_create_playbook_run(self):
        """测试创建 Playbook Run"""
        from agent_net.storage import (
            create_enclave, create_playbook, create_playbook_run,
            get_playbook_run, add_enclave_member,
        )
        from agent_net.enclave.models import Enclave, Playbook, Stage

        # 创建 Enclave
        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")
        await add_enclave_member(enclave_id, "did:agentnexus:architect", "architect")

        # 创建 Playbook
        playbook_id = Playbook.gen_id()
        stages = [Stage(name="design", role="architect", description="输出设计")]
        await create_playbook(playbook_id, "流程", [s.to_dict() for s in stages])

        # 创建 Run
        run_id = Playbook.gen_id().replace("pb_", "run_")
        await create_playbook_run(run_id, enclave_id, playbook_id, "流程")

        run = await get_playbook_run(run_id)
        assert run is not None
        assert run["enclave_id"] == enclave_id
        assert run["playbook_id"] == playbook_id
        assert run["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_latest_playbook_run(self):
        """测试获取最新 Playbook Run"""
        from agent_net.storage import (
            create_enclave, create_playbook, create_playbook_run,
            get_latest_playbook_run, add_enclave_member,
        )
        from agent_net.enclave.models import Enclave, Playbook, Stage

        # 创建 Enclave
        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")
        await add_enclave_member(enclave_id, "did:agentnexus:architect", "architect")

        # 创建 Playbook
        playbook_id = Playbook.gen_id()
        stages = [Stage(name="design", role="architect", description="输出设计")]
        await create_playbook(playbook_id, "流程", [s.to_dict() for s in stages])

        # 创建多个 Run
        import time
        run_id1 = Playbook.gen_id().replace("pb_", "run_")
        await create_playbook_run(run_id1, enclave_id, playbook_id, "流程1")
        time.sleep(0.01)  # 确保时间不同
        run_id2 = Playbook.gen_id().replace("pb_", "run_")
        await create_playbook_run(run_id2, enclave_id, playbook_id, "流程2")

        # 获取最新 run
        latest = await get_latest_playbook_run(enclave_id)
        assert latest is not None
        assert latest["run_id"] == run_id2  # 应该是最新的那个

        # 空 Enclave 应返回 None
        empty_enclave_id = Enclave.gen_id()
        await create_enclave(empty_enclave_id, "空项目", "did:agentnexus:owner")
        empty = await get_latest_playbook_run(empty_enclave_id)
        assert empty is None

    @pytest.mark.asyncio
    async def test_stage_execution(self):
        """测试阶段执行记录"""
        from agent_net.storage import (
            create_enclave, create_playbook, create_playbook_run,
            create_stage_execution, get_stage_execution, update_stage_execution,
        )
        from agent_net.enclave.models import Enclave, Playbook, Stage

        # 准备数据
        enclave_id = Enclave.gen_id()
        await create_enclave(enclave_id, "测试项目", "did:agentnexus:owner")

        playbook_id = Playbook.gen_id()
        await create_playbook(playbook_id, "流程", [
            Stage(name="design", role="architect").to_dict()
        ])

        run_id = Playbook.gen_id().replace("pb_", "run_")
        await create_playbook_run(run_id, enclave_id, playbook_id)

        # 创建阶段执行记录
        ok = await create_stage_execution(
            run_id=run_id,
            stage_name="design",
            assigned_did="did:agentnexus:architect",
            task_id="task_001",
        )
        assert ok

        exec_record = await get_stage_execution(run_id, "design")
        assert exec_record is not None
        assert exec_record["status"] == "active"
        assert exec_record["assigned_did"] == "did:agentnexus:architect"
        assert exec_record["retry_count"] == 0

        # 更新状态
        await update_stage_execution(run_id, "design", status="completed", output_ref="design_doc")

        exec_record2 = await get_stage_execution(run_id, "design")
        assert exec_record2["status"] == "completed"
        assert exec_record2["output_ref"] == "design_doc"

        # 重复创建同一阶段应重新分配并递增 retry_count
        ok2 = await create_stage_execution(
            run_id=run_id,
            stage_name="design",
            assigned_did="did:agentnexus:architect2",
            task_id="task_002",
        )
        assert ok2

        exec_record3 = await get_stage_execution(run_id, "design")
        assert exec_record3["status"] == "active"
        assert exec_record3["assigned_did"] == "did:agentnexus:architect2"
        assert exec_record3["task_id"] == "task_002"
        assert exec_record3["output_ref"] == ""
        assert exec_record3["retry_count"] == 1

        await update_stage_execution(
            run_id, "design",
            retry_count=2,
            task_id="task_003",
            assigned_did="did:agentnexus:architect3",
        )
        exec_record4 = await get_stage_execution(run_id, "design")
        assert exec_record4["retry_count"] == 2
        assert exec_record4["task_id"] == "task_003"
        assert exec_record4["assigned_did"] == "did:agentnexus:architect3"


class TestLocalVaultBackend:
    """LocalVaultBackend 测试"""

    @pytest.mark.asyncio
    async def test_backend_operations(self):
        """测试 LocalVaultBackend 完整操作"""
        from agent_net.enclave import LocalVaultBackend
        from agent_net.storage import DB_PATH

        backend = LocalVaultBackend(enclave_id="enc_test", db_path=DB_PATH)

        # 写入
        entry = await backend.put("test_key", "test_value", "did:agentnexus:owner", "测试")
        assert entry.key == "test_key"
        assert entry.version == "1"

        # 读取
        entry2 = await backend.get("test_key")
        assert entry2.value == "test_value"

        # 更新
        entry3 = await backend.put("test_key", "updated", "did:agentnexus:owner")
        assert entry3.version == "2"

        # 历史版本
        history = await backend.history("test_key")
        assert len(history) == 2

        # 列出
        entries = await backend.list()
        assert len(entries) == 1

        # 删除
        ok = await backend.delete("test_key", "did:agentnexus:owner")
        assert ok

        # 删除后读取应抛异常
        with pytest.raises(Exception):  # VaultKeyNotFoundError
            await backend.get("test_key")


class TestEnclaveModels:
    """Enclave 数据模型测试"""

    def test_enclave_model(self):
        """测试 Enclave 模型"""
        from agent_net.enclave.models import Enclave, Member

        enclave = Enclave(
            enclave_id="enc_test",
            name="测试项目",
            owner_did="did:agentnexus:owner",
            members=[
                Member(enclave_id="enc_test", did="did:agentnexus:m1", role="developer")
            ],
        )

        d = enclave.to_dict()
        assert d["enclave_id"] == "enc_test"
        assert len(d["members"]) == 1

        enclave2 = Enclave.from_dict(d)
        assert enclave2.name == enclave.name
        assert len(enclave2.members) == 1

    def test_stage_model(self):
        """测试 Stage 模型"""
        from agent_net.enclave.models import Stage

        stage = Stage(
            name="design",
            role="architect",
            description="输出设计",
            input_keys=["requirements"],
            output_key="design_doc",
            next="review",
            on_reject="design",
        )

        d = stage.to_dict()
        assert d["name"] == "design"
        assert d["input_keys"] == ["requirements"]

        stage2 = Stage.from_dict(d)
        assert stage2.name == stage.name
        assert stage2.input_keys == stage.input_keys

    def test_playbook_model(self):
        """测试 Playbook 模型"""
        from agent_net.enclave.models import Playbook, Stage

        pb = Playbook(
            playbook_id="pb_test",
            name="标准流程",
            stages=[
                Stage(name="design", role="architect"),
                Stage(name="review", role="reviewer"),
            ],
        )

        d = pb.to_dict()
        assert len(d["stages"]) == 2

        pb2 = Playbook.from_dict(d)
        assert pb2.name == pb.name
        assert len(pb2.stages) == 2
