"""Two fixed owner operations. No source, Render, activation or arbitrary SQL.
Existing Owner issuer, encrypted Vault, GitHub transport and terminal envelope.
"""
import copy
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from . import intake_owner as op
from .operational_owner import Owner
from .operational_publication import canonical, GitHub

COUNCILS = {
    'tameside': dict(contract='tameside-screening-metadata-five-v1', qualification_sha256='6fcf084c2cf987471f7a81e389f918bb975044bcb24b6834d036b017c459d0f7'),
    'manchester': dict(contract='manchester-screening-metadata-v1', qualification_sha256='4c602866c0d6f388854e85c00d2ca2bd1244eaaca1aed059cc5a20bbdd537aa1')}
SCREENING = '58e2a1a1dae30a21b8fa150a27d223793d4601e8d400a686c4f8e17d999e1b7e'
ISSUER = 'ingestion_barrier_releaser'
ISSUER_MEMBERS = "SELECT grantor::regrole::text,admin_option,inherit_option,set_option FROM pg_auth_members WHERE roleid='ingestion_barrier_releaser'::regrole AND member=current_user::regrole ORDER BY grantor"
FLAGS = "SELECT pg_has_role(current_user,'ingestion_barrier_releaser','USAGE'),pg_has_role(current_user,'ingestion_barrier_releaser','SET')"


def private_path(b, key, path):
    expected = b.get(key)
    op.require(type(expected) is str and Path(expected).is_absolute() and '..' not in Path(expected).parts and
               str(Path(path).absolute()) == expected and str(Path(expected).resolve()) == expected,
               'OPERATION_VAULT_BINDING')


def validate_policy(b, policy, *, now=None):
    op.validate_binding(b, opening=True, now=now)
    op.require(type(policy) is dict and set(policy) == {'expires_at','max_runs','overlap_days','councils','expected_stop','execution_binding','test_evidence','screening_config','hostaddr','route','render_profile'}, 'PERIOD_EXACT_POLICY')
    op.require(hashlib.sha256(canonical(policy)).hexdigest() == b.get('period_policy_sha256'), 'PERIOD_POLICY_HASH')
    op.require(type(policy['max_runs']) is int and policy['max_runs'] == 1 and type(policy['overlap_days']) is int and policy['overlap_days'] == 7 and policy['test_evidence'] is False, 'PERIOD_SINGLE_RUN')
    op.require(policy['councils'] == COUNCILS and policy['screening_config'] == SCREENING and policy['execution_binding'] == op.APPLICATION_BINDING and policy['expected_stop'] == op.ACCEPTED_STOP, 'PERIOD_REVIEWED_BINDINGS')
    op.require(policy['route'] == b['route'] and policy['hostaddr'] == b['hostaddr'] and type(policy['expires_at']) in (int,float) and (time.time() if now is None else now)+960 < policy['expires_at'] <= b['valid_until'] and policy['expires_at'] <= b.get('publication_valid_until',0), 'PERIOD_ROUTE_EXPIRY')
    if 'timing_policy' in b:
        target=b['runtime_deadline'] if b['timing_policy']['version']=='SEPARATE_EXPIRY_V2_RESERVE' else b['valid_until']
        op.require(policy['expires_at']==target,'PERIOD_FIXED_DEADLINE')
    profile=policy['render_profile']
    fields={'mode','service_id','revision','browser_path','browser_sha256','aggregate_bytes','source_rss_bytes','controller_rss_bytes','reserve_bytes','source_seconds'}
    op.require(type(profile) is dict and set(profile)==fields and profile==b.get('render_profile') and profile['mode']=='render-intake-v1' and profile['service_id']=='crn-d9sv93vavr4c73f98rb0' and profile['revision']==op.APPLICATION_BINDING['revision'], 'PERIOD_PROFILE')
    op.require(type(profile['browser_path']) is str and Path(profile['browser_path']).is_absolute() and '..' not in Path(profile['browser_path']).parts and re.fullmatch('[a-f0-9]{64}',profile['browser_sha256']) and all(type(profile[k]) is int for k in ('aggregate_bytes','source_rss_bytes','controller_rss_bytes','reserve_bytes','source_seconds')) and 1879048192<=profile['aggregate_bytes']<=2147483648 and (profile['source_rss_bytes'],profile['controller_rss_bytes'],profile['reserve_bytes'],profile['source_seconds'])==(1073741824,268435456,536870912,75), 'PERIOD_PROFILE')
    return policy


