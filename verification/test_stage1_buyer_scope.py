import pytest
from sqlalchemy import create_engine,event,select
from sqlalchemy.orm import Session
from app.db.models import Base,Buyer,BuyerMandate,Workspace,Settings,Contact,Company,ApplicationCompany,Council,Application,Site
from app.security import access
from app.services.authorised_reads import buyer_by_key,mandate_by_id
from app.services.ui_commands import add_credits,set_site_exclusion,save_contacts
from app.policy.buyer_profile_store import list_active_buyer_options,get_buyer_profile_dataclass
from verification.test_stage1_access import admission

@pytest.fixture
def database():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Workspace(id=1,name='A'),Workspace(id=2,name='B'),Settings(id=1,credits_remaining=0)])
        session.add_all([Buyer(id=1,workspace_id=1,buyer_key='allowed',display_name='Allowed',status='active',buyer_type='housebuilder'),Buyer(id=2,workspace_id=1,buyer_key='forbidden',display_name='Forbidden',status='active',buyer_type='housebuilder'),Buyer(id=3,workspace_id=2,buyer_key='foreign',display_name='Foreign',status='active',buyer_type='housebuilder')])
        session.flush()
        from app.policy.buyer_profiles import BUYER_PROFILES
        from app.policy.buyer_profile_store import _template_to_mandate_fields
        template=next(iter(BUYER_PROFILES.values()))
        for i in (1,2,3):session.add(BuyerMandate(id=i,**_template_to_mandate_fields(template,i)))
        session.add(Council(code='test',name='Test',base_url='https://example.invalid',doc_system='idox',date_field_mode='received'))
        session.add(Site(id=1,council_code='test',canonical_address='Test',display_address='Test'))
        session.commit()
        yield session

@pytest.mark.parametrize('role',['reader','operator'])
def test_buyer_identifiers_scoped_before_load(admission,database,role):
    registry,claims,*_=admission
    actor=registry.issue(dict(claims,sub=role),role)
    with access.actor_scope(actor):
        assert list_active_buyer_options(database)==[('allowed','Allowed')]
        assert buyer_by_key(database,'allowed').id==1
        assert mandate_by_id(database,1).buyer_id==1
        for key in ('forbidden','foreign','missing'):
            with pytest.raises(access.AccessDenied):get_buyer_profile_dataclass(database,key)
        for identifier in (2,3,999):
            with pytest.raises(access.AccessDenied):mandate_by_id(database,identifier)
        assert not any(isinstance(o,Buyer) and o.id in (2,3) for o in database.identity_map.values())
        assert not any(isinstance(o,BuyerMandate) and o.id in (2,3) for o in database.identity_map.values())


def test_denied_mutation_zero_sql_and_no_autoflush(admission,database):
    registry,claims,*_=admission
    actor=registry.issue(dict(claims,sub='reader'),'reader')
    statements=[]
    event.listen(database.bind,'before_cursor_execute',lambda c,cu,s,*a:statements.append(s))
    database.add(Workspace(name='must not flush'))
    with access.actor_scope(actor):
        for call in (lambda:add_credits(database,10),lambda:set_site_exclusion(database,1,True),lambda:save_contacts(database,1,1,{})):
            with pytest.raises(access.AccessDenied):call()
    assert statements==[]


def test_operator_commits_existing_actions(admission,database):
    registry,claims,*_=admission
    actor=registry.issue(claims,'operator')
    with access.actor_scope(actor):
        add_credits(database,10)
        set_site_exclusion(database,1,True,'Synthetic reason')
    database.expire_all()
    assert database.get(Settings,1).credits_remaining==10
    assert database.get(Site,1).excluded_reason=='Synthetic reason'
    assert not database.get(Site,1).excluded_at is None


def test_operator_cannot_write_other_buyer_or_workspace(admission,database):
    from app.policy.buyer_profile_store import seed_default_buyer_profiles,run_buyer_onboarding_baseline,bootstrap_acquisition_monitoring
    registry,claims,*_=admission;actor=registry.issue(claims,'operator')
    other_workspace=database.get(Workspace,2);other_mandate=database.get(BuyerMandate,2)
    statements=[]
    event.listen(database.bind,'before_cursor_execute',lambda c,cu,s,*a:statements.append(s))
    with access.actor_scope(actor):
        for call in (lambda:seed_default_buyer_profiles(database,other_workspace),lambda:run_buyer_onboarding_baseline(database,other_mandate),lambda:bootstrap_acquisition_monitoring(database)):
            with pytest.raises(access.AccessDenied):call()
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)


