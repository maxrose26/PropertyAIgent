"""Static contracts of the screening-v3 activation candidate (PR #175): names, clocks, the single-use hosted workflow, the generated SQL artefacts and the manifest. Offline; nothing is installed, registered or dispatched."""
import hashlib
import json
import re
from pathlib import Path

import pytest

pytest.importorskip('resource')      # the owner/runner modules import the Linux-only `resource` module (CI is Linux)

import yaml

from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import policy_screening_v3 as p
from verification.ingestion_storage import screening_v3_hosted as hosted
from verification.ingestion_storage import screening_v3_worker_sql as sv3

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/stage4-screening-v3-retained-once.yml'


def text(path):
    return (ROOT / path).read_bytes().decode('utf-8').replace('\r\n', '\n')


def test_the_names_agree_everywhere_and_there_is_exactly_one_screening_only_allowance():
    assert orr.SV3_NAME == p.NAME == orr.SV3_AUTHORITY + '_SCREEN' == hosted.SV3_AUTHORITY + '_SCREEN'
    assert p.NAME.endswith('_SCREEN') and '_CAPTURE' not in p.NAME
    assert orr.SV3_MODE != orr.SV3_POLICY_MODE and orr.SV3_STATE != orr.SV3_POLICY_STATE and orr.SV3_HOSTED_AUTHORITY != orr.SV3_AUTHORITY
    # none of the consumed names or namespaces is reused
    consumed = {orr.WINDOW_AUTHORITY, orr.WINDOW_POLICY_AUTHORITY, orr.CAPTURE_AUTHORITY, orr.PROBE_AUTHORITY, orr.PIPELINE_AUTHORITY, orr.WINDOW_HOSTED_AUTHORITY, orr.WINDOW_STATE, orr.WINDOW_POLICY_STATE}
    assert not consumed & {orr.SV3_AUTHORITY, orr.SV3_POLICY_AUTHORITY, orr.SV3_HOSTED_AUTHORITY, orr.SV3_STATE, orr.SV3_POLICY_STATE}
    assert orr.SV3_EVIDENCE_DIRECTORY.startswith('docs/design/ingestion-operational-execution-') and orr.SV3_EVIDENCE_DIRECTORY != orr.WINDOW_EVIDENCE_DIRECTORY


def test_the_clocks_are_the_provisional_600_300_900_and_never_extend_the_grant():
    b = orr.SV3_BINDING
    assert (b['execution_deadline_seconds'], b['cleanup_reserve_seconds'], b['grant_lifetime_seconds']) == (600, 300, 900)
    assert b['execution_deadline_seconds'] + b['cleanup_reserve_seconds'] == b['grant_lifetime_seconds'] and b['grant_minutes'] * 60 == b['grant_lifetime_seconds']
    assert b['screening_wait_seconds'] <= b['execution_deadline_seconds']      # the owner never waits for the hosted result longer than the execution deadline
    assert b['ready_wait_seconds'] > b['grant_lifetime_seconds']      # queueing and approval are bounded SEPARATELY and are outside the grant lifetime
    assert hosted.sp.SCREENING_WAIT_SECONDS + 2 * hosted.sp.POLL_SECONDS < b['execution_deadline_seconds']      # the hosted wait for the owner's marker fits inside the deadline
    source = text('verification/ingestion_storage/operational_runner.py')
    assert "self.owner.grant_expiry=min(self.expiry,datetime.now(timezone.utc)+timedelta(seconds=pb['grant_lifetime_seconds']))" in source      # fixed at registration, never extended
    assert source.index("hosted-ready/ready.json") < source.index("self.batch_bindings=self.owner.register(batches3")      # the allowance is registered only AFTER the hosted job is ready
    timing = orr.PIPELINE_TIMING
    assert b['ready_wait_seconds'] + b['grant_lifetime_seconds'] + 600 <= orr.PIPELINE_DEADLINES['job'] and orr.PIPELINE_DEADLINES['job'] + orr.PIPELINE_DEADLINES['diagnostic_window'] <= timing['work_seconds']


def test_the_hosted_and_owner_bindings_are_the_same_exact_scope():
    b = orr.SV3_BINDING
    assert b['source'] == dict(requests=0, redirects=0, retries=0, source_client='NONE') and b['screening'] == dict(batches=5, children=24, retained_rows=30, new_items=29, bound_keys=59)
    assert b['capture_key'] == p.CAPTURE_KEY == hosted.CAPTURE_KEY and b['hard_stop_generation'] == 3 and b['stop_state_sha256'] == p.G3_SHA
    assert orr.SV3_PREDECESSOR['consumed_window_names'] == [p.WINDOW_CAPTURE, p.WINDOW_SCREEN]
    assert hosted.ScreeningV3HostedRunner.GRANT_SUFFIX == '_SCREEN' and hosted.ScreeningV3HostedRunner.EVIDENCE == orr.SV3_EVIDENCE_DIRECTORY and hosted.ScreeningV3HostedRunner.MANIFEST == orr.SV3_MANIFEST_PATH


