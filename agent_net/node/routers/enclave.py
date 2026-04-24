"""Enclave API (ADR-013)"""
from fastapi import APIRouter, Depends, HTTPException

from agent_net.node._auth import (
    _require_token,
    _verify_actor,
    _verify_actor_is_enclave_member,
    _verify_actor_is_enclave_owner,
)
from agent_net.node._models import (
    CreateEnclaveRequest, UpdateEnclaveRequest,
    AddMemberRequest, UpdateMemberRequest,
    VaultPutRequest, CreatePlaybookRunRequest,
)
from agent_net.storage import (
    create_enclave, get_enclave, list_enclaves, update_enclave, delete_enclave,
    add_enclave_member, get_enclave_member, list_enclave_members,
    update_enclave_member, remove_enclave_member,
    vault_get, vault_put, vault_list, vault_history, vault_delete,
    create_playbook, get_playbook,
    create_playbook_run, get_playbook_run, get_latest_playbook_run, update_playbook_run,
    create_stage_execution, list_stage_executions,
)

router = APIRouter()


def _check_vault_permission(member: dict, required: str) -> None:
    if not member:
        raise HTTPException(403, "Not a member of this enclave")
    perms = member.get("permissions", "rw")
    if required == "rw" and perms == "r":
        raise HTTPException(403, "Read-only access")
    if required == "admin" and perms != "admin":
        raise HTTPException(403, "Admin access required")


def _build_stages_status(stage_executions: list, playbook: dict) -> dict:
    stages_status = {}
    if playbook:
        for stage in playbook["stages"]:
            stage_name = stage["name"]
            exec_record = next(
                (e for e in stage_executions if e["stage_name"] == stage_name), None
            )
            stages_status[stage_name] = {
                "status": exec_record["status"] if exec_record else "pending",
                "assigned_did": exec_record["assigned_did"] if exec_record else "",
                "task_id": exec_record["task_id"] if exec_record else "",
                "output_ref": exec_record["output_ref"] if exec_record else "",
            }
    return stages_status


# ── Enclave CRUD ──────────────────────────────────────────────

@router.post("/enclaves")
async def api_create_enclave(req: CreateEnclaveRequest, _=Depends(_require_token)):
    from agent_net.enclave.models import Enclave
    await _verify_actor(req.owner_did)
    enclave_id = Enclave.gen_id()
    await create_enclave(
        enclave_id=enclave_id, name=req.name, owner_did=req.owner_did,
        vault_backend=req.vault_backend, vault_config=req.vault_config,
    )
    for role, member_data in req.members.items():
        await add_enclave_member(
            enclave_id=enclave_id, did=member_data["did"], role=role,
            permissions=member_data.get("permissions", "rw"),
            handbook=member_data.get("handbook", ""),
        )
    owner_member = await get_enclave_member(enclave_id, req.owner_did)
    if not owner_member:
        await add_enclave_member(
            enclave_id=enclave_id, did=req.owner_did,
            role="owner", permissions="admin", handbook="Enclave owner",
        )
    return {"status": "ok", "enclave_id": enclave_id}


@router.get("/enclaves")
async def api_list_enclaves(actor_did: str, status: str = None, _=Depends(_require_token)):
    await _verify_actor(actor_did)
    enclaves = await list_enclaves(did=actor_did, status=status)
    result = []
    for enc in enclaves:
        members = await list_enclave_members(enc["enclave_id"])
        enc["members"] = members
        result.append(enc)
    return {"status": "ok", "enclaves": result, "count": len(result)}


@router.get("/enclaves/{enclave_id}")
async def api_get_enclave(enclave_id: str, actor_did: str, _=Depends(_require_token)):
    await _verify_actor_is_enclave_member(enclave_id, actor_did)
    enc = await get_enclave(enclave_id)
    if not enc:
        raise HTTPException(404, "Enclave not found")
    enc["members"] = await list_enclave_members(enclave_id)
    return {"status": "ok", **enc}


