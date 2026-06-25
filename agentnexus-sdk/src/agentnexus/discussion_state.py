"""Discussion voting state machine."""
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List
from enum import Enum
import uuid
import time
import asyncio
import json

from .discussion_models import *  # noqa: F401,F403


# ── Discussion State Machine ─────────────────────────────────────────────

class DiscussionState(str, Enum):
    """Discussion lifecycle states."""
    OPEN = "open"
    VOTING = "voting"
    CONCLUDED = "concluded"


@dataclass
class VoteState:
    """Internal vote tracking state."""
    topic_id: str
    votes: Dict[str, str] = field(default_factory=dict)  # did -> "approve"/"reject"/"abstain"
    status: DiscussionState = DiscussionState.OPEN
    start_time: float = field(default_factory=time.time)
    seq_counter: int = 1  # Next sequence number for this topic

    def to_content(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "votes": self.votes,
            "status": self.status,
            "start_time": self.start_time,
            "seq_counter": self.seq_counter,
        }

    @classmethod
    def from_content(cls, content: dict) -> "VoteState":
        return cls(
            topic_id=content["topic_id"],
            votes=content.get("votes", {}),
            status=DiscussionState(content.get("status", "open")),
            start_time=content.get("start_time", time.time()),
            seq_counter=content.get("seq_counter", 1),
        )


class DiscussionStateMachine:
    """
    Discussion state machine for SDK-side tracking.

    States:
    - open: Discussion started, accepting replies
    - voting: Votes being cast
    - concluded: Discussion closed

    Valid transitions:
    - open -> open (reply)
    - open -> voting (first vote)
    - open -> concluded (manual conclude without voting)
    - voting -> voting (more votes)
    - voting -> concluded (auto via consensus or manual)
    """

    def __init__(self, discussion_start: DiscussionStart, initiator_did: str):
        self.topic_id = discussion_start.topic_id
        self.title = discussion_start.title
        self.participants = discussion_start.participants
        self.consensus = discussion_start.consensus
        self.related_task_id = discussion_start.related_task_id
        self.initiator_did = initiator_did

        self._state = DiscussionState.OPEN
        self._vote_state = VoteState(topic_id=discussion_start.topic_id)
        self._known_message_ids: set[int] = set()  # For reply_to validation
        self._timeout_task: Optional[asyncio.Task] = None

    @property
    def state(self) -> DiscussionState:
        return self._state

    @property
    def is_concluded(self) -> bool:
        return self._state == DiscussionState.CONCLUDED

    def record_message_id(self, msg_id: int) -> None:
        """Record a known message ID for reply_to validation."""
        self._known_message_ids.add(msg_id)

    def validate_reply_to(self, reply_to: Optional[int]) -> tuple[bool, str]:
        """
        Validate reply_to references a known message.

        Returns:
            (is_valid, status) where status is "valid", "unverified_ref", or "none"
        """
        if reply_to is None:
            return True, "none"
        if reply_to in self._known_message_ids:
            return True, "valid"
        return False, "unverified_ref"

    def add_vote(self, from_did: str, vote: str) -> bool:
        """
        Record a vote.

        Args:
            from_did: Voter's DID
            vote: "approve", "reject", or "abstain"

        Returns:
            True if vote was recorded, False if discussion is concluded
        """
        if self.is_concluded:
            return False

        self._vote_state.votes[from_did] = vote
        self._state = DiscussionState.VOTING
        self._vote_state.status = DiscussionState.VOTING
        return True

    def check_consensus(self) -> Optional[str]:
        """
        Check if consensus is reached.

        Returns:
            "approve", "reject", or None if no consensus yet
        """
        if not self.consensus:
            return None

        votes = self._vote_state.votes
        participants = set(self.participants)

        if self.consensus.mode == ConsensusMode.MAJORITY:
            approves = sum(1 for v in votes.values() if v == "approve")
            rejects = sum(1 for v in votes.values() if v == "reject")
            total = len([v for v in votes.values() if v in ("approve", "reject")])

            if total > 0:
                if approves > rejects and approves > total / 2:
                    return "approve"
                if rejects >= approves and rejects > total / 2:
                    return "reject"

        elif self.consensus.mode == ConsensusMode.UNANIMOUS:
            voted = set(votes.keys())
            # Check if all participants have voted
            if voted >= participants:
                values = set(votes.values())
                if values == {"approve"}:
                    return "approve"
                if "reject" in values:
                    return "reject"

        elif self.consensus.mode == ConsensusMode.LEADER_DECIDES:
            leader_vote = votes.get(self.consensus.leader_did)
            if leader_vote in ("approve", "reject"):
                return leader_vote

        return None

    def get_remaining_timeout(self) -> Optional[float]:
        """Get remaining timeout in seconds, or None if no timeout."""
        if not self.consensus or self.consensus.timeout_seconds is None:
            return None
        elapsed = time.time() - self._vote_state.start_time
        remaining = self.consensus.timeout_seconds - elapsed
        return max(0, remaining)

    def conclude(self) -> None:
        """Mark discussion as concluded."""
        self._state = DiscussionState.CONCLUDED
        self._vote_state.status = DiscussionState.CONCLUDED
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None

    def get_next_seq(self) -> int:
        """Get and increment the next sequence number."""
        seq = self._vote_state.seq_counter
        self._vote_state.seq_counter += 1
        return seq

    def get_vote_state_content(self) -> dict:
        """Get vote state for persistence (nexus_v1_internal)."""
        return self._vote_state.to_content()


__all__ = [name for name in globals() if not name.startswith("__")]
