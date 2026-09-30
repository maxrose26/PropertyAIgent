"""Runs as the ordinary user inside the private OS namespaces."""
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from verification.ah_pg.cluster import initial_proof

root=Path(sys.argv[1]); host_ns=sys.argv[2]; pg=Path(sys.argv[3]); out=Path(sys.argv[4]); repo=Path.cwd()
def call(args,log,timeout=1200):
    with (out/log).open('w') as f:
        return subprocess.run(list(map(str,args)),stdout=f,stderr=subprocess.STDOUT,timeout=timeout).returncode
if os.getuid()==0 or set(os.listdir('/sys/class/net'))!={'lo'} or os.readlink('/proc/self/ns/net')==host_ns:
    raise SystemExit('Isolation mismatch; no initdb permitted')
# Complete dependency imports AND native test collection before creating a cluster.
if call([sys.executable,'verification/ah_pg/preflight.py',out/'dependencies.json'],'preflight.log'): raise SystemExit(1)
if call([sys.executable,'-m','pytest','--collect-only','-q','-p','no:cacheprovider','verification/revisit_pg/test_native.py'],'native-collected.txt'): raise SystemExit(1)
if call([pg/'initdb','-D',root/'pgdata','-U','ah_cluster_owner','--encoding=UTF8','--locale=C','--auth-local=reject','--auth-host=trust'],'initdb.log'): raise SystemExit(1)
options="-h 127.0.0.1 -p 55439 -c unix_socket_directories='' -c max_connections=30"
try:
    if call([pg/'pg_ctl','-D',root/'pgdata','-l',out/'postgres.log','-o',options,'-w','start'],'start.log'): raise SystemExit(1)
    m=initial_proof(root,host_ns,pg)
    (out/'cluster-identity.json').write_text(json.dumps(m,indent=2)+'\n')
    os.environ['AH_DISPOSABLE_ROOT']=str(root)
    rc=call([sys.executable,'-m','pytest','-q','-p','no:cacheprovider','verification/revisit_pg/test_native.py','--junitxml='+str(out/'native.xml')],'native.log')
    (out/'native-exit.txt').write_text(str(rc)+'\n')
    cases=list(ET.parse(out/'native.xml').iter('testcase')) if (out/'native.xml').exists() else []
    bad=[c.get('classname','')+'::'+c.get('name','') for c in cases if any(c.find(x) is not None for x in ('failure','error','skipped'))]
    (out/'native-summary.json').write_text(json.dumps({'exit':rc,'collected':len(cases),'failures_or_skips':bad,'archive_inspection_required':True},indent=2)+'\n')
    if rc or len(cases)!=20 or bad: raise SystemExit(1)
finally:
    if call([pg/'pg_ctl','-D',root/'pgdata','-m','immediate','-w','stop'],'stop.log',timeout=60):
        raise SystemExit('Disposable cluster shutdown failed')
