"""Shared bounded Tameside five-page engine; observation and counted wrappers."""
from dataclasses import asdict
import hashlib,json,os,re,stat
from pathlib import Path
from urllib.parse import urlencode,urljoin,urlsplit,parse_qs,parse_qsl
from bs4 import BeautifulSoup
from app.scrapers.discovery_idox import observe_listing_rows,ListingError
from .idox_sort import sort_payload,require_reference_sort
from .four_council_proof import ProofLog,PrivateResponseBodies,encoded,sha,ProofError
from verification.stage26b_l1.request_boundary import BoundaryFailure

MODE='TAMESIDE_FIVE_PER_PAGE_V1'
COUNTED_MODE='TAMESIDE_FIVE_COUNT_V1'
COUNTED_CONTRACT='tameside-screening-metadata-five-v1'
ROW=dict(council='tameside',semantics='RECEIVED',start='2026-10-24',end='2026-10-30')
TRACE_LIMIT=8192
CODES=frozenset('CALIBRATION_SCOPE CALIBRATION_RETENTION_INCOMPLETE CALIBRATION_PAGE_SIZE_IGNORED CALIBRATION_SORT_CHANGED CALIBRATION_PAGE_IDENTITY CALIBRATION_NAVIGATION_AMBIGUOUS CALIBRATION_NAVIGATION_UNSUPPORTED CALIBRATION_NAVIGATION_CONFLICT CALIBRATION_REPEATED_PAGE CALIBRATION_DUPLICATE_IDENTITY CALIBRATION_CONTRADICTORY_COUNTS CALIBRATION_ERROR_RESPONSE CALIBRATION_SESSION_EXPIRED CALIBRATION_UNEXPECTED_MESSAGE CALIBRATION_ROW_LAYOUT_REFUSED CALIBRATION_SEARCH_BINDING CALIBRATION_PAGE_CAP CALIBRATION_ROW_CAP CALIBRATION_REQUEST_CAP CALIBRATION_BYTE_CAP CALIBRATION_DEADLINE CALIBRATION_TRACE_BOUND CALIBRATION_TRACE_IO CALIBRATION_UNKNOWN'.split())

class CalibrationError(ValueError):
    def __init__(self,code,detail=None):
        self.code=code if type(code) is str and code in CODES else 'CALIBRATION_UNKNOWN'
        self.detail=detail
        super().__init__(self.code)

def require(ok,code,detail=None):
    if not ok:raise CalibrationError(code,detail)

def checkpoint(path,value):
    raw=encoded(value);require(len(raw)<=TRACE_LIMIT,'CALIBRATION_TRACE_BOUND')
    try:
        parent=path.parent;st=parent.lstat()
        require(not parent.is_symlink() and stat.S_ISDIR(st.st_mode) and st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o700,'CALIBRATION_TRACE_IO')
        if path.exists() or path.is_symlink():
            st=path.lstat();require(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o600,'CALIBRATION_TRACE_IO')
        temporary=path.with_suffix('.next')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:
            require(f.write(raw)==len(raw),'CALIBRATION_TRACE_IO');f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
        fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
    except CalibrationError:raise
    except Exception:raise CalibrationError('CALIBRATION_TRACE_IO') from None

def safe_controls(fields):
    # This private map records actual submitted controls but never the token.
    out={}
    for k,v in fields.items():
        if k=='_csrf':continue
        require(type(k) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.()]{0,79}',k) is not None and type(v) is str and len(v)<=160,'CALIBRATION_NAVIGATION_UNSUPPORTED')
        out[k]=v
    return out

def disabled(node):
    return any(n.has_attr('disabled') or n.get('aria-disabled')=='true' or 'disabled' in n.get('class',[]) or n.has_attr('hidden') or n.get('aria-hidden')=='true' or bool(re.search(r'display\s*:\s*none',n.get('style',''),re.I)) for n in [node,*node.parents] if getattr(n,'attrs',None) is not None)

