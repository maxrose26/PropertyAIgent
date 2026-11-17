"""Stopped preparation using the existing recovery, encrypted journal and Render IO.

No implicit production authority. Recovery precedes namespace installation and
deployment. Ambiguous provider effects are observed, never resubmitted. The
caller supplies the already verified owner route and frozen #213 module.
"""
import copy
import hashlib
import json
import time
from pathlib import Path
from contextlib import contextmanager

from . import bolton_recovery_guard, tameside_owner_journal as journal_api
from .tameside_package import PERIOD
from .tameside_candidate import EXPIRY

BUILD_COMMAND = ('pip install -r requirements.txt && python -m '
                 'verification.ingestion_storage.tameside_build_receipt')
COMMITTED = 'COMMITTED_STATE_VERIFIED_READ_ONLY'
CHECKPOINT_SHA = 'a5ba6be74c47eea89bd5068111bf3bc65198c8b4fd54c5036394a2c512f55c52'


def pinned_modules(root):
    """Keep the frozen relative imports separate from the candidate package."""
    import importlib
    import importlib.util
    import subprocess
    import sys
    root=Path(root).resolve()
    require(subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],
        text=True,timeout=10).strip()=='f027ba28af69ae70208eab5ed047e4a8a81c6337',
        'PREPARATION_FROZEN_REVISION')
    subprocess.run(['git','-C',str(root),'diff','--quiet','HEAD','--','verification'],
                   check=True,timeout=10)
    name='_tameside_frozen_owner'
    path=root/'verification/ingestion_storage/__init__.py'
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,path,submodule_search_locations=[str(path.parent)])
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    require(Path(sys.modules[name].__file__).resolve()==path,'PREPARATION_FROZEN_IMPORT_DRIFT')
    return (importlib.import_module(name+'.owner_pilot'),
            importlib.import_module(name+'.bolton01_settlement'),
            importlib.import_module(name+'.intake_successor').owner_sql())


