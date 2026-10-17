"""Native dedicated-scope probe; run as a standalone module in CI only."""
import json,subprocess,sys
from verification.ingestion_storage.operational_memory import OperationalMemory

def main():
    memory=OperationalMemory()
    version=subprocess.run(['gh','--version'],capture_output=True,timeout=5)
    assert version.returncode==0 and version.stdout.startswith(b'gh version ')
    if sys.argv[1]=='excess':
        subprocess.run([sys.executable,'-c','a=bytearray(400*1024**2); print(len(a))'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        raise AssertionError('KERNEL_CEILING_DID_NOT_TERMINATE_GROUP')
    result=memory.close()
    assert result['owned_survivors']==0 and result['owned_groups_removed']
    assert result['memory']['controller']['peak_bytes']<=256*1024**2
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()
