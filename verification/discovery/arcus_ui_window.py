"""Fixed public listing UI; no synthetic RPC, detail or document navigation."""
import asyncio
from datetime import datetime
import hashlib
import json
import re
import time
from urllib.parse import urlsplit, parse_qs
from .manchester_shape import DESTINATION, START, END
from .arcus_ui_config import MANCHESTER
CASE='discovery_manchester_ui_window'
AURA='https://arcusbe.manchester.gov.uk/pr/s/sfsites/aura'
MAX_SEGMENTS=6
METADATA_LABELS={'Proposal','Description','Site Address','Location of works','Application type'}


def metadata_capture_evidence(value):
    if (not isinstance(value,dict) or set(value)!={'version','row_item_count','label_counts','route'}
        or type(value['version']) is not int or value['version']!=1
        or value['route']!='VISIBLE_ROW_EXACT_RENDERED_LABEL_V2'
        or type(value['row_item_count']) is not int or not 0<=value['row_item_count']<=20
        or not isinstance(value['label_counts'],dict) or set(value['label_counts'])!=METADATA_LABELS
        or any(type(n) is not int or n not in (0,1) for n in value['label_counts'].values())):
        raise ValueError('metadata evidence shape')
    return {**value,'label_counts':dict(value['label_counts'])}



def qualify_segment(marker,cards,expected_first,previous_total=None,config=MANCHESTER):
    m=re.fullmatch(r'Showing\s+(\d+)\s+to\s+(\d+)\s+of\s+(\d+)\s+results',marker.strip())
    if not m: raise ValueError('page marker')
    first,last,total=map(int,m.groups())
    if first!=expected_first or last<first or last>total or last-first+1!=len(cards) or len(cards)>10:
        raise ValueError('page continuity/count')
    if previous_total is not None and total!=previous_total: raise ValueError('changing total')
    rows=[]
    for c in cards:
        links=c['links']; fields=c['fields']
        if len(links)!=1: raise ValueError('record link identity')
        ref=links[0]['text'].strip(); u=urlsplit(links[0]['href'])
        if (u.scheme!='https' or u.netloc!=config.host or u.fragment
            or not re.fullmatch(r'/pr/s/detail/[A-Za-z0-9]{18}',u.path)
            or parse_qs(u.query)!= {'c__r':['Arcus_BE_Public_Register']}): raise ValueError('record destination')
        refs=[x['value'].strip() for x in fields if x['label'].lower()=='reference']
        if refs!=[ref] or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/._ -]{0,99}',ref): raise ValueError('displayed reference')
        dates=[x['value'].strip() for x in fields if x['label'].lower()=='valid date']
        if config.row_date:
            if len(dates)!=1: raise ValueError('date evidence')
            d=datetime.strptime(dates[0],'%d/%m/%Y').date().isoformat()
            if not config.start<=d<=config.end: raise ValueError('date outside interval')
        elif dates:raise ValueError('unqualified date projection')
        rows.append({'reference':ref,'source_record_id':u.path.rsplit('/',1)[1],
            'source_url':u.geturl(),'validated_date':{'state':'PRESENT_VALUE','literal':dates[0]} if config.row_date else {'state':'UNKNOWN','literal':None},
            'materiality':'POTENTIALLY_MATERIAL','relationship':'UNKNOWN',
            'field_capture_scope':['reference','validated_date'] if config.row_date else ['reference']})
        if config.assessment_metadata:
            from .screening_capture import project_fields
            rows[-1].update(project_fields(c))
        elif config.capture_metadata:
            metadata={}
            for key,names,limit in [('proposal',{'proposal','description'},1024),('address',{'site address','location of works'},600),('application_type',{'application type'},160)]:
                values=[x for x in fields if x['label'].casefold() in names]
                if len(values)>1:raise ValueError('metadata alias conflict')
                item=values[0] if values else None
                if item and (not isinstance(item.get('value'),str) or len(item['value'])>limit):raise ValueError('metadata value bound')
                metadata[key]=dict(state='PRESENT_VALUE' if item and item['value'] else 'PRESENT_BLANK' if item else 'UNKNOWN',value=item['value'] if item else None,locator='visible listing field:'+item['label'] if item else 'NOT_CAPTURED',truncated=bool(item and item.get('truncated')))
            rows[-1]['fields']=metadata
            if 'metadata_capture_evidence' in c:
                rows[-1]['metadata_capture_evidence']=metadata_capture_evidence(c['metadata_capture_evidence'])
            rows[-1]['field_capture_scope']+=['proposal','address','application_type']
    if len({r['reference'] for r in rows})!=len(rows) or len({r['source_record_id'] for r in rows})!=len(rows):
        raise ValueError('duplicate page identity')
    return first,last,total,rows


