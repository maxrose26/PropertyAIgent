"""Single approved PA-TAM001 v1.3 read. No retry or operational mutation."""
import ast, hashlib, io, json, os, signal, sys, time, uuid
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
SERVICE = 'srv-d9qbl7qjnfac73d8nieg'
DEPLOY = '2fa0f07cfdfb56a27243ebff18110d441f9da04d'
PIN = 'f027ba28af69ae70208eab5ed047e4a8a81c6337'
CLASS_SHA = '4959d79558bd5c4a5aabb8ec6c5dd6f05c02720c23bcefa9bf6985507673b36f'
class Refusal(Exception): pass
def require(ok, code):
    if not ok: raise Refusal(code)

def run(factory, started):
    out = dict(scope='PA-TAM001 v1.3', execution_id=str(uuid.uuid4()),
        started_at=datetime.now(timezone.utc).isoformat(), statements_attempted=0,
        statements_completed=0, connections_attempted=0, connections_opened=0,
        returned_value_bytes=0, observations={}, rollback_acknowledged=False,
        rollback_attempted=False, connection_closed=None, status='INCOMPLETE', retry=False)
    c = None
    def deadline(*_): raise Refusal('OVERALL_DEADLINE')
    def arm(seconds):
        remaining=seconds-(time.monotonic()-started)
        require(remaining>0, 'OVERALL_DEADLINE')
        signal.setitimer(signal.ITIMER_REAL,remaining)
    def execute(statement):
        require(out['statements_attempted']<7,'STATEMENT_CAP')
        out['statements_attempted']+=1
        cursor=c.execute(statement)
        out['statements_completed']+=1
        return cursor
    signal.signal(signal.SIGALRM,deadline)
    signal.signal(signal.SIGTERM,deadline)
    try:
        arm(15)
        db=factory()
        out['connections_attempted']=1
        with db.connection() as c:
            out['connections_opened']=1
            try:
                for statement in STATEMENTS[:3]: execute(statement)
                for name, statement in zip(('controller','work','sessions'),STATEMENTS[3:6]):
                    # Same approved SELECT, bounded in the server before return.
                    bounded="SELECT CASE WHEN octet_length(payload)>21000 THEN 'null' ELSE payload END FROM (SELECT coalesce(jsonb_agg(to_jsonb(q)),'[]'::jsonb)::text AS payload FROM ("+statement+") q) b"
                    raw=execute(bounded).fetchone()[0]
                    out['returned_value_bytes']+=len(raw.encode())
                    require(out['returned_value_bytes']<=65536,'RESULT_CAP')
                    rows=json.loads(raw)
                    require(isinstance(rows,list),'SERVER_RESULT_CAP')
                    out['observations'][name]=rows
                out['status']='READ_COMPLETED_REVIEW_REQUIRED'
            finally:
                try:
                    arm(18)
                    out['rollback_attempted']=True
                    cursor=execute(STATEMENTS[6])
                    out['rollback_acknowledged']=(cursor.statusmessage=='ROLLBACK' and c.info.transaction_status.name=='IDLE')
                except BaseException:
                    out['rollback_acknowledged']=False
                finally:
                    try:
                        c.close()
                        out['connection_closed']=bool(c.closed)
                    except BaseException:
                        out['connection_closed']=False
    except BaseException as exc:
        out['status']='STOP_INCOMPLETE_NO_RETRY'
        out['reason']=str(exc) if isinstance(exc,Refusal) else 'CONFIGURATION_OR_DATABASE_REFUSAL'
        if getattr(exc,'sqlstate',None): out['sqlstate']=exc.sqlstate
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        out['elapsed_ms']=int((time.monotonic()-started)*1000)
        if not out['rollback_acknowledged'] or out['connection_closed'] is not True:
            out['status']='STOP_INCOMPLETE_NO_RETRY'
        out['finished_at']=datetime.now(timezone.utc).isoformat()
    return out

