import requests
from verification.discovery.remaining_source_once import wigan_shape


def test_wigan_diagnostic_never_dispatches_a_second_request(monkeypatch):
    calls=[]
    class Session:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def mount(self,*args):pass
        def request(self,*args,**kwargs):
            calls.append(args);raise requests.Timeout('fixture')
    monkeypatch.setattr(requests,'Session',Session)
    audit=wigan_shape()
    assert len(calls)==1 and audit['failure'] is not None
    assert audit['resource']['requests_attempted']==1
    assert audit['cleanup']=='SESSION_BOUNDARY_CLOSED'
