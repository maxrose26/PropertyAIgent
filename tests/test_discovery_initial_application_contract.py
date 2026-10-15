"""Retained evidence reassessment and explicitly SYNTHETIC offline transport tests.

No live source compatibility, Bolton initial-status acceptance or production proof.
"""
import copy,json
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from app.db.models import Application
from verification.direct_reference.fixtures import Session,summary
from verification.discovery import material_qualification as q
from verification.discovery.rejection_audit import observation_audit
from verification.discovery.r0_fixed80_qualification import targets
from tests.test_discovery_admission import engine


def projected(body):
    row=targets()[0];transport=Session(body)
    with patch('verification.direct_reference.refresh.requests_session',lambda:transport),\
      patch('verification.direct_reference.batch_supervisor.resource_limits',lambda:None):
        raw=q.idox_worker(row)
    assert transport.closed and all(x.closed for x in transport.responses)
    raw.update(process_cleanup='CLOSED',live_owned_survivors=0,peak_owned_rss=100,
               owned_processes_seen=1,supervisor_seconds=1,supervisor_limit_hit=False)
    return row,raw,q.project_idox(row,raw)


def test_retained42_cannot_be_promoted_offline_under_accepted_contract():
    path=Path('docs/design/stage4-r0-execution/initial-application-preparation/retained42-offline-assessment.json')
    # Minimized retained observations, not reconstructed source HTML.
    rows=json.loads(path.read_bytes())['rows']
    assert len(rows)==42
    for row in rows:
        e=row['observation_evidence']
        assert e['identity_qualification']=='EXACT_DISPLAYED_REFERENCE'
        assert e['supported_literal_facts']['Status']=='Deposited' and e['verification_scope']=='COUPLED'
        assert e['field_states']['decision']==e['field_states']['decision_date']=='NOT_PRESENT'
        assert e['b2_eligible'] is False


@pytest.mark.parametrize('status',['Deposited','Awaiting decision','Unknown synthetic status'])
def test_real_idox_worker_projector_audit_preserves_unaccepted_initial_status(status):
    body=summary(targets()[0]['reference'],status=status,omit=('Decision','Decision Issued Date'))
    row,raw,resource=projected(body);obs=resource['observation'];audit=observation_audit(row,resource)
    assert resource['failure'] is None and obs.literal_verified and obs.verification_scope=='COUPLED'
    assert not obs.b2_eligible and not audit['b2_eligible']
    assert audit['supported_literal_facts']['Status']==status
    assert audit['field_states']['decision']==audit['field_states']['decision_date']=='NOT_PRESENT'
    assert audit['rejection_reason']=='B2_EVIDENCE_SCOPE_INELIGIBLE'
    # Relabelling/setting eligible is not a supported Idox path.
    changed=copy.deepcopy(raw);changed['observation'].update(verification_scope='INITIAL_STATUS_ONLY',b2_eligible=True)
    assert q.project_idox(row,changed)['failure']=='INVALID_ARTIFACT'


@pytest.mark.parametrize('kind',['wrong','missing','conflicting','malformed'])
def test_idox_invalid_identity_status_and_parser_diagnostics_fail_closed(kind):
    ref=targets()[0]['reference'];body=summary(ref,status='Deposited',omit=('Decision','Decision Issued Date'))
    if kind=='wrong':body=summary('WRONG',status='Deposited')
    elif kind=='missing':body=summary(ref,status='Deposited',omit=('Status',))
    elif kind=='conflicting':body=body.replace(b'</table>',b'<tr><th>Status</th><td>Different synthetic status</td></tr></table>')
    else:body=b'<html><table id="simpleDetailsTable"><tr><th>Reference</th><td>truncated'
    row,raw,r=projected(body)
    assert r['failure'] or not r['observation'].b2_eligible
    if raw['failure']:
        d=raw['failure_diagnostic'];assert d['stage'] in {'SUMMARY_PARSE','EXACT_REFERENCE','OBSERVATION'}
        assert d['body_bytes']==len(body) and '<html>' not in str(d) and 'Deposited' not in str(d)
        assert d==r['audit']['failure_diagnostic']


