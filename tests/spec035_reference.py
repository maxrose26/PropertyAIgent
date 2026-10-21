"""Executable reference for Specification 035 sections 3A-3F (count bases, evidence status, scope relations and bounds, owner relationship assessments, headline, search certainty over a size range, size admission,
read model). This is the SPECIFICATION written as code so its examples can be checked; it is not application code, is imported by nothing in app/, and changes no behaviour. The implementation proposal reproduces it
(and these examples are its acceptance tests). Pure functions over plain dicts."""
PROPOSED='PROPOSED';APPROVED='APPROVED';EITHER='EITHER'
PERMISSION_SOURCES={'DECISION_NOTICE','APPROVED_PLANS_SCHEDULE'}      # only these can establish an APPROVED count: a form, proposal, statement or officer recommendation cannot (and no assessment can)
RESOLVED='RESOLVED';QUALIFIED='QUALIFIED_MAXIMUM';CONFLICT='CONFLICT_UNRESOLVED';ALTERNATIVES='ALTERNATIVE_PERMISSIONS';NOT_ESTABLISHED='NOT_ESTABLISHED';PER_SCOPE='PER_SCOPE'
MEETS='MEETS_SIZE_FILTER';POSSIBLE='POSSIBLE_SIZE_MATCH';NO_MATCH='NONE'
LABELS={MEETS:'Meets size filter',POSSIBLE:'Possible size match'}
LABEL_NOTE='A size match is not a confirmed quantity, a planning approval or a buyer fit.'
DOCUMENT_STATED='DOCUMENT_STATED';REVIEWER_ASSESSED='REVIEWER_ASSESSED'
ASSESSMENT_KINDS={'SUPERSEDES','NON_OVERLAPPING_PARTS','COMMON_DEVELOPMENT','EXHAUSTS_DEVELOPMENT'}
DEFAULT_METRIC='residential_dwellings'
INF=float('inf')


def parse(value):
    """('EXACT', n) or ('UP_TO', n)."""
    if isinstance(value,int) and not isinstance(value,bool):return 'EXACT',value
    if isinstance(value,str) and value.startswith('UP_TO:'):return 'UP_TO',int(value.split(':')[1])
    raise ValueError('BAD_COUNT_VALUE')


def supported_minimum(record):
    """"Up to N" has NO evidenced positive lower bound unless one is separately supported: a positive value, a source kind and the literal words. Otherwise the lower bound is 0."""
    m=record.get('minimum')
    if isinstance(m,dict) and isinstance(m.get('value'),int) and not isinstance(m.get('value'),bool) and m['value']>=1 and m.get('source_kind') and (m.get('quote') or '').strip():return m['value']
    return None


def valid_assessment(a,records):
    """An owner relationship assessment (D10) is evidence of a relationship, labelled reviewer-assessed. It counts only if made by an authenticated owner with actor, timestamp, rationale, citations and an exact scope,
    and its subject and target exist. It never creates permission evidence (it cannot touch a record's source kind), never changes planning status, and never establishes legal supersession."""
    ids={r['id']:r for r in records}
    ok=(a.get('kind') in ASSESSMENT_KINDS and a.get('authenticated') is True and bool(str(a.get('actor') or '').strip()) and bool(str(a.get('timestamp') or '').strip())
        and bool(str(a.get('rationale') or '').strip()) and isinstance(a.get('citations'),list) and bool(a['citations']) and all(str(c).strip() for c in a['citations']))
    if not ok:return False
    if a['kind']!='SUPERSEDES':return isinstance(a.get('scopes'),list) and len(a['scopes'])>=2 and all(str(x).strip() for x in a['scopes'])      # a scope relation names the exact scopes it covers
    if a['kind']=='SUPERSEDES':
        s,t=ids.get(a.get('subject')),ids.get(a.get('target'))
        return bool(s and t and s['basis']==t['basis'] and s.get('scope','whole')==t.get('scope','whole')==a['scope'])      # exact scope: the assessment names the one scope both records are in
    return True


def supported_relation(relation,kind):
    """A document-stated scope relation: a source kind and the literal words. A phase LABEL alone proves nothing."""
    return relation.get('relation')==kind and bool(relation.get('source_kind')) and bool((relation.get('quote') or '').strip())


