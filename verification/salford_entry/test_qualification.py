"""Offline retained qualification assertions; not a source client."""
import json
from pathlib import Path
import socket
import pytest
from verification.da0.contracts import VERSION,GATES,validate_registry,eligible,Snapshot,snapshot_diff,FieldEvidence,FieldState

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/'docs/design/salford-entry-preflight/EVIDENCE.json'


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args,**kwargs):raise AssertionError('offline qualification cannot query sources')
    monkeypatch.setattr(socket.socket,'connect',denied)
    monkeypatch.setattr(socket,'create_connection',denied)
    monkeypatch.setattr(socket,'getaddrinfo',denied)


def load():return json.loads(PATH.read_text())


def test_exact_registered_source_and_no_admission():
    e=load();rs=json.loads((ROOT/'verification/da0/registry_fixtures.json').read_text())['records']
    r=validate_registry(next(x for x in rs if x['source_id']==e['source_id']))
    assert e['binding_contract_version']==VERSION and e['catalogue_url'] in r['admission']['exact_urls']
    assert e['source_id']=='salford-historical-csv' and r['council']=='salford'
    assert not eligible(r,'salford',r['fact_domain'],e['proposed_capability'])
    assert e['operational'] is False and e['execution_authority'] is None


def test_inaccessible_file_does_not_prove_historical_only_or_pass():
    e=load();assert e['decision']=='BLOCKED' and e['source_scope']=='UNKNOWN'
    assert e['documented_scope_start']=='2014-04-01'
    assert e['actual_latest_record_date'] is e['actual_earliest_record_date'] is None
    assert set(e['gates'])==GATES and set(e['gates'].values())=={'UNKNOWN'}
    assert not e['header_obtained'] and not e['complete_capture_obtained']
    assert e['file_bytes'] is e['row_count'] is None


@pytest.mark.parametrize('field',['application_reference','application_status','decision','decision_date','source_extract_date','application_type'])
def test_standard_definition_is_not_observed_csv_truth(field):
    f=load()['field_semantics'][field]
    assert f['schema_definition']=='CONFIRMED'
    assert f['source_semantics']=='PARTIALLY_CONFIRMED' and f['current_field_availability']=='UNTESTED'


@pytest.mark.parametrize('field',['record_modified_date','record_created_date','validation_date'])
def test_schema_does_not_manufacture_missing_timestamp(field):
    assert load()['field_semantics'][field]['source_semantics']=='UNKNOWN'


def test_complete_32_control_references_no_false_absence_or_scope_exclusion():
    e=load();rows=e['cross_checks']
    assert len(rows)==32==len({r['application_id'] for r in rows})==len({r['reference'] for r in rows})
    assert rows==sorted(rows,key=lambda r:r['reference'])
    assert all(r['result']=='UNTESTED' and set(r['field_availability'].values())=={'UNTESTED'} for r in rows)
    assert e['cross_check_counts']==dict(FOUND_EXACT=0,NOT_FOUND_WITHIN_PROVED_COMPLETE_SCOPE=0,AMBIGUOUS=0,FORMAT_DIFFERENCE=0,OUTSIDE_DATASET_SCOPE=0,UNTESTED=32)
    assert e['manifest_sample_provenance']['code_commit']=='371acef3e2a075d8fb7a8579540f87f5dc72c985'
    assert e['manifest_sample_provenance']['qualification']=='QUALIFIED_RETAINED_BASIS'
    assert len(e['manifest_sample_provenance']['sha256'])==64
    assert {r['reference'] for r in rows if r['site_id']==179}=={'23/81719/HYBEIA','NOT/2026/0722','PA/2026/0239'}


def test_no_raw_rows_private_values_or_restricted_enrichment():
    e=load();expected={'application_id','site_id','reference','council','result','qualification','field_availability'}
    assert all(set(r)==expected for r in e['cross_checks'])
    for key in ['source_status_raw','source_decision_raw','proposal_raw','applicant','cookies','DATABASE_URL']:
        assert '"'+key+'"' not in PATH.read_text()
    assert 'UPRN' in e['restricted_fields_out_of_scope']
    assert e['rights_state']=='RIGHTS_CONFIRMED_WITH_ATTRIBUTION' and e['gates']['RIGHTS']=='UNKNOWN'


def test_head_failure_does_not_invent_http_status_or_size():
    r=next(x for x in load()['observations'] if x['id']=='S5')
    assert r['result']=='URL_ERROR' and 'http_status' not in r
    assert r['response_body_read'] is False and r['redirects_followed']==r['retries']==0


def test_blank_and_missing_stay_distinct_even_with_documented_schema():
    assert FieldEvidence(FieldState.BLANK,None,'synthetic-field')!=FieldEvidence(FieldState.MISSING,None,'synthetic-field')
    assert set(load()['capability_qualifications'].values())=={'UNPROVED'}
    assert load()['change_mechanism']=='UNKNOWN'


def test_partial_capture_cannot_establish_removals():
    s=Snapshot('salford-historical-csv','unknown','unknown','unimplemented','research',(),False,False,None)
    with pytest.raises(ValueError,match='partial snapshot'):snapshot_diff(s,s)


def test_no_invented_resource_size_or_next_candidate_execution():
    e=load();assert e['resource_envelope_state']=='NOT_QUALIFIED_NO_SIZE_OR_COUNT_EVIDENCE'
    assert e['next_candidate']['source_id']=='manchester-shlaa' and e['next_candidate']['new_research'] is False
    assert e['wigan_comparison_provenance']['new_requests'] is False
    assert json.loads(json.dumps(e,sort_keys=True,separators=(',',':')))==e
