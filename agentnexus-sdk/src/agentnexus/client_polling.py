"""
AgentNexus SDK Client

Core client implementation for connecting to AgentNexus network.
"""
import asyncio
import json


from .exceptions import (
    MessageDeliveryError,
)
from .models import Message
from .actions import (
    ActionMessage,
    ActionType,
    PROTOCOL_NEXUS_V1,
)
from .discussion import (
    DiscussionMessageType,
)


class ClientPollingMixin:
    async def _poll_loop(self) -> None:
        """Background polling loop for incoming messages."""
        success_count = 0
        while self._running:
            try:
                await self._poll_messages()
                # Reset backoff on success
                self._poll_backoff = 1.0
                self._poll_interval = 2.0
                success_count += 1
                # After 10 consecutive successes, consider connection stable
                # and reset any accumulated backoff state
                if success_count >= 10:
                    success_count = 0
            except Exception as e:
                success_count = 0
                # Exponential backoff
                self._poll_interval = min(
                    self._poll_interval * 2,
                    self._max_backoff,
                )
                print(f"[SDK] Poll error, backing off to {self._poll_interval}s: {e}")

            await asyncio.sleep(self._poll_interval)

    async def _poll_messages(self) -> None:
        """Poll for new messages and dispatch to callbacks."""
        if not self._session:
            return

        async with self._session.get(
            f"{self.daemon_url}/messages/inbox/{self.agent_info.did}",
            params={"actor_did": self.agent_info.did},
            headers={"Authorization": f"Bearer {self.token}"} if self.token else None,
        ) as resp:
            if resp.status != 200:
                raise MessageDeliveryError(f"Poll failed: {resp.status}")

            payload = await resp.json()
            messages = payload.get("messages", payload) if isinstance(payload, dict) else payload

            for msg_data in messages:
                msg = Message(
                    id=msg_data["id"],
                    from_did=msg_data["from"],
                    content=msg_data["content"],
                    timestamp=msg_data["timestamp"],
                    session_id=msg_data.get("session_id", ""),
                    reply_to=msg_data.get("reply_to"),
                    message_type=msg_data.get("message_type"),
                    protocol=msg_data.get("protocol"),
                    message_id=msg_data.get("message_id"),
                )

                await self._dispatch_message(msg)

    async def _fetch_all_messages(self) -> list[Message]:
        """
        Fetch all messages for this Agent (including delivered ones).

        Used by DiscussionManager to query discussion history.
        """
        if not self._session:
            return []

        async with self._session.get(
            f"{self.daemon_url}/messages/all/{self.agent_info.did}",
            params={"limit": 1000, "actor_did": self.agent_info.did},
            headers={"Authorization": f"Bearer {self.token}"} if self.token else None,
        ) as resp:
            if resp.status != 200:
                return []

            data = await resp.json()
            messages = data.get("messages", [])
            return [
                Message(
                    id=msg_data["id"],
                    from_did=msg_data["from"],
                    content=msg_data["content"],
                    timestamp=msg_data["timestamp"],
                    session_id=msg_data.get("session_id", ""),
                    reply_to=msg_data.get("reply_to"),
                    message_type=msg_data.get("message_type"),
                    protocol=msg_data.get("protocol"),
                    message_id=msg_data.get("message_id"),
                )
                for msg_data in messages
            ]

    async def _dispatch_message(self, msg: Message) -> None:
        """Dispatch message to appropriate callbacks."""
        # Check if this is a Discussion Protocol message
        if (
            msg.message_type
            and msg.protocol == PROTOCOL_NEXUS_V1
            and msg.message_type in self._discussion_callbacks
        ):
            callbacks = self._discussion_callbacks[msg.message_type]
            if callbacks:
                try:
                    content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content

                    # Handle discussion message via DiscussionManager
                    if self._discussion_manager:
                        if msg.message_type == DiscussionMessageType.START:
                            sm = self._discussion_manager.handle_discussion_start(
                                msg.from_did, content, msg.id
                            )
                            for cb in callbacks:
                                try:
                                    result = cb(sm)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception as e:
                                    print(f"[SDK] Discussion callback error: {e}")
                            return
                        elif msg.message_type == DiscussionMessageType.REPLY:
                            reply, sm, validation_status = self._discussion_manager.handle_discussion_reply(
                                msg.from_did, content, msg.id
                            )
                            for cb in callbacks:
                                try:
                                    result = cb(reply, sm, validation_status)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception as e:
                                    print(f"[SDK] Discussion callback error: {e}")
                            return
                        elif msg.message_type == DiscussionMessageType.VOTE:
                            vote, sm, consensus_result = self._discussion_manager.handle_discussion_vote(
                                msg.from_did, content, msg.id
                            )
                            for cb in callbacks:
                                try:
                                    result = cb(vote, sm, consensus_result)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception as e:
                                    print(f"[SDK] Discussion callback error: {e}")
                            # Auto-conclude if consensus reached and we're the initiator
                            if consensus_result and sm.topic_id in self._discussion_manager._initiated:
                                await self._discussion_manager._check_auto_conclude(sm.topic_id)
                            return
                        elif msg.message_type == DiscussionMessageType.CONCLUDE:
                            conclude_msg, sm = self._discussion_manager.handle_discussion_conclude(
                                msg.from_did, content, msg.id
                            )
                            for cb in callbacks:
                                try:
                                    result = cb(conclude_msg, sm)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception as e:
                                    print(f"[SDK] Discussion callback error: {e}")
                            return
                except json.JSONDecodeError:
                    pass  # Fall through to action handling

        # Check if this is an Action Layer message
        if (
            msg.message_type
            and msg.protocol == PROTOCOL_NEXUS_V1
            and msg.message_type in self._action_callbacks
        ):
            callbacks = self._action_callbacks[msg.message_type]
            content = None
            # Check for emergency_halt (state_notify with status="emergency_halt")
            if msg.message_type == ActionType.STATE_NOTIFY:
                try:
                    content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                    if content.get("status") == "emergency_halt":
                        # Handle emergency halt with built-in enforcement
                        if self._emergency_controller:
                            result = await self._emergency_controller.handle_emergency_halt(
                                msg.from_did, content, self
                            )
                            if result.get("handled"):
                                # Emergency halt executed, don't call user callbacks
                                return
                        # Fall through if not handled (no controller or unauthorized)

                except (json.JSONDecodeError, TypeError):
                    pass

            if msg.message_type == ActionType.TASK_PROPOSE:
                try:
                    content = content if content is not None else (
                        json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                    )
                    action_msg = ActionMessage(
                        from_did=msg.from_did,
                        message_type=msg.message_type,
                        content=content,
                    )
                    handled = await self.worker.handle_task_propose(action_msg)
                    if handled:
                        return
                except json.JSONDecodeError:
                    pass

            if callbacks:
                # Parse content as action
                try:
                    content = content if content is not None else (
                        json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                    )
                    action_msg = ActionMessage(
                        from_did=msg.from_did,
                        message_type=msg.message_type,
                        content=content,
                    )
                    for cb in callbacks:
                        try:
                            result = cb(action_msg)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            print(f"[SDK] Callback error: {e}")
                    return
                except json.JSONDecodeError:
                    pass  # Fall through to regular message handling

        # Regular message or no action callback registered
        for cb in self._message_callbacks:
            try:
                result = cb(msg)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                print(f"[SDK] Message callback error: {e}")



__all__ = ["ClientPollingMixin"]
