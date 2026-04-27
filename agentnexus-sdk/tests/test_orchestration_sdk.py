"""
Tests for the orchestration SDK facades.
"""
from types import SimpleNamespace

import pytest

from agentnexus.actions import ActionMessage, StateNotify
from agentnexus.enclave import EnclaveManager, VaultProxy
from agentnexus.owner import OwnerClient
from agentnexus.secretary import SecretaryClient
from agentnexus.team import TeamClient
from agentnexus.worker import WorkerRuntime, StageContext
from agentnexus.runs import RunClient, RunStatus, IntakeInfo


class FakeClient:
    def __init__(self, *, fail_bind: bool = False):
        self.agent_info = SimpleNamespace(did="did:agentnexus:actor")
        self.requests = []
        self.notifications = []
        self.fail_bind = fail_bind
        self.owner = OwnerClient(self)
        self.team = TeamClient(self)
        self.secretary = SecretaryClient(self)
        self.runs = RunClient(self)
        self.enclaves = EnclaveManager(self)
        self.worker = WorkerRuntime(self)

    async def _request(self, method, path, *, json=None, params=None, auth=True):
        self.requests.append(
            {
                "method": method,
                "path": path,
                "json": json,
                "params": params,
                "auth": auth,
            }
        )
        if path == "/owner/register":
            return {"did": "did:agentnexus:owner", "public_key_hex": "abc", "profile": {"name": "Owner"}}
        if path == "/agents/register":
            return {"did": "did:agentnexus:secretary", "profile": {"name": "Secretary"}}
        if path == "/owner/bind":
            if self.fail_bind:
                raise RuntimeError("bind failed")
            return {"status": "ok"}
        if path == "/agents/did:agentnexus:secretary" and method == "DELETE":
            return {"status": "ok", "deleted": True}
        if path == "/secretary/dispatch":
            return {
                "status": "dispatched",
                "session_id": json["session_id"],
                "run_id": "run_1",
                "enclave_id": "enc_1",
                "selected_workers": {"developer": "did:agentnexus:worker"},
            }
        if path == "/owner/workers/v2/did:agentnexus:owner":
            return {
                "workers": [
                    {
                        "did": "did:agentnexus:worker",
                        "owner_did": "did:agentnexus:owner",
                        "worker_type": "resident",
                        "presence": "available",
                    }
                ]
            }
        if path == "/enclaves":
            return {"enclave_id": "enc_1"}
        if path == "/enclaves/enc_1":
            return {
                "enclave_id": "enc_1",
                "name": "Project",
                "owner_did": "did:agentnexus:owner",
                "status": "active",
                "vault_backend": "local",
            }
        if path == "/enclaves/enc_1/vault/spec.md":
            return {
                "key": "spec.md",
                "value": "ok",
                "version": "1",
                "updated_by": "did:agentnexus:actor",
                "updated_at": 1.0,
            }
        return {"status": "ok"}

    async def notify_state(self, **kwargs):
        self.notifications.append(kwargs)


@pytest.mark.asyncio
async def test_owner_secretary_team_facades_call_daemon_contract():
    client = FakeClient()

    owner = await client.owner.register("Owner")
    secretary = await client.secretary.register(owner.did)
    workers = await client.team.list_workers(owner.did)
    result = await client.secretary.dispatch(
        session_id="sess_1",
        owner_did=owner.did,
        actor_did=secretary.did,
        objective="Implement feature",
        required_roles=["developer"],
    )

    assert owner.did == "did:agentnexus:owner"
    assert secretary.did == "did:agentnexus:secretary"
    assert workers[0].presence == "available"
    assert result.enclave_id == "enc_1"
    assert client.requests[0]["path"] == "/owner/register"
    assert any(req["path"] == "/owner/bind" for req in client.requests)
    assert client.requests[-1]["json"]["actor_did"] == secretary.did


@pytest.mark.asyncio
async def test_enclave_create_passes_owner_and_actor_did():
    client = FakeClient()

    enclave = await client.enclaves.create(
        "Project",
        {"developer": {"did": "did:agentnexus:worker"}},
        owner_did="did:agentnexus:owner",
        actor_did="did:agentnexus:secretary",
    )

    create_request = client.requests[0]
    get_request = client.requests[1]
    assert enclave.enclave_id == "enc_1"
    assert create_request["json"]["owner_did"] == "did:agentnexus:owner"
    assert create_request["json"]["actor_did"] == "did:agentnexus:secretary"
    assert get_request["params"]["actor_did"] == "did:agentnexus:secretary"


