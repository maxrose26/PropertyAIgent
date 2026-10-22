"""Opt-in proof projection for four fixed historical windows. No transport.

The projection is structural, not a source qualification or a stored response.
Hidden values and arbitrary source/exception text never enter its output.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from bs4 import BeautifulSoup
from .source_diagnostics import transport_facts

VERSION = 'FOUR_COUNCIL_STRUCTURAL_PROOF_V1'
TARGETS = frozenset({('bury','RECEIVED','2026-10-08','2026-10-14'),
    ('oldham','RECEIVED','2026-10-08','2026-10-14'),
    ('rochdale','VALIDATED','2026-10-08','2026-10-14'),
    ('tameside','RECEIVED','2026-10-01','2026-10-07')})
OPERATIONS = frozenset({'FORM','SEARCH','SORT','PAGE','REFINE','FORM_REQUEST',
    'SEARCH_REQUEST','SORT_REQUEST','PAGE_REQUEST','REFINE_REQUEST','FORM_PARSE',
    'ZERO_CHECK','SORT_FORM_PARSE','SORT_VERIFY','PAGE_PARSE','CRITERIA_ECHO',
    'CRITERIA','PAGE_MARKER','ROW_LOCATORS','ROW_QUALIFICATION','NEXT_CONTROL'})
MAX_BODY = 500_000
MAX_PROOF = 24 * 1024
MAX_OBSERVATION = 512 * 1024
MAX_EVENTS = 12

class ProofError(ValueError):
    pass

def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def require_scope(council,semantics,start,end):
    scope=(council,semantics,str(start),str(end))
    if scope not in TARGETS:raise ProofError('PROOF_SCOPE_REJECTED')
    return scope

def _count(n):
    if not 0 <= n <= 20000:raise ProofError('PROOF_STRUCTURE_BOUND')
    return n

def _text(node):
    return ' '.join(node.get_text(' ',strip=True).split())

def project(body,scope):
    """Only fixed literals, integers and equality results survive projection."""
    if body is None:return {'availability':'UNAVAILABLE'}
    if type(body) is not bytes:raise ProofError('PROOF_BODY_TYPE')
    if not body:return {'availability':'EMPTY'}
    if len(body)>MAX_BODY or body.count(b'<')>20000:return {'availability':'OVERSIZED'}
    try:html=body.decode('utf-8','strict')
    except UnicodeError:return {'availability':'INVALID_ENCODING'}
    soup=BeautifulSoup(html,'html.parser')
    result={'availability':'PRESENT','document_closed':bool(re.search(r'</html\s*>\s*$',html,re.I)),
        'forms':_count(len(soup.select('form'))),'result_containers':_count(len(soup.select('#searchresults'))),
        'result_rows':_count(len(soup.select('#searchresults > li.searchresult'))),
        'order_by_selects':_count(len(soup.select('select[name="orderBy"]'))),
        'message_boxes':_count(len(soup.select('div.messagebox'))),
        'zero_literal_matches':_count(sum(_text(x)=='No results found.' for x in soup.select('div.messagebox li'))),
        'result_heading_matches':_count(sum(bool(re.fullmatch(r'Planning\s*[–-]\s*Results for Application Search',_text(x))) for x in soup.select('h1'))),
        'pagers':[],'sort_controls':{},'criteria':{}}
    pagers=soup.select('p.pager')
    if len(pagers)>4:raise ProofError('PROOF_PAGER_BOUND')
    for p in pagers:
        marker=re.fullmatch(r'Showing\s+(\d{1,7})\s*-\s*(\d{1,7})\s+of\s+(\d{1,7})(?:\s.*)?',_text(p))
        result['pagers'].append({'count_marker':list(map(int,marker.groups())) if marker else None,
            'next_controls':_count(len(p.select('a.next')))})
    for name,allowed in [('orderBy',{'Reference'}),('orderByDirection',{'Descending'}),
                         ('searchCriteria.resultsPerPage',{'5','10','20','50','100'})]:
        selects=soup.select('select[name="'+name+'"]')
        values=[o.get('value') for s in selects for o in s.select('option[selected]')]
        result['sort_controls'][name]={'controls':_count(len(selects)),
            'selected_count':_count(len(values)),
            'selected':values[0] if len(values)==1 and values[0] in allowed else 'UNKNOWN_OR_OTHER'}
    council,semantics,start,end=scope
    for suffix,expected in [('Start',start),('End',end)]:
        name='date(application'+('Received' if semantics=='RECEIVED' else 'Validated')+suffix+')'
        nodes=soup.select('input[name="'+name+'"]')
        expected=datetime.strptime(expected,'%Y-%m-%d').strftime('%d/%m/%Y')
        result['criteria'][suffix]={'controls':_count(len(nodes)),
            'matches_requested':len(nodes)==1 and nodes[0].get('value')==expected}
    return result

class ProofLog:
    def __init__(self,council,semantics,start,end):
        self.scope=require_scope(council,semantics,start,end)
        self.events=[]
    def add(self,body,operation,*,transport=None):
        if operation not in OPERATIONS or len(self.events)>=MAX_EVENTS:raise ProofError('PROOF_OPERATION_BOUND')
        projection=project(body,self.scope)
        event={'operation':operation,'observed_at':datetime.now(timezone.utc).isoformat(),
            'original_response_sha256':sha(body) if body is not None else None,
            'original_response_availability':'PRESENT' if body is not None else 'UNAVAILABLE',
            'rendered_dom_sha256':None,
            'body_bytes':len(body) if body is not None else None,'sanitised_evidence':projection,
            'sanitised_sha256':sha(encoded(projection)),'projection_version':VERSION,
            'transport':transport_facts(transport,None) if transport is not None else None}
        candidate=self.events+[event]
        if len(encoded(candidate))>MAX_PROOF:raise ProofError('PROOF_OUTPUT_BOUND')
        self.events=candidate
    def add_rendered(self,projection,operation):
        # This is a locator observation, NOT a raw DOM or HTTP response.
        self.add(None,operation)
        self.events[-1].update(sanitised_evidence=projection,sanitised_sha256=sha(encoded(projection)),
            original_response_availability='NOT_CAPTURED_RENDERED_LOCATORS')
        if len(encoded(self.events))>MAX_PROOF:raise ProofError('PROOF_OUTPUT_BOUND')
    def result(self):
        return {'version':VERSION,'scope':list(self.scope),'events':self.events,
            'events_sha256':sha(encoded(self.events)),'complete_response_archive':False}

def write_audit(path,value):
    """Exclusive bounded export. An exception is a stop, never a successful audit.

    No new archive service: the existing caller still publishes the resulting audit.
    A partially written file is removed and cannot be mistaken for a completed receipt.
    """
    if 'retained_proof' in value:validate_audit(value)
    elif not value.get('failure'):raise ProofError('PROOF_MISSING')
    path=Path(path);raw=encoded(value)
    if len(raw)>=MAX_OBSERVATION:raise ProofError('PROOF_OBSERVATION_OUTPUT_BOUND')
    created=False
    try:
        with path.open('xb') as f:
            created=True
            f.write(raw);f.flush()
            import os
            os.fsync(f.fileno())
        if path.read_bytes()!=raw:raise ProofError('PROOF_EXPORT_READBACK')
    except Exception:
        if created:
            try:path.unlink(missing_ok=True)
            except OSError:raise ProofError('PROOF_EXPORT_CLEANUP_UNCERTAIN') from None
        raise ProofError('PROOF_EXPORT_FAILED') from None


def validate_proof(value):
    if not isinstance(value,dict) or set(value)!={'version','scope','events','events_sha256','complete_response_archive'}:raise ProofError('PROOF_SCHEMA')
    if value['version']!=VERSION or value['complete_response_archive'] is not False:raise ProofError('PROOF_SCHEMA')
    require_scope(*value['scope'])
    events=value['events']
    if not isinstance(events,list) or not 1<=len(events)<=MAX_EVENTS or len(encoded(events))>MAX_PROOF or sha(encoded(events))!=value['events_sha256']:raise ProofError('PROOF_EVENTS_BINDING')
    projection_keys={'availability','document_closed','forms','result_containers','result_rows','order_by_selects','message_boxes','zero_literal_matches','result_heading_matches','pagers','sort_controls','criteria'}
    for e in events:
        if set(e)!={'operation','observed_at','original_response_sha256','original_response_availability','rendered_dom_sha256','body_bytes','sanitised_evidence','sanitised_sha256','projection_version','transport'}:raise ProofError('PROOF_EVENT_SCHEMA')
        if e['operation'] not in OPERATIONS or e['projection_version']!=VERSION:raise ProofError('PROOF_EVENT_BINDING')
        try:
            timestamp=datetime.fromisoformat(e['observed_at'])
            if timestamp.tzinfo is None or timestamp.utcoffset()!=timezone.utc.utcoffset(None):raise ValueError
        except (ValueError,TypeError):raise ProofError('PROOF_TIMESTAMP') from None
        for k in ('original_response_sha256','rendered_dom_sha256'):
            if e[k] is not None and (not isinstance(e[k],str) or not re.fullmatch('[0-9a-f]{64}',e[k])):raise ProofError('PROOF_HASH')
        if e['original_response_availability'] not in {'PRESENT','UNAVAILABLE','NOT_CAPTURED_RENDERED_LOCATORS'}:raise ProofError('PROOF_RESPONSE_STATE')
        if (e['original_response_availability']=='PRESENT') != (e['original_response_sha256'] is not None):raise ProofError('PROOF_RESPONSE_BINDING')
        if e['original_response_sha256'] is not None and e['rendered_dom_sha256'] is not None:raise ProofError('PROOF_HASH_KIND')
        if e['body_bytes'] is not None and (type(e['body_bytes']) is not int or not 0<=e['body_bytes']<=20*1024*1024):raise ProofError('PROOF_BODY_BOUND')
        if e['transport'] is not None:
            from .source_diagnostics import validate_transport
            validate_transport(e['transport'])
        p=e['sanitised_evidence']
        if not isinstance(p,dict) or sha(encoded(p))!=e['sanitised_sha256']:raise ProofError('PROOF_SANITISED_HASH')
        if p.get('view')=='PLAYWRIGHT_RENDERED_LOCATORS':
            if value['scope'][0]!='rochdale' or e['original_response_availability']!='NOT_CAPTURED_RENDERED_LOCATORS' or any(e[k] is not None for k in ('original_response_sha256','rendered_dom_sha256','body_bytes')):raise ProofError('PROOF_RENDERED_BINDING')
            if set(p)!={'availability','view','markers','cards','zero_literal_matches','next_controls','criteria','visibility'}:raise ProofError('PROOF_RENDERED_SCHEMA')
            if p['availability'] not in {'PRESENT','PARTIAL','UNAVAILABLE'}:raise ProofError('PROOF_RENDERED_STATE')
            if not isinstance(p['markers'],list) or len(p['markers'])>4:raise ProofError('PROOF_RENDERED_MARKERS')
            for m in p['markers']:
                if m is not None and (not isinstance(m,list) or len(m)!=3 or any(type(n) is not int or not 0<=n<=9999999 for n in m)):raise ProofError('PROOF_RENDERED_MARKERS')
            if set(p['visibility'])!={'markers','zero_literal_matches','next_controls'} or any(not isinstance(v,list) or len(v)>4 or any(x is not None and type(x) is not bool for x in v) for v in p['visibility'].values()):raise ProofError('PROOF_VISIBILITY')
            for k in ('cards','zero_literal_matches','next_controls'):
                if p[k] is not None and (type(p[k]) is not int or not 0<=p[k]<=20000):raise ProofError('PROOF_RENDERED_COUNT')
            allowed={'Valid date from','Valid date to','Location of works','Description','Decision notice was sent date from','Decision notice was sent date to','Ward','Application Status','Application type','Parish','Category'}
            if set(p['criteria'])!=allowed or any(v not in {'MATCH','MISMATCH','ABSENT','AMBIGUOUS','UNAVAILABLE','NOT_ATTEMPTED'} for v in p['criteria'].values()):raise ProofError('PROOF_RENDERED_CRITERIA')
            continue
        if e['original_response_availability']=='NOT_CAPTURED_RENDERED_LOCATORS':raise ProofError('PROOF_RENDERED_BINDING')
        if p.get('availability')!='PRESENT':
            if set(p)!={'availability'} or p['availability'] not in {'EMPTY','UNAVAILABLE','OVERSIZED','INVALID_ENCODING'}:raise ProofError('PROOF_PROJECTION_SCHEMA')
            continue
        if set(p) not in (projection_keys,projection_keys|{'rendered'}):raise ProofError('PROOF_PROJECTION_SCHEMA')
        # Recursively allow only structural keys and fixed literal values. No arbitrary source strings.
        allowed_strings={'PRESENT','UNKNOWN_OR_OTHER','Reference','Descending','5','10','20','50','100'}
        allowed_keys=projection_keys|{'rendered','count_marker','next_controls','controls','selected_count','selected',
            'orderBy','orderByDirection','searchCriteria.resultsPerPage','Start','End','matches_requested',
            'cards','markers','Valid date from','Valid date to','labels','located_controls'}
        def fixed(x):
            if isinstance(x,dict):
                if not set(x)<=allowed_keys:raise ProofError('PROOF_PROJECTION_KEYS')
                for v in x.values():fixed(v)
            elif isinstance(x,list):
                if len(x)>4:raise ProofError('PROOF_PROJECTION_LIST')
                for v in x:fixed(v)
            elif isinstance(x,str):
                if x not in allowed_strings:raise ProofError('PROOF_PROJECTION_VALUE')
            elif x is None or type(x) is bool:pass
            elif type(x) is int and 0<=x<=9_999_999:pass
            else:raise ProofError('PROOF_PROJECTION_VALUE')
        fixed(p)
    return value


async def capture_rochdale(page,config):
    """Bounded existing rendered locators (including shadow DOM), no clicks/network.

    Preserve partial evidence on the 500ms collection deadline. No full DOM/body,
    tokens, arbitrary text, response-hash claim or zero-result qualification.
    """
    import asyncio
    require_scope(config.council,'VALIDATED',config.start,config.end)
    expected={'Valid date from':datetime.strptime(config.start,'%Y-%m-%d').strftime('%d/%m/%Y'),
        'Valid date to':datetime.strptime(config.end,'%Y-%m-%d').strftime('%d/%m/%Y'),
        **{label:'' for label in config.blank_inputs},**{label:'Select an option' for label in config.blank_combos},
        'Category':'Planning Applications'}
    out={'availability':'UNAVAILABLE','view':'PLAYWRIGHT_RENDERED_LOCATORS','markers':[],
        'cards':None,'zero_literal_matches':None,'next_controls':None,
        'criteria':{label:'NOT_ATTEMPTED' for label in expected},'visibility':{'markers':[],'zero_literal_matches':[],'next_controls':[]}}
    async def collect():
        loc=page.locator('p.pr-pagination__results');n=await loc.count()
        if not 0<=n<=4:raise ProofError('PROOF_RENDERED_MARKER_BOUND')
        for i in range(n):
            out['visibility']['markers'].append(await loc.nth(i).is_visible())
            raw=await loc.nth(i).inner_text(timeout=100)
            m=re.fullmatch(r'Showing\s+(\d{1,7})\s+to\s+(\d{1,7})\s+of\s+(\d{1,7})\s+results',' '.join(raw.split())) if len(raw)<=160 else None
            out['markers'].append(list(map(int,m.groups())) if m else None)
        for k,loc in [('cards',page.locator('div[role="list"].slds-box')),
                      ('zero_literal_matches',page.locator('p:text-is("No results found")')),
                      ('next_controls',page.locator('a.pr-pagination__link').filter(has_text='Next'))]:
            out[k]=_count(await loc.count())
            if k!='cards':
                if out[k]>4:raise ProofError('PROOF_VISIBILITY_BOUND')
                for i in range(out[k]):out['visibility'][k].append(await loc.nth(i).is_visible())
        out['availability']='PARTIAL'
        for label,value in expected.items():
            is_input=label in ('Valid date from','Valid date to') or label in config.blank_inputs
            loc=page.get_by_label(label,exact=True) if is_input else page.get_by_role('combobox',name=label,exact=True)
            try:
                n=await loc.count()
                if n==0:out['criteria'][label]='ABSENT';continue
                if n!=1:out['criteria'][label]='AMBIGUOUS';continue
                raw=await loc.input_value(timeout=100) if is_input else await loc.inner_text(timeout=100)
                out['criteria'][label]='MATCH' if raw.strip()==value else 'MISMATCH'
            except Exception:out['criteria'][label]='UNAVAILABLE'
        out['availability']='PRESENT'
    try:await asyncio.wait_for(collect(),timeout=0.5)
    except ProofError:raise
    except Exception:pass
    return out


def validate_audit(value,expected_scope=None):
    p=validate_proof(value['retained_proof'])
    scope=tuple(p['scope'])
    if expected_scope is not None and scope!=tuple(expected_scope):raise ProofError('PROOF_ENCLOSING_SCOPE')
    if 'requested_interval' in value:
        c='rochdale' if value.get('case')=='discovery_rochdale_ui_window' else value.get('council')
        if (c,value.get('date_semantics'),*value['requested_interval'])!=scope:raise ProofError('PROOF_ENCLOSING_SCOPE')
    if 'response_provenance' in value:
        hashes={v.get('body_sha256') for v in value['response_provenance']}
        if any(e['original_response_sha256'] is not None and e['original_response_sha256'] not in hashes for e in p['events']):raise ProofError('PROOF_RESPONSE_PROVENANCE')
    return value
