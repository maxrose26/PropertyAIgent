"""One read-only projection for source claims; disabled unless explicitly enabled."""
from dataclasses import replace
import os
from sqlalchemy.orm import object_session
from app.policy.ah_assessment import AHAssessment, AHClaim, TenureClaim
from app.policy.ah_claim_store import context, fold, source_valid, ClaimError, read_snapshot
from app.db.ah_claim_schema import claims, verify_schema
from sqlalchemy import select, or_


def enabled():
    return os.environ.get('PROPERTYAIGENT_AH_SOURCE_CLAIMS') == '1'


def with_legacy(assessment, legacy):
    """Retain unverified legacy leads without replacing an explicit source unknown."""
    if legacy is None:
        return assessment
    count=assessment.count
    if not count.document_id and not assessment.alternatives and count.qualifier=='unknown':
        count=legacy.count
    return replace(assessment,count=count,reported_percentage=legacy.reported_percentage,
        percentage_review_reason=legacy.percentage_review_reason,
        reported_tenure=legacy.reported_tenure,reported_evidence=legacy.reported_evidence)


def select_claims(conn, application_ids, *, phase_label=None):
    """None means no captured assertions; unknown is an explicit assessment.

    A missing enabled schema is an error, never an implicit legacy fallback.
    Application/scheme IDs, not unreviewed stage strings, define contexts.
    """
    verify_schema(conn)
    seed=list(conn.execute(select(claims.c.scheme_application_id).where(or_(
        claims.c.application_id.in_(application_ids),claims.c.scheme_application_id.in_(application_ids)))).scalars())
    if not seed:
        return None
    cr,ev,_=context(conn,sorted(set(seed)))
    state,links=fold(cr,ev)
    replaced={e['claim_id'] for e in links if e['action'] in ('CORRECT','SUPERSEDE')}
    replacement_graph={}
    for e in links:
        if e['action'] in ('CORRECT','SUPERSEDE'):
            replacement_graph.setdefault(e['claim_id'],[]).append(e['related_claim_id'])
    def valid_terminal(cid, seen=frozenset()):
        if cid in seen:
            raise ClaimError('replacement_cycle')
        successors=replacement_graph.get(cid,[])
        return all(valid_terminal(n,seen|{cid}) for n in successors) if successors else state[cid]['status']=='ACCEPT'
    invalid_replacement=any(not valid_terminal(cid) for cid in replacement_graph)
    explicit_conflicts={e['claim_id'] for e in links if e['action']=='CONFLICT'} | {e['related_claim_id'] for e in links if e['action']=='CONFLICT'}
    evidence=[]; eligible=[]; pending=[]; tenures=[]; tenure_groups={}
    for c in cr:
        s=state[c['id']]
        relevant=phase_label is None or c['scope_label']==phase_label
        if not relevant:
            continue
        status=s['status']
        try:
            apps=source_valid(conn,c,accepting=status=='ACCEPT')
            app=apps[c['application_id']]
        except ClaimError:
            status='NEEDS_REVIEW'; apps={}; app={}
        if apps:
            from app.pipeline.material_change import resolve_decided_state
            decided=resolve_decided_state(app.get('decision'),app.get('status'))
        else:
            decided='unresolved'
        historical=c['id'] in replaced or decided in ('refused','withdrawn')
        checked=bool(s['accept'] and s['accept']['stage_checked'])
        stage=c['planning_stage'] if checked else c['planning_stage'] + ' (reported; stage unverified)'
        qstate=('verified' if c['qualifier']=='exact' else 'estimated') if status=='ACCEPT' and c['qualifier']!='unknown' else 'unknown'
        item=AHClaim(value=float(c['value']) if c['value'] is not None else None,
            lower=float(c['lower_bound']) if c['lower_bound'] is not None else None,
            upper=float(c['upper_bound']) if c['upper_bound'] is not None else None,
            qualifier=c['qualifier'],state=qstate,
            application_reference=app.get('reference') or str(c['application_id']),
            scope_type='whole_site' if c['scope_kind']=='whole_scheme' else c['scope_kind'],
            scope_label=c['scope_label'],stage=stage,document_id=str(c['document_id']),
            source_url=c['document_url_snapshot'],document_date=str(c['document_date']) if c['document_date'] else None,
            passage=c['passage_text'],review_reason='Source and scope checked' if status=='ACCEPT' else 'Source/scope review pending or invalid')
        evidence.append({'id':c['id'],'application_id':c['application_id'],'scheme_application_id':c['scheme_application_id'],
            'scope_key':c['scope_key'],'metric':c['metric'],'tenure_name':c['tenure_name'],
            'status':status,'historical':historical,'stage_checked':checked,
            'document_id':c['document_id'],'passage_locator':c['passage_locator'],
            'passage_hash':c['passage_hash'],'claim':item.__dict__,
            'replacements':[e['related_claim_id'] for e in links if e['claim_id']==c['id'] and e['action'] in ('CORRECT','SUPERSEDE')]})
        if historical or status in ('REJECT','WITHDRAW'):
            continue
        if c['metric']=='tenure_count':
            tenures.append(TenureClaim(c['tenure_name'],item))
            key=(c['scheme_application_id'],c['scope_key'],c['tenure_name'])
            tenure_groups.setdefault(key,set()).add((item.qualifier,item.value,item.lower,item.upper,status))
            continue
        if status=='ACCEPT':
            eligible.append((c,item))
        else:
            pending.append((c,item))
    if not evidence:
        return None
    # Independent documents may corroborate. Different scopes and roots are
    # never summed or allowed to cherry-pick a numeric bound.
    keys={(c['scheme_application_id'],c['scope_kind'],c['scope_key'],i.qualifier,i.value,i.lower,i.upper) for c,i in eligible}
    count=AHClaim(); alternatives=()
    if invalid_replacement:
        reason='Replacement requires review; historical evidence has not been resurrected.'
        alternatives=tuple(i for _,i in eligible)+ (AHClaim(),)
        count=AHClaim(state='conflicting')
    elif len(keys)>1 or pending and eligible or any(c['id'] in explicit_conflicts for c,_ in eligible):
        reason='Conflicting or pending applicable claims; investigate the retained alternatives. Document date does not choose a winner.'
        alternatives=tuple(i for _,i in eligible+pending)
        count=AHClaim(state='conflicting')
    elif eligible:
        count=eligible[0][1]
        reason=('Equivalent checked sources ' + ', '.join(str(c['id']) for c,_ in eligible)) if len(eligible)>1 else 'Accepted source claim ' + str(eligible[0][0]['id'])
        reason += '; scoped evidence only, not a statement of current availability.'
    else:
        reason='No accepted quantitative evidence; retain reported information for investigation.'
    disputed_tenures={k[2] for k,v in tenure_groups.items() if len(v)>1}
    if disputed_tenures:
        tenures=[replace(t,claim=replace(t.claim,state='conflicting')) if t.name in disputed_tenures else t for t in tenures]
        reason+=' Conflicting tenure quantities retained for investigation: ' + ', '.join(sorted(disputed_tenures)) + '.'
    return AHAssessment(count=count,alternatives=alternatives,tenures=tuple(tenures),
        source_claims=tuple(evidence),selection_reason=reason,
        relationships=tuple({'from':e['claim_id'],'to':e['related_claim_id'],'action':e['action'],'reason':e['reason']} for e in links))


def for_applications(applications, legacy=None, *, phase_label=None):
    if not enabled():
        return legacy
    attached=[a for a in applications if object_session(a) is not None]
    if not attached:
        # Detached inputs cannot silently assert a complete claim inventory.
        raise ClaimError('enabled_claim_reader_requires_attached_applications')
    session=object_session(attached[0])
    if any(object_session(a) is not session for a in attached):
        raise ClaimError('mixed_claim_read_sessions')
    with session.no_autoflush:
        if session.get_bind().dialect.name=='sqlite':
            # In-memory SQLite pools may hand out the SAME DBAPI connection.
            # Preserve the caller's transaction; never close/rollback it via a
            # second wrapper and never flush pending ORM changes.
            conn=session.connection()
            if not conn.connection.driver_connection.in_transaction:
                conn.exec_driver_sql('BEGIN')
            assessment=select_claims(conn,[a.id for a in applications],phase_label=phase_label)
        else:
            with read_snapshot(session.get_bind()) as conn:
                assessment=select_claims(conn,[a.id for a in applications],phase_label=phase_label)
    if assessment is None:
        return legacy
    if legacy:
        assessment=with_legacy(assessment,legacy)
    return assessment