def _assessed_relation(a,kind):
    return a.get('kind')==kind


def _scope_state(active,historical,assessed_supersession):
    """One scope of one basis. `active` are records not superseded by an explicit statement (document-stated, or an owner assessment flagged as such)."""
    if not active:return dict(state=NOT_ESTABLISHED,competing=[],historical=historical)
    values={(parse(r['value'])) for r in active}
    competing=[(r['id'],r['value']) for r in active]
    if len(values)==1:
        kind,n=next(iter(values))
        out=dict(state=RESOLVED if kind=='EXACT' else QUALIFIED,quantity=n if kind=='EXACT' else None,maximum=n if kind=='UP_TO' else None,qualifier=active[0].get('qualifier'),competing=competing,historical=historical)
        if kind=='UP_TO':
            mins=[supported_minimum(r) for r in active if supported_minimum(r)];out['minimum']=max(mins) if mins else None
        if assessed_supersession:out.update(relationship_basis=REVIEWER_ASSESSED,legal_supersession_established=False)
        return out
    # distinct figures that nothing relates: never resolved by date, upload order, size or source rank
    alt=any('alternative_to' in r.get('relations',{}) for r in active)
    return dict(state=ALTERNATIVES if alt else CONFLICT,competing=competing,historical=historical)


def _covers(relations,assessments,kind,names):
    """Is there a document-stated (or valid owner-assessed) relation of this kind covering exactly these scopes?"""
    names=frozenset(names)
    for x in relations:
        if supported_relation(x,kind) and frozenset(x['scopes'])>=names:return DOCUMENT_STATED
    for a in assessments:
        if _assessed_relation(a,kind) and a.get('scopes') and frozenset(a['scopes'])>=names:return REVIEWER_ASSESSED
    return None


def resolve_basis(records,basis,scope_relations=(),assessments=()):
    recs=[r for r in records if r['basis']==basis]
    unsupported=[]
    if basis==APPROVED:
        unsupported=[r['id'] for r in recs if r['source_kind'] not in PERMISSION_SOURCES]      # an assessment can never move a record out of this list
        recs=[r for r in recs if r['source_kind'] in PERMISSION_SOURCES]
    valid=[a for a in assessments if valid_assessment(a,records)]
    rejected=[a.get('id') for a in assessments if not valid_assessment(a,records)]
    scopes={}
    for r in recs:scopes.setdefault(r.get('scope','whole'),[]).append(r)
    per={}
    for scope,group in scopes.items():
        ids={r['id'] for r in group}
        stated={r['relations']['supersedes'] for r in group if r.get('relations',{}).get('supersedes') in ids}      # only an EXPLICIT supersedes between two supported records of the same scope
        assessed={a['target'] for a in valid if a['kind']=='SUPERSEDES' and a['subject'] in ids and a['target'] in ids}-stated
        active=[r for r in group if r['id'] not in stated|assessed]
        per[scope]=_scope_state(active,sorted(stated|assessed),bool(assessed))
    if not per:return dict(state=NOT_ESTABLISHED,scopes={},unsupported_as_approved=unsupported,rejected_assessments=rejected)
    if len(per)==1:
        out=dict(next(iter(per.values())));out['scopes']=per;out['unsupported_as_approved']=unsupported;out['rejected_assessments']=rejected;return out
    names=set(per)
    metrics={r.get('metric',DEFAULT_METRIC) for r in recs if r.get('scope','whole') in names}
    non_overlap=_covers(scope_relations,valid,'NON_OVERLAPPING_PARTS',names)
    if all(v['state']==RESOLVED for v in per.values()) and non_overlap and len(metrics)==1:
        out=dict(state=RESOLVED,quantity=sum(v['quantity'] for v in per.values()),scopes=per,combined=True,competing=[],historical=[],unsupported_as_approved=unsupported,rejected_assessments=rejected)
        if non_overlap==REVIEWER_ASSESSED:out.update(relationship_basis=REVIEWER_ASSESSED,legal_supersession_established=False)
        return out
    out=dict(state=PER_SCOPE,overlap='UNRESOLVED',scopes=per,combined=False,competing=[],historical=[],unsupported_as_approved=unsupported,rejected_assessments=rejected)
    # Bounds. The UNION of the specified scopes is at least its largest member and at most all added (true however the scopes overlap), but only for compatible counts (one basis, one metric).
    if len(metrics)==1:
        sc=[scenarios(v) for v in per.values()]
        union=(max(min(lo for lo,_ in p) for p in sc),sum(max(hi for _,hi in p) for p in sc))
        membership=_covers(scope_relations,valid,'COMMON_DEVELOPMENT',names) or _covers(scope_relations,valid,'EXHAUSTS_DEVELOPMENT',names)
        exhaustion=_covers(scope_relations,valid,'EXHAUSTS_DEVELOPMENT',names)
        # A WHOLE-SCHEME total needs supported common-development membership; its upper bound exists only with evidence that those scopes exhaust the development.
        scheme=None if not membership else ((union[0],union[1]) if exhaustion else (union[0],None))
        out.update(union_bounds=union,membership=bool(membership),exhaustion=bool(exhaustion),scheme_bounds=scheme)
        assessed_used=REVIEWER_ASSESSED in (membership,exhaustion)
        if assessed_used:out.update(relationship_basis=REVIEWER_ASSESSED,legal_supersession_established=False)
    else:out.update(union_bounds=None,membership=False,exhaustion=False,scheme_bounds=None)
    return out


