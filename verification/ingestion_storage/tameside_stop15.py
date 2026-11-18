"""STOP15-only continuation with distinct stopped correction deployment.

Owner code and corrected deployed runtime have deliberately separate identities.
Compilation is offline. Returned SQL/command bytes require amendment acceptance.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from . import release_candidate
from .tameside_package import PERIOD
from .tameside_preparation import require

BASE_RUNTIME = '9524503fa90228f31d48d16a58121c45d3eb90b8'
RUNTIME = 'dd36ba711932e9f831daf7e885e40447be43d41d'
CHECKPOINT = '0e6d08aa0b6e04c669998a828924e30322bab4ac73a0cf157a9d63b5fac955af'
OLD_MANIFEST = 'dd4d381be32c592bf8346172c538305662953beb259b1fe7b6d880acd2f46e54'
OLD_INDEX = '276e45cecd898b12ea1d2c427c230febbe4714d9ea32bf60ab3798ac05c73496'
OLD_BOUND = 1794954750.6068778
DEPLOYMENT = 'dep-dbud93o8v5cc738opj1g'
COMPLETED = ('BUILD_CONFIGURATION','BUILD_ENVIRONMENT','ONE_RESUME_BUILD',
    'RESUSPEND','RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT',
    'DISPOSITIONS','WRITER')
OWNER_FILES = ('release_candidate.py','tameside_owner_access.py','tameside_stop15.py','tameside_stop15_run.py','stop15_replacement.py','tameside_owner_journal.py','tameside_journal_capacity.py','tameside_contained.py')


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def retained_start(state, *, ordinal, sha256):
    """Exact retained state, not a count-only or caller-asserted STOP proof."""
    require(ordinal == 18 and sha256 == CHECKPOINT, 'STOP15_CHECKPOINT_IDENTITY')
    require(state.get('status') == 'STOPPED_PACKAGE_SEALED'
        and state.get('source_revision') == BASE_RUNTIME
        and state.get('deployment') == DEPLOYMENT, 'STOP15_RETAINED_BUILD')
    require(state.get('bound_at') == OLD_BOUND
        and state.get('manifest',{}).get('manifest_binding_sha256') == OLD_MANIFEST
        and hashlib.sha256(json.dumps(state['package_index'],sort_keys=True,indent=2).encode()).hexdigest() == OLD_INDEX,
        'STOP15_ELAPSED_PACKAGE')
    require(set(state.get('intents',{})) == set(COMPLETED)
        and all(state['intents'][n].get('state')=='ACKNOWLEDGED' for n in COMPLETED),
        'STOP15_COMPLETED_EFFECTS')
    require(state.get('cleanup_reserve',{}).get('cleanup_writes') == 0
        and not any(k in state for k in ('access','binding','job','first_failure','continuation')),
        'STOP15_PRIOR_CONTINUATION')
    return copy.deepcopy(state)


def worker_command(root, code, value):
    """Isolated exact worker checkout; never spoof RENDER_GIT_COMMIT."""
    root=Path(root).resolve()
    require(subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],
        text=True,timeout=5).strip()==RUNTIME, 'STOP15_RUNTIME_PIN')
    subprocess.run(['git','-C',str(root),'diff','--exit-code','HEAD','--'],
        check=True,stdout=subprocess.DEVNULL,timeout=5)
    env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','TZ')}
    result=subprocess.run([sys.executable,'-B','-c',code],cwd=root,env=env,
        input=canonical(value),capture_output=True,timeout=15,check=False)
    require(result.returncode==0 and len(result.stdout)<=262144,'STOP15_WORKER_COMPILER_REFUSED')
    return json.loads(result.stdout)


def compile_remaining(runtime_root, manifest, *, bound_at, owner_journal_source, contained_start=False):
    """Corrected runtime seals its own identity; corrected owner supplies only install.

    No repeated recovery or completed installation artifact appears in the returned set.
    The original elapsed package remains in its original journal row unchanged.
    """
    code="""import sys,json,base64