STATEMENTS = ['BEGIN READ ONLY', "SET LOCAL statement_timeout = '10s'", "SET LOCAL lock_timeout = '3s'", "SELECT session_user, current_user, current_database(),\n current_setting('transaction_read_only') AS read_only,\n current_setting('statement_timeout') AS statement_timeout,\n current_setting('lock_timeout') AS lock_timeout,\n outcome::jsonb->'global_stop' AS global_stop,\n outcome::jsonb->'manual_stop' AS manual_stop,\n outcome::jsonb->'last_hard_stop' AS last_hard_stop,\n outcome::jsonb->'hard_stop_generation' AS generation,\n outcome::jsonb->'intake_run'->>'period' AS period,\n outcome::jsonb->'intake_run'->>'id' AS run_id,\n outcome::jsonb->'intake_run'->>'state' AS run_state,\n encode(sha256(convert_to(outcome::jsonb::text,'UTF8')),'hex') AS controller_sha\nFROM public.ingestion_work_items WHERE key=repeat('0',64)", "WITH candidates AS (\n SELECT w.*, count(*) OVER () AS total\n FROM public.ingestion_work_items w\n WHERE w.state='CLAIMED'\n    OR w.phase IN ('SOURCE_INTENT','WRITE_INTENT')\n    OR w.state='PERSISTENCE_UNCERTAIN'\n ORDER BY w.key LIMIT 8\n)\nSELECT w.total,w.key,w.authority,w.revision,w.state,w.phase,w.fence,\n w.attempt_count,w.task,w.contract,w.subject::jsonb,\n w.checkpoint IS NULL AS no_checkpoint,\n w.lease_until < extract(epoch FROM clock_timestamp()) AS lease_expired,\n (SELECT count(*) FROM public.ingestion_work_attempts a\n   WHERE a.work_key=w.key) AS attempts,\n (SELECT count(*) FROM public.ingestion_work_attempts a\n   WHERE a.work_key=w.key AND a.fence=1 AND a.phase='SOURCE_INTENT'\n   AND a.finished_at IS NULL AND a.checkpoint IS NULL\n   AND a.authority=w.authority) AS expected_pending_attempts,\n encode(sha256(convert_to(jsonb_build_object(\n  'work',to_jsonb(w)-'total',\n  'attempts',coalesce((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.fence)\n    FROM public.ingestion_work_attempts a WHERE a.work_key=w.key),\n    '[]'::jsonb))::text,'UTF8')),'hex') AS work_attempt_sha\nFROM candidates w ORDER BY w.key", "SELECT count(*) OVER () AS total,pid,usename,application_name,\n backend_start,xact_start,state\nFROM pg_stat_activity\nWHERE pid<>pg_backend_pid() AND\n (usename LIKE 'ingestion_%' OR application_name='propertyaigent_owner_pilot')\nORDER BY pid LIMIT 8", 'ROLLBACK']

def preflight():
    out={}
    require(os.environ.get('RENDER_SERVICE_ID') == SERVICE, 'SERVICE_MISMATCH')
    require(os.environ.get('RENDER_GIT_COMMIT') == DEPLOY, 'DEPLOYMENT_DRIFT')
    require(bool(os.environ.get('DATABASE_URL')), 'DATABASE_CONFIGURATION_ABSENT')
    pins = {
      'verification/ingestion_storage/owner_pilot.py':'c5412249c9c42979425f518ad6e2827222e936c5',
      'verification/ingestion_storage/intake_owner.py':'cc41273779102e3fd57359e98e2717db5211e3a5',
      'verification/ingestion_storage/tls_trust.py':'f08d8647a2b740facaa7614d8cf7466fc379cc8a',
      'verification/ingestion_storage/trust/supabase-prod-ca-2021.crt':'3d693669b23c340c57a3457bdc8b6fefe1806cc5'}
    for name, expected in pins.items():
        p = Path(name)
        require(p.is_file() and not p.is_symlink(), 'SOURCE_OR_CA_ABSENT')
        raw = p.read_bytes()
        require(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==expected,
                'SOURCE_OR_CA_DRIFT')
    source = Path('verification/ingestion_storage/owner_pilot.py').read_text()
    node = next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Database')
    require(hashlib.sha256(ast.get_source_segment(source,node).encode()).hexdigest()==CLASS_SHA,
            'FROZEN_DATABASE_CLASS_DRIFT')
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        from verification.ingestion_storage.owner_pilot import Database
    require(Path(sys.modules[Database.__module__].__file__).resolve()==
            Path('verification/ingestion_storage/owner_pilot.py').resolve(), 'IMPORT_PATH_DRIFT')
    out['deployed_revision_verified'] = DEPLOY
    return Database

def main():
    started=globals().get('transport_started',time.monotonic())
    try:
        factory=preflight()
    except BaseException:
        print('{"status":"PREFLIGHT_REFUSED_NO_RETRY","connections_attempted":0}',flush=True)
        return
    result=run(factory,started)
    print(json.dumps(result,sort_keys=True,separators=(',',':')),flush=True)

if __name__=='__main__':
    main()
