"""Offline fixed-scope proposals; synthetic parent responses, no public calls."""
import hashlib,json,time,os
from copy import deepcopy
from pathlib import Path
import pytest
from tests.test_discovery_idox_window import Response
from verification.bolton_recon.fixtures import FORM
from verification.discovery import r0_exact9 as nine,bolton_parent_metadata as parents


@pytest.fixture(autouse=True)
def credential_free_test_context(monkeypatch):
    for k in list(os.environ):
        if 'DATABASE' in k or k.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')):
            monkeypatch.delenv(k,raising=False)


def test_exact9_provenance_limits_and_unregistered_template():
    m=json.loads(nine.MANIFEST.read_bytes());p=nine.plan()
    prior=json.loads((nine.PACK/'source-exact16-result.json').read_bytes())
    assert m['rows']==prior['not_attempted'] and len(m['rows'])==9
    assert nine.PROFILE['requests']==9*10 and nine.PROFILE['bytes']==9*3_000_000
    assert nine.PROFILE['seconds']==9*55 and not (nine.ROOT/nine.WORKFLOW).exists()
    assert p['manifest_sha256']==hashlib.sha256(nine.MANIFEST.read_bytes()).hexdigest()
    template=nine.TEMPLATE.read_text();assert 'GITHUB_WORKFLOW_SHA: ${{ github.workflow_sha }}' in template
    assert 'verification.discovery.r0_exact9' in template and 'environment:' not in template and 'DATABASE_URL' not in template
    assert 'timeout-minutes: 16' in template


def test_exact9_actual_worker_delegates_manifest_checkpoint_parent(monkeypatch,tmp_path):
    monkeypatch.delenv('DATABASE_URL',raising=False);seen={}
    def execute(plan,digest,**kw):
        seen.update(plan=plan,digest=digest,reader=kw['reader'],limits=kw['limits'],containment=kw['containment'])
        kw['checkpoint']({'window':plan['rows'][0],'synthetic':True})
        return dict(results=[],stop_reason=None,completeness='INCOMPLETE')
    monkeypatch.setattr(nine.recovery,'_execute_fixed',execute)
    nine.execute_worker(nine.plan(),tmp_path/'result.json',tmp_path)
    assert seen['plan']['rows']==json.loads(nine.MANIFEST.read_bytes())['rows']
    assert (tmp_path/'checkpoints/000.json').is_file()
    assert seen['digest']==nine.MANIFEST_SHA and seen['reader'] is nine.finite.read and seen['containment']


