"""
Enclave API for SDK

ADR-013 §7 定义的 SDK Enclave API。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .client import AgentNexusClient


@dataclass
class VaultEntry:
    """Vault 文档条目"""
    key: str
    value: str
    version: str
    updated_by: str
    updated_at: float
    message: str = ""
    action: str = "update"

    @classmethod
    def from_dict(cls, d: dict) -> "VaultEntry":
        return cls(
            key=d.get("key", ""),
            value=d.get("value", ""),
            version=str(d.get("version", "")),
            updated_by=d.get("updated_by", ""),
            updated_at=d.get("updated_at", 0.0),
            message=d.get("message", ""),
            action=d.get("action", "update"),
        )


@dataclass
class EnclaveInfo:
    """Enclave 信息"""
    enclave_id: str
    name: str
    owner_did: str
    status: str
    vault_backend: str
    created_at: float

    @classmethod
    def from_dict(cls, d: dict) -> "EnclaveInfo":
        return cls(
            enclave_id=d.get("enclave_id", ""),
            name=d.get("name", ""),
            owner_did=d.get("owner_did", ""),
            status=d.get("status", "active"),
            vault_backend=d.get("vault_backend", "local"),
            created_at=d.get("created_at", 0.0),
        )


@dataclass
class PlaybookRunInfo:
    """Playbook 运行信息"""
    run_id: str
    enclave_id: str
    playbook_name: str
    current_stage: str
    run_status: str
    stages: dict
    started_at: float
    completed_at: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "PlaybookRunInfo":
        return cls(
            run_id=d.get("run_id", ""),
            enclave_id=d.get("enclave_id", ""),
            playbook_name=d.get("playbook_name", ""),
            current_stage=d.get("current_stage", ""),
            run_status=d.get("run_status", "running"),
            stages=d.get("stages", {}),
            started_at=d.get("started_at", 0.0),
            completed_at=d.get("completed_at"),
        )


class VaultProxy:
    """
    Vault 操作代理。

    用法：
        await enclave.vault.put("requirements", "...")
        doc = await enclave.vault.get("requirements")
    """

    def __init__(self, client: "AgentNexusClient", enclave_id: str, actor_did: str | None = None):
        self._client = client
        self._enclave_id = enclave_id
        self._actor_did = actor_did

    def _actor(self, actor_did: str | None = None) -> str:
        return actor_did or self._actor_did or self._client.agent_info.did

    async def get(
        self,
        key: str,
        version: Optional[str] = None,
        *,
        actor_did: str | None = None,
    ) -> VaultEntry:
        """读取文档"""
        params = {"actor_did": self._actor(actor_did)}
        if version:
            params["version"] = version
        data = await self._client._request(
            "GET",
            f"/enclaves/{self._enclave_id}/vault/{key}",
            params=params,
        )
        return VaultEntry.from_dict(data)

    async def put(
        self,
        key: str,
        value: str,
        message: str = "",
        *,
        author_did: str | None = None,
    ) -> VaultEntry:
        """写入文档"""
        data = await self._client._request(
            "PUT",
            f"/enclaves/{self._enclave_id}/vault/{key}",
            json={
                "value": value,
                "author_did": author_did or self._actor(),
                "message": message,
            },
        )
        return VaultEntry.from_dict(data)

    async def list(self, prefix: str = "", *, actor_did: str | None = None) -> list[VaultEntry]:
        """列出文档"""
        params = {"actor_did": self._actor(actor_did)}
        if prefix:
            params["prefix"] = prefix
        data = await self._client._request(
            "GET",
            f"/enclaves/{self._enclave_id}/vault",
            params=params,
        )
        entries = data.get("entries", [])
        return [VaultEntry.from_dict(e) for e in entries]

    async def history(
        self,
        key: str,
        limit: int = 10,
        *,
        actor_did: str | None = None,
    ) -> list[VaultEntry]:
        """查看历史版本"""
        data = await self._client._request(
            "GET",
            f"/enclaves/{self._enclave_id}/vault/{key}/history",
            params={"actor_did": self._actor(actor_did), "limit": limit},
        )
        history = data.get("history", [])
        return [VaultEntry.from_dict(e) for e in history]

    async def delete(self, key: str, *, author_did: str | None = None) -> bool:
        """删除文档"""
        await self._client._request(
            "DELETE",
            f"/enclaves/{self._enclave_id}/vault/{key}",
            json={"author_did": author_did or self._actor()},
        )
        return True


class PlaybookRunProxy:
    """
    Playbook 运行代理。

    用法：
        run = await enclave.run_playbook(playbook_def)
        status = await run.get_status()
    """

    def __init__(
        self,
        client: "AgentNexusClient",
        enclave_id: str,
        run_id: str,
        actor_did: str | None = None,
    ):
        self._client = client
        self._enclave_id = enclave_id
        self._run_id = run_id
        self._actor_did = actor_did

    @property
    def run_id(self) -> str:
        return self._run_id

    async def get_status(self, *, actor_did: str | None = None) -> PlaybookRunInfo:
        """获取运行状态"""
        data = await self._client._request(
            "GET",
            f"/enclaves/{self._enclave_id}/runs/{self._run_id}",
            params={"actor_did": actor_did or self._actor_did or self._client.agent_info.did},
        )
        return PlaybookRunInfo.from_dict(data)


class EnclaveProxy:
    """
    Enclave 代理对象。

    用法：
        enclave = await nexus.create_enclave(...)
        await enclave.vault.put("doc", "content")
        run = await enclave.run_playbook(playbook_def)
    """

    def __init__(
        self,
        client: "AgentNexusClient",
        enclave_id: str,
        info: EnclaveInfo,
        actor_did: str | None = None,
    ):
        self._client = client
        self._enclave_id = enclave_id
        self._info = info
        self._actor_did = actor_did
        self._vault = VaultProxy(client, enclave_id, actor_did=actor_did)

    @property
    def enclave_id(self) -> str:
        return self._enclave_id

    @property
    def info(self) -> EnclaveInfo:
        return self._info

    @property
    def vault(self) -> VaultProxy:
        """访问 Vault 操作"""
        return self._vault

    async def run_playbook(
        self,
        playbook: Optional[dict] = None,
        playbook_id: Optional[str] = None,
        *,
        actor_did: str | None = None,
    ) -> PlaybookRunProxy:
        """
        启动 Playbook。

        Args:
            playbook: Playbook 定义（内联）
            playbook_id: 已存在的 Playbook ID（与 playbook 二选一）

        Returns:
            PlaybookRunProxy
        """
        actor = actor_did or self._actor_did or self._client.agent_info.did
        payload = {"actor_did": actor}
        if playbook_id:
            payload["playbook_id"] = playbook_id
        elif playbook:
            payload["playbook"] = playbook
        else:
            raise ValueError("Either playbook or playbook_id must be provided")

        data = await self._client._request(
            "POST",
            f"/enclaves/{self._enclave_id}/runs",
            json=payload,
        )
        run_id = data.get("run_id", "")
        return PlaybookRunProxy(self._client, self._enclave_id, run_id, actor_did=actor)

    async def get_run(
        self,
        run_id: Optional[str] = None,
        *,
        actor_did: str | None = None,
    ) -> PlaybookRunInfo:
        """
        获取 Playbook 运行状态。

        Args:
            run_id: Run ID（省略则返回最新）

        Returns:
            PlaybookRunInfo
        """
        if run_id:
            path = f"/enclaves/{self._enclave_id}/runs/{run_id}"
        else:
            path = f"/enclaves/{self._enclave_id}/runs"

        data = await self._client._request(
            "GET",
            path,
            params={"actor_did": actor_did or self._actor_did or self._client.agent_info.did},
        )
        return PlaybookRunInfo.from_dict(data)

    async def add_member(
        self,
        did: str,
        role: str,
        permissions: str = "rw",
        handbook: str = "",
        *,
        actor_did: str | None = None,
    ) -> bool:
        """添加成员"""
        await self._client._request(
            "POST",
            f"/enclaves/{self._enclave_id}/members",
            json={
                "actor_did": actor_did or self._actor_did or self._client.agent_info.did,
                "did": did,
                "role": role,
                "permissions": permissions,
                "handbook": handbook,
            },
        )
        return True

    async def remove_member(self, did: str, *, actor_did: str | None = None) -> bool:
        """移除成员"""
        await self._client._request(
            "DELETE",
            f"/enclaves/{self._enclave_id}/members/{did}",
            params={"actor_did": actor_did or self._actor_did or self._client.agent_info.did},
        )
        return True


class EnclaveManager:
    """
    Enclave 管理器。

    用法：
        enclave = await nexus.enclaves.create(...)
        enclaves = await nexus.enclaves.list()
    """

    def __init__(self, client: "AgentNexusClient"):
        self._client = client

    async def create(
        self,
        name: str,
        members: dict[str, dict],
        vault_backend: str = "local",
        vault_config: Optional[dict] = None,
        *,
        owner_did: str | None = None,
        actor_did: str | None = None,
    ) -> EnclaveProxy:
        """
        创建 Enclave。

        Args:
            name: Enclave 名称
            members: 成员映射 {"role": {"did": "...", "handbook": "...", "permissions": "rw"}}
            vault_backend: Vault 后端类型（local / git）
            vault_config: Vault 配置（git 需要 repo_path）

        Returns:
            EnclaveProxy
        """
        owner = owner_did or self._client.agent_info.did
        actor = actor_did or self._client.agent_info.did
        data = await self._client._request(
            "POST",
            "/enclaves",
            json={
                "name": name,
                "owner_did": owner,
                "actor_did": actor,
                "vault_backend": vault_backend,
                "vault_config": vault_config or {},
                "members": members,
            },
        )
        enclave_id = data.get("enclave_id", "")

        # 获取完整信息
        info = await self._get_info(enclave_id, actor_did=actor)
        return EnclaveProxy(self._client, enclave_id, info, actor_did=actor)

    async def get(self, enclave_id: str, *, actor_did: str | None = None) -> EnclaveProxy:
        """获取 Enclave"""
        actor = actor_did or self._client.agent_info.did
        info = await self._get_info(enclave_id, actor_did=actor)
        return EnclaveProxy(self._client, enclave_id, info, actor_did=actor)

    async def list(self, *, actor_did: str | None = None, status: str | None = None) -> list[EnclaveInfo]:
        """列出我参与的 Enclave"""
        params = {"actor_did": actor_did or self._client.agent_info.did}
        if status:
            params["status"] = status
        data = await self._client._request("GET", "/enclaves", params=params)
        enclaves = data.get("enclaves", [])
        return [EnclaveInfo.from_dict(e) for e in enclaves]

    async def _get_info(self, enclave_id: str, *, actor_did: str | None = None) -> EnclaveInfo:
        """获取 Enclave 信息"""
        data = await self._client._request(
            "GET",
            f"/enclaves/{enclave_id}",
            params={"actor_did": actor_did or self._client.agent_info.did},
        )
        return EnclaveInfo.from_dict(data)

    async def archive(self, enclave_id: str, *, actor_did: str | None = None) -> bool:
        """归档 Enclave"""
        await self._client._request(
            "DELETE",
            f"/enclaves/{enclave_id}",
            params={"actor_did": actor_did or self._client.agent_info.did},
        )
        return True
