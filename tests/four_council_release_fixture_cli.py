"""Standalone whole-wrapper rehearsal. Synthetic sources/API; optional real kernel.

No production registration, account, SQL, council route or external API is used.
Native mode is admitted only by the existing dedicated memory scope in offline CI.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from verification.discovery import four_council_release as r
from verification.ingestion_storage.operational_publication import GitHub, canonical
from tests.test_discovery_four_council_release import API, Memory, audit, registration
from tests.test_discovery_three_council_isolation import local_audit, registration as successor_registration


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--native',action='store_true');p.add_argument('--successor',action='store_true');p.add_argument('--fault',choices=['none','unknown','cancel','cancel-startup','unavailable','local-all','local-0','local-1','local-2'],default='none');p.add_argument('--worker',type=int);p.add_argument('--browser-fixture',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
    def source_value(index):
        if a.successor and a.fault in ('local-all',f'local-{index-1}'):
            return local_audit(index,'selector' if index==3 else 'sort')
        return audit(index,complete=not(a.fault=='unknown' and index==(1 if a.successor else 0)))
    if a.worker is not None:
        if a.native and not a.browser_fixture:r.owner_source_context()
        if a.fault in ('cancel','cancel-startup'):
            nested=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],start_new_session=True)
            (a.root/'nested.json').write_text(json.dumps(dict(pid=nested.pid)))
            time.sleep(30)
        if a.native and a.worker==1 and not a.browser_fixture:
            from verification.direct_reference import instrumented_probe as probe
            original_popen=subprocess.Popen
            def fixture_browser(command,**kwargs):
                assert command[2]=='verification.direct_reference.instrumented_probe'
                output=command[command.index('--output')+1]
                replacement=[sys.executable,'-m','tests.four_council_release_fixture_cli','--root',str(a.root),'--worker','1','--output',output,'--browser-fixture']
                if a.successor:replacement+=['--successor','--fault',a.fault]
                return original_popen(replacement,**kwargs)
            with patch.object(probe.subprocess,'Popen',fixture_browser):
                probe.supervised('discovery_rochdale_ui_window',a.output,execution_mode='four-council-owner-local',window=('2026-10-08','2026-10-14'),retain_proof=True)
            return 0
        value=source_value(a.worker)
        r.write_new(a.output,canonical(value));return 0
    a.root.mkdir(parents=True,exist_ok=True)
    reg=(successor_registration() if a.successor else registration());reg.update(revision=r.git('rev-parse','HEAD'),tree=r.git('rev-parse','HEAD^{tree}'))
    api=API(reg);original=api.runner;head_reads=[0]
    def transport(command,**kwargs):
        if command[3]=='GET' and '/git/ref/' in command[4]:
            head_reads[0]+=1
            if a.fault=='cancel-startup' and head_reads[0]>=5:api.ref_moved=True
            if a.fault=='cancel' and (a.root/'nested.json').exists():api.ref_moved=True
        if a.fault=='unavailable' and '/contents/' in command[4]:raise TimeoutError('synthetic unavailable control')
        return original(command,**kwargs)
    original_source=r.Source;original_memory=r.OperationalMemory
    class FixtureSource(original_source):
        def command(self,index,out):
            return [sys.executable,'-m','tests.four_council_release_fixture_cli','--root',str(a.root),'--worker',str(index),'--output',str(out),'--fault',a.fault]+(['--native'] if a.native else [])+(['--successor'] if a.successor else [])
    class SyntheticSource:
        # Contract simulation for hosts with mismatched /proc. The native mode
        # below runs real Popen/preexec/cgroup cancellation, not this substitute.
        def __init__(self,memory,registration,root):self.root=root
        def run(self,index,check):
            check();return source_value(index),dict(source_group_closed=True,supervised_seconds=.01)
    os.environ['HOME']=str(a.root)
    for key in list(os.environ):
        if any(k in key.upper() for k in ('DATABASE','SUPABASE','OPENAI','ANTHROPIC')):os.environ.pop(key)
    reg_path=a.root/'registration.json';reg_path.write_bytes(canonical(reg))
    original_validate=r.validate
    original_read=Path.read_text
    def read(path,*args,**kwargs):
        value=original_read(path,*args,**kwargs)
        if str(path)=='/proc/self/stat' and not a.native:return str(os.getpid())+' '+value.split(' ',1)[1]
        return value
    def memory():return original_memory() if a.native else Memory(a.root)
    def github(emit,check,**kwargs):return GitHub(emit,check,runner=transport,**kwargs)
    with patch.object(r,'Source',FixtureSource if a.native else SyntheticSource),patch.object(r,'OperationalMemory',memory),patch.object(r,'GitHub',github),patch.object(r,'validate',lambda value:original_validate(value,checkout=a.native)),patch.object(Path,'read_text',read):
        fake_process=type('Process',(),{'children':lambda self,recursive:[]})()
        context=patch('psutil.Process',lambda:fake_process) if not a.native else __import__('contextlib').nullcontext()
        with context,patch.object(sys,'argv',['fixed-release','run','--registration',str(reg_path),'--registration-sha256',r.sha(reg_path.read_bytes()),'--enable-reviewed-source-only-stop-treatment']):
            code=r.main()
    final=a.root/'.local/state/propertyaigent'/reg['release_id']/'final-result.json'
    value=json.loads(final.read_bytes())
    assert value['database_connections']==value['application_writes']==0
    assert code==(0 if a.fault=='none' else 1)
    if a.fault=='none':assert len(value['results'])==(3 if a.successor else 4) and value['cleanup']=='CLOSED'
    if a.fault=='unknown':assert len(value['results'])==1 and len(value['not_attempted'])==(2 if a.successor else 3)
    if a.fault.startswith('local-'):
        assert a.successor and len(value['results'])==3 and not value['not_attempted']
        assert value['status']=='OBSERVATIONS_FINISHED_WITH_GAPS' and value['accounting_complete']
        assert value['cleanup']=='CLOSED' and value['final_publication']=='VERIFIED'
    if a.native:assert value['owned_cleanup']['owned_groups_removed'] and value['process_cleanup']=='CLOSED'
    (a.root/'rehearsal.json').write_bytes(canonical(value))
    print(json.dumps(dict(rehearsal='NATIVE_CGROUP_FIXTURE' if a.native else 'CONTRACT_SIMULATION',fault=a.fault,verified=True)))
    return 0

if __name__=='__main__':sys.exit(main())