@pytest.mark.asyncio
async def test_secretary_register_rolls_back_orphan_agent_on_bind_failure():
    client = FakeClient(fail_bind=True)

    with pytest.raises(RuntimeError, match="bind failed"):
        await client.secretary.register("did:agentnexus:owner")

    assert client.requests[-1] == {
        "method": "DELETE",
        "path": "/agents/did:agentnexus:secretary",
        "json": None,
        "params": {"actor_did": "did:agentnexus:secretary"},
        "auth": True,
    }


@pytest.mark.asyncio
async def test_vault_read_uses_actor_did_query():
    client = FakeClient()
    vault = VaultProxy(client, "enc_1", actor_did="did:agentnexus:secretary")

    entry = await vault.get("spec.md")

    assert entry.value == "ok"
    assert client.requests[0]["params"]["actor_did"] == "did:agentnexus:secretary"


@pytest.mark.asyncio
async def test_worker_runtime_deliver_sends_artifact_ref():
    client = FakeClient()
    seen = {}

    @client.worker.on_stage("developer")
    async def handle(ctx):
        seen["stage"] = ctx.stage_name
        await ctx.deliver(kind="document", key="result.md", summary="done")

    handled = await client.worker.handle_task_propose(
        ActionMessage(
            from_did="did:agentnexus:secretary",
            message_type="task_propose",
            content={
                "task_id": "task_1",
                "run_id": "run_1",
                "enclave_id": "enc_1",
                "stage_name": "implement",
                "role": "developer",
            },
        )
    )

    assert handled
    assert seen["stage"] == "implement"
    assert client.notifications[0]["output_ref"] == {"enclave_id": "enc_1", "key": "result.md"}


def test_state_notify_roundtrip_with_output_ref():
    notify = StateNotify(
        status="completed",
        task_id="task_1",
        output_ref={"enclave_id": "enc_1", "key": "result.md"},
        context={"summary": "done"},
    )

    restored = StateNotify.from_content(notify.to_content())

    assert restored.output_ref == {"enclave_id": "enc_1", "key": "result.md"}
    assert restored.context == {"summary": "done"}


# ── Additional test cases from design doc §14 ─────────────────────


@pytest.mark.asyncio
async def test_worker_runtime_builds_stage_context():
    """task_propose with run/stage metadata should construct StageContext."""
    client = FakeClient()
    captured_ctx = None

    @client.worker.on_stage("developer")
    async def handle(ctx):
        nonlocal captured_ctx
        captured_ctx = ctx

    handled = await client.worker.handle_task_propose(
        ActionMessage(
            from_did="did:agentnexus:secretary",
            message_type="task_propose",
            content={
                "task_id": "task_1",
                "run_id": "run_1",
                "enclave_id": "enc_1",
                "stage_name": "implement",
                "role": "developer",
                "context_snapshot": {"req": "login module"},
            },
        )
    )

    assert handled
    assert captured_ctx is not None
    assert captured_ctx.task_id == "task_1"
    assert captured_ctx.run_id == "run_1"
    assert captured_ctx.enclave_id == "enc_1"
    assert captured_ctx.stage_name == "implement"
    assert captured_ctx.role == "developer"
    assert captured_ctx.context_snapshot == {"req": "login module"}
    assert captured_ctx.from_did == "did:agentnexus:secretary"
    assert captured_ctx.assigned_did == "did:agentnexus:actor"


@pytest.mark.asyncio
async def test_stage_context_deliver():
    """deliver() should write to Vault first, then notify completed."""
    client = FakeClient()

    @client.worker.on_stage("developer")
    async def handle(ctx):
        await ctx.deliver(
            kind="design_doc",
            key="design/spec.md",
            value="# Spec",
            summary="完成登录模块设计",
        )

    await client.worker.handle_task_propose(
        ActionMessage(
            from_did="did:agentnexus:secretary",
            message_type="task_propose",
            content={
                "task_id": "task_1",
                "run_id": "run_1",
                "enclave_id": "enc_1",
                "stage_name": "design",
                "role": "developer",
            },
        )
    )

    # Vault put should have been called (captured in requests)
    vault_puts = [r for r in client.requests if r["path"] == "/enclaves/enc_1/vault/design/spec.md"]
    assert len(vault_puts) == 1
    assert vault_puts[0]["json"]["value"] == "# Spec"
    assert vault_puts[0]["json"]["message"] == "完成登录模块设计"

    # notify_state should have been called with output_ref
    assert len(client.notifications) == 1
    assert client.notifications[0]["status"] == "completed"
    assert client.notifications[0]["output_ref"] == {"enclave_id": "enc_1", "key": "design/spec.md"}


