"""
Agent Legacy DID Method Handler

解析 did:agent:<hex> 格式的 DID（向后兼容旧格式）。
"""
import logging

import aiosqlite

from agent_net.common.did import DIDResolutionResult, DIDNotFoundError
from agent_net.common.did_methods.base import DIDMethodHandler
from agent_net.common.did_methods.utils import build_did_document

logger = logging.getLogger(__name__)


class AgentLegacyHandler(DIDMethodHandler):
    """
    did:agent 方法处理器（向后兼容）。

    格式: did:agent:<hex>

    需要本地数据库来查找公钥，因为 did:agent 格式本身不包含可解析的公钥。
    """

    method = "agent"

    def __init__(self, db_path: str):
        """
        初始化处理器。

        Args:
            db_path: SQLite 数据库路径
        """
        self.db_path = db_path

    async def resolve(self, did: str, method_specific_id: str) -> DIDResolutionResult:
        """
        解析 did:agent:<hex>

        Args:
            did: 完整的 DID 字符串
            method_specific_id: hex 部分

        Returns:
            DIDResolutionResult

        Raises:
            DIDNotFoundError: 无法从本地数据库找到公钥
        """
        pubkey_bytes = await self._get_local_agent_key(did)

        if not pubkey_bytes:
            # 回退：从 hex 字符串解析（如果 key_part 是有效的 32 字节 hex）
            if len(method_specific_id) == 64:  # 32 bytes = 64 hex chars
                try:
                    pubkey_bytes = bytes.fromhex(method_specific_id)
                except ValueError:
                    pass

        if not pubkey_bytes:
            raise DIDNotFoundError(
                f"Cannot resolve did:agent without local database entry: {did}"
            )

        did_document = build_did_document(did, pubkey_bytes)

        return DIDResolutionResult(
            did=did,
            method="agent",
            public_key=pubkey_bytes,
            did_document=did_document,
            metadata={"version": "legacy", "backward_compat": True},
        )

    async def _get_local_agent_key(self, did: str) -> bytes | None:
        """
        从本地数据库获取 Agent 的公钥。

        Args:
            did: Agent DID

        Returns:
            32 字节公钥，或 None
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT profile FROM agents WHERE did=?", (did,)
                ) as cur:
                    row = await cur.fetchone()
                    if not row:
                        return None

                import json
                profile = json.loads(row[0])

                # 尝试从 profile 获取公钥
                pubkey_hex = profile.get("public_key_hex")
                if pubkey_hex:
                    return bytes.fromhex(pubkey_hex)

        except Exception as e:
            logger.warning(f"Failed to get local agent key for {did}: {type(e).__name__} — {e}")

        return None
