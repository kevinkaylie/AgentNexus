"""
Tests for Action Layer (ADR-007)
"""
import pytest

from agentnexus.actions import (
    TaskPropose,
    TaskClaim,
    ResourceSync,
    StateNotify,
    TaskStatus,
    TaskStateMachine,
    ActionType,
    PROTOCOL_NEXUS_V1,
)


class TestTaskPropose:
    """Tests for TaskPropose action."""

    def test_basic_propose(self):
        """Test basic task proposal."""
        task = TaskPropose(
            task_id="task_001",
            title="Implement feature",
        )
        content = task.to_content()

        assert content["task_id"] == "task_001"
        assert content["title"] == "Implement feature"
        assert "description" not in content

    def test_full_propose(self):
        """Test task proposal with all fields."""
        task = TaskPropose(
            task_id="task_002",
            title="Complex task",
            description="Detailed description",
            deadline="2026-05-01",
            required_caps=["python", "async"],
            priority="high",
        )
        content = task.to_content()

        assert content["description"] == "Detailed description"
        assert content["deadline"] == "2026-05-01"
        assert content["required_caps"] == ["python", "async"]
        assert content["priority"] == "high"

    def test_propose_roundtrip(self):
        """Test task proposal serialization roundtrip."""
        original = TaskPropose(
            task_id="task_003",
            title="Test",
            description="Desc",
        )
        content = original.to_content()
        restored = TaskPropose.from_content(content)

        assert restored.task_id == original.task_id
        assert restored.title == original.title
        assert restored.description == original.description


class TestTaskClaim:
    """Tests for TaskClaim action."""

    def test_basic_claim(self):
        """Test basic task claim."""
        claim = TaskClaim(task_id="task_001")
        content = claim.to_content()

        assert content["task_id"] == "task_001"
        assert "eta" not in content

    def test_claim_with_message(self):
        """Test task claim with message."""
        claim = TaskClaim(
            task_id="task_001",
            eta="2 hours",
            message="I'll handle this",
        )
        content = claim.to_content()

        assert content["eta"] == "2 hours"
        assert content["message"] == "I'll handle this"


class TestResourceSync:
    """Tests for ResourceSync action."""

    def test_basic_sync(self):
        """Test basic resource sync."""
        sync = ResourceSync(
            key="config",
            value={"debug": True},
        )
        content = sync.to_content()

        assert content["key"] == "config"
        assert content["value"] == {"debug": True}

    def test_sync_with_version(self):
        """Test resource sync with version."""
        sync = ResourceSync(
            key="data",
            value=[1, 2, 3],
            version="v1.2.3",
        )
        content = sync.to_content()

        assert content["version"] == "v1.2.3"


class TestStateNotify:
    """Tests for StateNotify action."""

    def test_basic_notify(self):
        """Test basic state notification."""
        notify = StateNotify(status="completed")
        content = notify.to_content()

        assert content["status"] == "completed"

    def test_notify_with_progress(self):
        """Test state notification with progress."""
        notify = StateNotify(
            task_id="task_001",
            status="in_progress",
            progress=0.5,
        )
        content = notify.to_content()

        assert content["task_id"] == "task_001"
        assert content["progress"] == 0.5

    def test_notify_error(self):
        """Test state notification with error."""
        notify = StateNotify(
            status="failed",
            error="Connection timeout",
        )
        content = notify.to_content()

        assert content["status"] == "failed"
        assert content["error"] == "Connection timeout"

    def test_is_terminal(self):
        """Test terminal state detection."""
        assert StateNotify(status="completed").is_terminal()
        assert StateNotify(status="failed").is_terminal()
        assert not StateNotify(status="in_progress").is_terminal()


class TestTaskStateMachine:
    """Tests for TaskStateMachine."""

    def test_initial_state(self):
        """Test initial state is pending."""
        sm = TaskStateMachine()
        assert sm.status == TaskStatus.PENDING

    def test_valid_transition_pending_to_in_progress(self):
        """Test valid transition from pending to in_progress."""
        sm = TaskStateMachine()
        result = sm.transition(TaskStatus.IN_PROGRESS)

        assert result
        assert sm.status == TaskStatus.IN_PROGRESS

    def test_valid_transition_in_progress_to_completed(self):
        """Test valid transition from in_progress to completed."""
        sm = TaskStateMachine(TaskStatus.IN_PROGRESS)
        result = sm.transition(TaskStatus.COMPLETED)

        assert result
        assert sm.status == TaskStatus.COMPLETED

    def test_invalid_transition_pending_to_completed(self):
        """Test invalid direct transition from pending to completed."""
        sm = TaskStateMachine()
        result = sm.transition(TaskStatus.COMPLETED)

        assert not result
        assert sm.status == TaskStatus.PENDING

    def test_terminal_state(self):
        """Test terminal state detection."""
        sm = TaskStateMachine(TaskStatus.COMPLETED)
        assert sm.is_terminal()

        sm = TaskStateMachine(TaskStatus.FAILED)
        assert sm.is_terminal()

    def test_blocked_recovery(self):
        """Test recovery from blocked state."""
        sm = TaskStateMachine(TaskStatus.BLOCKED)
        result = sm.transition(TaskStatus.IN_PROGRESS)

        assert result
        assert sm.status == TaskStatus.IN_PROGRESS

    def test_no_transition_from_terminal(self):
        """Test no transitions from terminal states."""
        sm = TaskStateMachine(TaskStatus.COMPLETED)
        result = sm.transition(TaskStatus.IN_PROGRESS)

        assert not result
        assert sm.status == TaskStatus.COMPLETED


class TestActionType:
    """Tests for ActionType enum."""

    def test_action_types(self):
        """Test action type values."""
        assert ActionType.TASK_PROPOSE == "task_propose"
        assert ActionType.TASK_CLAIM == "task_claim"
        assert ActionType.RESOURCE_SYNC == "resource_sync"
        assert ActionType.STATE_NOTIFY == "state_notify"

    def test_protocol_constant(self):
        """Test protocol constant."""
        assert PROTOCOL_NEXUS_V1 == "nexus_v1"
