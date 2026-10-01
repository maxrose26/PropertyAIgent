"""Fail-closed offline comparison of native PostgreSQL catalogue exports.

No connection, DSN, environment-file loading, migration or production override.
An expected native catalogue must be independently generated from the reviewed
DDL in a clean disposable database, not learned from the candidate under test.
"""
import hashlib
import json
from pathlib import Path

SECTIONS = ('relations','columns','constraints','indexes','sequences',
            'sequence_dependencies','triggers','functions','policies','acl',
            'default_acl','roles','memberships')

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def compare(expected_schema, actual, reference):
    errors=[]
    contract=expected_schema.get('_native_verifier',{})
    required=('reference_sha256','migration_sha256','server_version_num','role_names')
    if any(not contract.get(k) for k in required):
        return {'status':'BLOCKED','differences':['Native reference contract not established'], 'native_execution_proven':False}
    schema_payload={k:v for k,v in expected_schema.items() if not k.startswith('_')}
    if reference.get('expected_ddl_sha256') != digest(schema_payload): errors.append('reference.expected_ddl_sha256')
    if digest(reference) != contract['reference_sha256']: errors.append('reference.sha256')
    if reference.get('migration_sha256') != contract['migration_sha256']: errors.append('reference.migration_sha256')
    for label,snapshot in (('reference',reference),('actual',actual)):
        if snapshot.get('migration_sha256') != contract['migration_sha256']: errors.append(label+'.migration_sha256')
        if snapshot.get('expected_ddl_sha256') != digest(schema_payload): errors.append(label+'.expected_ddl_sha256')
        if snapshot.get('server_version_num') != contract['server_version_num']: errors.append(label+'.server_version_num')
        if snapshot.get('role_names') != contract['role_names']: errors.append(label+'.role_names')
        if set(snapshot.get('catalog',{})) != set(SECTIONS): errors.append(label+'.catalog.section_inventory')
    # Required empty sets remain meaningful (policies/default grants); never skip them.
    for section in SECTIONS:
        want=reference.get('catalog',{}).get(section)
        got=actual.get('catalog',{}).get(section)
        if not isinstance(want,list) or not isinstance(got,list):
            errors.append(section+'.invalid_rows');continue
        if sorted(map(digest,want)) != sorted(map(digest,got)): errors.append(section)
    return {'status':'FAIL' if errors else 'PASS','differences':sorted(set(errors)),
            'native_execution_proven':False,
            'meaning':'Catalogue equality only; execution and permission probes require separate evidence'}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('expected_schema',type=Path);p.add_argument('actual',type=Path);p.add_argument('reference',type=Path)
    args=p.parse_args()
    try:
        result=compare(*(json.loads(path.read_text()) for path in (args.expected_schema,args.actual,args.reference)))
    except (ValueError,TypeError,AttributeError,KeyError,OSError) as exc:
        result={'status':'FAIL','differences':['Invalid input: '+type(exc).__name__],'native_execution_proven':False}
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='PASS' else 2)
