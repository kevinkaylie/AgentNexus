"""Third review: deterministic local concurrency, fencing and replay probes."""
import asyncio
import copy
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
    from agent_net.node.daemon import app
    h = runpy.run_path(str(ROOT / 'tests/test_code_review_api.py'))
    with tempfile.TemporaryDirectory() as directory:
        s.DB_PATH = Path(directory) / 'review.db'
        await s.init_db()
        session = await h['_profile_session']()
        sid, run = session['profile_session_id'], session['external_run_id']
        headers = await h['_worker']('worker:r3', sessions=[sid])
        eid = await h['_bind_assignment'](session, worker_did='worker:r3')
        headers['X-Correlation-Id'] = 'corr_cr_1'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test', headers=headers) as client:
            body = h['_artifact_request'](run)
            original = router.vault_put
            ready = asyncio.Event()
            count = 0
            vault_lock = asyncio.Lock()
            async def barrier(*args, **kwargs):
                nonlocal count
                count += 1
                if count == 2:
                    ready.set()
                await asyncio.wait_for(ready.wait(), timeout=10)
                async with vault_lock:
                    return await original(*args, **kwargs)
            router.vault_put = barrier
            try:
                results = await asyncio.gather(*(client.post(h['ARTIFACT_URL'], json=body, headers={'Idempotency-Key': 'same-key'}) for _ in range(2)))
                print('CONCURRENT_SAME_KEY', sorted(r.status_code for r in results))
                print('CONCURRENT_ERRORS', [r.text for r in results if r.status_code >= 400])
            finally:
                router.vault_put = original
            reserialized = await client.post(h['ARTIFACT_URL'], content=json.dumps(body, indent=2), headers={'Content-Type': 'application/json', 'Idempotency-Key': 'same-key'})
            print('SAME_BUSINESS_DIFFERENT_JSON', reserialized.status_code, reserialized.json().get('code'))
            await s.update_objective_execution(eid, lease_expires_at=time.time()-60)
            expired = await client.post(h['ARTIFACT_URL'], json=body, headers={'Idempotency-Key': 'expired-lease'})
            print('EXPIRED_LEASE', expired.status_code)
            await s.update_objective_execution(eid, lease_expires_at=time.time()+600)
            async def cancel_during_io(*args, **kwargs):
                await s.update_objective_execution(eid, status='cancelled')
                return await original(*args, **kwargs)
            router.vault_put = cancel_during_io
            try:
                stale = await client.post(h['ARTIFACT_URL'], json=body, headers={'Idempotency-Key': 'cancelled-during-upload'})
                print('CANCEL_DURING_UPLOAD', stale.status_code)
            finally:
                router.vault_put = original
        issuer = 'urn:code-review:coordinator:test'
        coordinator = h['_client'](await h['_coordinator'](sessions=[sid]))
        env = h['_envelope']('receipt', session_id=session['coordination_session_id'], sender=issuer, run_id=run,
                             payload=h['_receipt_payload'](run, issuer_id=issuer))
        first = coordinator.post(h['MESSAGE_URL'], json=env)
        other = copy.deepcopy(env)
        other['created_at'] = '2026-09-22T00:00:00Z'
        replay = coordinator.post(h['MESSAGE_URL'], json=other)
        print('MESSAGE_NONBUSINESS_REPLAY', first.status_code, replay.status_code)
        unbound = h['_envelope']('receipt', session_id='never-authorized-session', sender=issuer, run_id='unregistered-run',
                                 payload=h['_receipt_payload']('unregistered-run', issuer_id=issuer))
        response = coordinator.post(h['MESSAGE_URL'], json=unbound)
        print('UNREGISTERED_RECEIPT_SCOPE', response.status_code)


if __name__ == '__main__':
    asyncio.run(main())