@pytest.mark.asyncio
async def test_stage_context_reject():
    """reject() should notify with rejected status and reason."""
    client = FakeClient()

    @client.worker.on_stage("reviewer")
    async def handle(ctx):
        await ctx.reject(reason="测试未通过，需要补充边界用例")

    await client.worker.handle_task_propose(
        ActionMessage(
            from_did="did:agentnexus:secretary",
            message_type="task_propose",
            content={
                "task_id": "task_1",
                "run_id": "run_1",
                "enclave_id": "enc_1",
                "stage_name": "review",
                "role": "reviewer",
            },
        )
    )

    assert len(client.notifications) == 1
    assert client.notifications[0]["status"] == "rejected"
    assert client.notifications[0]["reason"] == "测试未通过，需要补充边界用例"


@pytest.mark.asyncio
async def test_team_list_workers_v2_params():
    """role/presence params should be correctly passed to v2 endpoint."""
    client = FakeClient()

    workers = await client.team.list_workers(
        "did:agentnexus:owner",
        actor_did="did:agentnexus:admin",
        role="developer",
        presence="available",
    )

    req = client.requests[0]
    assert req["path"] == "/owner/workers/v2/did:agentnexus:owner"
    assert req["params"]["role"] == "developer"
    assert req["params"]["presence"] == "available"
    assert req["params"]["actor_did"] == "did:agentnexus:admin"
    assert len(workers) == 1


@pytest.mark.asyncio
async def test_team_worker_mutation_uses_query_params():
    """Worker mutation endpoints are FastAPI scalar params, so SDK must use query params."""
    client = FakeClient()

    await client.team.set_blocked(
        "did:agentnexus:worker",
        True,
        actor_did="did:agentnexus:owner",
        reason="quota exceeded",
    )
    await client.team.set_worker_type(
        "did:agentnexus:worker",
        "interactive_cli",
        actor_did="did:agentnexus:owner",
    )

    blocked_req = client.requests[-2]
    assert blocked_req["method"] == "PATCH"
    assert blocked_req["path"] == "/workers/did:agentnexus:worker/blocked"
    assert blocked_req["json"] is None
    assert blocked_req["params"] == {
        "blocked": True,
        "actor_did": "did:agentnexus:owner",
        "reason": "quota exceeded",
    }

    worker_type_req = client.requests[-1]
    assert worker_type_req["method"] == "PATCH"
    assert worker_type_req["path"] == "/agents/did:agentnexus:worker/worker-type"
    assert worker_type_req["json"] is None
    assert worker_type_req["params"] == {
        "worker_type": "interactive_cli",
        "actor_did": "did:agentnexus:owner",
    }


@pytest.mark.asyncio
async def test_secretary_dispatch_payload():
    """Dispatch payload should be complete and return DispatchResult."""
    client = FakeClient()

    result = await client.secretary.dispatch(
        session_id="sess_test",
        owner_did="did:agentnexus:owner",
        actor_did="did:agentnexus:secretary",
        objective="Test objective",
        required_roles=["developer", "reviewer"],
        entry_mode="owner_pre_authorized",
        source={"channel": "webhook", "message_ref": "msg_42"},
    )

    req = client.requests[-1]
    assert req["path"] == "/secretary/dispatch"
    assert req["json"]["session_id"] == "sess_test"
    assert req["json"]["owner_did"] == "did:agentnexus:owner"
    assert req["json"]["actor_did"] == "did:agentnexus:secretary"
    assert req["json"]["objective"] == "Test objective"
    assert req["json"]["required_roles"] == ["developer", "reviewer"]
    assert req["json"]["entry_mode"] == "owner_pre_authorized"
    assert req["json"]["source"] == {"channel": "webhook", "message_ref": "msg_42"}

    assert result.status == "dispatched"
    assert result.session_id == "sess_test"
    assert result.run_id == "run_1"
    assert result.enclave_id == "enc_1"
    assert result.selected_workers == {"developer": "did:agentnexus:worker"}


