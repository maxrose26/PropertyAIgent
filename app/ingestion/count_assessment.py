"""Proposal-text residential count assessment (specification 035, sections 3-6 and 10, Phase A).

PURE and OFFLINE: one proposal string (and an optional application type) in, one plain dict out. No database, network, model call, clock or configuration; it writes nothing and re-screens nothing. It never
reads or writes the legacy scalar columns. The counting rules are the specification's: R-ATTACH, R-UNITS, R-SUM, R-PRODUCT, R-EXISTING, R-HOUSING, R-CONTEXT, R-UNUSABLE, R-AMEND, R-MIXED, and the fixed
definitions of proposed / existing / lost / net. The text yields at most ONE supported PROPOSED-basis record (source kind LISTING_PROPOSAL_TEXT); approved counts need permission evidence and can never come from
this module. Admission is the size gate only (count_evidence.size_outcome); category and role come from the existing classifier plus the specification's roles. Wording analysis is linear in the text length."""
import re

from . import count_evidence as ce

RULE_VERSION='residential-count-v2'
SOURCE_KIND='LISTING_PROPOSAL_TEXT'
NE='NOT_ESTABLISHED';NONE='NONE'
MAX_TEXT=8192      # the screening bound: anything longer is not analysed

NUMBER_WORDS={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,
              'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
_TENS='twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety'
_UNITS='one|two|three|four|five|six|seven|eight|nine'
_NUM=r'(\d{1,4}|(?:'+_TENS+r')[- ](?:'+_UNITS+r')|'+'|'.join(NUMBER_WORDS)+r')'      # "twenty-four" / "twenty four" are one number, never "twenty" 
DWELLING_NOUN=r'(?:dwellings?|dwellinghouses?|houses?|flats?|apartments?|maisonettes?|bungalows?|townhouses?|homes?|(?:residential|self[- ]contained|affordable|retirement|extra[- ]care|living)\s+(?:units?|accommodation))'
_STOP=r'(?:comprising|comprises|containing|including|with|for|to|of|and|within|providing|creating|into|from|on|at)'
_NOT_COUNT=r'(?:bed|beds|bedroom|bedrooms|bedded|room|rooms|storey|storeys|story|stories|car|cars|parking|space|spaces|person|persons|bay|bays|m|metres?)'
ATTACHED=re.compile(r'(?<![\w/.,-])'+_NUM+r'\b[\s-]*(?:no\.?\s+)?(?!'+_NOT_COUNT+r'\b)(?:(?!'+_STOP+r'\b)[\w-]+\.?\s+){0,3}?'+DWELLING_NOUN+r'\b(?!\s+(?:blocks?|buildings?)\b)',re.I)
UP_TO=re.compile(r'\b(?:up\s+to|not\s+exceeding|no\s+more\s+than|maximum\s+of)\s+'+_NUM+r'\b[\s-]*(?:no\.?\s+)?(?:(?!'+_STOP+r'\b)[\w-]+\.?\s+){0,4}?'+DWELLING_NOUN+r'\b',re.I)
_GROUP=r'(?:apartment\s+)?(?:blocks?|buildings?|terraces?|towers?|wings?)'
_STATE=r'(?:(?:existing|former|retained|redundant|derelict|vacant)\s+)?'      # "2 existing blocks of 6 flats each" is still a product, and an existing one
PRODUCT=re.compile(r'(?<![\w/.,-])'+_NUM+r'\s+'+_STATE+_GROUP+r'\s+(?:of|comprising|containing)\s+'+_NUM+r'\s+(?:(?!'+_STOP+r'\b)[\w-]+\s+){0,2}?'+DWELLING_NOUN+r'\s+each\b',re.I)
PRODUCT_IN_EACH=re.compile(r'(?<![\w/.,-])'+_NUM+r'\s+(?:(?!'+_STOP+r'\b)[\w-]+\s+){0,2}?'+DWELLING_NOUN+r'\s+in\s+each\s+of\s+'+_NUM+r'\s+'+_GROUP+r'\b',re.I)
GROUP_OF_UNCLEAR=re.compile(r'(?<![\w/.,-])'+_NUM+r'\s+'+_GROUP+r'\s+of\s+'+_NUM+r'\s+(?:(?!'+_STOP+r'\b)[\w-]+\s+){0,2}?'+DWELLING_NOUN+r'\b(?!\s+each\b)',re.I)      # "2 blocks of 6 flats": per block or in total? not decided by guessing
STUDENT=re.compile(r'\bstudents?\b|\bcluster\s+(?:flats?|units?|apartments?)\b',re.I)      # decision D4: student accommodation is not dwelling supply
_AUX=r'(?:(?:are|is|will\s+be|to\s+be|being|be)\s+)?'
AFTER_RETAINED=re.compile(r'\A\s*'+_AUX+r'(?:retained|existing|remaining|to\s+remain)\b',re.I)      # directly after the count's own noun: "3 dwellings retained", never "... and retained community hall"
AFTER_REMOVED=re.compile(r'\A\s*'+_AUX+r'(?:demolished|removed)\b',re.I)
AFTER_STUDENT=re.compile(r'\A\s*(?:for|to\s+house|to\s+accommodate)\s+students?\b|\A\s*\(?\s*student\s+(?:use|accommodation|housing)\b',re.I)      # "12 flats for students"
HUNDRED=re.compile(r'\b(?:hundred|thousand)\b(?:\s+and\s+[\w-]+(?:[- ]\w+)?)?\s+(?:[\w-]+\s+){0,2}?'+DWELLING_NOUN+r'\b',re.I)      # number words this module does not parse, only where they count dwellings
BARE_UNITS=re.compile(r'(?<![\w/.,-])(\d{1,4})\s+(?:no\.?\s+)?units?\b',re.I)
RESIDENTIAL_WORDING=re.compile(r'\b(?:dwellings?|houses?|flats?|apartments?|residential|housing|homes?|bungalows?|maisonettes?)\b',re.I)
NON_RES_UNIT_WORDS=re.compile(r'\b(?:retail|commercial|office|offices|storage|industrial|warehouse|shops?|workshops?|air\s+handling|extract|plant|parking|student|hotel|bed|beds)\b',re.I)
NOT_HOUSING_SUPPLY=re.compile(r'\b(?:holiday|temporary|caravans?|static|lodges?|glamping|serviced|short[- ]let|pods?)\b',re.I)
BEDSPACES=re.compile(r'(?<![\w/.,-])\d{1,4}[\s-]*bed(?:room)?s?\b',re.I)
CARE_USE=re.compile(r'\b(?:care\s+home|nursing\s+home|hostel|hotel|student|residential\s+institution|hospice)\b',re.I)
NONRES_UNITS=re.compile(r'(?<![\w/.,-])'+_NUM+r'\s+(?:no\.?\s+)?(?:(?!'+_STOP+r'\b)[\w-]+\s+){0,2}?(shops?|retail\s+units?|offices?|cafes?|cafés?|restaurants?|commercial\s+units?|workshops?)\b',re.I)
NONRES_DEST=re.compile(r'\b(?:hotel|hostel|offices?|shops?|retail|commercial|restaurant|cafes?|school|clinic|storage|warehouse|industrial|community|surgery)\b',re.I)
EXISTING_WORDS=re.compile(r'\b(?:demolition|demolish\w*|removal|loss|clearance|existing|retention|retain\w*|former)\b',re.I)
DEMOLITION_WORDS=re.compile(r'\b(?:demolition|demolish\w*|removal|clearance)\b',re.I)
REPLACE_WORDS=re.compile(r'\breplac\w+\b',re.I)
CONTEXT_WORDS=re.compile(r'\b(?:wider|overall|masterplan|allocation|parent|approved|previously)\b',re.I)
ADJACENT_WORDS=re.compile(r'\b(?:adjoining|adjacent|neighbouring|next\s+to|opposite)\b',re.I)
CREATING=re.compile(r'\b(?:erection|construction|construct\w*|development|creation|provision|provid\w+|formation|comprising|proposed|new|build\w*|redevelopment|replac\w+)\b',re.I)
CHANGE_AWAY=re.compile(r'\b(?:change\s+of\s+use|conversions?|sub-?division|amalgamation)\s+(?:of|to|from)\b',re.I)
WORKS=re.compile(r'\b(?:alterations?|extensions?|refurbishment|renovation|repairs?)\s+(?:of|to)\b',re.I)
INTRODUCES=re.compile(r'\b(?:to|into|as)\b|\bprovid\w+|\bcreat\w+',re.I)
CLAUSE_BREAK=re.compile(r'[.;:,()\n]')
PARENT_MARKER=re.compile(r'\bpursuant\s+to\b',re.I)
WIDER_MARKER=re.compile(r',?\s*\bpart\s+of\s+(?:a\s+|the\s+)?wider\s+(?:scheme|development|site|allocation)\b(?:\s+of)?',re.I)
JOIN=re.compile(r'\s*(?:,\s*and\b|,|;|&|\band\b|\bplus\b|\btogether\s+with\b)\s*(?:(?:the\s+)?(?:erection|construction|conversion|change\s+of\s+use|provision|formation)\s+of\s+(?:an?\s+|the\s+)?[\w\s-]{0,40}?\s+(?:to|into|as)\s+)?\Z',re.I)
MIXED_WORDING=re.compile(r'\b(?:mixed[- ]use|ground[- ]floor|commercial|retail|shops?|offices?|cafes?|restaurants?|workspace|community\s+use)\b',re.I)
REVISED=re.compile(r'\b(?:increase|reduce|decrease|amend|change|vary)\s+(?:the\s+)?(?:number\s+of\s+)?(?:dwellings|homes|houses|flats|apartments|units)?\s*from\s+'+_NUM+r'(?:\s+(?:dwellings|homes|houses|flats|apartments|units))?\s+to\s+'+_NUM+r'\b',re.I)
SECTION_73=re.compile(r'\b(?:section\s*73|s\.?\s*73|variation\s+(?:of|to)|non-?material|amendments?|amend|vary|substitution|substitute|removal\s+of\s+(?:conditions?|condition\s+\d+)|(?:plans?|scheme|dwellings?|permission|development)\s+approved|approved\s+(?:plans?|scheme|under|pursuant|permission))\b',re.I)

RELATED_ROLES={'variation_or_amendment':'AMENDMENT_OF_PARENT','condition_discharge_or_details':'DISCHARGE_OF_PARENT','external_consultation':'AMENDMENT_OF_PARENT','screening_or_scoping_opinion':'PRE_APPLICATION_SIGNAL'}


def _value(token):
    t=token.lower()
    if t in NUMBER_WORDS:return NUMBER_WORDS[t]
    if t.isdigit():return int(t)
    tens,units=re.split(r'[- ]',t);return NUMBER_WORDS[tens]+NUMBER_WORDS[units]


def _classify_mention(text,m):
    """('NEW'|'LOST'|'RETAINED'|'CONTEXT'|'ADJACENT'|'NOT_HOUSING', reason) for one attached dwelling count (R-EXISTING, R-CONTEXT, R-HOUSING)."""
    if NOT_HOUSING_SUPPLY.search(m.group(0)):return 'NOT_HOUSING',None
    after=CLAUSE_BREAK.split(text[m.end():m.end()+40],1)[0]
    if STUDENT.search(m.group(0)) or AFTER_STUDENT.search(after):return 'STUDENT',None      # D4, only where the student wording belongs to THIS count      # only the words up to the end of this clause say what this count is
    if AFTER_REMOVED.search(after):return 'LOST','DEMOLITION'      # "3 dwellings to be demolished": the words AFTER the count say what it is
    if AFTER_RETAINED.search(after):return 'RETAINED',None
    cuts=[c.end() for c in CLAUSE_BREAK.finditer(text,0,m.start())]
    window=text[max(cuts[-1] if cuts else 0,m.start()-120):m.start()]
    if ADJACENT_WORDS.search(window):return 'ADJACENT',None
    inside_existing=bool(EXISTING_WORDS.search(m.group(0)))
    existing=[x.start() for x in EXISTING_WORDS.finditer(window)];creating=[x.start() for x in CREATING.finditer(window)]
    context=[x.start() for x in CONTEXT_WORDS.finditer(window)]
    if context and not (creating and creating[-1]>context[-1]):return 'CONTEXT',None
    away=[t.start() for t in CHANGE_AWAY.finditer(window) if not INTRODUCES.search(window,t.end())]
    works=[t.start() for t in WORKS.finditer(window) if not INTRODUCES.search(window,t.end())]
    if away:return 'LOST','CONVERSION_AWAY'
    if works:return 'RETAINED',None
    if inside_existing or (existing and not (creating and creating[-1]>existing[-1])):
        if DEMOLITION_WORDS.search(window[existing[-1]-0:] if existing else '') or DEMOLITION_WORDS.search(m.group(0)):return 'LOST','DEMOLITION'
        if REPLACE_WORDS.search(window):return 'LOST','REPLACEMENT'
        return 'RETAINED',None
    if REPLACE_WORDS.search(window) and not creating:return 'LOST','REPLACEMENT'
    return 'NEW',None


def _mentions(text):
    """Attached dwelling counts in order, after consuming blocks-of-N products and qualified maxima, with R-UNITS as the only fallback."""
    spans=[];work=text
    for m in PRODUCT.finditer(text):
        spans.append(('PRODUCT',m.start(),m.end(),_value(m.group(1))*_value(m.group(2)),m));work=work[:m.start()]+' '*(m.end()-m.start())+work[m.end():]
    for m in PRODUCT_IN_EACH.finditer(work):
        spans.append(('PRODUCT',m.start(),m.end(),_value(m.group(1))*_value(m.group(2)),m));work=work[:m.start()]+' '*(m.end()-m.start())+work[m.end():]
    for m in UP_TO.finditer(work):
        spans.append(('UP_TO',m.start(),m.end(),_value(m.group(1)),m));work=work[:m.start()]+' '*(m.end()-m.start())+work[m.end():]
    for m in ATTACHED.finditer(work):spans.append(('EXACT',m.start(),m.end(),_value(m.group(1)),m))
    if not [s for s in spans if s[0]!='PRODUCT'] and RESIDENTIAL_WORDING.search(text) and not NON_RES_UNIT_WORDS.search(text):
        for m in BARE_UNITS.finditer(work):spans.append(('EXACT',m.start(),m.end(),int(m.group(1)),m))      # R-UNITS
    spans.sort(key=lambda s:s[1])
    return spans


def _parent_reference(text):
    from .listing_screening import REFERENCE
    for m in REFERENCE.finditer(text):
        if not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',m.group()):return m.group()
    return None


def _first_attached(text):
    for s in _mentions(text):
        if s[0]=='UP_TO':return 'UP_TO:%d'%s[3]
        if s[0] in ('EXACT','PRODUCT'):return s[3]
    return None


def _category(text,application_type):
    from app.scrapers.unit_filter import classify_application_category
    c=classify_application_category(text)
    amend=SECTION_73.search(text);create=CREATING.search(text);first_count=ATTACHED.search(text)
    if c=='primary_residential' and _parent_reference(text) and amend and (create is None or amend.start()<=create.start()) and (first_count is None or amend.start()<=first_count.start()):c='variation_or_amendment'      # amending wording that leads the text (before any creation clause or count), with a named permission: an amendment, not a new scheme; a text that opens with a creation clause stays a new scheme
    return c


def _blank(category,role,admission,reason,proposed=NE,**over):
    out=dict(rule_version=RULE_VERSION,category=category,scheme_role=role,proposed_total=proposed,approved_total=NE,lost=NE,existing=NE,net=NE,non_residential_units={},parent_context=None,admission=admission,reason=reason,
             records=[],source_kind=SOURCE_KIND)
    out.update(over);return out


def _nonres(text):
    out={}
    for m in NONRES_UNITS.finditer(text):
        w=m.group(2).lower();kind='retail' if re.match(r'shop|retail',w) else 'office' if w.startswith('office') else 'food_and_drink' if re.match(r'caf|restaurant',w) else 'commercial'
        out[kind]=out.get(kind,0)+_value(m.group(1))
    return out


def assess_proposal(text,*,application_type=None,threshold=10,proposal_state='PRESENT_VALUE',evidence=(),scope_relations=(),assessments=()):
    """Assess one proposal. `evidence` may carry further supported count records (other source kinds, other bases, with relations); they are resolved by count_evidence exactly as the specification says, and
    never by this module's text rules. Returns the four count metrics, the non-residential units, the category, scheme role, parent context, the size-gate admission outcome and its reason code, the proposed
    record the text supports, and the labelled headline."""
    text=text if isinstance(text,str) else ''
    if proposal_state!='PRESENT_VALUE' or not text.strip() or len(text)>MAX_TEXT:return _blank('unknown','NEW_SCHEME','RETAIN_UNUSABLE_PROPOSAL','PROPOSAL_NOT_USABLE')
    category=_category(text,application_type);role='PHASE_OF_PARENT' if category=='reserved_matters' else RELATED_ROLES.get(category,'NEW_SCHEME')
    ref=_parent_reference(text)
    if role in ('AMENDMENT_OF_PARENT','DISCHARGE_OF_PARENT','PRE_APPLICATION_SIGNAL'):
        if role=='PRE_APPLICATION_SIGNAL':return _blank(category,role,'RETAIN_WATCHLIST','SCREENING_OR_SCOPING_OPINION')
        relation='DISCHARGE_OF' if role=='DISCHARGE_OF_PARENT' else ('AMENDMENT_TO' if re.search(r'\bamendment\s+to\b',text,re.I) else 'VARIATION_OF')
        parent=dict(reference=ref,context_count=_first_attached(text),relation=relation)
        r=REVISED.search(text)
        if r:parent.update(context_count=_value(r.group(1)),revised_total=_value(r.group(2)))      # R-AMEND: only a stated resulting total is a revised total
        return _blank(category,role,'RETAIN_RELATED_TO_PARENT','DISCHARGE_OF_PARENT_CONDITIONS' if role=='DISCHARGE_OF_PARENT' else 'AMENDMENT_OF_PARENT',parent_context=parent)
    own,parent=text,None
    if role=='PHASE_OF_PARENT':
        m=PARENT_MARKER.search(text)
        if m:own=text[:m.start()];parent=dict(reference=ref,context_count=_first_attached(text[m.end():]),relation='PURSUANT_TO')
        elif ref:parent=dict(reference=ref,context_count=None,relation='PURSUANT_TO')      # reserved matters always keep their parent relationship
    else:
        m=WIDER_MARKER.search(text)
        if m:own=text[:m.start()];parent=dict(reference=ref,context_count=_first_attached(text[m.end():]),relation='PART_OF_WIDER_SCHEME')
    nonres=_nonres(own)
    ambiguous=None
    if GROUP_OF_UNCLEAR.search(own):ambiguous=('ROUTE_COUNT_UNCONFIRMED','AMBIGUOUS_PER_GROUP_COUNT')
    elif HUNDRED.search(own):ambiguous=('ROUTE_COUNT_UNCONFIRMED','COUNT_WORDING_NOT_PARSED')
    # ---- classify every attached count in the application's own words
    new=[];lost=[];retained=[];not_housing=False;student=False
    for kind,a,b,value,m in _mentions(own):
        c,why=_classify_mention(own,m)      # a multiplied block count is classified exactly like any other count BEFORE it is assigned: demolishing 2 blocks of 6 flats each loses 12, it does not propose 12
        if c=='NEW':new.append((kind,a,b,value))
        elif c=='LOST':lost.append((a,b,value,why))
        elif c=='RETAINED':retained.append((a,b,value))
        elif c=='NOT_HOUSING':not_housing=True
        elif c=='STUDENT':student=True
    if student and not ambiguous:      # D4: student cluster flats and beds are not dwelling supply; alongside genuine dwellings the scheme is for review, never guessed
        ambiguous=('ROUTE_COUNT_UNCONFIRMED','STUDENT_ACCOMMODATION_IN_MIXED_SCHEME') if new else ('RETAIN_NOT_RESIDENTIAL_SUPPLY','STUDENT_ACCOMMODATION')
    # residential wording that is NOT merely the description of existing or lost stock (E17 "12 flats to a hotel" has none left; "residential flats and a ground floor shop" has)
    stripped=own
    for a,b,*_ in sorted(lost+retained,reverse=True):stripped=stripped[:a]+' '*(b-a)+stripped[b:]
    res_left=bool(RESIDENTIAL_WORDING.search(stripped))
    lost_total=sum(v for _,_,v,_ in lost) if lost else None
    existing_total=(sum(v for _,_,v,_ in lost)+sum(v for _,_,v in retained)) if (lost or retained) else None
    works_only=bool(retained) and not lost
    # ---- the proposed quantity (R-SUM, R-PRODUCT, qualified maxima)
    proposed=NE;reason=None;value=None
    if ambiguous:new=[]
    if new:
        up=[n for n in new if n[0]=='UP_TO']
        if up and len(new)==1:proposed='UP_TO:%d'%up[0][3];value=proposed
        elif up:proposed=NE;reason='MULTIPLE_PROPOSED_DWELLING_COUNTS'
        else:
            ok=all(JOIN.match(own[new[i][2]:new[i+1][1]]) for i in range(len(new)-1))
            vals=[n[3] for n in new]
            if len(vals)>=3 and any(v==sum(vals)-v for v in vals):ok=False;reason='POSSIBLE_BREAKDOWN_OF_A_TOTAL'      # "36 dwellings, 18 houses and 18 flats": a total plus its breakdown is never added
            if len(vals)>=2 and len({(n[0],n[3],own[n[1]:n[2]].lower()) for n in new})<len(new):ok=False;reason='REPEATED_COUNT'      # the same figure twice is a repeat or a breakdown, not two schemes
            if ok:proposed=sum(n[3] for n in new);value=proposed
            else:proposed=NE;reason=reason or 'MULTIPLE_PROPOSED_DWELLING_COUNTS'
    # ---- outcomes without a proposed quantity
    admission=None
    if value is None:
        if ambiguous:admission,reason=ambiguous
        elif reason:admission,reason='ROUTE_COUNT_UNCONFIRMED',reason
        elif not_housing:proposed,admission,reason=NONE,'RETAIN_NOT_RESIDENTIAL_SUPPLY','NOT_HOUSING_SUPPLY'
        elif BEDSPACES.search(own) and CARE_USE.search(own):admission,reason='RETAIN_NOT_RESIDENTIAL_SUPPLY','BEDS_NOT_DWELLINGS'
        elif role=='PHASE_OF_PARENT':admission,reason='ROUTE_COUNT_UNCONFIRMED','RESERVED_MATTERS_WITHOUT_STATED_COUNT'      # no count in a reserved-matters clause is a question for investigation, never "no residential created"
        elif res_left and (nonres or NONRES_DEST.search(stripped) or MIXED_WORDING.search(stripped)):
            admission,reason='ROUTE_COUNT_UNCONFIRMED','MIXED_USE_WITHOUT_STATED_RESIDENTIAL_COUNT'      # explicit residential wording alongside commercial use, but no count
            if category in ('primary_residential','unknown'):category='mixed_use'
        elif lost or retained or nonres or not res_left or NONRES_DEST.search(stripped):proposed,admission,reason=NONE,'RETAIN_NOT_RESIDENTIAL_SUPPLY','NO_RESIDENTIAL_CREATED'
        else:admission,reason='ROUTE_COUNT_UNCONFIRMED','RESIDENTIAL_WITHOUT_STATED_COUNT'
        if lost and not retained and category=='primary_residential':category='non_target_admin_or_minor'      # change of use away from housing
    # ---- loss, existing and net (proposed basis; NONE counts as 0; nothing inferred)
    lost_out=lost_total if lost_total is not None else (NONE if works_only else NE)
    pn=0 if proposed==NONE else (proposed if isinstance(proposed,int) else None);dn=0 if lost_out==NONE else (lost_out if isinstance(lost_out,int) else None)
    net=pn-dn if pn is not None and dn is not None else NE
    if nonres and value is not None and category=='primary_residential':category='mixed_use'
    records=[]
    if value is not None:records=[dict(id='t1',basis=ce.PROPOSED,scope='whole',value=value,source_kind=SOURCE_KIND,document_date=None,revision=None,qualifier='outline' if category=='outline_application' else None,relations={})]
    allrec=records+list(evidence)
    if allrec:
        size=ce.size_outcome(allrec,threshold,scope_relations,assessments)
        if size in ('ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','RETAIN_BELOW_THRESHOLD'):
            admission=size
            reason={'ADMIT_SCHEME':'PROPOSED_TOTAL_AT_OR_ABOVE_THRESHOLD','RETAIN_BELOW_THRESHOLD':'PROPOSED_TOTAL_BELOW_THRESHOLD'}.get(size) or ('QUALIFIED_MAXIMUM_AT_OR_ABOVE_THRESHOLD' if any(isinstance(r['value'],str) for r in allrec) and not any(ce.basis_class(ce.resolve_basis(allrec,b,scope_relations,assessments),threshold,None)!=ce.NO_MATCH and ce.resolve_basis(allrec,b,scope_relations,assessments)['state'] in (ce.CONFLICT,ce.ALTERNATIVES) for b in (ce.PROPOSED,ce.APPROVED)) else 'COUNT_CONFLICT')
    out=_blank(category,role,admission,reason,proposed=proposed,lost=lost_out,existing=existing_total if existing_total is not None else NE,net=net,non_residential_units=nonres,parent_context=parent,records=records)
    out['headline']=ce.headline(allrec,scope_relations,assessments)
    return out