def _value_interval(record_or_value,state_min=None):
    kind,n=parse(record_or_value)
    if kind=='EXACT':return n,n
    return (state_min or 0),n      # "up to N" can be anything from 0 to N unless a positive minimum is separately supported


def scenarios(state):
    """The ways the count of the thing being asked about could be, each an interval (lo, hi) (hi None = unbounded): the real value is somewhere inside it. Conflicting or alternative figures are SEPARATE scenarios.
    For several scopes whose overlap is unresolved this is the whole-scheme interval ONLY when common-development membership is supported (and bounded above only if the scopes exhaust it); otherwise it is the
    bounds of their union, which is not a whole-scheme total (search then judges each scope on its own)."""
    s=state['state']
    if s==NOT_ESTABLISHED:return []
    if s==PER_SCOPE:
        if state.get('scheme_bounds'):return [state['scheme_bounds']]
        parts=[scenarios(v) for v in state['scopes'].values()]
        return [(max(min(lo for lo,_ in p) for p in parts),sum(max(hi for _,hi in p) for p in parts))]      # the union's bounds (what the display may say about these scopes together)
    if s==RESOLVED:return [(state['quantity'],state['quantity'])]
    if s==QUALIFIED:return [(state.get('minimum') or 0,state['maximum'])]
    return [_value_interval(v) for _,v in state['competing']]


def _scenario_class(interval,size_min,size_max):
    lo,hi=interval;hi=INF if hi is None else hi
    if hi<size_min or (size_max is not None and lo>size_max):return 'OUT'
    if lo>=size_min and (size_max is None or hi<=size_max):return 'IN'
    return 'STRADDLE'


def _fold(classes):
    if not classes or all(c=='OUT' for c in classes):return NO_MATCH
    return MEETS if all(c=='IN' for c in classes) else POSSIBLE


def basis_result(state,size_min=10,size_max=None):
    """(class, level, scopes). Certainty is judged against the ENTIRE selected range. Several scopes with no supported common-development membership are judged one scope at a time: that is a SCOPE-level
    result naming the scopes that earn it, never a statement about the whole scheme."""
    if state['state']==PER_SCOPE and not state.get('scheme_bounds'):
        per={n:basis_class(v,size_min,size_max) for n,v in state['scopes'].items()}
        best=MEETS if MEETS in per.values() else POSSIBLE if POSSIBLE in per.values() else NO_MATCH
        return best,'SCOPE',sorted(n for n,c in per.items() if c==best and best!=NO_MATCH)
    return _fold([_scenario_class(i,size_min,size_max) for i in scenarios(state)]),'SCHEME',[]


def basis_class(state,size_min=10,size_max=None):
    return basis_result(state,size_min,size_max)[0]


