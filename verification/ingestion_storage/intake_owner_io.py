"""Private owner-local I/O for finite intake preparation; no scheduler or retry.

Render transport implements only documented service/env reads, exact env replace
and terminal-job read. It cannot deploy, submit jobs, resume or change schedules.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import time

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from .intake_owner import require,validate_binding
from .operational_publication import canonical
from .restricted_route import url
from .render_intake import SERVICE

VAULT_LIMIT = 32768
KEEP = {'PYTHONUNBUFFERED', 'PLAYWRIGHT_BROWSERS_PATH', 'INGESTION_RENDER_PROFILE', 'LANG', 'TZ', 'OPENBLAS_NUM_THREADS'}


class Vault:
    """Authenticated encrypted closure baseline, fsynced before effects; key stays in memory."""
    def __init__(self, path, passphrase, *, create=False):
        self.path = Path(path)
        require(len(passphrase) >= 24, 'VAULT_PASSPHRASE_LENGTH')
        if create:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            self.salt = os.urandom(16)
        else:
            self._check(); raw = self.path.read_bytes()
            require(len(raw) > 16, 'VAULT_INCOMPLETE')
            self.salt = raw[:16]
        key = Scrypt(salt=self.salt, length=32, n=2**14, r=8, p=1).derive(passphrase.encode())
        self.cipher = Fernet(base64.urlsafe_b64encode(key))

    def _check(self):
        s = self.path.lstat()
        require(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o600
                and s.st_nlink == 1 and s.st_size <= VAULT_LIMIT, 'PRIVATE_VAULT_REQUIRED')

    def save(self, value):
        self._check()
        raw = self.salt + self.cipher.encrypt(canonical(value))
        require(len(raw) <= VAULT_LIMIT, 'VAULT_32K_BOUND')
        temporary = self.path.with_name(self.path.name + '.next')
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(raw); f.flush(); os.fsync(f.fileno())
            os.replace(temporary, self.path)
            fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        finally:
            if temporary.exists(): temporary.unlink()

    def load(self):
        self._check()
        return json.loads(self.cipher.decrypt(self.path.read_bytes()[16:]))


class Render:
    """Eight calls / 40 active seconds maximum, no retry and no redirect."""
    def __init__(self, token):
        import requests
        self.token = token; self.calls = 0; self.started = time.monotonic()
        self.session = requests.Session(); self.session.trust_env = False

    def call(self, method, suffix='', body=None):
        allowed = suffix in ('', '/env-vars?limit=100', '/env-vars', '/jobs?limit=100') or (
            suffix.startswith('/jobs/job-') and __import__('re').fullmatch('/jobs/job-[a-z0-9]{20}', suffix))
        require(allowed and method in ('GET', 'PUT') and (method != 'PUT' or suffix == '/env-vars'), 'RENDER_FIXED_OPERATION')
        require(self.calls < 8 and time.monotonic() - self.started < 40, 'RENDER_FINITE_BOUND')
        self.calls += 1
        try:
            with self.session.request(method, 'https://api.render.com/v1/services/' + SERVICE + suffix,
                    headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/json'},
                    json=body, timeout=(3, 5), allow_redirects=False, stream=True) as response:
                require(response.status_code == 200, 'RENDER_RESPONSE_UNCERTAIN')
                raw = bytearray()
                for chunk in response.iter_content(4096):
                    raw.extend(chunk)
                    require(len(raw) <= 32768 and time.monotonic() - self.started < 40, 'RENDER_RESPONSE_BOUND')
                return json.loads(raw)
        except Exception:
            raise RuntimeError('RENDER_RESPONSE_UNCERTAIN_NO_RETRY') from None


def env_values(response):
    require(isinstance(response, list) and len(response) < 100, 'RENDER_COMPLETE_ENV_PAGE_REQUIRED')
    result = {}
    for item in response:
        value = item.get('envVar', item)
        require(isinstance(value, dict) and set(value) >= {'key', 'value'} and
                isinstance(value['key'], str) and isinstance(value['value'], str) and
                value['key'] not in result, 'RENDER_ENV_SHAPE')
        result[value['key']] = value['value']
    return result


def service_guard(value):
    require(value.get('id') == SERVICE and value.get('type') == 'cron_job' and
            value.get('suspended') == 'suspended' and value.get('autoDeploy') == 'no', 'RENDER_SAFETY_CONTROLS')
    found = []
    def walk(v, path=''):
        if isinstance(v, dict):
            for k, x in v.items():
                if k in ('startCommand', 'cronCommand', 'dockerCommand', 'schedule', 'branch', 'buildCommand', 'rootDir', 'plan'):
                    found.append((path + '/' + k, x))
                if isinstance(x, (dict, list)): walk(x, path + '/' + k)
        elif isinstance(v, list):
            for i, x in enumerate(v): walk(x, path + '/' + str(i))
    walk(value)
    commands = [x for p, x in found if p.endswith(('/startCommand', '/cronCommand'))]
    require(commands and all(x == '/bin/true' for x in commands) and
            any(p.endswith('/schedule') and isinstance(x, str) for p, x in found), 'RENDER_COMMAND_SCHEDULE')
    return hashlib.sha256(canonical(found)).hexdigest()


def operation_observation(b,x,operation,*,now=None):
    now=time.time() if now is None else now
    keys={'version','operation','binding_sha256','service_id','observed_at','env_groups','secret_files','inherited_credential_names','reviewed','no_current_work','other_activity_stopped','deployment_id','revision','suspended'}
    require(type(x) is dict and set(x)==keys and x['version']=='FINITE_OPERATION_OBSERVATION_V1' and x['operation']==operation,'OPERATION_OBSERVATION_BINDING')
    require(x['binding_sha256']==hashlib.sha256(canonical(b)).hexdigest() and x['service_id']==SERVICE and x['deployment_id']==b.get('retained_deployment') and x['revision']==b['execution_binding']['revision'],'OPERATION_OBSERVATION_BINDING')
    require(type(x['observed_at']) in (int,float) and 0<=now-x['observed_at']<=300,'OPERATION_OBSERVATION_STALE')
    require(x['env_groups']==[] and x['secret_files']==[] and x['inherited_credential_names']==[] and all(x[k] is True for k in ('reviewed','no_current_work','other_activity_stopped','suspended')),'OPERATION_OBSERVATION_DRIFT')
    return x


def boundary(b,observation=None):
    if 'timing_policy' in b:return operation_observation(b,observation,'HANDOFF')
    x = b.get('inherited_boundary', {})
    require(x.get('service_id') == SERVICE and x.get('env_groups') == [] and x.get('secret_files') == [] and
            x.get('inherited_credential_names') == [] and x.get('reviewed') is True and
            type(x.get('observed_at')) in (int, float) and 0 <= time.time() - x['observed_at'] <= 300,
            'REVIEWED_INHERITED_BOUNDARY_REQUIRED')


def handoff(api, state, save, publication_token, *, observation=None):
    b = state['binding']; boundary(b,observation)
    database=b.get('evidence_backend')=='POSTGRES_PILOT_V1'
    if 'timing_policy' in b:validate_binding(b,opening=True)
    require(state.get('state') == 'ACTIVATION_ACKNOWLEDGED' and 'render' not in state, 'HANDOFF_SINGLE_USE')
    require(time.time() + 960 < b['valid_until'], 'HANDOFF_CREDENTIAL_WINDOW')
    from .intake_owner_operations import installation_token_allowed
    require(publication_token is None if database else installation_token_allowed(publication_token), 'SELF_REVOCABLE_INSTALLATION_TOKEN_REQUIRED')
    require(database or type(b.get('publication_valid_until')) in (int,float) and
            time.time()+960 < b['publication_valid_until'] and (b['valid_until']<=b['publication_valid_until'] if 'timing_policy' in b else b['publication_valid_until']<=b['valid_until']), 'FINITE_SELF_REVOCABLE_PUBLICATION_TOKEN')
    guard = service_guard(api.call('GET'))
    require(guard == b.get('render_config_sha256'), 'RENDER_REVIEWED_CONFIGURATION')
    original = env_values(api.call('GET', '/env-vars?limit=100'))
    new = {k: v for k, v in original.items() if k in KEEP}
    require('PLAYWRIGHT_BROWSERS_PATH' in new, 'RENDER_PROFILE_MAPPING_REQUIRED')
    # The reviewed post-build restoration intentionally has no B profile yet.
    # Carry the exact bound profile in this same finite handoff, never a second
    # configuration write. Any pre-existing different profile remains drift.
    profile = b.get('render_profile')
    require('INGESTION_RENDER_PROFILE' not in original or
            json.loads(original['INGESTION_RENDER_PROFILE']) == profile, 'RENDER_PROFILE_MAPPING_REQUIRED')
    new['INGESTION_RENDER_PROFILE'] = canonical(profile).decode()
    # Browser existence/hash is checked in the job, never guessed on the owner host.
    keys={'mode','service_id','revision','browser_path','browser_sha256','aggregate_bytes',
          'source_rss_bytes','controller_rss_bytes','reserve_bytes','source_seconds'}
    import re
    require(isinstance(profile,dict) and set(profile)==keys and profile['mode']=='render-intake-v1' and
            profile['service_id']==SERVICE and isinstance(profile['browser_path'],str) and
            Path(profile['browser_path']).is_absolute() and '..' not in Path(profile['browser_path']).parts and
            re.fullmatch('[a-f0-9]{64}',profile['browser_sha256']) and
            # Reserve-B runtime supplies the approved directory explicitly to
            # its restricted browser child. Keep the restored service setting
            # (for example Playwright's build selector '0') unchanged; only the
            # child environment must equal the profile. Legacy guards remain.
            (b.get('timing_policy',{}).get('version')=='SEPARATE_EXPIRY_V2_RESERVE' or
             new['PLAYWRIGHT_BROWSERS_PATH']==profile['browser_path']) and
            all(type(profile[k]) is int for k in ('source_rss_bytes','controller_rss_bytes','reserve_bytes','source_seconds')) and
            (profile['source_rss_bytes'],profile['controller_rss_bytes'],profile['reserve_bytes'],profile['source_seconds'])==
            (1073741824,268435456,536870912,75),'EXACT_RENDER_PROFILE_FIELDS_AND_LIMITS')
    require(profile == b.get('render_profile') and profile.get('revision') == b['execution_binding']['revision'] and
            type(profile.get('aggregate_bytes')) is int and profile['aggregate_bytes'] >= 1879048192 and
            profile['aggregate_bytes'] <= 2147483648, 'RENDER_BOUND_INTEGER_PROFILE')
    for role, name in [('ingestion_worker_login', 'INGESTION_WORKER_DATABASE_URL'),
                       ('ingestion_effect_login', 'INGESTION_EFFECT_DATABASE_URL')]:
        new[name] = url(b['route'], role, state['passwords'][role])
    if not database:new['GH_TOKEN'] = publication_token
    boundary(b,observation)
    if 'timing_policy' in b:validate_binding(b,opening=True)
    state['render'] = dict(original=original, expected=new, guard=guard, state='PUT_INTENT_NO_RETRY',
                          publication_token=publication_token, publication_state='NOT_REQUESTED' if database else 'ACTIVE', mapped_at=time.time())
    if 'timing_policy' in b:state['render']['handoff_observation_sha256']=hashlib.sha256(canonical(observation)).hexdigest()
    save(state)
    api.call('PUT', '/env-vars', [{'key': k, 'value': v} for k, v in sorted(new.items())])
    require(env_values(api.call('GET', '/env-vars?limit=100')) == new and service_guard(api.call('GET')) == guard,
            'RENDER_HANDOFF_READBACK')
    state['render']['state'] = 'PUT_ACKNOWLEDGED'; save(state)
    return dict(status='RENDER_HANDOFF_ACKNOWLEDGED', service_id=SERVICE, names=sorted(new), calls=api.calls,**(dict(observation_sha256=state['render']['handoff_observation_sha256']) if 'timing_policy' in b else {}))


def submission_check(api,state,save,observation):
    """Fresh readback and one durable local submission intent; never submits a job."""
    from . import intake_owner as op
    b=state['binding'];op.validate_binding(b,opening=True)
    require('timing_policy' in b and state.get('state')=='ACTIVATION_ACKNOWLEDGED' and state.get('render',{}).get('state')=='PUT_ACKNOWLEDGED','SUBMISSION_HANDOFF_REQUIRED')
    require('submission_state' not in state['render'],'SUBMISSION_PRIOR_INTENT_NO_RETRY')
    operation_observation(b,observation,'SUBMISSION')
    require(service_guard(api.call('GET'))==state['render']['guard'] and env_values(api.call('GET','/env-vars?limit=100'))==state['render']['expected'],'SUBMISSION_CURRENT_STATE_DRIFT')
    operation_observation(b,observation,'SUBMISSION');op.validate_binding(b,opening=True)
    path=Path(b['submission_intent_path'])
    require(path.is_absolute() and str(path.resolve())==str(path) and path.parent==Path(b['release_root']),'SUBMISSION_INTENT_PATH')
    record=dict(version='ONE_B_SUBMISSION_INTENT_V2',binding_sha256=hashlib.sha256(canonical(b)).hexdigest(),observation_sha256=hashlib.sha256(canonical(observation)).hexdigest(),period=b['period'],max_submissions=1,retry=False,checked_at=time.time(),deadline=b['valid_until']-1500)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(canonical(record));f.flush();os.fsync(f.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    state['render']['submission_state']='SUBMISSION_INTENT_NO_RETRY';save(state)
    return dict(status='SUSPENDED_SINGLE_SUBMISSION_READY',period=b['period'],latest_submission_exclusive=b['valid_until']-1500,intent_sha256=hashlib.sha256(canonical(record)).hexdigest(),observation_sha256=record['observation_sha256'],checked_at=record['checked_at'],provider_mutations=0)


def reconcile_handoff(api, state, save):
    r = state['render']; actual = env_values(api.call('GET', '/env-vars?limit=100'))
    result = 'EXPECTED' if actual == r['expected'] else 'ORIGINAL' if actual == r['original'] else 'DRIFT'
    r['reconciliation'] = result; save(state)
    return dict(status='RECONCILIATION_ONLY', observed=result, retry=False)


def submission_ack_timing(b,job):
    # Inform acceptance; never prevent independent containment/restoration.
    try:
        from datetime import datetime
        created=datetime.fromisoformat(job['createdAt'].replace('Z','+00:00')).timestamp()
        return 'WITHIN_APPROVED_DEADLINE' if b['timing_policy']['bound_at']<=created<b['valid_until']-1500 else 'OUTSIDE_APPROVED_DEADLINE'
    except BaseException:return 'UNKNOWN'


def restore_handoff(api, state, save, job_id):
    require(state.get('state') == 'DATABASE_CLOSURE_ACKNOWLEDGED', 'DATABASE_CLOSURE_FIRST')
    r = state['render']
    require(r.get('state')!='RESTORE_INTENT_NO_RETRY','RESTORATION_PRIOR_INTENT_RECONCILE_NO_RETRY')
    require(r.get('state') == 'PUT_ACKNOWLEDGED' or r.get('reconciliation') == 'EXPECTED', 'HANDOFF_RECONCILIATION_REQUIRED')
    # A canceled-before-submission preparation must also have a closure route.
    # Complete (<100) job inventory and no post-handoff creation are required.
    import re
    if job_id is None:
        from datetime import datetime
        jobs=api.call('GET','/jobs?limit=100')
        require(isinstance(jobs,list) and len(jobs)<100,'COMPLETE_JOB_INVENTORY_REQUIRED')
        for item in jobs:
            job=item.get('job',item)
            require(job.get('status') in ('succeeded','failed','canceled') and job.get('finishedAt') and
                    datetime.fromisoformat(job['createdAt'].replace('Z','+00:00')).timestamp()<r['mapped_at'],
                    'JOB_EXISTS_REQUIRES_NAMED_TERMINAL_READBACK')
    else:
        require(re.fullmatch('job-[a-z0-9]{20}', job_id), 'TERMINAL_JOB_ID_REQUIRED')
        job = api.call('GET', '/jobs/' + job_id)
        require(job.get('id') == job_id and job.get('status') in ('succeeded', 'failed', 'canceled') and job.get('finishedAt'),
                'RENDER_JOB_NOT_TERMINAL')
    if 'timing_policy' in state['binding']:
        r['submission_ack_timing']='NO_JOB_VERIFIED' if job_id is None else submission_ack_timing(state['binding'],job)
    require(service_guard(api.call('GET')) == r['guard'] and
            env_values(api.call('GET', '/env-vars?limit=100')) == r['expected'], 'RENDER_RESTORE_DRIFT')
    r['state'] = 'RESTORE_INTENT_NO_RETRY'; save(state)
    api.call('PUT', '/env-vars', [{'key': k, 'value': v} for k, v in sorted(r['original'].items())])
    require(env_values(api.call('GET', '/env-vars?limit=100')) == r['original'] and
            service_guard(api.call('GET')) == r['guard'], 'RENDER_RESTORE_READBACK')
    r['state'] = 'RESTORATION_ACKNOWLEDGED'; r['expected'] = {}; save(state)
    return dict(status='RESTORATION_VERIFIED', service_id=SERVICE, job_id=job_id, calls=api.calls,
                publication_token='WITHDRAWN_FROM_SERVICE_SNAPSHOT_NOT_PROVIDER_REVOKED',
                **(dict(submission_ack_timing=r['submission_ack_timing']) if 'submission_ack_timing' in r else {}))
