"""
Tests for Discussion Protocol (ADR-011)
"""
import pytest
import asyncio
import time

from agentnexus.discussion import (
    DiscussionStart,
    DiscussionReply,
    DiscussionVote,
    DiscussionConclude,
    Consensus,
    ActionItem,
    ConsensusMode,
    TimeoutAction,
    ConclusionType,
    DiscussionStateMachine,
    DiscussionState,
)


class TestDiscussionModels:
    """Tests for discussion data models."""

    def test_discussion_start_to_content(self):
        """Test DiscussionStart serialization."""
        start = DiscussionStart(
            topic_id="disc_test123",
            title="Test Discussion",
            participants=["did:a", "did:b"],
            context="Some context",
        )
        content = start.to_content()

        assert content["topic_id"] == "disc_test123"
        assert content["title"] == "Test Discussion"
        assert content["participants"] == ["did:a", "did:b"]
        assert content["context"] == "Some context"
        assert content["seq"] == 1
        assert "consensus" not in content

    def test_discussion_start_with_consensus(self):
        """Test DiscussionStart with consensus rules."""
        consensus = Consensus(
            mode=ConsensusMode.MAJORITY,
            timeout_seconds=300,
            timeout_action=TimeoutAction.AUTO_REJECT,
        )
        start = DiscussionStart(
            topic_id="disc_test",
            title="Vote Test",
            participants=["did:a", "did:b", "did:c"],
            consensus=consensus,
        )
        content = start.to_content()

        assert content["consensus"]["mode"] == "majority"
        assert content["consensus"]["timeout_seconds"] == 300
        assert content["consensus"]["timeout_action"] == "auto_reject"

    def test_discussion_start_from_content(self):
        """Test DiscussionStart deserialization."""
        content = {
            "topic_id": "disc_test",
            "title": "Test",
            "participants": ["did:a"],
            "context": "ctx",
            "consensus": {"mode": "unanimous"},
            "seq": 1,
        }
        start = DiscussionStart.from_content(content)

        assert start.topic_id == "disc_test"
        assert start.consensus.mode == "unanimous"

    def test_discussion_reply_to_content(self):
        """Test DiscussionReply serialization."""
        reply = DiscussionReply(
            topic_id="disc_test",
            content="I agree with this proposal",
            reply_to=42,
            mentions=["did:other"],
            request_escalate=False,
            seq=2,
        )
        content = reply.to_content()

        assert content["topic_id"] == "disc_test"
        assert content["content"] == "I agree with this proposal"
        assert content["reply_to"] == 42
        assert content["mentions"] == ["did:other"]
        assert "request_escalate" not in content  # False is not included

    def test_discussion_reply_with_escalate(self):
        """Test DiscussionReply with escalation request."""
        reply = DiscussionReply(
            topic_id="disc_test",
            content="We need to escalate",
            request_escalate=True,
        )
        content = reply.to_content()

        assert content["request_escalate"] is True

    def test_discussion_vote_to_content(self):
        """Test DiscussionVote serialization."""
        vote = DiscussionVote(
            topic_id="disc_test",
            vote="approve",
            reason="Looks good to me",
            seq=3,
        )
        content = vote.to_content()

        assert content["vote"] == "approve"
        assert content["reason"] == "Looks good to me"

    def test_discussion_conclude_to_content(self):
        """Test DiscussionConclude serialization."""
        conclude = DiscussionConclude(
            topic_id="disc_test",
            conclusion="Approved with minor changes",
            conclusion_type=ConclusionType.CONSENSUS,
            action_items=[
                ActionItem(type="update_document", ref="adr-011", description="Update spec"),
            ],
        )
        content = conclude.to_content()

        assert content["conclusion"] == "Approved with minor changes"
        assert content["conclusion_type"] == "consensus"
        assert len(content["action_items"]) == 1
        assert content["action_items"][0]["ref"] == "adr-011"