class PeriodIssuer(Owner):
    """Fixed lifecycle checks around the existing register_intake_period primitive.

    No new connection: wrapper supplies this exact terminal-owned connection.
    Checks surround BEGIN, the fixed registration call and COMMIT in the existing issuer.
    """
    def q(self,c,statement,params=None,*,effect=False):
        if statement == 'COMMIT':
            op.require(c.execute(op.MEMBERS).fetchall()==self.prior_members and c.execute(FLAGS).fetchone()==(False,False), 'PERIOD_PRIVILEGE_RESTORATION')
            op.require(op.control(c)==self.expected_control and op.ledger_sha(c,self.prior_control)==self.prior_ledger, 'PERIOD_LEDGER_POSTCONDITION')
            self.expected_ledger=op.ledger_sha(c)
            op.inventory(c);op.owner_absent(c)
            self.journal['state']='COMMIT_INTENT_NO_RETRY';self.save(self.journal)
        result=super().q(c,statement,params,effect=effect)
        if statement == 'GRANT ingestion_barrier_releaser TO CURRENT_USER WITH INHERIT TRUE, SET TRUE':
            during=c.execute(op.MEMBERS).fetchall()
            temporary=(ISSUER,'postgres','postgres',False,True,True)
            op.require(len(during)==len(self.prior_members)+1 and set(during)==set(self.prior_members)|{temporary} and c.execute(FLAGS).fetchone()==(True,True),'PERIOD_EXACT_TEMPORARY_ISSUER')
        if statement == 'COMMIT':
            op.require(op.control(c)==self.expected_control and op.ledger_sha(c)==self.expected_ledger and c.execute(op.MEMBERS).fetchall()==self.prior_members and c.execute(FLAGS).fetchone()==(False,False),'PERIOD_COMMITTED_READBACK')
            self.journal['state']='COMMIT_ACKNOWLEDGED';self.save(self.journal)
        if statement == 'BEGIN':
            c.execute("SET LOCAL statement_timeout='10s';SET LOCAL lock_timeout='3s';SET LOCAL idle_in_transaction_session_timeout='20s'")
            op.identity(c);op.inventory(c);op.owner_absent(c)
            self.prior_members=op.dormant(c)
            rows=c.execute(ISSUER_MEMBERS).fetchall()
            op.require(len(rows)==1 and rows[0][0]!='postgres' and rows[0][1:]==(True,False,False) and c.execute(FLAGS).fetchone()==(False,False), 'PERIOD_EXISTING_ISSUER_ADMIN_ONLY')
            before=op.control(c)
            op.require(op.stop_snapshot(before)==op.ACCEPTED_STOP, 'PERIOD_STOP_CHANGED')
            op.retained_cleanup(c,before);op.no_hazards(c,before)
            op.require(self.period not in before.get('intake_periods',{}),'PERIOD_ALREADY_EXISTS_NO_RETRY')
            server_now=float(c.execute('SELECT extract(epoch FROM clock_timestamp())').fetchone()[0])
            op.require(960 < self.policy['expires_at']-server_now <= 2100,'PERIOD_SERVER_EXPIRY')
            if 'timing_policy' in self.journal['binding']:op.validate_binding(self.journal['binding'],opening=True,now=server_now)
            self.prior_control=copy.deepcopy(before);self.prior_ledger=op.ledger_sha(c);self.server_before=server_now
        if statement == 'SELECT public.ingestion_register_bolton_exception(%s::jsonb)':
            entry=result[0][0]
            server_after=float(c.execute('SELECT extract(epoch FROM clock_timestamp())').fetchone()[0])
            op.require(type(entry) is dict and set(entry)==set(self.policy)|{'registered_at','days'} and type(entry.get('registered_at')) in (int,float) and self.server_before<=entry['registered_at']<=server_after and entry.get('days')=={} and {k:entry[k] for k in self.policy}==self.policy,'PERIOD_REGISTRATION_READBACK')
            self.expected_control=copy.deepcopy(self.prior_control)
            self.expected_control.setdefault('intake_periods',{})[self.period]=entry
        return result