def test_supported_arcus_projector_audit_shared_admission_readback(engine):
    from verification.discovery.committee_exact import targets as arcus_targets,_run_cohort
    from verification.direct_reference.arcus_adapter import _from_observed_row
    from tests.test_discovery_committee_exact import seed
    seed(engine);row=next(r for r in arcus_targets() if r['reference']=='145583/FO/2026')
    def source(r,app_id):
        states={'reference':{'state':'PRESENT_VALUE','value':r['reference']},
                'status':{'state':'PRESENT_VALUE','value':'Under Consideration'},
                'decision':{'state':'CONFLICTING','value':None},'decision_date':{'state':'NOT_PRESENT','value':None}}
        probe=dict(outcome='GUEST_JSON_OBSERVED',attempted=True,http_status=200,received_bytes=100,
             exact_record_id_present=True,exact_reference_value_present=True,other_record_identity_count=0,
             record_identity_sources=1,response_sha256='a'*64,record_field_states=states)
        obs=_from_observed_row(dict(r,application_id=app_id),probe,initial_status=True)
        resource=dict(observation=obs,failure=None,audit=dict(cleanup_state='CLOSED',budget_state='WITHIN_LIMITS'))
        audit=observation_audit(r,resource);assert audit['b2_eligible'] and audit['verification_scope']=='INITIAL_STATUS_ONLY'
        return resource
    result=_run_cohort(engine,'SYNTHETIC-OFFLINE',[row],source)
    assert result[0]['verification_scope']=='INITIAL_STATUS_ONLY'
    with DBSession(engine) as session:
        app=session.scalar(select(Application).where(Application.reference==row['reference']))
        assert app.status=='Under Consideration' and app.decision is None and app.status_verified_at is None
        meta=json.loads(app.planning_field_verification)
        assert meta['status']['verified_at'] and meta['decision']['state']=='CONFLICTING'
        assert meta['decision']['verified_at'] is meta['decision_date']['verified_at'] is None
        app.status='RETAINED_CHANGED_STATUS';session.commit()
    again=_run_cohort(engine,'SYNTHETIC-AGAIN',[row],lambda *_:pytest.fail('already known must not fetch/reset'))
    assert again[0]['admission']['outcome']=='ALREADY_KNOWN'
    with DBSession(engine) as session:assert session.scalar(select(Application)).status=='RETAINED_CHANGED_STATUS'


def test_unaccepted_idox_literal_cannot_enter_initial_b2_by_relabel(engine):
    from verification.discovery.committee_exact import _run_cohort
    row=targets()[0];row=dict(row,trigger_url='https://bolton.moderngov.co.uk/ieListDocuments.aspx?MId=SYNTHETIC',trigger_sha256='b'*64,portal_evidence_fingerprint='a'*64)
    def source(r,app_id):
        _,_,resource=projected(summary(r['reference'],status='Deposited',omit=('Decision','Decision Issued Date')))
        obs=resource['observation'];obs.application_id=app_id
        # Explicit adversarial mutation: B2 must still reject council/route/literal.
        obs.verification_scope='INITIAL_STATUS_ONLY';obs.b2_eligible=True
        obs.field_evidence={k:{'state':v,'value':obs.literal_fields.get({'reference':'Reference','status':'Status','decision':'Decision','decision_date':'Decision Issued Date'}[k])} for k,v in obs.field_states.items()}
        return resource
    result=_run_cohort(engine,'SYNTHETIC-REJECT',[row],source)
    assert result[0]['planning_observation']!='FIELD_LEVEL_VERIFIED'
    with DBSession(engine) as session:
        app=session.scalar(select(Application));assert app.status is app.decision is app.planning_field_verification is None
        assert app.site_id is None


