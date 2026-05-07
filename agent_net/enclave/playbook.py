"""
Playbook 引擎

ADR-013 §4 定义的流程编排引擎。

职责：
1. 根据阶段定义，向对应角色的 Agent 发送 task_propose
2. 监听 notify_state(completed/rejected)，推进到下一阶段
3. 处理超时、回退、跳过
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

from agent_net.storage import (
    get_enclave,
    list_enclave_members,
    get_playbook,
    get_playbook_run,
    update_playbook_run,
    get_stage_execution,
    create_stage_execution,
    update_stage_execution,
    list_stage_executions,
    vault_get,
)
from agent_net.enclave.models import Stage, Playbook


def _artifact_ref(enclave_id: str, key: str) -> dict:
    """Canonical Vault artifact reference used in delivery manifests."""
    return {"enclave_id": enclave_id, "key": key}


def _serialize_ref(ref) -> str:
    """Store artifact references safely in TEXT columns."""
    if ref is None:
        return ""
    if isinstance(ref, (dict, list)):
        return json.dumps(ref, separators=(",", ":"), ensure_ascii=False)
    return str(ref)


def _deserialize_ref(ref: str):
    if not ref:
        return ""
    try:
        return json.loads(ref)
    except (TypeError, json.JSONDecodeError):
        return ref


class PlaybookEngine:
    """
    Playbook 执行引擎。

    用法：
        engine = PlaybookEngine(daemon_url, token)
        run_id = await engine.start(enclave_id, playbook_id)
        await engine.on_stage_completed(run_id, stage_name)
    """

    def __init__(self, daemon_url: str = "http://localhost:8765", token: str = ""):
        self.daemon_url = daemon_url
        self.token = token
        self.max_retries = 2

    async def _send_task_propose(
        self,
        from_did: str,
        to_did: str,
        role: str,
        title: str,
        task_id: str,
        enclave_id: str,
        run_id: str,
        stage_name: str,
        input_keys: list[str],
        output_key: str,
        context_snapshot: dict | None = None,
        session_id: str = "",
    ) -> None:
        """D-SEC-09: 发送 task_propose，继承 session_id 确保消息链路完整。"""
        import aiohttp

        content = {
            "task_id": task_id,
            "title": title,
            "enclave_id": enclave_id,
            "run_id": run_id,
            "stage_name": stage_name,
            "role": role,
            "input_keys": input_keys,
            "output_key": output_key,
            "context_snapshot": context_snapshot or {},
            "message_type": "task_propose",
            "protocol": "nexus_v1",
            "schema_version": "1",
        }

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        body = {
            "from_did": from_did,
            "to_did": to_did,
            "content": content,
            "message_type": "task_propose",
        }
        if session_id:
            body["session_id"] = session_id

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.daemon_url}/messages/send",
                json=body,
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Failed to send task_propose: {text}")

    async def start(
        self,
        enclave_id: str,
        playbook_id: str,
        run_id: str,
    ) -> str:
        """
        启动 Playbook 执行。

        Args:
            enclave_id: Enclave ID
            playbook_id: Playbook ID
            run_id: Run ID（已创建的 playbook_runs 记录）

        Returns:
            run_id
        """
        # 获取 Playbook 定义
        playbook_data = await get_playbook(playbook_id)
        if not playbook_data:
            raise ValueError(f"Playbook not found: {playbook_id}")

        stages = [Stage.from_dict(s) for s in playbook_data["stages"]]
        if not stages:
            raise ValueError("Playbook has no stages")

        # 找到第一个阶段
        first_stage = stages[0]
        await self._start_stage(enclave_id, run_id, first_stage)

        # 更新 run 的 current_stage
        await update_playbook_run(run_id, current_stage=first_stage.name)

        return run_id

    async def _start_stage(
        self,
        enclave_id: str,
        run_id: str,
        stage: Stage,
    ) -> None:
        """启动一个阶段"""
        # 查找该角色的成员
        members = await list_enclave_members(enclave_id)
        assigned_member = None
        for m in members:
            if m["role"] == stage.role:
                assigned_member = m
                break

        if not assigned_member:
            # 找不到对应角色的成员
            await update_stage_execution(
                run_id, stage.name,
                status="blocked",
            )
            return

        assigned_did = assigned_member["did"]

        # 生成 task_id
        task_id = f"task_{int(time.time() * 1000)}"

        # 创建阶段执行记录
        await create_stage_execution(
            run_id=run_id,
            stage_name=stage.name,
            assigned_did=assigned_did,
            task_id=task_id,
        )

        # 发送任务提案
        enclave = await get_enclave(enclave_id)
        from_did = enclave["owner_did"] if enclave else assigned_did

        # Phase B D-SEC-10: 构建 Context Snapshot（含 Handoff Checkpoint）
        run = await get_playbook_run(run_id)
        run_ctx = run.get("context", {}) or {} if run else {}
        session_id = run_ctx.get("session_id", "")
        context_snapshot = await self._build_context_snapshot(
            run_id=run_id,
            enclave_id=enclave_id,
            run=run or {},
            stage=stage,
            session_id=session_id,
        )

        await self._send_task_propose(
            from_did=from_did,
            to_did=assigned_did,
            role=stage.role,
            title=stage.description or stage.name,
            task_id=task_id,
            enclave_id=enclave_id,
            run_id=run_id,
            stage_name=stage.name,
            input_keys=stage.input_keys or [],
            output_key=stage.output_key or "",
            context_snapshot=context_snapshot,
            session_id=session_id,
        )

    async def _build_context_snapshot(
        self,
        run_id: str,
        enclave_id: str,
        run: dict,
        stage: Stage,
        session_id: str = "",
    ) -> dict:
        """
        Phase B D-SEC-10: 构建阶段交接的 Context Snapshot。
        必填字段：thread_id, session_id, objective, current_stage, assigned_role, inputs, handoff_summary, updated_at
        """
        # 获取前序已完成阶段的 checkpoint（支持 dict 和 list 两种结构）
        run_context = run.get("context", {}) or {}
        latest_checkpoint = self._latest_checkpoint(run_context)

        # 构建 input artifact refs
        input_refs = [_artifact_ref(enclave_id, key) for key in (stage.input_keys or [])]

        # 构建输出目标 ref
        output_ref = _artifact_ref(enclave_id, stage.output_key) if stage.output_key else None

        snapshot = {
            "thread_id": run_id,
            "session_id": session_id,
            "objective": run_context.get("objective", run.get("playbook_name", "")),
            "current_stage": stage.name,
            "assigned_role": stage.role,
            "inputs": input_refs,
            "output": output_ref,
            "handoff_summary": latest_checkpoint.get("summary", "") if latest_checkpoint else "",
            "updated_at": time.time(),
        }

        # 如果有前序 checkpoint，注入 decisions / open_questions / next_stage_hints
        if latest_checkpoint:
            snapshot["decisions"] = latest_checkpoint.get("decisions", [])
            snapshot["open_questions"] = latest_checkpoint.get("open_questions", [])
            snapshot["next_stage_hints"] = latest_checkpoint.get("next_stage_hints", "")

        # Context Policy: 如果配置了 max_context_tokens，记录到 snapshot
        if stage.max_context_tokens:
            snapshot["max_context_tokens"] = stage.max_context_tokens
        if stage.context_policy:
            snapshot["context_policy"] = stage.context_policy

        # D-SEC-10: Context Budget 估算（Phase B 用字符近似：1 token ≈ 4 字符英文 / 2 字符中文）
        budget = run_context.get("context_budget", {}) or {}
        planned = self._estimate_snapshot_tokens(snapshot)
        budget["estimated_context_tokens_planned"] = planned

        snapshot["context_budget"] = {
            "estimated_context_tokens_planned": planned,
            "max_context_tokens": stage.max_context_tokens or 0,
        }
        if stage.context_policy:
            snapshot["context_budget"]["artifact_mode"] = stage.context_policy.get("artifact_mode", "summary_plus_ref")

        # 记录到 run context 供后续追踪
        run_context["context_budget"] = budget
        await update_playbook_run(run_id, context=run_context)

        return snapshot

    def _estimate_snapshot_tokens(self, snapshot: dict) -> int:
        """
        Phase B D-SEC-10: 估算 Context Snapshot 的 token 数。
        字符近似：1 token ≈ 4 字符英文 / 2 字符中文（取中间值 ≈ 3 字符/token）。
        """
        import json
        snapshot_json = json.dumps(snapshot, ensure_ascii=False)
        char_count = len(snapshot_json)
        # 粗略估算：3 字符 ≈ 1 token
        return max(1, char_count // 3)

    def _latest_checkpoint(self, run_context: dict) -> dict | None:
        """
        获取最近一个 Handoff Checkpoint。
        存储结构：checkpoints[stage_name] = checkpoint（设计文档规范）
        向后兼容：旧数据可能为 list 结构。
        """
        checkpoints = run_context.get("checkpoints")
        if not checkpoints:
            return None
        if isinstance(checkpoints, dict):
            # 按 stage 顺序，取最后一个有值的
            latest = None
            for ckpt in checkpoints.values():
                if ckpt and isinstance(ckpt, dict):
                    latest = ckpt
            return latest
        if isinstance(checkpoints, list) and checkpoints:
            return checkpoints[-1]
        return None

    async def _generate_handoff_checkpoint(
        self,
        run_id: str,
        stage_name: str,
        stage: Stage,
        output_ref: str | dict,
        assigned_did: str,
        status: str = "completed",
        summary: str = "",
    ) -> dict:
        """
        Phase B D-SEC-10: 生成 Handoff Checkpoint，写入 playbook_runs.context。
        """
        if not summary:
            summary = f"Stage {stage_name} {status}"
        checkpoint = {
            "run_id": run_id,
            "stage_name": stage_name,
            "status": status,
            "summary": summary,
            "artifacts": [
                {"kind": stage_name, "ref": output_ref, "produced_by": assigned_did}
            ] if output_ref else [],
            "decisions": [],
            "open_questions": [],
            "next_stage_hints": f"Proceed to {stage.next}" if stage.next else "",
            "created_at": time.time(),
        }

        # 写入 run context 的 checkpoints dict（设计文档: checkpoints[stage_name]）
        from agent_net.storage import get_playbook_run, update_playbook_run
        run = await get_playbook_run(run_id)
        if run:
            run_ctx = run.get("context", {}) or {}
            checkpoints = run_ctx.get("checkpoints")
            if isinstance(checkpoints, list):
                # 迁移旧 list 结构 → dict
                checkpoints = {
                    ckpt.get("stage_name", f"migrated_{i}"): ckpt
                    for i, ckpt in enumerate(checkpoints) if isinstance(ckpt, dict)
                }
            if not isinstance(checkpoints, dict):
                checkpoints = {}
            checkpoints[stage_name] = checkpoint

            # D-SEC-10: 记录 Context Budget 实际用量
            budget = run_ctx.get("context_budget", {}) or {}
            budget["estimated_context_tokens_actual"] = self._estimate_snapshot_tokens(checkpoint)
            run_ctx["context_budget"] = budget

            run_ctx["checkpoints"] = checkpoints
            await update_playbook_run(run_id, context=run_ctx)

        return checkpoint

    async def on_stage_completed(
        self,
        run_id: str,
        stage_name: str,
        output_ref: str | dict = "",
    ) -> None:
        """
        阶段完成回调。

        更新阶段状态，推进到下一阶段。
        """
        # 获取 run 和 playbook 信息
        run = await get_playbook_run(run_id)
        if not run:
            return

        playbook_data = await get_playbook(run["playbook_id"])
        if not playbook_data:
            return

        stages = [Stage.from_dict(s) for s in playbook_data["stages"]]

        # 找到当前阶段
        current_stage = None
        for s in stages:
            if s.name == stage_name:
                current_stage = s
                break

        if not current_stage:
            return

        # 更新阶段执行状态
        await update_stage_execution(
            run_id, stage_name,
            status="completed",
            output_ref=_serialize_ref(output_ref),
        )

        # D-SEC-05: 生成 Stage Delivery Manifest，并将 output_ref 更新为 Vault key
        vault_key = f"manifests/{run_id}/{stage_name}"
        manifest_ref = _artifact_ref(run["enclave_id"], vault_key)
        stage_exec = await get_stage_execution(run_id, stage_name)
        if stage_exec:
            from agent_net.storage import store_stage_manifest
            artifacts = []
            if output_ref:
                artifacts.append({
                    "kind": stage_name,
                    "ref": output_ref,
                    "produced_by": stage_exec.get("assigned_did", ""),
                    "summary": f"Stage {stage_name} completed",
                })
            required_outputs = [stage_name]
            manifest = await store_stage_manifest(
                run_id=run_id,
                stage_name=stage_name,
                status="completed",
                artifacts=artifacts,
                required_outputs=required_outputs,
                produced_by=stage_exec.get("assigned_did", ""),
            )
            # 将 output_ref 更新为 Vault key（可解析的 Artifact Ref）
            await update_stage_execution(
                run_id, stage_name,
                output_ref=_serialize_ref(manifest_ref),
            )

        # 推进到下一阶段
        if current_stage.next:
            # 找到下一阶段
            next_stage = None
            for s in stages:
                if s.name == current_stage.next:
                    next_stage = s
                    break

            if next_stage:
                # D-SEC-10: 生成 Handoff Checkpoint，供下一阶段消费
                await self._generate_handoff_checkpoint(
                    run_id=run_id,
                    stage_name=stage_name,
                    stage=current_stage,
                    output_ref=manifest_ref,
                    assigned_did=stage_exec.get("assigned_did", "") if stage_exec else "",
                )
                await self._start_stage(run["enclave_id"], run_id, next_stage)
                await update_playbook_run(run_id, current_stage=next_stage.name)
            else:
                # 下一阶段不存在，标记完成
                await self._mark_playbook_completed(run_id, run)
        else:
            # D-SEC-10: Final stage completion checkpoint
            await self._generate_handoff_checkpoint(
                run_id=run_id,
                stage_name=stage_name,
                stage=current_stage,
                output_ref=manifest_ref,
                assigned_did=stage_exec.get("assigned_did", "") if stage_exec else "",
            )
            # 没有下一阶段，Playbook 完成
            await self._mark_playbook_completed(run_id, run)

    async def _mark_playbook_completed(self, run_id: str, run: dict) -> None:
        """
        Playbook 完成回调，生成 Final Delivery Manifest（D-SEC-05）。
        """
        await update_playbook_run(run_id, status="completed", completed_at=time.time())

        # D-SEC-05: 生成 Final Delivery Manifest
        from agent_net.storage import store_final_manifest, get_stage_executions_for_run
        executions = await get_stage_executions_for_run(run_id)
        stage_manifest_ids = [f"manifest_{e['stage_name']}_{run_id}" for e in executions if e["status"] == "completed"]
        final_artifacts = []
        for e in executions:
            if e["status"] != "completed" or not e.get("output_ref"):
                continue

            manifest_ref = _deserialize_ref(e["output_ref"])
            if isinstance(manifest_ref, dict) and manifest_ref.get("key"):
                entry = await vault_get(
                    manifest_ref.get("enclave_id", run["enclave_id"]),
                    manifest_ref["key"],
                )
                if entry:
                    try:
                        stage_manifest = json.loads(entry["value"])
                        final_artifacts.extend(stage_manifest.get("artifacts", []))
                        continue
                    except (TypeError, json.JSONDecodeError):
                        pass

            final_artifacts.append({
                "kind": e["stage_name"],
                "ref": manifest_ref,
                "produced_by": e.get("assigned_did", ""),
            })

        await store_final_manifest(
            run_id=run_id,
            status="completed",
            summary=f"Playbook run {run_id} completed",
            stage_manifest_ids=stage_manifest_ids,
            final_artifacts=final_artifacts,
            produced_by=run.get("owner_did", ""),
        )

    async def on_stage_rejected(
        self,
        run_id: str,
        stage_name: str,
        reason: str = "",
    ) -> None:
        """
        阶段被拒绝回调。

        回退到 on_reject 阶段。
        """
        # 更新阶段执行状态
        await update_stage_execution(
            run_id, stage_name,
            status="rejected",
            output_ref=reason,
        )

        # 获取 run 和 playbook 信息
        run = await get_playbook_run(run_id)
        if not run:
            return

        playbook_data = await get_playbook(run["playbook_id"])
        if not playbook_data:
            return

        stages = [Stage.from_dict(s) for s in playbook_data["stages"]]

        # 找到当前阶段
        current_stage = None
        for s in stages:
            if s.name == stage_name:
                current_stage = s
                break

        if not current_stage:
            return

        # D-SEC-10: 记录拒绝 Checkpoint，包含拒绝原因
        await self._generate_handoff_checkpoint(
            run_id=run_id,
            stage_name=stage_name,
            stage=current_stage,
            output_ref="",
            assigned_did="",
            status="rejected",
            summary=f"Stage {stage_name} rejected: {reason}" if reason else f"Stage {stage_name} rejected",
        )

        # 回退到 on_reject 阶段
        if current_stage.on_reject:
            reject_stage = None
            for s in stages:
                if s.name == current_stage.on_reject:
                    reject_stage = s
                    break

            if reject_stage:
                existing = await get_stage_execution(run_id, reject_stage.name)
                retry_count = existing.get("retry_count", 0) if existing else 0
                if retry_count >= self.max_retries:
                    await update_playbook_run(
                        run_id,
                        status="failed",
                        completed_at=time.time(),
                    )
                    return
                await self._start_stage(run["enclave_id"], run_id, reject_stage)
                await update_playbook_run(run_id, current_stage=reject_stage.name)
            else:
                # 回退阶段不存在，标记失败
                await update_playbook_run(
                    run_id,
                    status="failed",
                    completed_at=time.time(),
                )
        else:
            # 没有回退目标，标记失败
            await update_playbook_run(
                run_id,
                status="failed",
                completed_at=time.time(),
            )

    async def get_status(self, run_id: str) -> dict:
        """查询 Playbook 执行状态"""
        run = await get_playbook_run(run_id)
        if not run:
            return {"error": "Run not found"}

        # 获取阶段执行记录
        stage_executions = await list_stage_executions(run_id)

        # 获取 Playbook 定义
        playbook_data = await get_playbook(run["playbook_id"])

        # 构建阶段状态映射
        stages_status = {}
        if playbook_data:
            for stage in playbook_data["stages"]:
                stage_name = stage["name"]
                exec_record = next(
                    (e for e in stage_executions if e["stage_name"] == stage_name),
                    None
                )
                stages_status[stage_name] = {
                    "status": exec_record["status"] if exec_record else "pending",
                    "assigned_did": exec_record["assigned_did"] if exec_record else "",
                    "task_id": exec_record["task_id"] if exec_record else "",
                    "output_ref": exec_record["output_ref"] if exec_record else "",
                    "retry_count": exec_record["retry_count"] if exec_record else 0,
                }

        return {
            "run_id": run["run_id"],
            "playbook_name": run["playbook_name"],
            "current_stage": run["current_stage"],
            "run_status": run["status"],
            "stages": stages_status,
            "started_at": run["started_at"],
            "completed_at": run.get("completed_at"),
        }


# 全局实例
_playbook_engine: Optional[PlaybookEngine] = None


def get_playbook_engine() -> PlaybookEngine:
    """获取全局 PlaybookEngine 实例"""
    global _playbook_engine
    if _playbook_engine is None:
        _playbook_engine = PlaybookEngine()
    return _playbook_engine


def init_playbook_engine(daemon_url: str, token: str) -> PlaybookEngine:
    """初始化全局 PlaybookEngine 实例"""
    global _playbook_engine
    _playbook_engine = PlaybookEngine(daemon_url, token)
    return _playbook_engine