def test_dirty_other_buyer_cannot_autoflush_through_allowed_command(admission,database):
    registry,claims,*_=admission;actor=registry.issue(claims,'operator')
    other=database.get(Buyer,2);other.display_name='not permitted'
    statements=[];event.listen(database.bind,'before_cursor_execute',lambda c,cu,s,*a:statements.append(s))
    with access.actor_scope(actor),pytest.raises(access.AccessDenied):add_credits(database,10)
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)


def test_claim_cannot_be_substituted_from_another_buyer(admission,database):
    from app.db.models import AcquisitionSubjectAnchor,AgentEvaluationClaim
    from app.policy.agent_evaluation_persistence import record_evaluation_outcome
    from verification.test_stage1_commands import Untouchable
    database.add(AcquisitionSubjectAnchor(id=1,subject_type='planning_delivery',anchor_id=1,scope_key='WHOLE_SITE'))
    claim=AgentEvaluationClaim(id=1,buyer_mandate_id=2,subject_anchor_id=1,acquisition_type='planning_delivery',evaluation_input_fingerprint='fixture')
    database.add(claim);database.commit()
    registry,claims,*_=admission;actor=registry.issue(claims,'operator')
    statements=[];event.listen(database.bind,'before_cursor_execute',lambda c,cu,s,*a:statements.append(s))
    with access.actor_scope(actor),pytest.raises(access.AccessDenied):
        record_evaluation_outcome(database,claim=claim,result=Untouchable(),buyer_mandate_id=1,subject_anchor_id=1,acquisition_type='planning_delivery',opportunity_id='site:1',buyer_mandate_fingerprint='fixture',evaluation_input_fingerprint='fixture',model_id='fixture',structured_output_schema_version=1)
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)
    assert claim.status=='claimed' and claim.history_id is None


def test_revocation_before_commit_does_not_write(admission,database,monkeypatch):
    import json
    registry,claims,_,path,policy=admission;actor=registry.issue(claims,'operator')
    original=database.commit
    def revoke_and_commit():
        policy['principals'][0]['enabled']=False;path.write_text(json.dumps(policy));original()
    monkeypatch.setattr(database,'commit',revoke_and_commit)
    statements=[];event.listen(database.bind,'before_cursor_execute',lambda c,cu,s,*a:statements.append(s))
    with access.actor_scope(actor),pytest.raises(access.AccessDenied):add_credits(database,10)
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)


@pytest.mark.parametrize('operation',['buyer','mandate','options','profile'])
def test_revocation_during_private_read_denies_result(admission,database,operation):
    import json
    registry,claims,_,path,policy=admission;actor=registry.issue(claims,'operator')
    def revoke(*args):
        policy['principals'][0]['enabled']=False;path.write_text(json.dumps(policy))
    event.listen(database.bind,'after_cursor_execute',revoke,once=True)
    actions={'buyer':lambda:buyer_by_key(database,'allowed'),'mandate':lambda:mandate_by_id(database,1),'options':lambda:list_active_buyer_options(database),'profile':lambda:get_buyer_profile_dataclass(database,'allowed')}
    with access.actor_scope(actor),pytest.raises(access.AccessDenied):actions[operation]()


def test_reparenting_other_mandate_does_not_launder_authority(admission,database):
    registry,claims,*_=admission;actor=registry.issue(claims,'operator')
    other=database.get(BuyerMandate,2);other.buyer_id=1
    statements=[];event.listen(database.bind,'before_cursor_execute',lambda c,cu,s,*a:statements.append(s))
    with access.actor_scope(actor),pytest.raises(access.AccessDenied):add_credits(database,10)
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)


def test_visual_review_reloads_and_checks_relationships(admission,database):
    from app.db.models import VisualEvidence
    from app.visuals.review import confirm_image,relink_image,mark_primary
    image=VisualEvidence(id=1,site_id=1,source_page=1,image_type='unknown',status='current')
    sibling=VisualEvidence(id=2,site_id=1,source_page=2,image_type='unknown',status='current')
    database.add_all([image,sibling]);database.commit()
    registry,claims,*_=admission;actor=registry.issue(claims,'operator')
    with access.actor_scope(actor):
        confirm_image(database,image,'forged-attribution')
        mark_primary(database,image,[image,sibling])
        with pytest.raises(access.AccessDenied):relink_image(database,image,site_id=999)
        assert image.site_id==1 and image.is_primary
        assert image.confirmed_by==access.actor_label() and not sibling.is_primary
