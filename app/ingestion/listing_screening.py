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


RULE_V1='manchester-listing-screen-assessment-v1'
RULE_V2='manchester-listing-screen-assessment-v2'
SIZE_BELOW='KNOWN_BELOW_SCREENING_THRESHOLD'
SIZE_AT_OR_ABOVE='KNOWN_AT_OR_ABOVE_SCREENING_THRESHOLD'
SIZE_NOT_ESTABLISHED='SIZE_NOT_ESTABLISHED'
RESIDENTIAL_WORDING=re.compile(r'\b(?:dwellings?|houses?|flats?|apartments?|residential|housing|homes?)\b',re.I)      # the v1 test, unchanged; v1 and v2 share it
# What a number may describe (v2 only). A count is a SCHEME SIZE only when it is attached to a dwelling noun ("12 dwellings", "six self contained flats"; deliberately not a bare "unit") and that mention
# is not about existing or removed dwellings ("demolition of 14 flats") and the number is not a bedroom, storey, space or person count ("a 60 bedroom care home"). Anything else is left as SIZE_NOT_ESTABLISHED, which makes no claim and changes no disposition.
_NUMBER_WORDS={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,
               'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
_DWELLING_NOUN=r'(?:dwellings?|dwellinghouses?|houses?|flats?|apartments?|maisonettes?|bungalows?|townhouses?|homes?|(?:residential|self[- ]contained|affordable|retirement|extra[- ]care|student|living)\s+(?:units?|accommodation))'
ATTACHED_COUNT=re.compile(r'(?<![\w/.,-])(\d{1,4}|'+'|'.join(_NUMBER_WORDS)+r')\b[\s-]*(?:no\.?\s+)?(?!(?:bed|beds|bedroom|bedrooms|bedded|room|rooms|storey|storeys|story|stories|car|cars|parking|space|spaces|person|persons|bay|bays|m|metres?)\b)(?:[\w-]+\.?\s+){0,3}?'+_DWELLING_NOUN+r'\b(?!\s+(?:blocks?|buildings?)\b)',re.I)      # "4 no. apartment blocks" counts blocks, not apartments
EXISTING_OR_REMOVED=re.compile(r'\b(?:demolition|demolish\w*|removal|loss|clearance|existing|retention|retain\w*|former|approved|previously|wider|overall|masterplan|allocation|parent|outline)\b',re.I)
NOT_HOUSING_SUPPLY=re.compile(r'\b(?:holiday|temporary|caravans?|static|lodges?|glamping|serviced|short[- ]let|pods?)\b',re.I)
CREATING=re.compile(r'\b(?:erection|construction|construct\w*|development|creation|provision|provid\w+|formation|comprising|proposed|new|build\w*|redevelopment|replac\w+)\b',re.I)
# "change of use of 12 flats" / "conversion of 12 flats" / "alterations to 12 flats" name the EXISTING dwellings, until a "to / into / as / provide ..." introduces what is created: "change of use of offices to 12 flats" is new.
TRANSFORMING=re.compile(r'\b(?:change of use|conversions?|alterations?|extensions?|refurbishment|renovation|sub-?division|amalgamation)\s+(?:of|to|from)\b',re.I)
INTRODUCES=re.compile(r'\b(?:to|into|as)\b|\bprovid\w+|\bcreat\w+',re.I)
CLAUSE_BREAK=re.compile(r'[.;:,()\n]')


def council_unit_threshold(council):
    """The council's CONFIGURED screening threshold (config/councils.yaml `unit_threshold`, the value the weekly pipeline already passes to `qualify`)."""
    from app.config import get_council
    return get_council(council).unit_threshold


def screen_row(row,*,rule_version=RULE_V1,council=None,unit_threshold=None):
    """Record-level screening.

    `rule_version=RULE_V1` (the default) is the original behaviour, byte for byte: every existing caller, stored result and stored-versus-recomputed comparison is unchanged. `RULE_V2` is opt-in per call and ADDITIVE:
    the disposition logic is the same, but it uses the council's configured threshold and adds `size_assessment`, `known_unit_count`, `screening_threshold` and `size_reason`, so that "size established and
    below the screening threshold" is no longer indistinguishable from "insufficient evidence". Nothing re-screens an existing item: a v2 result is a new result under its own rule version."""
    if rule_version not in (RULE_V1,RULE_V2):raise ValueError('UNKNOWN_SCREENING_RULE_VERSION')
    if rule_version==RULE_V1:
        if council is not None or unit_threshold is not None:raise ValueError('RULE_V1_TAKES_NO_THRESHOLD')
        return _screen(row,None,RULE_V1)
    if (council is None)==(unit_threshold is None):raise ValueError('RULE_V2_REQUIRES_EXACTLY_ONE_OF_COUNCIL_OR_THRESHOLD')
    threshold=council_unit_threshold(council) if council is not None else unit_threshold
    if type(threshold) is not int or threshold<=0:raise ValueError('INVALID_SCREENING_THRESHOLD')
    out=_screen(row,threshold,RULE_V2)
    return out


def _count_attachment(text,count):
    """What the qualifier's count (its largest candidate) is, judged against EVERY count attached to a dwelling noun in the wording. Returns one of
    'NOT_ATTACHED' (no count is attached to a dwelling noun), 'ONLY_EXISTING' (every attached count is about existing, removed, approved or wider-scheme dwellings), 'MULTIPLE' (more than one proposed count, e.g.
    "5 houses and 5 flats": the parts are never summed or guessed), 'DISAGREES' (the single proposed count is not the qualifier's) or 'SINGLE_NEW' (exactly one proposed count and it is the qualifier's).
    A mention is about existing dwellings when existing, removal, approval or wider-scheme wording is inside it or precedes it in its clause with no creating wording in between, when a transformation
    ("change of use from / of", "conversion of", "alterations to") precedes it with nothing introducing the new use, or when it is not housing supply (holiday, temporary, caravan, lodge ...)."""
    proposed=[];attached=0
    for m in ATTACHED_COUNT.finditer(text):
        word=m.group(1).lower();value=_NUMBER_WORDS[word] if word in _NUMBER_WORDS else int(word)
        if NOT_HOUSING_SUPPLY.search(m.group(0)):continue      # holiday homes and the like are not attached dwellings at all
        attached+=1
        cuts=[c.end() for c in CLAUSE_BREAK.finditer(text,0,m.start())]
        window=text[max(cuts[-1] if cuts else 0,m.start()-120):m.start()]
        existing=[x.start() for x in EXISTING_OR_REMOVED.finditer(window)];creating=[x.start() for x in CREATING.finditer(window)]
        for t in TRANSFORMING.finditer(window):
            if not INTRODUCES.search(window,t.end()):existing.append(t.start())      # the transformation names the existing dwellings and nothing after it introduces the new ones
        existing.sort()
        inside=bool(EXISTING_OR_REMOVED.search(m.group(0)))      # "20 existing houses"
        if inside or (existing and not (creating and creating[-1]>existing[-1])):continue
        proposed.append(value)
    if not attached:return 'NOT_ATTACHED'
    if not proposed:return 'ONLY_EXISTING'
    if len(proposed)>1:return 'MULTIPLE'
    return 'SINGLE_NEW' if proposed[0]==count else 'DISAGREES'


def _screen(row,threshold,rule):
    from app.scrapers.unit_filter import qualify
    f=row['fields']['proposal'];text=f.get('value') or ''
    usable=f['state']=='PRESENT_VALUE' and bool(text.strip()) and not f.get('truncated')
    q=(qualify(text) if threshold is None else qualify(text,threshold)) if usable else None
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
    residential=bool(RESIDENTIAL_WORDING.search(text))
    if not usable or c['overflow']:disposition='INSUFFICIENT_EVIDENCE'
    elif related:disposition='RELATED_APPLICATION_FOLLOW_THROUGH'
    elif residential and q.qualifies:disposition='SUPPORTED_PROCESSING_PRIORITY'
    elif q.classification in {'Excluded - non-residential','Excluded - likely single-unit change of use'} or q.category=='non_target_admin_or_minor':
        disposition='DEEPER_PROCESSING_EXCLUDED_FOR_THIS_SLICE'
    else:disposition='INSUFFICIENT_EVIDENCE'
    out=dict(rule_version=rule,proposal_usable=usable,
        disposition=disposition,retained=True,permanent_exclusion=False,commercial_relevance='UNKNOWN',
        existing_classification=q.classification if q else None,existing_category=q.category if q else None,
        raw_generic_count=q.unit_count if q else None,residential_dwelling_count=None,
        citations=c,site_relationship='UNKNOWN',progress='UNKNOWN')
    if rule==RULE_V2:
        count=q.unit_count if q is not None else None
        # The existing qualifier decides eligibility; v2 only adds what the number describes. First applicable reason wins.
        if q is None:assessment,reason=SIZE_NOT_ESTABLISHED,'PROPOSAL_NOT_USABLE'
        elif related:assessment,reason=SIZE_NOT_ESTABLISHED,'RELATED_APPLICATION_LEAD'      # the related-application lead takes precedence; the count may describe the parent scheme
        elif q.classification=='Excluded - non-residential':assessment,reason=SIZE_NOT_ESTABLISHED,'NOT_RESIDENTIAL_PROPOSAL'      # e.g. "change of use of 12 flats to a hotel": not a housing scheme, whatever the number
        elif q.classification=='Excluded - secondary/admin':assessment,reason=SIZE_NOT_ESTABLISHED,'ADMINISTRATIVE_OR_SECONDARY_APPLICATION'
        elif count is None:assessment,reason=SIZE_NOT_ESTABLISHED,'NO_UNIT_COUNT'
        elif not residential:assessment,reason=SIZE_NOT_ESTABLISHED,'COUNT_WITHOUT_RESIDENTIAL_WORDING'      # e.g. "1 NO. AIR HANDLING UNIT": a number, not a dwelling count
        elif not (q.classification.startswith('Ignore - under ') or q.classification.startswith('Confirmed - ')):assessment,reason=SIZE_NOT_ESTABLISHED,'UNRECOGNISED_QUALIFIER_OUTCOME'      # default-deny
        else:
            attachment=_count_attachment(text,count)
            if attachment=='NOT_ATTACHED':assessment,reason=SIZE_NOT_ESTABLISHED,'COUNT_NOT_ATTACHED_TO_A_DWELLING_NOUN'
            elif attachment=='ONLY_EXISTING':assessment,reason=SIZE_NOT_ESTABLISHED,'COUNT_DESCRIBES_EXISTING_OR_REMOVED_DWELLINGS'
            elif attachment=='MULTIPLE':assessment,reason=SIZE_NOT_ESTABLISHED,'MULTIPLE_PROPOSED_DWELLING_COUNTS'      # parts are never summed: "5 houses and 5 flats" is not "5"
            elif attachment=='DISAGREES':assessment,reason=SIZE_NOT_ESTABLISHED,'COUNT_DISAGREES_WITH_THE_PROPOSED_MENTION'
            elif count<threshold:assessment,reason=SIZE_BELOW,'DWELLING_COUNT_BELOW_THRESHOLD'
            else:assessment,reason=SIZE_AT_OR_ABOVE,'DWELLING_COUNT_AT_OR_ABOVE_THRESHOLD'
        out.update(size_assessment=assessment,known_unit_count=count if assessment!=SIZE_NOT_ESTABLISHED else None,screening_threshold=threshold,size_reason=reason)
    return out
