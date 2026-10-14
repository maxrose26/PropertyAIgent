"""Observed public result-sort form; tokens stay in memory and out of audit."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from app.scrapers.discovery_idox import ListingError, MAX_BODY


def sort_payload(body, base):
    if not isinstance(body,bytes) or not 0<len(body)<=MAX_BODY: raise ListingError('sort body bound')
    soup=BeautifulSoup(body.decode('utf-8','strict'),'html.parser')
    selects=soup.select('select[name="orderBy"]')
    if len(selects)!=1: raise ListingError('sort selector')
    form=selects[0].find_parent('form')
    if form is None or str(form.get('method','')).lower()!='post': raise ListingError('sort form')
    target=urljoin(base+'/',form.get('action',''))
    if target!=base+'/pagedSearchResults.do': raise ListingError('sort target')
    wanted={'orderBy':'Reference','orderByDirection':'Descending','searchCriteria.resultsPerPage':'10'}
    payload={}
    for c in form.select('input,select,textarea,button'):
        name=c.get('name',''); kind=c.get('type','').lower()
        if c.has_attr('disabled'): raise ListingError('disabled sort control')
        if c.name=='input' and kind=='submit' and not name and c.get('value')=='Go': continue
        if not name or name in payload: raise ListingError('sort duplicate/unnamed')
        if c.name=='select' and name in wanted:
            opts=[x.get('value') for x in c.find_all('option')]
            if opts.count(wanted[name])!=1: raise ListingError('sort option')
            payload[name]=wanted[name]
        elif c.name=='input' and kind=='hidden' and name in {'_csrf','searchCriteria.page','action'}:
            v=c.get('value','')
            if not isinstance(v,str) or len(v)>1024 or any(ord(x)<32 for x in v): raise ListingError('sort hidden bound')
            if name in {'action','searchCriteria.page'} and v!={'action':'order','searchCriteria.page':'1'}[name]:
                raise ListingError('sort operation/page')
            payload[name]=v
        else: raise ListingError('unexpected sort control')
    if set(payload)!=set(wanted)|{'_csrf','searchCriteria.page','action'}: raise ListingError('sort control set')
    return target,payload


def require_reference_sort(body):
    soup=BeautifulSoup(body.decode('utf-8','strict'),'html.parser')
    for name,value in [('orderBy','Reference'),('orderByDirection','Descending')]:
        options=soup.select('select[name="'+name+'"] option[selected]')
        if len(options)!=1 or options[0].get('value')!=value: raise ListingError('sort not retained')
