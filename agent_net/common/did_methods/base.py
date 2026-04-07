"""
DID Method Handler 基类

每个 DID 方法（agentnexus, agent, key, web, meeet 等）实现一个 Handler 子类。
"""
from abc import ABC, abstractmethod
from typing import Optional

from agent_net.common.did import DIDResolutionResult, DIDError


class DIDMethodHandler(ABC):
    """
    DID 方法处理器抽象基类。

    子类必须实现：
    - method: str — DID 方法名（如 "agentnexus", "meeet"）
    - resolve(): 解析 DID 并返回 DIDResolutionResult
    """

    method: str  # 子类必须声明，如 "agentnexus" / "meeet" / "aps"

    @abstractmethod
    async def resolve(self, did: str, method_specific_id: str) -> DIDResolutionResult:
        """
        解析 DID，返回 DIDResolutionResult。

        Args:
            did: 完整的 DID 字符串
            method_specific_id: DID 方法特定部分（did:method:xxx 中的 xxx）

        Returns:
            DIDResolutionResult 包含 did_document、public_key 等

        Raises:
            DIDError 子类：解析失败时抛出
        """
        ...
