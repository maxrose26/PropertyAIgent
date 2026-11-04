from decimal import Decimal
import pytest
from verification.ingestion_storage import runtime_authentication as a
D=1793827036.7709913

def row(role,value):
    worker=role=='ingestion_worker_login'
    return (role,role,True,'10s','3s','20s',True,worker,worker,worker,value)

@pytest.mark.parametrize('role',a.op.ROLES)
def test_captured_exact_numeric_deadline_matches(role):
    assert a.profile_comparison(row(role,Decimal('1793827036.770991')),role,D)['status']=='MATCH'

@pytest.mark.parametrize('role',a.op.ROLES)
@pytest.mark.parametrize('value',[Decimal('1793827036.770990'),Decimal('1793827036.770992'),Decimal('NaN'),Decimal('Infinity'),1793827036.77099,'1793827036.770991',None])
def test_different_or_nonexact_deadline_refuses(role,value):
    result=a.profile_comparison(row(role,value),role,D)
    assert result['status']=='MISMATCH' and result['first_mismatch']=='credential_deadline'
    assert all(v for k,v in result['checks'].items() if k!='credential_deadline')

@pytest.mark.parametrize('now',[D-1500,D,D+1])
def test_expired_or_insufficient_reserve_refuses_before_connect(monkeypatch,now):
    from types import SimpleNamespace
    monkeypatch.setattr(a.time,'time',lambda:now)
    runtime=SimpleNamespace(args=SimpleNamespace(period='offline'),binding={},emit=lambda *_:None)
    value=a.qualify(runtime,D,budget_factory=lambda **kw:pytest.fail('CONNECTION_ATTEMPTED'))
    assert value['status']=='REFUSED' and value['attempts']==[] and value['source_requests']==0

@pytest.mark.parametrize('deadline',[D,-0.5,0.000001,253402300799.0])
def test_exact_conversion_independent_of_decimal_context(deadline):
    from decimal import localcontext
    from datetime import datetime,timezone
    dt=datetime.fromtimestamp(deadline,timezone.utc)
    with localcontext() as c:
        c.prec=4
        actual=a.exact_deadline_epoch(deadline)
    # String construction used as independent oracle, including negative epochs.
    import calendar
    seconds=calendar.timegm(dt.utctimetuple())
    expected=Decimal(seconds)+Decimal(dt.microsecond)/Decimal(1000000)
    assert actual==expected