def original_checkpoint(pinned, db):
    class ReadOnly:
        key = db.key
        @contextmanager
        def connection(self):
            with db.connection() as c:
                c.execute('BEGIN READ ONLY')
                try:
                    yield c
                finally:
                    c.execute('ROLLBACK')
    j = pinned.Journal(ReadOnly(),period=pinned.PERIOD)
    j.period='b-bolton-20261103-1105-01'
    j.owner_period=j.period+'_owner'
    j.owner_run=hashlib.sha256(j.owner_period.encode()).hexdigest()[:32]
    state=j.load()
    require(state and state.get('status')=='CLOSED' and j.ordinal==55 and
            j.previous==CHECKPOINT_SHA, 'PREPARATION_ORIGINAL_CHECKPOINT_DRIFT')
    return state


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def installed_journal(db, source):
    """Independently recognise only the original or exact revised function."""
    journal_api.render_install(source)  # frozen source validation
    expected = source.replace(" IF p_period NOT IN (",
        " IF p_period NOT IN ('"+journal_api.JOURNAL+"',", 1).split('$owner_state$')[1]
    with db.connection() as c:
        c.execute('BEGIN READ ONLY')
        try:
            row = c.execute("SELECT prosrc,proowner='ingestion_storage_owner'::regrole,"
                "prosecdef,proconfig FROM pg_proc WHERE oid="
                "'public.ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()
            require(row and row[1:] == (True, True, ['search_path=pg_catalog']),
                    'PREPARATION_JOURNAL_BOUNDARY')
            require(c.execute("SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),"
                "pg_has_role(current_user,'ingestion_storage_owner','SET'),"
                "has_schema_privilege('ingestion_storage_owner','public','CREATE')").fetchone()
                == (False, False, False), 'PREPARATION_PERMISSIONS_NOT_RESTORED')
            if row[0] == expected:
                return True
            require(hashlib.sha256(row[0].encode()).hexdigest() == journal_api.BODY_SHA,
                    'PREPARATION_JOURNAL_DRIFT')
            return False
        finally:
            c.execute('ROLLBACK')


def recover_and_install(db, *, recovery, binding, journal_source, interrupt=lambda _: None):
    """Resume by independent state, not by repeating an uncertain transaction.

    The existing original checkpoint and recovery inspector remain usable before
    the new namespace exists. Installation changes no historical journal rows.
    """
    require(hashlib.sha256(Path(recovery.__file__).read_bytes()).hexdigest()==
            bolton_recovery_guard.SOURCE_SHA256,'PREPARATION_RECOVERY_SOURCE_DRIFT')
    installed=installed_journal(db,journal_source)
    inspector=recovery.inspect
    if installed:
        # Frozen inspector remains intact except its source-derived journal
        # inventory expectation. No observed hash is accepted as an expectation.
        # Clone function namespaces, never mutate the imported recovery module.
        from types import FunctionType, SimpleNamespace
        expected=journal_source.replace(" IF p_period NOT IN (",
            " IF p_period NOT IN ('"+journal_api.JOURNAL+"',",1).split('$owner_state$')[1]
        baseline=recovery.a06.baseline
        verifier=baseline.__globals__['verify_inventory']
        contracts=verifier.__globals__['function_contracts']
        def revised_contracts():
            values=copy.deepcopy(contracts())
            for value in values:
                if value['name']=='ingestion_intake_owner_state':
                    value['sha256']=hashlib.sha256(expected.encode()).hexdigest()
            return values
        def clone(fn,**changes):
            return FunctionType(fn.__code__,dict(fn.__globals__,**changes),fn.__name__,fn.__defaults__,fn.__closure__)
        verify=clone(verifier,function_contracts=revised_contracts)
        a06=SimpleNamespace(**dict(vars(recovery.a06),baseline=clone(baseline,verify_inventory=verify)))
        inspector=clone(recovery.inspect,common=clone(recovery.common,a06=a06))
    with db.connection() as c:
        observed = inspector(c, binding)
    if observed['status'] != COMMITTED:
        require(observed['status'] == 'READY_FOR_REVIEW_NOT_AUTHORISED',
                'PREPARATION_RECOVERY_UNKNOWN')
        require(time.time()+2100<=EXPIRY,'PREPARATION_EXPIRY_RESERVE')
        try:
            with db.connection() as c:
                bolton_recovery_guard.recover(c, binding, pinned_module=recovery)
        except Exception:
            with db.connection() as c:
                checked = recovery.inspect(c, binding)
            require(checked['status'] == COMMITTED, 'PREPARATION_RECOVERY_UNCERTAIN')
    with db.connection() as c:
        observed = inspector(c, binding)
    require(observed['status'] == COMMITTED and observed['stop'] == recovery.STOP15,
            'PREPARATION_RECOVERY_READBACK')
    interrupt('RECOVERY_READBACK')
    if not installed_journal(db, journal_source):
        require(time.time()+2100<=EXPIRY,'PREPARATION_EXPIRY_RESERVE')
        try:
            with db.connection() as c:
                c.execute(journal_api.render_install(journal_source))
        except Exception:
            require(installed_journal(db, journal_source), 'PREPARATION_INSTALL_UNCERTAIN')
    require(installed_journal(db, journal_source), 'PREPARATION_INSTALL_READBACK')
    interrupt('JOURNAL_INSTALLED')
    return observed


class StoppedDeployment:
    """Resumable build only. Never clears a stop, grants login or submits a job.

    Provider is the frozen Render.call interface; every write has a separately
    decrypted durable intent BEFORE dispatch. A pending intent is read back and
    never sent again. False/ambiguous readback requires containment/review.
    """
    def __init__(self, pinned, db, api_factory, *, revision, checkpoint, baseline,
                 interrupt=lambda _: None, clock=time.time):
        require(len(revision) == 40 and all(c in '0123456789abcdef' for c in revision),
                'PREPARATION_REVISION')
        self.pinned, self.db, self.api_factory = pinned, db, api_factory
        self.revision, self.interrupt, self.clock = revision, interrupt, clock
        self.provider_calls=0;self.provider_bytes=0;self.provider_started=time.monotonic()
        self.checkpoint, self.baseline = copy.deepcopy(checkpoint), copy.deepcopy(baseline)
        require(checkpoint.get('ordinal') == 55 and checkpoint.get('sha256') == CHECKPOINT_SHA,
                'PREPARATION_ORIGINAL_CHECKPOINT')
        original=original_checkpoint(pinned,db)
        require(original['original_environment']==baseline['environment'] and
                original['original_service']==baseline['service'], 'PREPARATION_RESTORATION_BASELINE')
        self.journal = journal_api._bound_journal(pinned, db)
        state = self.journal.load()
        if state is None:
            require(self.clock()+2100<=EXPIRY,'PREPARATION_EXPIRY_RESERVE')
            current_service=self.call('GET')
            current_guard=pinned.service_guard(current_service)
            require(current_guard == original.get('original_guard',pinned.service_guard(baseline['service']))
                    and self.environment() == baseline['environment'], 'PREPARATION_PROVIDER_BASELINE_DRIFT')
            if 'original_guard' in original:
                require(current_guard==original['original_guard'],'PREPARATION_RETAINED_GUARD_DRIFT')
            configured=copy.deepcopy(current_service)
            configured['branch']='pa-tam002/'+revision
            configured['serviceDetails']['envSpecificDetails'].update(
                buildCommand=BUILD_COMMAND,startCommand='/bin/true')
            self.pinned.complete_inventory(self.call('GET','/jobs?limit=100'),'job')
            deploys=self.pinned.complete_inventory(self.call('GET','/deploys?limit=100'),'deploy')
            require(sorted(r['id'] for r in deploys)==sorted(baseline['deploy_ids']),
                    'PREPARATION_DEPLOY_BASELINE_DRIFT')
            state = dict(period=PERIOD, status='STOPPED_PREPARATION',
                source_revision=revision, original_checkpoint=checkpoint,
                original_service=baseline['service'], original_environment=baseline['environment'],
                original_guard=current_guard, build_guard=pinned.service_guard(configured),
                original_deploy_ids=baseline['deploy_ids'], intents={},
                cleanup_reserve=dict(pinned.cleanup_reserve_policy(), cleanup_writes=0))
            self.state = state
            self.save()
        else:
            require(state.get('source_revision') == revision and
                    state.get('original_checkpoint') == checkpoint and
                    state.get('original_service') == baseline['service'] and
                    state.get('original_environment') == baseline['environment'] and
                    state.get('original_deploy_ids') == baseline['deploy_ids'],
                    'PREPARATION_EXISTING_OPERATION_DRIFT')
            self.state = state
        if self.state['cleanup_reserve'].get('cleanup_writes',0):
            self.journal.cleanup_mode=True
        self.interrupt('CHECKPOINT_READY')

    def call(self, method, path='', body=None):
        require(self.provider_calls<40 and time.monotonic()-self.provider_started<40,
                'PREPARATION_PROVIDER_PHASE_BOUND')
        self.provider_calls+=1
        api = self.api_factory()
        try:
            result=api.call(method, path, body)
            self.provider_bytes+=len(json.dumps(result).encode())
            require(self.provider_bytes<=786432 and time.monotonic()-self.provider_started<40,
                    'PREPARATION_PROVIDER_RESULT_BOUND')
            return result
        finally:
            api.close()

    def save(self):
        wanted = copy.deepcopy(self.state)
        cleanup=bool(getattr(self.journal,'cleanup_mode',False))
        # Journal.save fills reserve accounting in the value passed to it.
        try:
            self.journal.save(wanted)
        except Exception:
            self.journal, observed = journal_api.reconcile(self.pinned, self.db)
            require(observed == wanted, 'PREPARATION_CHECKPOINT_ACK_UNKNOWN')
        self.journal, observed = journal_api.reconcile(self.pinned, self.db)
        self.journal.cleanup_mode=cleanup
        require(observed == wanted, 'PREPARATION_CHECKPOINT_READBACK')
        self.state = observed

    def stopped(self):
        with self.db.connection() as c:
            c.execute('BEGIN READ ONLY')
            try:
                ctl = c.execute("SELECT outcome::jsonb FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                require(ctl.get('hard_stop_generation') == 15 and ctl.get('global_stop') ==
                    {'reason':'DAILY_INTAKE_SHARED_FAILURE'} and ctl.get('manual_stop') in
                    ('DAILY_INTAKE_SHARED_FAILURE','ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'),
                    'PREPARATION_STOP15_CHANGED')
                require(c.execute("SELECT bool_and(NOT rolcanlogin) FROM pg_roles WHERE rolname IN "
                    "('ingestion_worker_login','ingestion_effect_login')").fetchone() == (True,),
                    'PREPARATION_RUNTIME_NOT_DORMANT')
            finally:
                c.execute('ROLLBACK')

    def effect(self, name, method, path, body, matches, *, cleanup=False, before=lambda:None):
        entry = self.state['intents'].get(name)
        if entry is None:
            if not cleanup:
                self.stopped()
                require(self.clock() + 2100 <= EXPIRY, 'PREPARATION_EXPIRY_RESERVE')
            self.state['intents'][name] = dict(state='INTENT', at=self.clock())
            self.save()
            self.interrupt(name+':INTENT')
            if not cleanup:
                self.stopped()
                self.pinned.complete_inventory(self.call('GET','/jobs?limit=100'),'job')
                self.pinned.complete_inventory(self.call('GET','/deploys?limit=100'),'deploy')
            before()
            try:
                self.call(method, path, body)
            except Exception:
                # Read below; never dispatch a second time.
                pass
            self.interrupt(name+':EFFECT')
        if self.state['intents'][name]['state'] == 'ACKNOWLEDGED':
            return
        require(matches(), 'PREPARATION_EFFECT_UNKNOWN:'+name)
        self.state['intents'][name]['state'] = 'ACKNOWLEDGED'
        self.save()
        self.interrupt(name+':READBACK')

    def environment(self):
        return self.pinned.env_values(self.call('GET', '/env-vars?limit=100'))

    def prepare(self):
        """The immutable candidate ref must resolve to revision before calling.

        Ref is pa-tam002/<full SHA>; it is not the moving PR branch. Resuming is
        the sole build dispatch, as in frozen #213; POST /deploys is never used.
        """
        require(not self.state['cleanup_reserve'].get('cleanup_writes',0),
                'PREPARATION_CONTAINED_NO_RESUME')
        service = self.state['original_service']
        harmless = {k:v for k,v in self.state['original_environment'].items()
                    if k in ('PYTHONUNBUFFERED', 'LANG', 'TZ', 'OPENBLAS_NUM_THREADS')}
        configured = copy.deepcopy(service)
        configured['branch'] = 'pa-tam002/'+self.revision
        configured['serviceDetails']['envSpecificDetails'].update(
            buildCommand=BUILD_COMMAND, startCommand='/bin/true')
        guard = self.state['build_guard']
        def unchanged(expected_guard,expected_env):
            require(self.pinned.service_guard(self.call('GET'))==expected_guard and
                    self.environment()==expected_env,'PREPARATION_PREWRITE_DRIFT')
        # No secrets in the build environment, no source command or live flag.
        self.effect('BUILD_ENVIRONMENT', 'PUT', '/env-vars',
            [{'key':k,'value':v} for k,v in sorted(harmless.items())],
            lambda: self.environment() == harmless,
            before=lambda:unchanged(self.state['original_guard'],self.state['original_environment']))
        self.effect('BUILD_CONFIGURATION', 'PATCH', '',
            dict(branch=configured['branch'], serviceDetails=dict(envSpecificDetails=
                dict(buildCommand=BUILD_COMMAND, startCommand='/bin/true'))),
            lambda: self.pinned.service_guard(self.call('GET')) == guard,
            before=lambda:unchanged(self.state['original_guard'],harmless))
        def deployed():
            require(self.clock()-self.state['intents']['ONE_RESUME_BUILD']['at']<300,
                    'PREPARATION_BUILD_POLL_BOUND')
            rows = self.call('GET', '/deploys?limit=100')
            require(type(rows) is list and len(rows)<100, 'PREPARATION_DEPLOY_INVENTORY')
            added = [r.get('deploy',r) for r in rows
                     if r.get('deploy',r)['id'] not in self.state['original_deploy_ids']]
            require(len(added)<=1, 'PREPARATION_OVERLAPPING_DEPLOYMENT')
            if not added:
                return False
            item = added[0]
            require(item.get('commit',{}).get('id') == self.revision, 'PREPARATION_DEPLOY_REVISION')
            self.state['deployment'] = item['id']
            return item.get('status') == 'live'
        # A pending build is deliberately resumable by readback only. The caller
        # polls prepare(), within the original provider/time limits, not POST.
        self.effect('ONE_RESUME_BUILD', 'POST', '/resume', None, deployed,
                    before=lambda:unchanged(guard,harmless))
        self.effect('RESUSPEND', 'POST', '/suspend', None,
                    lambda: self.call('GET').get('suspended') == 'suspended', cleanup=True)
        self.restore()
        require(deployed(), 'PREPARATION_BUILD_READBACK')
        self.state['status'] = 'STOPPED_BUILD_READY'
        self.save()

        return copy.deepcopy(self.state)

    def restore(self, *, containment=False):
        """Existing config/env restoration, journalled and independently checked.

        Call only after provider deployment is terminal and service is suspended.
        This path requires no collection policy or enabled credentials.
        """
        self.pinned.complete_inventory(self.call('GET','/jobs?limit=100'),'job')
        self.pinned.complete_inventory(self.call('GET','/deploys?limit=100'),'deploy')
        require(self.call('GET').get('suspended') == 'suspended', 'PREPARATION_RESTORE_NOT_SUSPENDED')
        original = self.state['original_service']
        details = original['serviceDetails']['envSpecificDetails']
        current_guard=self.pinned.service_guard(self.call('GET'))
        require(current_guard in (self.state['original_guard'],self.state['build_guard']),
                'PREPARATION_RESTORE_CONFIGURATION_DRIFT')
        current_env=self.environment()
        harmless={k:v for k,v in self.state['original_environment'].items()
                  if k in ('PYTHONUNBUFFERED','LANG','TZ','OPENBLAS_NUM_THREADS')}
        require(current_env in (self.state['original_environment'],harmless),
                'PREPARATION_RESTORE_ENVIRONMENT_DRIFT')
        prefix='CONTAIN_' if containment else ''
        if not containment or current_guard!=self.state['original_guard']:
            self.effect(prefix+'RESTORE_BUILD_CONFIGURATION','PATCH','',dict(branch=original['branch'],
            serviceDetails=dict(envSpecificDetails=dict(buildCommand=details['buildCommand'],startCommand='/bin/true'))),
            lambda:self.pinned.service_guard(self.call('GET'))==self.state['original_guard'],cleanup=True)
        if not containment or current_env!=self.state['original_environment']:
            self.effect(prefix+'RESTORE_BUILD_ENVIRONMENT','PUT','/env-vars',
            [{'key':k,'value':v} for k,v in sorted(self.state['original_environment'].items())],
            lambda:self.environment()==self.state['original_environment'],cleanup=True)

    def contain(self):
        """Terminal-only restoration after interrupted preparation, no build retry."""
        self.pinned.complete_inventory(self.call('GET','/deploys?limit=100'),'deploy')
        self.pinned.complete_inventory(self.call('GET','/jobs?limit=100'),'job')
        self.journal.cleanup_mode = True
        self.effect('CONTAIN_SUSPEND','POST','/suspend',None,
            lambda:self.call('GET').get('suspended')=='suspended',cleanup=True)
        self.restore(containment=True)
        self.state['status']='PREPARATION_CONTAINED_NO_SUBMISSION'
        self.save()

def prepare_stopped(db, *, pinned, recovery, binding, journal_source, api_factory,
                    revision, checkpoint, baseline, interrupt=lambda _:None):
    """Actual ordered entry point: recovery/readback -> journal -> durable build.

    Returns while STOP15 is still in force. The existing stopped writer/campaign
    installation, manifest sealing, release, activation and handoff follow only
    after this returns STOPPED_BUILD_READY. No expiry is bound before deployment.
    """
    recover_and_install(db,recovery=recovery,binding=binding,journal_source=journal_source,
                        interrupt=interrupt)
    deployment=StoppedDeployment(pinned,db,api_factory,revision=revision,
        checkpoint=checkpoint,baseline=baseline,interrupt=interrupt)
    return deployment.prepare()
