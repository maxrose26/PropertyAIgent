"""Minimal derived observation using the accepted family evaluator. Offline only."""
from collections import Counter
from datetime import datetime, timezone
import json
from sqlalchemy import select
from app.db.models import Application, Buyer, BuyerMandate
from app.services.authorised_reads import buyer_query
from app.policy.buyer_profile_store import _resolve_default_mandate_for_buyer
from app.reporting.buyer_family_feed import load_buyer_family_inputs, evaluate_buyer_families
from verification.buyer_dependency.safety import guarded_window, ObservationFailure

VERSION='buyer-dependency-observation-v1'
LIMITS=dict(buyers=20,families=12000,subjects=20000,rows=40000,bytes=2000000,queries=12000,seconds=120)

def encode(artifact):
    raw=json.dumps(artifact,sort_keys=True,separators=(',',':'),ensure_ascii=True)
    if len(raw.encode())>LIMITS['bytes']: raise ObservationFailure('output byte overflow')
    return raw

def observe(session, *, code_sha, synthetic=False, structural=None, expected_buyer_ids=None):
    if len(code_sha)!=40 or any(c not in '0123456789abcdef' for c in code_sha):
        raise ObservationFailure('exact SHA required')
    records=[]; counts=Counter({k:0 for k in ["DIRECT_FACTUAL_DEPENDENCY","CONTEXT_DEPENDENCY","DISCOVERY_RELATIONSHIP","UNKNOWN"]}); seen=set(); contexts={}
    with guarded_window(session,synthetic=synthetic,max_queries=LIMITS['queries'],seconds=LIMITS['seconds']) as safety:
        buyers=session.execute(buyer_query().order_by(Buyer.id)).scalars().all()
        if not synthetic and expected_buyer_ids is None: raise ObservationFailure('buyer census expectations required')
        if expected_buyer_ids is not None and {b.id for b in buyers}!=set(expected_buyer_ids): raise ObservationFailure('buyer scope incomplete')
        if not buyers or len(buyers)>LIMITS['buyers']: raise ObservationFailure('buyer count invalid')
        mandates={}
        for buyer in buyers:
            active=session.execute(select(BuyerMandate).where(BuyerMandate.buyer_id==buyer.id,BuyerMandate.status=='active')).scalars().all()
            if len(active)!=1: raise ObservationFailure('missing/ambiguous mandate')
            mandate=_resolve_default_mandate_for_buyer(session,buyer)
            if mandate is None or mandate.id!=active[0].id: raise ObservationFailure('mandate mismatch')
            mandates[buyer.id]=mandate
        inputs=load_buyer_family_inputs(session)
        # Batched IDs only for mapping the existing exact source reference. No
        # newest/same-site inference: reference must come from freshness adapter.
        applications=session.execute(select(Application.id,Application.site_id,Application.reference)).all()
        by_source={}
        for aid,sid,ref in applications: by_source.setdefault((sid,ref),[]).append(aid)
        for buyer in buyers:
            result=evaluate_buyer_families(session,buyer.buyer_key,inputs,LIMITS['families']+1,contexts=contexts,include_excluded=True)
            families=[*result['families'],*result['excluded_families']]
            if len(families)!=result['counts']['families_considered']: raise ObservationFailure('family truncation')
            if len(families)>LIMITS['families']: raise ObservationFailure('family overflow')
            member_count=0
            for family in families:
                counts['families']+=1
                for subject in family.members:
                    member_count+=1; counts['subjects']+=1
                    key=(buyer.id,subject.subject_key)
                    if key in seen: raise ObservationFailure('duplicate subject')
                    seen.add(key)
                    card=subject.source or {}; params=card.get('params',{})
                    sid=int(params['site_id']) if 'site_id' in params else None
                    allocation=int(params['allocation_id']) if 'allocation_id' in params else None
                    role='REPRESENTATIVE' if subject is family.representative else 'MEMBER'
                    counts[role]+=1
                    positions=card.get('planning_freshness') or [(None,None,None)]
                    for label,ref,freshness in positions:
                        ids=by_source.get((sid,ref),[]) if ref else []
                        exact=len(ids)==1 and freshness is not None and freshness.planning_state!='unknown_unverified' and freshness.freshness!='conflicting'
                        dependency='DIRECT_FACTUAL_DEPENDENCY' if exact else 'UNKNOWN'
                        aid=ids[0] if exact else None
                        correlation='UNRESOLVED'
                        if structural is not None:
                            keys=[('sites',sid),('applications',aid),('local_plan_sites',allocation)]
                            missing=[(s,i) for s,i in keys if i is not None and i not in structural.get(s,set())]
                            correlation='UNRESOLVED' if missing else 'MATCHED_STRUCTURAL_ENTITY'
                        records.append(dict(buyer_id=buyer.id,mandate_id=mandates[buyer.id].id,mandate_fingerprint=mandates[buyer.id].matching_fingerprint,subject_key=subject.subject_key,subject_type=subject.domain,subject_scope=subject.slot,site_id=sid,allocation_id=allocation,family_identity=list(family.family_key),role=role,visibility='TERMINALLY_EXCLUDED' if family.is_terminally_excluded else 'ADMITTED_CANDIDATE',status_source_application_id=aid,status_source_reference=ref if exact else None,supported_field='planning_status' if exact else None,dependency_type=dependency,attribution='EXACT_EXISTING_STATUS_SOURCE' if exact else 'UNRESOLVED',structural_correlation=correlation))
                        counts[dependency]+=1
                        if len(records)>LIMITS['rows']: raise ObservationFailure('row overflow')
            if member_count!=result['counts']['subjects_considered']: raise ObservationFailure('member truncation')
            if member_count>LIMITS['subjects']: raise ObservationFailure('subject overflow')
        output=dict(manifest_version=VERSION,execution_status='COMPLETE',overflow=False,code_sha=code_sha,observed_at=datetime.now(timezone.utc).isoformat(),snapshot=safety['snapshot'],isolation=safety['isolation'],synthetic=synthetic,counts=dict(counts,buyers=len(buyers),rows=len(records)),records=sorted(records,key=lambda r:(r['buyer_id'],r['subject_key'],r['status_source_application_id'] or 0)),limits=LIMITS.copy())
        output['query_count']=safety['queries']
        encode(output)
    return output