def test_fixed_parent_metadata_summary_and_privacy(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    summary=b'<html><table id="simpleDetailsTable"><tr><th>Reference</th><td>00284/26</td></tr><tr><th>Proposal</th><td>Development of 49 apartments</td></tr><tr><th>Applicant</th><td>PRIVATE PERSON</td></tr></table></html>'
    listed=b'<html><a href="applicationDetails.do?activeTab=summary&amp;keyVal=PARENT">record</a></html>'
    bodies=[FORM,listed,summary];responses=[]
    def dispatch(*a,**kw):
        r=Response(bodies.pop(0));responses.append(r);return r
    out=parents.metadata('00284/26',dispatch)
    assert out['identity']=='EXACT_DISPLAYED_REFERENCE' and out['failure'] is None
    assert out['fields']['Proposal']['value']=='Development of 49 apartments'
    assert out['fields']['Status']['state']=='NOT_PRESENT'
    assert 'PRIVATE PERSON' not in json.dumps(out) and all(r.closed for r in responses)
    assert out['cleanup']=='BOUNDARY_CLOSED' and out['resource']['requests_attempted']==3
    assert not out['persistence']


@pytest.mark.parametrize('text',[
    '<html><a href="applicationDetails.do?activeTab=summary&amp;keyVal=A">a</a><a href="applicationDetails.do?activeTab=summary&amp;keyVal=B">b</a></html>',
    '<html><a href="https://wrong.invalid/applicationDetails.do?activeTab=summary&amp;keyVal=A">a</a></html>',
    '<html><a class="next" href="advancedSearchResults.do?action=page2">Next</a></html>',
])
def test_parent_ambiguity_pagination_wrong_origin_withheld(monkeypatch,text):
    monkeypatch.delenv('DATABASE_URL',raising=False);bodies=[FORM,text.encode()]
    out=parents.metadata('00284/26',lambda *a,**kw:Response(bodies.pop(0)))
    assert out['identity']=='WITHHELD' and out['failure'] and out['resource']['requests_attempted']==2


def test_parent_arbitrary_identity_and_credentials_rejected(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    with pytest.raises(ValueError):parents.metadata('other',lambda *a,**k:pytest.fail('source'))
    monkeypatch.setenv('DATABASE_URL','not-used')
    with pytest.raises(ValueError):parents.metadata('00284/26',lambda *a,**k:pytest.fail('source'))


def test_actual_retained_priority_citations_and_bad_states():
    from app.pipeline.discovery_screening import screen
    p=nine.ROOT/'docs/design/stage4-r0-execution/bolton-screening-exact16-registration/bolton53-screening.json'
    raw=json.loads(p.read_bytes());rows=raw if isinstance(raw,list) else raw.get('records',raw.get('rows',[]))
    # Exact retained descriptions are tested in the ledger regardless of schema.
    for r in rows:
        if r['reference'] in {'01769/26','01827/26'}:
            result=screen(dict(fields=dict(proposal=r['proposal'])))
            assert set(r['explicit_related_references']) <= set(result['related_reference_literals'])
    text=p.read_text();assert '00284/26' in text and '20683/25' in text
    for proposal,parent in [('NON-MATERIAL AMENDMENT TO APPLICATION 00284/26 TO INCLUDE CHANGES','00284/26'),('VARIATION OF CONDITION ON APPLICATION 20683/25','20683/25')]:
        s=screen(dict(fields=dict(proposal=dict(state='PRESENT_VALUE',value=proposal,locator='a.summaryLink'))))
        assert parent in s['related_reference_literals'] and s['relationship']=='UNKNOWN' and not s['exclusion']
    for state,value in [('CONFLICTING','application 20683/25'),('UNPARSEABLE',{'bad':1}),('PRESENT_VALUE',{'bad':1})]:
        s=screen(dict(fields=dict(proposal=dict(state=state,value=value,locator='test'))))
        assert s['related_reference_literals']==[] and s['retained']


def test_actual_exact9_template_parent_supervisor_worker_chain(tmp_path,monkeypatch):
    import sys,psutil,yaml
    from unittest.mock import MagicMock,patch
    from tests.test_discovery_r0_registered_scopes import context,proc_namespace
    from tests.test_discovery_r0_recovery_proposal import evidence
    from verification.discovery import r0_proposal as outer,r0_registered_scopes as shared
    wf=yaml.load(nine.TEMPLATE.read_text(),Loader=yaml.BaseLoader)
    env=dict(context('bolton53'),GITHUB_WORKFLOW_REF='maxrose26/PropertyAIgent/'+nine.WORKFLOW+'@refs/heads/master')
    replacements={'${{ inputs.reviewed_sha }}':'a'*40,'${{ inputs.manifest_sha }}':nine.MANIFEST_SHA,
        '${{ inputs.authority }}':nine.AUTHORITY,'${{ github.workflow_sha }}':'a'*40,
        '${{ env.SOURCE_JOB_STARTED_EPOCH }}':str(int(time.time()))}
    for step in wf['jobs']['source']['steps']:
        env.update({k:replacements[v] for k,v in step.get('env',{}).items() if v in replacements})
    for k,v in env.items():monkeypatch.setenv(k,v)
    for k,v in [('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2')]:
        with pytest.raises(ValueError):nine.admit('a'*40,nine.MANIFEST_SHA,nine.AUTHORITY,dict(env,**{k:v}),workflow_bytes=nine.TEMPLATE.read_bytes())
    directory=tmp_path/'audit';calls=[];launches=[]
    def reader(row):
        assert len(list((directory/'checkpoints').glob('*.json')))==len(calls)
        calls.append(row);return evidence(row)
    def runner(command,**kw):
        launches.append(command)
        assert command[1:3]==['-m','verification.discovery.r0_exact9']
        assert not any('DATABASE' in k or 'AUTHORITY' in k for k in kw['env'])
        plan=json.loads(Path(command[command.index('--worker')+1]).read_bytes());assert plan==nine.plan()
        nine.execute_worker(plan,Path(command[command.index('--output')+1]),directory)
        child=MagicMock(pid=999999,returncode=0);child.poll.return_value=0;child.wait.return_value=0;return child
    real=outer.supervise_round;admit=nine.admit
    monkeypatch.setattr(sys,'argv',['exact9','--reviewed-sha','a'*40,'--manifest-sha',nine.MANIFEST_SHA,'--authority',nine.AUTHORITY,'--output',str(directory)])
    with proc_namespace(),patch.object(nine,'admit',side_effect=lambda s,m,a,e:admit(s,m,a,e,workflow_bytes=nine.TEMPLATE.read_bytes())),patch.object(shared,'checkout'),patch.object(nine.finite,'read',reader),patch.object(outer,'supervise_round',side_effect=lambda p,o,**kw:real(p,o,runner=runner,**kw)),patch.object(psutil,'Process',return_value=MagicMock()),patch.object(psutil,'wait_procs',return_value=([],[])):
        assert nine.main()==0
    assert len(calls)==9 and len(launches)==1
