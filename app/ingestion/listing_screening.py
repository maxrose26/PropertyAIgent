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


def _screen_v1(row):
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


RULE_V1='manchester-listing-screen-assessment-v1'
RULE_V3='manchester-listing-screen-assessment-v3'


def council_unit_threshold(council):
    """The council's CONFIGURED platform admission threshold (config/councils.yaml `unit_threshold`; specification 035 decision D6: a platform threshold, not a buyer parameter)."""
    from app.config import get_council
    return get_council(council).unit_threshold


def screen_row(row,*,rule_version=RULE_V1,council=None,unit_threshold=None):
    """Record-level screening.

    `rule_version=RULE_V1` (the DEFAULT) is the original behaviour, byte for byte: every existing caller, stored result and stored-versus-recomputed comparison is unchanged, and it takes no threshold.
    `RULE_V3` (specification 035, Phase A) is OPT-IN per call and ADDITIVE: the v1 result is carried unchanged and a `count_assessment` block is added (the four counts, category, scheme role, parent context,
    size-gate admission and headline), with `routing_authority = "count_assessment"`. The v1-shaped `disposition` of a v3 result is informational and must not route anything (use `routing_of`). Nothing in the
    repository selects v3, nothing re-screens an existing item, and a v3 result is a NEW result under its own rule version, never an edit of an old one.
    BOUNDEDNESS: v3 calls the legacy qualifier first (through the v1 result). That qualifier's digit-run stall is fixed in app/scrapers/unit_filter.py (UNIT_COUNT_PATTERNS) and end-to-end screening is tested
    bounded under a hard timeout (tests/test_unit_filter_digit_runs.py). Residual limits are listed in the pull request that fixed it."""
    if rule_version not in (RULE_V1,RULE_V3):raise ValueError('UNKNOWN_SCREENING_RULE_VERSION')
    if rule_version==RULE_V1:
        if council is not None or unit_threshold is not None:raise ValueError('RULE_V1_TAKES_NO_THRESHOLD')
        return _screen_v1(row)
    if (council is None)==(unit_threshold is None):raise ValueError('RULE_V3_REQUIRES_EXACTLY_ONE_OF_COUNCIL_OR_THRESHOLD')
    threshold=council_unit_threshold(council) if council is not None else unit_threshold
    if type(threshold) is not int or threshold<=0:raise ValueError('INVALID_SCREENING_THRESHOLD')
    from .count_assessment import assess_proposal
    out=_screen_v1(row);f=row['fields']['proposal']
    state=f['state'] if not f.get('truncated') else 'TRUNCATED'
    out['rule_version']=RULE_V3
    out['routing_authority']='count_assessment'
    out['count_assessment']=assess_proposal(f.get('value') or '',proposal_state=state,threshold=threshold)
    out['count_assessment_threshold']=threshold
    return out


# The allowed routing outcomes per rule version. A value outside the named version's vocabulary fails closed (specification 035 section 6A).
ROUTING_VOCABULARY={
    RULE_V1:frozenset({'SUPPORTED_PROCESSING_PRIORITY','RELATED_APPLICATION_FOLLOW_THROUGH','DEEPER_PROCESSING_EXCLUDED_FOR_THIS_SLICE','INSUFFICIENT_EVIDENCE'}),
    RULE_V3:frozenset({'ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT','ROUTE_COUNT_UNCONFIRMED','RETAIN_BELOW_THRESHOLD','RETAIN_NOT_RESIDENTIAL_SUPPLY','RETAIN_RELATED_TO_PARENT','RETAIN_WATCHLIST','RETAIN_UNUSABLE_PROPOSAL'})}


def routing_of(result):
    """The ONE authoritative routing field of a stored or fresh screening result, chosen by its rule version (specification 035 section 6A): ('disposition', value) for v1 results,
    ('count_assessment', admission) for v3 results. Any other rule version, a missing field, or a result whose authority label disagrees with its rule version fails closed."""
    version=result.get('rule_version')
    if version==RULE_V1 and 'routing_authority' not in result and 'disposition' in result:
        outcome=result['disposition'];authority='disposition'
    elif version==RULE_V3 and result.get('routing_authority')=='count_assessment' and isinstance(result.get('count_assessment'),dict):
        outcome=result['count_assessment'].get('admission');authority='count_assessment'
    else:raise ValueError('ROUTING_AUTHORITY_UNRESOLVED')
    if not isinstance(outcome,str) or outcome not in ROUTING_VOCABULARY[version]:raise ValueError('ROUTING_OUTCOME_NOT_IN_VOCABULARY')      # unknown, misspelt, wrong-version or non-string outcomes fail closed
    return authority,outcome


