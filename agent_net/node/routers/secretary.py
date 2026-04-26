"""秘书编排端点 — D-SEC-02"""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException

from agent_net.node._auth import (
    _require_token,
    _verify_actor_is_secretary,
    _verify_actor_is_owner,
    _verify_actor_is_enclave_member,
)
from agent_net.storage import (
    create_intake, get_intake, update_intake, list_intakes,
    list_workers, get_owner, is_secretary,
    create_enclave, add_enclave_member, get_enclave,
    create_playbook, get_playbook, create_playbook_run, get_playbook_run,
    create_stage_execution, update_playbook_run,
)

router = APIRouter()


# ── Intake 管理 ──────────────────────────────────────────────

@router.post("/secretary/intake")
async def api_create_intake(req: dict, _=Depends(_require_token)):
    """D-SEC-02: 秘书创建 intake 记录。"""
    session_id = req.get("session_id")
    owner_did = req.get("owner_did")
    actor_did = req.get("actor_did")
    objective = req.get("objective")
    required_roles = req.get("required_roles", [])
    preferred_playbook = req.get("preferred_playbook")
    source = req.get("source", {})

    if not all([session_id, owner_did, actor_did, objective, required_roles]):
        raise HTTPException(400, "Missing required fields: session_id, owner_did, actor_did, objective, required_roles")

    # 校验 actor_did 是 owner 绑定的 secretary
    await _verify_actor_is_secretary(actor_did)
    sec = await is_secretary(actor_did)
    if not sec or sec.get("owner_did") != owner_did:
        raise HTTPException(403, "Secretary is not bound to this owner")

    # 校验 owner 存在
    owner = await get_owner(owner_did)
    if not owner:
        raise HTTPException(404, "Owner not found")

    intake = await create_intake(
        session_id=session_id,
        owner_did=owner_did,
        actor_did=actor_did,
        objective=objective,
        required_roles=required_roles,
        preferred_playbook=preferred_playbook,
        source_channel=source.get("channel"),
        source_message_ref=source.get("message_ref"),
        constraints=req.get("constraints"),
    )
    return {"status": "accepted", "intake": intake}


@router.get("/secretary/intake/{session_id}")
async def api_get_intake(session_id: str, actor_did: str, _=Depends(_require_token)):
    """D-SEC-02: 查询 intake 状态。"""
    await _verify_actor_is_secretary(actor_did)
    intake = await get_intake(session_id)
    if not intake:
        raise HTTPException(404, "Intake not found")
    return {"status": "ok", "intake": intake}


@router.get("/secretary/intakes/{owner_did}")
async def api_list_intakes(owner_did: str, actor_did: str, status: str = None, _=Depends(_require_token)):
    """D-SEC-02: 列出 owner 的 intake 记录。"""
    await _verify_actor_is_owner(actor_did)
    if actor_did != owner_did:
        raise HTTPException(403, "Actor cannot list another owner's intakes")
    intakes = await list_intakes(owner_did, status)
    return {"status": "ok", "intakes": intakes, "count": len(intakes)}


# ── 秘书接单 → 选人 → 建 Enclave → 启动 Run ──────────────────

