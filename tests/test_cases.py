"""
测试套件 - 对应规格书中的5个测试用例
运行方式: python -m pytest tests/ -v
或直接: python tests/test_cases.py
"""
import asyncio
import json
import sys
import time
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, ".")

from agent_net.storage import init_db
from agent_net.identity import generate_did, AgentProfile
from agent_net.router import Router
from agent_net import storage


# ── 测试夹具 ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def use_test_db(tmp_path, monkeypatch):
    """每个测试使用独立的临时数据库"""
    import agent_net.storage as s
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(s, "DB_PATH", test_db)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(s.init_db())
    loop.close()


# ── tc01: 本地自动注册 ────────────────────────────────────

def test_tc01_local_auto_register():
    """tc01 - 启动后能自动注册Agent并通过list_local_agents返回正确信息"""
    async def _run():
        did = generate_did("openclaw_001")
        profile = AgentProfile(
            id=did,
            name="OpenClaw实例",
            capabilities=["ETC_Settlement", "OCR_Recognition"],
            location="Nanjing",
        )
        await storage.register_agent(did, profile.to_dict(), is_local=True)

        agents = await storage.list_local_agents()
        assert len(agents) == 1
        assert agents[0]["did"] == did
        assert agents[0]["profile"]["name"] == "OpenClaw实例"
        print(f"  [tc01 PASS] DID={did}, agents={len(agents)}")

    asyncio.run(_run())


# ── tc02: 内网点对点通信 ──────────────────────────────────

def test_tc02_local_p2p_message():
    """tc02 - 同一节点内Agent A发消息给Agent B，本地直投，延迟<5ms"""
    async def _run():
        r = Router()
        did_a = generate_did("agent_a")
        did_b = generate_did("agent_b")

        # 注册本地会话
        r.register_local_session(did_a)
        r.register_local_session(did_b)

        t0 = time.perf_counter()
        result = await r.route_message(did_a, did_b, "Hello from A!")
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert result["method"] == "local"
        assert result["status"] == "delivered"
        assert elapsed_ms < 5.0, f"延迟 {elapsed_ms:.2f}ms 超过5ms"

        msg = await r.receive(did_b)
        assert msg is not None
        assert msg["content"] == "Hello from A!"
        print(f"  [tc02 PASS] 延迟={elapsed_ms:.3f}ms, method={result['method']}")

    asyncio.run(_run())


# ── tc03: NAT穿透（模拟） ─────────────────────────────────

def test_tc03_nat_traversal_fallback():
    """tc03 - 远程DID不可达时自动降级到离线存储（模拟NAT穿透失败场景）"""
    async def _run():
        r = Router(relay_url="http://unreachable-relay:9999")
        did_a = generate_did("node_a")
        did_b = generate_did("node_b")  # 未注册本地会话，模拟远程节点

        # 添加一个不可达的通讯录条目
        await storage.upsert_contact(did_b, "http://192.168.99.99:8765", "http://unreachable-relay:9999")

        result = await r.route_message(did_a, did_b, "Cross-NAT message")
        # P2P和Relay都失败，应降级到离线
        assert result["method"] == "offline"
        assert result["status"] == "queued"
        print(f"  [tc03 PASS] NAT穿透失败后降级: method={result['method']}")

    asyncio.run(_run())


# ── tc04: 离线消息投递 ────────────────────────────────────

def test_tc04_offline_message_delivery():
    """tc04 - B离线时A发消息，B上线后通过fetch_inbox收到消息"""
    async def _run():
        r = Router()
        did_a = generate_did("sender")
        did_b = generate_did("receiver")

        # B未注册本地会话（离线状态）
        r.register_local_session(did_a)

        # A发消息给离线的B
        result = await r.route_message(did_a, did_b, "离线消息测试内容")
        assert result["status"] == "queued"

        # B上线，拉取收件箱
        inbox = await storage.fetch_inbox(did_b)
        assert len(inbox) == 1
        assert inbox[0]["content"] == "离线消息测试内容"
        assert inbox[0]["from"] == did_a

        # 再次拉取，消息已标记delivered，不重复返回
        inbox2 = await storage.fetch_inbox(did_b)
        assert len(inbox2) == 0
        print(f"  [tc04 PASS] 离线消息已投递, from={inbox[0]['from']}")

    asyncio.run(_run())


# ── tc05: 语义寻址 ────────────────────────────────────────

def test_tc05_semantic_search():
    """tc05 - search_agents('Bank')返回包含Bank能力标签的Agent列表"""
    async def _run():
        # 注册几个测试Agent
        agents_data = [
            ("ETC助手", ["ETC_Settlement", "Bank_Binding", "OCR_Recognition"]),
            ("银行助理", ["Bank_Query", "Transfer", "Balance_Check"]),
            ("天气服务", ["Weather_Query", "Location_Service"]),
        ]
        for name, caps in agents_data:
            did = generate_did(name)
            profile = AgentProfile(id=did, name=name, capabilities=caps)
            await storage.register_agent(did, profile.to_dict(), is_local=True)

        results = await storage.search_agents_by_capability("Bank")
        assert len(results) == 2, f"期望2个结果，实际{len(results)}"

        names = [r["profile"]["name"] for r in results]
        assert "ETC助手" in names
        assert "银行助理" in names
        assert "天气服务" not in names
        print(f"  [tc05 PASS] 搜索'Bank'返回{len(results)}个Agent: {names}")

    asyncio.run(_run())