def issue_period(c,b,policy,journal,save):
    """A consumed ARMED vault is required; caller never retries this function."""
    validate_policy(b,policy)
    op.require(journal.get('version')=='FINITE_INTAKE_PERIOD_V1' and journal.get('state')=='ARMED_NO_RETRY' and journal.get('binding')==b and journal.get('policy')==policy,'PERIOD_JOURNAL_BINDING')
    issuer=PeriodIssuer(lambda:c,lambda *_:None,lambda:None,expiry=datetime.fromtimestamp(b['valid_until'],timezone.utc),bindings=b['execution_binding'],limits=dict(connections=(1,1),commands=(32,32,32)))
    issuer.period=b['period'];issuer.policy=policy;issuer.journal=journal;issuer.save=save
    # Existing primitive owns its connection context. Its close is the only close;
    # the surrounding terminal with-context closing an already closed handle is inert.
    try:
        result=issuer.register_intake_period(b['period'],policy)
        return dict(outcome='COMMIT_ACKNOWLEDGED',period=b['period'],policy_sha256=b['period_policy_sha256'],temporary_issuer='REMOVED',original_memberships='PRESERVED',readback='EXACT_ON_SAME_CONNECTION',connections=issuer.connections,retry=False)
    except BaseException:
        if not c.closed:
            try:c.execute('ROLLBACK')
            except BaseException:pass
        if journal.get('state')=='COMMIT_INTENT_NO_RETRY':
            raise op.Denied('PERIOD_COMMIT_ACK_UNCERTAIN') from None
        raise


# GitHub documents variable-length opaque ghs_ installation tokens (~520 bytes),
# not a fixed length. These are LOCAL input bounds, not GitHub format maxima:
# preserve the existing24-byte minimum;2048 fits within the unchanged4000-byte
# serialized secret pipe and32768-byte encrypted vault. No JWT parsing/claims.
INSTALLATION_TOKEN_MIN_BYTES = 24
INSTALLATION_TOKEN_MAX_BYTES = 2048


def installation_token_allowed(token):
    return (type(token) is str and INSTALLATION_TOKEN_MIN_BYTES <= len(token) <= INSTALLATION_TOKEN_MAX_BYTES
            and token.startswith('ghs_') and all(0x21 <= ord(c) <= 0x7e for c in token))


def token_arm(b,token,save):
    op.validate_binding(b)
    op.require(installation_token_allowed(token),'INSTALLATION_TOKEN_ONLY')
    op.require(b.get('publication_scope')=={'repository':'maxrose26/PropertyAIgent','contents':'write','metadata':'read'} and type(b.get('publication_valid_until')) in (int,float),'TOKEN_REVIEWED_SCOPE_REQUIRED')
    state=dict(version='FINITE_PUBLICATION_TOKEN_V1',binding=b,state='ARMED_NO_RETRY',token=token,token_sha256=hashlib.sha256(token.encode()).hexdigest())
    save(state)
    return dict(status='PRIVATE_PUBLICATION_TOKEN_ARMED',token_value='ENCRYPTED_LOCAL_ONLY',provider_calls=0)


def token_load(b,state):
    op.require(state.get('version')=='FINITE_PUBLICATION_TOKEN_V1' and state.get('binding')==b and state.get('state')=='ARMED_NO_RETRY','TOKEN_PRIOR_INTENT_RECONCILE_NO_RETRY')
    token=state.get('token')
    op.require(installation_token_allowed(token) and hashlib.sha256(token.encode()).hexdigest()==state.get('token_sha256'),'TOKEN_PRIVATE_BINDING')
    return token


def claim_revocation(b):
    """Exclusive persistent one-use record; never reset after any uncertainty."""
    path=b['publication_vault_path']+'.revoke-consumed'
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(canonical(dict(version='ONE_PUBLICATION_REVOKE_V1',period=b['period'],retry=False)))
        f.flush();os.fsync(f.fileno())
    fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def token_revoke(b,state,save,*,runner=None):
    """Independent of access, database and Render state, including lost restores."""
    token=token_load(b,state)
    private_path(b,'publication_vault_path',b['publication_vault_path'])
    claim_revocation(b)
    state['state']='REVOKE_INTENT_NO_RETRY';save(state)
    if runner is None:
        def runner(command,**kw):
            return subprocess.run(command,env={'PATH':'/usr/bin:/bin','HOME':str(Path.home()),'GH_TOKEN':token,'GH_PROMPT_DISABLED':'1'},**kw)
    try:
        GitHub(lambda *_:None,lambda:None,runner=runner,bound=1).call('DELETE','installation/token')
    except BaseException:
        raise op.Denied('TOKEN_REVOKE_ACK_UNCERTAIN') from None
    state.update(state='REVOKED_ACKNOWLEDGED',token='');save(state)
    return dict(status='PUBLICATION_TOKEN_REVOCATION_ACKNOWLEDGED',calls=1,retry=False,database_required=False,restoration_required=False)
