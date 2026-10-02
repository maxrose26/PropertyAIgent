"""Offline-only synthetic authority adapter, never imported by application code.

Historical functional tests now run as an explicitly admitted local operator.
Fresh fixtures contain explicit buyer rows and Settings; no production fallback.
"""
import json
import time
from contextlib import contextmanager
from pathlib import Path
from app.security import access

PAID_ACTIONS = ['contacts.enrich','plan.summary','allocation.summary','shortlist.intelligence','shortlist.research','search.parse','report.narrative','evaluation.run']

@contextmanager
def synthetic_context(directory):
    import os
    path=Path(directory)/'synthetic-policy.json'
    issuer='http://127.0.0.1:19999'
    policy=dict(version=1,enabled=True,environment='local',issuer=issuer,client_id='offline-test',web_processes=1,web_replicas=1,owner_subject='synthetic-operator',principals=[dict(issuer=issuer,subject='synthetic-operator',role='operator',enabled=True,workspace_id=1,buyer_ids=[1,2,3,4])],paid_actions=dict.fromkeys(PAID_ACTIONS,True))
    path.write_text(json.dumps(policy))
    old_path=os.environ.get('PROPERTYAIGENT_ACCESS_POLICY');old_registry=access.registry
    os.environ['PROPERTYAIGENT_ACCESS_POLICY']=str(path)
    registry=access.LeaseRegistry();registry.boot=int(time.time())-1;registry.middleware_ready=True
    access.registry=registry
    claims=dict(iss=issuer,sub='synthetic-operator',aud='offline-test',iat=int(time.time()),exp=int(time.time())+3600,email_verified=True)
    actor=registry.issue(claims,'synthetic-offline-cookie')
    try:
        with access.actor_scope(actor): yield actor
    finally:
        access.registry=old_registry
        if old_path is None: os.environ.pop('PROPERTYAIGENT_ACCESS_POLICY',None)
        else: os.environ['PROPERTYAIGENT_ACCESS_POLICY']=old_path


def seed_fixture(engine):
    from sqlalchemy.orm import Session
    from app.db.models import Settings, Workspace, Buyer, BuyerMandate
    from app.policy.buyer_profile_store import _template_to_buyer_fields, _template_to_mandate_fields
    from app.policy.buyer_profiles import BUYER_PROFILES, BUYER_PROFILE_ORDER
    with Session(engine) as session:
        if session.get(Settings,1) is None: session.add(Settings(id=1,credits_remaining=0))
        if session.get(Workspace,1) is None:
            # Model defaults preserve the accepted pilot fields.
            session.add(Workspace(id=1,name='Synthetic pilot'))
            session.flush()
            for idx,key in enumerate(BUYER_PROFILE_ORDER,1):
                template=BUYER_PROFILES[key]
                session.add(Buyer(id=idx,**_template_to_buyer_fields(template,1)))
                session.flush()
                session.add(BuyerMandate(id=idx,**_template_to_mandate_fields(template,idx)))
        session.commit()