@pytest.mark.asyncio
async def test_sdk_owner_abort():
    """SDK abort should call the correct endpoint with actor_did and reason."""
    client = FakeClient()

    await client.secretary.abort(
        session_id="sess_1",
        actor_did="did:agentnexus:owner",
        reason="需求变更，终止",
    )

    req = client.requests[-1]
    assert req["path"] == "/secretary/intake/sess_1/abort"
    assert req["json"]["actor_did"] == "did:agentnexus:owner"
    assert req["json"]["reason"] == "需求变更，终止"


def test_legacy_notify_state_without_output_ref():
    """Legacy notify_state calls without output_ref should still work."""
    notify = StateNotify(
        status="in_progress",
        task_id="task_1",
        progress=0.5,
    )

    content = notify.to_content()
    assert "output_ref" not in content
    assert "reason" not in content
    assert "context" not in content
    assert content["status"] == "in_progress"
    assert content["task_id"] == "task_1"
    assert content["progress"] == 0.5


def test_run_status_from_dict():
    """RunStatus should parse correctly from Daemon response."""
    data = {
        "run_id": "run_42",
        "enclave_id": "enc_1",
        "playbook_name": "default",
        "current_stage": "implement",
        "run_status": "running",
        "stages": {"design": "completed", "implement": "running"},
        "started_at": 1711000000.0,
    }
    status = RunStatus.from_dict(data)
    assert status.run_id == "run_42"
    assert status.status == "running"
    assert status.stages == {"design": "completed", "implement": "running"}


def test_intake_info_from_dict_nested():
    """IntakeInfo.from_dict should handle both nested and flat intake data."""
    # Nested format (as returned by get_intake)
    nested = {
        "intake": {
            "session_id": "sess_1",
            "owner_did": "did:agentnexus:owner",
            "actor_did": "did:agentnexus:secretary",
            "status": "running",
            "objective": "Test",
            "required_roles": ["developer"],
            "selected_workers": {"developer": "did:agentnexus:worker"},
            "run_id": "run_1",
        }
    }
    info = IntakeInfo.from_dict(nested)
    assert info.session_id == "sess_1"
    assert info.run_id == "run_1"
    assert info.selected_workers == {"developer": "did:agentnexus:worker"}

    # Flat format
    flat = {
        "session_id": "sess_2",
        "owner_did": "did:agentnexus:owner",
        "actor_did": "did:agentnexus:secretary",
        "status": "pending",
        "objective": "Test 2",
        "required_roles": [],
    }
    info2 = IntakeInfo.from_dict(flat)
    assert info2.session_id == "sess_2"
    assert info2.status == "pending"


@pytest.mark.asyncio
async def test_worker_runtime_ignores_non_stage_propose():
    """task_propose without run/enclave/stage fields should not trigger stage callback."""
    client = FakeClient()

    @client.worker.on_stage("developer")
    async def handle(ctx):
        raise AssertionError("Stage callback should not be called")

    handled = await client.worker.handle_task_propose(
        ActionMessage(
            from_did="did:agentnexus:peer",
            message_type="task_propose",
            content={
                "task_id": "task_legacy",
                "title": "Legacy task",
            },
        )
    )

    assert handled is False


@pytest.mark.asyncio
async def test_worker_runtime_catches_missing_fields():
    """task_propose with partial run/stage fields should not trigger stage callback."""
    client = FakeClient()

    @client.worker.on_stage("developer")
    async def handle(ctx):
        raise AssertionError("Stage callback should not be called")

    # Missing run_id
    handled = await client.worker.handle_task_propose(
        ActionMessage(
            from_did="did:agentnexus:peer",
            message_type="task_propose",
            content={
                "task_id": "task_x",
                "enclave_id": "enc_1",
                "stage_name": "design",
            },
        )
    )
    assert handled is False


@pytest.mark.asyncio
async def test_stage_context_unbound_rejects():
    """StageContext without _client should raise RuntimeError on deliver/reject."""
    ctx = StageContext(
        task_id="t",
        run_id="r",
        enclave_id="e",
        stage_name="s",
        role="dev",
        from_did="a",
        assigned_did="b",
    )

    with pytest.raises(RuntimeError, match="not bound"):
        await ctx.deliver(kind="doc", key="x.md")

    with pytest.raises(RuntimeError, match="not bound"):
        await ctx.reject(reason="no client")


@pytest.mark.asyncio
async def test_run_client_abort_delegates_to_secretary():
    """runs.abort() should delegate to secretary.abort()."""
    client = FakeClient()

    await client.runs.abort("sess_1", actor_did="did:agentnexus:owner", reason="cancelled")

    req = client.requests[-1]
    assert req["path"] == "/secretary/intake/sess_1/abort"
