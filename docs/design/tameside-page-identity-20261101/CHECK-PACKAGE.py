"""Local package/checkout checks only. No connection or execution authority."""
import hashlib
import importlib.util
import importlib.metadata
import json
from pathlib import Path
import subprocess

p=Path(__file__).resolve().parent
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
listed={}
for line in (p/'SHA256SUMS').read_text().splitlines():
    h,n=line.split('  ',1)
    f=p/n
    assert not Path(n).is_absolute() and '..' not in Path(n).parts and not f.is_symlink(), 'PACKAGE_PATH'
    assert f.is_file() and sha(f)==h, 'PACKAGE_HASH:'+n
    listed[n]=h
actual={str(f.relative_to(p)) for f in p.rglob('*') if f.is_file() and f.name!='SHA256SUMS'}
assert actual==set(listed), 'UNBOUND_PACKAGE_FILE'
b=json.loads((p/'BINDINGS.json').read_text());repo=Path(b['checkout_path'])
assert subprocess.check_output(['/usr/bin/git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==b['owner_commit'], 'CHECKOUT_COMMIT'
assert subprocess.check_output(['/usr/bin/git','-C',str(repo),'rev-parse','HEAD^{tree}'],text=True).strip()==b['owner_tree'], 'CHECKOUT_TREE'
assert subprocess.check_output(['/usr/bin/git','-C',str(repo),'status','--porcelain'],text=True)=='', 'CHECKOUT_DIRTY'
for n,h in {**b['runtime_files'],**b['preparation_files']}.items():
    assert not (repo/n).is_symlink() and sha(repo/n)==h, 'CHECKOUT_FILE_HASH:'+n
assert sha(Path(b['interpreter']))==b['interpreter_sha256'], 'INTERPRETER_HASH'
for name, h in b['original_evidence'].items():
    f=Path(name)
    assert not f.is_symlink() and f.is_file() and sha(f)==h, 'ORIGINAL_EVIDENCE_CHANGED'
for name, version in b['dependency_versions'].items():
    assert importlib.metadata.version(name)==version, 'DEPENDENCY_VERSION_CHANGED:'+name
assert all(importlib.util.find_spec(n) is not None for n in ('psycopg','sqlalchemy','cryptography','requests','playwright')), 'EXISTING_DEPENDENCY_MISSING'
print(json.dumps(dict(status='LOCAL_PACKAGE_CHECKS_PASS',files=len(listed),production_connections=0,
                     source_requests=0,provider_calls=0,owner_commit=b['owner_commit']),sort_keys=True))