async def read_cards(page,config=MANCHESTER):
    """Read exact row-bound fields; optional metadata never leaves its card."""
    cards=page.locator('div[role="list"].slds-box')
    count=await cards.count()
    if not 1<=count<=10: raise ValueError('card count')
    out=[]
    for i in range(count):
        card=cards.nth(i)
        links=card.locator('a[href*="/detail/"]')
        if await links.count()!=1: raise ValueError('record link count')
        ref=await links.inner_text(timeout=1500)
        href=await links.get_attribute('href',timeout=1500)
        # DOM href may be relative; qualify_segment still restricts the destination.
        from urllib.parse import urljoin
        href=urljoin(config.destination,href or '')
        if len(ref)>100 or len(href)>512: raise ValueError('link bound')
        items=card.locator('[role="listitem"]')
        if await items.count()>20: raise ValueError('field count')
        fields=[]
        for name in (('Reference','Valid Date') if config.row_date else ('Reference',)):
            field=items.filter(has_text=re.compile(r'^\s*'+re.escape(name),re.I))
            if await field.count()!=1: raise ValueError('field label count')
            text=await field.inner_text(timeout=1500)
            parts=text.strip().split('\n',1)
            if len(parts)!=2 or parts[0].strip().lower()!=name.lower(): raise ValueError('field label')
            value=parts[1].strip()
            if len(value)>160: raise ValueError('field value bound')
            fields.append({'label':name,'value':value})
        if config.assessment_metadata:
            from .screening_capture import capture_fields
            captured=await capture_fields(items)
            out.append({'links':[{'text':ref,'href':href}],'fields':fields,
                        'assessment_capture':captured})
            continue
        if config.capture_metadata:
            label_counts={}
            # Exact visible labels only; never read applicant/contact fields or raw HTML.
            for name,limit in [('Proposal',1024),('Description',1024),('Site Address',600),('Location of works',600),('Application type',160)]:
                # has_text sees DOM textContent, not layout-produced innerText
                # newlines. Match the prefix here, then verify the exact rendered
                # first line below. Never loosen the final label/value contract.
                field=items.filter(has_text=re.compile(r'^\s*'+re.escape(name),re.I))
                n=await field.count()
                label_counts[name]=n
                if n>1:raise ValueError('metadata label conflict')
                if n==1:
                    text=await field.inner_text(timeout=1500);parts=text.strip().split('\n',1)
                    if len(parts)!=2 or parts[0].strip().casefold()!=name.casefold():raise ValueError('metadata label shape')
                    value=parts[1].strip()
                    fields.append({'label':name,'value':value[:limit],'truncated':len(value)>limit})
        out.append({'links':[{'text':ref,'href':href}],'fields':fields})
        if config.capture_metadata:
            out[-1]['metadata_capture_evidence']={'version':1,'row_item_count':await items.count(),
                'label_counts':label_counts,'route':'VISIBLE_ROW_EXACT_RENDERED_LABEL_V2'}
    return out


CRITERIA_OPERATIONS=frozenset({'RESULT_MARKER_VISIBLE','CRITERIA_DISCLOSURE','VALID_FROM','VALID_TO',
    'BLANK_INPUT','BLANK_COMBO','CATEGORY'})
LOCAL_TIMEOUT='SOURCE_LOCAL_CRITERIA_CONTROL_TIMEOUT'

async def criteria_control(operation, action, audit):
    # Only the actual Playwright locator timeout at a named operation qualifies.
    # A same-named builtin exception, generic stage or arbitrary payload cannot.
    from playwright.async_api import TimeoutError as LocatorTimeout
    if operation not in CRITERIA_OPERATIONS:raise ValueError('criteria operation')
    try:return await action()
    except LocatorTimeout:
        audit['criteria_control_timeout']={'code':LOCAL_TIMEOUT,'operation':operation,
            'exception_contract':'PLAYWRIGHT_LOCATOR_TIMEOUT_V1'}
        raise


