"""Local, inactive preparation only. No DB/GitHub, credentials or expiry rendering."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,stat
from pathlib import Path


def checked_file(path,bound):
    mode=path.lstat()
    if path.is_symlink() or not stat.S_ISREG(mode.st_mode) or mode.st_size>bound:raise SystemExit('STOP: INPUT_FILE_BOUND')
    return mode


def main(argv=None):
    a=argparse.ArgumentParser();a.add_argument('--checkout',type=Path,required=True);a.add_argument('--assets',type=Path,required=True);a.add_argument('--original-result',type=Path,required=True);a.add_argument('--original-audit',type=Path,required=True);a.add_argument('--reconciliation',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--evidence-head',required=True);a.add_argument('--release-id',required=True);x=a.parse_args(argv)
    for key in ('checkout','assets','original_result','original_audit','reconciliation','output'):setattr(x,key,getattr(x,key).absolute())
    os.umask(0o077);os.chdir(x.checkout)
    sys.path.insert(0,str(x.checkout.resolve()))
    from verification.ingestion_storage import oldham_owner_package as pkg,oldham_reuse as r
    from verification.ingestion_storage.operational_publication import canonical
    from app.ingestion.ledger import digest
    if pkg.git('status','--porcelain') or not re.fullmatch('[a-f0-9]{40}',x.evidence_head):raise SystemExit('STOP: CHECKOUT_OR_EVIDENCE_HEAD')
    if not re.fullmatch('oldham-owner-[a-z0-9-]{1,60}',x.release_id) or x.release_id==r.FAILED_RELEASE:raise SystemExit('STOP: RELEASE_ID')
    # Files must all exist before creating the new preparation directory.
    paths={'failed_claim':x.assets/'failed-claim.json','original_result':x.original_result,'original_audit':x.original_audit,'reconciliation':x.reconciliation}
    for key,p in paths.items():checked_file(p,r.FILES[key])
    claim=json.loads(paths['failed_claim'].read_bytes());p=claim['package']
    if claim['package_sha256']!=r.FAILED_PACKAGE or digest(p)!=r.FAILED_PACKAGE:raise SystemExit('STOP: FAILED_CLAIM_HASH')
    for key in ('source','outer','qualification'):
        f=x.assets/p[key]['name']
        checked_file(f,{'source':512*1024,'outer':16*1024,'qualification':64*1024}[key])
        if pkg.sha(f.read_bytes())!=p[key]['sha256']:raise SystemExit('STOP: RETAINED_ASSET_HASH')
    x.output.mkdir(mode=0o700,parents=False,exist_ok=False)
    descriptors={}
    for key,f in paths.items():
        name={'failed_claim':'failed-claim.json','original_result':'original-result.json','original_audit':'original-audit.jsonl','reconciliation':'reconciliation.json'}[key]
        destination=x.output/name;shutil.copy2(f,destination) # preserves original mode finding; never chmods the source
        descriptors[key]=dict(name=name,sha256=pkg.sha(destination.read_bytes()))
    for key in ('source','outer','qualification'):shutil.copy2(x.assets/p[key]['name'],x.output/p[key]['name'])
    p.pop('transition');p.update(version=pkg.VERSION_INSTALLED,release_id=x.release_id,revision=pkg.git('rev-parse','HEAD'),tree=pkg.git('rev-parse','HEAD^{tree}'),dependencies=pkg.dependencies(),evidence_head=x.evidence_head,expires_at=None,
        reuse=dict(authority=r.AUTHORITY,registration_sha256=r.REGISTRATION,failed_package_sha256=r.FAILED_PACKAGE,failed_release_id=r.FAILED_RELEASE,role_settings=r.SETTINGS,**descriptors))
    p['qualification_binding']['dependencies_sha256']=digest(p['dependencies'])
    # Original package versions are retained; no installation/upgrade is attempted.
    if p['packages']!=pkg.packages():raise SystemExit('STOP: OWNER_RUNTIME_VERSION_MISMATCH')
    raw=canonical(p);out=x.output/'package.INACTIVE.json';out.write_bytes(raw)
    pkg.validate(out,pkg.sha(raw),inactive=True)
    print(json.dumps(dict(status='INACTIVE_VALIDATED',package=str(out),sha256=pkg.sha(raw),expires_at=None,database_connections=0,credentials_requested=False)))
    return 0

if __name__=='__main__':raise SystemExit(main())
