"""Standalone kernel OOM probe, no credentials or network."""
import subprocess,sys
from verification.ingestion_storage.operational_cleanup import Memory

if __name__=='__main__':
    memory=Memory()
    assert subprocess.run(['gh','--version'],capture_output=True,timeout=3).returncode==0
    subprocess.run([sys.executable,'-I','-B','-c','x=bytearray(400*1024**2)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
    raise AssertionError('KERNEL_MEMORY_CEILING_DID_NOT_KILL_SCOPE')
