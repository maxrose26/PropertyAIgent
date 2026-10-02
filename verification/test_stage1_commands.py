"""Every inventoried service rejects before touching its inputs/providers."""
import importlib,inspect,json
from pathlib import Path
import pytest
from app.security import access
from verification.test_stage1_access import admission

MANIFEST=json.loads((Path(__file__).with_name('stage1_service_manifest.json')).read_text())
CASES=[(p,n,a) for p,functions in MANIFEST.items() for n,a in functions.items() if a!='read']
class Untouchable:
    def __getattr__(self,name): raise AssertionError('Denied service touched an input: '+name)
    def __iter__(self): raise AssertionError('Denied service iterated an input')
    def __bool__(self): raise AssertionError('Denied service inspected an input')

@pytest.mark.parametrize('path,name,action',CASES)
@pytest.mark.parametrize('subject',[None,'reader'])
def test_service_denial_before_inputs(admission,path,name,action,subject):
    registry,claims,*_=admission
    function=getattr(importlib.import_module(path[:-3].replace('/','.')),name)
    args=[];kwargs={}
    for parameter in inspect.signature(function).parameters.values():
        if parameter.default is not inspect.Parameter.empty: continue
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY,inspect.Parameter.POSITIONAL_OR_KEYWORD):args.append(Untouchable())
        elif parameter.kind==inspect.Parameter.KEYWORD_ONLY:kwargs[parameter.name]=Untouchable()
    if subject:
        actor=registry.issue(dict(claims,sub=subject),'reader-cookie')
        with access.actor_scope(actor),pytest.raises(access.AccessDenied):function(*args,**kwargs)
    else:
        with pytest.raises(access.AccessDenied):function(*args,**kwargs)

@pytest.mark.parametrize('path,name,action',[case for case in CASES if case[2].startswith('paid:')])
def test_operator_paid_switch_denies_before_inputs(admission,path,name,action):
    registry,claims,_,policy_path,policy=admission
    policy['paid_actions']={};policy_path.write_text(json.dumps(policy))
    actor=registry.issue(claims,'operator')
    function=getattr(importlib.import_module(path[:-3].replace('/','.')),name)
    args=[];kwargs={}
    for parameter in inspect.signature(function).parameters.values():
        if parameter.default is not inspect.Parameter.empty:continue
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY,inspect.Parameter.POSITIONAL_OR_KEYWORD):args.append(Untouchable())
        elif parameter.kind==inspect.Parameter.KEYWORD_ONLY:kwargs[parameter.name]=Untouchable()
    with access.actor_scope(actor),pytest.raises(access.AccessDenied):function(*args,**kwargs)


def test_provider_revocation_before_result_delivery(admission):
    from app.security.commands import command
    registry,claims,_,path,policy=admission
    actor=registry.issue(claims,'operator')
    class Client:
        @property
        def responses(self):return self
        def create(self,**kwargs):
            policy['principals'][0]['enabled']=False;path.write_text(json.dumps(policy))
            return 'must not return'
    @command('search.parse',paid=True)
    def action(client):return client.responses.create(input='fixture')
    with access.actor_scope(actor),pytest.raises(access.AccessDenied):action(Client())


def test_paid_call_and_input_bounds(admission):
    from app.security.commands import command
    registry,claims,*_=admission;actor=registry.issue(claims,'operator');calls=[]
    class Client:
        @property
        def responses(self):return self
        def create(self,**kwargs):calls.append(kwargs);return 'ok'
    @command('search.parse',paid=True)
    def twice(client):
        client.responses.create(input='first')
        return client.responses.create(input='second')
    @command('search.parse',paid=True)
    def large(client,text):return client.responses.create(input=text)
    with access.actor_scope(actor):
        with pytest.raises(access.AccessDenied):twice(Client())
        assert len(calls)==1
        with pytest.raises(access.AccessDenied):large(Client(),'x'*20001)
        assert len(calls)==1


def test_internal_provider_uses_paid_boundary(admission,monkeypatch):
    from app.policy import acquisition_evaluate as module
    import openai
    registry,claims,_,path,policy=admission
    policy['paid_actions']['evaluation.run']=True;path.write_text(json.dumps(policy))
    actor=registry.issue(claims,'operator');calls=[]
    class Client:
        @property
        def responses(self):return self
        def create(self,**kwargs):calls.append(kwargs);raise AssertionError('Oversized provider input reached SDK')
    monkeypatch.setattr(openai,'OpenAI',Client)
    monkeypatch.setattr(module,'render_prompt',lambda context:'x'*300001)
    with access.actor_scope(actor):
        result,_=module._run_llm_and_validate(client=None,model='synthetic',reasoning_effort=None,context=None,key=None,mandate_fingerprint='fixture',opportunity_fingerprint='fixture',collect_telemetry=False)
    assert calls==[]
    assert 'AccessDenied' in result.diagnostic_detail


def test_visual_image_positive_with_nontrivial_payload(admission,monkeypatch,tmp_path):
    from app.visuals.classification import classify_page
    from types import SimpleNamespace
    registry,claims,_,path,policy=admission
    policy['paid_actions']['visual.classify']=True;path.write_text(json.dumps(policy));actor=registry.issue(claims,'operator')
    source=tmp_path/'fixture.png';source.write_bytes(b'x'*400000);calls=[]
    class Client:
        @property
        def responses(self):return self
        def create(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text=json.dumps(dict(is_useful=True,image_type='site_location_plan',likely_object='site',reason='fixture',confidence='high',review_required=True)))
    with access.actor_scope(actor):result=classify_page(Client(),str(source))
    assert len(calls)==1 and result['is_useful'] is True
    assert len(calls[0]['input'][0]['content'][1]['image_url'])>300000


def test_provider_option_clones_share_budget_and_recheck_authority(admission):
    from app.security.commands import bounded_provider
    registry,claims,*_=admission;actor=registry.issue(claims,'operator');calls=[]
    class Client:
        responses=None
        def __init__(self):self.responses=self
        def with_options(self,**options):assert options=={'timeout':30};return self
        def create(self,**kwargs):calls.append(kwargs);return 'ok'
    with access.actor_scope(actor):
        provider=bounded_provider(Client(),'search.parse')
        first=provider.with_options(timeout=30);second=provider.with_options(timeout=30)
        assert first.responses.create(input='fixture')=='ok'
        with pytest.raises(access.AccessDenied):second.responses.create(input='excess')
        assert len(calls)==1
        registry.revoke(actor.cookie_key)
        with pytest.raises(access.AccessDenied):provider.with_options(timeout=30)
