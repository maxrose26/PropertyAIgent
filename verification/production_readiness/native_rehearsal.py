"""Executable CI-only native rehearsal. No supplied DSN or production path."""
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import uuid
from verification.production_readiness.ci_guard import ServiceAuthority, PASSWORD, BOOTSTRAP
from verification.production_readiness.catalog_verifier import compare,digest

P=Path(__file__).parent
ROLES=['ah_ci_owner','ah_ci_reader','ah_ci_importer','ah_ci_registrar','ah_ci_nobody','ah_ci_anon','ah_ci_authenticated','ah_ci_service_role']

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def check_files():
    contract=json.loads((P/'candidate_contract.json').read_text())
    for name,want in contract['files'].items():
        if sha(P/name)!=want: raise ValueError('Artifact hash mismatch: '+name)
    return contract

def claim_insert(conn,key='one',scope=1):
    # Labelled software fixtures only: no real cohort content/identities imported.
    return conn.execute("""INSERT INTO ah_source_claims
    (application_id,site_id,scheme_application_id,scope_kind,scope_key,scope_label,scope_basis,metric,qualifier,value,
     document_id,document_date,passage_text,passage_locator,passage_hash,planning_stage,origin_kind,origin_reference,
     created_by,recorded_at,import_key,payload_hash)
    VALUES (1,1,%s,'whole_scheme','WHOLE_SCHEME','SYNTHETIC','SYNTHETIC TEST ONLY','affordable_count','exact',72,
     1,'2024-01-01','SYNTHETIC72','fixture',%s,'proposed','reviewed_import','SYNTHETIC','fixture',now(),%s,%s) RETURNING id""",
     (scope,'a'*64,key,'b'*64)).fetchone()[0]

def event_insert(conn,cid,action,sequence=1,previous=None,related=None):
    return conn.execute("""INSERT INTO ah_claim_events
    (claim_id,sequence,previous_event_id,action,related_claim_id,source_checked,scope_checked,stage_checked,
     actor_id,reason,recorded_at,request_key,request_hash)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'fixture-reviewer','SYNTHETIC TEST ONLY',now(),%s,%s) RETURNING id""",
    (cid,sequence,previous,action,related,action=='ACCEPT',action=='ACCEPT',action=='ACCEPT',uuid.uuid4().hex,'c'*64)).fetchone()[0]

def evidence_hash(c):
    return {t:{'count':len(rows),'sha256':digest(rows)} for t in ('ah_source_claims','ah_claim_events')
       for rows in [[list(r) for r in c.execute('SELECT row_to_json(t)::text FROM '+t+' t ORDER BY id').fetchall()]]}

