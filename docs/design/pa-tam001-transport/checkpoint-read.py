"""PA-TAM001 v1.5 inactive read payload. No retry, save, or live authority."""
import ast, base64, hashlib, io, ipaddress, json, os, re, signal, sys, time
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from psycopg.pq import TransactionStatus
SERVICE='srv-d9qbl7qjnfac73d8nieg'
DEPLOY='2fa0f07cfdfb56a27243ebff18110d441f9da04d'
PIN='f027ba28af69ae70208eab5ed047e4a8a81c6337'
PERIOD='b-bolton-20261103-1105-01'
OWNER_RUN='65ea9cfb9eb260a54b728d1de44eb4d7'
EXPECTED_SHA='a5ba6be74c47eea89bd5068111bf3bc65198c8b4fd54c5036394a2c512f55c52'
EXPECTED_BINDING=dict(revision='ee9dbb7b9dccca161aad46526248f14a9661ce9c',workflow_sha256='946258265cf2e7f346ef57b18c7a7bb5056600581cf51ba4b595459c12c367b9',manifest_sha256='570b020ca03ad47a2d00c265f1a752cd39c0eb70d91c1071f70ffed17de07eba')
CLOSURE=dict(status='VERIFIED',runtime_memberships=0,sessions=0,temporary_owner_absent=True,stable_verifiers='MATCH',suspended=True,configuration_equal=True,environment_equal=True,authorities_closed=True)
FINAL=dict(suspended=True,configuration_equal=True,environment_equal=True)
CAP=65536
# Conservative allowance for both single text-column RowDescriptions, DataRow
# framing, six CommandComplete messages and ReadyForQuery. JSON metadata, base64
# expansion, keys, separators and identity values are counted in server payloads.
PROTOCOL_RESERVE=4096
class Refusal(Exception): pass
def require(ok,code):
    if not ok: raise Refusal(code)
