"""Synthetic structural regressions; not reconstructed live HTML."""
from datetime import date
import pytest
from tests.e2e_connection_support import idox_audit,idox_contract,entry,SCHEME,outer,_idox_page
from app.ingestion.ledger import Denied
from app.ingestion.ledger import DEFAULT_LIMITS
from app.scrapers.discovery_idox import parse_page,ListingError
START=date(2026,11,3);END=date(2026,11,5)
def rows(n):return [entry(f'B/{i}/26',SCHEME) for i in range(n)]
@pytest.mark.parametrize('count',[7,24])
def test_real_reader_and_capture_validator_require_explicit_total_and_terminal(count):
 audit=idox_audit('bolton',rows(count),START,END)
 receipt=idox_contract('bolton',START,END).project(audit,outer(),DEFAULT_LIMITS)
 assert len(receipt['records'])==count and audit['enumeration_evidence']=='COUNT_RECONCILED'
def test_seven_rows_without_pager_remain_unknown_and_capture_refuses():
 audit=idox_audit('bolton',rows(7),START,END,single_page_no_pager=True)
 assert audit['enumeration_evidence']=='TOTAL_UNKNOWN' and audit['resource']['requests_attempted']==4
 with pytest.raises(Denied):idox_contract('bolton',START,END).project(audit,outer(),DEFAULT_LIMITS)
@pytest.mark.parametrize('kind',['truncated','conflicting','missing_next'])
def test_ambiguous_and_truncated_responses_refuse(kind):
 body=_idox_page('bolton',rows(7),START,END)
 if kind=='truncated':body=body.replace(b'</html>',b'')
 if kind=='conflicting':body=body.replace(b'</html>',b'<p class="pager">Showing 1-7 of 8</p></html>')
 if kind=='missing_next':body=body.replace(b'of 7',b'of 8')
 with pytest.raises(ListingError):parse_page(body,'bolton',1,START,END)
