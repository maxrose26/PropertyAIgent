"""The window demonstration reuses the EXISTING completeness contract unchanged. Offline, through the real window runner and the real adapter: the observed multi-page shape (22 references over three pages, an explicit
total on every page) is accepted as a complete window; a single page with no total reproduces the 22 October stop exactly; a window beyond the page ceiling stops rather than being accepted; nothing relaxes the ceilings."""
import re
from datetime import date

import pytest
from bs4 import BeautifulSoup

from app.ingestion.batching import batch_plans
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.ledger import DEFAULT_LIMITS,Denied
from verification.discovery.idox_window import WindowConfig,run
from tests.test_discovery_idox_window import FORM,Response,page
from tests.test_discovery_ingestion_ledger import outer
from tests.window_demonstration_fixture import weekly_window


def echo(start,end):
    return FORM.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="%s"'%start).replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="%s"'%end)


def perform(cfg,bodies):
    it=iter(bodies);calls=[]
    def dispatch(*a,**kw):calls.append(1);return Response(next(it))
    return run(dispatch,cfg),calls


def test_the_observed_multi_page_window_is_accepted_by_the_unchanged_contract_within_six_of_ten_requests():
    cfg,audit=weekly_window()
    receipt=IdoxListingContract('controller-idox',cfg,'a'*64).project(audit,outer(),DEFAULT_LIMITS)
    assert receipt['kind']=='LISTING_RECEIPT_V1' and len(receipt['records'])==22 and receipt['window']['terminal_evidence']=='EXPLICIT_LAST_EQUALS_TOTAL'
    assert receipt['applied_interval']==['2026-09-28','2026-10-04'] and audit['resource']['requests_attempted']==6<=10 and audit['resource']['retries']==0 and audit['resource']['redirects']==0
    receipt['durable_archive']={'sha256':'b'*64};receipt.pop('window')
    plans=batch_plans('c'*64,receipt)
    assert len(plans)==5 and [p['checkpoint']['plan']['first'] for p in plans]==[0,5,10,15,20]      # 22 rows in five-row batches, within the twelve allowed


def test_a_single_page_with_no_total_reproduces_the_22_october_stop_exactly():
    cfg=WindowConfig('bolton','RECEIVED',date(2026,9,28),date(2026,10,4),0)
    single=page(first=1,last=4,total=4,refs=('1/26','2/26','3/26','4/26'),pager=False)
    audit,calls=perform(cfg,[FORM,single,single,echo(b'28/09/2026',b'04/10/2026')])
    assert audit['enumeration_evidence']=='TOTAL_UNKNOWN' and audit['unique_references']==4 and audit['pages'][0]['total'] is None and len(calls)==4 and audit['failure'] is None      # four requests, four rows, no total
    with pytest.raises(Denied,match='IDOX_WINDOW_BINDING_OR_COMPLETENESS'):IdoxListingContract('controller-idox',cfg,'a'*64).project(audit,outer(),DEFAULT_LIMITS)      # the contract is NOT relaxed


def test_a_window_beyond_the_page_ceiling_is_not_accepted_and_the_ceiling_is_not_expanded():
    cfg=WindowConfig('bolton','RECEIVED',date(2026,9,28),date(2026,10,4),0);pages=[]
    for n in range(7):
        refs=tuple(f'{3000+n*10+i:05d}/26' for i in range(10))
        body=page(first=n*10+1,last=n*10+10,total=70,refs=refs,next_page=n+2 if n<6 else None)
        body=re.sub(rb'keyVal=K(\d+)',lambda m,n=n:b'keyVal=K'+str(n*10+int(m[1])).encode(),body)
        pages.append(body)
    audit,calls=perform(cfg,[FORM,pages[0],*pages[:6],echo(b'28/09/2026',b'04/10/2026')])
    assert audit['capped'] is True and audit['enumeration_evidence']=='PAGE_CAP' and len(audit['pages'])==6 and len(calls)<=10
    with pytest.raises(Denied,match='IDOX_WINDOW_BINDING_OR_COMPLETENESS'):IdoxListingContract('controller-idox',cfg,'a'*64).project(audit,outer(),DEFAULT_LIMITS)


def test_a_window_of_ten_rows_or_fewer_shows_no_pager_and_stops_rather_than_inferring_completeness():
    cfg=WindowConfig('bolton','RECEIVED',date(2026,9,28),date(2026,10,4),0)
    short=page(first=1,last=10,total=10,refs=tuple(f'{4000+i}/26' for i in range(10)),pager=False)
    audit,_=perform(cfg,[FORM,short,short,echo(b'28/09/2026',b'04/10/2026')])
    assert audit['enumeration_evidence']=='TOTAL_UNKNOWN'
    with pytest.raises(Denied,match='IDOX_WINDOW_BINDING_OR_COMPLETENESS'):IdoxListingContract('controller-idox',cfg,'a'*64).project(audit,outer(),DEFAULT_LIMITS)
