"""Historical table-text projections/synthetic HTML, not original or live HTML."""
import json
from pathlib import Path
import pytest
from verification.stage26b_l1 import bolton_literal as b
from verification.stage26b_l1.bolton_rehearsal import fixture_html, FixtureResponse

def omitted(case,*labels):
    html=fixture_html(case)
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,'html.parser')
    for row in soup.find_all('tr'):
        if row.th.get_text() in labels:row.decompose()
    return str(soup)

@pytest.mark.parametrize('labels',[(),('Decision',),('Decision Issued Date',),('Decision','Decision Issued Date')])
def test_optional_fields_are_independent(labels):
    facts=b.parse_summary(omitted(b.CASES[0],*labels),b.CASES[0])
    result=b.interpret(b.CASES[0],facts)
    for label in ('Decision','Decision Issued Date'):
        key=b.FIELD_IDS[label]
        assert facts.evidence[key]==('NOT_PRESENT' if label in labels else 'PRESENT_BLANK')
    assert result['semantic_state']=='UNKNOWN_UNMAPPED'
    if labels:
        assert result['semantic_materiality']=='UNKNOWN_REQUIRES_REVIEW'
        assert result['source_retrieval']=='COMPLETE_FOR_STATUS_ONLY'
    else:assert result['source_retrieval']=='COMPLETE_FOR_STATUS_DECISION_DATE'

@pytest.mark.parametrize('label',['Reference','Status'])
def test_mandatory_fields_fail_with_safe_diagnostic(label):
    with pytest.raises(b.BoundaryFailure) as e:b.parse_summary(omitted(b.CASES[0],label),b.CASES[0])
    assert e.value.diagnostics['fields'][b.FIELD_IDS[label]]=={'state':'NOT_PRESENT','occurrences':0}
    assert set(e.value.diagnostics['fields'])==set(b.FIELD_IDS.values())
    assert 'Deposited' not in json.dumps(e.value.diagnostics)

@pytest.mark.parametrize('label',['Reference','Status','Decision','Decision Issued Date'])
def test_conflicts_remain_failure(label):
    html=fixture_html(b.CASES[0]).replace('</table>',f'<tr><th>{label}</th><td>CONFLICT</td></tr></table>')
    with pytest.raises(b.BoundaryFailure) as e:b.parse_summary(html,b.CASES[0])
    assert e.value.outcome=='AMBIGUOUS_SOURCE_RESULT'
    assert e.value.diagnostics['fields'][b.FIELD_IDS[label]]['state']=='CONFLICTING'
    assert 'CONFLICT"' not in json.dumps(e.value.diagnostics)

def test_identical_duplicate_reference_state_and_count():
    c=b.CASES[0]
    html=fixture_html(c).replace('</table>',f'<tr><th>Reference</th><td>{c.reference}</td></tr></table>')
    facts=b.parse_summary(html,c)
    assert facts.diagnostics['fields']['reference']==dict(state='PRESENT_VALUE',occurrences=2)

def test_malformed_date_diagnostic_is_value_free():
    with pytest.raises(b.BoundaryFailure) as e:b.parse_summary(fixture_html(b.CASES[0],date='private-date-text'),b.CASES[0])
    assert e.value.diagnostics['fields']['decision_date']['state']=='UNPARSEABLE'
    assert 'private-date-text' not in json.dumps(e.value.diagnostics)

def test_missing_decision_does_not_certify_granted_or_clear_prior_fact():
    c=b.CASES[1];f=b.parse_summary(omitted(c,'Decision'),c);r=b.interpret(c,f)
    assert r['semantic_state']=='UNKNOWN_UNMAPPED'
    assert r['field_evidence']['decision']=='NOT_PRESENT'
    assert 'decision' not in r['source_fact_change_scope']
    assert r['semantic_materiality']=='UNKNOWN_REQUIRES_REVIEW'

def test_missing_date_blocks_materiality_even_when_new_decision_known():
    c=b.CASES[1]
    html=omitted(c,'Decision Issued Date').replace('Approve subject to conditions','Refused')
    r=b.interpret(c,b.parse_summary(html,c))
    assert r['semantic_state']=='refused' and r['source_fact_change']=='CHANGED'
    assert r['semantic_materiality']=='UNKNOWN_REQUIRES_REVIEW'

def test_unknown_extra_field_never_exported():
    c=b.CASES[0]
    html=omitted(c,'Decision','Decision Issued Date').replace('</table>','<tr><th>SECRET NAME</th><td>PERSON SECRET</td></tr></table>')
    def dispatch(method,url,**kw):return FixtureResponse((html if url==c.url else fixture_html(b.CASES[1])).encode())
    audit=b.run(sha='a'*40,dispatch=dispatch);b.validate(audit)
    assert audit['execution_status']=='COMPLETE'
    assert all(s not in b.encode(audit) for s in (b'SECRET NAME',b'PERSON SECRET'))
    assert audit['results'][0]['source_fact_change_scope']==['status']

def test_retained_minimised_projection():
    data=json.loads(Path('tests/fixtures/bolton-field-evidence.json').read_text())
    assert data['truth']=='RETAINED_HISTORICAL_TABLE_PROJECTION'
    for row,case in zip(data['cases'],b.CASES):
        from html import escape
        html='<html><table id="simpleDetailsTable">'+''.join('<tr><th>'+escape(k)+'</th><td>'+escape(v)+'</td></tr>' for k,v in row['fields'].items())+'</table></html>'
        f=b.parse_summary(html,case);r=b.interpret(case,f)
        assert r['semantic_state']==row['expected_semantic_state']
        if case.application_id==202:
            assert f.evidence['decision']==f.evidence['decision_date']=='NOT_PRESENT'

def test_diagnostic_schema_rejects_arbitrary_value():
    f=b.parse_summary(fixture_html(b.CASES[0]),b.CASES[0])
    f.diagnostics['fields']['status']['value']='SECRET'
    with pytest.raises(ValueError):b.validate_diagnostics(f.diagnostics)