def main(out):
    out.mkdir(parents=True,exist_ok=False)
    results=[];authority=None;created=[]
    def write(name,data): (out/name).write_text(json.dumps(data,indent=2,default=str)+'\n')
    def passed(name,**data): results.append({'case':name,'status':'PASS',**data})
    def forbidden(conn,name,statement,params=None,states=('42501',)):
        try: conn.execute(statement,params)
        except authority.driver.Error as exc:
            if exc.sqlstate not in states: raise AssertionError(name+': unexpected SQLSTATE '+str(exc.sqlstate)) from exc
            passed(name,sqlstate=exc.sqlstate);return
        raise AssertionError(name+': operation unexpectedly succeeded')
    try:
        contract=check_files()
        root=P.parents[1]
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        if head!=os.environ.get('GITHUB_SHA') or subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip():
            raise ValueError('Checkout SHA/tree mismatch')
        authority=ServiceAuthority(os.environ,root)
        from psycopg import sql
        from verification.production_readiness.native_exporter import export_catalog
        def snapshot(c):
            if c.info.transaction_status == 0:
                with c.transaction():
                    c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    return export_catalog(c,ROLES,mig_hash,ddl_hash)
            return export_catalog(c,ROLES,mig_hash,ddl_hash,allow_writable_snapshot=True)
        token=uuid.uuid4().hex[:16]
        names={k:'ah_ci_'+token+'_'+k for k in ('reference','target','partial','defaults')}
        with authority.admin() as admin:
            if admin.execute('SELECT rolname FROM pg_roles WHERE rolname=ANY(%s)',(ROLES,)).fetchall(): raise ValueError('Pre-existing rehearsal roles')
            for role in ROLES:
                admin.execute(sql.SQL('CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal(PASSWORD)))
            for name in names.values():
                admin.execute(sql.SQL('CREATE DATABASE {} OWNER ah_ci_owner TEMPLATE template0').format(sql.Identifier(name)))
                created.append(name);authority.register_database(name)
        expected=json.loads((P/'expected_schema.json').read_text())
        payload={k:v for k,v in expected.items() if not k.startswith('_')}
        migration=(P/'003_ci_candidate.sql').read_text()
        mig_hash=sha(P/'003_ci_candidate.sql');ddl_hash=digest(payload)
        for name in names.values():
            with authority.connect(name,'ah_ci_owner') as c:
                c.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
                c.execute('CREATE TABLE applications(id integer PRIMARY KEY); CREATE TABLE sites(id integer PRIMARY KEY); CREATE TABLE documents(id integer PRIMARY KEY)')
                c.execute('INSERT INTO applications VALUES(1),(2); INSERT INTO sites VALUES(1); INSERT INTO documents VALUES(1)')
        with authority.connect(names['reference'],'ah_ci_owner') as c:
            # Reference is independently instantiated from expected JSON, never target catalogue.
            with c.transaction():
                for obj in payload.values():
                    c.execute(obj['ddl'])
                    for index in obj['indexes']: c.execute(index)
                c.execute((P/'reference_security.sql').read_text())
                c.execute((P/'security_contract.sql').read_text())
        with authority.connect(names['target'],'ah_ci_owner') as c: c.execute(migration,prepare=False)
        with authority.connect(names['reference']) as c: reference=snapshot(c)
        bound=copy.deepcopy(expected)
        bound['_native_verifier']={'reference_sha256':digest(reference),'migration_sha256':mig_hash,
             'server_version_num':reference['server_version_num'],'role_names':ROLES}
        write('reference-catalogue.json',reference);write('bound-expected-schema.json',bound)
        def verify(c): return compare(bound,snapshot(c),reference)
        with authority.connect(names['target']) as c:
            actual=snapshot(c);write('catalogue.json',actual)
            report=compare(bound,actual,reference);write('verifier.json',report)
            if report['status']!='PASS': raise AssertionError('Fresh install mismatch: '+str(report['differences']))
            passed('fresh-install-verifier')
            write('versions.json',{'git_sha':head,'python':platform.python_version(),'psycopg':authority.driver.__version__,
                'postgresql':c.execute('SELECT version()').fetchone()[0],'migration_sha256':mig_hash,
                'expected_schema_file_sha256':sha(P/'expected_schema.json'),'expected_ddl_sha256':ddl_hash,
                'service':authority.service,'cluster_identity':authority.identity})
        with authority.connect(names['target'],'ah_ci_owner') as c:
            forbidden(c,'second-run-explicit-rejection',migration,states=('P0001',));c.execute('ROLLBACK')
            if verify(c)['status']!='PASS': raise AssertionError('Repeat changed schema')
        with authority.connect(names['partial'],'ah_ci_owner') as c:
            c.execute(payload['ah_source_claims']['ddl'])
            forbidden(c,'partial-install-rejection',migration,states=('P0001',));c.execute('ROLLBACK')
            if verify(c)['status']!='FAIL': raise AssertionError('Partial schema accepted')
        drift=[('extra-table','CREATE TABLE ah_unexpected(id int)'),('extra-column','ALTER TABLE ah_source_claims ADD COLUMN surprise int'),
          ('wrong-default','ALTER TABLE ah_source_claims ALTER COLUMN schema_version SET DEFAULT 2'),
          ('wrong-nullability','ALTER TABLE ah_source_claims ALTER COLUMN scope_label DROP NOT NULL'),
          ('wrong-type','ALTER TABLE ah_source_claims ALTER COLUMN scope_label TYPE text'),
          ('missing-check','ALTER TABLE ah_source_claims DROP CONSTRAINT ah_stage'),
          ('missing-index','DROP INDEX ix_ah_payload'),('missing-trigger','DROP TRIGGER ah_source_claims_deny_mutation ON ah_source_claims'),
          ('rls-disabled','ALTER TABLE ah_source_claims DISABLE ROW LEVEL SECURITY'),
          ('unexpected-policy','CREATE POLICY unexpected ON ah_source_claims USING(true)'),
          ('unexpected-grant','GRANT SELECT ON ah_source_claims TO ah_ci_nobody'),
          ('sequence-grant','GRANT USAGE ON SEQUENCE ah_source_claims_id_seq TO ah_ci_nobody'),
          ('unsafe-default','ALTER DEFAULT PRIVILEGES FOR ROLE ah_ci_owner IN SCHEMA public GRANT SELECT ON TABLES TO ah_ci_anon')]
        with authority.connect(names['target']) as c:
            for label,statement in drift:
                c.execute('BEGIN ISOLATION LEVEL REPEATABLE READ');c.execute(statement)
                result=verify(c)
                c.execute('ROLLBACK')
                if result['status']!='FAIL': raise AssertionError('Drift accepted: '+label)
                passed('drift-'+label,differences=result['differences'])
            for field in ('migration_sha256','expected_ddl_sha256'):
                bad=copy.deepcopy(actual);bad[field]='wrong'
                if compare(bound,bad,reference)['status']!='FAIL': raise AssertionError('Hash mismatch accepted')
                passed('mismatch-'+field)
            badref=copy.deepcopy(reference);badref['catalog']['policies'].append({'unexpected':True})
            if compare(bound,actual,badref)['status']!='FAIL': raise AssertionError('Reference tamper accepted')
            passed('reference-hash-mismatch')
        # Seed named-role defaults BEFORE migration; exact hardening must neutralize them.
        with authority.connect(names['defaults'],'ah_ci_owner') as c:
            c.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ah_ci_anon')
            c.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO ah_ci_authenticated')
            c.execute('ALTER DEFAULT PRIVILEGES GRANT EXECUTE ON FUNCTIONS TO ah_ci_service_role')
            c.execute(migration,prepare=False)
        with authority.connect(names['defaults']) as c:
            result=verify(c)
            if result['status']!='PASS': raise AssertionError('Unsafe defaults not neutralized: '+str(result))
            passed('named-role-defaults-neutralized')
        with authority.connect(names['target']) as c:
            rows=c.execute('SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=ANY(%s)',(ROLES,)).fetchall()
            if any(any(row[1:]) for row in rows): raise AssertionError('Privileged runtime role')
            passed('role-flags',roles=rows)
            for role in ROLES[1:]:
                if c.execute("SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace AND relname LIKE 'ah_%%' AND relowner=(SELECT oid FROM pg_roles WHERE rolname=%s)",(role,)).fetchone()[0]: raise AssertionError('Runtime ownership')
            passed('runtime-not-owner')
        for role in ROLES[1:]:
            with authority.connect(names['target'],role) as c:
                forbidden(c,role+'-dark-read-denied','SELECT * FROM ah_source_claims')
        with authority.connect(names['target']) as c:
            c.execute((P/'local_role_probe.sql').read_text())
        with authority.connect(names['target'],'ah_ci_importer') as c:
            c.execute('BEGIN');claim_insert(c,'rolled-back');c.execute('ROLLBACK')
            if c.execute('SELECT count(*) FROM ah_source_claims').fetchone()[0]!=0: raise AssertionError('Rollback retained fixture')
            passed('append-transaction-rollback')
            first=claim_insert(c);second=claim_insert(c,'two')
            accepted=event_insert(c,first,'ACCEPT')
            e=event_insert(c,second,'ACCEPT')
            event_insert(c,first,'SUPERSEDE',2,accepted,second)
            event_insert(c,second,'WITHDRAW',2,e)
            third=claim_insert(c,'three');event_insert(c,third,'CORRECT',related=second)
            passed('append-claims-review-history')
            try: claim_insert(c,'out-of-scope',2)
            except authority.driver.Error as exc:
                if exc.sqlstate!='42501': raise
                passed('out-of-cohort-insert-denied',sqlstate=exc.sqlstate)
            else: raise AssertionError('Out of scope insert permitted')
        for role in ('ah_ci_reader','ah_ci_importer','ah_ci_registrar','ah_ci_nobody'):
            with authority.connect(names['target'],role) as c:
                for table in ('ah_source_claims','ah_claim_events'):
                    for op in ('UPDATE '+table+' SET id=id','DELETE FROM '+table,'TRUNCATE '+table,'ALTER TABLE '+table+' OWNER TO '+role):
                        forbidden(c,role+':'+op,op)
                forbidden(c,role+'-bypass-denied','ALTER ROLE '+role+' BYPASSRLS')
        with authority.connect(names['target'],'ah_ci_reader') as c:
            if c.execute('SELECT count(*) FROM ah_source_claims').fetchone()[0]!=3: raise AssertionError('Reader missing evidence')
            forbidden(c,'reader-insert-denied','INSERT INTO ah_source_claims DEFAULT VALUES')
            passed('bounded-reader-works')
        with authority.connect(names['target'],'ah_ci_registrar') as c:
            c.execute('INSERT INTO documents VALUES(2)');passed('registrar-document-only')
            forbidden(c,'registrar-claim-insert-denied','INSERT INTO ah_source_claims DEFAULT VALUES')
        with authority.connect(names['target']) as c:
            before=evidence_hash(c)
            for table in ('ah_source_claims','ah_claim_events'):
                for op in ('UPDATE '+table+' SET id=id','DELETE FROM '+table,'TRUNCATE '+table):
                    forbidden(c,'trigger-'+op,op,states=('P0001',))
            if evidence_hash(c)!=before: raise AssertionError('Forbidden mutation changed evidence')
            passed('append-only-triggers-preserve-hashes')
        # Demonstrate revocation waiting on an in-flight writer, then bounded rollback and disable.
        with authority.connect(names['target'],'ah_ci_importer') as writer, authority.connect(names['target']) as admin:
            before=evidence_hash(admin);writer.execute('BEGIN');claim_insert(writer,'in-flight')
            admin.execute('BEGIN')
            forbidden(admin,'in-flight-disable-waits','LOCK TABLE ah_source_claims IN ACCESS EXCLUSIVE MODE',states=('55P03',))
            admin.execute('ROLLBACK');writer.execute('ROLLBACK')
            admin.execute('BEGIN');admin.execute('LOCK TABLE ah_source_claims,ah_claim_events IN ACCESS EXCLUSIVE MODE')
            admin.execute('REVOKE ALL ON ah_source_claims,ah_claim_events FROM ah_ci_reader,ah_ci_importer')
            admin.execute('REVOKE ALL ON SEQUENCE ah_source_claims_id_seq,ah_claim_events_id_seq FROM ah_ci_importer')
            admin.execute('COMMIT')
            if evidence_hash(admin)!=before: raise AssertionError('Disable changed history')
            write('disable-hashes.json',{'before':before,'after':evidence_hash(admin)})
            passed('disable-preserves-history-after-inflight-rollback')
        for role in ('ah_ci_reader','ah_ci_importer'):
            with authority.connect(names['target'],role) as c:
                forbidden(c,role+'-disabled-read','SELECT * FROM ah_source_claims')
                forbidden(c,role+'-disabled-write','INSERT INTO ah_source_claims DEFAULT VALUES')
        write('overall.json',{'status':'PASS_NATIVE_REHEARSAL_NOT_PRODUCTION_APPROVAL','cases':len(results)})
    except BaseException as exc:
        write('overall.json',{'status':'FAILED_OR_BLOCKED','error_type':type(exc).__name__,'message':str(exc)[:1500]})
        raise
    finally:
        write('case-results.json',results)
        for name,prefixes in {'permission-report.json':('ah_ci','reader','registrar','bounded','role','runtime','named','out-of'),
          'append-only-report.json':('append','trigger'), 'drift-repeatability-report.json':('drift','second','partial','mismatch','reference'),
          'disable-report.json':('disable','in-flight')}.items(): write(name,[r for r in results if r['case'].startswith(prefixes)])
        cleanup={'databases_dropped':[],'service_stop':'workflow always step required'}
        if authority:
            try:
                from psycopg import sql
                with authority.admin() as c:
                    for name in reversed(created):
                        c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)));cleanup['databases_dropped'].append(name)
            except Exception as exc:
                cleanup['error_type']=type(exc).__name__;write('overall.json',{'status':'FAILED_CLEANUP'})
        write('cleanup.json',cleanup)
        write('evidence-checksums.json',{f.name:sha(f) for f in out.iterdir() if f.is_file() and f.name!='evidence-checksums.json'})
        if cleanup.get('error_type'): raise RuntimeError('Disposable cleanup failed')

if __name__=='__main__':
    import sys
    main(Path(sys.argv[1]))