@router.post("/secretary/dispatch")
async def api_dispatch(req: dict, _=Depends(_require_token)):
    """
    D-SEC-02: 秘书接单并启动协作链路。
    输入: {session_id, owner_did, actor_did, objective, required_roles, preferred_playbook, source, entry_mode}
    entry_mode: "owner_pre_authorized" | "owner_confirm_required"
    """
    session_id = req.get("session_id")
    owner_did = req.get("owner_did")
    actor_did = req.get("actor_did")
    objective = req.get("objective")
    required_roles = req.get("required_roles", [])
    preferred_playbook = req.get("preferred_playbook")
    entry_mode = req.get("entry_mode", "owner_pre_authorized")

    if not all([session_id, owner_did, actor_did, objective, required_roles]):
        raise HTTPException(400, "Missing required fields")

    # 1. 校验 secretary 身份
    await _verify_actor_is_secretary(actor_did)
    sec = await is_secretary(actor_did)
    if not sec or sec.get("owner_did") != owner_did:
        raise HTTPException(403, "Secretary is not bound to this owner")

    owner = await get_owner(owner_did)
    if not owner:
        raise HTTPException(404, "Owner not found")

    # 2. 入口模式判断
    if entry_mode == "owner_confirm_required":
        # 先创建 intake，停在 awaiting_owner_confirm
        intake = await create_intake(
            session_id=session_id, owner_did=owner_did, actor_did=actor_did,
            objective=objective, required_roles=required_roles,
            preferred_playbook=preferred_playbook,
            source_channel=req.get("source", {}).get("channel"),
            source_message_ref=req.get("source", {}).get("message_ref"),
        )
        await update_intake(session_id, status="awaiting_owner_confirm")
        return {"status": "awaiting_owner_confirm", "intake": intake}

    # 3. 选人 — 从 Worker Registry 按 required_roles 匹配
    workers = await list_workers(owner_did)
    selected_workers = {}
    missing_roles = []

    for role in required_roles:
        # 按 capabilities 匹配：role 名称应在 worker capabilities 中
        matched = None
        for w in workers:
            caps = [c.lower() for c in w.get("capabilities", [])]
            profile_type = w.get("profile_type", "").lower()
            if role.lower() in caps or role.lower() == profile_type:
                if w.get("online"):
                    matched = w["did"]
                    break
                elif not matched:
                    matched = w["did"]  # 离线备选
        if matched:
            selected_workers[role] = matched
        else:
            missing_roles.append(role)

    if missing_roles:
        intake = await create_intake(
            session_id=session_id, owner_did=owner_did, actor_did=actor_did,
            objective=objective, required_roles=required_roles,
            preferred_playbook=preferred_playbook,
        )
        await update_intake(session_id, status="blocked")
        return {
            "status": "blocked",
            "reason": f"Missing roles: {', '.join(missing_roles)}",
            "missing_roles": missing_roles,
        }

    # 4. 创建 Enclave
    from agent_net.enclave.models import Enclave, PlaybookRun
    enclave_id = Enclave.gen_id()
    await create_enclave(
        enclave_id=enclave_id, name=f"sec-{session_id[:8]}",
        owner_did=owner_did, vault_backend="local",
    )

    # Owner 作为 admin 加入
    await add_enclave_member(
        enclave_id=enclave_id, did=owner_did, role="owner",
        permissions="admin", handbook="Enclave owner",
    )

    # 秘书作为 rw 加入（需要继续写 Vault / 创建 Run）
    await add_enclave_member(
        enclave_id=enclave_id, did=actor_did, role="secretary",
        permissions="rw", handbook="Secretary orchestrator",
    )

    # Worker 成员加入
    for role, did in selected_workers.items():
        await add_enclave_member(
            enclave_id=enclave_id, did=did, role=role,
            permissions="rw", handbook=f"Role: {role}",
        )

    # 5. 选择 Playbook
    playbook = None
    if preferred_playbook:
        playbook = await get_playbook(preferred_playbook)

    stages = None
    if not playbook:
        # 创建默认 Playbook
        from agent_net.enclave.models import Playbook, PlaybookRun, Stage
        playbook_id = Playbook.gen_id()
        stages = []
        for role in required_roles:
            stages.append({"name": role, "role": role, "description": f"{role} stage"})
        await create_playbook(
            playbook_id=playbook_id, name="default-orchestration",
            stages=stages, description="Default secretary playbook",
            created_by=actor_did,
        )
        playbook = await get_playbook(playbook_id)

    if stages is None:
        stages = playbook.get("stages", [])

    # 6. 创建 Run
    run_id = PlaybookRun.gen_id()
    await create_playbook_run(
        run_id=run_id, enclave_id=enclave_id,
        playbook_id=playbook["playbook_id"], playbook_name=playbook["name"],
    )

    # 7. 建立 session_id -> run_id 绑定（P1_2: 先创建 intake 再更新）
    await create_intake(
        session_id=session_id, owner_did=owner_did, actor_did=actor_did,
        objective=objective, required_roles=required_roles,
        preferred_playbook=preferred_playbook,
        source_channel=req.get("source", {}).get("channel"),
        source_message_ref=req.get("source", {}).get("message_ref"),
    )
    await update_intake(session_id, status="running", run_id=run_id, selected_workers=selected_workers)

    # 8. 初始化 Context Snapshot
    snapshot = {
        "thread_id": run_id,
        "session_id": session_id,
        "objective": objective,
        "current_stage": stages[0]["name"] if stages else None,
        "intake": {
            "session_id": session_id,
            "source": req.get("source", {}),
            "selected_workers": selected_workers,
        },
    }
    await update_playbook_run(run_id, current_stage=stages[0]["name"] if stages else None, context=snapshot)

    # 9. 启动第一个 stage
    if stages:
        first_stage = stages[0]
        assigned_did = selected_workers.get(first_stage["role"])
        if assigned_did:
            await create_stage_execution(
                run_id=run_id, stage_name=first_stage["name"], assigned_did=assigned_did,
            )

    return {
        "status": "started",
        "run_id": run_id,
        "enclave_id": enclave_id,
        "playbook_name": playbook["name"],
        "current_stage": stages[0]["name"] if stages else None,
        "selected_workers": selected_workers,
    }


