"""
Enclave 数据模型

ADR-013 §2 定义的表结构和数据类。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ─────────────────────────────────────────────────────────────────
# 数据类
# ─────────────────────────────────────────────────────────────────

@dataclass
class Member:
    """Enclave 成员"""
    enclave_id: str
    did: str
    role: str                           # 角色名（如 architect / developer）
    permissions: str = "rw"             # r / rw / admin
    handbook: str = ""                  # 角色职责说明
    joined_at: float = 0.0

    def __post_init__(self):
        if self.joined_at == 0.0:
            self.joined_at = _now()

    def to_dict(self) -> dict:
        return {
            "enclave_id": self.enclave_id,
            "did": self.did,
            "role": self.role,
            "permissions": self.permissions,
            "handbook": self.handbook,
            "joined_at": self.joined_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Member":
        return cls(
            enclave_id=d["enclave_id"],
            did=d["did"],
            role=d["role"],
            permissions=d.get("permissions", "rw"),
            handbook=d.get("handbook", ""),
            joined_at=d.get("joined_at", 0.0),
        )


@dataclass
class Enclave:
    """Enclave 项目组"""
    enclave_id: str
    name: str
    owner_did: str
    status: str = "active"              # active / paused / archived
    vault_backend: str = "local"         # local / git / notion / s3
    vault_config: dict = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    members: list[Member] = field(default_factory=list)

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = _now()
        if self.updated_at == 0.0:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "enclave_id": self.enclave_id,
            "name": self.name,
            "owner_did": self.owner_did,
            "status": self.status,
            "vault_backend": self.vault_backend,
            "vault_config": self.vault_config,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "members": [m.to_dict() for m in self.members],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Enclave":
        return cls(
            enclave_id=d["enclave_id"],
            name=d["name"],
            owner_did=d["owner_did"],
            status=d.get("status", "active"),
            vault_backend=d.get("vault_backend", "local"),
            vault_config=d.get("vault_config", {}),
            created_at=d.get("created_at", 0.0),
            updated_at=d.get("updated_at", 0.0),
            members=[Member.from_dict(m) for m in d.get("members", [])],
        )

    @staticmethod
    def gen_id() -> str:
        return _gen_id("enc")


# ─────────────────────────────────────────────────────────────────
# Playbook 数据类
# ─────────────────────────────────────────────────────────────────

@dataclass
class Stage:
    """Playbook 阶段定义"""
    name: str                           # 阶段名（唯一）
    role: str                           # 执行角色
    description: str = ""                # 任务描述
    input_keys: list[str] = field(default_factory=list)   # 依赖的 Vault key
    output_key: str = ""                # 本阶段产出物的 Vault key
    next: str = ""                      # 成功后的下一阶段
    on_reject: str = ""                 # 被拒绝后回退到的阶段
    timeout_seconds: int = 0            # 超时时间（0=不限）

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "input_keys": self.input_keys,
            "output_key": self.output_key,
            "next": self.next,
            "on_reject": self.on_reject,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Stage":
        return cls(
            name=d["name"],
            role=d["role"],
            description=d.get("description", ""),
            input_keys=d.get("input_keys", []),
            output_key=d.get("output_key", ""),
            next=d.get("next", ""),
            on_reject=d.get("on_reject", ""),
            timeout_seconds=d.get("timeout_seconds", 0),
        )


@dataclass
class Playbook:
    """Playbook 定义（可复用）"""
    playbook_id: str
    name: str
    stages: list[Stage]
    description: str = ""
    created_by: str = ""
    created_at: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = _now()

    def to_dict(self) -> dict:
        return {
            "playbook_id": self.playbook_id,
            "name": self.name,
            "stages": [s.to_dict() for s in self.stages],
            "description": self.description,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Playbook":
        return cls(
            playbook_id=d["playbook_id"],
            name=d["name"],
            stages=[Stage.from_dict(s) for s in d.get("stages", [])],
            description=d.get("description", ""),
            created_by=d.get("created_by", ""),
            created_at=d.get("created_at", 0.0),
        )

    @staticmethod
    def gen_id() -> str:
        return _gen_id("pb")


@dataclass
class PlaybookRun:
    """Playbook 执行实例"""
    run_id: str
    enclave_id: str
    playbook_id: str
    playbook_name: str = ""             # 冗余存储，便于查询
    current_stage: str = ""              # 当前阶段名
    status: str = "running"              # running / paused / completed / failed
    context: dict = field(default_factory=dict)  # 运行时上下文
    started_at: float = 0.0
    completed_at: float = 0.0

    def __post_init__(self):
        if self.started_at == 0.0:
            self.started_at = _now()

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "enclave_id": self.enclave_id,
            "playbook_id": self.playbook_id,
            "playbook_name": self.playbook_name,
            "current_stage": self.current_stage,
            "status": self.status,
            "context": self.context,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlaybookRun":
        return cls(
            run_id=d["run_id"],
            enclave_id=d["enclave_id"],
            playbook_id=d["playbook_id"],
            playbook_name=d.get("playbook_name", ""),
            current_stage=d.get("current_stage", ""),
            status=d.get("status", "running"),
            context=d.get("context", {}),
            started_at=d.get("started_at", 0.0),
            completed_at=d.get("completed_at", 0.0),
        )

    @staticmethod
    def gen_id() -> str:
        return _gen_id("run")


@dataclass
class StageExecution:
    """阶段执行记录"""
    run_id: str
    stage_name: str
    assigned_did: str = ""              # 执行者 DID
    status: str = "pending"             # pending / active / completed / rejected / skipped
    task_id: str = ""                   # 关联的 task_id
    output_ref: str = ""                # 产出物引用（vault key）
    started_at: float = 0.0
    completed_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "stage_name": self.stage_name,
            "assigned_did": self.assigned_did,
            "status": self.status,
            "task_id": self.task_id,
            "output_ref": self.output_ref,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StageExecution":
        return cls(
            run_id=d["run_id"],
            stage_name=d["stage_name"],
            assigned_did=d.get("assigned_did", ""),
            status=d.get("status", "pending"),
            task_id=d.get("task_id", ""),
            output_ref=d.get("output_ref", ""),
            started_at=d.get("started_at", 0.0),
            completed_at=d.get("completed_at", 0.0),
        )