from verification.ingestion_storage.tameside_package import compile_package
v=json.load(sys.stdin)
f=compile_package(v['manifest'],bound_at=v['bound_at'],owner_journal_source=v['source'])
print(json.dumps({k:base64.b64encode(b).decode() for k,b in f.items()}))
"""
    original=worker_command(runtime_root,code,dict(manifest=manifest,bound_at=bound_at,source=owner_journal_source))
    files={k:base64.b64decode(v,validate=True) for k,v in original.items()}
    policy=json.loads(files['policy.json'])
    require(policy['execution_binding']['revision']==RUNTIME,'STOP15_POLICY_RUNTIME')
    files['campaign-install.sql']=release_candidate.render_campaign_install(
        as_of=datetime.fromtimestamp(bound_at,timezone.utc),period=PERIOD,policy=policy,
        release_manifest_sha256=manifest['manifest_binding_sha256']).encode()
    for name in ('owner-journal-install.sql','private-writer-install.sql','package.json'):
        del files[name]
    owner={p:hashlib.sha256(Path(__file__).with_name(p).read_bytes()).hexdigest() for p in OWNER_FILES}
    index=dict(version=1,kind='STOP15_CONTINUATION_INACTIVE',worker_revision=RUNTIME,
        owner_files=owner,prior_deployment=DEPLOYMENT,replacement_revision=RUNTIME,prior_checkpoint=dict(ordinal=18,sha256=CHECKPOINT),
        elapsed=dict(manifest_sha256=OLD_MANIFEST,package_sha256=OLD_INDEX,bound_at=OLD_BOUND),
        bound_at=bound_at,latest_submission=bound_at+600,access_deadline=bound_at+2100,
        files={k:dict(sha256=hashlib.sha256(v).hexdigest(),bytes=len(v)) for k,v in files.items()})
    if contained_start:
        from . import tameside_contained as contained
        index.update(kind='CONTAINED_STOP15_CONTINUATION_INACTIVE',prior_checkpoint=dict(ordinal=34,sha256=contained.CHECKPOINT),retained_deployment=contained.DEPLOYMENT,replacement_required=False,cleanup_consumed=contained.USED)
        index.pop('replacement_revision');index.pop('prior_deployment')
    files['continuation.json']=json.dumps(index,sort_keys=True,indent=2).encode()
    return files


def campaign_acl(connection):
    rows=connection.execute("SELECT pg_get_userbyid(x.grantee),x.privilege_type,x.is_grantable "
        "FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x "
        "WHERE p.oid='public.ingestion_register_campaign_once(jsonb)'::regprocedure "
        "AND x.grantee<>p.proowner ORDER BY 1").fetchall()
    require(rows==[('ingestion_worker','EXECUTE',False),('postgres','EXECUTE',False)],
        'STOP15_CAMPAIGN_ACL')


def one_sql(db, journal, state, *, name, sql, observe, defer_ack=False):
    """Reuse durable intent/CAS: ambiguous effects are read, never resubmitted.

    observe must use a separate read-only connection and exact installed/state
    expectations. This helper cannot run an already completed preparation phase.
    """
    require(name in ('CAMPAIGN','RELEASE'),'STOP15_REPLAY_FORBIDDEN')
    key='STOP15_'+name
    entry=state['intents'].get(key)
    digest=hashlib.sha256(sql.encode()).hexdigest()
    def save():
        wanted=copy.deepcopy(state)
        try:journal.save(wanted)
        except Exception:
            require(read_journal(journal)==wanted,'STOP15_JOURNAL_ACK_UNKNOWN')
        require(read_journal(journal)==wanted,'STOP15_JOURNAL_READBACK')
        state.clear();state.update(wanted)
    if entry is None:
        state['intents'][key]=dict(state='INTENT',sql_sha256=digest)
        save()  # no transaction starts until durable intent is read back
        try:
            with db.connection() as c:c.execute(sql)
        except Exception:
            require(observe(),'STOP15_EFFECT_UNKNOWN')
    else:
        require(entry.get('sql_sha256')==digest,'STOP15_INTENT_DRIFT')
    require(observe(),'STOP15_EFFECT_UNKNOWN')
    if state['intents'][key]['state']!='ACKNOWLEDGED':
        state['intents'][key]['state']='ACKNOWLEDGED'
        if not defer_ack:save()
    return state


def read_journal(journal):
    db=journal.db
    class ReadOnly:
        key=db.key
        @contextmanager
        def connection(self):
            with db.connection() as c:
                c.execute('BEGIN READ ONLY')
                try:yield c
                finally:c.execute('ROLLBACK')
    journal.db=ReadOnly()
    try:return journal.load()
    finally:journal.db=db


def capacity(journal, retained, projected_states):
    """Validate actual encrypted sizes using the frozen journal without writes."""
    from . import tameside_contained as contained
    require((18<=journal.ordinal<=20 and retained['cleanup_reserve']['cleanup_writes']==0) or contained.projectable(journal,retained),
        'STOP15_CAPACITY_BASELINE')
    require(0<len(projected_states)<=47-journal.ordinal,'STOP15_NORMAL_ROW_BUDGET')
    import copy
    probe=copy.copy(journal);probe.state=copy.deepcopy(retained)
    sizes=[]
    for state in projected_states:
        state=copy.deepcopy(state)
        sizes.append(probe.save(state,validate_only=True))
        probe.ordinal+=1;probe.state=state
    # The original journal reserves these bytes for closure. Do not substitute
    # only row arithmetic for the existing exact encryption/byte ceiling.
    return dict(start_ordinal=journal.ordinal,normal_remaining=47-journal.ordinal,cleanup_reserved=16-retained['cleanup_reserve']['cleanup_writes'],
        projected_last_normal_ordinal=probe.ordinal,
        projected_normal_writes=len(projected_states),projected_ciphertext_bytes=sizes)
