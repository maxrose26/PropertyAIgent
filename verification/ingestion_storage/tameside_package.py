"""Pure deterministic policy/command sealing; no I/O beyond pinned source reads."""
import hashlib
import base64
import json
import shlex
from datetime import datetime,timezone
from pathlib import Path
from .daily_intake_runtime import execution_binding
from .inactive_tameside_first_issuer import prepare_inactive_campaign_owner_batch,review_inactive_campaign_owner_policy
from .tameside_candidate import EXPIRY
from app.ingestion.ledger import digest
from app.ingestion.listing_screening import ScreeningRule,RULE_V3

PERIOD='S4_FINITE_677f555670666bcf21f45860'
HOSTADDR='18.169.28.97'


def seal_policy(*,manifest_sha256,bound_at,hostaddr=HOSTADDR):
    """One accepted recipe: 2100s access, 185s cleanup reserve, fixed ceiling.

    bound_at is recorded once before activation. Never slide it on failure.
    A changed current address refuses this package, rather than silently rebinding.
    The manifest hash comes ONLY from independent post-recovery readback.
    """
    import math,re
    if (type(bound_at) not in (int,float) or not math.isfinite(bound_at)
            or bound_at+2100>EXPIRY or hostaddr!=HOSTADDR
            or not re.fullmatch('[a-f0-9]{64}',manifest_sha256)):
        raise ValueError('TAMESIDE_SEAL_INPUTS')
    as_of=datetime.fromtimestamp(bound_at,timezone.utc)
    preview=prepare_inactive_campaign_owner_batch(as_of,'tameside','2026-09-15','2026-09-21')
    if preview['period']!=PERIOD:raise ValueError('TAMESIDE_PERIOD_DRIFT')
    binding=execution_binding()
    policy=dict(expires_at=bound_at+1915,max_runs=1,overlap_days=7,
        councils={'tameside':dict(contract='tameside-screening-metadata-five-v1',
            qualification_sha256=hashlib.sha256(Path('docs/design/tameside-b-connection-20261101/tameside-qualification.json').read_bytes()).hexdigest())},
        expected_stop=dict(global_stop=None,manual_stop=None,last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',hard_stop_generation=16),
        execution_binding=binding,test_evidence=False,
        screening_config=digest(ScreeningRule(RULE_V3,unit_threshold=10,link_related=False).config()),
        hostaddr=hostaddr,route='POOLER',mode='CAMPAIGN_FINITE_HISTORICAL_V1',
        campaign_batch=preview['campaign_batch'],campaign_source_plan_sha256=preview['campaign_source_plan_sha256'],
        release_manifest_sha256=manifest_sha256,evidence_backend='POSTGRES_PILOT_V1',
        private_release=dict(schema='PA_D002_LIVE_PRIVATE_V1',revision=binding['revision'],councils=['tameside'],semantics='RECEIVED'))
    review_inactive_campaign_owner_policy(as_of,'tameside','2026-09-15','2026-09-21',period=PERIOD,
        policy=policy,observed_stop=policy['expected_stop'],execution_binding=binding)
    return policy


def encode_policy(policy):
    return json.dumps(policy,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def job_command(policy,*,policy_path,output):
    # Paths are fixed private staging locations in the existing runtime, not
    # shell interpolation. The runtime rechecks build, expiry, hash and route.
    for path in (policy_path,output):
        if not str(path).startswith('/tmp/') or '..' in Path(path).parts:
            raise ValueError('TAMESIDE_PRIVATE_RUNTIME_PATH')
    return shlex.join(['/usr/bin/timeout','--signal=INT','--kill-after=5s','960s',
        'python','-B','-m','verification.ingestion_storage.tameside_candidate',
        '--policy-base64',base64.b64encode(encode_policy(policy)).decode(),'--policy-sha256',hashlib.sha256(encode_policy(policy)).hexdigest(),
        '--period',PERIOD,'--output',str(output),'--hostaddr',policy['hostaddr'],
        '--access-deadline',str(policy['expires_at']+185)])


def compile_package(manifest,*,bound_at,owner_journal_source):
    """Compile exact transaction/command bytes after independent manifest read.

    Does not execute, connect, create credentials, or infer owner acceptance.
    The separately approved recipe binds the only execution-derived values.
    """
    from . import release_candidate as release
    from .inactive_owner_writer_install import render_inactive_writer_install
    from .tameside_owner_journal import render_install
    policy=seal_policy(manifest_sha256=manifest['manifest_binding_sha256'],bound_at=bound_at)
    as_of=datetime.fromtimestamp(bound_at,timezone.utc)
    files={
        'policy.json':encode_policy(policy),
        'manifest.json':json.dumps(manifest,sort_keys=True,separators=(',',':')).encode(),
        'owner-journal-install.sql':render_install(owner_journal_source).encode(),
        'private-writer-install.sql':render_inactive_writer_install(release.RELEASE_PATH.with_name('private_evidence_writer_transition.sql').read_text()).encode(),
        'campaign-install.sql':release.render_campaign_install(as_of=as_of,period=PERIOD,policy=policy,release_manifest_sha256=manifest['manifest_binding_sha256']).encode(),
        'conditional-release.sql':release.render_release(manifest,expires_at=manifest['expires_at']).encode(),
        'job-command.txt':job_command(policy,policy_path='/tmp/propertyaigent-tameside-policy.json',output='/tmp/propertyaigent-tameside-once').encode(),
    }
    receipt=dict(version=1,status='INACTIVE_COMPILED_NOT_EXECUTED',period=PERIOD,
        bound_at=bound_at,access_deadline=policy['expires_at']+185,expiry_ceiling=EXPIRY,
        execution_binding=policy['execution_binding'],batch=policy['campaign_batch'],
        files={name:dict(sha256=hashlib.sha256(body).hexdigest(),bytes=len(body)) for name,body in files.items()})
    files['package.json']=json.dumps(receipt,sort_keys=True,indent=2).encode()
    return files
