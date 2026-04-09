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

    def __init__(self, client: "AgentNexusClient", enclave_id: str):
        self._client = client
        self._enclave_id = enclave_id

    async def get(self, key: str, version: Optional[str] = None) -> VaultEntry:
        """读取文档"""
        if not self._client._session:
            raise RuntimeError("Client not connected")

        url = f"{self._client.daemon_url}/enclaves/{self._enclave_id}/vault/{key}"
        params = {"version": version} if version else None

        async with self._client._session.get(url, params=params) as resp:
            if resp.status == 404:
                raise KeyError(f"Key not found: {key}")
            if resp.status != 200:
                raise RuntimeError(f"Vault get failed: {await resp.text()}")

            data = await resp.json()
            return VaultEntry.from_dict(data)

    async def put(
        self,
        key: str,
        value: str,
        message: str = "",
    ) -> VaultEntry:
        """写入文档"""
        if not self._client._session:
            raise RuntimeError("Client not connected")

        headers = {}
        if self._client.token:
            headers["Authorization"] = f"Bearer {self._client.token}"

        async with self._client._session.put(
            f"{self._client.daemon_url}/enclaves/{self._enclave_id}/vault/{key}",
            headers=headers,
            json={
                "value": value,
                "author_did": self._client.agent_info.did,
                "message": message,
            },
        ) as resp:
            if resp.status == 403:
                raise PermissionError("No write permission for this vault")
            if resp.status != 200:
                raise RuntimeError(f"Vault put failed: {await resp.text()}")

            data = await resp.json()
            return VaultEntry.from_dict(data)

    async def list(self, prefix: str = "") -> list[VaultEntry]:
        """列出文档"""
        if not self._client._session:
            raise RuntimeError("Client not connected")

        params = {"prefix": prefix} if prefix else None
        async with self._client._session.get(
            f"{self._client.daemon_url}/enclaves/{self._enclave_id}/vault",
            params=params,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Vault list failed: {await resp.text()}")

            data = await resp.json()
            entries = data.get("entries", [])
            return [VaultEntry.from_dict(e) for e in entries]

    async def history(self, key: str, limit: int = 10) -> list[VaultEntry]:
        """查看历史版本"""
        if not self._client._session:
            raise RuntimeError("Client not connected")

        async with self._client._session.get(
            f"{self._client.daemon_url}/enclaves/{self._enclave_id}/vault/{key}/history",
            params={"limit": limit},
        ) as resp:
            if resp.status == 404:
                raise KeyError(f"Key not found: {key}")
            if resp.status != 200:
                raise RuntimeError(f"Vault history failed: {await resp.text()}")

            data = await resp.json()
            history = data.get("history", [])
            return [VaultEntry.from_dict(e) for e in history]

    async def delete(self, key: str) -> bool:
        """删除文档"""
        if not self._client._session:
            raise RuntimeError("Client not connected")

        headers = {}
        if self._client.token:
            headers["Authorization"] = f"Bearer {self._client.token}"

        async with self._client._session.delete(
            f"{self._client.daemon_url}/enclaves/{self._enclave_id}/vault/{key}",
            headers=headers,
            json={"author_did": self._client.agent_info.did},
        ) as resp:
            if resp.status == 403:
                raise PermissionError("No delete permission for this vault")
            return resp.status == 200


class PlaybookRunProxy:
    """
    Playbook 运行代理。

    用法：
        run = await enclave.run_playbook(playbook_def)
        status = await run.get_status()
    """

    def __init__(self, client: "AgentNexusClient", enclave_id: str, run_id: str):
        self._client = client
        self._enclave_id = enclave_id
        self._run_id = run_id

    @property
    def run_id(self) -> str:
        return self._run_id

    async def get_status(self) -> PlaybookRunInfo:
        """获取运行状态"""
        if not self._client._session:
            raise RuntimeError("Client not connected")

        async with self._client._session.get(
            f"{self._client.daemon_url}/enclaves/{self._enclave_id}/runs/{self._run_id}",
        ) as resp:
            if resp.status == 404:
                raise KeyError(f"Run not found: {self._run_id}")
            if resp.status != 200:
                raise RuntimeError(f"Get run status failed: {await resp.text()}")

            data = await resp.json()
            return PlaybookRunInfo.from_dict(data)


class EnclaveProxy:
    """
    Enclave 代理对象。

    用法：
        enclave = await nexus.create_enclave(...)
        await enclave.vault.put("doc", "content")
        run = await enclave.run_playbook(playbook_def)
    """

    def __init__(self, client: "AgentNexusClient", enclave_id: str, info: EnclaveInfo):
        self._client = client
        self._enclave_id = enclave_id
        self._info = info
        self._vault = VaultProxy(client, enclave_id)

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
        playbook: dict,
        playbook_id: Optional[str] = None,
    ) -> PlaybookRunProxy:
        """
        启动 Playbook。

        Args:
            playbook: Playbook 定义（内联）
            playbook_id: 已存在的 Playbook ID（与 playbook 二选一）

        Returns:
            PlaybookRunProxy
        """
        if not self._client._session:
            raise RuntimeError("Client not connected")

        headers = {}
        if self._client.token:
            headers["Authorization"] = f"Bearer {self._client.token}"

        payload = {}
        if playbook_id:
            payload["playbook_id"] = playbook_id
        else:
            payload["playbook"] = playbook

        async with self._client._session.post(
            f"{self._client.daemon_url}/enclaves/{self._enclave_id}/runs",
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Run playbook failed: {await resp.text()}")

            data = await resp.json()
            run_id = data.get("run_id", "")
            return PlaybookRunProxy(self._client, self._enclave_id, run_id)

    async def get_run(self, run_id: Optional[str] = None) -> PlaybookRunInfo:
        """
        获取 Playbook 运行状态。

        Args:
            run_id: Run ID（省略则返回最新）

        Returns:
            PlaybookRunInfo
        """
        if not self._client._session:
            raise RuntimeError("Client not connected")

        if run_id:
            url = f"{self._client.daemon_url}/enclaves/{self._enclave_id}/runs/{run_id}"
        else:
            url = f"{self._client.daemon_url}/enclaves/{self._enclave_id}/runs"

        async with self._client._session.get(url) as resp:
            if resp.status == 404:
                raise KeyError(f"Run not found")
            if resp.status != 200:
                raise RuntimeError(f"Get run failed: {await resp.text()}")

            data = await resp.json()
            return PlaybookRunInfo.from_dict(data)

    async def add_member(
        self,
        did: str,
        role: str,
        permissions: str = "rw",
        handbook: str = "",
    ) -> bool:
        """添加成员"""
        if not self._client._session:
            raise RuntimeError("Client not connected")

        headers = {}
        if self._client.token:
            headers["Authorization"] = f"Bearer {self._client.token}"

        async with self._client._session.post(
            f"{self._client.daemon_url}/enclaves/{self._enclave_id}/members",
            headers=headers,
            json={
                "did": did,
                "role": role,
                "permissions": permissions,
                "handbook": handbook,
            },
        ) as resp:
            return resp.status == 200

    async def remove_member(self, did: str) -> bool:
        """移除成员"""
        if not self._client._session:
            raise RuntimeError("Client not connected")

        headers = {}
        if self._client.token:
            headers["Authorization"] = f"Bearer {self._client.token}"

        async with self._client._session.delete(
            f"{self._client.daemon_url}/enclaves/{self._enclave_id}/members/{did}",
            headers=headers,
        ) as resp:
            return resp.status == 200


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
        if not self._client._session:
            raise RuntimeError("Client not connected")

        headers = {}
        if self._client.token:
            headers["Authorization"] = f"Bearer {self._client.token}"

        async with self._client._session.post(
            f"{self._client.daemon_url}/enclaves",
            headers=headers,
            json={
                "name": name,
                "owner_did": self._client.agent_info.did,
                "vault_backend": vault_backend,
                "vault_config": vault_config or {},
                "members": members,
            },
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Create enclave failed: {await resp.text()}")

            data = await resp.json()
            enclave_id = data.get("enclave_id", "")

            # 获取完整信息
            info = await self._get_info(enclave_id)
            return EnclaveProxy(self._client, enclave_id, info)

    async def get(self, enclave_id: str) -> EnclaveProxy:
        """获取 Enclave"""
        info = await self._get_info(enclave_id)
        return EnclaveProxy(self._client, enclave_id, info)

    async def list(self) -> list[EnclaveInfo]:
        """列出我参与的 Enclave"""
        if not self._client._session:
            raise RuntimeError("Client not connected")

        async with self._client._session.get(
            f"{self._client.daemon_url}/enclaves",
            params={"did": self._client.agent_info.did},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"List enclaves failed: {await resp.text()}")

            data = await resp.json()
            enclaves = data.get("enclaves", [])
            return [EnclaveInfo.from_dict(e) for e in enclaves]

    async def _get_info(self, enclave_id: str) -> EnclaveInfo:
        """获取 Enclave 信息"""
        if not self._client._session:
            raise RuntimeError("Client not connected")

        async with self._client._session.get(
            f"{self._client.daemon_url}/enclaves/{enclave_id}",
        ) as resp:
            if resp.status == 404:
                raise KeyError(f"Enclave not found: {enclave_id}")
            if resp.status != 200:
                raise RuntimeError(f"Get enclave failed: {await resp.text()}")

            data = await resp.json()
            return EnclaveInfo.from_dict(data)

    async def archive(self, enclave_id: str) -> bool:
        """归档 Enclave"""
        if not self._client._session:
            raise RuntimeError("Client not connected")

        headers = {}
        if self._client.token:
            headers["Authorization"] = f"Bearer {self._client.token}"

        async with self._client._session.delete(
            f"{self._client.daemon_url}/enclaves/{enclave_id}",
            headers=headers,
        ) as resp:
            return resp.status == 200
