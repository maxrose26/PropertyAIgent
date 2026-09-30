"""Sole Render cron ownership. No time lease and no advisory-lock fallback."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
import uuid
from app.pipeline.discovery_config import is_production_runtime, require_discovery_enabled

SERVICE_ID = "crn-d9sv93vavr4c73f98rb0"
CONTRACT = 1
# No observed scheduled-job identity contract yet. Never infer one from the
# shell's shl-* identity or allow an environment flag to attest to itself.
# A reviewed platform identity contract must be committed before activation.
SCHEDULED_INSTANCE_PATTERN = None
SCHEDULER_CONTRACT = "render-scheduled-v1"


def verified_scheduled_instance(instance):
    return bool(isinstance(instance, str) and not instance.startswith("shl-")
                and SCHEDULED_INSTANCE_PATTERN is not None
                and re.fullmatch(SCHEDULED_INSTANCE_PATTERN, instance))


def require_scheduled_identity():
    instance = os.getenv("RENDER_INSTANCE_ID")
    if (os.getenv("RENDER_SERVICE_TYPE") != "cron" or
            os.getenv("RENDER_SERVICE_ID") != SERVICE_ID or not instance):
        raise RuntimeError("discovery owner runtime identity invalid")
    if not verified_scheduled_instance(instance):
        raise RuntimeError("scheduled-job identity unverified; shell/other execution rejected")
    return instance



def process_identity(pid):
    try:
        import psutil
        p = psutil.Process(pid)
        return None if p.status() == psutil.STATUS_ZOMBIE else p.create_time()
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return None


def boot_identity():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


class DiscoveryOwner:
    def __init__(self, path='/tmp/propertyaigent-discovery.lock'):
        self.path = path
        self.fd = None
        self.identity = None

    def __enter__(self):
        import fcntl
        require_discovery_enabled()
        if is_production_runtime():
            require_scheduled_identity()
        boot = boot_identity()
        started = process_identity(os.getpid())
        if started is None:
            raise RuntimeError('supervisor process identity unavailable')
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise RuntimeError('discovery owner still active') from None
        self.identity = dict(version=CONTRACT, invocation=str(uuid.uuid4()),
            service=os.getenv('RENDER_SERVICE_ID', 'local'),
            instance=os.getenv('RENDER_INSTANCE_ID', boot), boot=boot,
            pid=os.getpid(), pid_start=started)
        if is_production_runtime():
            self.identity["scheduler_contract"] = SCHEDULER_CONTRACT
        return self

    def __exit__(self, *args):
        # Do not LOCK_UN: inherited open description retains lock until last child closes.
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def child_environment(self, run_id):
        return {**os.environ, 'PROPERTYAIGENT_OWNER': json.dumps(self.identity),
                'PROPERTYAIGENT_OWNER_FD': str(self.fd), 'PROPERTYAIGENT_OWNER_PATH': self.path, 'PROPERTYAIGENT_RUN_ID': str(run_id)}


def verify_child():
    """Check inherited locked file description, not just an environment claim."""
    require_discovery_enabled()
    if is_production_runtime():
        require_scheduled_identity()
    raw = os.getenv('PROPERTYAIGENT_OWNER')
    if not raw and not is_production_runtime():
        return None
    if not raw:
        raise RuntimeError('standalone production discovery is blocked')
    import fcntl
    owner = json.loads(raw)
    fd = int(os.environ['PROPERTYAIGENT_OWNER_FD'])
    path = os.environ['PROPERTYAIGENT_OWNER_PATH']
    actual, expected = os.fstat(fd), os.stat(path)
    if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
        raise RuntimeError('child lock descriptor mismatch')
    if is_production_runtime() and (
        owner.get('service') != SERVICE_ID or owner.get('scheduler_contract') != SCHEDULER_CONTRACT or os.getenv('RENDER_SERVICE_TYPE') != 'cron'
        or os.getenv('PROPERTYAIGENT_DISCOVERY_ACTIVATED') != '1'):
        raise RuntimeError('child production activation blocked')
    if owner['service'] != os.getenv('RENDER_SERVICE_ID', 'local') or owner['instance'] != os.getenv('RENDER_INSTANCE_ID', boot_identity()):
        raise RuntimeError('child owner runtime mismatch')
    # Inherited descriptor already owns lock. A separately opened fd must conflict.
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    check = os.open(path, os.O_RDWR)
    try:
        try:
            fcntl.flock(check, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            raise RuntimeError('child lock is not exclusively held')
    finally:
        os.close(check)
    return owner


def terminal_evidence(old, new):
    if not old or old.get('version') != CONTRACT:
        return None  # historical record; not an owner
    if old['invocation'] == new['invocation']:
        return None
    if old['service'] == new['service'] == SERVICE_ID and old['instance'] != new['instance']:
        if all(identity.get('scheduler_contract') == SCHEDULER_CONTRACT
               and verified_scheduled_instance(identity.get('instance')) for identity in (old, new)):
            return 'same_service_successor_admitted'
        raise RuntimeError('competing discovery ownership unresolved: scheduler identity unverified')
    if old.get('boot') == new.get('boot') and old.get('instance') == new.get('instance'):
        identities = [(old['pid'], old['pid_start'])]
        if old.get('child_pid'):
            identities.append((old['child_pid'], old['child_start']))
        if all(process_identity(pid) != started for pid, started in identities):
            return 'same_host_processes_exited'
    raise RuntimeError('competing discovery ownership unresolved')


def reconcile_owners(session, owner):
    import datetime as dt
    from sqlalchemy import select
    from app.db.models import ScrapeRun, ParentLookupWork
    now = dt.datetime.now(dt.timezone.utc)
    for run in session.scalars(select(ScrapeRun).where(
            (ScrapeRun.status == 'running') | ScrapeRun.id.in_(select(
                ParentLookupWork.owner_scrape_run_id).where(ParentLookupWork.last_outcome == 'in_flight')))):
        progress = json.loads(run.progress or '{}')
        old = progress.get('owner')
        evidence = terminal_evidence(old, owner.identity)
        if not evidence:
            continue
        if run.status == 'running':
            run.status = 'failed'
            run.finished_at = now
        progress['recovery'] = dict(reason='interrupted_confirmed', evidence=evidence,
            observed_at=now.isoformat(), successor=owner.identity, finished_at_is_reconciliation=True)
        run.progress = json.dumps(progress)
        for work in session.scalars(select(ParentLookupWork).where(
                ParentLookupWork.owner_scrape_run_id == run.id, ParentLookupWork.last_outcome == 'in_flight')):
            work.last_outcome = None
            work.owner_scrape_run_id = None
            work.next_eligible_at = now
            work.reason = 'interrupted_unknown'
        session.commit()


def release_interrupted_work(session, run_id):
    """Only called after the owned process group has been terminated and reaped."""
    import datetime as dt
    from sqlalchemy import update
    from app.db.models import ParentLookupWork
    session.execute(update(ParentLookupWork).where(
        ParentLookupWork.owner_scrape_run_id == run_id,
        ParentLookupWork.last_outcome == 'in_flight').values(
        last_outcome=None, owner_scrape_run_id=None,
        next_eligible_at=dt.datetime.now(dt.timezone.utc), reason='interrupted_unknown'))
    session.commit()
