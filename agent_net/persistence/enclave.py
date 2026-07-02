"""Enclave, vault, playbook, and stage persistence."""
from __future__ import annotations

import json
import secrets
import time
import uuid
from typing import Optional

import aiosqlite

from .context import connect, get_db_path


# ── Enclave CRUD ─────────────────────────────────────────────────────

async def create_enclave(
    enclave_id: str,
    name: str,
    owner_did: str,
    vault_backend: str = "local",
    vault_config: dict = None,
) -> str:
    """创建 Enclave"""
    now = time.time()
    async with connect() as db:
        await db.execute(
            """INSERT INTO enclaves
               (enclave_id, name, owner_did, vault_backend, vault_config, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (enclave_id, name, owner_did, vault_backend, json.dumps(vault_config or {}), now, now)
        )
        await db.commit()
    return enclave_id


async def get_enclave(enclave_id: str) -> Optional[dict]:
    """获取 Enclave 详情"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM enclaves WHERE enclave_id = ?", (enclave_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "enclave_id": row["enclave_id"],
        "name": row["name"],
        "owner_did": row["owner_did"],
        "status": row["status"],
        "vault_backend": row["vault_backend"],
        "vault_config": json.loads(row["vault_config"] or "{}"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def list_enclaves(did: str = None, status: str = None) -> list[dict]:
    """列出 Enclave，可按成员 DID 或状态过滤"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        if did:
            # 按成员 DID 查询
            query = """
                SELECT e.* FROM enclaves e
                JOIN enclave_members em ON e.enclave_id = em.enclave_id
                WHERE em.did = ?
            """
            params = [did]
            if status:
                query += " AND e.status = ?"
                params.append(status)
        else:
            query = "SELECT * FROM enclaves"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status)
        query += " ORDER BY created_at DESC"

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    return [{
        "enclave_id": r["enclave_id"],
        "name": r["name"],
        "owner_did": r["owner_did"],
        "status": r["status"],
        "vault_backend": r["vault_backend"],
        "vault_config": json.loads(r["vault_config"] or "{}"),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    } for r in rows]


async def update_enclave(enclave_id: str, **kwargs) -> bool:
    """更新 Enclave 属性"""
    allowed = {"name", "status", "vault_backend", "vault_config"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    updates["updated_at"] = time.time()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [enclave_id]

    async with connect() as db:
        result = await db.execute(
            f"UPDATE enclaves SET {set_clause} WHERE enclave_id = ?", values
        )
        await db.commit()
        return result.rowcount > 0


async def delete_enclave(enclave_id: str) -> bool:
    """归档 Enclave（软删除）"""
    return await update_enclave(enclave_id, status="archived")


# ── Enclave Members CRUD ────────────────────────────────────────────

async def add_enclave_member(
    enclave_id: str,
    did: str,
    role: str,
    permissions: str = "rw",
    handbook: str = "",
) -> bool:
    """添加成员"""
    now = time.time()
    async with connect() as db:
        try:
            await db.execute(
                """INSERT INTO enclave_members
                   (enclave_id, did, role, permissions, handbook, joined_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (enclave_id, did, role, permissions, handbook, now)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False  # 已存在


async def get_enclave_member(enclave_id: str, did: str) -> Optional[dict]:
    """获取单个成员"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM enclave_members WHERE enclave_id = ? AND did = ?",
            (enclave_id, did)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "enclave_id": row["enclave_id"],
        "did": row["did"],
        "role": row["role"],
        "permissions": row["permissions"],
        "handbook": row["handbook"] or "",
        "joined_at": row["joined_at"],
    }


async def list_enclave_members(enclave_id: str) -> list[dict]:
    """列出 Enclave 所有成员"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM enclave_members WHERE enclave_id = ? ORDER BY joined_at",
            (enclave_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    return [{
        "enclave_id": r["enclave_id"],
        "did": r["did"],
        "role": r["role"],
        "permissions": r["permissions"],
        "handbook": r["handbook"] or "",
        "joined_at": r["joined_at"],
    } for r in rows]


async def update_enclave_member(enclave_id: str, did: str, **kwargs) -> bool:
    """更新成员属性"""
    allowed = {"role", "permissions", "handbook"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [enclave_id, did]

    async with connect() as db:
        result = await db.execute(
            f"UPDATE enclave_members SET {set_clause} WHERE enclave_id = ? AND did = ?",
            values
        )
        await db.commit()
        return result.rowcount > 0


async def remove_enclave_member(enclave_id: str, did: str) -> bool:
    """移除成员"""
    async with connect() as db:
        result = await db.execute(
            "DELETE FROM enclave_members WHERE enclave_id = ? AND did = ?",
            (enclave_id, did)
        )
        await db.commit()
        return result.rowcount > 0


# ── Vault Operations ──────────────────────────────────────────────────

async def vault_get(enclave_id: str, key: str, version: int = None) -> Optional[dict]:
    """读取 Vault 文档"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        if version:
            async with db.execute(
                """SELECT * FROM enclave_vault_history
                   WHERE enclave_id = ? AND key = ? AND version = ?""",
                (enclave_id, key, version)
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute(
                "SELECT * FROM enclave_vault WHERE enclave_id = ? AND key = ?",
                (enclave_id, key)
            ) as cursor:
                row = await cursor.fetchone()

    if not row:
        return None
    return {
        "key": row["key"],
        "value": row["value"],
        "version": row["version"],
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
        "message": row["message"] or "",
    }


async def vault_put(
    enclave_id: str,
    key: str,
    value: str,
    author_did: str,
    message: str = "",
) -> dict:
    """写入 Vault 文档"""
    now = time.time()
    async with connect() as db:
        # 检查是否已存在
        async with db.execute(
            "SELECT version FROM enclave_vault WHERE enclave_id = ? AND key = ?",
            (enclave_id, key)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            new_version = row[0] + 1
            action = "update"
            await db.execute(
                """UPDATE enclave_vault
                   SET value = ?, version = ?, updated_by = ?, updated_at = ?, message = ?
                   WHERE enclave_id = ? AND key = ?""",
                (value, new_version, author_did, now, message, enclave_id, key)
            )
        else:
            new_version = 1
            action = "create"
            await db.execute(
                """INSERT INTO enclave_vault
                   (enclave_id, key, value, version, updated_by, updated_at, message)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (enclave_id, key, value, new_version, author_did, now, message)
            )

        # 写入历史
        await db.execute(
            """INSERT INTO enclave_vault_history
               (enclave_id, key, value, version, updated_by, updated_at, message, action)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (enclave_id, key, value, new_version, author_did, now, message, action)
        )

        await db.commit()

    return {
        "key": key,
        "version": new_version,
        "updated_by": author_did,
        "updated_at": now,
        "action": action,
    }


async def vault_list(enclave_id: str, prefix: str = "") -> list[dict]:
    """列出 Vault 文档"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        if prefix:
            async with db.execute(
                """SELECT key, version, updated_by, updated_at, message
                   FROM enclave_vault
                   WHERE enclave_id = ? AND key LIKE ?
                   ORDER BY key""",
                (enclave_id, f"{prefix}%")
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """SELECT key, version, updated_by, updated_at, message
                   FROM enclave_vault WHERE enclave_id = ? ORDER BY key""",
                (enclave_id,)
            ) as cursor:
                rows = await cursor.fetchall()

    return [{
        "key": r["key"],
        "version": r["version"],
        "updated_by": r["updated_by"],
        "updated_at": r["updated_at"],
        "message": r["message"] or "",
    } for r in rows]


async def vault_history(enclave_id: str, key: str, limit: int = 10) -> list[dict]:
    """查看文档历史"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT version, updated_by, updated_at, message, action
               FROM enclave_vault_history
               WHERE enclave_id = ? AND key = ?
               ORDER BY version DESC LIMIT ?""",
            (enclave_id, key, limit)
        ) as cursor:
            rows = await cursor.fetchall()

    return [{
        "key": key,
        "version": r["version"],
        "updated_by": r["updated_by"],
        "updated_at": r["updated_at"],
        "message": r["message"] or "",
        "action": r["action"] or "update",
    } for r in rows]


async def vault_delete(enclave_id: str, key: str, author_did: str) -> bool:
    """删除 Vault 文档"""
    now = time.time()
    async with connect() as db:
        # 检查是否存在
        async with db.execute(
            "SELECT version FROM enclave_vault WHERE enclave_id = ? AND key = ?",
            (enclave_id, key)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return False

        # 写入历史（标记删除）
        await db.execute(
            """INSERT INTO enclave_vault_history
               (enclave_id, key, value, version, updated_by, updated_at, message, action)
               VALUES (?, ?, '', ?, ?, ?, '', 'delete')""",
            (enclave_id, key, row[0] + 1, author_did, now)
        )

        # 删除
        await db.execute(
            "DELETE FROM enclave_vault WHERE enclave_id = ? AND key = ?",
            (enclave_id, key)
        )
        await db.commit()
        return True


# ── Playbook Operations ──────────────────────────────────────────────

async def create_playbook(
    playbook_id: str,
    name: str,
    stages: list[dict],
    description: str = "",
    created_by: str = "",
    version: str = "1",
    fingerprint: str = "",
) -> str:
    """创建 Playbook"""
    now = time.time()
    async with connect() as db:
        await db.execute(
            """INSERT INTO playbooks
               (playbook_id, name, version, fingerprint, stages, description, created_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (playbook_id, name, version, fingerprint, json.dumps(stages), description, created_by, now)
        )
        await db.commit()
    return playbook_id


async def get_playbook(playbook_id: str) -> Optional[dict]:
    """获取 Playbook"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM playbooks WHERE playbook_id = ?", (playbook_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "playbook_id": row["playbook_id"],
        "name": row["name"],
        "version": row["version"] or "1",
        "fingerprint": row["fingerprint"] or "",
        "stages": json.loads(row["stages"]),
        "description": row["description"] or "",
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


async def create_playbook_run(
    run_id: str,
    enclave_id: str,
    playbook_id: str,
    playbook_name: str = "",
    coordination_session_id: str | None = None,
) -> str:
    """创建 Playbook 执行实例"""
    now = time.time()
    async with connect() as db:
        await db.execute(
            """INSERT INTO playbook_runs
               (run_id, coordination_session_id, enclave_id, playbook_id, playbook_name, started_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, coordination_session_id, enclave_id, playbook_id, playbook_name, now)
        )
        await db.commit()
    return run_id


async def get_playbook_run(run_id: str) -> Optional[dict]:
    """获取 Playbook 执行实例"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM playbook_runs WHERE run_id = ?", (run_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "coordination_session_id": row["coordination_session_id"],
        "enclave_id": row["enclave_id"],
        "playbook_id": row["playbook_id"],
        "playbook_name": row["playbook_name"],
        "current_stage": row["current_stage"] or "",
        "status": row["status"],
        "context": json.loads(row["context"] or "{}"),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


async def get_latest_playbook_run(enclave_id: str) -> Optional[dict]:
    """获取 Enclave 最新的 Playbook 执行实例"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM playbook_runs
               WHERE enclave_id = ?
               ORDER BY started_at DESC
               LIMIT 1""",
            (enclave_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "coordination_session_id": row["coordination_session_id"],
        "enclave_id": row["enclave_id"],
        "playbook_id": row["playbook_id"],
        "playbook_name": row["playbook_name"],
        "current_stage": row["current_stage"] or "",
        "status": row["status"],
        "context": json.loads(row["context"] or "{}"),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


async def list_playbook_runs_for_coordination_session(coordination_session_id: str) -> list[dict]:
    """List PlaybookRun instances attached to a CoordinationSession."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM playbook_runs
               WHERE coordination_session_id = ?
               ORDER BY started_at ASC""",
            (coordination_session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [{
        "run_id": row["run_id"],
        "coordination_session_id": row["coordination_session_id"],
        "enclave_id": row["enclave_id"],
        "playbook_id": row["playbook_id"],
        "playbook_name": row["playbook_name"],
        "current_stage": row["current_stage"] or "",
        "status": row["status"],
        "context": json.loads(row["context"] or "{}"),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    } for row in rows]


async def update_playbook_run(run_id: str, **kwargs) -> bool:
    """更新 Playbook 执行实例"""
    allowed = {"current_stage", "status", "context", "completed_at", "coordination_session_id"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    # 处理 context 的 JSON 序列化
    if "context" in updates:
        updates["context"] = json.dumps(updates["context"])

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [run_id]

    async with connect() as db:
        result = await db.execute(
            f"UPDATE playbook_runs SET {set_clause} WHERE run_id = ?", values
        )
        await db.commit()
        return result.rowcount > 0


async def create_stage_execution(
    run_id: str,
    stage_name: str,
    assigned_did: str = "",
    task_id: str = "",
) -> bool:
    """Create or reassign a stage execution record."""
    now = time.time()
    async with connect() as db:
        try:
            await db.execute(
                """INSERT INTO stage_executions
                   (run_id, stage_name, assigned_did, status, task_id, started_at)
                   VALUES (?, ?, ?, 'active', ?, ?)""",
                (run_id, stage_name, assigned_did, task_id, now)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            await db.execute(
                """UPDATE stage_executions
                   SET assigned_did = ?, status = 'active', task_id = ?,
                       output_ref = '', retry_count = COALESCE(retry_count, 0) + 1,
                       started_at = ?, completed_at = NULL
                   WHERE run_id = ? AND stage_name = ?""",
                (assigned_did, task_id, now, run_id, stage_name)
            )
            await db.commit()
            return True


async def get_stage_execution(run_id: str, stage_name: str) -> Optional[dict]:
    """获取阶段执行记录"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM stage_executions WHERE run_id = ? AND stage_name = ?",
            (run_id, stage_name)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "stage_name": row["stage_name"],
        "assigned_did": row["assigned_did"] or "",
        "status": row["status"],
        "task_id": row["task_id"] or "",
        "output_ref": row["output_ref"] or "",
        "retry_count": row["retry_count"] or 0,
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


async def get_stage_execution_by_task(task_id: str) -> Optional[dict]:
    """通过 task_id 获取阶段执行记录"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM stage_executions WHERE task_id = ?",
            (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "stage_name": row["stage_name"],
        "assigned_did": row["assigned_did"] or "",
        "status": row["status"],
        "task_id": row["task_id"] or "",
        "output_ref": row["output_ref"] or "",
        "retry_count": row["retry_count"] or 0,
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


async def get_stage_executions_for_run(run_id: str) -> list[dict]:
    """获取 Run 下所有阶段执行记录"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM stage_executions WHERE run_id = ? ORDER BY started_at",
            (run_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [{
        "run_id": row["run_id"],
        "stage_name": row["stage_name"],
        "assigned_did": row["assigned_did"] or "",
        "status": row["status"],
        "task_id": row["task_id"] or "",
        "output_ref": row["output_ref"] or "",
        "retry_count": row["retry_count"] or 0,
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    } for row in rows]


async def update_stage_execution(run_id: str, stage_name: str, **kwargs) -> bool:
    """更新阶段执行记录"""
    allowed = {
        "status", "output_ref", "completed_at", "assigned_did",
        "task_id", "started_at", "retry_count",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [run_id, stage_name]

    async with connect() as db:
        result = await db.execute(
            f"UPDATE stage_executions SET {set_clause} WHERE run_id = ? AND stage_name = ?",
            values
        )
        await db.commit()
        return result.rowcount > 0


async def list_stage_executions(run_id: str) -> list[dict]:
    """列出 Playbook Run 的所有阶段"""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM stage_executions WHERE run_id = ? ORDER BY started_at",
            (run_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [{
        "run_id": row["run_id"],
        "stage_name": row["stage_name"],
        "assigned_did": row["assigned_did"] or "",
        "status": row["status"],
        "task_id": row["task_id"] or "",
        "output_ref": row["output_ref"] or "",
        "retry_count": row["retry_count"] or 0,
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    } for row in rows]