@router.patch("/enclaves/{enclave_id}")
async def api_update_enclave(enclave_id: str, req: UpdateEnclaveRequest, _=Depends(_require_token)):
    if not req.actor_did:
        raise HTTPException(400, "Missing actor_did")
    await _verify_actor_is_enclave_owner(enclave_id, req.actor_did)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    updates.pop("actor_did", None)
    if not updates:
        raise HTTPException(400, "No fields to update")
    ok = await update_enclave(enclave_id, **updates)
    if not ok:
        raise HTTPException(404, "Enclave not found")
    return {"status": "ok"}


@router.delete("/enclaves/{enclave_id}")
async def api_delete_enclave(enclave_id: str, actor_did: str, _=Depends(_require_token)):
    await _verify_actor_is_enclave_owner(enclave_id, actor_did)
    ok = await delete_enclave(enclave_id)
    if not ok:
        raise HTTPException(404, "Enclave not found")
    return {"status": "ok", "archived": True}


# ── Members ───────────────────────────────────────────────────

@router.post("/enclaves/{enclave_id}/members")
async def api_add_member(enclave_id: str, req: AddMemberRequest, _=Depends(_require_token)):
    await _verify_actor_is_enclave_owner(enclave_id, req.actor_did)
    if not await get_enclave(enclave_id):
        raise HTTPException(404, "Enclave not found")
    ok = await add_enclave_member(
        enclave_id=enclave_id, did=req.did, role=req.role,
        permissions=req.permissions, handbook=req.handbook,
    )
    if not ok:
        raise HTTPException(409, "Member already exists")
    return {"status": "ok"}


@router.delete("/enclaves/{enclave_id}/members/{did}")
async def api_remove_member(enclave_id: str, did: str, actor_did: str, _=Depends(_require_token)):
    await _verify_actor_is_enclave_owner(enclave_id, actor_did)
    ok = await remove_enclave_member(enclave_id, did)
    if not ok:
        raise HTTPException(404, "Member not found")
    return {"status": "ok"}


@router.patch("/enclaves/{enclave_id}/members/{did}")
async def api_update_member(enclave_id: str, did: str, req: UpdateMemberRequest, _=Depends(_require_token)):
    if not req.actor_did:
        raise HTTPException(400, "Missing actor_did")
    await _verify_actor_is_enclave_owner(enclave_id, req.actor_did)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    updates.pop("actor_did", None)
    if not updates:
        raise HTTPException(400, "No fields to update")
    ok = await update_enclave_member(enclave_id, did, **updates)
    if not ok:
        raise HTTPException(404, "Member not found")
    return {"status": "ok"}


# ── Vault ─────────────────────────────────────────────────────

@router.get("/enclaves/{enclave_id}/vault")
async def api_vault_list(enclave_id: str, actor_did: str, prefix: str = "", _=Depends(_require_token)):
    await _verify_actor_is_enclave_member(enclave_id, actor_did)
    entries = await vault_list(enclave_id, prefix)
    return {"status": "ok", "entries": entries, "count": len(entries)}


@router.get("/enclaves/{enclave_id}/vault/{key:path}")
async def api_vault_get(enclave_id: str, key: str, actor_did: str, version: str = None, _=Depends(_require_token)):
    await _verify_actor_is_enclave_member(enclave_id, actor_did)
    entry = await vault_get(enclave_id, key, version=int(version) if version else None)
    if not entry:
        raise HTTPException(404, f"Key not found: {key}")
    return {"status": "ok", **entry}


@router.put("/enclaves/{enclave_id}/vault/{key:path}")
async def api_vault_put(enclave_id: str, key: str, req: VaultPutRequest, _=Depends(_require_token)):
    member = await _verify_actor_is_enclave_member(enclave_id, req.author_did)
    _check_vault_permission(member, "rw")
    result = await vault_put(
        enclave_id=enclave_id, key=key, value=req.value,
        author_did=req.author_did, message=req.message,
    )
    return {"status": "ok", **result}


@router.delete("/enclaves/{enclave_id}/vault/{key:path}")
async def api_vault_delete(enclave_id: str, key: str, actor_did: str, _=Depends(_require_token)):
    member = await _verify_actor_is_enclave_member(enclave_id, actor_did)
    _check_vault_permission(member, "rw")
    ok = await vault_delete(enclave_id, key, actor_did)
    if not ok:
        raise HTTPException(404, f"Key not found: {key}")
    return {"status": "ok", "deleted": True}


