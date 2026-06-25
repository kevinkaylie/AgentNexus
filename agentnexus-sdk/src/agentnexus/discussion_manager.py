"""Discussion lifecycle manager."""
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List
from enum import Enum
import uuid
import time
import asyncio
import json

from .discussion_models import *  # noqa: F401,F403
from .discussion_state import *  # noqa: F401,F403


# ── Discussion Manager ───────────────────────────────────────────────────

class DiscussionManager:
    """
    Manages multiple discussions for an Agent.

    Responsibilities:
    - Track discussions initiated by this Agent
    - Track discussions participated in
    - Handle timeout tasks
    - Provide discussion history queries
    """

    def __init__(self, client: "AgentNexusClient"):
        """
        Initialize DiscussionManager.

        Args:
            client: The AgentNexusClient instance
        """
        self._client = client
        self._my_did = client.agent_info.did

        # topic_id -> DiscussionStateMachine (for discussions we initiated)
        self._initiated: Dict[str, DiscussionStateMachine] = {}
        # topic_id -> DiscussionStateMachine (for discussions we participate in)
        self._participating: Dict[str, DiscussionStateMachine] = {}

        # topic_id -> list[Message] for history caching
        self._history_cache: Dict[str, list] = {}

    async def start_discussion(
        self,
        title: str,
        participants: List[str],
        context: Optional[str] = None,
        consensus: Optional[Consensus] = None,
        related_task_id: Optional[str] = None,
    ) -> str:
        """
        Start a new discussion.

        Uses point-to-point fanout: sends to each participant individually.

        Args:
            title: Discussion title
            participants: List of participant DIDs
            context: Optional context/background
            consensus: Optional consensus rules
            related_task_id: Optional related task

        Returns:
            Generated topic_id
        """
        topic_id = f"disc_{uuid.uuid4().hex}"

        # Ensure we're in participants
        if self._my_did not in participants:
            participants = participants + [self._my_did]

        discussion_start = DiscussionStart(
            topic_id=topic_id,
            title=title,
            participants=participants,
            context=context,
            consensus=consensus,
            related_task_id=related_task_id,
            seq=1,
        )

        # Create state machine
        state_machine = DiscussionStateMachine(discussion_start, self._my_did)
        self._initiated[topic_id] = state_machine

        # Start timeout task if needed
        if consensus and consensus.timeout_seconds:
            state_machine._timeout_task = asyncio.create_task(
                self._handle_timeout(topic_id)
            )

        # Fanout to all participants (except self)
        content = discussion_start.to_content()
        for participant_did in participants:
            if participant_did != self._my_did:
                await self._client.send(
                    to_did=participant_did,
                    content=content,
                    message_type=DiscussionMessageType.START,
                    protocol=PROTOCOL_NEXUS_V1,
                )

        return topic_id

    async def reply(
        self,
        topic_id: str,
        content: str,
        reply_to: Optional[int] = None,
        mentions: Optional[List[str]] = None,
        request_escalate: bool = False,
    ) -> None:
        """
        Reply to a discussion.

        Args:
            topic_id: The discussion to reply to
            content: Reply content
            reply_to: Optional message ID to quote
            mentions: Optional DIDs to mention
            request_escalate: Request escalation
        """
        state_machine = self._get_state_machine(topic_id)
        if not state_machine:
            raise ValueError(f"Unknown discussion: {topic_id}")

        if state_machine.is_concluded:
            raise ValueError(f"Discussion {topic_id} is already concluded")

        seq = state_machine.get_next_seq()

        reply = DiscussionReply(
            topic_id=topic_id,
            content=content,
            reply_to=reply_to,
            mentions=mentions,
            request_escalate=request_escalate,
            seq=seq,
        )

        # Fanout to all participants
        msg_content = reply.to_content()
        for participant_did in state_machine.participants:
            if participant_did != self._my_did:
                result = await self._client.send(
                    to_did=participant_did,
                    content=msg_content,
                    message_type=DiscussionMessageType.REPLY,
                    protocol=PROTOCOL_NEXUS_V1,
                )
                # Record message ID if we got one back
                if result and "id" in result:
                    state_machine.record_message_id(result["id"])

    async def vote(
        self,
        topic_id: str,
        vote: str,
        reason: Optional[str] = None,
    ) -> None:
        """
        Cast a vote in a discussion.

        Args:
            topic_id: The discussion to vote on
            vote: "approve", "reject", or "abstain"
            reason: Optional reason
        """
        state_machine = self._get_state_machine(topic_id)
        if not state_machine:
            raise ValueError(f"Unknown discussion: {topic_id}")

        if state_machine.is_concluded:
            raise ValueError(f"Discussion {topic_id} is already concluded")

        seq = state_machine.get_next_seq()

        discussion_vote = DiscussionVote(
            topic_id=topic_id,
            vote=vote,
            reason=reason,
            seq=seq,
        )

        # Record our vote locally
        state_machine.add_vote(self._my_did, vote)

        # Fanout to all participants
        msg_content = discussion_vote.to_content()
        for participant_did in state_machine.participants:
            if participant_did != self._my_did:
                await self._client.send(
                    to_did=participant_did,
                    content=msg_content,
                    message_type=DiscussionMessageType.VOTE,
                    protocol=PROTOCOL_NEXUS_V1,
                )

        # Check if we should auto-conclude (if we're the initiator)
        if topic_id in self._initiated:
            await self._check_auto_conclude(topic_id)

    async def conclude(
        self,
        topic_id: str,
        conclusion: str,
        conclusion_type: str = ConclusionType.CONSENSUS,
        action_items: Optional[List[ActionItem]] = None,
    ) -> None:
        """
        Conclude a discussion.

        Only the initiator can call this, except for auto-conclude from consensus.

        Args:
            topic_id: The discussion to conclude
            conclusion: Conclusion text
            conclusion_type: Type of conclusion
            action_items: Optional follow-up actions
        """
        state_machine = self._initiated.get(topic_id)
        if not state_machine:
            raise ValueError(f"Not the initiator of discussion: {topic_id}")

        if state_machine.is_concluded:
            raise ValueError(f"Discussion {topic_id} is already concluded")

        seq = state_machine.get_next_seq()

        discussion_conclude = DiscussionConclude(
            topic_id=topic_id,
            conclusion=conclusion,
            conclusion_type=conclusion_type,
            action_items=action_items,
            seq=seq,
        )

        state_machine.conclude()

        # Fanout to all participants
        msg_content = discussion_conclude.to_content()
        for participant_did in state_machine.participants:
            if participant_did != self._my_did:
                await self._client.send(
                    to_did=participant_did,
                    content=msg_content,
                    message_type=DiscussionMessageType.CONCLUDE,
                    protocol=PROTOCOL_NEXUS_V1,
                )

    # ── Message Handling ───────────────────────────────────────────────

    def handle_discussion_start(
        self,
        from_did: str,
        content: dict,
        msg_id: int,
    ) -> DiscussionStateMachine:
        """Handle incoming discussion_start."""
        discussion_start = DiscussionStart.from_content(content)

        state_machine = DiscussionStateMachine(discussion_start, from_did)
        state_machine.record_message_id(msg_id)

        # Store as participating (unless we're also the initiator)
        if from_did == self._my_did:
            self._initiated[discussion_start.topic_id] = state_machine
        else:
            self._participating[discussion_start.topic_id] = state_machine

        return state_machine

    def handle_discussion_reply(
        self,
        from_did: str,
        content: dict,
        msg_id: int,
    ) -> tuple[DiscussionReply, DiscussionStateMachine, str]:
        """
        Handle incoming discussion_reply.

        Returns:
            (reply, state_machine, validation_status)
            validation_status is one of: "valid", "unverified_ref", "none"
        """
        reply = DiscussionReply.from_content(content)
        topic_id = reply.topic_id

        state_machine = self._get_state_machine(topic_id)
        if not state_machine:
            raise ValueError(f"Unknown discussion: {topic_id}")

        state_machine.record_message_id(msg_id)

        # Validate reply_to
        is_valid, validation_status = state_machine.validate_reply_to(reply.reply_to)

        # Record in history cache
        self._add_to_history(topic_id, msg_id, from_did, content)

        return reply, state_machine, validation_status

    def handle_discussion_vote(
        self,
        from_did: str,
        content: dict,
        msg_id: int,
    ) -> tuple[DiscussionVote, DiscussionStateMachine, Optional[str]]:
        """
        Handle incoming discussion_vote.

        Returns:
            (vote, state_machine, consensus_result)
            consensus_result is "approve"/"reject" if consensus reached, else None
        """
        vote = DiscussionVote.from_content(content)
        topic_id = vote.topic_id

        state_machine = self._get_state_machine(topic_id)
        if not state_machine:
            raise ValueError(f"Unknown discussion: {topic_id}")

        state_machine.record_message_id(msg_id)
        state_machine.add_vote(from_did, vote.vote)

        # Check consensus if we're the initiator
        consensus_result = None
        if topic_id in self._initiated:
            consensus_result = state_machine.check_consensus()

        return vote, state_machine, consensus_result

    def handle_discussion_conclude(
        self,
        from_did: str,
        content: dict,
        msg_id: int,
    ) -> tuple[DiscussionConclude, DiscussionStateMachine]:
        """Handle incoming discussion_conclude."""
        conclude_msg = DiscussionConclude.from_content(content)
        topic_id = conclude_msg.topic_id

        state_machine = self._get_state_machine(topic_id)
        if not state_machine:
            raise ValueError(f"Unknown discussion: {topic_id}")

        # Verify sender is initiator
        if from_did != state_machine.initiator_did:
            raise ValueError(
                f"Only initiator {state_machine.initiator_did} can conclude, got {from_did}"
            )

        state_machine.conclude()
        state_machine.record_message_id(msg_id)

        return conclude_msg, state_machine

    # ── History Query ──────────────────────────────────────────────────

    async def get_discussion_history(
        self,
        topic_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> list:
        """
        Get discussion history.

        Args:
            topic_id: Filter by topic
            task_id: Filter by related task

        Returns:
            List of messages
        """
        # Check cache first
        if topic_id and topic_id in self._history_cache:
            cached = self._history_cache[topic_id]
            # Also check if we need to filter by task_id
            if task_id:
                sm = self._get_state_machine(topic_id)
                if sm and sm.related_task_id == task_id:
                    return cached
            else:
                return cached

        # Query from daemon inbox via client
        # Fetch all messages and filter by discussion message types
        try:
            messages = await self._client._fetch_all_messages()

            discussion_types = {
                DiscussionMessageType.START,
                DiscussionMessageType.REPLY,
                DiscussionMessageType.VOTE,
                DiscussionMessageType.CONCLUDE,
            }

            results = []
            topic_sm_map: dict[str, DiscussionStateMachine] = {}

            for msg in messages:
                if msg.protocol != PROTOCOL_NEXUS_V1:
                    continue
                if msg.message_type not in discussion_types:
                    continue

                try:
                    content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                except (json.JSONDecodeError, TypeError):
                    continue

                msg_topic_id = content.get("topic_id")
                if not msg_topic_id:
                    continue

                # Filter by topic_id if specified
                if topic_id and msg_topic_id != topic_id:
                    continue

                # Filter by task_id if specified
                if task_id:
                    # Check if this discussion is related to the task
                    if msg.message_type == DiscussionMessageType.START:
                        if content.get("related_task_id") != task_id:
                            continue
                    elif msg_topic_id in topic_sm_map:
                        sm = topic_sm_map[msg_topic_id]
                        if sm.related_task_id != task_id:
                            continue
                    else:
                        continue

                # Build result message
                result = {
                    "id": msg.id,
                    "from": msg.from_did,
                    "content": content,
                    "message_type": msg.message_type,
                    "timestamp": msg.timestamp,
                }
                results.append(result)

                # Track state machines for task_id filtering
                if task_id and msg.message_type == DiscussionMessageType.START:
                    sm = self._get_state_machine(msg_topic_id)
                    if sm:
                        topic_sm_map[msg_topic_id] = sm

            # Sort by timestamp
            results.sort(key=lambda x: x["timestamp"])

            # Update cache
            if topic_id:
                self._history_cache[topic_id] = results

            return results

        except Exception as e:
            print(f"[SDK] Failed to fetch discussion history: {e}")
            # Fall back to cache
            if topic_id:
                return self._history_cache.get(topic_id, [])
            return []

    # ── Internal Methods ───────────────────────────────────────────────

    def _get_state_machine(self, topic_id: str) -> Optional[DiscussionStateMachine]:
        """Get state machine for a topic (from either initiated or participating)."""
        if topic_id in self._initiated:
            return self._initiated[topic_id]
        return self._participating.get(topic_id)

    def _add_to_history(self, topic_id: str, msg_id: int, from_did: str, content: dict):
        """Add message to history cache."""
        if topic_id not in self._history_cache:
            self._history_cache[topic_id] = []
        self._history_cache[topic_id].append({
            "id": msg_id,
            "from": from_did,
            "content": content,
            "timestamp": time.time(),
        })

    async def _check_auto_conclude(self, topic_id: str) -> None:
        """Check if discussion should auto-conclude from consensus."""
        state_machine = self._initiated.get(topic_id)
        if not state_machine or state_machine.is_concluded:
            return

        consensus_result = state_machine.check_consensus()
        if consensus_result:
            # Auto-conclude
            conclusion = f"Consensus reached: {consensus_result}"
            await self.conclude(
                topic_id=topic_id,
                conclusion=conclusion,
                conclusion_type=ConclusionType.CONSENSUS,
            )

    async def _handle_timeout(self, topic_id: str) -> None:
        """Handle discussion timeout."""
        state_machine = self._initiated.get(topic_id)
        if not state_machine or not state_machine.consensus:
            return

        timeout_action = state_machine.consensus.timeout_action

        try:
            remaining = state_machine.get_remaining_timeout()
            if remaining and remaining > 0:
                await asyncio.sleep(remaining)

            if state_machine.is_concluded:
                return

            # Execute timeout action
            if timeout_action == TimeoutAction.AUTO_APPROVE:
                await self.conclude(
                    topic_id=topic_id,
                    conclusion="Auto-approved due to timeout",
                    conclusion_type=ConclusionType.CONSENSUS,
                )
            elif timeout_action == TimeoutAction.AUTO_REJECT:
                await self.conclude(
                    topic_id=topic_id,
                    conclusion="Auto-rejected due to timeout",
                    conclusion_type=ConclusionType.NO_CONSENSUS,
                )
            elif timeout_action == TimeoutAction.ESCALATE:
                # TODO: Implement escalation
                await self.conclude(
                    topic_id=topic_id,
                    conclusion="Escalated due to timeout",
                    conclusion_type=ConclusionType.ESCALATED,
                )

        except asyncio.CancelledError:
            pass  # Discussion concluded before timeout

__all__ = [name for name in globals() if not name.startswith("__")]
