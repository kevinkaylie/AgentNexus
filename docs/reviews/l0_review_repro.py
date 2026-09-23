"""Local review probes; isolated temporary DB, no server or production credentials."""
import asyncio
import importlib.util
import json
import runpy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


async def main():
    import agent_net.storage as storage
    import agent_net.node._auth as auth
    from agent_net.node.daemon import app
    from fastapi.testclient import TestClient
    helpers = runpy.run_path(str(ROOT / "tests/test_code_review_api.py"))
    with tempfile.TemporaryDirectory() as directory:
        storage.DB_PATH = Path(directory) / "review.db"
        auth._daemon_token = "local-review-only"
        await storage.init_db()
        client = TestClient(app, headers={"Authorization": "Bearer local-review-only"}, raise_server_exceptions=False)
        await storage.grant_role("coordinator:test", "coordinator")
        await storage.grant_role("worker:test", "worker")
        env = helpers["_envelope"]("assignment", session_id="session:test", sender="worker:test")
        denied = client.post("/coordination/code-review/v1/messages", json=env)
        env["sender_id"] = "coordinator:test"
        accepted = client.post("/coordination/code-review/v1/messages", json=env)
        view = client.get("/coordination/code-review/v1/messages/" + env["message_id"])
        print("IDENTITY", denied.status_code, accepted.status_code, accepted.json().get("enforcement"))
        print("EMPTY_ASSIGNMENT_PAYLOAD", accepted.status_code, "MESSAGE_VIEW", view.status_code, sorted(view.json()))
        body = {"run_id": "run:test", "attempt_id": "attempt:test", "assignment_epoch": 1,
                "artifact_body": "{}", "media_type": "application/json", "schema_version": "code_review.report.v1",
                "retention_until": "2099-01-01T00:00:00Z"}
        exact = client.post("/coordination/code-review/v1/artifacts", json=body)
        body["producer_id"] = "worker:test"
        first = client.post("/coordination/code-review/v1/artifacts", json=body, headers={"Idempotency-Key": "upload:1"})
        second = client.post("/coordination/code-review/v1/artifacts", json=body, headers={"Idempotency-Key": "upload:1"})
        print("UPLOAD", exact.status_code, first.status_code, "retention", first.json().get("retention_until"),
              "EXTRA", "enforcement" in first.json(), "REPLAY_NEW_ID", first.json().get("artifact_id") != second.json().get("artifact_id"))
        body["artifact_id"] = "immutable-test"
        saved = client.post("/coordination/code-review/v1/artifacts", json=body)
        body["artifact_body"] = '{"changed":true}'
        overwrite = client.post("/coordination/code-review/v1/artifacts", json=body)
        readback = client.get("/coordination/code-review/v1/artifacts/immutable-test/raw")
        print("IMMUTABILITY", saved.status_code, overwrite.status_code, readback.status_code, readback.json().get("code"))
        raw = client.get("/coordination/code-review/v1/artifacts/" + first.json()["artifact_id"] + "/raw")
        print("RAW_WITHOUT_RUN_SESSION_ACTOR", raw.status_code)
        import agent_net.node.routers.code_review as router
        receipt = helpers["_envelope"]("receipt", session_id="session:test", sender="coordinator:test", run_id="run:test")
        receipt["payload"] = {"kind": "accepted", "receipt_id": "receipt:crash", "decision": "confirmed", "issuer_id": "coordinator:test"}
        original = router.create_profile_receipt
        async def crash(*args, **kwargs):
            raise RuntimeError("simulated crash after durable inbox")
        router.create_profile_receipt = crash
        failed = client.post("/coordination/code-review/v1/messages", json=receipt)
        router.create_profile_receipt = original
        retry = client.post("/coordination/code-review/v1/messages", json=receipt)
        stored = await storage.get_message(receipt["message_id"])
        print("RECEIPT_RECOVERY", failed.status_code, retry.status_code, stored["state"], stored["receipts"])


if __name__ == "__main__":
    asyncio.run(main())
    helper = runpy.run_path(str(ROOT / "tests/test_code_review_provider_adapter.py"))
    from agent_net.code_review import build_profile_report
    report = build_profile_report(provider_id="hczj", native_report={"schema_version": "hczj.review_report.v1", "outcome": "findings_present", "findings": ["malformed-finding"]},
        native_coverage={"status": "complete", "planned_files": [], "reviewed_files": [], "omitted_files": [], "gap_reasons": [], "inherited_gaps": []},
        identity=helper["_identity"](), execution_metadata=helper["_metadata"](), usage=helper["_usage"]())
    print("DROPPED_FINDING", report["outcome"], report["findings"])
    checker = runpy.run_path(str(ROOT / "specs/profiles/code-review/v1/tools/check_evidence.py"))
    failures = []
    checker["check_worker_refusal_evidenced"]({"worker_refusal_evidenced": True}, {}, "probe", failures, {})
    checker["check_forged_receipt_refused"]({"forged_receipt_refused": True, "samples": [{"case": "forged_receipt_rejected", "response_status": 200}]}, {}, "probe", failures, {})
    checker["check_must_refuse_when_unconfigured"]({"unconfigured_behavior": "does not reject; allows requests"}, {}, "probe", failures, {})
    print("REFUSAL_CHECKS_WITHOUT_REFUSAL", failures)
