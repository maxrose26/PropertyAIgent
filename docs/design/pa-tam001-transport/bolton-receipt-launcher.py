"""PA-TAM001 v1.4 candidate. Preparation is NOT production authority."""
import base64, hashlib, json, os, re, signal, socket, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
DECISION = 'PA-TAM001 v1.4'
CORE_SHA = '4812f04b185c0ac16a545dbc6218491c350156d53771efc71eeb3a7d22f7989d'
INSTANCE = 'srv-d9qbl7qjnfac73d8nieg-8684bcc77c-xgxgz'
MAX_RECEIPT = 131072

def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

def sha(raw): return hashlib.sha256(raw).hexdigest()

def save(path, value):
    raw = encoded(value)
    if len(raw) > MAX_RECEIPT: raise ValueError('RECEIPT_CAP')
    fd = os.open(str(path)+'.tmp', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    os.replace(str(path)+'.tmp', path)

def read_file(path):
    if path.is_symlink(): raise ValueError('SYMLINK')
    with path.open('rb') as f: raw=f.read(MAX_RECEIPT+1)
    if len(raw)>MAX_RECEIPT: raise ValueError('RECEIPT_CAP')
    return raw, json.loads(raw)

def identity(invocation):
    if not re.fullmatch(r'pa-tam001-v1-4-[a-z0-9-]{1,60}', invocation): raise ValueError('ID')
    return dict(invocation_id=invocation, launcher_sha256=sha(Path(__file__).read_bytes()),
                core_sha256=CORE_SHA, decision_id=DECISION, instance=socket.gethostname(),
                expected_service='srv-d9qbl7qjnfac73d8nieg',
                expected_deployment='2fa0f07cfdfb56a27243ebff18110d441f9da04d',
                owner_adapter_pin='f027ba28af69ae70208eab5ed047e4a8a81c6337')

def start(root, binding, started):
    age=time.monotonic()-started
    if age<0 or age>=10: raise ValueError('PRELAUNCH_DEADLINE')
    if binding['instance']!=INSTANCE: raise ValueError('INSTANCE_DRIFT')
    os.umask(0o077)
    root.mkdir(mode=0o700)  # Exclusive ID; no replacement, retry or resume.
    save(root/'ack.json', dict(binding, kind='INVOCATION_ACCEPTED_PRE_DATABASE',
        accepted_at=datetime.now(timezone.utc).isoformat(), started_monotonic=started,
        approval_required=True, database_result='UNKNOWN', retry=False))
    # timeout remains independent of the worker's Python signal/cleanup handlers.
    remaining=18.5-(time.monotonic()-started)
    if remaining<=0: raise ValueError('PRELAUNCH_DEADLINE')
    with (root/'worker.log').open('xb') as log:
        subprocess.Popen(['timeout','--signal=TERM','--kill-after=1s',str(remaining)+'s',
            sys.executable,'-B',str(Path(__file__).resolve()),'worker',binding['invocation_id'],str(started)],
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,close_fds=True)
    print((root/'ack.json').read_text(),flush=True)

def load_core():
    raw=base64.b64decode(CORE)
    if sha(raw)!=CORE_SHA: raise ValueError('CORE_PIN')
    scope={'__name__':'frozen_bolton_core'}
    exec(compile(raw,'frozen-bolton-read.py','exec'),scope)
    return scope

def worker(root, binding, started, core=None):
    ack_raw,ack=read_file(root/'ack.json')
    if any(ack.get(k)!=v for k,v in binding.items()) or ack['started_monotonic']!=started:
        raise ValueError('ACK_BINDING')
    fd=os.open(root/'worker.claim',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    if time.monotonic()-started>=15: return  # ACK-only is UNKNOWN.
    def expired(*_): raise TimeoutError('PREFLIGHT_TIMEOUT')
    signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,15-(time.monotonic()-started))
    try:
        sys.path.insert(0,os.getcwd())  # Same import root as the reviewed python -c route.
        engine=core if core is not None else load_core()
        factory=engine['preflight']()
    except BaseException:
        result=dict(status='PREFLIGHT_REFUSED_NO_DATABASE_ATTEMPT',connections_attempted=0,
            statements_attempted=0,rollback_acknowledged=None,connection_closed=None)
    else:
        # Frozen runner: one connection, three setup+three SELECT+ROLLBACK,
        # 10s statement/3s lock, server+cumulative cap, 15s work/18s cleanup.
        result=engine['run'](factory,started)
        result['scope']=DECISION
        result['execution_id']=binding['invocation_id']
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
    save(root/'completion.json',dict(binding,kind='BOUNDED_READ_RESULT',
        ack_sha256=sha(ack_raw),finished_at=datetime.now(timezone.utc).isoformat(),
        overall_elapsed_ms=int((time.monotonic()-started)*1000),result=result,retry=False))

def readback(root,binding):
    try:
        if binding['instance']!=INSTANCE or root.is_symlink(): raise ValueError('INSTANCE_OR_PATH')
        ar,a=read_file(root/'ack.json'); cr,c=read_file(root/'completion.json')
        if any(a.get(k)!=v or c.get(k)!=v for k,v in binding.items()): raise ValueError('BINDING')
        if a['kind']!='INVOCATION_ACCEPTED_PRE_DATABASE' or c['kind']!='BOUNDED_READ_RESULT': raise ValueError('KIND')
        if c['ack_sha256']!=sha(ar): raise ValueError('ACK_HASH')
        r=c['result']
        if type(c['overall_elapsed_ms']) is not int or not 0<=c['overall_elapsed_ms']<20000: raise ValueError('DEADLINE')
        if not isinstance(r,dict): raise ValueError('RESULT')
        if r.get('status')=='READ_COMPLETED_REVIEW_REQUIRED':
            if not (r['execution_id']==binding['invocation_id'] and r['connections_opened']==1 and
                    r['connections_attempted']==1 and r['statements_attempted']==7 and
                    r['statements_completed']==7 and 0<=r['returned_value_bytes']<=65536 and
                    r['rollback_acknowledged'] is True and r['connection_closed'] is True):
                raise ValueError('RESULT_LIMITS_OR_CLEANUP')
        return dict(verification='RECEIPT_INTEGRITY_VERIFIED_NOT_BOLTON_MATCH',ack=a,completion=c,
                    ack_sha256=sha(ar),completion_sha256=sha(cr))
    except (OSError,ValueError,KeyError,TypeError):
        return dict(verification='UNKNOWN_STOP_NO_RETRY',invocation_id=binding['invocation_id'])

def main():
    action,invocation,*args=sys.argv[1:]
    binding=identity(invocation);root=Path('/tmp')/invocation
    if action=='read': print(json.dumps(readback(root,binding),sort_keys=True));return
    if action not in ('start','worker') or len(args)!=1: raise ValueError('ACTION')
    started=float(args[0])
    if action=='start': start(root,binding,started)
    else: worker(root,binding,started)

CORE = 'IiIiU2luZ2xlIGFwcHJvdmVkIFBBLVRBTTAwMSB2MS4zIHJlYWQuIE5vIHJldHJ5IG9yIG9wZXJhdGlvbmFsIG11dGF0aW9uLiIiIgppbXBvcnQgYXN0LCBoYXNobGliLCBpbywganNvbiwgb3MsIHNpZ25hbCwgc3lzLCB0aW1lLCB1dWlkCmZyb20gY29udGV4dGxpYiBpbXBvcnQgcmVkaXJlY3Rfc3Rkb3V0LCByZWRpcmVjdF9zdGRlcnIKZnJvbSBkYXRldGltZSBpbXBvcnQgZGF0ZXRpbWUsIHRpbWV6b25lCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aApTRVJWSUNFID0gJ3Nydi1kOXFibDdxam5mYWM3M2Q4bmllZycKREVQTE9ZID0gJzJmYTBmMDdjZmRmYjU2YTI3MjQzZWJmZjE4MTEwZDQ0MWY5ZGEwNGQnClBJTiA9ICdmMDI3YmEyOGFmNjlhZTcwMjA4ZWFiNWVkMDQ3ZTRhOGE4MWM2MzM3JwpDTEFTU19TSEEgPSAnNDk1OWQ3OTU1OGJkNWM0YTVhYWJiOGVjNmM1ZGQ2ZjA1YzAyNzIwYzIzYmNlZmE5YmY2OTg1NTA3NjczYjM2ZicKY2xhc3MgUmVmdXNhbChFeGNlcHRpb24pOiBwYXNzCmRlZiByZXF1aXJlKG9rLCBjb2RlKToKICAgIGlmIG5vdCBvazogcmFpc2UgUmVmdXNhbChjb2RlKQoKZGVmIHJ1bihmYWN0b3J5LCBzdGFydGVkKToKICAgIG91dCA9IGRpY3Qoc2NvcGU9J1BBLVRBTTAwMSB2MS4zJywgZXhlY3V0aW9uX2lkPXN0cih1dWlkLnV1aWQ0KCkpLAogICAgICAgIHN0YXJ0ZWRfYXQ9ZGF0ZXRpbWUubm93KHRpbWV6b25lLnV0YykuaXNvZm9ybWF0KCksIHN0YXRlbWVudHNfYXR0ZW1wdGVkPTAsCiAgICAgICAgc3RhdGVtZW50c19jb21wbGV0ZWQ9MCwgY29ubmVjdGlvbnNfYXR0ZW1wdGVkPTAsIGNvbm5lY3Rpb25zX29wZW5lZD0wLAogICAgICAgIHJldHVybmVkX3ZhbHVlX2J5dGVzPTAsIG9ic2VydmF0aW9ucz17fSwgcm9sbGJhY2tfYWNrbm93bGVkZ2VkPUZhbHNlLAogICAgICAgIHJvbGxiYWNrX2F0dGVtcHRlZD1GYWxzZSwgY29ubmVjdGlvbl9jbG9zZWQ9Tm9uZSwgc3RhdHVzPSdJTkNPTVBMRVRFJywgcmV0cnk9RmFsc2UpCiAgICBjID0gTm9uZQogICAgZGVmIGRlYWRsaW5lKCpfKTogcmFpc2UgUmVmdXNhbCgnT1ZFUkFMTF9ERUFETElORScpCiAgICBkZWYgYXJtKHNlY29uZHMpOgogICAgICAgIHJlbWFpbmluZz1zZWNvbmRzLSh0aW1lLm1vbm90b25pYygpLXN0YXJ0ZWQpCiAgICAgICAgcmVxdWlyZShyZW1haW5pbmc+MCwgJ09WRVJBTExfREVBRExJTkUnKQogICAgICAgIHNpZ25hbC5zZXRpdGltZXIoc2lnbmFsLklUSU1FUl9SRUFMLHJlbWFpbmluZykKICAgIGRlZiBleGVjdXRlKHN0YXRlbWVudCk6CiAgICAgICAgcmVxdWlyZShvdXRbJ3N0YXRlbWVudHNfYXR0ZW1wdGVkJ108NywnU1RBVEVNRU5UX0NBUCcpCiAgICAgICAgb3V0WydzdGF0ZW1lbnRzX2F0dGVtcHRlZCddKz0xCiAgICAgICAgY3Vyc29yPWMuZXhlY3V0ZShzdGF0ZW1lbnQpCiAgICAgICAgb3V0WydzdGF0ZW1lbnRzX2NvbXBsZXRlZCddKz0xCiAgICAgICAgcmV0dXJuIGN1cnNvcgogICAgc2lnbmFsLnNpZ25hbChzaWduYWwuU0lHQUxSTSxkZWFkbGluZSkKICAgIHNpZ25hbC5zaWduYWwoc2lnbmFsLlNJR1RFUk0sZGVhZGxpbmUpCiAgICB0cnk6CiAgICAgICAgYXJtKDE1KQogICAgICAgIGRiPWZhY3RvcnkoKQogICAgICAgIG91dFsnY29ubmVjdGlvbnNfYXR0ZW1wdGVkJ109MQogICAgICAgIHdpdGggZGIuY29ubmVjdGlvbigpIGFzIGM6CiAgICAgICAgICAgIG91dFsnY29ubmVjdGlvbnNfb3BlbmVkJ109MQogICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICBmb3Igc3RhdGVtZW50IGluIFNUQVRFTUVOVFNbOjNdOiBleGVjdXRlKHN0YXRlbWVudCkKICAgICAgICAgICAgICAgIGZvciBuYW1lLCBzdGF0ZW1lbnQgaW4gemlwKCgnY29udHJvbGxlcicsJ3dvcmsnLCdzZXNzaW9ucycpLFNUQVRFTUVOVFNbMzo2XSk6CiAgICAgICAgICAgICAgICAgICAgIyBTYW1lIGFwcHJvdmVkIFNFTEVDVCwgYm91bmRlZCBpbiB0aGUgc2VydmVyIGJlZm9yZSByZXR1cm4uCiAgICAgICAgICAgICAgICAgICAgYm91bmRlZD0iU0VMRUNUIENBU0UgV0hFTiBvY3RldF9sZW5ndGgocGF5bG9hZCk+MjEwMDAgVEhFTiAnbnVsbCcgRUxTRSBwYXlsb2FkIEVORCBGUk9NIChTRUxFQ1QgY29hbGVzY2UoanNvbmJfYWdnKHRvX2pzb25iKHEpKSwnW10nOjpqc29uYik6OnRleHQgQVMgcGF5bG9hZCBGUk9NICgiK3N0YXRlbWVudCsiKSBxKSBiIgogICAgICAgICAgICAgICAgICAgIHJhdz1leGVjdXRlKGJvdW5kZWQpLmZldGNob25lKClbMF0KICAgICAgICAgICAgICAgICAgICBvdXRbJ3JldHVybmVkX3ZhbHVlX2J5dGVzJ10rPWxlbihyYXcuZW5jb2RlKCkpCiAgICAgICAgICAgICAgICAgICAgcmVxdWlyZShvdXRbJ3JldHVybmVkX3ZhbHVlX2J5dGVzJ108PTY1NTM2LCdSRVNVTFRfQ0FQJykKICAgICAgICAgICAgICAgICAgICByb3dzPWpzb24ubG9hZHMocmF3KQogICAgICAgICAgICAgICAgICAgIHJlcXVpcmUoaXNpbnN0YW5jZShyb3dzLGxpc3QpLCdTRVJWRVJfUkVTVUxUX0NBUCcpCiAgICAgICAgICAgICAgICAgICAgb3V0WydvYnNlcnZhdGlvbnMnXVtuYW1lXT1yb3dzCiAgICAgICAgICAgICAgICBvdXRbJ3N0YXR1cyddPSdSRUFEX0NPTVBMRVRFRF9SRVZJRVdfUkVRVUlSRUQnCiAgICAgICAgICAgIGZpbmFsbHk6CiAgICAgICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICAgICAgYXJtKDE4KQogICAgICAgICAgICAgICAgICAgIG91dFsncm9sbGJhY2tfYXR0ZW1wdGVkJ109VHJ1ZQogICAgICAgICAgICAgICAgICAgIGN1cnNvcj1leGVjdXRlKFNUQVRFTUVOVFNbNl0pCiAgICAgICAgICAgICAgICAgICAgb3V0Wydyb2xsYmFja19hY2tub3dsZWRnZWQnXT0oY3Vyc29yLnN0YXR1c21lc3NhZ2U9PSdST0xMQkFDSycgYW5kIGMuaW5mby50cmFuc2FjdGlvbl9zdGF0dXMubmFtZT09J0lETEUnKQogICAgICAgICAgICAgICAgZXhjZXB0IEJhc2VFeGNlcHRpb246CiAgICAgICAgICAgICAgICAgICAgb3V0Wydyb2xsYmFja19hY2tub3dsZWRnZWQnXT1GYWxzZQogICAgICAgICAgICAgICAgZmluYWxseToKICAgICAgICAgICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICAgICAgICAgIGMuY2xvc2UoKQogICAgICAgICAgICAgICAgICAgICAgICBvdXRbJ2Nvbm5lY3Rpb25fY2xvc2VkJ109Ym9vbChjLmNsb3NlZCkKICAgICAgICAgICAgICAgICAgICBleGNlcHQgQmFzZUV4Y2VwdGlvbjoKICAgICAgICAgICAgICAgICAgICAgICAgb3V0Wydjb25uZWN0aW9uX2Nsb3NlZCddPUZhbHNlCiAgICBleGNlcHQgQmFzZUV4Y2VwdGlvbiBhcyBleGM6CiAgICAgICAgb3V0WydzdGF0dXMnXT0nU1RPUF9JTkNPTVBMRVRFX05PX1JFVFJZJwogICAgICAgIG91dFsncmVhc29uJ109c3RyKGV4YykgaWYgaXNpbnN0YW5jZShleGMsUmVmdXNhbCkgZWxzZSAnQ09ORklHVVJBVElPTl9PUl9EQVRBQkFTRV9SRUZVU0FMJwogICAgICAgIGlmIGdldGF0dHIoZXhjLCdzcWxzdGF0ZScsTm9uZSk6IG91dFsnc3Fsc3RhdGUnXT1leGMuc3Fsc3RhdGUKICAgIGZpbmFsbHk6CiAgICAgICAgc2lnbmFsLnNldGl0aW1lcihzaWduYWwuSVRJTUVSX1JFQUwsMCkKICAgICAgICBvdXRbJ2VsYXBzZWRfbXMnXT1pbnQoKHRpbWUubW9ub3RvbmljKCktc3RhcnRlZCkqMTAwMCkKICAgICAgICBpZiBub3Qgb3V0Wydyb2xsYmFja19hY2tub3dsZWRnZWQnXSBvciBvdXRbJ2Nvbm5lY3Rpb25fY2xvc2VkJ10gaXMgbm90IFRydWU6CiAgICAgICAgICAgIG91dFsnc3RhdHVzJ109J1NUT1BfSU5DT01QTEVURV9OT19SRVRSWScKICAgICAgICBvdXRbJ2ZpbmlzaGVkX2F0J109ZGF0ZXRpbWUubm93KHRpbWV6b25lLnV0YykuaXNvZm9ybWF0KCkKICAgIHJldHVybiBvdXQKClNUQVRFTUVOVFMgPSBbJ0JFR0lOIFJFQUQgT05MWScsICJTRVQgTE9DQUwgc3RhdGVtZW50X3RpbWVvdXQgPSAnMTBzJyIsICJTRVQgTE9DQUwgbG9ja190aW1lb3V0ID0gJzNzJyIsICJTRUxFQ1Qgc2Vzc2lvbl91c2VyLCBjdXJyZW50X3VzZXIsIGN1cnJlbnRfZGF0YWJhc2UoKSxcbiBjdXJyZW50X3NldHRpbmcoJ3RyYW5zYWN0aW9uX3JlYWRfb25seScpIEFTIHJlYWRfb25seSxcbiBjdXJyZW50X3NldHRpbmcoJ3N0YXRlbWVudF90aW1lb3V0JykgQVMgc3RhdGVtZW50X3RpbWVvdXQsXG4gY3VycmVudF9zZXR0aW5nKCdsb2NrX3RpbWVvdXQnKSBBUyBsb2NrX3RpbWVvdXQsXG4gb3V0Y29tZTo6anNvbmItPidnbG9iYWxfc3RvcCcgQVMgZ2xvYmFsX3N0b3AsXG4gb3V0Y29tZTo6anNvbmItPidtYW51YWxfc3RvcCcgQVMgbWFudWFsX3N0b3AsXG4gb3V0Y29tZTo6anNvbmItPidsYXN0X2hhcmRfc3RvcCcgQVMgbGFzdF9oYXJkX3N0b3AsXG4gb3V0Y29tZTo6anNvbmItPidoYXJkX3N0b3BfZ2VuZXJhdGlvbicgQVMgZ2VuZXJhdGlvbixcbiBvdXRjb21lOjpqc29uYi0+J2ludGFrZV9ydW4nLT4+J3BlcmlvZCcgQVMgcGVyaW9kLFxuIG91dGNvbWU6Ompzb25iLT4naW50YWtlX3J1bictPj4naWQnIEFTIHJ1bl9pZCxcbiBvdXRjb21lOjpqc29uYi0+J2ludGFrZV9ydW4nLT4+J3N0YXRlJyBBUyBydW5fc3RhdGUsXG4gZW5jb2RlKHNoYTI1Nihjb252ZXJ0X3RvKG91dGNvbWU6Ompzb25iOjp0ZXh0LCdVVEY4JykpLCdoZXgnKSBBUyBjb250cm9sbGVyX3NoYVxuRlJPTSBwdWJsaWMuaW5nZXN0aW9uX3dvcmtfaXRlbXMgV0hFUkUga2V5PXJlcGVhdCgnMCcsNjQpIiwgIldJVEggY2FuZGlkYXRlcyBBUyAoXG4gU0VMRUNUIHcuKiwgY291bnQoKikgT1ZFUiAoKSBBUyB0b3RhbFxuIEZST00gcHVibGljLmluZ2VzdGlvbl93b3JrX2l0ZW1zIHdcbiBXSEVSRSB3LnN0YXRlPSdDTEFJTUVEJ1xuICAgIE9SIHcucGhhc2UgSU4gKCdTT1VSQ0VfSU5URU5UJywnV1JJVEVfSU5URU5UJylcbiAgICBPUiB3LnN0YXRlPSdQRVJTSVNURU5DRV9VTkNFUlRBSU4nXG4gT1JERVIgQlkgdy5rZXkgTElNSVQgOFxuKVxuU0VMRUNUIHcudG90YWwsdy5rZXksdy5hdXRob3JpdHksdy5yZXZpc2lvbix3LnN0YXRlLHcucGhhc2Usdy5mZW5jZSxcbiB3LmF0dGVtcHRfY291bnQsdy50YXNrLHcuY29udHJhY3Qsdy5zdWJqZWN0Ojpqc29uYixcbiB3LmNoZWNrcG9pbnQgSVMgTlVMTCBBUyBub19jaGVja3BvaW50LFxuIHcubGVhc2VfdW50aWwgPCBleHRyYWN0KGVwb2NoIEZST00gY2xvY2tfdGltZXN0YW1wKCkpIEFTIGxlYXNlX2V4cGlyZWQsXG4gKFNFTEVDVCBjb3VudCgqKSBGUk9NIHB1YmxpYy5pbmdlc3Rpb25fd29ya19hdHRlbXB0cyBhXG4gICBXSEVSRSBhLndvcmtfa2V5PXcua2V5KSBBUyBhdHRlbXB0cyxcbiAoU0VMRUNUIGNvdW50KCopIEZST00gcHVibGljLmluZ2VzdGlvbl93b3JrX2F0dGVtcHRzIGFcbiAgIFdIRVJFIGEud29ya19rZXk9dy5rZXkgQU5EIGEuZmVuY2U9MSBBTkQgYS5waGFzZT0nU09VUkNFX0lOVEVOVCdcbiAgIEFORCBhLmZpbmlzaGVkX2F0IElTIE5VTEwgQU5EIGEuY2hlY2twb2ludCBJUyBOVUxMXG4gICBBTkQgYS5hdXRob3JpdHk9dy5hdXRob3JpdHkpIEFTIGV4cGVjdGVkX3BlbmRpbmdfYXR0ZW1wdHMsXG4gZW5jb2RlKHNoYTI1Nihjb252ZXJ0X3RvKGpzb25iX2J1aWxkX29iamVjdChcbiAgJ3dvcmsnLHRvX2pzb25iKHcpLSd0b3RhbCcsXG4gICdhdHRlbXB0cycsY29hbGVzY2UoKFNFTEVDVCBqc29uYl9hZ2codG9fanNvbmIoYSkgT1JERVIgQlkgYS5mZW5jZSlcbiAgICBGUk9NIHB1YmxpYy5pbmdlc3Rpb25fd29ya19hdHRlbXB0cyBhIFdIRVJFIGEud29ya19rZXk9dy5rZXkpLFxuICAgICdbXSc6Ompzb25iKSk6OnRleHQsJ1VURjgnKSksJ2hleCcpIEFTIHdvcmtfYXR0ZW1wdF9zaGFcbkZST00gY2FuZGlkYXRlcyB3IE9SREVSIEJZIHcua2V5IiwgIlNFTEVDVCBjb3VudCgqKSBPVkVSICgpIEFTIHRvdGFsLHBpZCx1c2VuYW1lLGFwcGxpY2F0aW9uX25hbWUsXG4gYmFja2VuZF9zdGFydCx4YWN0X3N0YXJ0LHN0YXRlXG5GUk9NIHBnX3N0YXRfYWN0aXZpdHlcbldIRVJFIHBpZDw+cGdfYmFja2VuZF9waWQoKSBBTkRcbiAodXNlbmFtZSBMSUtFICdpbmdlc3Rpb25fJScgT1IgYXBwbGljYXRpb25fbmFtZT0ncHJvcGVydHlhaWdlbnRfb3duZXJfcGlsb3QnKVxuT1JERVIgQlkgcGlkIExJTUlUIDgiLCAnUk9MTEJBQ0snXQoKZGVmIHByZWZsaWdodCgpOgogICAgb3V0PXt9CiAgICByZXF1aXJlKG9zLmVudmlyb24uZ2V0KCdSRU5ERVJfU0VSVklDRV9JRCcpID09IFNFUlZJQ0UsICdTRVJWSUNFX01JU01BVENIJykKICAgIHJlcXVpcmUob3MuZW52aXJvbi5nZXQoJ1JFTkRFUl9HSVRfQ09NTUlUJykgPT0gREVQTE9ZLCAnREVQTE9ZTUVOVF9EUklGVCcpCiAgICByZXF1aXJlKGJvb2wob3MuZW52aXJvbi5nZXQoJ0RBVEFCQVNFX1VSTCcpKSwgJ0RBVEFCQVNFX0NPTkZJR1VSQVRJT05fQUJTRU5UJykKICAgIHBpbnMgPSB7CiAgICAgICd2ZXJpZmljYXRpb24vaW5nZXN0aW9uX3N0b3JhZ2Uvb3duZXJfcGlsb3QucHknOidjNTQxMjI0OWM5YzQyOTc5NDI1ZjUxOGFkNmUyODI3MjIyZTkzNmM1JywKICAgICAgJ3ZlcmlmaWNhdGlvbi9pbmdlc3Rpb25fc3RvcmFnZS9pbnRha2Vfb3duZXIucHknOidjYzQxMjczNzc5MTAyZTNmZDU3MzU5ZTk4ZTI3MTdkYjUyMTFlM2E1JywKICAgICAgJ3ZlcmlmaWNhdGlvbi9pbmdlc3Rpb25fc3RvcmFnZS90bHNfdHJ1c3QucHknOidmMDhkODY0N2EyYjc0MGZhY2FhNzYxNGQ4Y2Y3NDY2ZmMzNzljYzhhJywKICAgICAgJ3ZlcmlmaWNhdGlvbi9pbmdlc3Rpb25fc3RvcmFnZS90cnVzdC9zdXBhYmFzZS1wcm9kLWNhLTIwMjEuY3J0JzonM2Q2OTM2NjliMjNjMzQwYzU3YTM0NTdiZGM4YjZmZWZlMTgwNmNjNSd9CiAgICBmb3IgbmFtZSwgZXhwZWN0ZWQgaW4gcGlucy5pdGVtcygpOgogICAgICAgIHAgPSBQYXRoKG5hbWUpCiAgICAgICAgcmVxdWlyZShwLmlzX2ZpbGUoKSBhbmQgbm90IHAuaXNfc3ltbGluaygpLCAnU09VUkNFX09SX0NBX0FCU0VOVCcpCiAgICAgICAgcmF3ID0gcC5yZWFkX2J5dGVzKCkKICAgICAgICByZXF1aXJlKGhhc2hsaWIuc2hhMShiJ2Jsb2IgJytzdHIobGVuKHJhdykpLmVuY29kZSgpK2InXDAnK3JhdykuaGV4ZGlnZXN0KCk9PWV4cGVjdGVkLAogICAgICAgICAgICAgICAgJ1NPVVJDRV9PUl9DQV9EUklGVCcpCiAgICBzb3VyY2UgPSBQYXRoKCd2ZXJpZmljYXRpb24vaW5nZXN0aW9uX3N0b3JhZ2Uvb3duZXJfcGlsb3QucHknKS5yZWFkX3RleHQoKQogICAgbm9kZSA9IG5leHQobiBmb3IgbiBpbiBhc3QucGFyc2Uoc291cmNlKS5ib2R5IGlmIGlzaW5zdGFuY2Uobixhc3QuQ2xhc3NEZWYpIGFuZCBuLm5hbWU9PSdEYXRhYmFzZScpCiAgICByZXF1aXJlKGhhc2hsaWIuc2hhMjU2KGFzdC5nZXRfc291cmNlX3NlZ21lbnQoc291cmNlLG5vZGUpLmVuY29kZSgpKS5oZXhkaWdlc3QoKT09Q0xBU1NfU0hBLAogICAgICAgICAgICAnRlJPWkVOX0RBVEFCQVNFX0NMQVNTX0RSSUZUJykKICAgIHdpdGggcmVkaXJlY3Rfc3Rkb3V0KGlvLlN0cmluZ0lPKCkpLCByZWRpcmVjdF9zdGRlcnIoaW8uU3RyaW5nSU8oKSk6CiAgICAgICAgZnJvbSB2ZXJpZmljYXRpb24uaW5nZXN0aW9uX3N0b3JhZ2Uub3duZXJfcGlsb3QgaW1wb3J0IERhdGFiYXNlCiAgICByZXF1aXJlKFBhdGgoc3lzLm1vZHVsZXNbRGF0YWJhc2UuX19tb2R1bGVfX10uX19maWxlX18pLnJlc29sdmUoKT09CiAgICAgICAgICAgIFBhdGgoJ3ZlcmlmaWNhdGlvbi9pbmdlc3Rpb25fc3RvcmFnZS9vd25lcl9waWxvdC5weScpLnJlc29sdmUoKSwgJ0lNUE9SVF9QQVRIX0RSSUZUJykKICAgIG91dFsnZGVwbG95ZWRfcmV2aXNpb25fdmVyaWZpZWQnXSA9IERFUExPWQogICAgcmV0dXJuIERhdGFiYXNlCgpkZWYgbWFpbigpOgogICAgc3RhcnRlZD1nbG9iYWxzKCkuZ2V0KCd0cmFuc3BvcnRfc3RhcnRlZCcsdGltZS5tb25vdG9uaWMoKSkKICAgIHRyeToKICAgICAgICBmYWN0b3J5PXByZWZsaWdodCgpCiAgICBleGNlcHQgQmFzZUV4Y2VwdGlvbjoKICAgICAgICBwcmludCgneyJzdGF0dXMiOiJQUkVGTElHSFRfUkVGVVNFRF9OT19SRVRSWSIsImNvbm5lY3Rpb25zX2F0dGVtcHRlZCI6MH0nLGZsdXNoPVRydWUpCiAgICAgICAgcmV0dXJuCiAgICByZXN1bHQ9cnVuKGZhY3Rvcnksc3RhcnRlZCkKICAgIHByaW50KGpzb24uZHVtcHMocmVzdWx0LHNvcnRfa2V5cz1UcnVlLHNlcGFyYXRvcnM9KCcsJywnOicpKSxmbHVzaD1UcnVlKQoKaWYgX19uYW1lX189PSdfX21haW5fXyc6CiAgICBtYWluKCkK'
if __name__=='__main__': main()
