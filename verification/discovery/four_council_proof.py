"""Opt-in proof projection for four fixed historical windows. No transport.

The projection is structural, not a source qualification or a stored response.
Hidden values and arbitrary source/exception text never enter its output.
"""
from datetime import datetime, timezone
from contextlib import contextmanager
from contextvars import ContextVar
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

_manifest_scope=ContextVar('manifest_proof_scope',default=None)
_profile_scope=ContextVar('manifest_collection_profile',default=None)

def current_collection_profile():
    value=_profile_scope.get()
    return dict(value) if value is not None else None


def current_manifest_scope():
    row=_manifest_scope.get()
    return dict(row) if row is not None else None


@contextmanager
def manifest_scope(row, profile=None):
    from .campaign_manifest import require_row
    row=dict(require_row(row,profiled=profile is not None))
    if profile is not None:
        from .source_profiles import validate
        validate(profile,row)
    token=_manifest_scope.set(row)
    profile_token=_profile_scope.set(profile)
    try:
        if profile is None:yield
        else:
            from .source_profiles import selected
            with selected(profile):yield
    finally:
        _profile_scope.reset(profile_token)
        _manifest_scope.reset(token)


def require_scope(council,semantics,start,end):
    scope=(council,semantics,str(start),str(end))
    selected=current_manifest_scope()
    if selected is not None:
        if scope!=tuple(selected[k] for k in ('council','semantics','start','end')):raise ProofError('PROOF_SCOPE_REJECTED')
    elif scope not in TARGETS:raise ProofError('PROOF_SCOPE_REJECTED')
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
            selected=current_collection_profile()
            if (value['scope'][0]!='rochdale' and (selected is None or selected['family']!='ARCUS_UI' or selected['council']!=value['scope'][0])) or e['original_response_availability']!='NOT_CAPTURED_RENDERED_LOCATORS' or any(e[k] is not None for k in ('original_response_sha256','rendered_dom_sha256','body_bytes')):raise ProofError('PROOF_RENDERED_BINDING')
            if set(p)!={'availability','view','markers','cards','zero_literal_matches','next_controls','criteria','visibility'}:raise ProofError('PROOF_RENDERED_SCHEMA')
            if p['availability'] not in {'PRESENT','PARTIAL','UNAVAILABLE'}:raise ProofError('PROOF_RENDERED_STATE')
            if not isinstance(p['markers'],list) or len(p['markers'])>4:raise ProofError('PROOF_RENDERED_MARKERS')
            for m in p['markers']:
                if m is not None and (not isinstance(m,list) or len(m)!=3 or any(type(n) is not int or not 0<=n<=9999999 for n in m)):raise ProofError('PROOF_RENDERED_MARKERS')
            if set(p['visibility'])!={'markers','zero_literal_matches','next_controls'} or any(not isinstance(v,list) or len(v)>4 or any(x is not None and type(x) is not bool for x in v) for v in p['visibility'].values()):raise ProofError('PROOF_VISIBILITY')
            for k in ('cards','zero_literal_matches','next_controls'):
                if p[k] is not None and (type(p[k]) is not int or not 0<=p[k]<=20000):raise ProofError('PROOF_RENDERED_COUNT')
            allowed={'Valid date from','Valid date to','Location of works','Description','Decision notice was sent date from','Decision notice was sent date to','Ward','Application Status','Application type','Parish','Category'}
            if selected is not None:
                from .source_profiles import config
                c=config(selected);allowed={'Valid date from','Valid date to','Category',*c.blank_inputs,*c.blank_combos}
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
        selected=current_collection_profile()
        c=selected['council'] if selected is not None and value.get('case')==selected['case'] else 'rochdale' if value.get('case')=='discovery_rochdale_ui_window' else value.get('council')
        if (c,value.get('date_semantics'),*value['requested_interval'])!=scope:raise ProofError('PROOF_ENCLOSING_SCOPE')
    if 'response_provenance' in value:
        hashes={v.get('body_sha256') for v in value['response_provenance']}
        if any(e['original_response_sha256'] is not None and e['original_response_sha256'] not in hashes for e in p['events']):raise ProofError('PROOF_RESPONSE_PROVENANCE')
    return value