class TestDiscussionStateMachine:
    """Tests for discussion state machine."""

    @pytest.fixture
    def simple_discussion(self):
        """Create a simple discussion without consensus."""
        start = DiscussionStart(
            topic_id="disc_simple",
            title="Simple Discussion",
            participants=["did:initiator", "did:participant"],
        )
        return DiscussionStateMachine(start, "did:initiator")

    @pytest.fixture
    def majority_discussion(self):
        """Create a discussion with majority consensus."""
        consensus = Consensus(mode=ConsensusMode.MAJORITY)
        start = DiscussionStart(
            topic_id="disc_majority",
            title="Majority Vote",
            participants=["did:a", "did:b", "did:c"],
            consensus=consensus,
        )
        return DiscussionStateMachine(start, "did:a")

    @pytest.fixture
    def unanimous_discussion(self):
        """Create a discussion with unanimous consensus."""
        consensus = Consensus(mode=ConsensusMode.UNANIMOUS)
        start = DiscussionStart(
            topic_id="disc_unanimous",
            title="Unanimous Vote",
            participants=["did:a", "did:b"],
            consensus=consensus,
        )
        return DiscussionStateMachine(start, "did:a")

    @pytest.fixture
    def leader_discussion(self):
        """Create a discussion with leader_decides consensus."""
        consensus = Consensus(
            mode=ConsensusMode.LEADER_DECIDES,
            leader_did="did:leader",
        )
        start = DiscussionStart(
            topic_id="disc_leader",
            title="Leader Decides",
            participants=["did:a", "did:b", "did:leader"],
            consensus=consensus,
        )
        return DiscussionStateMachine(start, "did:a")

    def test_initial_state(self, simple_discussion):
        """Test initial state is open."""
        assert simple_discussion.state == DiscussionState.OPEN
        assert not simple_discussion.is_concluded

    def test_record_message_id(self, simple_discussion):
        """Test message ID recording for reply_to validation."""
        simple_discussion.record_message_id(1)
        simple_discussion.record_message_id(2)

        is_valid, status = simple_discussion.validate_reply_to(1)
        assert is_valid
        assert status == "valid"

        is_valid, status = simple_discussion.validate_reply_to(999)
        assert not is_valid
        assert status == "unverified_ref"

        is_valid, status = simple_discussion.validate_reply_to(None)
        assert is_valid
        assert status == "none"

    def test_add_vote(self, majority_discussion):
        """Test adding votes."""
        result = majority_discussion.add_vote("did:a", "approve")
        assert result
        assert majority_discussion.state == DiscussionState.VOTING

    def test_add_vote_after_conclude(self, majority_discussion):
        """Test voting after discussion concluded."""
        majority_discussion.conclude()
        result = majority_discussion.add_vote("did:a", "approve")
        assert not result

    def test_majority_consensus_reached(self, majority_discussion):
        """Test majority consensus detection."""
        # 2 out of 3 approve -> majority
        majority_discussion.add_vote("did:a", "approve")
        majority_discussion.add_vote("did:b", "approve")
        majority_discussion.add_vote("did:c", "reject")

        result = majority_discussion.check_consensus()
        assert result == "approve"

    def test_majority_consensus_not_reached(self, majority_discussion):
        """Test no consensus when tied."""
        # 1 approve, 1 reject, 1 abstain -> no majority
        majority_discussion.add_vote("did:a", "approve")
        majority_discussion.add_vote("did:b", "reject")
        majority_discussion.add_vote("did:c", "abstain")

        result = majority_discussion.check_consensus()
        assert result is None

    def test_unanimous_consensus_approve(self, unanimous_discussion):
        """Test unanimous approval."""
        unanimous_discussion.add_vote("did:a", "approve")
        unanimous_discussion.add_vote("did:b", "approve")

        result = unanimous_discussion.check_consensus()
        assert result == "approve"

    def test_unanimous_consensus_reject(self, unanimous_discussion):
        """Test unanimous rejection when one rejects."""
        unanimous_discussion.add_vote("did:a", "approve")
        unanimous_discussion.add_vote("did:b", "reject")

        result = unanimous_discussion.check_consensus()
        assert result == "reject"

    def test_leader_decides(self, leader_discussion):
        """Test leader decides consensus."""
        # Non-leader votes don't determine outcome
        leader_discussion.add_vote("did:a", "approve")
        result = leader_discussion.check_consensus()
        assert result is None

        # Leader's vote decides
        leader_discussion.add_vote("did:leader", "reject")
        result = leader_discussion.check_consensus()
        assert result == "reject"

    def test_conclude(self, simple_discussion):
        """Test concluding discussion."""
        simple_discussion.conclude()

        assert simple_discussion.is_concluded
        assert simple_discussion.state == DiscussionState.CONCLUDED

    def test_get_next_seq(self, simple_discussion):
        """Test sequence number generation."""
        seq1 = simple_discussion.get_next_seq()
        seq2 = simple_discussion.get_next_seq()
        seq3 = simple_discussion.get_next_seq()

        assert seq1 == 1
        assert seq2 == 2
        assert seq3 == 3

    def test_get_remaining_timeout(self, majority_discussion):
        """Test timeout calculation."""
        # No timeout set
        assert majority_discussion.get_remaining_timeout() is None

    def test_get_remaining_timeout_with_timeout(self):
        """Test timeout calculation with actual timeout."""
        consensus = Consensus(
            mode=ConsensusMode.MAJORITY,
            timeout_seconds=300,
        )
        start = DiscussionStart(
            topic_id="disc_timeout",
            title="Timeout Test",
            participants=["did:a"],
            consensus=consensus,
        )
        sm = DiscussionStateMachine(start, "did:a")

        remaining = sm.get_remaining_timeout()
        assert remaining is not None
        assert remaining > 0
        assert remaining <= 300

    def test_vote_state_persistence(self, majority_discussion):
        """Test vote state can be serialized for persistence."""
        majority_discussion.add_vote("did:a", "approve")
        majority_discussion.add_vote("did:b", "reject")

        state_content = majority_discussion.get_vote_state_content()

        assert state_content["topic_id"] == "disc_majority"
        assert state_content["votes"]["did:a"] == "approve"
        assert state_content["votes"]["did:b"] == "reject"
        assert state_content["status"] == "voting"