@router.post("/secretary/intake/{session_id}/confirm")
async def api_confirm_intake(session_id: str, req: dict, _=Depends(_require_token)):
    """D-SEC-02: Owner 确认 intake，触发 dispatch。"""
    owner_did = req.get("owner_did")
    actor_did = req.get("actor_did")
    if not owner_did or not actor_did:
        raise HTTPException(400, "Missing owner_did or actor_did")

    await _verify_actor_is_owner(actor_did)
    if actor_did != owner_did:
        raise HTTPException(403, "Only the owner can confirm")

    intake = await get_intake(session_id)
    if not intake:
        raise HTTPException(404, "Intake not found")
    if intake["status"] != "awaiting_owner_confirm":
        raise HTTPException(400, f"Intake status is {intake['status']}, not awaiting confirmation")

    await update_intake(session_id, status="ready_to_start")
    return {"status": "confirmed", "session_id": session_id}


# ── D-SEC-06: Owner 接管 ─────────────────────────────────────

@router.post("/secretary/intake/{session_id}/abort")
async def api_abort_run(session_id: str, req: dict, _=Depends(_require_token)):
    """
    D-SEC-06: Owner 终止整个 Run。
    请求体：{"actor_did": "<owner_did>", "reason": "<可选>"}
    """
    actor_did = req.get("actor_did")
    reason = req.get("reason", "")
    if not actor_did:
        raise HTTPException(400, "Missing actor_did")

    await _verify_actor_is_owner(actor_did)

    intake = await get_intake(session_id)
    if not intake:
        raise HTTPException(404, "Intake not found")
    if intake["owner_did"] != actor_did:
        raise HTTPException(403, "Actor is not the owner of this intake")

    run_id = intake.get("run_id")
    if not run_id:
        await update_intake(session_id, status="aborted")
        return {"status": "aborted", "session_id": session_id, "note": "No active run to abort"}

    # 终止 Playbook Run
    run = await get_playbook_run(run_id)
    if not run:
        raise HTTPException(404, "Playbook run not found")
    if run["status"] in ("completed", "failed", "aborted"):
        raise HTTPException(400, f"Run already in terminal state: {run['status']}")

    import time
    await update_playbook_run(run_id, status="aborted", completed_at=time.time())
    await update_intake(session_id, status="aborted")

    # 将所有 active/pending 的 stage_execution 标记为 aborted
    from agent_net.storage import get_stage_executions_for_run, update_stage_execution
    executions = await get_stage_executions_for_run(run_id)
    for exe in executions:
        if exe["status"] in ("pending", "active"):
            await update_stage_execution(
                run_id=run_id,
                stage_name=exe["stage_name"],
                status="aborted",
                output_ref=reason,
            )

    return {"status": "aborted", "session_id": session_id, "run_id": run_id, "reason": reason}
