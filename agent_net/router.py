"""
路由模块 - 判断目标DID是本地还是远程，选择传输路径
"""
import asyncio
import aiohttp
from typing import Optional
from . import storage

RELAY_URL = "https://relay.agent-net.io"  # 可配置


class Router:
    def __init__(self, relay_url: str = RELAY_URL):
        self.relay_url = relay_url
        self._local_sessions: dict[str, asyncio.Queue] = {}  # did -> message queue

    def register_local_session(self, did: str):
        if did not in self._local_sessions:
            self._local_sessions[did] = asyncio.Queue()

    def unregister_local_session(self, did: str):
        self._local_sessions.pop(did, None)

    def is_local(self, did: str) -> bool:
        return did in self._local_sessions

    async def route_message(self, from_did: str, to_did: str, content: str,
                            session_id: str = "", reply_to: int | None = None) -> dict:
        """路由消息：本地直投 -> 远程P2P -> Relay -> 离线存储"""
        # 1. 本地直投
        if self.is_local(to_did):
            await self._local_sessions[to_did].put({
                "from": from_did,
                "content": content,
                "session_id": session_id,
                "reply_to": reply_to,
            })
            return {"status": "delivered", "method": "local", "session_id": session_id}

        # 2. 查通讯录，尝试远程投递
        contact = await storage.get_contact(to_did)
        if contact and contact.get("endpoint"):
            try:
                result = await self._send_remote(from_did, to_did, content, contact["endpoint"],
                                                 session_id, reply_to)
                if result:
                    return {"status": "delivered", "method": "p2p", "session_id": session_id}
            except Exception:
                pass

        # 3. 尝试 Relay
        if contact and contact.get("relay"):
            try:
                result = await self._send_relay(from_did, to_did, content, contact["relay"],
                                                session_id, reply_to)
                if result:
                    return {"status": "delivered", "method": "relay", "session_id": session_id}
            except Exception:
                pass

        # 4. 离线存储
        await storage.store_message(from_did, to_did, content, session_id, reply_to)
        return {"status": "queued", "method": "offline", "session_id": session_id}

    async def _send_remote(self, from_did: str, to_did: str, content: str, endpoint: str,
                           session_id: str = "", reply_to: int | None = None) -> bool:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{endpoint}/deliver",
                json={"from": from_did, "to": to_did, "content": content,
                      "session_id": session_id, "reply_to": reply_to},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200

    async def _send_relay(self, from_did: str, to_did: str, content: str, relay: str,
                          session_id: str = "", reply_to: int | None = None) -> bool:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{relay}/relay",
                json={"from": from_did, "to": to_did, "content": content,
                      "session_id": session_id, "reply_to": reply_to},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status == 200

    async def receive(self, did: str, timeout: float = 0.1) -> Optional[dict]:
        """非阻塞接收本地消息"""
        if did not in self._local_sessions:
            return None
        try:
            return await asyncio.wait_for(self._local_sessions[did].get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None


# 全局单例
router = Router()