class TestConsensusModel:
    """Tests for Consensus model."""

    def test_basic_consensus(self):
        """Test basic consensus without optional fields."""
        consensus = Consensus(mode=ConsensusMode.MAJORITY)
        data = consensus.to_dict()

        assert data["mode"] == "majority"
        assert "leader_did" not in data

    def test_full_consensus(self):
        """Test consensus with all fields."""
        consensus = Consensus(
            mode=ConsensusMode.LEADER_DECIDES,
            leader_did="did:leader",
            timeout_seconds=600,
            timeout_action=TimeoutAction.ESCALATE,
        )
        data = consensus.to_dict()

        assert data["mode"] == "leader_decides"
        assert data["leader_did"] == "did:leader"
        assert data["timeout_seconds"] == 600
        assert data["timeout_action"] == "escalate"

    def test_consensus_roundtrip(self):
        """Test consensus serialization roundtrip."""
        original = Consensus(
            mode=ConsensusMode.UNANIMOUS,
            timeout_seconds=300,
        )
        data = original.to_dict()
        restored = Consensus.from_dict(data)

        assert restored.mode == original.mode
        assert restored.timeout_seconds == original.timeout_seconds


class TestActionItem:
    """Tests for ActionItem model."""

    def test_action_item_basic(self):
        """Test basic action item."""
        item = ActionItem(
            type="create_task",
            description="Implement feature X",
        )
        data = item.to_dict()

        assert data["type"] == "create_task"
        assert data["description"] == "Implement feature X"
        assert "ref" not in data

    def test_action_item_with_ref(self):
        """Test action item with reference."""
        item = ActionItem(
            type="update_document",
            ref="adr-011",
            description="Update discussion protocol",
        )
        data = item.to_dict()

        assert data["ref"] == "adr-011"

    def test_action_item_roundtrip(self):
        """Test action item serialization roundtrip."""
        original = ActionItem(
            type="update_document",
            ref="adr-007",
            description="Update spec",
        )
        data = original.to_dict()
        restored = ActionItem.from_dict(data)

        assert restored.type == original.type
        assert restored.ref == original.ref
        assert restored.description == original.description


class TestDiscussionStartFanout:
    """Tests for discussion_start fanout to participants."""

    def test_discussion_start_includes_all_participants(self):
        """Test discussion_start content includes all participants."""
        start = DiscussionStart(
            topic_id="disc_test",
            title="Test Discussion",
            participants=["did:a", "did:b", "did:c"],
            context="Test context",
        )
        content = start.to_content()

        assert "participants" in content
        assert len(content["participants"]) == 3
        assert "did:a" in content["participants"]
        assert "did:b" in content["participants"]
        assert "did:c" in content["participants"]

    def test_discussion_start_protocol_and_type(self):
        """Test discussion_start has correct message_type and protocol."""
        start = DiscussionStart(
            topic_id="disc_test",
            title="Test",
            participants=["did:a"],
        )
        # Message type should be "discussion_start"
        # Protocol should be "nexus_v1"
        content = start.to_content()
        assert content["topic_id"].startswith("disc_")


