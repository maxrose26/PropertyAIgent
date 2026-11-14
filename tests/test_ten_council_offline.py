"""Offline ten-council profile inventory, not collection/source qualification."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.pipeline.discovery_contract import COUNCILS
from verification.discovery import campaign_manifest as campaign
from verification.discovery import finite_acceptance as finite
from verification.discovery import ten_council_offline as candidate
from verification.discovery import source_profiles
from verification.discovery.idox_window import WindowConfig


def inventory():
    return candidate.build(datetime(2026, 11, 10, 12, tzinfo=timezone.utc))


def test_nine_existing_profiles_and_all_ten_unknown_live_scopes_are_explicit():
    value=inventory()
    assert value['version']==candidate.VERSION
    assert value['fallback_start']=='2026-09-15'
    assert value['endpoint_date']=='2026-11-10'
    assert value['window_count']==9 and value['scope_count']==90
    assert value['source_shape_count']==81
    assert value['trafford_unqualified_count']==9
    assert value['required_councils']==sorted(candidate.TEN)
    assert all(value[k] is False for k in (
        'source_contracts_qualified','sql_issuer_qualified','collection_authorised',
        'persisted_records_verified','backlog_populated','prospective_coverage_proven'))
    assert candidate.validate(value)==value
    assert len(value['windows'])==9
    assert sum(len(w['original_nine_packages']) for w in value['windows'])==45
    assert value['windows'][-1]['last_day_not_yet_complete'] is True
    for w in value['windows']:
        assert len(w['profiles'])==10
        assert {x['row']['council'] for x in w['profiles']}==candidate.TEN
        old=finite.manifest(w['start'],w['end'],'SUSPENSION_CATCHUP')
        assert w['original_nine_manifest_sha256']==finite.digest(old)
        nine={x['row']['council']:x for x in w['profiles'] if x['profile'] is not None}
        assert set(nine)==COUNCILS
        for row in old['rows']:
            item=nine[row['council']]
            assert item['row']==row and item['profile']==source_profiles.profile(row,'SCREENING_METADATA')
            assert item['source_contract_qualified'] is False
        t=next(x for x in w['profiles'] if x['row']['council']=='trafford')
        assert t['profile'] is None and t['row']['semantics']=='UNKNOWN_NOT_QUALIFIED'
        assert t['host_hint']=='pa.trafford.gov.uk'
        assert t['state']=='TRAFFORD_PARSER_HINT_ONLY'
        assert 'OFFICIAL_DATE_BASIS' in t['missing_evidence']
        assert t['sql_issuer_qualified'] is False


def test_trafford_can_parse_synthetic_but_cannot_enter_existing_live_caller():
    from app.scrapers.discovery_idox import parse_page, ListingError
    from tests.test_discovery_idox_listing import page
    from datetime import date
    day=date(2026,9,28)
    a=parse_page(page(refs=('TRA/26/001','TRA/26/002')),'trafford',1,day,day)
    assert len(a.rows)==2 and a.terminal=='EXPLICIT_LAST_EQUALS_TOTAL'
    with pytest.raises(ListingError):
        parse_page(page().replace(b'keyVal=K0',b'https://evil.invalid/'), 'trafford',1,day,day)
    with pytest.raises(ValueError,match='TRAFFORD_SOURCE_NOT_QUALIFIED'):
        WindowConfig('trafford')
    with pytest.raises(ValueError):
        source_profiles.profile(dict(council='trafford',start='2026-09-15',end='2026-09-21',semantics='RECEIVED'),'SCREENING_METADATA')


@pytest.mark.parametrize('mutate',[
    lambda v:v.update(source_contracts_qualified=True),
    lambda v:v.update(backlog_populated=True),
    lambda v:v['windows'][0]['profiles'][0]['row'].update(end='2026-09-22'),
    lambda v:v['windows'][0]['profiles'][-1].update(source_contract_qualified=True),
    lambda v:v['windows'][0].update(original_nine_manifest_sha256='0'*64),
    lambda v:v['windows'][0]['original_nine_packages'].clear(),
    lambda v:v.update(endpoint_date='2026-11-11'),
    lambda v:v.update(scope_count=81),
])
def test_inventory_rejects_substitution_and_false_source_or_persistence_claims(mutate):
    changed=deepcopy(inventory());mutate(changed)
    with pytest.raises(ValueError,match='TEN_COUNCIL_INVENTORY_UNVERIFIED'):
        candidate.validate(changed)


def test_as_of_date_cannot_be_guessed_or_pulled_from_a_running_manifest():
    with pytest.raises(ValueError,match='TEN_COUNCIL_AWARE_CLOCK'):
        candidate.build(datetime(2026,11,10,12))
    morning=inventory()
    tomorrow=candidate.build(datetime(2026,11,11,12,tzinfo=timezone.utc))
    assert morning['endpoint_date']=='2026-11-10'
    assert tomorrow['endpoint_date']=='2026-11-11'
    assert morning['window_count']==tomorrow['window_count']==9
    assert morning['windows'][-1]['end']=='2026-11-10'
    assert tomorrow['windows'][-1]['end']=='2026-11-11'
    assert candidate.validate(morning)==morning
    assert candidate.validate(tomorrow)==tomorrow
