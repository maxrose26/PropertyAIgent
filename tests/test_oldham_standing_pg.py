"""Two actual command halves, restricted PG17, real gh/loopback API; no council.

The parent is the owner; the child receives only worker/effect URLs on stdin.
Provisioned fixture state is explicitly synthetic, separate from operation cost.
"""
import base64,copy,hashlib,io,json,os,subprocess,sys,time,threading,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url
from tests.storage_gh_fixture import real_gh_store
from tests.oldham_wrapper_fixture import packet,Backend
from tests.e2e_pg_world import settings
from verification.ingestion_storage import oldham_standing_plan as plan,oldham_owner_package as pkg
from verification.ingestion_storage.oldham_standing_owner import StandingOperation
from verification.ingestion_storage.oldham_reuse import InstalledReuse
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_publication import canonical
from verification.ingestion_storage.standing_access import GITHUB
from app.ingestion.ledger import digest

RESULTS=[]


def seed(metadata,path,raw,commit='1'*40):
    sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    metadata.git_objects[sha]=dict(sha=sha,content=base64.b64encode(raw).decode(),encoding='base64')
    metadata.git_objects.setdefault(commit,dict(tree={'sha':'2'*40},parents=[]))
    tree=metadata.git_objects['2'*40]['tree'];tree[:]=[x for x in tree if x['path']!=path];tree.append(dict(path=path,mode='100644',type='blob',sha=sha))