# ── tc06: 通讯录 endpoint 为空 → 自动降级 offline ──────────────

def test_tc06_empty_contact_endpoint_falls_back_offline():
    """tc06 - contact 存在但 endpoint 为空时，路由自动降级到 offline"""
    async def _run():
        r = Router()
        did_a = generate_did("tc06_sender")
        did_b = generate_did("tc06_receiver")
        r.register_local_session(did_a)

        # 注册通讯录但 endpoint 为空字符串（模拟地址已失效）
        await storage.upsert_contact(did_b, "", None)

        result = await r.route_message(did_a, did_b, "fallback test")
        assert result["method"] == "offline"
        assert result["status"] == "queued"
        print(f"  [tc06 PASS] 空 endpoint 自动降级: method={result['method']}")

    asyncio.run(_run())


# ── tc07: 多发送方消息独立存储，fetch_inbox 一次性取回 ──────────

def test_tc07_inbox_multiple_senders():
    """tc07 - 多个发送方的消息独立存储，fetch_inbox 全部取回且不重复"""
    async def _run():
        r = Router()
        did_a = generate_did("tc07_a")
        did_b = generate_did("tc07_b")
        did_c = generate_did("tc07_c")  # 收件人（离线）
        r.register_local_session(did_a)
        r.register_local_session(did_b)

        r1 = await r.route_message(did_a, did_c, "from A")
        r2 = await r.route_message(did_b, did_c, "from B")
        assert r1["status"] == "queued"
        assert r2["status"] == "queued"

        inbox = await storage.fetch_inbox(did_c)
        assert len(inbox) == 2
        senders = {m["from"] for m in inbox}
        assert did_a in senders and did_b in senders

        # 再次取收件箱 → 已标记 delivered，不重复返回
        inbox2 = await storage.fetch_inbox(did_c)
        assert len(inbox2) == 0
        print(f"  [tc07 PASS] 两封消息独立存储并取回，第二次为空")

    asyncio.run(_run())


# ── tc08: /deliver 端点透传 message_type 和 protocol ──────────────────────

def test_tc08_deliver_endpoint_preserves_message_type(tmp_path, monkeypatch):
    """tc08 - /deliver 端点必须透传 message_type 和 protocol（Bug: B1 回归测试）"""
    import importlib
    import agent_net.storage as st
    import agent_net.node.daemon as d

    # 隔离 DB
    monkeypatch.setattr(st, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(d, "DAEMON_TOKEN_FILE", str(tmp_path / "token.txt"))
    monkeypatch.setattr(d, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(d, "NODE_CONFIG_FILE", str(tmp_path / "node_config.json"))

    importlib.reload(d)
    from agent_net.node.daemon import router

    with TestClient(d.app) as client:
        token = d._daemon_token

        sender_did = client.post(
            "/agents/register",
            json={"name": "sender"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()["did"]
        receiver_did = client.post(
            "/agents/register",
            json={"name": "receiver"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()["did"]

        # 重要：在发送前注册本地会话，否则 router 会认为 receiver 离线
        router.register_local_session(receiver_did)

        # 通过 /deliver 发送带 message_type 和 protocol 的 Action Layer 消息
        deliver_payload = {
            "from": sender_did,
            "to": receiver_did,
            "content": json.dumps({"title": "测试任务", "description": "验证 message_type 透传"}),
            "session_id": "sess_tc08_test",
            "message_type": "task_propose",
            "protocol": "nexus_v1",
        }
        resp = client.post("/deliver", json=deliver_payload)
        assert resp.status_code == 200, f"/deliver failed: {resp.text}"

        # 接收方从本地队列取消息，验证 message_type 和 protocol 没有丢失
        msg = asyncio.run(router.receive(receiver_did, timeout=2.0))
        assert msg is not None, "receiver 未收到消息"
        assert msg.get("message_type") == "task_propose", \
            f"message_type 丢失，期望 'task_propose'，实际: {msg.get('message_type')}"
        assert msg.get("protocol") == "nexus_v1", \
            f"protocol 丢失，期望 'nexus_v1'，实际: {msg.get('protocol')}"

        print(f"  [tc08 PASS] message_type={msg['message_type']}, protocol={msg['protocol']} — 透传正确")


if __name__ == "__main__":
    print("=== AgentNexus 自测用例 ===\n")
    tests = [
        test_tc01_local_auto_register,
        test_tc02_local_p2p_message,
        test_tc03_nat_traversal_fallback,
        test_tc04_offline_message_delivery,
        test_tc05_semantic_search,
        test_tc08_deliver_endpoint_preserves_message_type,
    ]
    # 简单runner（不依赖pytest）
    import tempfile, os, pathlib
    import agent_net.storage as s

    passed = 0
    for test_fn in tests:
        with tempfile.TemporaryDirectory() as tmp:
            s.DB_PATH = pathlib.Path(tmp) / "test.db"
            asyncio.run(s.init_db())
            try:
                test_fn()
                passed += 1
            except Exception as e:
                print(f"  [FAIL] {test_fn.__name__}: {e}")

    print(f"\n结果: {passed}/{len(tests)} 通过")
