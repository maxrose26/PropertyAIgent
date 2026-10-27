"""Existing launcher/worker/finish and publisher, synthetic sources/API, real delegated cgroups.

Hosted native fixture only; no council, database, browser, cache preparation or pressure allocation.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from verification.discovery import four_council_release as r
from verification.ingestion_storage.operational_publication import GitHub,canonical
from tests.test_discovery_four_council_release import API
from tests.source_profile_support import selection,audit,registration


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--selection',type=int,choices=(0,1,2),default=0)
    p.add_argument('--worker',type=int);p.add_argument('--output',type=Path);p.add_argument('--group',type=Path)
    p.add_argument('--registration',type=Path);p.add_argument('--registration-sha256')
    a=p.parse_args()
    if a.worker is not None:
        reg=json.loads(a.registration.read_bytes())
        def reader(row,**kwargs):
            assert kwargs==dict(retain_proof=True,no_transport_retry=True,fixed_four_rows=True,
                execution_mode='four-council-owner-local' if row['council'] in r.finite.ARCUS else None,
                execution_budget='BROWSER_SOURCE_V2' if row['council'] in r.finite.ARCUS else None,campaign_scope=row,
                collection_profile=reg['manifest']['source_profiles'][a.worker])
            return audit(row)
        with patch.object(r.finite,'read',reader):
            r.worker(a.worker,a.output,a.group,campaign_registration=a.registration,campaign_registration_sha256=a.registration_sha256)
        return 0
    a.root.mkdir(parents=True,exist_ok=False)
    plan=selection((('bolton','manchester','stockport'),('bury','rochdale','wigan'),('oldham','salford','tameside'))[a.selection])
    reg=registration(plan);reg.update(revision=r.git('rev-parse','HEAD'),tree=r.git('rev-parse','HEAD^{tree}'))
    api=API(reg)
    original=r.Source
    class FixtureSource(original):
        def command(self,index,out):
            command=super().command(index,out)
            assert command[4]==str(index) and '--campaign-registration' in command
            return [sys.executable,'-m','tests.source_profile_fixture','--root',str(a.root),'--worker',str(index),'--output',str(out),'--group',str(self.memory.source),
                '--registration',command[command.index('--campaign-registration')+1],'--registration-sha256',command[-1]]
    def github(emit,check,**kwargs):return GitHub(emit,check,runner=api.runner,**kwargs)
    # Match the existing native fixture's private evidence HOME; no credentials enter children.
    os.environ['HOME']=str(a.root)
    for key in list(os.environ):
        if any(word in key.upper() for word in ('DATABASE','SUPABASE','OPENAI','ANTHROPIC')):os.environ.pop(key)
    path=a.root/'registration.json';path.write_bytes(canonical(reg))
    with patch.object(r,'Source',FixtureSource),patch.object(r,'GitHub',github),patch.object(sys,'argv',['fixture','run','--registration',str(path),
        '--registration-sha256',r.sha(path.read_bytes()),'--enable-reviewed-source-only-stop-treatment']):
        code=r.main()
    state=a.root/'.local/state/propertyaigent'/reg['release_id']
    result=json.loads((state/'final-result.json').read_bytes())
    assert code==0 and result['status']=='MANIFEST_OBSERVATIONS_COMPLETE' and result['cleanup']=='CLOSED'
    assert [v['scope'] for v in result['results']]==reg['manifest']['rows']
    assert result['database_connections']==result['application_writes']==0 and not result['coverage_advance']
    assert result['owned_cleanup']['owned_groups_removed'] and result['owned_cleanup']['owned_survivors']==0
    for receipt in result['results']:
        outer=receipt['outer_supervisor']
        assert outer['evidence']=='SOURCE_CGROUP_READBACK' and outer['peak_owned_rss']>0 and outer['cleanup']=='CLOSED' and outer['live_owned_survivors']==0
    metrics=dict(native=True,source_inputs='SYNTHETIC_NOT_COUNCIL_QUALIFICATION',selection=a.selection,rows=reg['manifest']['rows'],accounting=result['accounting'],cleanup=result['cleanup'],
        final_publication=result['final_publication'],retained_bytes=sum(p.stat().st_size for p in state.rglob('*') if p.is_file()))
    (a.root/'rehearsal.json').write_bytes(canonical(metrics));print(json.dumps(metrics,sort_keys=True))
    return 0


if __name__=='__main__':sys.exit(main())