# Opt-in private sidecar for the already-budgeted responses, not a complete
# response archive inside the structural proof or public source JSON.
PRIVATE_BODY_LIMIT = 2_000_000
PRIVATE_SINGLE_LIMIT = 500_000
PRIVATE_INDEX_LIMIT = 16384
PRIVATE_OPERATIONS = frozenset({'FORM','SEARCH','SORT','PAGE','REFINE'})


class PrivateResponseBodies:
    def __init__(self, root):
        import os,stat
        self.root=Path(root);self.used=0;self.failed=False
        self.value=dict(kind='PRIVATE_RESPONSE_BODIES_V1',bytes_kind='REQUESTS_ITER_CONTENT_BEFORE_CHARSET_CONVERSION_NOT_WIRE',
                        limit_bytes=PRIVATE_BODY_LIMIT,state='OPEN',entries=[])
        st=self.root.lstat()
        if self.root.is_symlink() or not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o700:
            raise ProofError('PRIVATE_RESPONSE_UNSAFE_PATH')
        if next(self.root.iterdir(),None) is not None:raise ProofError('PRIVATE_RESPONSE_NEW_DIRECTORY_REQUIRED')
        self._persist(initial=True)

    def _persist(self, *, initial=False):
        import os,stat
        st=self.root.lstat()
        if self.root.is_symlink() or not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o700:raise ProofError('PRIVATE_RESPONSE_UNSAFE_PATH')
        raw=encoded(self.value)
        if len(raw)>PRIVATE_INDEX_LIMIT:raise ProofError('PRIVATE_RESPONSE_INDEX_BOUND')
        name='index.json' if initial else 'index.next'
        fd=os.open(self.root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:
            if f.write(raw)!=len(raw):raise ProofError('PRIVATE_RESPONSE_INDEX_WRITE')
            f.flush();os.fsync(f.fileno())
        if not initial:
            prior=(self.root/'index.json').lstat()
            if not stat.S_ISREG(prior.st_mode) or prior.st_nlink!=1:raise ProofError('PRIVATE_RESPONSE_UNSAFE_PATH')
            os.replace(self.root/name,self.root/'index.json')
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)

    def record(self, operation, sequence, body, *, complete=True):
        """Never changes request/refusal/cleanup behaviour, including on disk error."""
        import os
        if self.failed:return
        try:
            if operation not in PRIVATE_OPERATIONS or type(sequence) is not int or not 1<=sequence<=10 or type(body) is not bytes:
                raise ProofError('PRIVATE_RESPONSE_BINDING')
            if len(self.value['entries'])>=10 or any(e['sequence']>=sequence for e in self.value['entries']):
                raise ProofError('PRIVATE_RESPONSE_BINDING')
            entry=dict(operation=operation,sequence=sequence,observed_bytes=len(body),observed_sha256=sha(body),
                       name=f'{sequence:02d}-{operation}.body',retained_bytes=0,retained_sha256=None,complete=False,status='PLANNED')
            self.value['entries'].append(entry);self._persist()
            if len(body)>PRIVATE_SINGLE_LIMIT:entry['status']='BODY_LIMIT'
            elif self.used+len(body)>PRIVATE_BODY_LIMIT:entry['status']='AGGREGATE_LIMIT'
            else:
                try:
                    fd=os.open(self.root/entry['name'],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'wb') as f:
                        written=f.write(body);f.flush();os.fsync(f.fileno())
                    saved=(self.root/entry['name']).read_bytes()
                    entry.update(retained_bytes=len(saved),retained_sha256=sha(saved))
                    self.used+=len(saved)
                    entry['complete']=complete is True and written==len(body) and saved==body
                    entry['status']='COMPLETE' if entry['complete'] else 'PARTIAL'
                except FileExistsError:entry['status']='UNSAFE_PATH'
                except Exception:
                    entry['status']='WRITE_FAILURE'
                    entry['retained_bytes']=None
                    # Any file left by this exclusive write is unacknowledged,
                    # not a complete original. Never read a pre-existing link.
            if not entry['complete']:self.value['state']='INCOMPLETE'
            self._persist()
            if not entry['complete']:self.failed=True
        except Exception:
            self.failed=True  # durable index stays OPEN/PLANNED; never success

    def finish(self):
        if self.failed:return
        self.value['state']='FINISHED' if all(e['complete'] for e in self.value['entries']) else 'INCOMPLETE'
        try:self._persist()
        except Exception:self.failed=True


