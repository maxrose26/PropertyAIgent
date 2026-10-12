"""Offline tests of retained qualification evidence, never source acquisition."""
import hashlib
import json
from pathlib import Path
import socket
import pytest
from verification.da0.contracts import GATES, VERSION, validate_registry, eligible, Snapshot, snapshot_diff

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/design/wigan-entry-preflight/EVIDENCE.json'


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('qualification CI must not query a source')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)
    monkeypatch.setattr(socket, 'getaddrinfo', denied)


def load():
    return json.loads(EVIDENCE.read_text())


def test_bound_to_accepted_registry_no_source_substitution():
    e=load(); registry=json.loads((ROOT/'verification/da0/registry_fixtures.json').read_text())['records']
    indexed={r['source_id']:validate_registry(r) for r in registry}
    assert e['binding_contract_version']==VERSION
    assert {s['source_id'] for s in e['sources']}=={'wigan-2021-2030','wigan-2025','wigan-2026'}
    for source in e['sources']:
        r=indexed[source['source_id']]
        assert source['catalogue_url'] in r['admission']['exact_urls']
        assert r['council']=='wigan'
        assert not eligible(r,'wigan',r['fact_domain'],e['proposed_capability'])


def test_missing_proof_cannot_be_pass_or_no_go():
    e=load()
    assert set(e['gates'])==GATES and set(e['gates'].values())=={'UNKNOWN'}
    assert e['decision']=='BLOCKED' and e['operational'] is False and e['execution_authority'] is None
    assert not e['complete_capture_obtained'] and not e['counts_obtained'] and not e['schema_obtained']
    assert e['rights_state']=='RIGHTS_UNRESOLVED' and e['change_capability']=='UNKNOWN'


def test_complete_retained_control_sample_not_false_not_found():
    e=load(); rows=e['cross_checks']
    assert len(rows)==19==len({r['application_id'] for r in rows})==len({r['reference'] for r in rows})
    assert rows==sorted(rows,key=lambda r:r['reference'])
    assert all(r['result']=='UNTESTED' and set(r['field_availability'].values())=={'UNTESTED'} for r in rows)
    assert e['cross_check_counts']==dict(FOUND_EXACT=0,NOT_FOUND=0,AMBIGUOUS=0,FORMAT_DIFFERENCE=0,UNTESTED=19)
    assert e['manifest_sample_provenance']['qualification']=='QUALIFIED_RETAINED_BASIS'
    assert len(e['manifest_sample_provenance']['sha256'])==64
    assert e['manifest_sample_provenance']['code_commit']=='371acef3e2a075d8fb7a8579540f87f5dc72c985'
    assert next(r for r in rows if r['application_id']==721)['reference']=='A/20/88859/RMMAJ'


@pytest.mark.parametrize('field',['KEYVAL','DECSN','DATEDECISN','APPLDECTYP','DATEAPPDEC','status','record_modified_at'])
def test_field_names_and_blank_history_do_not_establish_semantics(field):
    assert load()['field_semantics'][field]=='UNKNOWN'


def test_no_raw_private_or_source_values_exported():
    e=load()
    expected={'application_id','site_id','reference','council','result','qualification','field_availability'}
    assert all(set(r)==expected for r in e['cross_checks'])
    for prohibited in ['source_status_raw','source_decision_raw','proposal_raw','applicant','cookies','DATABASE_URL']:
        assert '"'+prohibited+'"' not in EVIDENCE.read_text()
    assert json.loads(json.dumps(e,sort_keys=True,separators=(',',':')))==e


def test_failed_metadata_attempt_has_no_invented_http_status():
    row=next(r for r in load()['observations'] if r['id']=='R9')
    assert row['result']=='URL_ERROR' and 'http_status' not in row
    assert row['configured_timeout_seconds']==5 and row['redirects_followed']==row['retries']==0


def test_partial_source_cannot_establish_removal():
    partial=Snapshot('wigan-2026','annual-2026','unknown','unimplemented','research',(),False,False,None)
    with pytest.raises(ValueError,match='partial snapshot'):
        snapshot_diff(partial,partial)


def test_salford_is_separate_unexecuted_qualification_only():
    fallback=load()['salford_fallback']
    assert fallback['source_id']=='salford-historical-csv'
    assert fallback['new_live_research'] is False
    assert fallback['recommendation']=='NEXT_BOUNDED_QUALIFICATION_NOT_IMPLEMENTATION'
