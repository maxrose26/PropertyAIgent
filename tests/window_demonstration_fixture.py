"""A synthetic Bolton RECEIVED 2026-09-28 to 2026-10-04 window: 22 references over three pages (10, 10, 2) with an explicit `Showing a-b of 22` pager on every page, produced by the REAL window runner over injected
responses (no network). It mirrors the shape retained from the 14 October observation (22 references, three pages). Used by the disposable rehearsals only."""
import re
from datetime import date
from bs4 import BeautifulSoup
from verification.discovery.idox_window import WindowConfig,run
from tests.test_discovery_idox_window import FORM,Response,page


def weekly_window():
    cfg=WindowConfig('bolton','RECEIVED',date(2026,9,28),date(2026,10,4),0);pages=[]
    proposals=('Erection of 20 residential dwellings','Discharge of conditions pursuant to 02000/26','Replacement guttering to existing dwelling')
    for n,(first,last) in enumerate(((1,10),(11,20),(21,22))):
        refs=tuple(f'{2000+first+i:05d}/26' for i in range(last-first+1))
        body=page(first=first,last=last,total=22,refs=refs,next_page=n+2 if n<2 else None)
        body=re.sub(rb'keyVal=K(\d+)',lambda m,n=n:b'keyVal=K'+str(n*10+int(m[1])).encode(),body)      # received dates stay 'Mon 28 Sep 2026', inside the window
        soup=BeautifulSoup(body,'html.parser')
        for i,a in enumerate(soup.select('a.summaryLink')):a.string=proposals[(n*10+i)%3]
        pages.append(str(soup).encode())
    echo=FORM.replace(b'name="date(applicationReceivedStart)" value=""',b'name="date(applicationReceivedStart)" value="28/09/2026"').replace(b'name="date(applicationReceivedEnd)" value=""',b'name="date(applicationReceivedEnd)" value="04/10/2026"')
    bodies=iter([FORM,pages[0],*pages,echo]);calls=[]
    def dispatch(*a,**kw):calls.append(1);return Response(next(bodies))
    audit=run(dispatch,cfg)
    assert len(calls)==6 and audit['enumeration_evidence']=='COUNT_RECONCILED' and audit['unique_references']==22      # form, search, sort, page 2, page 3, criteria echo: six of the ten allowed
    return cfg,audit
