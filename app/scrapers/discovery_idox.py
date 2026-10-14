"""Pure Idox listing parser. No network, persistence or coverage self-certification.

Observed Bolton shapes are recorded in the discovery design evidence. Other
councils must qualify the same shape before this parser supports admission.
"""
from dataclasses import dataclass, replace
from datetime import date, datetime
import hashlib
import re
from urllib.parse import urljoin, urlsplit, parse_qsl
from bs4 import BeautifulSoup
from app.pipeline.discovery_contract import SOURCE_ROOTS, Literal

IDOX = frozenset({'bolton','bury','oldham','stockport','tameside','wigan'})
MAX_BODY = 500_000
MAX_ROWS = 100


class ListingError(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise ListingError(reason)


def text(el):
    return ' '.join(el.get_text(' ', strip=True).split())


def source_url(council, raw, *, page=None):
    require(council in IDOX, 'council')
    host, prefix = SOURCE_ROOTS[council]
    require(isinstance(raw,str) and len(raw)<=1024 and not re.search(r'[\\\s%]',raw), 'url syntax')
    u = urlsplit(urljoin('https://'+host+prefix,raw))
    require(u.scheme=='https' and u.netloc==host and not u.fragment, 'origin')
    try:
        pairs=parse_qsl(u.query,keep_blank_values=True,strict_parsing=True)
    except ValueError:
        raise ListingError('query') from None
    q=dict(pairs)
    require(len(q)==len(pairs), 'duplicate query')
    if page is None:
        require(u.path==prefix+'applicationDetails.do' and set(q) in ({'keyVal'},{'keyVal','activeTab'})
                and q.get('activeTab','summary')=='summary'
                and re.fullmatch(r'_BURY_DCAPR_[0-9]{1,20}' if council=='bury' else r'[A-Za-z0-9]{1,40}',q.get('keyVal','')), 'detail identity')
        return u.geturl(), q['keyVal']
    require(type(page) is int and page>=2 and u.path==prefix+'pagedSearchResults.do'
            and q=={'action':'page','searchCriteria.page':str(page)}, 'next page')
    return u.geturl()


@dataclass(frozen=True)
class ListingRow:
    reference: str | None
    identity_state: str
    source_key: str
    source_url: str
    fields: dict


@dataclass(frozen=True)
class ListingPage:
    rows: tuple[ListingRow,...]
    first: int | None
    last: int | None
    total: int | None
    next_url: str | None
    page_size: int
    terminal: str | None
    fingerprint: str


def literal(elements, locator):
    values = [text(x) for x in elements]
    if not values: return Literal('NOT_PRESENT',None,locator)
    if len(set(values))!=1: return Literal('CONFLICTING',None,locator)
    v=values[0]
    require(len(v)<=8192,'field bound')
    return Literal('PRESENT_VALUE' if v else 'PRESENT_BLANK',v,locator)


def parse_page(body: bytes, council: str, ordinal: int, start: date, end: date, semantics='RECEIVED'):
    require(council in IDOX and type(ordinal) is int and ordinal>=1, 'page identity')
    require(start<=end and semantics in {'RECEIVED','VALIDATED'}, 'interval')
    require(type(body) is bytes and 0<len(body)<=MAX_BODY, 'body bound')
    try: html=body.decode('utf-8',errors='strict')
    except UnicodeError: raise ListingError('encoding') from None
    require(re.search(r'</html\s*>\s*$',html,re.I), 'truncated document')
    soup=BeautifulSoup(html,'html.parser')
    require(not soup.find('base'), 'base element')
    headings=[text(h) for h in soup.select('h1')]
    require(len(headings)==1 and re.fullmatch(r'Planning\s*[–-]\s*Results for Application Search',headings[0]), 'result heading')
    containers=soup.select('#searchresults')
    require(len(containers)==1, 'result container')
    rawrows=containers[0].find_all('li',recursive=False)
    require(0<len(rawrows)<=MAX_ROWS and all('searchresult' in x.get('class',[]) for x in rawrows), 'result rows')
    sizes=soup.select('select#resultsPerPage option[selected]')
    require(len(sizes)==1 and sizes[0].get('value') in {'5','10','20','50','100'}, 'page size')
    size=int(sizes[0]['value'])
    require(len(rawrows)<=size, 'page overflow')
    rows=[]
    for row in rawrows:
        links=row.select('a[href*="applicationDetails.do"]') if council=='bury' else row.select('a.summaryLink')
        require(len(links)==1, 'record link')
        url,key=source_url(council,links[0].get('href'))
        metas=row.select('p.metaInfo')
        # Source-supported listing label, never URL-derived reference.
        refs=[]
        separator=r'[·|]' if council=='bury' else '·'
        for m in metas:
            refs.extend(re.findall(r'(?:^|'+separator+r')\s*Ref\. No:\s*([^·|]+)',text(m)))
        refs=[r.strip() for r in refs]
        valid=all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/._ -]{0,99}',r) for r in refs)
        state=('MISSING_IDENTITY' if not refs else 'CONFLICTING' if len(set(refs))!=1 else 'PRESENT_VALUE' if valid else 'UNPARSEABLE')
        ref=refs[0] if state=='PRESENT_VALUE' else None
        fields={'proposal':literal(links,'a[href*="applicationDetails.do"]' if council=='bury' else 'a.summaryLink'),'address':literal(row.select('p.address'),'p.address')}
        for label,name in [('Received','received_date'),('Validated','validated_date')]:
            values=[]
            for m in metas: values.extend(re.findall(r'(?:^|'+separator+r')\s*'+label+r':\s*([^·|]+)',text(m)))
            if not values: field=Literal('NOT_PRESENT',None,'p.metaInfo:'+label)
            elif len(set(values))!=1: field=Literal('CONFLICTING',None,'p.metaInfo:'+label)
            else:
                try: d=datetime.strptime(values[0].strip(),'%a %d %b %Y').date()
                except ValueError: field=Literal('UNPARSEABLE',None,'p.metaInfo:'+label)
                else: field=Literal('PRESENT_VALUE',values[0].strip(),'p.metaInfo:'+label)
            fields[name]=field
        relevant=fields['received_date' if semantics=='RECEIVED' else 'validated_date']
        require(relevant.state=='PRESENT_VALUE' and start<=datetime.strptime(relevant.value,'%a %d %b %Y').date()<=end,'result outside/unknown interval')
        rows.append(ListingRow(ref,state,key,url,fields))
    require(len({r.source_key for r in rows})==len(rows),'duplicate source key')
    ref_keys={}
    for r in rows:
        if r.reference is not None: ref_keys.setdefault(r.reference,set()).add(r.source_key)
    rows=[replace(r,reference=None,identity_state='CONFLICTING') if len(ref_keys.get(r.reference,set()))>1 else r for r in rows]
    pagers=soup.select('p.pager')
    markers=[]
    for p in pagers:
        match=re.match(r'Showing\s+(\d+)\s*-\s*(\d+)\s+of\s+(\d+)',text(p))
        require(match is not None,'pager shape')
        markers.append(tuple(map(int,match.groups())))
    require(len(set(markers))<=1,'conflicting page counts')
    nexts={a.get('href') for p in pagers for a in p.select('a.next')}
    require(len(nexts)<=1,'conflicting next')
    next_url=source_url(council,next(iter(nexts)),page=ordinal+1) if nexts else None
    first=last=total=None
    terminal=None
    if markers:
        first,last,total=markers[0]
        require(first==(ordinal-1)*size+1 and last-first+1==len(rows) and last<=total,'page count mismatch')
        require((next_url is not None)==(last<total),'next/count mismatch')
        if last==total: terminal='EXPLICIT_LAST_EQUALS_TOTAL'
    else:
        # A short first page without a total is not independently complete.
        require(ordinal==1 and not next_url,'missing pager')
    return ListingPage(tuple(rows),first,last,total,next_url,size,terminal,hashlib.sha256(body).hexdigest())
