"""D-SEC-09: Message Envelope v1 — message_id 持久化测试"""
import pytest
import pytest_asyncio
import uuid

from agent_net.storage import (
    init_db, register_owner, register_agent, bind_agent,
    store_message, fetch_inbox, fetch_session, get_agent,
)
from agent_net.common.did import DIDGenerator, AgentProfile
from nacl.encoding import HexEncoder


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    from agent_net.storage import DB_PATH
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    await init_db()
    yield


async def _create_agent(name: str, owner_did: str = None):
    """Helper: create and register an agent."""
    obj, _ = DIDGenerator.create_agentnexus(name)
    profile = AgentProfile(id=obj.did, name=name, type="GeneralAgent", capabilities=["test"]).to_dict()
    pk_hex = obj.private_key.encode(HexEncoder).decode()
    await register_agent(obj.did, profile, is_local=True, private_key_hex=pk_hex)
    if owner_did:
        await bind_agent(owner_did, obj.did)
    return obj


# ══════════════════════════════════════════════════════════════════════════════
# D-SEC-09: message_id 持久化
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_v10_sec_09_store_message_auto_generates_message_id():
    """store_message 未传 message_id 时自动生成。"""
    owner = await register_owner("TestOwner")
    agent = await _create_agent("AgentA", owner["did"])

    await store_message(
        from_did="did:agentnexus:sender",
        to_did=agent.did,
        content="Hello",
        session_id="sess_001",
    )

    inbox = await fetch_inbox(agent.did)
    assert len(inbox) == 1
    msg = inbox[0]
    assert "message_id" in msg
    assert msg["message_id"] is not None
    assert msg["message_id"].startswith("msg_")


@pytest.mark.asyncio
async def test_v10_sec_09_store_message_custom_message_id():
    """store_message 支持自定义 message_id。"""
    owner = await register_owner("TestOwner")
    agent = await _create_agent("AgentB", owner["did"])
    custom_id = f"msg_{uuid.uuid4().hex[:16]}"

    await store_message(
        from_did="did:agentnexus:sender",
        to_did=agent.did,
        content="Hello with custom ID",
        session_id="sess_002",
        message_id=custom_id,
    )

    inbox = await fetch_inbox(agent.did)
    assert len(inbox) == 1
    assert inbox[0]["message_id"] == custom_id


@pytest.mark.asyncio
async def test_v10_sec_09_fetch_inbox_returns_message_id():
    """fetch_inbox 返回结果包含 message_id 字段。"""
    owner = await register_owner("TestOwner")
    agent = await _create_agent("AgentC", owner["did"])

    await store_message(
        from_did="did:agentnexus:sender",
        to_did=agent.did,
        content="Inbox test",
        session_id="sess_003",
        message_id="msg_inbox_test",
    )

    inbox = await fetch_inbox(agent.did)
    assert len(inbox) == 1
    msg = inbox[0]
    assert msg["message_id"] == "msg_inbox_test"
    assert "id" in msg  # DB auto-increment id
    assert msg["from"] == "did:agentnexus:sender"
    assert msg["content"] == "Inbox test"


@pytest.mark.asyncio
async def test_v10_sec_09_fetch_session_returns_message_id():
    """fetch_session 返回结果包含 message_id 字段。"""
    owner = await register_owner("TestOwner")
    agent_a = await _create_agent("AgentD", owner["did"])
    agent_b = await _create_agent("AgentE", owner["did"])
    session = "sess_conversation"

    await store_message(agent_a.did, agent_b.did, "Hi", session, message_id="msg_001")
    await store_message(agent_b.did, agent_a.did, "Hey!", session, message_id="msg_002")
    await store_message(agent_a.did, agent_b.did, "How are you?", session, message_id="msg_003")

    # Mark as delivered so fetch_inbox doesn't consume them
    import aiosqlite
    from agent_net.storage import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE messages SET delivered=1 WHERE session_id=?", (session,))
        await db.commit()

    msgs = await fetch_session(session)
    assert len(msgs) == 3
    assert msgs[0]["message_id"] == "msg_001"
    assert msgs[1]["message_id"] == "msg_002"
    assert msgs[2]["message_id"] == "msg_003"


@pytest.mark.asyncio
async def test_v10_sec_09_message_id_uniqueness():
    """自动生成的 message_id 应当唯一。"""
    owner = await register_owner("TestOwner")
    agent = await _create_agent("AgentF", owner["did"])

    ids = set()
    for i in range(10):
        await store_message(
            from_did="did:agentnexus:sender",
            to_did=agent.did,
            content=f"Message {i}",
            session_id="sess_uniq",
        )

    # All 10 messages should have distinct message_ids
    import aiosqlite
    from agent_net.storage import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT message_id FROM messages WHERE session_id=?", ("sess_uniq",)
        ) as cursor:
            rows = await cursor.fetchall()

    assert len(rows) == 10
    msg_ids = [r[0] for r in rows]
    assert len(set(msg_ids)) == 10, "All message_ids should be unique"
