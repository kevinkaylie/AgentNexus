"""
Tests for Emergency Controller (ADR-011 Decision 9)
"""
import pytest
import asyncio

from agentnexus.emergency import (
    EmergencyConfig,
    EmergencyController,
    create_emergency_controller,
)


class TestEmergencyConfig:
    """Tests for EmergencyConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = EmergencyConfig()
        assert len(config.authorized_dids) == 0
        assert config.on_emergency is None

    def test_config_with_authorized_dids(self):
        """Test configuration with authorized DIDs."""
        config = EmergencyConfig(
            authorized_dids={"did:agentnexus:z6Mk...secretary"},
        )
        assert "did:agentnexus:z6Mk...secretary" in config.authorized_dids

    def test_config_with_callback(self):
        """Test configuration with callback."""
        cleanup_called = []

        async def cleanup():
            cleanup_called.append(True)

        config = EmergencyConfig(on_emergency=cleanup)
        assert config.on_emergency is not None


class TestEmergencyController:
    """Tests for EmergencyController."""

    @pytest.fixture
    def controller(self):
        """Create a controller with test config."""
        config = EmergencyConfig(
            authorized_dids={
                "did:agentnexus:z6Mk...admin",
                "did:agentnexus:z6Mk...secretary",
            },
        )
        return EmergencyController(config)

    def test_is_authorized_true(self, controller):
        """Test authorization check for authorized DID."""
        assert controller.is_authorized("did:agentnexus:z6Mk...admin")
        assert controller.is_authorized("did:agentnexus:z6Mk...secretary")

    def test_is_authorized_false(self, controller):
        """Test authorization check for unauthorized DID."""
        assert not controller.is_authorized("did:agentnexus:z6Mk...unknown")
        assert not controller.is_authorized("did:agentnexus:z6Mk...attacker")

    def test_is_halted_initial(self, controller):
        """Test initial halted state is False."""
        assert not controller.is_halted

    @pytest.mark.asyncio
    async def test_emergency_halt_from_authorized_did(self, controller):
        """Test emergency_halt from authorized DID triggers halt."""
        content = {
            "status": "emergency_halt",
            "scope": "all",
            "reason": "Token budget exceeded",
        }

        result = await controller.handle_emergency_halt(
            from_did="did:agentnexus:z6Mk...admin",
            content=content,
        )

        assert result["handled"] is True
        assert result["scope"] == "all"
        assert result["reason"] == "Token budget exceeded"
        assert controller.is_halted

    @pytest.mark.asyncio
    async def test_emergency_halt_from_unauthorized_did_ignored(self, controller):
        """Test emergency_halt from unauthorized DID is silently ignored."""
        content = {
            "status": "emergency_halt",
            "scope": "all",
            "reason": "Malicious attempt",
        }

        result = await controller.handle_emergency_halt(
            from_did="did:agentnexus:z6Mk...attacker",
            content=content,
        )

        # Should be silently ignored
        assert result["handled"] is False
        assert result["reason"] == "unauthorized"
        assert not controller.is_halted

    @pytest.mark.asyncio
    async def test_emergency_halt_already_halted(self, controller):
        """Test emergency_halt when already halted."""
        content = {
            "status": "emergency_halt",
            "scope": "all",
            "reason": "First halt",
        }

        # First halt
        await controller.handle_emergency_halt(
            from_did="did:agentnexus:z6Mk...admin",
            content=content,
        )

        # Second halt attempt
        result = await controller.handle_emergency_halt(
            from_did="did:agentnexus:z6Mk...secretary",
            content={"status": "emergency_halt", "scope": "all", "reason": "Second halt"},
        )

        assert result["handled"] is False
        assert result["reason"] == "already_halted"

    @pytest.mark.asyncio
    async def test_emergency_halt_with_callback(self):
        """Test emergency_halt triggers user callback."""
        callback_calls = []

        async def cleanup():
            callback_calls.append("cleanup_done")

        config = EmergencyConfig(
            authorized_dids={"did:agentnexus:z6Mk...admin"},
            on_emergency=cleanup,
        )
        controller = EmergencyController(config)

        await controller.handle_emergency_halt(
            from_did="did:agentnexus:z6Mk...admin",
            content={"status": "emergency_halt", "scope": "all", "reason": "Test"},
        )

        # Callback should have been called
        assert "cleanup_done" in callback_calls

    @pytest.mark.asyncio
    async def test_emergency_halt_callback_sync(self):
        """Test emergency_halt with sync callback."""
        callback_calls = []

        def sync_cleanup():
            callback_calls.append("sync_cleanup")

        config = EmergencyConfig(
            authorized_dids={"did:agentnexus:z6Mk...admin"},
            on_emergency=sync_cleanup,
        )
        controller = EmergencyController(config)

        await controller.handle_emergency_halt(
            from_did="did:agentnexus:z6Mk...admin",
            content={"status": "emergency_halt", "scope": "all", "reason": "Test"},
        )

        assert "sync_cleanup" in callback_calls

    @pytest.mark.asyncio
    async def test_emergency_halt_with_scope_target(self, controller):
        """Test emergency_halt with specific target scope."""
        content = {
            "status": "emergency_halt",
            "scope": "did:agentnexus:z6Mk...target",
            "reason": "Specific agent issue",
        }

        result = await controller.handle_emergency_halt(
            from_did="did:agentnexus:z6Mk...admin",
            content=content,
        )

        assert result["handled"] is True
        assert result["scope"] == "did:agentnexus:z6Mk...target"

    @pytest.mark.asyncio
    async def test_wait_for_halt(self, controller):
        """Test waiting for halt."""
        # Start a task that will trigger halt after delay
        async def trigger_halt():
            await asyncio.sleep(0.1)
            await controller.handle_emergency_halt(
                from_did="did:agentnexus:z6Mk...admin",
                content={"status": "emergency_halt", "scope": "all", "reason": "Test"},
            )

        asyncio.create_task(trigger_halt())

        # Wait for halt
        halted = await controller.wait_for_halt(timeout=1.0)
        assert halted
        assert controller.is_halted

    @pytest.mark.asyncio
    async def test_wait_for_halt_timeout(self, controller):
        """Test wait_for_halt times out if no halt."""
        halted = await controller.wait_for_halt(timeout=0.1)
        assert not halted
        assert not controller.is_halted

    def test_reset(self, controller):
        """Test reset clears halt state."""
        controller._halted = True
        controller._halt_event.set()

        controller.reset()

        assert not controller.is_halted
        assert not controller._halt_event.is_set()


class TestCreateEmergencyController:
    """Tests for create_emergency_controller helper."""

    def test_create_with_list(self):
        """Test creating controller with list of DIDs."""
        controller = create_emergency_controller([
            "did:agentnexus:z6Mk...a",
            "did:agentnexus:z6Mk...b",
        ])

        assert controller.is_authorized("did:agentnexus:z6Mk...a")
        assert controller.is_authorized("did:agentnexus:z6Mk...b")
        assert not controller.is_authorized("did:agentnexus:z6Mk...c")

    def test_create_with_callback(self):
        """Test creating controller with callback."""
        async def cleanup():
            pass

        controller = create_emergency_controller(
            authorized_dids=["did:agentnexus:z6Mk...admin"],
            on_emergency=cleanup,
        )

        assert controller.config.on_emergency is cleanup


class TestEmergencyHaltBroadcastScope:
    """Tests for emergency_halt broadcast scope restrictions."""

    @pytest.fixture
    def controller(self):
        """Create a controller for testing scope."""
        return create_emergency_controller(["did:agentnexus:z6Mk...admin"])

    @pytest.mark.asyncio
    async def test_scope_all(self, controller):
        """Test scope=all is recorded."""
        result = await controller.handle_emergency_halt(
            from_did="did:agentnexus:z6Mk...admin",
            content={"status": "emergency_halt", "scope": "all", "reason": "Test"},
        )
        assert result["scope"] == "all"

    @pytest.mark.asyncio
    async def test_scope_task(self, controller):
        """Test scope=task_{id} is recorded."""
        result = await controller.handle_emergency_halt(
            from_did="did:agentnexus:z6Mk...admin",
            content={
                "status": "emergency_halt",
                "scope": "task_abc123",
                "reason": "Task stuck",
            },
        )
        assert result["scope"] == "task_abc123"

    @pytest.mark.asyncio
    async def test_scope_did(self, controller):
        """Test scope=did:... is recorded."""
        result = await controller.handle_emergency_halt(
            from_did="did:agentnexus:z6Mk...admin",
            content={
                "status": "emergency_halt",
                "scope": "did:agentnexus:z6Mk...target",
                "reason": "Agent issue",
            },
        )
        assert result["scope"] == "did:agentnexus:z6Mk...target"
