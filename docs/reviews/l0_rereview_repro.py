"""Second-round isolated review probes; no production credentials or network."""
import asyncio
import base64
import copy
import json
from pathlib import Path
import runpy
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


async def main():
    import agent_net.storage as s
    import agent_net.node.routers.code_review as router
    h = runpy.run_path(str(ROOT / 'tests/test_code_review_api.py'))
    with tempfile.TemporaryDirectory() as directory:
        s.DB_PATH = Path(directory) / 'review.db'
        await s.init_db()
        session = await h['_profile_session']()
        sid, run = session['profile_session_id'], session['external_run_id']
        worker = h['_client'](await h['_worker']('worker:review', sessions=[sid]))
        body = h['_artifact_request'](run)
        original = router.vault_put
        async def fail(*args, **kwargs):
            raise OSError('injected storage failure')
        router.vault_put = fail
        first = worker.post(h['ARTIFACT_URL'], json=body, headers={'Idempotency-Key': 'retry-key'})
        router.vault_put = original
        retry = worker.post(h['ARTIFACT_URL'], json=body, headers={'Idempotency-Key': 'retry-key'})
        print('UPLOAD_RECOVERY', first.status_code, retry.status_code, retry.json().get('code'))
        unknown = h['_artifact_request']('unregistered-run', attempt_id='unassigned-attempt', assignment_epoch=999)
        result = worker.post(h['ARTIFACT_URL'], json=unknown, headers={'Idempotency-Key': 'unknown-run'})
        print('UNBOUND_UPLOAD', result.status_code)
        unassigned = h['_artifact_request'](run, attempt_id='never-assigned', assignment_epoch=999)
        result = worker.post(h['ARTIFACT_URL'], json=unassigned, headers={'Idempotency-Key': 'unassigned'})
        print('UNASSIGNED_EPOCH_UPLOAD', result.status_code)
        coordinator = h['_client'](await h['_coordinator'](sessions=[sid]))
        issuer = 'urn:code-review:coordinator:test'
        env = h['_envelope']('receipt', session_id=session['coordination_session_id'], sender=issuer, run_id=run,
                             payload=h['_receipt_payload'](run, issuer_id=issuer))
        assert coordinator.post(h['MESSAGE_URL'], json=env).status_code == 202
        conflict = copy.deepcopy(env)
        conflict['payload']['receipt_id'] = 'receipt-rejected-message'
        response = coordinator.post(h['MESSAGE_URL'], json=conflict)
        orphan = await s.get_profile_receipt('receipt-rejected-message')
        print('REJECTED_MESSAGE_SIDE_EFFECT', response.status_code, 'receipt_persisted', orphan is not None)
        validator = h['_client'](await h['_provision'](principal_id='validator:review', roles=['validator'], dids=['validator:review'], sessions=[sid]))
        await s.grant_role('validator:review', 'validator')
        validation = h['_envelope']('receipt', session_id=session['coordination_session_id'], sender='validator:review', run_id=run,
                                    payload=h['_receipt_payload'](run, kind='validated', issuer_id='validator:review'))
        result = validator.post(h['MESSAGE_URL'], json=validation)
        print('LEGITIMATE_VALIDATOR', result.status_code, result.json().get('safe_message'))


if __name__ == '__main__':
    asyncio.run(main())
    h = runpy.run_path(str(ROOT / 'tests/test_code_review_provider_adapter.py'))
    from agent_net.code_review import build_profile_report
    report = build_profile_report(provider_id='hczj', native_report={'schema_version': 'hczj.review_report.v1', 'outcome': 'findings_present', 'findings': None},
        native_coverage={'schema_version': 'hczj.review_coverage.v1', 'status': 'complete', 'planned_files': [], 'reviewed_files': [], 'omitted_files': [], 'gap_reasons': [], 'inherited_gaps': []},
        identity=h['_identity'](), execution_metadata=h['_metadata'](), usage=h['_usage']())
    print('NULL_FINDINGS', report['outcome'], report['findings'])
    checker = runpy.run_path(str(ROOT / 'specs/profiles/code-review/v1/tools/check_evidence.py'))
    error = {'schema': 'not-an-error-schema', 'code': 'authority_denied', 'retryable': 'yes',
             'action_required': None, 'scope': 123, 'correlation_id': 'probe', 'safe_message': '', 'retry_after_seconds': -99}
    sample = {'subject': 'unrelated-admin', 'endpoint': 'GET /unrelated/health', 'response_status': 403,
              'raw_bytes_b64': base64.b64encode(json.dumps(error).encode()).decode()}
    failures = []
    accepted = checker['verify_refusal_sample'](sample, 'probe', failures)
    print('INVALID_REFUSAL_SCHEMA', accepted, failures)
