"""Opt-in literal listing capture. No source navigation, persistence or inference."""
import hashlib
import json
import re

LABELS=(('Proposal',8192),('Description',8192),('Site Address',600),
        ('Location of works',600),('Application type',160),
        ('Received Date',160),('Date received',160),('Received',160))


async def capture_fields(items):
    """Only exact rendered labels leave the row; no raw HTML/private fields."""
    from playwright.async_api import TimeoutError as LocatorTimeout
    out=[]
    for name,limit in LABELS:
        matches=items.filter(has_text=re.compile(r'^\s*'+re.escape(name),re.I))
        n=await matches.count()
        if not 0<=n<=20:raise ValueError('ASSESSMENT_LABEL_COUNT')
        exact=[];timed_out=False
        for i in range(n):
            field=matches.nth(i)
            try:
                raw=await field.inner_text(timeout=1500)
                parts=raw.strip().split('\n',1)
                if len(parts)!=2 or parts[0].strip().casefold()!=name.casefold():continue
                dom=await field.text_content(timeout=1500)
                exact.append((parts,dom))
            except LocatorTimeout:timed_out=True
        entry=dict(label=name,matches=len(exact),state='UNKNOWN',value=None,locator='visible listing field:'+name)
        if timed_out:
            entry.update(state='UNKNOWN',capture_failure='LOCATOR_TIMEOUT')
        elif len(exact)>1:entry['state']='CONFLICTING'
        elif len(exact)==1:
            parts,dom=exact[0];value=parts[1].strip()
            entry.update(value=value[:limit],state='PRESENT_VALUE' if value else 'PRESENT_BLANK',
                truncated=len(value)>limit,rendered_label=parts[0].strip(),
                dom_text_content=(dom or '')[:limit+len(name)+32],
                original_characters=len(value),value_sha256=hashlib.sha256(value.encode()).hexdigest())
        out.append(entry)
    return out


def project_fields(card):
    captured=card['assessment_capture']
    if [x['label'] for x in captured]!=[x[0] for x in LABELS]:raise ValueError('CAPTURE_LABELS')
    fields={}
    for key,names in [('proposal',{'Proposal','Description'}),('address',{'Site Address','Location of works'}),
                      ('application_type',{'Application type'}),('received_date',{'Received Date','Date received','Received'})]:
        found=[x for x in captured if x['label'] in names and x['matches']]
        if not found:fields[key]=dict(state='UNKNOWN',value=None,locator='NOT_CAPTURED',truncated=False)
        elif len(found)>1:fields[key]=dict(state='CONFLICTING',value=None,locator='visible listing aliases',truncated=False)
        else:fields[key]=dict(found[0])
    valid=next((x for x in card['fields'] if x['label']=='Valid Date'),None)
    fields['validated_date']=dict(state='PRESENT_VALUE' if valid else 'UNKNOWN',
        value=valid['value'] if valid else None,locator='visible listing field:Valid Date',truncated=False)
    return dict(fields=fields,assessment_capture=captured,
        capture_sha256=hashlib.sha256(json.dumps(captured,sort_keys=True).encode()).hexdigest(),
        field_capture_scope=['reference',*fields])


REFERENCE=re.compile(r'(?<![A-Za-z0-9/_-])(?:[A-Z]{1,12}-\d{4}-\d{3,7}|(?:[A-Z]{1,12}/)?\d{2,7}/(?:[A-Z]{1,12}/)?\d{2,7}|[A-Z]{1,12}/\d{4,7})(?:/[A-Z0-9]{1,12})*(?![A-Za-z0-9/_-])',re.I)


def citations(text):
    matches=list(REFERENCE.finditer(text))
    records=[]
    for m in matches[:32]:
        if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',m.group()):continue
        a=max(text.rfind('.',0,m.start())+1,text.rfind('\n',0,m.start())+1,m.start()-240)
        ends=[i for i in (text.find('.',m.end()),text.find('\n',m.end())) if i>=0]
        b=min(min(ends)+1 if ends else len(text),m.end()+240)
        wording=text[a:b]
        relation=re.search(r'\b(?:relating to|pursuant to|variation (?:of|to)|following|associated with|discharge of|amendment to|attached to)\b',wording,re.I)
        records.append(dict(literal=m.group(),start=m.start(),end=m.end(),supporting_wording=wording,
            wording_start=a,relation_wording=relation.group() if relation else None,
            relation='EXPLICIT_WORDING_UNVERIFIED_LEAD' if relation else 'UNRESOLVED_CITATION',
            target_council=None,target_council_state='UNKNOWN',confirmed_relationship=False))
    return dict(occurrences=records,overflow=len(matches)>32,complete=len(matches)<=32)


def screen_row(row):
    from app.scrapers.unit_filter import qualify
    f=row['fields']['proposal'];text=f.get('value') or ''
    usable=f['state']=='PRESENT_VALUE' and bool(text.strip()) and not f.get('truncated')
    q=qualify(text) if usable else None
    occurrences=[];overflow=False
    for key in ('proposal','address','application_type'):
        value=row['fields'].get(key,{})
        found=citations(value.get('value') or '')
        overflow=overflow or found['overflow']
        occurrences.extend(dict(x,source_field=key,locator=value.get('locator')) for x in found['occurrences'])
    c=dict(occurrences=occurrences[:32],overflow=overflow or len(occurrences)>32,
           complete=usable and not overflow and len(occurrences)<=32 and not any(
               row['fields'].get(k,{}).get('truncated') for k in ('proposal','address','application_type')),
           coverage='OBSERVED_ALLOWLISTED_TEXT_ONLY')
    # Existing secondary/admin qualification must not suppress relation signals.
    related=q is not None and (q.category in {'variation_or_amendment','condition_discharge_or_details','reserved_matters','external_consultation'} or bool(c['occurrences']))
    residential=bool(re.search(r'\b(?:dwellings?|houses?|flats?|apartments?|residential|housing|homes?)\b',text,re.I))
    if not usable or c['overflow']:disposition='INSUFFICIENT_EVIDENCE'
    elif related:disposition='RELATED_APPLICATION_FOLLOW_THROUGH'
    elif residential and q.qualifies:disposition='SUPPORTED_PROCESSING_PRIORITY'
    elif q.classification in {'Excluded - non-residential','Excluded - likely single-unit change of use'} or q.category=='non_target_admin_or_minor':
        disposition='DEEPER_PROCESSING_EXCLUDED_FOR_THIS_SLICE'
    else:disposition='INSUFFICIENT_EVIDENCE'
    return dict(rule_version='manchester-listing-screen-assessment-v1',proposal_usable=usable,
        disposition=disposition,retained=True,permanent_exclusion=False,commercial_relevance='UNKNOWN',
        existing_classification=q.classification if q else None,existing_category=q.category if q else None,
        raw_generic_count=q.unit_count if q else None,residential_dwelling_count=None,
        citations=c,site_relationship='UNKNOWN',progress='UNKNOWN')
