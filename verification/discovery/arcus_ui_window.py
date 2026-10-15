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
    if len({r['reference'] for r in rows})!=len(rows) or len({r['source_record_id'] for r in rows})!=len(rows):
        raise ValueError('duplicate page identity')
    return first,last,total,rows


async def read_cards(page,config=MANCHESTER):
    """Read only the two qualified fields through ordinary bounded locators."""
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
        out.append({'links':[{'text':ref,'href':href}],'fields':fields})
    return out


async def enumerate_ui(page,audit,stopped,config=MANCHESTER):
    audit.update(listing_stage='CRITERIA',listing_segments=[],listing_records=[],completeness='UNKNOWN',applied_interval=None,
                 source_qualification='CANDIDATE_PUBLIC_UI_CONTRACT')
    try:
        await page.locator('p.pr-pagination__results').wait_for(state='visible',timeout=10000)
        # An ordinary disclosure toggle exposes the source's retained filters.
        await page.get_by_role('button',name='Show the search criteria',exact=True).click(timeout=3000)
        expected={'Valid date from':datetime.strptime(config.start,'%Y-%m-%d').strftime('%d/%m/%Y'),'Valid date to':datetime.strptime(config.end,'%Y-%m-%d').strftime('%d/%m/%Y'),**{k:'' for k in config.blank_inputs}}
        for label,value in expected.items():
            if await page.get_by_label(label,exact=True).input_value(timeout=1500)!=value: raise ValueError('applied filter mismatch')
        for label in config.blank_combos:
            if (await page.get_by_role('combobox',name=label,exact=True).inner_text()).strip()!='Select an option':
                raise ValueError('hidden filter')
        if (await page.get_by_role('combobox',name='Category',exact=True).inner_text()).strip()!='Planning Applications':
            raise ValueError('category')
        audit['applied_interval']=[config.start,config.end]
        audit['applied_evidence']='VISIBLE_RETAINED_CRITERIA_AND_ROW_VALID_DATES' if config.row_date else 'VISIBLE_RETAINED_VALID_DATE_CRITERIA'
        expected_first=1; total=None; seen_refs=set();seen_keys=set()
        for ordinal in range(1,MAX_SEGMENTS+1):
            if stopped.is_set(): raise ValueError('resource stop')
            until=time.monotonic()+5
            while True:
                audit['listing_stage']='PAGE_MARKER'
                marker=' '.join((await page.locator('p.pr-pagination__results').inner_text()).split())
                if re.match(r'Showing\s+'+str(expected_first)+r'\s+to\s+',marker): break
                if time.monotonic()>until or stopped.is_set(): raise ValueError('pagination did not advance')
                await asyncio.sleep(.1)
            audit['listing_stage']='ROW_LOCATORS'
            cards=await read_cards(page,config)
            audit['listing_stage']='ROW_QUALIFICATION'
            first,last,total,rows=qualify_segment(marker,cards,expected_first,total,config)
            for r in rows:
                if r['reference'] in seen_refs or r['source_record_id'] in seen_keys: raise ValueError('cross-page duplicate')
                seen_refs.add(r['reference']);seen_keys.add(r['source_record_id'])
            audit['listing_records'].extend(rows)
            audit['listing_segments'].append({'ordinal':ordinal,'first':first,'last':last,'total':total,
                'evidence_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()})
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
            await next_link.click(timeout=3000)
            expected_first=last+1
    except Exception as exc:
        audit['completeness']='INCOMPLETE' if audit['listing_segments'] else 'FAILED'
        audit['listing_failure']=type(exc).__name__+(':'+str(exc)[:80] if isinstance(exc,ValueError) else '')