# ------------------------------------------------------------------ slice 1: explicit rule selection, configuration-bound identity, version-aware eligibility
V1_CONTRACT='listing-screen-v1'
V3_CONTRACT='listing-screen-v3'
SCREENING_CONTRACT_RULES={V1_CONTRACT:RULE_V1,V3_CONTRACT:RULE_V3}      # a contract name fixes its rule version; there is no other way to select v3


# The code that produces a saved v3 assessment, including its embedded v1 result (listing_screening._screen_v1 -> unit_filter). Bound by byte digest so a change to any of it can never silently share an identity.
# `ledger.py` is also loaded (for `digest`) but is bound through DIGEST_PROBE instead of by file, so an unrelated ledger edit does not re-key every identity.
BOUND_MODULES=('app/ingestion/listing_screening.py','app/ingestion/count_assessment.py','app/ingestion/count_evidence.py','app/scrapers/unit_filter.py')
DIGEST_PROBE_VECTOR={'b':[1,2.5,{'z':None,'a':'\u00e9'}],'a':True}
V1_RESULT_KEYS=('citations','commercial_relevance','disposition','existing_category','existing_classification','permanent_exclusion','progress','proposal_usable','raw_generic_count','residential_dwelling_count','retained','site_relationship')      # what _screen_v1 returns, less rule_version


def lf_sha256(raw):
    """sha256 of bytes with CRLF normalised to LF (never a text-mode read)."""
    return hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()


def code_binding(files=None):
    """sha256 over the canonical list of {path, sha256(LF-normalised bytes)} of the bound modules. Bytes are read in binary and CRLF is normalised to LF, so a Windows autocrlf checkout and a Linux checkout agree.
    Fails closed if a bound file cannot be read."""
    from pathlib import Path
    from .ledger import digest
    base=Path(__file__).resolve().parents[2];entries=[]
    for rel in (files or BOUND_MODULES):
        try:raw=(base/rel).read_bytes()
        except OSError:raise ValueError('CODE_BINDING_UNAVAILABLE') from None
        entries.append(dict(path=rel,sha256=lf_sha256(raw)))
    return digest(entries)


def digest_probe():
    """The digest of a fixed vector: detects a change in the canonical-JSON `ledger.digest` function without binding the whole of ledger.py."""
    from .ledger import digest
    return digest(DIGEST_PROBE_VECTOR)


def qualifier_output_of(result):
    """The embedded v1 result of a screening result: everything the v1 qualifier and citation extractor produced, without the v3 additions."""
    return {k:result[k] for k in V1_RESULT_KEYS}


class ScreeningRule:
    """One explicitly registered screening rule. v1 takes no threshold. v3 carries the council-configured threshold FROZEN at construction (read once, here, never per record).
    `link_related` (default True, the disposable-ledger behaviour) controls only whether `Coordinator.screening` stores a snapshot of other assessments; production registrations set it False (history is a
    separate bounded read). It is not decision-affecting and so is not part of the identity."""
    def __init__(self,rule_version,*,unit_threshold=None,council=None,link_related=True):
        if rule_version not in (RULE_V1,RULE_V3):raise ValueError('UNKNOWN_SCREENING_RULE_VERSION')
        if rule_version==RULE_V1:
            if unit_threshold is not None or council is not None:raise ValueError('RULE_V1_TAKES_NO_THRESHOLD')
        else:
            if (unit_threshold is None)==(council is None):raise ValueError('RULE_V3_REQUIRES_EXACTLY_ONE_OF_COUNCIL_OR_THRESHOLD')
            if council is not None:unit_threshold=council_unit_threshold(council)
            if type(unit_threshold) is not int or unit_threshold<=0:raise ValueError('INVALID_SCREENING_THRESHOLD')
        # Frozen: the threshold and the configuration binding are computed once, here, and cannot be reassigned.
        if type(link_related) is not bool:raise ValueError('INVALID_LINK_RELATED')
        self._rule_version=rule_version;self._unit_threshold=unit_threshold;self._link_related=link_related
        self._config=None if rule_version==RULE_V1 else self._build_config()

    rule_version=property(lambda self:self._rule_version)
    unit_threshold=property(lambda self:self._unit_threshold)
    link_related=property(lambda self:self._link_related)

    def __setattr__(self,name,value):
        if name.startswith('_') and name not in self.__dict__:object.__setattr__(self,name,value)
        else:raise AttributeError('SCREENING_RULE_IS_FROZEN')

    def _build_config(self):
        from .count_assessment import RULE_VERSION,MAX_TEXT
        return dict(rule_version=RULE_V3,count_spec_version=RULE_VERSION,assessor='count_assessment',unit_threshold=self._unit_threshold,max_text_chars=MAX_TEXT,
                    code_binding=code_binding(),digest_probe=digest_probe())

    def contract(self):
        return V1_CONTRACT if self.rule_version==RULE_V1 else V3_CONTRACT

    def config(self):
        """Every decision-affecting setting of a v3 assessment. Changing any of them gives a different config_sha256 and so a different assessment identity."""
        return None if self._config is None else dict(self._config)

    def screen(self,record):
        if self.rule_version==RULE_V1:return screen_row(record)
        return screen_row(record,rule_version=RULE_V3,unit_threshold=self.unit_threshold)


