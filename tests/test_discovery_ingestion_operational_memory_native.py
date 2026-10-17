"""Native dedicated-scope probe; run as a standalone module in CI only."""
import json,subprocess,sys,tempfile
from pathlib import Path
from verification.ingestion_storage.operational_memory import OperationalMemory
from verification.ingestion_storage.operational_supervisor import supervise

def main():
    memory=OperationalMemory()
    version=subprocess.run(['gh','--version'],capture_output=True,timeout=5)
    assert version.returncode==0 and version.stdout.startswith(b'gh version ')
    if sys.argv[1]=='excess':
        subprocess.run([sys.executable,'-c','a=bytearray(400*1024**2); print(len(a))'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        raise AssertionError('KERNEL_CEILING_DID_NOT_TERMINATE_GROUP')
    # Exercise the real credential-free source preexec placement. No network,
    # database or GitHub credentials are supplied to this harmless child.
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)/'source-probe'
        code="""import json,os,time
from pathlib import Path
p=Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip()[3:].lstrip('/')
assert p.name=='source' and p.parent.name=='propertyaigent-operational-once.scope'
assert (p/'memory.max').read_text().strip()==str(1024**3)
assert not any('TOKEN' in k or 'PASSWORD' in k or 'DATABASE' in k for k in os.environ)
Path(os.environ['HOME'],'placement.json').write_text(json.dumps({'path':str(p),'memory_max':int((p/'memory.max').read_text())}))
time.sleep(.2)
"""
        source=supervise([sys.executable,'-I','-B','-c',code],environment={},root=root,seconds=5,source=True,memory_group=memory.source)
        assert source['exit_code']==0 and source['cleanup']=='CLOSED' and source['accounting_complete'] and not source['limit_hit']
        placement=json.loads((root/'placement.json').read_text())
        assert placement['path']==str(memory.source) and placement['memory_max']==1024**3
    result=memory.close()
    result['credential_free_source_placement_verified']=True
    assert result['owned_survivors']==0 and result['owned_groups_removed']
    assert result['memory']['controller']['peak_bytes']<=256*1024**2
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()