def validate_private_responses(root, source=None):
    """Read only, finite, no HTML decoding, log/export or acceptance override."""
    import os,stat
    root=Path(root);st=root.lstat()
    if root.is_symlink() or not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o700:
        raise ProofError('PRIVATE_RESPONSE_UNSAFE_PATH')
    f=root/'index.json';st=f.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o600 or st.st_size>PRIVATE_INDEX_LIMIT:
        raise ProofError('PRIVATE_RESPONSE_UNSAFE_PATH')
    value=json.loads(f.read_bytes())
    if type(value) is not dict or set(value)!={'kind','bytes_kind','limit_bytes','state','entries'} or value.get('bytes_kind')!='REQUESTS_ITER_CONTENT_BEFORE_CHARSET_CONVERSION_NOT_WIRE':raise ProofError('PRIVATE_RESPONSE_BINDING')
    entries=value['entries']
    if value.get('kind')!='PRIVATE_RESPONSE_BODIES_V1' or value.get('limit_bytes')!=PRIVATE_BODY_LIMIT or value.get('state')!='FINISHED' or type(entries) is not list or len(entries)>10:
        raise ProofError('PRIVATE_RESPONSE_RETENTION_INCOMPLETE')
    total=0;last=0;names={'index.json'}
    for e in entries:
        if type(e) is not dict or set(e)!={'operation','sequence','observed_bytes','observed_sha256','name','retained_bytes','retained_sha256','complete','status'}:raise ProofError('PRIVATE_RESPONSE_BINDING')
        if any(type(e[k]) is not int or not 0<=e[k]<=PRIVATE_SINGLE_LIMIT for k in ('observed_bytes','retained_bytes')) or any(type(e[k]) is not str or re.fullmatch('[a-f0-9]{64}',e[k]) is None for k in ('observed_sha256','retained_sha256')):raise ProofError('PRIVATE_RESPONSE_BINDING')
        if type(e['sequence']) is not int or not last<e['sequence']<=10 or e['operation'] not in PRIVATE_OPERATIONS:
            raise ProofError('PRIVATE_RESPONSE_BINDING')
        last=e['sequence'];name=f"{last:02d}-{e['operation']}.body";names.add(name)
        if e['name']!=name or e.get('complete') is not True or e.get('status')!='COMPLETE':raise ProofError('PRIVATE_RESPONSE_RETENTION_INCOMPLETE')
        body=root/name;st=body.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o600 or st.st_size>PRIVATE_SINGLE_LIMIT:
            raise ProofError('PRIVATE_RESPONSE_UNSAFE_PATH')
        raw=body.read_bytes();total+=len(raw)
        if total>PRIVATE_BODY_LIMIT or len(raw)!=e['observed_bytes'] or len(raw)!=e['retained_bytes'] or sha(raw)!=e['observed_sha256'] or sha(raw)!=e['retained_sha256']:
            raise ProofError('PRIVATE_RESPONSE_RETENTION_INCOMPLETE')
    if {f.name for f in root.iterdir()}!=names:raise ProofError('PRIVATE_RESPONSE_UNSAFE_PATH')
    if source is not None:
        resource=source.get('resource',{})
        if type(resource.get('requests_attempted')) is not int or last>resource['requests_attempted'] or type(resource.get('received_bytes')) is not int or total>resource['received_bytes']:raise ProofError('PRIVATE_RESPONSE_PROOF_BINDING')
        previous=0
        for event in source.get('retained_proof',{}).get('events',[]):
            if event['original_response_sha256'] is not None:
                matches=[e for e in entries if e['sequence']>previous and e['operation']==event['operation'] and e['observed_sha256']==event['original_response_sha256'] and e['observed_bytes']==event['body_bytes']]
                if not matches:raise ProofError('PRIVATE_RESPONSE_PROOF_BINDING')
                previous=matches[0]['sequence']
    return value