async def enumerate_ui(page,audit,stopped,config=MANCHESTER,*,retain_proof=False,budget=None,deadline=None):
    """budget/deadline None: historical waits (unchanged literals). With an execution budget
    (docs/design/execution-budget-20261026/SPEC.md) every wait is min(step cap, remaining) of the
    single observation deadline; a truncated wait that expires is ObservationDeadline."""
    proof=None
    if type(retain_proof) is not bool:raise ValueError('proof selection')
    if (budget is None)!=(deadline is None):raise ValueError('budget selection')
    # Imported only when budgeted: the default path never depends on the new module.
    ObservationDeadline=None
    if deadline is not None:from .execution_budget import ObservationDeadline
    truncated=[False]
    def wait_ms(default_ms,step_seconds=None,scope_end=None):
        # Default: the historical literal. Budgeted: min(step, scope remaining, observation remaining).
        if deadline is None:return default_ms
        step=default_ms/1000 if step_seconds is None else step_seconds
        if scope_end is not None:
            scope_left=scope_end-deadline.clock()
            if scope_left<=0:raise ObservationDeadline('OBSERVATION_DEADLINE')
            step_cut=min(step,scope_left);cut=step_cut<step
        else:step_cut=step;cut=False
        value=deadline.cap_ms(step_cut)
        truncated[0]=cut or deadline.truncated
        return value
    timings={} if deadline is not None else None
    if retain_proof:
        from .four_council_proof import ProofLog
        proof=ProofLog(config.council,'VALIDATED',config.start,config.end)
    audit.update(listing_stage='CRITERIA',listing_segments=[],listing_records=[],completeness='UNKNOWN',applied_interval=None,
                 source_qualification='CANDIDATE_PUBLIC_UI_CONTRACT',enumeration_evidence=None)
    try:
        # The sealed Manchester zero observation has a paragraph "No results
        # found" and no pagination marker. Absence of pagination alone is NEVER
        # zero evidence. Applied criteria and contradictory rows are checked below.
        # Only Manchester has retained source evidence for this zero shape.
        zero_supported=config.council=='manchester'
        result_selector='p.pr-pagination__results, p:text-is("No results found")' if zero_supported else 'p.pr-pagination__results'
        ready_started=time.monotonic()
        ready_ms=wait_ms(10000,budget['ready_seconds'] if budget else None)
        await criteria_control('RESULT_MARKER_VISIBLE',lambda:page.locator(result_selector).wait_for(state='visible',timeout=ready_ms),audit)
        criteria_started=time.monotonic()
        if timings is not None:timings['READY']=int((criteria_started-ready_started)*1000)
        criteria_end=deadline.clock()+budget['criteria_seconds'] if deadline is not None else None
        # An ordinary disclosure toggle exposes the source's retained filters.
        disclosure_ms=wait_ms(3000,scope_end=criteria_end)
        await criteria_control('CRITERIA_DISCLOSURE',lambda:page.get_by_role('button',name='Show the search criteria',exact=True).click(timeout=disclosure_ms),audit)
        expected={'Valid date from':datetime.strptime(config.start,'%Y-%m-%d').strftime('%d/%m/%Y'),'Valid date to':datetime.strptime(config.end,'%Y-%m-%d').strftime('%d/%m/%Y'),**{k:'' for k in config.blank_inputs}}
        for label,value in expected.items():
            operation='VALID_FROM' if label=='Valid date from' else 'VALID_TO' if label=='Valid date to' else 'BLANK_INPUT'
            control_ms=wait_ms(1500,scope_end=criteria_end)
            if await criteria_control(operation,lambda:page.get_by_label(label,exact=True).input_value(timeout=control_ms),audit)!=value: raise ValueError('applied filter mismatch')
        for label in config.blank_combos:
            control_ms=wait_ms(1500,scope_end=criteria_end)
            if (await criteria_control('BLANK_COMBO',lambda:page.get_by_role('combobox',name=label,exact=True).inner_text(timeout=control_ms),audit)).strip()!='Select an option':
                raise ValueError('hidden filter')
        control_ms=wait_ms(1500,scope_end=criteria_end)
        if (await criteria_control('CATEGORY',lambda:page.get_by_role('combobox',name='Category',exact=True).inner_text(timeout=control_ms),audit)).strip()!='Planning Applications':
            raise ValueError('category')
        if timings is not None:timings['CRITERIA']=int((time.monotonic()-criteria_started)*1000)
        audit['applied_interval']=[config.start,config.end]
        audit['applied_evidence']='VISIBLE_RETAINED_CRITERIA_AND_ROW_VALID_DATES' if config.row_date else 'VISIBLE_RETAINED_VALID_DATE_CRITERIA'
        zero=page.locator('p:text-is("No results found")')
        if zero_supported and await zero.count():
            if (await zero.count()!=1 or await zero.inner_text(timeout=wait_ms(1500))!='No results found'
                or await page.locator('div[role="list"].slds-box').count()!=0
                or await page.locator('p.pr-pagination__results').count()!=0
                or await page.locator('a.pr-pagination__link').filter(has_text='Next').count()!=0):
                raise ValueError('zero result conflict')
            audit['explicit_zero_evidence']='EXACT_VISIBLE_ZERO_AND_RETAINED_CRITERIA_NO_ROWS_OR_NEXT'
            audit['listing_segments']=[{'ordinal':1,'first':0,'last':0,'total':0,
                'evidence_sha256':hashlib.sha256(b'No results found').hexdigest()}]
            audit['enumeration_evidence']='COUNT_RECONCILED'
            return
        expected_first=1; total=None; seen_refs=set();seen_keys=set()
        for ordinal in range(1,MAX_SEGMENTS+1):
            if stopped.is_set(): raise ValueError('resource stop')
            segment_started=time.monotonic()
            until=time.monotonic()+(5 if deadline is None else wait_ms(8000,budget['segment_poll_seconds'])/1000)
            while True:
                audit['listing_stage']='PAGE_MARKER'
                marker_kwargs={} if deadline is None else {'timeout':wait_ms(8000,max(.001,until-time.monotonic()))}
                marker=' '.join((await page.locator('p.pr-pagination__results').inner_text(**marker_kwargs)).split())
                if re.match(r'Showing\s+'+str(expected_first)+r'\s+to\s+',marker): break
                if time.monotonic()>until or stopped.is_set():
                    if deadline is not None and truncated[0]:raise ObservationDeadline('OBSERVATION_DEADLINE')
                    raise ValueError('pagination did not advance')
                await asyncio.sleep(.1)
            audit['listing_stage']='ROW_LOCATORS'
            if deadline is None:cards=await read_cards(page,config)
            else:
                try:cards=await asyncio.wait_for(read_cards(page,config),timeout=deadline.cap(deadline.remaining() or .001))
                except asyncio.TimeoutError:raise ObservationDeadline('OBSERVATION_DEADLINE') from None
            audit['listing_stage']='ROW_QUALIFICATION'
            first,last,total,rows=qualify_segment(marker,cards,expected_first,total,config)
            for r in rows:
                if r['reference'] in seen_refs or r['source_record_id'] in seen_keys: raise ValueError('cross-page duplicate')
                seen_refs.add(r['reference']);seen_keys.add(r['source_record_id'])
            audit['listing_records'].extend(rows)
            audit['listing_segments'].append({'ordinal':ordinal,'first':first,'last':last,'total':total,
                'evidence_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()})
            if timings is not None:timings.setdefault('SEGMENT',[]).append(int((time.monotonic()-segment_started)*1000))
            audit['listing_stage']='NEXT_CONTROL'
            next_link=page.locator('a.pr-pagination__link').filter(has_text='Next')
            count=await next_link.count()
            if last==total:
                if count: raise ValueError('terminal next conflict')
                audit['enumeration_evidence']='COUNT_RECONCILED';return
            if count!=1: raise ValueError('missing/ambiguous next')
            if ordinal==MAX_SEGMENTS:
                audit['completeness']='INCOMPLETE';audit['enumeration_evidence']='PAGE_CAP';return
            # Empty href was observed; disallow a link to any business/detail route.
            href=await next_link.get_attribute('href')
            if href not in ('',None,'#'): raise ValueError('unexpected next destination')
            await next_link.click(timeout=wait_ms(3000,budget['segment_click_seconds'] if budget else None))
            expected_first=last+1
    except Exception as exc:
        audit['completeness']='INCOMPLETE' if audit['listing_segments'] else 'FAILED'
        if deadline is not None and (isinstance(exc,ObservationDeadline) or (type(exc).__name__=='TimeoutError' and truncated[0])):
            # Budget expiry, including a deadline-truncated wait: never the allowlisted TimeoutError.
            audit['listing_failure']='ObservationDeadline';audit['observation_deadline']=True
            # A truncated control timeout is budget expiry, never the typed source-local timeout.
            truncated_control=audit.pop('criteria_control_timeout',None)
            if truncated_control is not None:audit['deadline_truncated_operation']=truncated_control.get('operation')
        else:
            audit['listing_failure']=(type(exc).__name__ if retain_proof and type(exc).__name__ in {'TimeoutError','ValueError'} else 'UNCLASSIFIED_FAILURE' if retain_proof else type(exc).__name__+(':'+str(exc)[:80] if isinstance(exc,ValueError) else ''))

    finally:
        if timings is not None:
            audit.setdefault('stage_timings',{}).update({k:(v[:6] if isinstance(v,list) else v) for k,v in timings.items()})
        if proof is not None:
            # Browser-local snapshot, no navigation/retry and no response-body claim.
            try:
                from .four_council_proof import capture_rochdale
                snapshot=await capture_rochdale(page,config)
                proof.add_rendered(snapshot,audit['listing_stage'])
                audit['retained_proof']=proof.result()
                if snapshot['availability']!='PRESENT':
                    raise ValueError('PROOF_UNAVAILABLE')
            except Exception:
                audit['proof_retention_failure']='PROOF_RETENTION_FAILED'
                audit['failure']='PROOF_RETENTION_FAILED'
                audit['completeness']='FAILED'
