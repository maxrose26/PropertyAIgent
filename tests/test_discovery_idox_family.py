from datetime import date
import pytest
from verification.discovery.idox_family import CASES, manifest
from verification.discovery.idox_window import run, WindowConfig, WindowBoundary
from verification.bolton_recon.fixtures import FORM
from tests.test_discovery_idox_window import Response, page
from verification.stage26b_l1.request_boundary import BoundaryFailure


def test_frozen_family_excludes_bolton_and_trafford():
    assert [c.council for c in CASES]==['bury','oldham','stockport','tameside','wigan']
    assert all(c.start==date(2026,9,28) and c.end==date(2026,10,4) for c in CASES)
    assert [c.council for c in CASES if c.semantics=='VALIDATED']==['stockport']
    assert len({x['base'] for x in manifest()})==5
    with pytest.raises(ValueError):WindowConfig('trafford')
    with pytest.raises(ValueError):WindowConfig('manchester')
    with pytest.raises(ValueError):WindowConfig(start=date(2026,1,1),end=date(2026,2,1))


@pytest.mark.parametrize('config',CASES)
def test_same_contract_binds_each_council_and_date_semantics(config):
    prefix=config.base.split('.gov.uk')[-1] if '.gov.uk' in config.base else '/online-applications'
    # Existing shared fixture shape, not evidence of live council compatibility.
    form=FORM.replace(b'/online-applications',prefix.encode())
    if config.semantics=='VALIDATED':form=form.replace(b'applicationReceived',b'applicationValidated')
    stem=b'Received' if config.semantics=='RECEIVED' else b'Validated'
    echo=form.replace(b'name="date(application'+stem+b'Start)" value=""',b'name="date(application'+stem+b'Start)" value="28/09/2026"').replace(b'name="date(application'+stem+b'End)" value=""',b'name="date(application'+stem+b'End)" value="04/10/2026"')
    listing=page().replace(b'/online-applications',prefix.encode())
    if config.council=='bury':listing=listing.replace(b'keyVal=K0',b'keyVal=_BURY_DCAPR_65225').replace(b'keyVal=K1',b'keyVal=_BURY_DCAPR_65221')
    bodies=[form,listing,listing,echo];responses=[];calls=[]
    def dispatch(method,url,**kw):
        assert url.startswith(config.base+'/')
        r=Response(bodies[len(calls)])
        if config.council=='wigan':r.headers={'Content-Type':'text/html;charset=UTF-8'}
        responses.append(r);calls.append((method,url,kw.get('data')));return r
    result=run(dispatch,config)
    assert result['failure'] is None and result['enumeration_evidence']=='COUNT_RECONCILED'
    assert result['completeness']=='UNKNOWN' and result['date_semantics']==config.semantics
    assert all(r.closed for r in responses)
    assert b'application'+stem in calls[1][2]
    boundary=WindowBoundary(dispatch,config)
    with pytest.raises(BoundaryFailure):boundary.retrieve('GET',WindowConfig().form_url)
    assert boundary.requests==0