def test_window_sort_failure_shape_is_bounded_and_never_completes():
    from tests.test_discovery_idox_window import perform
    from verification.bolton_recon.fixtures import FORM
    out,calls=perform([FORM,b'<html><form><input name="secret" value="DO_NOT_EXPORT"></form></html>'])
    assert len(calls)==2 and out['failure']=='ListingError:sort selector' and out['completeness']=='FAILED'
    d=out['failure_diagnostic'];assert d['code']=='SORT_SELECTOR_COUNT' and d['stage']=='SORT_FORM_PARSE'
    assert d['counts']['order_by_selects']==0 and 'DO_NOT_EXPORT' not in str(out)


def test_diagnostic_schema_rejects_raw_or_arbitrary_exception_values():
    from verification.discovery.source_diagnostics import shape,validate
    d=shape(b'<html>secret</html>','SUMMARY_PARSE','PARSER_FAILURE');assert validate(d)==d
    for change in [{'raw_html':'secret'},{'stage':'secret'},{'code':'password=secret'}]:
        with pytest.raises(ValueError):validate(dict(d,**change))


def test_remaining_manifests_are_disjoint_and_no_replay_is_authorised():
    p=Path('docs/design/stage4-r0-execution/initial-application-preparation')
    read=lambda name:json.loads((p/name).read_bytes())
    old=targets();original={(x['council'],x['reference']) for x in old}
    groups=[read(x)['rows'] for x in ['retained42-offline-assessment.json','failed-bolton-one.json','qualification-unattempted37.json']]
    identities=[{(x['council'],x['reference']) for x in g} for g in groups]
    assert [len(x) for x in identities]==[42,1,37]
    assert set.union(*identities)==original and all(not identities[i]&identities[j] for i,j in [(0,1),(0,2),(1,2)])
    twenty=read('primary-unattempted20.json');rows=twenty['rows']
    old27=json.loads(Path('docs/design/stage4-r0-execution/page-cap-correction/untouched27-manifest.json').read_bytes())['rows']
    assert rows==old27[7:] and len(rows)==20
    assert {r['council'] for r in rows}=={'rochdale','salford','stockport','tameside','wigan'}
    for file in p.glob('*.json'):
        value=json.loads(file.read_bytes())
        assert value['execution_authorised'] is value['registered'] is value['persistence'] is False
    caps=read('capped-manchester-three.json');assert len(caps['rows'])==3 and len(caps['proposed_partitions'])==6
    assert caps['per_call_cap_unchanged'] and caps['partition_completeness']=='UNPROVEN'
    assert read('preserved-comparison-proposal.json')['uncertain_date_references_added']==0


def test_arbitrary_exception_is_not_exported_in_window_diagnostic():
    from verification.discovery.idox_window import run,WindowConfig
    from verification.bolton_recon.recon import Failure
    from tests.test_discovery_idox_window import Response
    with patch.object(WindowConfig,'payload',side_effect=Failure('SYNTHETIC_REJECTION','SECRET_PRIVATE_URL_AND_TOKEN')):
        result=run(lambda *a,**k:Response(b'<html></html>'))
    assert result['failure']=='Failure:SOURCE_CONTRACT_REJECTED'
    assert 'SECRET' not in str(result) and result['completeness']=='FAILED'


def test_failed_request_does_not_report_previous_response_as_failure_body():
    from tests.test_discovery_idox_window import perform,page
    from verification.bolton_recon.fixtures import FORM
    # Synthetic third response absent: fail inside SORT_REQUEST, before any new
    # response is returned. Earlier valid response content must not be mislabelled.
    out,calls=perform([FORM,page()])
    assert len(calls)==3 and out['failure']=='UNCLASSIFIED_FAILURE'
    d=out['failure_diagnostic']
    assert d['stage']=='SORT_REQUEST' and d['body_bytes']==0 and d['shape_available'] is False
    assert out['completeness']=='FAILED'
