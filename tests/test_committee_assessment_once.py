from datetime import date
from verification.committee_assessment_once import refs,normalize,meeting_date,role,signals,START,END,assess


def test_frozen_dates_and_literal_reference_comparison():
    assert (START,END)==(date(2025,10,14),date(2026,10,14))
    assert meeting_date('14 Oct 2025 2.00 pm')==START
    assert normalize(' pa/2025/1084 ')=='PA/2025/1084'
    assert refs('143413/FO/2025 and 143413/FO/2025','manchester')==['143413/FO/2025']
    assert refs('Address73718 and budget72542','bury')==[]
    assert refs('App No. 72542','bury')==['72542']


def test_document_types_do_not_collapse_recommendation_and_outcome():
    assert role('Supplementary Planning Information')=='SUPPLEMENTARY_UPDATE'
    assert role('Printed draft minutes')=='COMMITTEE_MINUTES'
    assert role('Agenda reports pack')=='AGENDA_PACK'
    assert role('Planning Applications')=='OFFICER_REPORT'
    assert role('Delegated Decisions')=='DELEGATED_DECISION_LIST'
    assert role('Site plan')=='OTHER_ATTACHMENT'
    assert role('Item01')=='UNKNOWN_DOCUMENT_TYPE'
    assert signals('Recommendation: Approve','OFFICER_REPORT')[0]['classification']=='RECOMMEND_APPROVAL'
    assert signals('Recommendation: Approve','COMMITTEE_MINUTES')==[]


def test_boundary_filtering_cancellation_and_gap_are_explicit():
    index='''<html><h2>Planning Committee</h2><a href="ieListDocuments.aspx?MId=1">13 Oct 2025 2.00 pm</a><a href="ieListDocuments.aspx?MId=2">14 Oct 2025 2.00 pm</a><li><a href="ieListDocuments.aspx?MId=3">1 Nov 2025 2.00 pm</a> CANCELLED</li><a href="ieListDocuments.aspx?MId=4">14 Oct 2026 2.00 pm</a></html>'''
    class Reader:
        def get(self,url,council,pdf=False):
            if 'ieListMeetings' in url:return index,{'sha256':'fixture'}
            raise ValueError('fixture inaccessible')
    checkpoints=[];d=assess(Reader(),'bury',lambda d:checkpoints.append(len(d['meetings'])))
    assert len(d['meetings'])==2 and [r['date'] for r in d['meetings']]==['2025-10-14','2025-11-01']
    assert d['meetings'][0]['inspection']=='ACCESS_GAP'
    assert d['meetings'][1]['inspection']=='EXCLUDED_CANCELLED_OR_TRAINING'
    assert d['coverage']=='INCOMPLETE' and checkpoints
    assert d['future_meetings'][0]['date']=='2026-10-14'


def test_non_final_mentions_and_output_link_bounds(tmp_path):
    import pytest
    from bs4 import BeautifulSoup
    from verification.committee_assessment_once import source_links,bounded_checkpoint,MAX_LINKS,MAX_COUNCIL_OUTPUT
    assert signals('minded to approve','COMMITTEE_MINUTES')[0]['classification']=='MINDED_TO_APPROVE_MENTION_NON_FINAL'
    with pytest.raises(ValueError,match='link cap'):
        source_links(BeautifulSoup('<a href="x">x</a>'*(MAX_LINKS+1),'html.parser'),'https://example.invalid/')
    path=tmp_path/'checkpoint.json';path.write_text('preserved')
    with pytest.raises(ValueError,match='output cap'):
        bounded_checkpoint(path,{'data':'x'*MAX_COUNCIL_OUTPUT})
    assert path.read_text()=='preserved'
