"""Pure display and result-bound selection contracts; no policy or data mutation."""
from dataclasses import replace
import pytest
from app.policy.ah_assessment import AHAssessment, AHClaim
from app.reporting.ah_kpi import affordable_count_kpi
from app.ui.explore_selection import selection_widget_key, selected_site_ids


def claim(**changes):
    return replace(AHClaim(value=72, qualifier='exact', state='verified', application_reference='APP/1',
        scope_type='whole_site', scope_label='Whole scheme', document_id='source', passage='72 affordable homes'), **changes)


@pytest.mark.parametrize('changes,expected', [({},'72'),({'value':'72'},'72'),({'value':0},'0'),
    ({'qualifier':'approximate','state':'estimated'},'Approx. 72'),
    ({'qualifier':'at_least','value':None,'lower':70},'70+'),
    ({'qualifier':'range','value':None,'lower':71,'upper':74},'71–74'),
    ({'qualifier':'up_to','value':None,'upper':74},'Up to 74'),
    ({'state':'unknown'},'N/A'),({'scope_type':'unclear'},'N/A'),
    ({'scope_type':'component'},'N/A'),({'qualifier':'more_than'},'N/A'),
    ({'value':None},'N/A'),({'document_id':None},'N/A'),({'application_reference':None},'N/A')])
def test_compact_kpi(changes, expected):
    assert affordable_count_kpi(AHAssessment(count=claim(**changes)))==expected


def test_conflicts_never_show_a_falsely_exact_kpi():
    assert affordable_count_kpi(AHAssessment(count=claim(),alternatives=(claim(value=74),)))=='N/A'


def test_result_identity_reorder_shrink_empty_and_return_invalidate_selection():
    state={};first=selection_widget_key(state,[78,25,32])
    assert selection_widget_key(state,[78,25,32])==first
    reorder=selection_widget_key(state,[25,78,32]);assert reorder!=first
    shrink=selection_widget_key(state,[25]);assert shrink!=reorder
    empty=selection_widget_key(state,[]);assert empty!=shrink
    assert selection_widget_key(state,[78,25,32]) not in (first,reorder,shrink,empty)
    assert selected_site_ids([78,25],[0,1])==[78,25]
    assert selected_site_ids([78,25],[0,2])==[]
    assert selected_site_ids([78,25],[-1])==[]
    assert selected_site_ids([78,25],[True])==[]
    assert selected_site_ids([78,25],['0'])==[]


def test_current_qualified_count_with_separate_history_remains_compact():
    # Historical provenance is not an unresolved current alternative.
    a=AHAssessment(count=claim(), source_claims=({'value':0,'application_reference':'OLDER'},))
    assert affordable_count_kpi(a)=='72'
