"""Actual normal Manchester worker inside its outer supervisor, loopback only."""
import hashlib,json,os,subprocess,sys,tempfile,threading,time
from pathlib import Path
import pytest

@pytest.mark.skipif(os.environ.get('MANCHESTER_REAL_BROWSER')!='1',reason='hosted isolated Chromium only')
@pytest.mark.parametrize('inherited_temp',[False,True,'full'])
def test_worker_browser_inside_reviewed_supervisor(tmp_path,inherited_temp):
 from verification.ingestion_storage.operational_supervisor import supervise
 from verification.ingestion_storage.owner_pilot import source_profile
 from verification.direct_reference.prepared_font_cache import headless_shell_executable
 browser=os.environ['PLAYWRIGHT_BROWSERS_PATH'];sha=hashlib.sha256(Path(headless_shell_executable(browser)).read_bytes()).hexdigest()
 revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
 profile=source_profile(dict(browser_path=browser,browser_sha256=sha,execution_binding=dict(revision=revision),browser_canary="LAUNCHED_AND_CLOSED"),revision)
 receipt=tmp_path/'browser-receipt.json'
 # No real provider/source transport: the existing representative fixture starts
 # a loopback TLS server, routes Chromium exclusively to it, then invokes the real
 # source_worker with its exact normal 2 MiB per-file profile.
 env=dict(MANCHESTER_REAL_BROWSER='1',MEASURE_FILE_LIMIT='2097152',MEASURE_ACTUAL_WORKER='1',P09_BOUNDARY_RECEIPT=str(receipt))
 if inherited_temp:env['MEASURE_INHERITED_TEMP']='1'
 if inherited_temp=='full':env['MEASURE_FULL_PATH']='1'
 command=[sys.executable,'-c','import os,pytest;os.environ.update('+repr(env)+');raise SystemExit(pytest.main(["tests/test_manchester_file_measurement.py","-q","-s","--tb=short"]))']
 # Match production TMPDIR path length, without touching its real path.
 owned=Path(tempfile.mkdtemp(prefix='p09-fixture-'))/('x'*42)/'manchester-owned' if inherited_temp else tmp_path/'owned'
 owned.parent.mkdir(parents=True,exist_ok=True)
 observations=dict(max_entries=0,max_regular_bytes=0,symlinks_seen=False)
 stopped=threading.Event()
 def observe():
  while not stopped.wait(.002):
   paths=list(owned.rglob('*'))
   observations['max_entries']=max(observations['max_entries'],len(paths))
   observations['symlinks_seen'] |= any(p.is_symlink() for p in paths)
   sizes=[]
   for p in paths:
    try:
     if p.is_file() and not p.is_symlink():sizes.append(p.stat().st_size)
    except OSError:pass
   observations['max_regular_bytes']=max(observations['max_regular_bytes'],sum(sizes))
 observer=threading.Thread(target=observe,daemon=True);observer.start()
 try:outer=supervise(command,environment=dict(INGESTION_SOURCE_PRIVATE='ONCE',PLAYWRIGHT_BROWSERS_PATH=browser,INGESTION_RENDER_PROFILE=json.dumps(profile)),root=owned,source=True,seconds=75,execution_budget='BROWSER_SOURCE_V2',render_profile=profile)
 finally:stopped.set();observer.join()
 print('P09_BROWSER_BOUNDARY '+json.dumps(dict(outer=outer,inherited_temp=inherited_temp,observations=observations),sort_keys=True))
 if inherited_temp=='full':
  print('P09_FULL_READER '+(receipt.read_text() if receipt.exists() else '{}'))
  inner=Path(str(receipt)+'.inner')
  print('P09_INNER_WORKER '+(inner.read_text() if inner.exists() else '{}'))
  assert outer['cleanup']=='CLOSED' and outer['live_owned_survivors']==0,outer
  # Observation-only baseline: do not equate a failure with collector success.
  assert outer['limit_hit'] in (None,'OUTPUT_BOUND','ACCOUNTING_UNCERTAIN','OUTPUT_ACCOUNTING'),outer
  return
 assert outer['cleanup']=='CLOSED' and outer['live_owned_survivors']==0,outer
 assert outer['exit_code']==0 and outer['limit_hit'] is None,outer
 report=json.loads(receipt.read_text());assert report['actual_worker'] and report['records']==60 and report['enumeration']=='COUNT_RECONCILED'
 assert report['physical_requests']==1 and report['cleanup']=='CONTEXT_BROWSER_CLOSED'