@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
@pytest.mark.parametrize('scenario',['standing_success','standing_nominee','standing_delayed','standing_missing','standing_expired','standing_revoked','standing_wrong_identity','standing_altered','standing_stop','standing_publication','standing_barrier','standing_cancel'])
def test_standing_command(tmp_path,monkeypatch,real_gh_store,scenario):
    settings();metadata,secret,ciphertexts,requests=real_gh_store
    path,sha=packet(tmp_path/'input',records=5,nominees=int(scenario=='standing_nominee'),single_page=True,accept=monkeypatch,reuse=True,tag=scenario)
    p=json.loads(path.read_bytes());b=Backend(path);journal=Journal(tmp_path/'owner');op=None;child=None;worker=None;errors=[]
    # Override only fixture transport, not production command/issuer/writer.
    def cli(c,**kw):
        if c[1:4]==['api','--method','GET']:kw['allow_failure']=True
        return metadata.cli(c,**kw)
    try:
        # Bootstrap the exact retired/expired state with existing fixture, then
        # exercise the already-reviewed explicit historical cleanup first.
        dummy=SimpleNamespace()
        config=b.prepare('DISPOSABLE_FIXTURE_INPUT_ONLY',dummy)
        from verification.ingestion_storage.oldham_owner_once import Operation
        data=pkg.validate(path,sha,disposable=True)
        prelim=Operation(data,journal,None,b);prelim.started=time.monotonic()
        # Reuse config without repeating fixture setup.
        original_prepare=b.prepare;b.prepare=lambda raw,op:config
        prelim.prepare('DISPOSABLE_FIXTURE_INPUT_ONLY',prelim.started);InstalledReuse(prelim).run()
        w=b.world;until=(datetime.now(timezone.utc)+timedelta(days=90)).replace(microsecond=0)
        for role,cap in prelim.life.roles.items():
            password=make_url(w['urls'][role]).password
            w['boot'].execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD {} VALID UNTIL {}').format(sql.Identifier(role),sql.Literal(password),sql.Literal(until.isoformat())))
            with w['connect']('provisioning_migrator') as c:c.execute(sql.SQL('GRANT {} TO {} WITH ADMIN FALSE, INHERIT TRUE, SET FALSE').format(sql.Identifier(cap),sql.Identifier(role)))
        ciphertexts['INGESTION_WORKER_DATABASE_URL']=b'FIXTURE_PRESERVED_WORKER_CIPHERTEXT';ciphertexts['INGESTION_EFFECT_DATABASE_URL']=b'FIXTURE_PRESERVED_EFFECT_CIPHERTEXT'
        before_secrets=copy.deepcopy(ciphertexts)
        before_passwords=w['boot'].execute("SELECT rolname,rolpassword FROM pg_authid WHERE rolname=ANY(%s) ORDER BY 1",(list(prelim.life.roles),)).fetchall()
        value=plan.manifest(p,standing=dict(valid_until=until.isoformat(),state_sha256='0'*64,qualification_sha256='a'*64,credential_preparation_github_calls=0),runtime_admission=dict(run_number=1))
        op=StandingOperation(data,value,Journal(tmp_path/'batch-owner'),None,b);op.github.runner=cli;op.sleep=lambda n:time.sleep(2)
        op.prepare('DISPOSABLE_FIXTURE_INPUT_ONLY',time.monotonic())
        with op.owner.connection() as c:value['standing']['state_sha256']=digest(op._observe_standing(c))
        # New phase starts from exact sealed manifest, no operation data changes.
        op.seal=digest(value);op.owner.bindings['manifest_sha256']=op.seal
        for target,raw in [(str(pkg.QUALIFICATION),data['qraw']),(p['origin']['source_path'],data['source_raw']),(p['origin']['slot_path'],data['slot_raw'])]:seed(metadata,target,raw)
        prior='docs/design/ingestion-operational-execution-'+plan.PREVIOUS+'/completed/'
        seed(metadata,prior+'result-before-publication.json',Path('tests/fixtures/oldham_standing/prior-result.json').read_bytes(),plan.PREVIOUS_COMMIT)
        seed(metadata,prior+'events-prefix.jsonl',Path('tests/fixtures/oldham_standing/prior-events.jsonl').read_bytes(),plan.PREVIOUS_COMMIT)
        # Baseline holder correctly reflects cleanup; no new retirement/install.
        if scenario=='standing_barrier':w['boot'].execute("UPDATE ingestion_work_items SET phase='WRITE_INTENT' WHERE key=repeat('0',64)")
        op.preflight()
        def launch(event,payload):
            nonlocal child,worker
            journal_emit(event,payload)
            if event!='oldham_standing_runtime_launch_ready':return
            ctl=w['boot'].execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            if scenario in ('standing_missing','standing_expired','standing_revoked','standing_stop'):
                if scenario=='standing_missing':ctl['grants'].pop(op.execution['authority'])
                elif scenario=='standing_expired':ctl['grants'][op.execution['authority']]['expires_at']=0
                elif scenario=='standing_revoked':ctl['oldham_allowances'][op.execution['authority']]['revoked']=True
                else:ctl['hard_stop_generation']+=1
                w['boot'].execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
            if scenario=='standing_cancel':(op.journal.root/'STOP').touch()
            if scenario=='standing_altered':
                # Alter the committed claim after readback: runtime hash binding refuses.
                tree=metadata.git_objects[metadata.git_objects[metadata.git_head[0]]['tree']['sha']]['tree']
                entry=next(x for x in tree if x['path']==op.namespace+'/claim/claim.json');old=json.loads(base64.b64decode(metadata.git_objects[entry['sha']]['content']));old['manifest_sha256']='f'*64
                raw=canonical(old);entry['sha']=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest();metadata.git_objects[entry['sha']]=dict(sha=entry['sha'],content=base64.b64encode(raw).decode())
            f=tmp_path/'runtime-fixture.json';out=tmp_path/'runtime-output'
            f.write_text(json.dumps(dict(disposable='LOOPBACK_ONLY',gh=metadata.gh,gh_env=metadata.fixture_env(),native=os.environ.get('OLDHAM_STANDING_NATIVE')=='1')))
            env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','SYSTEMD_EXEC_PID')}
            env.update(DATABASE_URL='sqlite:///:memory:',PYTHONDONTWRITEBYTECODE='1',INGESTION_ACCEPTANCE_DISPOSABLE='PG17_ONLY',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REF='refs/heads/master',GITHUB_SHA=p['revision'],GITHUB_WORKFLOW_SHA=p['revision'],GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ID='12345',OLDHAM_STANDING_AUTHORITY='OLDHAM_STANDING_CAPTURE_SCREENING_V1_OWNER_APPROVED')
            command=[sys.executable,'-I','-B','-c','import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("tests.oldham_standing_rehearsal",run_name="__main__")',str(Path.cwd()),str(f),'--output',str(out),'--claim-commit',payload['claim_commit'],'--release-id',p['release_id'],'--manifest-sha256',op.seal]
            metadata.artifact_state['run']=dict(head_sha=p['revision'],run_number=1,run_attempt=1,path='.github/workflows/stage4-oldham-standing.yml',status='in_progress',conclusion=None)
            child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
            urls={r:w['urls'][r] for r in prelim.life.roles}
            if scenario=='standing_wrong_identity':urls['ingestion_worker_login']=w['urls']['ingestion_application_login']
            stream=('fixture-token\n'+urls['ingestion_worker_login']+'\n'+urls['ingestion_effect_login']+'\n').encode()
            def collect():
                try:
                    stdout,stderr=child.communicate(stream,timeout=120)
                    raw=(out/'final-result.json').read_bytes();events=(out/'events.jsonl').read_bytes()
                    data_zip=io.BytesIO()
                    with zipfile.ZipFile(data_zip,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('final-result.json',raw);z.writestr('events.jsonl',events)
                    blob=data_zip.getvalue();metadata.artifact_state.update(run=dict(head_sha=p['revision'],run_number=1,run_attempt=1,path='.github/workflows/stage4-oldham-standing.yml',status='completed',conclusion='success' if child.returncode==0 else 'failure'),artifact=dict(id=1,name='oldham-standing-12345-'+p['revision'],expired=False,digest='sha256:'+hashlib.sha256(blob).hexdigest()),zip=blob)
                    op._fixture_stdout=stdout;op._fixture_stderr=stderr
                except BaseException as e:errors.append(repr(e))
            worker=threading.Thread(target=collect);worker.start()
        journal_emit=op.journal.emit
        op.journal.emit=launch
        # Owner/issuer emitter remains journal's original bound method; runtime
        # ready is emitted through the instance method so the separate child starts.
        if scenario=='standing_delayed':
            original=op.capture_checkpoint
            def delayed(*a):result=original(*a);time.sleep(1);return result
            op.capture_checkpoint=delayed
        if scenario=='standing_publication':
            original_publish=op.publish
            def lost(files,part):
                result=original_publish(files,part)
                if part=='screening-authority':op.github.mutation_uncertain=True;raise ConnectionError('SYNTHETIC_ACK_LOSS')
                return result
            op.publish=lost
        result=op.execute()
        if worker:worker.join(timeout=125)
        assert not errors,errors
        assert worker is None or not worker.is_alive()
        RESULTS.append(dict(scenario=scenario,owner=result,hosted=None if child is None else json.loads((tmp_path/'runtime-output/final-result.json').read_text()),fixture_setup=w['setup_costs']))
        success=scenario in ('standing_success','standing_nominee','standing_delayed')
        if success:
            assert result['status']=='COMPLETED' and result['cleanup']=='CLOSED',result
            assert result['records']==5 and result['nominees']==int(scenario=='standing_nominee')
            assert result['authority_invalidation']=='VERIFIED' and result['credential_changes']==0
            assert result['accounting']['github']['combined']<=GITHUB['combined']
            assert result['accounting']['administration']['commands']<=240 and result['accounting']['administration']['connections']<=13
        else:assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['cleanup']=='UNCERTAIN',result
        after_passwords=w['boot'].execute("SELECT rolname,rolpassword FROM pg_authid WHERE rolname=ANY(%s) ORDER BY 1",(list(prelim.life.roles),)).fetchall()
        assert before_passwords==after_passwords and before_secrets==ciphertexts
        assert w['boot'].execute("SELECT count(*) FROM pg_stat_activity WHERE usename=ANY(%s)",(list(prelim.life.roles),)).fetchone()[0]==0
        assert not any(m in ('PUT','DELETE') for m,path_ in requests if '/secrets' in path_)
    finally:
        if child is not None and child.poll() is None:child.kill();child.wait(timeout=5)
        if worker is not None and worker.is_alive():worker.join(timeout=5)
        b.close()


def teardown_module():
    if os.environ.get('OLDHAM_STANDING_COST_PATH'):Path(os.environ['OLDHAM_STANDING_COST_PATH']).write_text(json.dumps(RESULTS,sort_keys=True))
