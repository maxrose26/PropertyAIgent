"""Injected bootstrap failures in this isolated test process, no app bypass flags."""
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.security import document_process as dp
OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True);records=[]
for failure in ('setpgid','status-save'):
 with tempfile.TemporaryDirectory() as directory:
  root=Path(directory);parent=dp.proc_info(dp.own_host_pid());config=root/'config.json'
  config.write_text(json.dumps(dict(version=1,job='1'*32,executable='/bin/true',parent_host=parent['host_pid'],parent_start=parent['start'])))
  before=len(list(Path('/proc/self/fd').iterdir()))
  original=Path.write_text
  def fail_group(*_):raise RuntimeError('synthetic process-group bootstrap failure')
  def fail_save(path,*args,**kwargs):
   if path.name=='status.next':raise OSError('synthetic status-save failure')
   return original(path,*args,**kwargs)
  with patch.object(dp,'audit_pipes',lambda:None):
   try:
    if failure=='setpgid':
     with patch.object(dp.os,'setpgid',fail_group):dp.guardian(str(config),['--remote-debugging-pipe'])
    else:
     with patch.object(Path,'write_text',fail_save):dp.guardian(str(config),['--remote-debugging-pipe'])
   except (RuntimeError,OSError):pass
   else:raise AssertionError('Bootstrap failure suppressed')
  after=len(list(Path('/proc/self/fd').iterdir()))
  try:child=os.waitpid(-1,os.WNOHANG)
  except ChildProcessError:child=None
  records.append(dict(failure=failure,fd_before=before,fd_after=after,remaining_child=child))
  assert child is None and before==after
(OUT/'result.json').write_text(json.dumps(records,indent=2));print('DONE bootstrap',records)