def quantity_status(state):
    if state['state']==PER_SCOPE and state.get('scheme_bounds'):return 'WHOLE_SCHEME_BOUNDS_ONLY'
    return {RESOLVED:'CONFIRMED_QUANTITY',QUALIFIED:'QUALIFIED_QUANTITY',CONFLICT:'QUANTITY_UNDER_REVIEW',ALTERNATIVES:'QUANTITY_UNDER_REVIEW',PER_SCOPE:'QUANTITY_UNDER_REVIEW',NOT_ESTABLISHED:'NOT_ESTABLISHED'}[state['state']]


def search_match(records,basis_choice,size_min=10,size_max=None,scope_relations=(),assessments=()):
    """`basis_choice` APPROVED, PROPOSED or EITHER (the discovery default); the selected size range is [size_min, size_max]. Returns the class, the bases that caused it, each causing basis's quantity status and
    whether the result is about the whole scheme or only named scopes (a size match says nothing about quantity certainty, planning approval or buyer fit)."""
    bases=(APPROVED,PROPOSED) if basis_choice==EITHER else (basis_choice,)
    states={b:resolve_basis(records,b,scope_relations,assessments) for b in bases}
    res={b:basis_result(s,size_min,size_max) for b,s in states.items()}
    best=MEETS if any(r[0]==MEETS for r in res.values()) else POSSIBLE if any(r[0]==POSSIBLE for r in res.values()) else NO_MATCH
    by=sorted(b for b,r in res.items() if r[0]==best and best!=NO_MATCH)
    level='SCOPE' if by and all(res[b][1]=='SCOPE' for b in by) else 'SCHEME'
    scopes=sorted({n for b in by for n in res[b][2]})
    return dict(match=best,matched_by=by,quantity_status={b:quantity_status(states[b]) for b in by},level=level,scopes=scopes if level=='SCOPE' else [])


def dedupe_by_scheme(results):
    """One row per scheme identity: the best class, the union of causing bases, every contributing application kept."""
    rank={MEETS:2,POSSIBLE:1,NO_MATCH:0};out={}
    for r in results:
        o=out.setdefault(r['scheme_id'],dict(scheme_id=r['scheme_id'],match=NO_MATCH,matched_by=set(),applications=[]))
        o['applications'].append(r['application'])
        if rank[r['match']]>rank[o['match']]:o['match']=r['match'];o['matched_by']=set(r['matched_by'])
        elif r['match']==o['match']:o['matched_by']|=set(r['matched_by'])
    return [dict(v,matched_by=sorted(v['matched_by']),applications=sorted(v['applications'])) for v in sorted(out.values(),key=lambda v:v['scheme_id'])]


def _qty(state):
    if state['state']==QUALIFIED:
        return 'minimum %d, up to %d'%(state['minimum'],state['maximum']) if state.get('minimum') else 'up to %d'%state['maximum']
    return '%d'%state['quantity']


