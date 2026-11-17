import importlib.util,json,os,socket,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('launcher',BASE/'bolton-receipt-launcher.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
spec2=importlib.util.spec_from_file_location('old_checks',BASE/'test_bolton_read.py')
old=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(old)
class Integrated(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'pa-tam001-v1-4-offline-01'
  self.binding=m.identity(self.root.name);self.host=patch.object(m,'INSTANCE',socket.gethostname());self.host.start()
  self.started=time.monotonic()
 def tearDown(self):self.host.stop();self.tmp.cleanup()
 def accepted(self):
  with patch.object(m.subprocess,'Popen') as spawn:
   m.start(self.root,self.binding,self.started)
   self.assertEqual(spawn.call_count,1)
   args=spawn.call_args.args[0]
   self.assertIn('--kill-after=1s',args)
   self.assertLessEqual(float(args[3][:-1]),18.5)
   self.assertTrue(spawn.call_args.kwargs['start_new_session'])
 def complete(self,c=None):
  self.accepted();self.c=c or old.Connection();d=old.DB(self.c)
  core=m.load_core();core['preflight']=lambda:lambda:d
  m.worker(self.root,self.binding,self.started,core)
  self.assertEqual(d.opens,1);self.assertLessEqual(len(self.c.calls),7)
  return m.readback(self.root,self.binding)
 def test_exact_core_and_success(self):
  import base64
  self.assertEqual(base64.b64decode(m.CORE),(BASE/'bolton-read.py').read_bytes())
  r=self.complete();self.assertEqual(r['verification'],'RECEIPT_INTEGRITY_VERIFIED_NOT_BOLTON_MATCH')
  self.assertEqual(r['completion']['result']['statements_completed'],7)
  self.assertEqual(r['completion']['result']['execution_id'],self.binding['invocation_id'])
  self.assertTrue(r['completion']['result']['rollback_acknowledged'])
  self.assertTrue(r['completion']['result']['connection_closed'])
 def test_duplicate_start_and_worker(self):
  self.complete();before=(self.root/'completion.json').read_bytes()
  with patch.object(m.subprocess,'Popen') as spawn:
   with self.assertRaises(FileExistsError):m.start(self.root,self.binding,time.monotonic())
   spawn.assert_not_called()
  with self.assertRaises(FileExistsError):m.worker(self.root,self.binding,self.started)
  self.assertEqual(before,(self.root/'completion.json').read_bytes())
 def test_missing_ack_and_completion(self):
  self.assertEqual(m.readback(self.root,self.binding)['verification'],'UNKNOWN_STOP_NO_RETRY')
  self.accepted();self.assertEqual(m.readback(self.root,self.binding)['verification'],'UNKNOWN_STOP_NO_RETRY')
 def test_tamper_malformed_and_oversize(self):
  self.complete();p=self.root/'completion.json';original=p.read_bytes();v=json.loads(original)
  for change in ({'invocation_id':'wrong'},{'launcher_sha256':'bad'},{'ack_sha256':'bad'},{'result':[]},{'overall_elapsed_ms':20000},{'overall_elapsed_ms':-1}):
   p.write_bytes(m.encoded(dict(v,**change)))
   self.assertEqual(m.readback(self.root,self.binding)['verification'],'UNKNOWN_STOP_NO_RETRY')
  for raw in (b'{',b'x'*(m.MAX_RECEIPT+1)):
   p.write_bytes(raw);self.assertEqual(m.readback(self.root,self.binding)['verification'],'UNKNOWN_STOP_NO_RETRY')
 def test_instance_replacement(self):
  self.complete();self.assertEqual(m.readback(self.root,dict(self.binding,instance='replacement'))['verification'],'UNKNOWN_STOP_NO_RETRY')
 def test_cleanup_separate(self):
  r=self.complete(old.Connection(ack=False))['completion']['result']
  self.assertFalse(r['rollback_acknowledged']);self.assertTrue(r['connection_closed'])
 def test_close_unknown(self):
  r=self.complete(old.Connection(close_error=True))['completion']['result']
  self.assertTrue(r['rollback_acknowledged']);self.assertFalse(r['connection_closed'])
 def test_real_preflight_timeout(self):
  self.started=time.monotonic()-14;self.root.mkdir()
  m.save(self.root/'ack.json',dict(self.binding,kind='INVOCATION_ACCEPTED_PRE_DATABASE',started_monotonic=self.started))
  t=time.monotonic();m.worker(self.root,self.binding,self.started,{'preflight':lambda:time.sleep(30)})
  self.assertLess(time.monotonic()-t,2)
  r=m.readback(self.root,self.binding)['completion']['result']
  self.assertEqual(r['connections_attempted'],0);self.assertIsNone(r['connection_closed'])
 def test_process_death_leaves_unknown(self):
  self.accepted()
  code=f'import importlib.util,time; from pathlib import Path; s=importlib.util.spec_from_file_location("m",{str(BASE.resolve()/"bolton-receipt-launcher.py")!r}); m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.worker(Path({str(self.root)!r}),{self.binding!r},{self.started!r},{{"preflight":lambda:None,"run":lambda *_:__import__("os")._exit(17)}})'
  p=subprocess.run([sys.executable,'-B','-c',code],env={},capture_output=True,timeout=3)
  self.assertEqual(p.returncode,17)
  self.assertEqual(m.readback(self.root,self.binding)['verification'],'UNKNOWN_STOP_NO_RETRY')
 def test_hard_timeout_survives_ignored_term(self):
  p=subprocess.run(['timeout','--signal=TERM','--kill-after=0.2s','0.2s',sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(30)'],capture_output=True,timeout=2)
  self.assertEqual(p.returncode,-9)
 def test_detached_cli_receipt_readback(self):
  import base64,hashlib,uuid,shutil
  fixture=b"def preflight(): return None\ndef run(factory, started): return {'status':'OFFLINE_TRANSPORT_FIXTURE','connections_attempted':0,'rollback_acknowledged':None,'connection_closed':None}\n"
  source=(BASE/'bolton-receipt-launcher.py').read_text()
  source=source.replace(m.CORE,base64.b64encode(fixture).decode()).replace(m.CORE_SHA,hashlib.sha256(fixture).hexdigest()).replace("srv-d9qbl7qjnfac73d8nieg-8684bcc77c-xgxgz",socket.gethostname())
  script=Path(self.tmp.name)/'offline-launcher.py';script.write_text(source)
  invocation='pa-tam001-v1-4-test-'+uuid.uuid4().hex
  root=Path('/tmp')/invocation
  try:
   p=subprocess.run([sys.executable,str(script),'start',invocation,str(time.monotonic())],env={},capture_output=True,text=True,timeout=3)
   self.assertEqual(p.returncode,0,p.stderr)
   ack=json.loads(p.stdout);self.assertEqual(ack['kind'],'INVOCATION_ACCEPTED_PRE_DATABASE')
   limit=time.monotonic()+3
   while not (root/'completion.json').exists() and time.monotonic()<limit:time.sleep(.05)
   r=subprocess.run([sys.executable,str(script),'read',invocation],env={},capture_output=True,text=True,timeout=3)
   receipt=json.loads(r.stdout)
   self.assertEqual(receipt['verification'],'RECEIPT_INTEGRITY_VERIFIED_NOT_BOLTON_MATCH')
   self.assertEqual(receipt['completion']['result']['status'],'OFFLINE_TRANSPORT_FIXTURE')
   self.assertEqual(receipt['completion']['result']['connections_attempted'],0)
  finally:
   if root.exists():shutil.rmtree(root)
if __name__=='__main__':unittest.main(verbosity=2)
