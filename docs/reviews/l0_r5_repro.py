"""Fifth review: repeat R4 probes and test an empty Coordinator binding."""
import asyncio
import json
from pathlib import Path
import runpy
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


async def main():
    import httpx
    import agent_net.storage as s
    import agent_net.node.routers.code_review as router
    import agent_net.persistence.code_review_store as store
    from agent_net.node.daemon import app
    h = runpy.run_path(str(ROOT / 'tests/test_code_review_api.py'))
    results = []
    for case in ('rebind_attempt', 'rebind_coordinator', 'lease_expires_waiting_for_lock', 'empty_coordinator_then_rebind'):
        with tempfile.TemporaryDirectory() as directory:
            s.DB_PATH = Path(directory) / 'review.db'
            await s.init_db()
            session = await h['_profile_session']()
            headers = await h['_worker']('worker:r4', sessions=[session['profile_session_id']])
            headers['X-Correlation-Id'] = 'corr_cr_1'
            eid = await h['_bind_assignment'](session, worker_did='worker:r4')
            if case == 'empty_coordinator_then_rebind':
                await store.bind_execution_assignment(
                    eid, profile_session_id=session['profile_session_id'],
                    external_run_id=session['external_run_id'],
                    external_attempt_id='A1', external_coordinator_id='',
                    assignment_epoch=1,
                )
            original = router.vault_put
            tasks = []
            expiry = None

            async def during_io(*args, **kwargs):
                nonlocal expiry
                result = await original(*args, **kwargs)
                if case.startswith('rebind_') or case == 'empty_coordinator_then_rebind':
                    await store.bind_execution_assignment(
                        eid, profile_session_id=session['profile_session_id'],
                        external_run_id=session['external_run_id'],
                        external_attempt_id='A2' if case == 'rebind_attempt' else 'A1',
                        external_coordinator_id='urn:code-review:coordinator:other' if case == 'rebind_coordinator' else 'urn:code-review:coordinator:test',
                        assignment_epoch=1,
                    )
                else:
                    expiry = time.time() + 0.5
                    await s.update_objective_execution(eid, lease_expires_at=expiry)
                    ready = asyncio.Event()
                    async def hold_lock():
                        async with store.connect() as db:
                            await db.execute('BEGIN IMMEDIATE')
                            ready.set()
                            await asyncio.sleep(1.2)
                            await db.commit()
                    tasks.append(asyncio.create_task(hold_lock()))
                    await ready.wait()
                return result

            router.vault_put = during_io
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test', headers=headers) as client:
                    response = await client.post(h['ARTIFACT_URL'], json=h['_artifact_request'](session['external_run_id']), headers={'Idempotency-Key': case})
                async with store.connect() as db:
                    async with db.execute('SELECT COUNT(*) FROM artifacts') as cur:
                        count = (await cur.fetchone())[0]
                results.append({'case': case, 'status': response.status_code, 'artifacts': count, 'expired_at_response': time.time() > expiry if expiry else None})
            finally:
                router.vault_put = original
                await asyncio.gather(*tasks)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