def paging_get(href,config,expected):
    """Normalize only a complete, supported returned paging destination.

    Never drop meaningful parameters: duplicate keys, extras, fragments and
    noncanonical encodings refuse. Parameter order alone has no semantics.
    """
    try:
        require(type(href) is str and 0<len(href)<=2048,'CALIBRATION_NAVIGATION_UNSUPPORTED')
        target=urljoin(config.base+'/',href);u=urlsplit(target);base=urlsplit(config.base)
        require(u.scheme=='https' and u.netloc==base.netloc and not u.fragment and '%' not in target and u.path==base.path+'/pagedSearchResults.do','CALIBRATION_NAVIGATION_UNSUPPORTED')
        pairs=parse_qsl(u.query,keep_blank_values=True,strict_parsing=True)
        require(len(pairs)==2 and len({k for k,v in pairs})==2 and dict(pairs)=={'action':'page','searchCriteria.page':str(expected)},'CALIBRATION_NAVIGATION_UNSUPPORTED')
        return config.base+'/pagedSearchResults.do?'+urlencode({'action':'page','searchCriteria.page':str(expected)})
    except CalibrationError:raise
    except Exception:raise CalibrationError('CALIBRATION_NAVIGATION_UNSUPPORTED') from None


def directions(soup,config,current):
    found={'NEXT':[],'PREVIOUS':[],'NUMBERED_NEXT':[]}
    for node in soup.select('a,button,input[type="submit"],input[type="button"],[role="button"],[onclick]'):
        label=' '.join((node.get('value','') if node.name=='input' else node.get_text(' ',strip=True)).split()).casefold()
        aria=node.get('aria-label','').strip().casefold();rel=node.get('rel',[]);classes=node.get('class',[])
        kind='NEXT' if label in ('next','next page','next >','next »','>','»') or aria in ('next','next page') or 'next' in rel or 'next' in classes else 'PREVIOUS' if label in ('previous','prev','previous page','<','«') or aria in ('previous','previous page') or 'prev' in rel or 'previous' in rel or 'prev' in classes or 'previous' in classes else None
        if kind is None:
            if label in ('load more','more results','more applications'):raise CalibrationError('CALIBRATION_NAVIGATION_UNSUPPORTED')
            if node.name=='a' and not disabled(node):
                q=parse_qs(urlsplit(node.get('href','')).query)
                values=q.get('searchCriteria.page',[])
                paging='searchCriteria.page' in q or urlsplit(node.get('href','')).path.endswith('/pagedSearchResults.do') or urlsplit(node.get('href','')).path=='pagedSearchResults.do'
                if paging and label.isdigit() and len(label)<=3 and int(label)>current:
                    require(int(label)==current+1,'CALIBRATION_NAVIGATION_AMBIGUOUS','NUMBERED_LINK_SKIPS_ADJACENT_PAGE')
                    kind='NUMBERED_NEXT'
                elif any(v.isdigit() and (len(v)>3 or int(v)>current) for v in values):
                    raise CalibrationError('CALIBRATION_NAVIGATION_AMBIGUOUS','UNCLASSIFIED_FORWARD_PAGE_LINK')
            if kind is None:continue
        e=dict(kind=kind,element=node.name,disabled=disabled(node),method=None,action_path=None,fields={},page=None)
        if not e['disabled']:
            expected=current+(1 if kind in ('NEXT','NUMBERED_NEXT') else -1)
            require(1<=expected<=7,'CALIBRATION_NAVIGATION_CONFLICT')
            if node.name=='a':
                href=node.get('href');require(type(href) is str and not node.has_attr('onclick'),'CALIBRATION_NAVIGATION_UNSUPPORTED')
                target=paging_get(href,config,expected)
                e.update(method='GET',action_path=urlsplit(target).path,fields={'action':'page','searchCriteria.page':str(expected)},page=expected)
                request=('GET',target,None)
            else:
                require(node.name in ('button','input'),'CALIBRATION_NAVIGATION_UNSUPPORTED')
                form=node.find_parent('form');require(form is not None and form.get('method','').upper()=='POST' and not any(node.has_attr(k) for k in ('onclick','formaction','formmethod','formenctype')),'CALIBRATION_NAVIGATION_UNSUPPORTED')
                target=urljoin(config.base+'/',form.get('action',''))
                require(target==config.base+'/pagedSearchResults.do','CALIBRATION_NAVIGATION_UNSUPPORTED')
                fields={}
                for field in form.select('input,select,textarea,button'):
                    if disabled(field):continue
                    typ=field.get('type','').lower();name=field.get('name','')
                    if field.name in ('button',) or typ in ('submit','button'):
                        if field is not node:continue
                        if not name:continue
                        value=field.get('value','')
                    elif field.name=='input' and typ=='hidden':value=field.get('value','')
                    elif field.name=='select':
                        options=field.select('option[selected]');require(len(options)==1,'CALIBRATION_NAVIGATION_AMBIGUOUS','POST_SELECT_NOT_SINGLE');value=options[0].get('value','')
                    else:raise CalibrationError('CALIBRATION_NAVIGATION_UNSUPPORTED')
                    require(name in {'_csrf','searchCriteria.page','action','orderBy','orderByDirection','searchCriteria.resultsPerPage'} and name not in fields and type(value) is str and len(value)<=1024,'CALIBRATION_NAVIGATION_UNSUPPORTED')
                    fields[name]=value
                require(fields.get('searchCriteria.page')==str(expected) and fields.get('action')=='page' and bool(fields.get('_csrf')),'CALIBRATION_NAVIGATION_CONFLICT')
                for k,v in [('orderBy','Reference'),('orderByDirection','Descending'),('searchCriteria.resultsPerPage','5')]:
                    require(k not in fields or fields[k]==v,'CALIBRATION_SORT_CHANGED')
                e.update(method='POST',action_path=urlsplit(target).path,fields=safe_controls(fields),page=expected)
                request=('POST',target,urlencode(fields).encode())
            found[kind].append((e,request))
        else:found[kind].append((e,None))
    summary={};next_request=None
    for kind,items in found.items():
        active=[x for x in items if not x[0]['disabled']]
        require(not active or len(active)==len(items),'CALIBRATION_NAVIGATION_CONFLICT')
        unique={x[1] for x in active};require(len(unique)<=1,'CALIBRATION_NAVIGATION_AMBIGUOUS','MULTIPLE_DISTINCT_DIRECTION_REQUESTS')
        summary[kind.lower()]=[x[0] for x in items]
        if kind=='NEXT' and active:next_request=active[0][1]
    # A numbered link can corroborate an explicit Next; it never authorises
    # navigation on its own. Reconcile after scanning both top/bottom pagers.
    numbered=[request for evidence,request in found['NUMBERED_NEXT'] if not evidence['disabled']]
    require(not numbered or next_request is not None,'CALIBRATION_NAVIGATION_AMBIGUOUS','NUMBERED_WITHOUT_EXPLICIT_NEXT')
    require(all(request==next_request for request in numbered),'CALIBRATION_NAVIGATION_CONFLICT')
    return summary,next_request