def screening_plan_binding(rule):
    """(plan binding, config_sha256) of a v3 rule: the `screening` object a batch plan carries and the digest a v3 registration lists. v1 has none."""
    from .ledger import digest
    if not isinstance(rule,ScreeningRule) or rule.rule_version!=RULE_V3:raise ValueError('V3_SCREENING_RULE_REQUIRED')
    sha=digest(rule.config())
    return dict(contract=V3_CONTRACT,config_sha256=sha),sha


def assessment_identity(record,rule):
    """(record_sha256, config, config_sha256, revision) of a v3 assessment of one source record. The revision is the ledger item revision: it binds the source record AND the configuration, so the same
    record under the same configuration is one item (idempotent) and a changed threshold is a different item. v1 keeps its historical revision (the record digest) and is not handled here."""
    from .ledger import digest
    config=rule.config()
    if config is None:raise ValueError('RULE_V1_HAS_NO_CONFIGURATION_BINDING')
    record_sha=digest(record);config_sha=digest(config)
    return record_sha,config,config_sha,digest(dict(record_sha256=record_sha,config_sha256=config_sha))


IDENTITY_ELIGIBLE={RULE_V1:frozenset({'SUPPORTED_PROCESSING_PRIORITY','RELATED_APPLICATION_FOLLOW_THROUGH'}),RULE_V3:frozenset({'ADMIT_SCHEME','ADMIT_FOR_ASSESSMENT'})}


def identity_admission_eligible(result,item=None):
    """True only when a stored screening result's ONE authoritative routing outcome (`routing_of`) permits creating a pending identity. It is the first condition of the two identity gates, never the only one:
    every existing factual-admission check still applies. Neither version's eligible outcome writes a count or confirms qualification. A legacy checkpoint with no rule version (the shape the existing tests
    build) is read as v1. Anything unresolvable, unknown or not in the named version's vocabulary is NOT eligible (fail closed)."""
    if not isinstance(result,dict) or not result:return False
    if 'rule_version' not in result and 'routing_authority' not in result:
        # Historical v1 shape. When the item is supplied it must be a v1 screening item: a versionless result is eligible only under listing-screen-v1. Any other contract (v3, an unknown listing-screen-*
        # name, or an arbitrary name) is refused, so a v3 item cannot be laundered through its informational v1 disposition.
        if item is not None and item.get('contract')!=V1_CONTRACT:return False
        d=result.get('disposition')
        return isinstance(d,str) and d in IDENTITY_ELIGIBLE[RULE_V1]
    try:authority,outcome=routing_of(result)
    except ValueError:return False
    if item is not None:
        # When the stored screening item is supplied it must be the item this result claims to be: contract matches the rule version, and a v3 revision matches the recorded assessment revision.
        if SCREENING_CONTRACT_RULES.get(item.get('contract'))!=result['rule_version']:return False
        if result['rule_version']==RULE_V3 and item.get('revision')!=result.get('assessment_revision'):return False
    return outcome in IDENTITY_ELIGIBLE[result['rule_version']]
