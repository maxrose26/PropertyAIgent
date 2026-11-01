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
from .intake_owner import require
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


def boundary(b):
    x = b.get('inherited_boundary', {})
    require(x.get('service_id') == SERVICE and x.get('env_groups') == [] and x.get('secret_files') == [] and
            x.get('inherited_credential_names') == [] and x.get('reviewed') is True and
            type(x.get('observed_at')) in (int, float) and 0 <= time.time() - x['observed_at'] <= 300,
            'REVIEWED_INHERITED_BOUNDARY_REQUIRED')


def handoff(api, state, save, publication_token):
    b = state['binding']; boundary(b)
    require(state.get('state') == 'ACTIVATION_ACKNOWLEDGED' and 'render' not in state, 'HANDOFF_SINGLE_USE')
    require(time.time() + 960 < b['valid_until'], 'HANDOFF_CREDENTIAL_WINDOW')
    from .intake_owner_operations import installation_token_allowed
    require(installation_token_allowed(publication_token), 'SELF_REVOCABLE_INSTALLATION_TOKEN_REQUIRED')
    require(type(b.get('publication_valid_until')) in (int,float) and
            time.time()+960 < b['publication_valid_until'] <= b['valid_until'], 'FINITE_SELF_REVOCABLE_PUBLICATION_TOKEN')
    guard = service_guard(api.call('GET'))
    require(guard == b.get('render_config_sha256'), 'RENDER_REVIEWED_CONFIGURATION')
    original = env_values(api.call('GET', '/env-vars?limit=100'))
    new = {k: v for k, v in original.items() if k in KEEP}
    require('INGESTION_RENDER_PROFILE' in new and 'PLAYWRIGHT_BROWSERS_PATH' in new, 'RENDER_PROFILE_MAPPING_REQUIRED')
    # Browser existence/hash is checked in the job, never guessed on the owner host.
    profile = json.loads(new['INGESTION_RENDER_PROFILE'])
    keys={'mode','service_id','revision','browser_path','browser_sha256','aggregate_bytes',
          'source_rss_bytes','controller_rss_bytes','reserve_bytes','source_seconds'}
    import re
    require(isinstance(profile,dict) and set(profile)==keys and profile['mode']=='render-intake-v1' and
            profile['service_id']==SERVICE and isinstance(profile['browser_path'],str) and
            Path(profile['browser_path']).is_absolute() and '..' not in Path(profile['browser_path']).parts and
            re.fullmatch('[a-f0-9]{64}',profile['browser_sha256']) and
            new['PLAYWRIGHT_BROWSERS_PATH']==profile['browser_path'] and
            all(type(profile[k]) is int for k in ('source_rss_bytes','controller_rss_bytes','reserve_bytes','source_seconds')) and
            (profile['source_rss_bytes'],profile['controller_rss_bytes'],profile['reserve_bytes'],profile['source_seconds'])==
            (1073741824,268435456,536870912,75),'EXACT_RENDER_PROFILE_FIELDS_AND_LIMITS')
    require(profile == b.get('render_profile') and profile.get('revision') == b['execution_binding']['revision'] and
            type(profile.get('aggregate_bytes')) is int and profile['aggregate_bytes'] >= 1879048192 and
            profile['aggregate_bytes'] <= 2147483648, 'RENDER_BOUND_INTEGER_PROFILE')
    for role, name in [('ingestion_worker_login', 'INGESTION_WORKER_DATABASE_URL'),
                       ('ingestion_effect_login', 'INGESTION_EFFECT_DATABASE_URL')]:
        new[name] = url(b['route'], role, state['passwords'][role])
    new['GH_TOKEN'] = publication_token
    state['render'] = dict(original=original, expected=new, guard=guard, state='PUT_INTENT_NO_RETRY',
                          publication_token=publication_token, publication_state='ACTIVE', mapped_at=time.time())
    save(state)
    api.call('PUT', '/env-vars', [{'key': k, 'value': v} for k, v in sorted(new.items())])
    require(env_values(api.call('GET', '/env-vars?limit=100')) == new and service_guard(api.call('GET')) == guard,
            'RENDER_HANDOFF_READBACK')
    state['render']['state'] = 'PUT_ACKNOWLEDGED'; save(state)
    return dict(status='RENDER_HANDOFF_ACKNOWLEDGED', service_id=SERVICE, names=sorted(new), calls=api.calls)


def reconcile_handoff(api, state, save):
    r = state['render']; actual = env_values(api.call('GET', '/env-vars?limit=100'))
    result = 'EXPECTED' if actual == r['expected'] else 'ORIGINAL' if actual == r['original'] else 'DRIFT'
    r['reconciliation'] = result; save(state)
    return dict(status='RECONCILIATION_ONLY', observed=result, retry=False)


def restore_handoff(api, state, save, job_id):
    require(state.get('state') == 'DATABASE_CLOSURE_ACKNOWLEDGED', 'DATABASE_CLOSURE_FIRST')
    r = state['render']
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
    require(service_guard(api.call('GET')) == r['guard'] and
            env_values(api.call('GET', '/env-vars?limit=100')) == r['expected'], 'RENDER_RESTORE_DRIFT')
    r['state'] = 'RESTORE_INTENT_NO_RETRY'; save(state)
    api.call('PUT', '/env-vars', [{'key': k, 'value': v} for k, v in sorted(r['original'].items())])
    require(env_values(api.call('GET', '/env-vars?limit=100')) == r['original'] and
            service_guard(api.call('GET')) == r['guard'], 'RENDER_RESTORE_READBACK')
    r['state'] = 'RESTORATION_ACKNOWLEDGED'; r['expected'] = {}; save(state)
    return dict(status='RESTORATION_VERIFIED', service_id=SERVICE, job_id=job_id, calls=api.calls,
                publication_token='WITHDRAWN_FROM_SERVICE_SNAPSHOT_NOT_PROVIDER_REVOKED')