def observe(body,config,ordinal):
    soup=BeautifulSoup(body.decode('utf-8','strict'),'html.parser')
    for node in soup.select('.error,.errors,.errorMessage,.messagebox,.warning,.alert,[role="alert"]'):
        text=' '.join(node.get_text(' ',strip=True).split())
        if not text:continue
        if re.search(r'session\s+(?:has\s+)?expired',text,re.I):raise CalibrationError('CALIBRATION_SESSION_EXPIRED')
        raise CalibrationError('CALIBRATION_ERROR_RESPONSE')
    rows,size,fingerprint=observe_listing_rows(body,config.council,config.start,config.end,config.semantics)
    from app.ingestion.idox_adapter import validate_listing_record
    keys=set();refs=set()
    try:
        for row in rows:validate_listing_record(config,asdict(row),keys,refs)
    except Exception:raise CalibrationError('CALIBRATION_ROW_LAYOUT_REFUSED') from None
    try:require_reference_sort(body);_,controls=sort_payload(body,config.base,calibration_five=True)
    except ListingError:raise CalibrationError('CALIBRATION_SORT_CHANGED') from None
    opts=soup.select('select[name="searchCriteria.resultsPerPage"] option[selected]')
    require(size==5 and len(opts)==1 and opts[0].get('value')=='5','CALIBRATION_PAGE_SIZE_IGNORED')
    # The form submits a future sort operation; its hidden page can reset to1.
    # It is not current-response identity. Keep its operation/shape validation.
    require(controls.get('action')=='page','CALIBRATION_PAGE_IDENTITY')
    nav,next_request=directions(soup,config,ordinal)
    counts=[]
    for node in soup.select('p.pager,.pagination,.paging'):
        text=' '.join(node.get_text(' ',strip=True).split())
        m=re.match(r'Showing\s+(\d+)\s*(?:-|–|to)\s*(\d+)\s+of\s+(\d+)',text,re.I)
        if m:counts.append(tuple(map(int,m.groups())))
    require(len(set(counts))<=1,'CALIBRATION_CONTRADICTORY_COUNTS')
    count=None
    if counts:
        first,last,total=counts[0]
        require(first==(ordinal-1)*5+1 and last-first+1==len(rows) and last<=total,'CALIBRATION_CONTRADICTORY_COUNTS')
        require((next_request is not None)==(last<total),'CALIBRATION_CONTRADICTORY_COUNTS')
        count=dict(first=first,last=last,total=total)
    current_labels=[]
    for n in soup.select('.pager .current,.pagination .current,.paging .current,[aria-current="page"],p.pager > strong'):
        value=n.get_text(' ',strip=True)
        if value.isdigit():current_labels.append(int(value))
    require(not current_labels or set(current_labels)=={ordinal},'CALIBRATION_PAGE_IDENTITY')
    require(count is not None or bool(current_labels),'CALIBRATION_PAGE_IDENTITY')
    identity_basis=(['DISPLAYED_RANGE'] if count is not None else [])+(['CURRENT_PAGE_MARKER'] if current_labels else [])
    sort_page=controls.get('searchCriteria.page','')
    sort_page=sort_page if re.fullmatch(r'[0-9]{1,3}',sort_page) else 'OTHER'

    terminal_labels=[]
    allowed_terminal={'You have reached the last page.':'LAST_PAGE_TEXT','This is the last page.':'LAST_PAGE_TEXT','End of results.':'END_OF_RESULTS_TEXT','No more results.':'NO_MORE_RESULTS_TEXT'}
    for text in soup.find_all(string=True):
        if text.find_parent(['script','style']) or text.find_parent(id='searchresults'):continue
        label=allowed_terminal.get(' '.join(str(text).split()))
        if label is not None:terminal_labels.append(label)
    page=dict(ordinal=ordinal,body_sha256=fingerprint,rows=len(rows),references=[x.reference for x in rows],page_size=size,current_page=ordinal,identity_basis=identity_basis,sort_form_page=sort_page,sort='REFERENCE_DESCENDING',navigation=nav,visible_current_pages=current_labels,explicit_terminal_labels=sorted(set(terminal_labels)),range=count,terminal_candidate=None)
    if next_request is None:
        page['terminal_candidate']='NEXT_DISABLED' if nav['next'] else 'NO_NEXT_CONTROL'
        if count is not None and count['last']==count['total']:page['terminal_candidate']='EXPLICIT_RANGE_LAST_EQUALS_TOTAL'
    return rows,page,next_request

