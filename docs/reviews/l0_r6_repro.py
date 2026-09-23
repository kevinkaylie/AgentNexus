"""Independent R5-1 closure probe against the real ASGI and SQLite paths."""
import asyncio
from pathlib import Path
import runpy
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


async def main():
    import httpx
    import agent_net.storage as storage
    from agent_net.code_review import ProfileError
    from agent_net.node.daemon import app
    from agent_net.persistence.context import connect
    from agent_net.persistence.code_review_store import (
        _verify_assignment_in_transaction, bind_execution_assignment,
    )

    helpers = runpy.run_path(str(ROOT / "tests/test_code_review_api.py"))
    with tempfile.TemporaryDirectory() as directory:
        storage.DB_PATH = Path(directory) / "review.db"
        await storage.init_db()
        session = await helpers["_profile_session"]()
        sid, run = session["profile_session_id"], session["external_run_id"]
        headers = await helpers["_worker"]("worker:r6", sessions=[sid])
        headers["X-Correlation-Id"] = "corr_cr_1"
        eid = await helpers["_bind_assignment"](session, worker_did="worker:r6")
        binding_args = dict(profile_session_id=sid, external_run_id=run,
                            external_attempt_id="A1", assignment_epoch=1)
        try:
            await bind_execution_assignment(
                eid, external_coordinator_id="", **binding_args,
            )
        except ProfileError as exc:
            print("EMPTY_BINDING", exc.code)
        else:
            print("EMPTY_BINDING", "ACCEPTED")

        # Simulate a legacy persisted row created before binding validation existed.
        async with connect() as db:
            await db.execute(
                "UPDATE objective_executions SET external_coordinator_id='' WHERE execution_id=?",
                (eid,),
            )
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test", headers=headers,
        ) as client:
            response = await client.post(
                helpers["ARTIFACT_URL"], json=helpers["_artifact_request"](run),
                headers={"Idempotency-Key": "legacy-empty-binding"},
            )
            print("LEGACY_EMPTY_UPLOAD", response.status_code, response.json().get("code"))
        async with connect() as db:
            async with db.execute("SELECT COUNT(*) FROM artifacts") as cur:
                print("ARTIFACTS_AFTER_REJECT", (await cur.fetchone())[0])
            await db.execute(
                "UPDATE objective_executions SET external_coordinator_id=? WHERE execution_id=?",
                ("urn:code-review:coordinator:test", eid),
            )
            await db.commit()
        async with connect() as db:
            try:
                await _verify_assignment_in_transaction(
                    db, execution_id=eid, profile_session_id=sid,
                    external_run_id=run, expected_attempt_id="A1",
                    expected_coordinator_id="", expected_epoch=1,
                    expected_worker_did="worker:r6",
                )
            except ProfileError as exc:
                print("EMPTY_EXPECTED_FENCING", exc.code)
            else:
                print("EMPTY_EXPECTED_FENCING", "BYPASSED")


if __name__ == "__main__":
    asyncio.run(main())
