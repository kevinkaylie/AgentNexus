"""Phase A 端到端演示 — 常驻秘书 → Intake → Enclave → Playbook → 交付 → 回传

使用方法:
    python3 scripts/demo_secretary_phase_a.py

演示流程:
1. 注册 Owner DID
2. 注册秘书子 Agent
3. 注册 3 个 Worker (architect, reviewer, developer)
4. 秘书接单 (intake)
5. 秘书选人 → 建 Enclave → 启动 Playbook Run
6. 写入需求产物到 Vault
7. 推进到第一个 stage
8. 查看最终状态
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_net.storage import (
    init_db, register_owner, register_secretary, register_agent,
    bind_agent, list_workers, create_intake, get_intake, update_intake,
    is_secretary, get_owner, get_agent,
    create_enclave, add_enclave_member, get_enclave,
    create_playbook, get_playbook, create_playbook_run,
    create_stage_execution, update_playbook_run, get_playbook_run,
    vault_put, vault_get, vault_list,
)
from agent_net.common.did import DIDGenerator, AgentProfile
from nacl.encoding import HexEncoder


async def main():
    # 初始化 DB（用测试 DB）
    from agent_net.storage import DB_PATH
    from pathlib import Path
    test_db = Path("data/agent_net_demo_phase_a.db")
    if test_db.exists():
        test_db.unlink()

    # 临时替换 DB 路径
    import agent_net.storage as _storage
    original_path = _storage.DB_PATH
    _storage.DB_PATH = test_db

    await init_db()

    print("=" * 60)
    print("Phase A 端到端演示：常驻秘书编排")
    print("=" * 60)

    # 1. 注册 Owner
    print("\n[1] 注册 Owner DID...")
    owner = await register_owner("DemoOwner")
    owner_did = owner["did"]
    print(f"    Owner: {owner_did}")

    # 2. 注册秘书
    print("\n[2] 注册秘书子 Agent...")
    sec = await register_secretary(owner_did, "DemoSecretary")
    sec_did = sec["did"]
    print(f"    Secretary: {sec_did}")

    sec_check = await is_secretary(sec_did)
    assert sec_check is not None, "Secretary check failed"
    print(f"    Secretary 验证通过")

    # 3. 注册 3 个 Worker
    print("\n[3] 注册 3 个 Worker (architect, reviewer, developer)...")
    workers = {}
    for role in ["architect", "reviewer", "developer"]:
        obj, _ = DIDGenerator.create_agentnexus(f"Worker_{role}")
        profile = AgentProfile(
            id=obj.did, name=f"Worker_{role}", type=role,
            capabilities=[role],
        ).to_dict()
        pk_hex = obj.private_key.encode(HexEncoder).decode()
        await register_agent(obj.did, profile, is_local=True, private_key_hex=pk_hex)
        await bind_agent(owner_did, obj.did)
        workers[role] = obj.did
        print(f"    {role}: {obj.did}")

    # 验证 Worker Registry
    print("\n[4] Worker Registry 查询...")
    registry = await list_workers(owner_did)
    print(f"    找到 {len(registry)} 个 Worker (不含秘书)")
    assert len(registry) == 3

    # 4. 秘书接单
    print("\n[5] 秘书创建 intake...")
    session_id = "sess_demo_001"
    intake = await create_intake(
        session_id=session_id,
        owner_did=owner_did,
        actor_did=sec_did,
        objective="完成 AgentNexus 秘书编排设计并形成可评审文档",
        required_roles=["architect", "reviewer", "developer"],
        preferred_playbook="pb_design_review_impl",
        source_channel="webhook",
        source_message_ref="msg_webhook_001",
    )
    print(f"    Intake: {intake['session_id']}, status={intake['status']}")

    # 5. 秘书选人
    print("\n[6] 秘书从 Worker Registry 选人...")
    selected = {}
    for role in ["architect", "reviewer", "developer"]:
        for w in registry:
            if w["profile_type"] == role:
                selected[role] = w["did"]
                break
    await update_intake(session_id, selected_workers=selected, status="ready_to_start")
    print(f"    Selected: {json.dumps(selected, indent=6)}")

    # 6. 创建 Enclave
    print("\n[7] 创建 Enclave...")
    from agent_net.enclave.models import Enclave
    enclave_id = Enclave.gen_id()
    await create_enclave(
        enclave_id=enclave_id, name=f"sec-{session_id[:8]}",
        owner_did=owner_did, vault_backend="local",
    )

    # 成员加入
    await add_enclave_member(enclave_id=enclave_id, did=owner_did, role="owner",
                             permissions="admin", handbook="Enclave owner")
    await add_enclave_member(enclave_id=enclave_id, did=sec_did, role="secretary",
                             permissions="rw", handbook="Secretary orchestrator")
    for role, did in selected.items():
        await add_enclave_member(enclave_id=enclave_id, did=did, role=role,
                                 permissions="rw", handbook=f"Role: {role}")

    print(f"    Enclave: {enclave_id}")
    print(f"    Members: owner + secretary + {len(selected)} workers")

    # 7. 写入需求产物
    print("\n[8] 秘书写入需求产物到 Vault...")
    requirements = json.dumps({
        "objective": "完成 AgentNexus 秘书编排设计",
        "required_roles": ["architect", "reviewer", "developer"],
        "source": "webhook",
    })
    await vault_put(enclave_id, "requirements/intake.json", requirements, sec_did, "Initial intake requirements")
    print(f"    写入: requirements/intake.json")

    # 8. 创建 Playbook
    print("\n[9] 创建 Playbook + Run...")
    playbook_id = "pb_demo_design_review"
    stages = [
        {"name": "design", "role": "architect", "description": "架构设计"},
        {"name": "review", "role": "reviewer", "description": "设计评审"},
        {"name": "implement", "role": "developer", "description": "实现开发"},
    ]
    await create_playbook(
        playbook_id=playbook_id, name="demo-design-review-impl",
        stages=stages, description="Demo Playbook",
        created_by=sec_did,
    )

    from agent_net.enclave.models import PlaybookRun
    run_id = PlaybookRun.gen_id()
    await create_playbook_run(
        run_id=run_id, enclave_id=enclave_id,
        playbook_id=playbook_id, playbook_name="demo-design-review-impl",
    )

    # 建立 session_id -> run_id 绑定
    await update_intake(session_id, run_id=run_id, status="running")

    # 初始化 Context Snapshot
    snapshot = {
        "thread_id": run_id,
        "session_id": session_id,
        "objective": "完成 AgentNexus 秘书编排设计",
        "current_stage": "design",
        "intake": {
            "session_id": session_id,
            "source": {"channel": "webhook"},
            "selected_workers": selected,
        },
    }
    await update_playbook_run(run_id, current_stage="design", context=snapshot)

    # 启动第一个 stage
    await create_stage_execution(
        run_id=run_id, stage_name="design",
        assigned_did=selected["architect"],
    )

    print(f"    Run: {run_id}")
    print(f"    Current stage: design")
    print(f"    Assigned to: {selected['architect']}")

    # 9. 查看 Vault 内容
    print("\n[10] Vault 内容列表...")
    entries = await vault_list(enclave_id)
    for e in entries:
        print(f"    - {e}")

    # 10. 查看 Run 状态
    print("\n[11] Run 最终状态...")
    run = await get_playbook_run(run_id)
    print(f"    run_id: {run['run_id']}")
    print(f"    status: {run['status']}")
    print(f"    current_stage: {run['current_stage']}")

    # 11. 回传状态
    print("\n[12] 回传状态给 owner...")
    intake_final = await get_intake(session_id)
    print(f"    session_id: {intake_final['session_id']}")
    print(f"    run_id: {intake_final['run_id']}")
    print(f"    status: {intake_final['status']}")
    print(f"    selected_workers: {json.dumps(intake_final['selected_workers'])}")

    print("\n" + "=" * 60)
    print("Phase A 演示完成！")
    print("秘书建单 → 选人 → 建 Enclave → 写入需求 → 启动 Playbook → 状态回传")
    print("=" * 60)

    # 恢复 DB 路径
    _storage.DB_PATH = original_path


if __name__ == "__main__":
    asyncio.run(main())
