"""Owned process/profile/output cleanup after real local failure injections."""
import json,os,signal,subprocess,sys,tempfile,time,shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.security import document_process as dp
if sys.argv[1]=='child':
 from playwright.sync_api import sync_playwright
 from app.security.document_browser import DocumentRenderer
 import requests
 root=Path(sys.argv[2]);mode=sys.argv[3];report=None;status=None;receipt=None
 fd_baseline=len(list(Path('/proc/self/fd').iterdir()))
 os.environ['PROPERTYAIGENT_DOCUMENT_CHROMIUM']=sys.argv[4]
 if mode=='deadline':dp.LIFETIME_LIMIT=8 # Shorter fixture deadline, never a larger application limit.
 try:
  with tempfile.TemporaryDirectory(prefix='propertyaigent-document-',dir=root) as directory:
   job=Path(directory)
   try:
    with sync_playwright() as pw:
     with dp.protected_browser(pw.chromium,job,remove_on_parent_loss=True) as (browser,status):
      context=browser.new_context(offline=True);page=context.new_page();page.set_content('<p>fixture</p>')
      if mode in ('parent','parent_after_close','parent_after_ack','deadline'):
       target=root/'existing.pdf';target.write_bytes(b'original')
       renderer=DocumentRenderer(context,requests.Session(),job)
       artifact=job/'verified.pdf';artifact.write_bytes(b'verified-pending-output')
       renderer.artifacts['fixture']=artifact;renderer.save_download(SimpleNamespace(url='fixture'),target)
       if mode!='parent_after_ack':Path(renderer.output_journal[0]['partial']).write_bytes(b'partial-copy')
      ready=status();ready['job_directory']=str(job);ready['custodian']=json.loads((job/'process/custodian-ready.json').read_text())
      if mode not in ('parent_after_close','parent_after_ack'):(root/'ready.json').write_text(json.dumps(ready))
      if mode=='crash':os.kill(int(status()['group']),signal.SIGKILL)
      elif mode=='guardian':os.kill(int(status()['guardian']),signal.SIGKILL)
      elif mode=='custodian':os.kill(ready['custodian']['pid'],signal.SIGKILL)
      elif mode=='cancel':raise KeyboardInterrupt('synthetic cancellation')
      elif mode=='stale':
       value=status();value['job']='0'*32;original_read=Path.read_bytes
       def stale_read(path):
        return json.dumps(value).encode() if path==job/'process/status.json' else original_read(path)
       with patch.object(Path,'read_bytes',stale_read):status()
      elif mode in ('normal','parent_after_close','parent_after_ack'):context.close()
      if mode not in ('normal','cancel','parent_after_close','parent_after_ack'):page.wait_for_timeout(10000)
     if mode=='parent_after_ack':status.finish_files(True)
     if mode in ('parent_after_close','parent_after_ack'):
      (root/'ready.json').write_text(json.dumps(ready));time.sleep(10)
     status.finish_files(True)
   except BaseException:
    if status is not None:status.finish_files(False)
    raise
   finally:
    if (job/'process/status.json').exists():report=json.loads((job/'process/status.json').read_text())
 except BaseException as exc:
  if status is not None:
   try:receipt=status.wait_custodian()
   except BaseException as owner_error:receipt={'error':type(owner_error).__name__}
  fd_final=len(list(Path('/proc/self/fd').iterdir()))
  (root/'child-result.json').write_text(json.dumps(dict(error=type(exc).__name__,message=str(exc)[:300],process_report=report,custodian_receipt=receipt,fd_baseline=fd_baseline,fd_final=fd_final)))
  sys.exit(2)
 if status is not None:receipt=status.wait_custodian()
 fd_final=len(list(Path('/proc/self/fd').iterdir()))
 (root/'child-result.json').write_text(json.dumps(dict(error=None,process_report=report,custodian_receipt=receipt,fd_baseline=fd_baseline,fd_final=fd_final)))
 sys.exit(0)
OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True);CHROME=sys.argv[2];records=[]
try:
 for mode in ('normal','cancel','crash','guardian','parent','stale','parent_after_close','parent_after_ack','custodian','deadline'):
  root=Path(tempfile.mkdtemp(prefix='propertyaigent-cleanup-fixture-'));evidence=OUT/mode;evidence.mkdir()
  with (root/'child.log').open('w') as log:
   child=subprocess.Popen([sys.executable,__file__,'child',str(root),mode,CHROME],env={'PATH':'/usr/bin:/bin','HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1'},stdout=log,stderr=log)
   end=time.monotonic()+35
   while not (root/'ready.json').exists() and child.poll() is None and time.monotonic()<end:time.sleep(.05)
   assert (root/'ready.json').exists(),f'{mode}: renderer did not start'
   ready=json.loads((root/'ready.json').read_text());job=Path(ready['job_directory'])
   if mode.startswith('parent'):child.kill()
   code=child.wait(timeout=15)
   end=time.monotonic()+8;alive=True;owner_alive=True
   while time.monotonic()<end:
    try:os.killpg(ready['group'],0)
    except ProcessLookupError:alive=False
    try:os.kill(ready['custodian']['pid'],0)
    except ProcessLookupError:owner_alive=False
    if not alive and not owner_alive and not job.exists():break
    time.sleep(.05)
   result=json.loads((root/'child-result.json').read_text()) if (root/'child-result.json').exists() else None
   records.append(dict(mode=mode,exit_code=code,group_alive=alive,custodian_alive=owner_alive,job_directory_exists=job.exists(),child_result=result,fixture_root=str(root)));print(records[-1],flush=True)
   # Export only after observation; mutable fixtures use the actual runtime /tmp.
   for name in ('ready.json','child-result.json','child.log'):
    if (root/name).exists():shutil.copyfile(root/name,evidence/name)
   (evidence/'remaining-files.json').write_text(json.dumps([str(p.relative_to(root)) for p in root.rglob('*')]))
   if result is not None:assert result['fd_final']==result['fd_baseline'],f'{mode}: descriptor leak'
   assert not alive,f'{mode}: renderer process group survives'
   assert not owner_alive,f'{mode}: file custodian survives'
   assert not job.exists(),f'{mode}: profile/document temporary files survive'
   assert not list(root.glob('.document-*')),f'{mode}: partial output survives'
   if mode in ('parent','parent_after_close','deadline'):assert (root/'existing.pdf').read_bytes()==b'original','Parent death must roll back pending output'
   if mode=='parent_after_ack':assert (root/'existing.pdf').read_bytes()==b'verified-pending-output','Acknowledged outputs must persist'
   if mode=='normal':assert code==0 and result['process_report']['closed'] and not result['process_report']['failure']
   elif mode!='parent':assert code!=0
   # Durable absence observation stays within the existing eight-second check bound.
   if mode=='deadline':
    while time.monotonic()<end:
     assert not job.exists() and not list(root.glob('.document-*')),'Deadline cleanup was recreated'
     time.sleep(.05)
   shutil.rmtree(root) # Harness-only files, after all owned-resource absence assertions.
finally:(OUT/'result.json').write_text(json.dumps(dict(records=records),indent=2))
print('DONE cleanup')