def encoded(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
SETUP=['BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY',"SET LOCAL statement_timeout = '10s'","SET LOCAL lock_timeout = '3s'"]
IDENTITY="""SELECT CASE WHEN octet_length(payload)<=1024 THEN payload
 ELSE '{"refusal":"IDENTITY_RESULT_CAP"}' END AS payload
 FROM (SELECT jsonb_build_array(current_database(),session_user,current_user,
 current_setting('transaction_read_only'),current_setting('statement_timeout'),
 current_setting('lock_timeout'))::text AS payload) s"""

def checkpoint_sql(remaining):
    require(type(remaining) is int and 128<=remaining<=CAP-PROTOCOL_RESERVE,'RESULT_BUDGET')
    # Materialize at most TWO rows once. Never aggregate or encode duplicate
    # bodies. COUNT=2 is enough to refuse, not a claim of the full row count.
    return """WITH rows AS MATERIALIZED (
 SELECT ordinal,body,sha256 FROM public.ingestion_intake_owner_state(
 'b-bolton-20261103-1105-01_owner','65ea9cfb9eb260a54b728d1de44eb4d7','',NULL::bytea)
 LIMIT 2), census AS (SELECT count(*) AS n FROM rows), envelope AS (
 SELECT CASE WHEN n<>1 THEN jsonb_build_object('refusal','CHECKPOINT_ROW_COUNT','rows_seen',n)::text
 ELSE (SELECT CASE
 WHEN ordinal IS DISTINCT FROM 55 THEN '{"refusal":"CHECKPOINT_ORDINAL"}'
 WHEN body IS NULL OR octet_length(body) NOT BETWEEN 1 AND 32768 THEN '{"refusal":"CHECKPOINT_BODY_SIZE"}'
 WHEN sha256 IS DISTINCT FROM 'EXPECTED' OR encode(sha256(body),'hex') IS DISTINCT FROM 'EXPECTED'
 THEN '{"refusal":"CHECKPOINT_HASH"}'
 ELSE jsonb_build_object('ordinal',ordinal,'sha256',sha256,'ciphertext_bytes',octet_length(body),
 'body_base64',encode(body,'base64'))::text END FROM rows LIMIT 1) END AS payload FROM census)
 SELECT CASE WHEN octet_length(payload)<=BUDGET THEN payload
 ELSE '{"refusal":"CHECKPOINT_RESULT_CAP"}' END AS payload FROM envelope""".replace('EXPECTED',EXPECTED_SHA).replace('BUDGET',str(remaining))

PROFILE_STR={'mode':r'render-intake-v1','service_id':r'crn-d9sv93vavr4c73f98rb0','revision':r'[a-f0-9]{40}',
 'browser_path':r'/[A-Za-z0-9_./-]{1,1023}','browser_sha256':r'[a-f0-9]{64}'}
PROFILE_INT=('aggregate_bytes','source_rss_bytes','controller_rss_bytes','reserve_bytes','source_seconds')
def projection(state):
    require(type(state) is dict,'CHECKPOINT_DECODE_SHAPE')
    require(state.get('period')==PERIOD and state.get('status')=='CLOSED'
            and state.get('job',{}).get('id')=='job-dbmq5qutlv9c73bn1rm0'
            and state.get('job_terminal',{}).get('status')=='failed','HISTORICAL_IDENTITY')
    binding=state.get('binding',{})
    require(type(binding) is dict and binding.get('execution_binding')==EXPECTED_BINDING,'HISTORICAL_BUILD')
    require(state.get('closure_verification')==CLOSURE and state.get('final_service')==FINAL,'HISTORICAL_CLOSURE')
    missing=[]
    def profile(value,label):
        if not isinstance(value,dict): missing.append(label); return None
        out={}
        for key,pattern in PROFILE_STR.items():
            if key not in value: missing.append(label+'.'+key); continue
            require(type(value[key]) is str and re.fullmatch(pattern,value[key]) is not None,'PROFILE_VALUE')
            if key=='browser_path': require('..' not in Path(value[key]).parts,'PROFILE_PATH')
            out[key]=value[key]
        for key in PROFILE_INT:
            if key not in value: missing.append(label+'.'+key); continue
            require(type(value[key]) is int and 0<value[key]<=2**40,'PROFILE_LIMIT')
            out[key]=value[key]
        return out
    out=dict(period=PERIOD,status='CLOSED',job_id='job-dbmq5qutlv9c73bn1rm0',job_terminal='failed',
             execution_binding=EXPECTED_BINDING,closure_verification=CLOSURE,final_service=FINAL)
    out['profile']=profile(state.get('profile'),'profile')
    out['bound_profile']=profile(binding.get('render_profile'),'binding.render_profile')
    out['profile_copies_equal']=out['profile']==out['bound_profile'] if out['profile'] is not None and out['bound_profile'] is not None else None
    safe={}
    patterns={'route':r'POOLER','credential_policy':r'STABLE_RESTRICTED_V1',
              'render_config_sha256':r'[a-f0-9]{64}'}
    for key,pattern in patterns.items():
        if key not in binding: missing.append('binding.'+key);continue
        require(type(binding[key]) is str and re.fullmatch(pattern,binding[key]) is not None,'BINDING_VALUE')
        safe[key]=binding[key]
    for key in ('hostaddr','owner_hostaddr'):
        if key not in binding:missing.append('binding.'+key);continue
        require(type(binding[key]) is str and len(binding[key])<=15,'BINDING_ADDRESS')
        try: require(ipaddress.ip_address(binding[key]).version==4,'BINDING_ADDRESS')
        except ValueError: raise Refusal('BINDING_ADDRESS') from None
        safe[key]=binding[key]
    for key in ('valid_until','runtime_deadline'):
        if key not in binding:missing.append('binding.'+key);continue
        require(type(binding[key]) in (int,float) and 0<binding[key]<10**11,'BINDING_DEADLINE')
        safe[key]=binding[key]
    # Deployment is an object in some old receipts. Never pass that object
    # wholesale: retain only specifically typed public identifiers.
    deployment=binding.get('retained_deployment')
    if type(deployment) is str and re.fullmatch(r'dep-[a-z0-9]{1,40}|[a-f0-9]{40}',deployment):safe['retained_deployment']=deployment
    elif type(deployment) is dict:
        safe['retained_deployment']={}
        for key,pattern in [('id',r'dep-[a-z0-9]{1,40}'),('commit',r'[a-f0-9]{40}')]:
            value=deployment.get(key)
            if type(value) is str and re.fullmatch(pattern,value):safe['retained_deployment'][key]=value
            else:missing.append('binding.retained_deployment.'+key)
    else: missing.append('binding.retained_deployment')
    out['binding']=safe
    credentials=state.get('stable_credentials',{})
    verifier=credentials.get('verifier_sha256') if type(credentials) is dict else None
    out['stable_credential_verifier_present']=verifier is not None
    out['bound_verifier_equal']=(verifier==binding['credential_verifier_sha256']) if verifier is not None and 'credential_verifier_sha256' in binding else None
    out['stable_configuration_present']=type(state.get('stable_configuration')) is dict
    out['missing_fields']=missing
    out['historical_only']=True
    require(len(encoded(out))<=8192,'PROJECTION_CAP')
    return out

# Exact AST source routines from frozen #213; embedded, never fetched at runtime.
DECODER_SHA = '12129e914911d8381efd59718b7beff04fba4b6c68e97495dd45a51c78d01dd6'
DECODER_SOURCE = 'Y2xhc3MgVmF1bHQ6CiAgICAiIiJBdXRoZW50aWNhdGVkIGVuY3J5cHRlZCBjbG9zdXJlIGJhc2VsaW5lLCBmc3luY2VkIGJlZm9yZSBlZmZlY3RzOyBrZXkgc3RheXMgaW4gbWVtb3J5LiIiIgogICAgZGVmIF9faW5pdF9fKHNlbGYsIHBhdGgsIHBhc3NwaHJhc2UsICosIGNyZWF0ZT1GYWxzZSk6CiAgICAgICAgc2VsZi5wYXRoID0gUGF0aChwYXRoKQogICAgICAgIHJlcXVpcmUobGVuKHBhc3NwaHJhc2UpID49IDI0LCAnVkFVTFRfUEFTU1BIUkFTRV9MRU5HVEgnKQogICAgICAgIGlmIGNyZWF0ZToKICAgICAgICAgICAgZmQgPSBvcy5vcGVuKHNlbGYucGF0aCwgb3MuT19DUkVBVCB8IG9zLk9fRVhDTCB8IG9zLk9fV1JPTkxZIHwgb3MuT19OT0ZPTExPVywgMG82MDApCiAgICAgICAgICAgIG9zLmNsb3NlKGZkKQogICAgICAgICAgICBzZWxmLnNhbHQgPSBvcy51cmFuZG9tKDE2KQogICAgICAgIGVsc2U6CiAgICAgICAgICAgIHNlbGYuX2NoZWNrKCk7IHJhdyA9IHNlbGYucGF0aC5yZWFkX2J5dGVzKCkKICAgICAgICAgICAgcmVxdWlyZShsZW4ocmF3KSA+IDE2LCAnVkFVTFRfSU5DT01QTEVURScpCiAgICAgICAgICAgIHNlbGYuc2FsdCA9IHJhd1s6MTZdCiAgICAgICAga2V5ID0gU2NyeXB0KHNhbHQ9c2VsZi5zYWx0LCBsZW5ndGg9MzIsIG49MioqMTQsIHI9OCwgcD0xKS5kZXJpdmUocGFzc3BocmFzZS5lbmNvZGUoKSkKICAgICAgICBzZWxmLmNpcGhlciA9IEZlcm5ldChiYXNlNjQudXJsc2FmZV9iNjRlbmNvZGUoa2V5KSkKCiAgICBkZWYgX2NoZWNrKHNlbGYpOgogICAgICAgIHMgPSBzZWxmLnBhdGgubHN0YXQoKQogICAgICAgIHJlcXVpcmUoc3RhdC5TX0lTUkVHKHMuc3RfbW9kZSkgYW5kIHMuc3RfdWlkID09IG9zLmdldHVpZCgpIGFuZCBzdGF0LlNfSU1PREUocy5zdF9tb2RlKSA9PSAwbzYwMAogICAgICAgICAgICAgICAgYW5kIHMuc3RfbmxpbmsgPT0gMSBhbmQgcy5zdF9zaXplIDw9IFZBVUxUX0xJTUlULCAnUFJJVkFURV9WQVVMVF9SRVFVSVJFRCcpCgogICAgZGVmIHNhdmUoc2VsZiwgdmFsdWUpOgogICAgICAgIHNlbGYuX2NoZWNrKCkKICAgICAgICByYXcgPSBzZWxmLnNhbHQgKyBzZWxmLmNpcGhlci5lbmNyeXB0KGNhbm9uaWNhbCh2YWx1ZSkpCiAgICAgICAgcmVxdWlyZShsZW4ocmF3KSA8PSBWQVVMVF9MSU1JVCwgJ1ZBVUxUXzMyS19CT1VORCcpCiAgICAgICAgdGVtcG9yYXJ5ID0gc2VsZi5wYXRoLndpdGhfbmFtZShzZWxmLnBhdGgubmFtZSArICcubmV4dCcpCiAgICAgICAgZmQgPSBvcy5vcGVuKHRlbXBvcmFyeSwgb3MuT19DUkVBVCB8IG9zLk9fRVhDTCB8IG9zLk9fV1JPTkxZIHwgb3MuT19OT0ZPTExPVywgMG82MDApCiAgICAgICAgdHJ5OgogICAgICAgICAgICB3aXRoIG9zLmZkb3BlbihmZCwgJ3diJykgYXMgZjoKICAgICAgICAgICAgICAgIGYud3JpdGUocmF3KTsgZi5mbHVzaCgpOyBvcy5mc3luYyhmLmZpbGVubygpKQogICAgICAgICAgICBvcy5yZXBsYWNlKHRlbXBvcmFyeSwgc2VsZi5wYXRoKQogICAgICAgICAgICBmZCA9IG9zLm9wZW4oc2VsZi5wYXRoLnBhcmVudCwgb3MuT19SRE9OTFkgfCBvcy5PX0RJUkVDVE9SWSkKICAgICAgICAgICAgdHJ5OiBvcy5mc3luYyhmZCkKICAgICAgICAgICAgZmluYWxseTogb3MuY2xvc2UoZmQpCiAgICAgICAgZmluYWxseToKICAgICAgICAgICAgaWYgdGVtcG9yYXJ5LmV4aXN0cygpOiB0ZW1wb3JhcnkudW5saW5rKCkKCiAgICBkZWYgbG9hZChzZWxmKToKICAgICAgICBzZWxmLl9jaGVjaygpCiAgICAgICAgcmV0dXJuIGpzb24ubG9hZHMoc2VsZi5jaXBoZXIuZGVjcnlwdChzZWxmLnBhdGgucmVhZF9ieXRlcygpWzE2Ol0pKQoKZGVmIGh5ZHJhdGVkX3N0YXRlKHN0b3JlZCk6CiAgICBpZiBpc2luc3RhbmNlKHN0b3JlZCxkaWN0KToKICAgICAgICBwYWNrZWQ9c3RvcmVkLmdldCgnam91cm5hbF9tZXRhZGF0YScpCiAgICAgICAgaWYgcGFja2VkIGlzIG5vdCBOb25lOgogICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICBvcC5yZXF1aXJlKHN0b3JlZC5nZXQoJ2NsZWFudXBfcmVzZXJ2ZScse30pLmdldCgndmVyc2lvbicpIGluICgnQ0xFQU5VUF9SRVNFUlZFX1YxJywnQ0xFQU5VUF9SRVNFUlZFX0RJQUdOT1NUSUMwMl8zNktfVjEnKSBhbmQgaXNpbnN0YW5jZShwYWNrZWQsZGljdCkgYW5kIHNldChwYWNrZWQpPT17J3ZlcnNpb24nLCdieXRlcycsJ3NoYTI1NicsJ2RhdGEnfSBhbmQgcGFja2VkWyd2ZXJzaW9uJ109PSdKT1VSTkFMX01FVEFEQVRBX0RFRkxBVEVfVjEnIGFuZCB0eXBlKHBhY2tlZFsnYnl0ZXMnXSkgaXMgaW50IGFuZCAwPD1wYWNrZWRbJ2J5dGVzJ108PTY1NTM2LCdPV05FUl9DT0RFX0JJTkRJTkcnKQogICAgICAgICAgICAgICAgY29tcHJlc3NlZD1iYXNlNjQuYjY0ZGVjb2RlKHBhY2tlZFsnZGF0YSddLHZhbGlkYXRlPVRydWUpCiAgICAgICAgICAgICAgICBvcC5yZXF1aXJlKGxlbihjb21wcmVzc2VkKTw9MzI3NjgsJ09XTkVSX0NPREVfQklORElORycpCiAgICAgICAgICAgICAgICBkZWNvZGVyPXpsaWIuZGVjb21wcmVzc29iaigpO3Jhdz1kZWNvZGVyLmRlY29tcHJlc3MoY29tcHJlc3NlZCxwYWNrZWRbJ2J5dGVzJ10rMSkKICAgICAgICAgICAgICAgIG9wLnJlcXVpcmUoZGVjb2Rlci5lb2YgYW5kIG5vdCBkZWNvZGVyLnVudXNlZF9kYXRhIGFuZCBub3QgZGVjb2Rlci51bmNvbnN1bWVkX3RhaWwgYW5kIGxlbihyYXcpPT1wYWNrZWRbJ2J5dGVzJ10gYW5kIGhhc2hsaWIuc2hhMjU2KHJhdykuaGV4ZGlnZXN0KCk9PXBhY2tlZFsnc2hhMjU2J10sJ09XTkVSX0NPREVfQklORElORycpCiAgICAgICAgICAgICAgICBkZWNvZGVkPWpzb24ubG9hZHMocmF3KQogICAgICAgICAgICAgICAgb3AucmVxdWlyZShpc2luc3RhbmNlKGRlY29kZWQsZGljdCkgYW5kIHNldChkZWNvZGVkKTw9Sk9VUk5BTF9NRVRBREFUQV9GSUVMRFMgYW5kIG5vdCBzZXQoZGVjb2RlZCkuaW50ZXJzZWN0aW9uKHN0b3JlZCkgYW5kIGNhbm9uaWNhbChkZWNvZGVkKT09cmF3LCdPV05FUl9DT0RFX0JJTkRJTkcnKQogICAgICAgICAgICAgICAgZGVsIHN0b3JlZFsnam91cm5hbF9tZXRhZGF0YSddO3N0b3JlZC51cGRhdGUoZGVjb2RlZCkKICAgICAgICAgICAgZXhjZXB0IChWYWx1ZUVycm9yLFR5cGVFcnJvcixLZXlFcnJvcix6bGliLmVycm9yKTpyYWlzZSBvcC5EZW5pZWQoJ09XTkVSX0NPREVfQklORElORycpIGZyb20gTm9uZQogICAgICAgIGJpbmRpbmc9c3RvcmVkLmdldCgnYWNjZXNzJyx7fSkuZ2V0KCdiaW5kaW5nJyx7fSkKICAgICAgICBpZiBpc2luc3RhbmNlKGJpbmRpbmcsZGljdCkgYW5kIGJpbmRpbmcuZ2V0KCd2ZXJzaW9uJyk9PSdST09UX0JJTkRJTkdfUkVGRVJFTkNFX1YxJzoKICAgICAgICAgICAgb3AucmVxdWlyZShzZXQoYmluZGluZyk9PXsndmVyc2lvbicsJ3NoYTI1Nid9IGFuZCBzdG9yZWQuZ2V0KCdjbGVhbnVwX3Jlc2VydmUnLHt9KS5nZXQoJ3ZlcnNpb24nKSBpbiAoJ0NMRUFOVVBfUkVTRVJWRV9WMScsJ0NMRUFOVVBfUkVTRVJWRV9ESUFHTk9TVElDMDJfMzZLX1YxJykgYW5kCiAgICAgICAgICAgICAgICBiaW5kaW5nWydzaGEyNTYnXT09aGFzaGxpYi5zaGEyNTYoY2Fub25pY2FsKHN0b3JlZC5nZXQoJ2JpbmRpbmcnKSkpLmhleGRpZ2VzdCgpLCdPV05FUl9DT0RFX0JJTkRJTkcnKQogICAgICAgICAgICBzdG9yZWRbJ2FjY2VzcyddWydiaW5kaW5nJ109Y29weS5kZWVwY29weShzdG9yZWRbJ2JpbmRpbmcnXSkKICAgIHJldHVybiBzdG9yZWQKCmRlZiBfdmF1bHQoc2VsZixyYXc9Tm9uZSx2YWx1ZT1Ob25lKToKICAgICAgICAjIE9ubHkgZW5jcnlwdGVkIGJ5dGVzIHRvdWNoIHRoZSB0ZW1wb3JhcnkgZmlsZXN5c3RlbS4gTm8gbmV3IGNyZWRlbnRpYWwKICAgICAgICAjIGlzIHBlcnNpc3RlZDsgcmVjb3ZlcnkgZGVyaXZlcyBpdHMga2V5IGZyb20gZXhpc3RpbmcgcHJvdGVjdGVkIGNvbmZpZy4KICAgICAgICB3aXRoIHRlbXBmaWxlLlRlbXBvcmFyeURpcmVjdG9yeShwcmVmaXg9J3Byb3BlcnR5YWlnZW50LW93bmVyLScpIGFzIGZvbGRlcjoKICAgICAgICAgICAgcD1QYXRoKGZvbGRlcikvJ3N0YXRlLnZhdWx0JwogICAgICAgICAgICBpZiByYXcgaXMgTm9uZToKICAgICAgICAgICAgICAgIHY9VmF1bHQocCxzZWxmLmRiLmtleSxjcmVhdGU9VHJ1ZSk7di5zYXZlKHNlcmlhbGl6ZWRfc3RhdGUodmFsdWUpKTtyZXR1cm4gcC5yZWFkX2J5dGVzKCkKICAgICAgICAgICAgZmQ9b3Mub3BlbihwLG9zLk9fQ1JFQVR8b3MuT19FWENMfG9zLk9fV1JPTkxZLDBvNjAwKQogICAgICAgICAgICB3aXRoIG9zLmZkb3BlbihmZCwnd2InKSBhcyBmOmYud3JpdGUocmF3KQogICAgICAgICAgICByZXR1cm4gaHlkcmF0ZWRfc3RhdGUoVmF1bHQocCxzZWxmLmRiLmtleSkubG9hZCgpKQoKZGVmIGNhbm9uaWNhbCh2KTpyZXR1cm4ganNvbi5kdW1wcyh2LHNvcnRfa2V5cz1UcnVlLHNlcGFyYXRvcnM9KCcsJywnOicpLGFsbG93X25hbj1GYWxzZSkuZW5jb2RlKCkK'

def decode(db,raw):
    import copy,stat,tempfile,zlib
    from types import SimpleNamespace
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    source=base64.b64decode(DECODER_SOURCE)
    require(hashlib.sha256(source).hexdigest()==DECODER_SHA,'DECODER_SOURCE_DRIFT')
    scope=dict(base64=base64,hashlib=hashlib,json=json,os=os,Path=Path,stat=stat,
               tempfile=tempfile,copy=copy,zlib=zlib,Fernet=Fernet,Scrypt=Scrypt,
               require=require,op=SimpleNamespace(require=require),VAULT_LIMIT=32768,
               JOURNAL_METADATA_FIELDS=frozenset(('binding','access','artifact','profile','policy','startup_preflight','observations','job','job_terminal','runtime_qualification','source_result','independent_result','original_environment','stable_credentials','stable_configuration')))
    exec(compile(source,'pinned-owner-decoder.py','exec'),scope)
    return scope['_vault'](SimpleNamespace(db=db),raw=raw)

def run(factory,started,decoder=decode):
    out=dict(scope='PA-TAM001 v1.5',statements_attempted=0,statements_completed=0,connections_attempted=0,
             connections_opened=0,returned_value_bytes=0,result_bytes_with_metadata_reserve=PROTOCOL_RESERVE,
             rollback_attempted=False,rollback_acknowledged=False,connection_closed=None,
             status='STOP_INCOMPLETE_NO_RETRY',retry=False)
    def deadline(*_):raise Refusal('OVERALL_DEADLINE')
    def arm(end):
        left=end-(time.monotonic()-started);require(left>0,'OVERALL_DEADLINE');signal.setitimer(signal.ITIMER_REAL,left)
    def execute(c,sql):
        require(out['statements_attempted']<6,'STATEMENT_CAP');out['statements_attempted']+=1
        cur=c.execute(sql);out['statements_completed']+=1;return cur
    def payload(c,sql):
        cur=execute(c,sql);rows=cur.fetchall();require(len(rows)==1 and len(rows[0])==1 and type(rows[0][0]) is str,'RESULT_SHAPE')
        raw=rows[0][0];size=len(raw.encode());out['returned_value_bytes']+=size
        out['result_bytes_with_metadata_reserve']=PROTOCOL_RESERVE+out['returned_value_bytes']
        require(out['result_bytes_with_metadata_reserve']<=CAP,'RESULT_CAP')
        return json.loads(raw)
    previous=signal.getsignal(signal.SIGALRM);term=signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGALRM,deadline);signal.signal(signal.SIGTERM,deadline)
    try:
        arm(15);db=factory();out['connections_attempted']=1
        with db.connection() as c:
            out['connections_opened']=1
            try:
                for sql in SETUP:execute(c,sql)
                identity=payload(c,IDENTITY)
                require(identity==['postgres','postgres','postgres','on','10s','3s'],'ACTUAL_IDENTITY_OR_SETTINGS')
                row=payload(c,checkpoint_sql(CAP-out['result_bytes_with_metadata_reserve']))
                require(type(row) is dict,'CHECKPOINT_ENVELOPE')
                if 'refusal' in row:
                    require(row['refusal'] in {'CHECKPOINT_ROW_COUNT','CHECKPOINT_ORDINAL','CHECKPOINT_BODY_SIZE','CHECKPOINT_HASH','CHECKPOINT_RESULT_CAP'},'CHECKPOINT_ENVELOPE')
                    raise Refusal(row['refusal'])
                require(set(row)=={'ordinal','sha256','ciphertext_bytes','body_base64'},'CHECKPOINT_ENVELOPE')
                require(row['ordinal']==55 and type(row['ciphertext_bytes']) is int and 1<=row['ciphertext_bytes']<=32768,'CHECKPOINT_METADATA')
                require(row['sha256']==EXPECTED_SHA and type(row['body_base64']) is str,'CHECKPOINT_HASH')
                raw=base64.b64decode(row['body_base64'].replace('\n',''),validate=True)
                require(len(raw)==row['ciphertext_bytes'] and hashlib.sha256(raw).hexdigest()==EXPECTED_SHA,'CHECKPOINT_HASH')
                state=decoder(db,raw);observed=projection(state)
                out['observations']=observed
                out.update(checkpoint_ordinal=55,checkpoint_sha256=EXPECTED_SHA,status='READ_COMPLETED_REVIEW_REQUIRED')
            finally:
                try:
                    arm(18);out['rollback_attempted']=True;cur=execute(c,'ROLLBACK')
                    out['rollback_acknowledged']=cur.statusmessage=='ROLLBACK' and c.info.transaction_status==TransactionStatus.IDLE
                except BaseException:out['rollback_acknowledged']=False
                finally:
                    try:arm(18.5);c.close();out['connection_closed']=bool(c.closed)
                    except BaseException:out['connection_closed']=False
    except BaseException as exc:
        out['status']='STOP_INCOMPLETE_NO_RETRY'
        out['reason']=str(exc) if isinstance(exc,Refusal) else 'CONFIGURATION_DATABASE_OR_DECODE_REFUSAL'
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous);signal.signal(signal.SIGTERM,term)
        out['elapsed_ms']=int((time.monotonic()-started)*1000)
        if out['rollback_acknowledged'] is not True or out['connection_closed'] is not True:out['status']='STOP_INCOMPLETE_NO_RETRY'
    return out

CLASS_SHA = '4959d79558bd5c4a5aabb8ec6c5dd6f05c02720c23bcefa9bf6985507673b36f'
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
