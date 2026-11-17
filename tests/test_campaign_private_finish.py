"""Exercise the actual finalisation seam in both modes, without source/network."""
import hashlib,json,textwrap
from pathlib import Path
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import daily_intake_runtime as runtime

@pytest.mark.parametrize('test_mode',[False,True])
def test_private_campaign_finalisation_never_calls_github(test_mode,tmp_path,monkeypatch):
    from app.ingestion import public_evidence
    monkeypatch.setattr(public_evidence,'project_public_summary',lambda result,**kw:dict(result))
    source=Path(runtime.__file__).read_text()
    start=source.index("            private_backend=(self.policy or {}).get('evidence_backend')")
    end=source.index("                    payload=dict(operation='intake_finish'",start)
    code=textwrap.dedent(source[start:end])+"\nfinally:\n    pass\n"
    archived=[]
    def archive(raw,events):
        archived.append((raw,events))
        return {'final/result-before-publication.json':dict(backend='PRIVATE_POSTGRES_V1',period='P',run_id='a'*32,name='final/result-before-publication.json',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),readback_verified=True)}
    def forbidden(*args,**kwargs):raise AssertionError('private campaign tried GitHub')
    actor=SimpleNamespace(policy=dict(evidence_backend='POSTGRES_PILOT_V1',mode='CAMPAIGN_FINITE_HISTORICAL_V1'),test=test_mode,authorities=['x'],run=SimpleNamespace(publication=lambda *a:None),archive_private_final=archive,events=[],github=None,head=None,args=SimpleNamespace(period='P',disposable_archive=str(tmp_path)),run_id='a'*32)
    scope=dict(self=actor,result=dict(status='RETAINED_AND_SCREENED',cleanup='CLOSED',authority_closure='INVALIDATED'),canonical=runtime.canonical,hashlib=hashlib,Path=Path,GitHub=forbidden,LIMITS=runtime.LIMITS)
    exec(compile(code,str(Path(runtime.__file__))+'[actual-finalisation-seam]','exec'),scope)
    assert len(archived)==1
    assert json.loads(archived[0][0])['github_publication']=='NOT_REQUESTED'
    assert scope['publication']['backend']=='PRIVATE_POSTGRES_V1'
    assert scope['publication']['sha256']==hashlib.sha256(archived[0][0]).hexdigest()
    assert 'commit' not in scope['publication']