def run_calibration(dispatch,config,*,response_evidence):
    return _run_five_page(dispatch,config,response_evidence=response_evidence,observation_only=True)


def run_counted_window(dispatch,config,*,response_evidence=None):
    from .four_council_proof import current_collection_profile
    p=current_collection_profile()
    require(p is not None and p.get('idox_pagination')==COUNTED_MODE and p.get('page_size')==5 and p.get('collection_mode')=='SCREENING_METADATA','CALIBRATION_SCOPE')
    return _run_five_page(dispatch,config,response_evidence=response_evidence,observation_only=False)


def _run_five_page(dispatch,config,*,response_evidence,observation_only):
    from .idox_window import WindowBoundary
    from verification.bolton_recon.recon import Failure
    require(type(observation_only) is bool and config.council=='tameside' and config.semantics=='RECEIVED' and config.max_transport_retries==0 and config.max_rows==60 and (config.end-config.start).days==6,'CALIBRATION_SCOPE')
    if observation_only:require(str(config.start)=='2026-10-24' and str(config.end)=='2026-10-30','CALIBRATION_SCOPE')
    store=getattr(response_evidence,'__self__',None)
    if observation_only:require(isinstance(store,PrivateResponseBodies),'CALIBRATION_SCOPE')
    progress_path=store.root.parent/'calibration-progress.json' if store is not None else None
    progress=dict(mode=MODE,state='IN_PROGRESS',acceptance_enabled=False,requests=[],pages=[],failure=None,criteria_verified=False)
    proof=ProofLog(config.council,config.semantics,config.start,config.end)
    b=WindowBoundary(dispatch,config,response_evidence=response_evidence,calibration_navigation=True);b.proof_log=proof
    out=dict(council=config.council,requested_interval=[str(config.start),str(config.end)],date_semantics=config.semantics,applied_interval=None,completeness='UNKNOWN',enumeration_evidence='CALIBRATION_OBSERVATION_ONLY',source_qualification='CANDIDATE_CONTRACT',persistence=False,pages=[],records=[],failure=None,capped=False,cleanup='UNKNOWN')
    stage='FORM_REQUEST';keys=set();refs=set();body_hashes=set();total=None
    def save():
        require(len(encoded(progress))<=TRACE_LIMIT,'CALIBRATION_TRACE_BOUND')
        if progress_path is not None:checkpoint(progress_path,progress)
    def fetch(phase,method,target,fields=None):
        b.budget.check();require(b.requests<10,'CALIBRATION_REQUEST_CAP')
        entry=dict(sequence=b.requests+1,operation=phase,method=method,action_path=urlsplit(target).path,fields=safe_controls(fields or {}),response='PENDING')
        if fields is None and method=='GET':entry['fields']={k:v[0] for k,v in parse_qs(urlsplit(target).query).items() if k in ('action','searchCriteria.page') and len(v)==1}
        progress['requests'].append(entry);save()
        b.phase=phase
        payload=urlencode(fields).encode() if fields is not None else None
        if method=='POST':b.admitted_post=target;b.admitted_body=payload
        else:b.next_url=target if phase=='PAGE' else None
        body=b.retrieve(method,target,payload);b.admitted_body=None
        require(store is None or not store.failed,'CALIBRATION_RETENTION_INCOMPLETE')
        entry.update(response='BODY_RETAINED',body_sha256=sha(body),body_bytes=len(body));save()
        return body
    try:
        require(progress_path is None or not progress_path.exists() and not progress_path.is_symlink(),'CALIBRATION_TRACE_IO');save()
        form=fetch('FORM','GET',config.form_url)
        stage='FORM_PARSE';target,fields=config.payload(form)
        stage='SEARCH_REQUEST';search=fetch('SEARCH','POST',target,fields);fields.clear()
        stage='SORT_FORM_PARSE';target,fields=sort_payload(search,config.base,calibration_five=True)
        require(fields.get('searchCriteria.page')=='1' and fields.get('action')=='page','CALIBRATION_PAGE_IDENTITY')
        stage='SORT_REQUEST';body=fetch('SORT','POST',target,fields);fields.clear()
        for ordinal in range(1,7):
            require(sha(body) not in body_hashes,'CALIBRATION_REPEATED_PAGE')
            stage='PAGE_PARSE';rows,page,next_request=observe(body,config,ordinal)
            if not observation_only:require(page['range'] is not None,'CALIBRATION_CONTRADICTORY_COUNTS')
            body_hashes.add(page['body_sha256'])
            for row in rows:
                require(row.source_key not in keys and row.reference not in refs,'CALIBRATION_DUPLICATE_IDENTITY')
                keys.add(row.source_key);refs.add(row.reference)
            require(len(keys)<=60,'CALIBRATION_ROW_CAP')
            if page['range'] is not None:
                require(total is None or total==page['range']['total'],'CALIBRATION_CONTRADICTORY_COUNTS');total=page['range']['total']
            require(total is None or len(keys)<=total,'CALIBRATION_CONTRADICTORY_COUNTS')
            if next_request is None:require(total is None or len(keys)==total,'CALIBRATION_CONTRADICTORY_COUNTS')
            progress['pages'].append(page);out['records'].extend(asdict(x) for x in rows)
            out['pages'].append(dict(ordinal=ordinal,first=page['range']['first'] if page['range'] else None,last=page['range']['last'] if page['range'] else None,total=page['range']['total'] if page['range'] else None,rows=len(rows),page_size=5,body_sha256=page['body_sha256'],terminal=None));save()
            if next_request is None:break
            require(ordinal<6,'CALIBRATION_PAGE_CAP');require(b.requests+2<=10,'CALIBRATION_REQUEST_CAP')
            method,target,payload=next_request
            fields=dict(parse_qs(payload.decode(),keep_blank_values=True)) if payload is not None else None
            if fields is not None:fields={k:v[0] for k,v in fields.items()}
            stage='PAGE_REQUEST';body=fetch('PAGE',method,target,fields)
            if fields is not None:fields.clear()
        if not observation_only:require(progress['pages'][-1]['terminal_candidate']=='EXPLICIT_RANGE_LAST_EQUALS_TOTAL','CALIBRATION_CONTRADICTORY_COUNTS')
        stage='REFINE_REQUEST';echo=fetch('REFINE','GET',config.base+'/refineSearch.do?action=refine')
        stage='CRITERIA_ECHO'
        try:_,fields=config.payload(echo,echo=True);fields.clear()
        except Exception:raise CalibrationError('CALIBRATION_SEARCH_BINDING') from None
        out.update(applied_interval=out['requested_interval'],applied_evidence='STRICT_REFINE_FORM_ECHO',applied_evidence_sha256=sha(echo),criteria_result_binding=dict(method='SAME_SESSION_POST_ENUMERATION_REFINE_NO_RESUBMIT',segment_sha256=[p['body_sha256'] for p in out['pages']],criteria_sha256=sha(echo),request_ordinal=b.requests,result_set_reenumerated=False,publication_semantics='UNKNOWN'))
        progress.update(state='OBSERVATIONS_REQUIRE_REVIEW' if observation_only else 'COUNT_RECONCILED',criteria_verified=True);save()
        if not observation_only:
            out['enumeration_evidence']='COUNT_RECONCILED'
            out['pages'][-1]['terminal']='EXPLICIT_LAST_EQUALS_TOTAL'
    except Exception as exc:
        if type(exc) is CalibrationError:code=exc.code
        elif isinstance(exc,BoundaryFailure):
            code={'run deadline':'CALIBRATION_DEADLINE','request ceiling':'CALIBRATION_REQUEST_CAP','response byte ceiling':'CALIBRATION_BYTE_CAP'}.get(exc.reason,'CALIBRATION_UNKNOWN')
        elif isinstance(exc,(ListingError,Failure)):code='CALIBRATION_ROW_LAYOUT_REFUSED'
        else:code='CALIBRATION_UNKNOWN'
        from .source_diagnostics import shape,transport_facts
        out['failure_diagnostic']=shape(b'',stage,'UNCLASSIFIED_FAILURE',transport_facts(b.last_response,exc,failure=b.transport_failure))
        if type(exc) is CalibrationError and exc.detail is not None:
            # Fixed codes only: no DOM text, URLs, form values, cookies or tokens.
            out['navigation_refusal']=dict(version='PAGINATION_REFUSAL_V1',check=exc.detail,stage=stage,ordinal=ordinal if stage=='PAGE_PARSE' else None,body_sha256=sha(body) if stage=='PAGE_PARSE' else None)
        progress.update(state='STOPPED_REQUIRES_REVIEW',failure=code);out['failure']=code;out['capped']=code.endswith('_CAP');out['completeness']='FAILED'
        try:save()
        except Exception:pass
        try:
            proof.add(None,stage,transport=b.last_response)
            proof.events[-1]['transport']=out['failure_diagnostic']['transport']
        except Exception:pass
    finally:
        b.admitted_body=None;b.close()
        out.update(unique_references=len(refs),resource=b.audit(out['completeness']),cleanup='BOUNDARY_CLOSED',response_provenance=b.response_provenance,retained_proof=proof.result())
        # The source export stays bounded even if a trace checkpoint was refused.
        compact=progress if len(encoded(progress))<=TRACE_LIMIT else dict(mode=MODE,state='STOPPED_REQUIRES_REVIEW',failure='CALIBRATION_TRACE_BOUND',acceptance_enabled=False,requests=[],pages=[],criteria_verified=False)
        if observation_only:out['calibration']=compact
        else:out.update(pagination_mode=COUNTED_MODE,pagination_evidence=compact)
    return out