class TestDiscussionReplyMentions:
    """Tests for discussion_reply with mentions and reply_to."""

    def test_reply_with_mentions(self):
        """Test reply_to and mentions are correctly passed."""
        reply = DiscussionReply(
            topic_id="disc_test",
            content="I agree with @did:b",
            reply_to=42,
            mentions=["did:b", "did:c"],
        )
        content = reply.to_content()

        assert content["reply_to"] == 42
        assert content["mentions"] == ["did:b", "did:c"]

    def test_reply_without_mentions(self):
        """Test reply without mentions omits field."""
        reply = DiscussionReply(
            topic_id="disc_test",
            content="Simple reply",
        )
        content = reply.to_content()

        assert "mentions" not in content
        assert "reply_to" not in content

    def test_reply_from_content_with_mentions(self):
        """Test deserialization of reply with mentions."""
        content = {
            "topic_id": "disc_test",
            "content": "Reply text",
            "reply_to": 10,
            "mentions": ["did:x"],
            "seq": 2,
        }
        reply = DiscussionReply.from_content(content)

        assert reply.reply_to == 10
        assert reply.mentions == ["did:x"]


class TestConsensusTimeout:
    """Tests for consensus timeout triggering timeout_action."""

    def test_timeout_action_auto_approve(self):
        """Test timeout_action auto_approve is set correctly."""
        consensus = Consensus(
            mode=ConsensusMode.MAJORITY,
            timeout_seconds=60,
            timeout_action=TimeoutAction.AUTO_APPROVE,
        )
        data = consensus.to_dict()

        assert data["timeout_action"] == "auto_approve"

    def test_timeout_action_auto_reject(self):
        """Test timeout_action auto_reject is set correctly."""
        consensus = Consensus(
            mode=ConsensusMode.UNANIMOUS,
            timeout_seconds=120,
            timeout_action=TimeoutAction.AUTO_REJECT,
        )
        data = consensus.to_dict()

        assert data["timeout_action"] == "auto_reject"

    def test_timeout_action_escalate(self):
        """Test timeout_action escalate is set correctly."""
        consensus = Consensus(
            mode=ConsensusMode.LEADER_DECIDES,
            leader_did="did:leader",
            timeout_seconds=300,
            timeout_action=TimeoutAction.ESCALATE,
        )
        data = consensus.to_dict()

        assert data["timeout_action"] == "escalate"

    def test_get_remaining_timeout_decreases(self):
        """Test remaining timeout decreases over time."""
        consensus = Consensus(
            mode=ConsensusMode.MAJORITY,
            timeout_seconds=10,
        )
        start = DiscussionStart(
            topic_id="disc_timeout",
            title="Test",
            participants=["did:a"],
            consensus=consensus,
        )
        sm = DiscussionStateMachine(start, "did:a")

        remaining1 = sm.get_remaining_timeout()
        time.sleep(0.1)
        remaining2 = sm.get_remaining_timeout()

        assert remaining1 is not None
        assert remaining2 is not None
        assert remaining2 < remaining1


class TestFallbackToOnMessage:
    """Tests for unregistered discussion callbacks falling back to on_message."""

    def test_discussion_message_type_values(self):
        """Test discussion message types are correctly defined."""
        from agentnexus.discussion import DiscussionMessageType

        assert DiscussionMessageType.START == "discussion_start"
        assert DiscussionMessageType.REPLY == "discussion_reply"
        assert DiscussionMessageType.VOTE == "discussion_vote"
        assert DiscussionMessageType.CONCLUDE == "discussion_conclude"

    def test_discussion_start_can_be_parsed_as_generic_message(self):
        """Test discussion_start can be handled as generic message."""
        start = DiscussionStart(
            topic_id="disc_test",
            title="Test",
            participants=["did:a"],
        )
        content = start.to_content()

        # Simulate parsing as generic message
        assert "topic_id" in content
        assert "title" in content
        assert content["topic_id"].startswith("disc_")


class TestConclusionNoConsensus:
    """Tests for conclusion_type no_consensus."""

    def test_conclusion_type_no_consensus(self):
        """Test conclusion with no_consensus type."""
        conclude = DiscussionConclude(
            topic_id="disc_test",
            conclusion="Design Agent wants optional, Dev Agent wants required",
            conclusion_type=ConclusionType.NO_CONSENSUS,
        )
        content = conclude.to_content()

        assert content["conclusion_type"] == "no_consensus"

    def test_conclusion_type_escalated(self):
        """Test conclusion with escalated type."""
        conclude = DiscussionConclude(
            topic_id="disc_test",
            conclusion="Escalated to human decision",
            conclusion_type=ConclusionType.ESCALATED,
        )
        content = conclude.to_content()

        assert content["conclusion_type"] == "escalated"

    def test_conclusion_with_action_items_records_positions(self):
        """Test conclusion records positions via action_items."""
        conclude = DiscussionConclude(
            topic_id="disc_test",
            conclusion="No consensus reached, positions recorded",
            conclusion_type=ConclusionType.NO_CONSENSUS,
            action_items=[
                ActionItem(
                    type="record_position",
                    ref="design-agent",
                    description="Position: make field optional",
                ),
                ActionItem(
                    type="record_position",
                    ref="dev-agent",
                    description="Position: keep field required",
                ),
            ],
        )
        content = conclude.to_content()

        assert len(content["action_items"]) == 2
        assert content["action_items"][0]["ref"] == "design-agent"
        assert content["action_items"][1]["ref"] == "dev-agent"