@router.get("/enclaves/{enclave_id}/vault/{key:path}/history")
async def api_vault_history(enclave_id: str, key: str, actor_did: str, limit: int = 10, _=Depends(_require_token)):
    await _verify_actor_is_enclave_member(enclave_id, actor_did)
    history = await vault_history(enclave_id, key, limit)
    return {"status": "ok", "history": history}


# ── Playbook Runs ─────────────────────────────────────────────

@router.post("/enclaves/{enclave_id}/runs")
async def api_create_playbook_run(enclave_id: str, req: CreatePlaybookRunRequest, _=Depends(_require_token)):
    from agent_net.enclave.models import Playbook, PlaybookRun, Stage

    member = await _verify_actor_is_enclave_member(enclave_id, req.actor_did)
    _check_vault_permission(member, "rw")

    if req.playbook_id:
        playbook = await get_playbook(req.playbook_id)
        if not playbook:
            raise HTTPException(404, "Playbook not found")
    elif req.playbook:
        playbook_id = Playbook.gen_id()
        stages = [Stage.from_dict(s) for s in req.playbook.get("stages", [])]
        await create_playbook(
            playbook_id=playbook_id,
            name=req.playbook.get("name", "inline"),
            stages=[s.to_dict() for s in stages],
            description=req.playbook.get("description", ""),
            created_by="",
        )
        playbook = await get_playbook(playbook_id)
    else:
        raise HTTPException(400, "Either playbook_id or playbook is required")

    run_id = PlaybookRun.gen_id()
    await create_playbook_run(
        run_id=run_id, enclave_id=enclave_id,
        playbook_id=playbook["playbook_id"], playbook_name=playbook["name"],
    )

    stages = playbook["stages"]
    assigned_did = None
    if stages:
        first_stage = stages[0]
        members = await list_enclave_members(enclave_id)
        for m in members:
            if m["role"] == first_stage["role"]:
                assigned_did = m["did"]
                break
        if assigned_did:
            await create_stage_execution(
                run_id=run_id, stage_name=first_stage["name"], assigned_did=assigned_did,
            )
            await update_playbook_run(run_id, current_stage=first_stage["name"])

    return {
        "status": "ok",
        "run_id": run_id,
        "current_stage": stages[0]["name"] if stages else None,
        "assigned_did": assigned_did,
    }


@router.get("/enclaves/{enclave_id}/runs")
async def api_get_latest_playbook_run(enclave_id: str, actor_did: str, _=Depends(_require_token)):
    await _verify_actor_is_enclave_member(enclave_id, actor_did)
    run = await get_latest_playbook_run(enclave_id)
    if not run:
        raise HTTPException(404, "No playbook runs found for this enclave")
    stage_executions = await list_stage_executions(run["run_id"])
    playbook = await get_playbook(run["playbook_id"])
    return {
        "status": "ok",
        "run_id": run["run_id"],
        "playbook_name": run["playbook_name"],
        "current_stage": run["current_stage"],
        "run_status": run["status"],
        "stages": _build_stages_status(stage_executions, playbook),
        "started_at": run["started_at"],
        "completed_at": run.get("completed_at"),
    }


@router.get("/enclaves/{enclave_id}/runs/{run_id}")
async def api_get_playbook_run(enclave_id: str, run_id: str, actor_did: str, _=Depends(_require_token)):
    await _verify_actor_is_enclave_member(enclave_id, actor_did)
    run = await get_playbook_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run["enclave_id"] != enclave_id:
        raise HTTPException(404, "Run not found in this enclave")
    stage_executions = await list_stage_executions(run_id)
    playbook = await get_playbook(run["playbook_id"])
    return {
        "status": "ok",
        "run_id": run["run_id"],
        "playbook_name": run["playbook_name"],
        "current_stage": run["current_stage"],
        "run_status": run["status"],
        "stages": _build_stages_status(stage_executions, playbook),
        "started_at": run["started_at"],
        "completed_at": run.get("completed_at"),
    }