def test_the_hosted_module_has_no_administrative_source_or_registration_capability():
    source = text('verification/ingestion_storage/screening_v3_hosted.py')
    for forbidden in ('Owner(', 'operational_owner import Owner', 'register(', 'capture_once', 'source_reader(', 'idox_source', 'DATABASE_URL', 'put_secret', 'map_and_activate', 'ALTER ROLE', 'GRANT '):
        assert forbidden not in source, forbidden
    assert 'sq.Qualification' in source and 'await_marker' in source and 'authority_present' in source and 'verify_assessed' in source and 'assessment_plan' in source


def test_the_workflow_is_dispatch_only_single_use_protected_and_restricted_credentials_only():
    raw = text('.github/workflows/stage4-screening-v3-retained-once.yml')
    doc = yaml.safe_load(raw)
    triggers = doc.get('on', doc.get(True))
    assert list(triggers) == ['workflow_dispatch']      # no push, schedule, pull_request or workflow_run trigger: nothing dispatches it automatically
    inputs = triggers['workflow_dispatch']['inputs']
    assert inputs['authority']['options'] == ['NOT_AUTHORISED', orr.SV3_HOSTED_AUTHORITY] and inputs['authority']['default'] == 'NOT_AUTHORISED'
    assert doc['permissions'] == {'contents': 'write'} and doc['concurrency']['cancel-in-progress'] is False
    job = doc['jobs']['screening']
    assert job['environment'] == 'stage4-production-canary' and job['timeout-minutes'] == 40      # the protected environment's approval is the human gate
    assert 'GITHUB_RUN_NUMBER" == 1' in raw and 'GITHUB_RUN_ATTEMPT" == 1' in raw and 'refs/heads/master' in raw      # single use
    secrets = set(re.findall(r'secrets\.([A-Z_]+)', raw))
    assert secrets == {'INGESTION_WORKER_DATABASE_URL', 'INGESTION_EFFECT_DATABASE_URL'}      # the two standing restricted credentials alone; no administrative secret
    assert 'verification.ingestion_storage.screening_v3_hosted' in raw and 'window_demonstration' not in raw and 'ingestion_storage.operational_runner' not in raw
    assert 'printf' in raw and 'env -i' in raw and 'hosted_memory_scope.sh' in raw      # secrets on stdin only, a scrubbed environment and the kernel-enforced memory scope


def test_the_generated_sql_artefacts_are_exactly_what_the_derivation_modules_produce():
    assert text('docs/design/ingestion-screening-v3-activation-20261030/worker-step-v3.sql') == sv3.installation_script()
    assert text('docs/design/ingestion-screening-v3-activation-20261030/worker-step-original.sql') == sv3.rollback_script()
    assert text(str(p.POLICY_FILE)) == p.v6_text()
    assert sv3.undo(sv3.derive()) == sv3.original_text()


def test_the_manifest_lists_only_existing_paths_and_states_the_provisional_clocks():
    manifest = json.loads(text(orr.SV3_MANIFEST_PATH))
    assert manifest['bound_paths'] == sorted(manifest['bound_paths']) and all((ROOT / path).is_file() for path in manifest['bound_paths'])
    assert orr.SV3_MANIFEST_PATH not in manifest['bound_paths']      # the manifest does not list itself
    assert manifest['authority']['name'] == p.NAME and manifest['clocks_seconds']['status'] == 'PROVISIONAL'
    for must in ('verification/ingestion_storage/operational_runner.py', 'verification/ingestion_storage/screening_v3_hosted.py', '.github/workflows/stage4-screening-v3-retained-once.yml', 'verification/ingestion_storage/retained_world.py'):
        assert must in manifest['bound_paths']
    assert hashlib.sha256((ROOT / orr.SV3_MANIFEST_PATH).read_bytes()).hexdigest()      # the hosted reader hashes exactly this file


def test_the_registration_validation_knows_both_new_modes_and_no_other_path_does():
    source = text('verification/ingestion_storage/operational_runner.py')
    for needle in ("SV3_POLICY_MODE:SV3_POLICY_AUTHORITY,SV3_MODE:SV3_AUTHORITY", "if r.get('mode')==SV3_POLICY_MODE:", "if r.get('mode')==SV3_MODE:", "'BOLTON_SCREENING_V3_BINDING'", "'BOLTON_SCREENING_V3_POLICY_BINDING'", "SV3_MODE,*SETTLED_MODES"):
        assert needle in source, needle
    assert text('verification/ingestion_storage/operational_runner.py').count('getattr(self,\'screening_rules\',None)') == 1      # v1 unless a v3 mode registered its rule
    assert 'SV3' not in text('verification/ingestion_storage/stable_pipeline.py')      # the accepted hosted pipeline is untouched