def headline(records,scope_relations=(),assessments=()):
    """The labelled headline quantity. Never silently chooses between competing figures; a reviewer-assessed relationship is always labelled as such."""
    ap=resolve_basis(records,APPROVED,scope_relations,assessments);pr=resolve_basis(records,PROPOSED,scope_relations,assessments)
    def competing(state):return [dict(record=i,value=v) for i,v in state['competing']]
    def scoped(state,label):
        parts=', '.join('%s: %s'%(name,_qty(v)) for name,v in sorted(state['scopes'].items()))
        return '%s by phase (%s; overlap not established)'%(label,parts)
    def tag(state,label):
        return label+(' (%s)'%('supersession reviewer-assessed' if state.get('historical') else 'relationship reviewer-assessed') if state.get('relationship_basis')==REVIEWER_ASSESSED else '')
    if ap['state'] in (RESOLVED,QUALIFIED):
        q=ap.get('qualifier');label='Approved%s: %s'%(' (%s)'%q if q else '',_qty(ap))
        if ap.get('combined'):label='Approved: %d (%s)'%(ap['quantity'],', '.join('%s: %d'%(n,v['quantity']) for n,v in sorted(ap['scopes'].items())))
        out=dict(kind='APPROVED',label=tag(ap,label))
        if pr['state'] in (RESOLVED,QUALIFIED) and _qty(pr)!=_qty(ap):
            revises=any(r['basis']==PROPOSED and r.get('relations',{}).get('revises') for r in records)
            out['alongside']='Proposed revision: %s'%_qty(pr) if revises else 'Proposed (relationship to the approval not established): %s'%_qty(pr)
        return out
    if ap['state'] in (CONFLICT,ALTERNATIVES):return dict(kind='UNDER_REVIEW',label='Unit count under review',competing=competing(ap),basis=APPROVED)
    if ap['state']==PER_SCOPE:return dict(kind='APPROVED_BY_PHASE',label=scoped(ap,'Approved'))
    if pr['state'] in (RESOLVED,QUALIFIED):
        label='Proposed: %s'%_qty(pr)
        if pr.get('combined'):label='Proposed: %d (%s)'%(pr['quantity'],', '.join('%s: %d'%(n,v['quantity']) for n,v in sorted(pr['scopes'].items())))
        elif pr['state']==QUALIFIED and pr.get('qualifier'):label='Proposed (%s): %s'%(pr['qualifier'],_qty(pr))
        return dict(kind='PROPOSED',label=tag(pr,label))
    if pr['state'] in (CONFLICT,ALTERNATIVES):return dict(kind='UNDER_REVIEW',label='Unit count under review',competing=competing(pr),basis=PROPOSED)
    if pr['state']==PER_SCOPE:return dict(kind='PROPOSED_BY_PHASE',label=scoped(pr,'Proposed'))
    return dict(kind='NONE',label='Unit count not established')


def size_outcome(records,threshold=10,scope_relations=(),assessments=()):
    """Size eligibility only (planning status and every other admission condition are separate gates). Conflicts and qualified quantities route to assessment, never to an exact confirmed total.
    The platform threshold is a minimum with no maximum."""
    states=[resolve_basis(records,b,scope_relations,assessments) for b in (APPROVED,PROPOSED)]
    def resolved_ok(s):
        if s['state']==RESOLVED:return s['quantity']>=threshold
        if s['state']==PER_SCOPE:return any(resolved_ok(v) for v in s['scopes'].values())      # scope-level eligibility: a scope that itself reaches the threshold admits; no whole-scheme claim is made
        return False
    if any(resolved_ok(s) for s in states):return 'ADMIT_SCHEME'
    if any(basis_class(s,threshold,None)!=NO_MATCH for s in states):return 'ADMIT_FOR_ASSESSMENT'      # qualified maximum, conflict or alternatives that reach the threshold
    if any(s['state']!=NOT_ESTABLISHED for s in states):return 'RETAIN_BELOW_THRESHOLD'
    return NOT_ESTABLISHED


def read_model(records,scope_relations=(),assessments=()):
    """The read model never returns a bare number. It always carries basis, qualifier and state; an exact scalar cache is offered ONLY next to them, under a NEW name, with its own semantics version.
    Legacy single-scalar columns are never fed from it implicitly (specification section 9A)."""
    hl=headline(records,scope_relations,assessments)
    bases={b:resolve_basis(records,b,scope_relations,assessments) for b in (APPROVED,PROPOSED)}
    cache=None
    for b in (APPROVED,PROPOSED):      # the headline basis: approved when established, else proposed
        s=bases[b]
        if s['state']==RESOLVED and not s.get('relationship_basis'):      # a reviewer-assessed resolution is shown, labelled, but never exported as a plain scalar
            cache=dict(value=s['quantity'],basis=b,qualifier=s.get('qualifier'),state=RESOLVED,semantics='residential-count-v2:headline_exact');break
        if s['state']!=NOT_ESTABLISHED:break      # an established-but-unresolved (or assessed) approval is not replaced by a proposed figure
    return dict(headline=hl,bases={b:dict(state=s['state'],qualifier=s.get('qualifier'),quantity=s.get('quantity'),maximum=s.get('maximum'),minimum=s.get('minimum'),competing=s.get('competing'),
                                          relationship_basis=s.get('relationship_basis')) for b,s in bases.items()},headline_scalar=cache)
