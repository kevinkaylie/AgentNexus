"""
路由模块 - 判断目标DID是本地还是远程，选择传输路径
v1.0-05: 新增意图路由，支持主 DID 自动转发到子 Agent
"""
import asyncio
import json
import hmac
import hashlib
import time
import logging
import aiohttp
from typing import Optional
from . import storage

logger = logging.getLogger(__name__)

# 意图路由匹配阈值（S1-05-1）
MIN_MATCH_SCORE = 2  # 至少 2 个关键词匹配才转发

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

    async def _intent_route(self, content: str, owner_did: str) -> Optional[str]:
        """
        根据消息内容匹配最合适的子 Agent（v1.0-05）。
        策略：关键词匹配 Agent capabilities + tags。

        Args:
            content: 消息内容
            owner_did: 主 DID

        Returns:
            匹配的子 Agent DID，或 None（无匹配）
        """
        try:
            agents = await storage.list_owned_agents(owner_did)
            if not agents:
                return None

            # 将 content 转为字符串
            content_str = content if isinstance(content, str) else json.dumps(content)
            content_lower = content_str.lower()

            best_match = None
            best_score = 0

            for agent in agents:
                profile = agent.get("profile", {})
                caps = profile.get("capabilities", [])
                tags = profile.get("tags", [])
                # 使用 set 去重，避免 tags 继承 capabilities 导致重复计数
                keywords = set(c.lower() for c in caps + tags)

                score = sum(1 for kw in keywords if kw in content_lower)
                if score > best_score:
                    best_score = score
                    best_match = agent["did"]

            # 匹配阈值，避免低质量转发（S1-05-1）
            if best_score < MIN_MATCH_SCORE:
                return None  # 无足够匹配，消息留在主 DID 收件箱

            logger.info(f"Intent route: {owner_did} → {best_match} (score={best_score})")
            return best_match
        except Exception as e:
            logger.warning(f"Intent route error for {owner_did}: {e}")
            return None

    async def route_message(self, from_did: str, to_did: str, content: str,
                            session_id: str = "", reply_to: int | None = None,
                            message_type: str | None = None,
                            protocol: str | None = None,
                            content_encoding: str | None = None,
                            message_id: str | None = None) -> dict:
        """路由消息：本地直投 -> 意图路由 -> 远程P2P -> Relay -> 离线存储"""
        # P2_2: 生成 message_id（如未提供）
        import uuid
        if not message_id:
            message_id = f"msg_{uuid.uuid4().hex[:16]}"

        # 1. 本地直投
        if self.is_local(to_did):
            await self._local_sessions[to_did].put({
                "from": from_did,
                "content": content,
                "session_id": session_id,
                "reply_to": reply_to,
                "message_type": message_type,
                "protocol": protocol,
                "content_encoding": content_encoding,
                "message_id": message_id,
            })
            if message_type == "state_notify":
                asyncio.create_task(self._intercept_playbook_state(from_did, content))
            return {"status": "delivered", "method": "local", "session_id": session_id, "message_id": message_id}

        # 2. 意图路由（v1.0-05，P1 修复）：如果 to_did 是主 DID 且不在本地，尝试转发到子 Agent
        #    这样外部发消息给离线的主 DID 时，可以先转发到在线的子 Agent
        owner = await storage.get_owner(to_did)
        if owner:
            target = await self._intent_route(content, to_did)
            if target:
                # 递归路由到子 Agent（保留原始 from_did）
                result = await self.route_message(
                    from_did, target, content, session_id, reply_to,
                    message_type, protocol, content_encoding, message_id,
                )
                # 如果转发成功，返回结果；否则继续尝试其他路由方式
                if result["status"] == "delivered":
                    return result

        # 3. 查通讯录，尝试远程投递
        contact = await storage.get_contact(to_did)
        if contact and contact.get("endpoint"):
            try:
                result = await self._send_remote(from_did, to_did, content, contact["endpoint"],
                                                 session_id, reply_to, message_type, protocol, content_encoding, message_id)
                if result:
                    return {"status": "delivered", "method": "p2p", "session_id": session_id, "message_id": message_id}
            except Exception:
                pass

        # 4. 尝试 Relay
        if contact and contact.get("relay"):
            try:
                result = await self._send_relay(from_did, to_did, content, contact["relay"],
                                                session_id, reply_to, message_type, protocol, content_encoding, message_id)
                if result:
                    return {"status": "delivered", "method": "relay", "session_id": session_id, "message_id": message_id}
            except Exception:
                pass

        # 5. 离线存储
        await storage.store_message(from_did, to_did, content, session_id, reply_to,
                                    message_type, protocol, content_encoding, message_id)

        # 5. Playbook 消息拦截（ADR-013 §4）
        if message_type == "state_notify":
            asyncio.create_task(self._intercept_playbook_state(from_did, content))

        # 6. 触发 Push 通知（ADR-012 L5）
        asyncio.create_task(self._push_notify(to_did, from_did, session_id, message_type, content))

        return {"status": "queued", "method": "offline", "session_id": session_id}

    async def _push_notify(self, to_did: str, from_did: str, session_id: str,
                           message_type: str | None, content: str):
        """消息到达后触发 Push 通知（ADR-012 §4）"""
        try:
            registrations = await storage.get_active_push_registrations(to_did)
            if not registrations:
                return  # 无注册，静默（消息已存储）

            # 构建通知 body
            preview = content[:200] if isinstance(content, str) else json.dumps(content)[:200]
            timestamp = time.time()

            for reg in registrations:
                try:
                    body = {
                        "event": "new_message",
                        "to_did": to_did,
                        "from_did": from_did,
                        "session_id": session_id,
                        "message_type": message_type,
                        "preview": preview,
                        "timestamp": timestamp,
                    }
                    body_json = json.dumps(body, separators=(',', ':'))
                    signature = hmac.new(
                        reg["callback_secret"].encode(),
                        body_json.encode(),
                        hashlib.sha256
                    ).hexdigest()

                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            reg["callback_url"],
                            json=body,
                            headers={
                                "Content-Type": "application/json",
                                "X-Nexus-Signature": f"sha256={signature}",
                                "X-Nexus-Timestamp": str(timestamp),
                            },
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as resp:
                            if resp.status >= 400:
                                logger.warning(f"Push notify failed for {reg['registration_id']}: HTTP {resp.status}")
                except Exception as e:
                    logger.warning(f"Push notify failed for {reg['registration_id']}: {e}")
        except Exception as e:
            logger.warning(f"Push notify error for {to_did}: {e}")

    async def _intercept_playbook_state(self, from_did: str, content: str):
        """
        拦截 state_notify 消息，检查是否关联 Playbook 并推进流程（ADR-013 §4）。
        """
        try:
            # 解析消息内容
            if not content:
                return
            try:
                msg = json.loads(content)
            except json.JSONDecodeError:
                return

            task_id = msg.get("task_id")
            if not task_id:
                return  # 普通状态通知，不是 Playbook 驱动的

            # 查找关联的 stage_execution
            from agent_net.storage import get_stage_execution_by_task
            execution = await get_stage_execution_by_task(task_id)
            if not execution:
                return  # 普通任务，不是 Playbook 驱动的

            status = msg.get("status")
            run_id = execution["run_id"]
            stage_name = execution["stage_name"]

            # 导入 PlaybookEngine
            from agent_net.enclave.playbook import get_playbook_engine
            engine = get_playbook_engine()

            if status == "completed":
                await engine.on_stage_completed(
                    run_id, stage_name,
                    output_ref=msg.get("output_ref", "")
                )
            elif status == "rejected":
                await engine.on_stage_rejected(
                    run_id, stage_name,
                    reason=msg.get("reason", "")
                )
            # 其他状态（in_progress 等）不需要处理

        except Exception as e:
            logger.warning(f"Playbook intercept error: {e}")

    async def _send_remote(self, from_did: str, to_did: str, content: str, endpoint: str,
                           session_id: str = "", reply_to: int | None = None,
                           message_type: str | None = None,
                           protocol: str | None = None,
                           content_encoding: str | None = None,
                           message_id: str | None = None) -> bool:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{endpoint}/deliver",
                json={"from": from_did, "to": to_did, "content": content,
                      "session_id": session_id, "reply_to": reply_to,
                      "message_type": message_type, "protocol": protocol,
                      "content_encoding": content_encoding, "message_id": message_id},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200

    async def _send_relay(self, from_did: str, to_did: str, content: str, relay: str,
                          session_id: str = "", reply_to: int | None = None,
                          message_type: str | None = None,
                          protocol: str | None = None,
                          content_encoding: str | None = None,
                          message_id: str | None = None) -> bool:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{relay}/relay",
                json={"from": from_did, "to": to_did, "content": content,
                      "session_id": session_id, "reply_to": reply_to,
                      "message_type": message_type, "protocol": protocol,
                      "content_encoding": content_encoding, "message_id": message_id},
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
