"""Continue actual guarded #213 recovery in the SAME disposable database."""
import json
import os
import sys
from pathlib import Path
import psycopg
import pytest
from psycopg import sql
from tests.e2e_pg_world import settings
from tests.test_release_candidate_pg import exercise_conditional_runtime


def main():
    state=json.load(sys.stdin)
    raw,info,_,_=settings()
    assert state['owner']['host']=='127.0.0.1'
    assert state['owner']['dbname']=='ingestion_provisioning_test'
    def connect(role):
        assert role=='provisioning_migrator'
        return psycopg.connect(**state['migrator'],autocommit=True,prepare_threshold=None)
    def actor():
        return psycopg.connect(**state['owner'],autocommit=True,prepare_threshold=None)
    with psycopg.connect(raw,autocommit=True) as boot:
        assert boot.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0]==state['database_oid']
        assert boot.execute("SELECT (outcome->>'hard_stop_generation')::int FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()==(15,)
        # New adapter, actual frozen SQL credential lifecycle. Only the fixed
        # disposable route differs; no production identity/SQL guard is removed.
        import copy,time
        from urllib.parse import unquote,urlparse
        from verification.ingestion_storage import tameside_owner_access
        source=Path(tameside_owner_access.__file__).read_text()
        assert source.count("==policy['route']=='POOLER'")==1
        source=source.replace("==policy['route']=='POOLER'","==policy['route']=='DISPOSABLE'")
        scope={'__package__':'verification.ingestion_storage'}
        exec(compile(source,'disposable-owner-access.py','exec'),scope)
        access={}
        def activate(policy,manifest):
            assert boot.execute("SELECT (outcome->>'hard_stop_generation')::int FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()==(16,)
            # This catch-up issuer is installed only by the disposable fixture.
            # It must not widen the real activation gate's callable surface.
            boot.execute('REVOKE EXECUTE ON FUNCTION ingestion_register_disposable_catchup(jsonb) FROM ingestion_worker')
            inventory={n:dict(sha256=h,security_definer=d) for n,h,d in boot.execute("SELECT p.proname,encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),p.prosecdef FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proowner='ingestion_storage_owner'::regrole").fetchall()}
            api=scope['lifecycle'](os.environ['S4_BOLTON_PINNED_CHECKOUT'],policy=policy,manifest=manifest,expected_inventory=inventory)
            hashes=dict(boot.execute("SELECT rolname,encode(sha256(convert_to(rolpassword,'UTF8')),'hex') FROM pg_authid WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login')").fetchall())
            b=dict(version='FINITE_INTAKE_OWNER_V1',period='S4_FINITE_677f555670666bcf21f45860',route=policy['route'],hostaddr=policy['hostaddr'],owner_hostaddr=policy['hostaddr'],execution_binding=policy['execution_binding'],accepted_stop=policy['expected_stop'],evidence_backend='POSTGRES_PILOT_V1',credential_policy='STABLE_RESTRICTED_V1',credential_verifier_sha256=hashes,runtime_deadline=policy['expires_at'],valid_until=policy['expires_at']+185)
            passwords={urlparse(url).username:unquote(urlparse(url).password) for url in state['urls'].values() if urlparse(url).username in tameside_owner_access.ROLES}
            assert set(passwords)==set(tameside_owner_access.ROLES),sorted(passwords)
            def save(value):access['state']=copy.deepcopy(value)
            # Fixture passwords are private disposable state. The actual helper
            # keeps the production entropy and verifier-preservation checks.
            with actor() as c:
                prepared=api.prepare_activation(c,b,stable_credentials=passwords)
                original=boot.execute("SELECT outcome::jsonb FROM ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
                changed=copy.deepcopy(original);changed['manual_stop']='OWNER_TEST_STOP'
                boot.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(changed),))
                try:
                    with pytest.raises(Exception,match='ACTIVATION_STOP_CHANGED'):
                        api.activate(c,b,save,prepared=prepared)
                    assert boot.execute("SELECT bool_and(NOT rolcanlogin) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login')").fetchone()==(True,)
                finally:
                    boot.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(original),))
                api.activate(c,b,save,prepared=prepared)
            access.update(api=api,binding=b,save=save)
        def install_journal():
            import subprocess
            from verification.ingestion_storage import tameside_owner_journal as j
            script="from verification.ingestion_storage.intake_successor import owner_sql;print(owner_sql(),end='')"
            source=subprocess.run([sys.executable,'-c',script],cwd=os.environ['S4_BOLTON_PINNED_CHECKOUT'],capture_output=True,text=True,check=True).stdout
            assert boot.execute("SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid='ingestion_intake_owner_state(text,text,text,bytea)'::regprocedure").fetchone()==(j.BODY_SHA,)
            with actor() as c:c.execute(j.render_install(source).replace("current_database() IS DISTINCT FROM 'postgres'","current_database() IS DISTINCT FROM 'ingestion_provisioning_test'"))
            with actor() as c:
                c.execute('BEGIN')
                q='SELECT * FROM ingestion_intake_owner_state(%s,%s,%s,%s)'
                first=c.execute(q,(j.JOURNAL,j.RUN,'',b'disposable encrypted-envelope fixture')).fetchone()
                assert first[0]==0
                assert c.execute(q,(j.JOURNAL,j.RUN,'',None)).fetchone()==first
                c.execute('SAVEPOINT duplicate')
                try:c.execute(q,(j.JOURNAL,j.RUN,'',b'different'))
                except psycopg.errors.RaiseException as exc:assert 'OWNER_STATE_CONCURRENT_OR_UNCERTAIN' in str(exc)
                else:raise AssertionError('stale journal write accepted')
                c.execute('ROLLBACK TO SAVEPOINT duplicate')
                c.execute('ROLLBACK')
                assert c.execute(q,(j.JOURNAL,j.RUN,'',None)).fetchone() is None
            with actor() as c:
                try:c.execute(j.render_install(source).replace("current_database() IS DISTINCT FROM 'postgres'","current_database() IS DISTINCT FROM 'ingestion_provisioning_test'"))
                except psycopg.errors.RaiseException as exc:
                    c.execute('ROLLBACK');assert 'TAMESIDE_JOURNAL_INSTALLED_DRIFT' in str(exc)
                else:raise AssertionError('duplicate journal installation accepted')
        def close():
            with actor() as c:receipt=access['api'].close(c,access['state'],access['save'])
            assert receipt['runtime_access']=='DISABLED' and receipt['temporary_owner']=='REMOVED'
            with actor() as c:
                assert c.execute("SELECT bool_and(NOT rolcanlogin) FROM pg_roles WHERE rolname IN ('ingestion_worker_login','ingestion_effect_login')").fetchone()==(True,)
                assert c.execute("SELECT count(*) FROM pg_auth_members WHERE member IN ('ingestion_worker_login'::regrole,'ingestion_effect_login'::regrole)").fetchone()==(0,)
        w=dict(boot=boot,connect=connect,actor=actor,urls=state['urls'],activate_restricted_fixture=activate,close_restricted_fixture=close,install_journal_fixture=install_journal)
        target=Path(sys.argv[1]);target.mkdir()
        try:
            with pytest.MonkeyPatch.context() as monkeypatch:
                result=exercise_conditional_runtime(w,target,monkeypatch,recovered=True)
        finally:
            for role,cap in [('ingestion_worker_login','ingestion_worker'),('ingestion_effect_login','ingestion_effect_broker')]:
                boot.execute(sql.SQL('ALTER ROLE {} NOLOGIN').format(sql.Identifier(role)))
                boot.execute(sql.SQL('REVOKE {} FROM {}').format(sql.Identifier(cap),sql.Identifier(role)))
        print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