class TestRequestEscalate:
    """Tests for request_escalate triggering escalation."""

    def test_reply_with_request_escalate(self):
        """Test reply can request escalation."""
        reply = DiscussionReply(
            topic_id="disc_test",
            content="We've discussed 3 rounds with no progress",
            request_escalate=True,
        )
        content = reply.to_content()

        assert content["request_escalate"] is True

    def test_reply_without_request_escalate(self):
        """Test reply without escalation omits field."""
        reply = DiscussionReply(
            topic_id="disc_test",
            content="Normal reply",
            request_escalate=False,
        )
        content = reply.to_content()

        # False should not be included
        assert "request_escalate" not in content

    def test_from_content_with_request_escalate(self):
        """Test deserialization preserves request_escalate."""
        content = {
            "topic_id": "disc_test",
            "content": "Need escalation",
            "request_escalate": True,
            "seq": 5,
        }
        reply = DiscussionReply.from_content(content)

        assert reply.request_escalate is True


class TestRelatedTaskId:
    """Tests for related_task_id association and query."""

    def test_discussion_start_with_related_task(self):
        """Test discussion_start includes related_task_id."""
        start = DiscussionStart(
            topic_id="disc_test",
            title="Translation terminology",
            participants=["did:a", "did:b"],
            related_task_id="task_abc123",
        )
        content = start.to_content()

        assert content["related_task_id"] == "task_abc123"

    def test_discussion_start_without_related_task(self):
        """Test discussion_start without related_task omits field."""
        start = DiscussionStart(
            topic_id="disc_test",
            title="General discussion",
            participants=["did:a"],
        )
        content = start.to_content()

        assert "related_task_id" not in content

    def test_from_content_with_related_task(self):
        """Test deserialization preserves related_task_id."""
        content = {
            "topic_id": "disc_test",
            "title": "Test",
            "participants": ["did:a"],
            "related_task_id": "task_xyz",
            "seq": 1,
        }
        start = DiscussionStart.from_content(content)

        assert start.related_task_id == "task_xyz"

    def test_state_machine_preserves_related_task(self):
        """Test state machine stores related_task_id."""
        start = DiscussionStart(
            topic_id="disc_test",
            title="Test",
            participants=["did:a"],
            related_task_id="task_123",
        )
        sm = DiscussionStateMachine(start, "did:initiator")

        assert sm.related_task_id == "task_123"


class TestSeqOrdering:
    """Tests for seq ordering in multi-party discussions."""

    def test_seq_increments_for_each_message(self):
        """Test seq increments for each message in topic."""
        start = DiscussionStart(
            topic_id="disc_seq",
            title="Test",
            participants=["did:a", "did:b"],
        )
        sm = DiscussionStateMachine(start, "did:a")

        seq1 = sm.get_next_seq()
        seq2 = sm.get_next_seq()
        seq3 = sm.get_next_seq()

        assert seq1 == 1
        assert seq2 == 2
        assert seq3 == 3

    def test_discussion_start_seq_defaults_to_one(self):
        """Test discussion_start seq defaults to 1."""
        start = DiscussionStart(
            topic_id="disc_test",
            title="Test",
            participants=["did:a"],
        )
        content = start.to_content()

        assert content["seq"] == 1

    def test_custom_seq_in_start(self):
        """Test custom seq can be set in discussion_start."""
        start = DiscussionStart(
            topic_id="disc_test",
            title="Test",
            participants=["did:a"],
            seq=5,
        )
        content = start.to_content()

        assert content["seq"] == 5

    def test_vote_includes_seq(self):
        """Test vote message includes seq."""
        vote = DiscussionVote(
            topic_id="disc_test",
            vote="approve",
            seq=3,
        )
        content = vote.to_content()

        assert content["seq"] == 3

    def test_conclude_includes_seq(self):
        """Test conclude message includes seq."""
        conclude = DiscussionConclude(
            topic_id="disc_test",
            conclusion="Done",
            seq=10,
        )
        content = conclude.to_content()

        assert content["seq"] == 10
