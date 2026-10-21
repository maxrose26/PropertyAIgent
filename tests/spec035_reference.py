"""Executable reference for Specification 035 sections 3A-3F (count bases, evidence status, scope overlap, headline, search certainty over a size range, size admission, read model).
This is the SPECIFICATION written as code so its examples can be checked; it is not application code, is imported by nothing in app/, and changes no behaviour. The implementation proposal reproduces it
(and these examples are its acceptance tests). Pure functions over plain dicts."""
PROPOSED='PROPOSED';APPROVED='APPROVED';EITHER='EITHER'
PERMISSION_SOURCES={'DECISION_NOTICE','APPROVED_PLANS_SCHEDULE'}      # only these can establish an APPROVED count: a form, proposal, statement or officer recommendation cannot
RESOLVED='RESOLVED';QUALIFIED='QUALIFIED_MAXIMUM';CONFLICT='CONFLICT_UNRESOLVED';ALTERNATIVES='ALTERNATIVE_PERMISSIONS';NOT_ESTABLISHED='NOT_ESTABLISHED';PER_SCOPE='PER_SCOPE'
MEETS='MEETS_SIZE_FILTER';POSSIBLE='POSSIBLE_SIZE_MATCH';NO_MATCH='NONE'
LABELS={MEETS:'Meets size filter',POSSIBLE:'Possible size match'}
LABEL_NOTE='A size match is not a confirmed quantity, a planning approval or a buyer fit.'


def parse(value):
    """('EXACT', n) or ('UP_TO', n)."""
    if isinstance(value,int) and not isinstance(value,bool):return 'EXACT',value
    if isinstance(value,str) and value.startswith('UP_TO:'):return 'UP_TO',int(value.split(':')[1])
    raise ValueError('BAD_COUNT_VALUE')


def _scope_state(active,historical):
    """One scope of one basis. `active` are records not superseded by an explicit, supported statement."""
    if not active:return dict(state=NOT_ESTABLISHED,competing=[],historical=historical)
    values={(parse(r['value'])) for r in active}
    competing=[(r['id'],r['value']) for r in active]
    if len(values)==1:
        kind,n=next(iter(values))
        return dict(state=RESOLVED if kind=='EXACT' else QUALIFIED,quantity=n if kind=='EXACT' else None,maximum=n if kind=='UP_TO' else None,qualifier=active[0].get('qualifier'),competing=competing,historical=historical)
    # distinct figures that nothing relates: never resolved by date, upload order, size or source rank
    alt=any('alternative_to' in r.get('relations',{}) for r in active)
    return dict(state=ALTERNATIVES if alt else CONFLICT,competing=competing,historical=historical)


def supported_non_overlap(relation):
    """A non-overlap relation counts only when a supported source states it: a source kind and the literal words. A phase LABEL alone proves nothing."""
    return relation.get('relation')=='NON_OVERLAPPING_PARTS' and bool(relation.get('source_kind')) and bool((relation.get('quote') or '').strip())


def resolve_basis(records,basis,scope_relations=()):
    recs=[r for r in records if r['basis']==basis]
    unsupported=[]
    if basis==APPROVED:
        unsupported=[r['id'] for r in recs if r['source_kind'] not in PERMISSION_SOURCES]
        recs=[r for r in recs if r['source_kind'] in PERMISSION_SOURCES]
    scopes={}
    for r in recs:scopes.setdefault(r.get('scope','whole'),[]).append(r)
    per={}
    for scope,group in scopes.items():
        ids={r['id'] for r in group}
        superseded={r['relations']['supersedes'] for r in group if r.get('relations',{}).get('supersedes') in ids}      # only an EXPLICIT supersedes between two supported records of the same scope
        active=[r for r in group if r['id'] not in superseded]
        per[scope]=_scope_state(active,sorted(superseded))
    if not per:return dict(state=NOT_ESTABLISHED,scopes={},unsupported_as_approved=unsupported)
    if len(per)==1:
        out=dict(next(iter(per.values())));out['scopes']=per;out['unsupported_as_approved']=unsupported;return out
    parts=[frozenset(x['scopes']) for x in scope_relations if supported_non_overlap(x)]
    names=set(per)
    if all(v['state']==RESOLVED for v in per.values()) and any(names<=p for p in parts):
        return dict(state=RESOLVED,quantity=sum(v['quantity'] for v in per.values()),scopes=per,combined=True,competing=[],historical=[],unsupported_as_approved=unsupported)
    return dict(state=PER_SCOPE,overlap='UNRESOLVED',scopes=per,combined=False,competing=[],historical=[],unsupported_as_approved=unsupported)


def _value_interval(value):
    kind,n=parse(value)
    return (n,n) if kind=='EXACT' else (1,n)      # "up to N" can be anything from one dwelling to N


def scenarios(state):
    """The ways the scheme-level count could be, each an interval (lo, hi): the real value is somewhere inside it. Conflicting or alternative figures are SEPARATE scenarios (one of them is true).
    Phases whose overlap is unresolved give ONE interval: at least the largest phase, at most all phases added."""
    s=state['state']
    if s==NOT_ESTABLISHED:return []
    if s==PER_SCOPE:
        parts=[scenarios(v) for v in state['scopes'].values()]
        lows=[min(lo for lo,_ in p) for p in parts];highs=[max(hi for _,hi in p) for p in parts]
        return [(max(lows),sum(highs))]
    if s==RESOLVED:return [(state['quantity'],state['quantity'])]
    if s==QUALIFIED:return [(1,state['maximum'])]
    return [_value_interval(v) for _,v in state['competing']]


def _scenario_class(interval,size_min,size_max):
    lo,hi=interval
    if hi<size_min or (size_max is not None and lo>size_max):return 'OUT'
    if lo>=size_min and (size_max is None or hi<=size_max):return 'IN'
    return 'STRADDLE'


def basis_class(state,size_min=10,size_max=None):
    """Certainty against the ENTIRE selected range [size_min, size_max] (size_max None = no upper bound): meets only if every possible count lies inside it; none only if every one lies outside."""
    classes=[_scenario_class(i,size_min,size_max) for i in scenarios(state)]
    if not classes or all(c=='OUT' for c in classes):return NO_MATCH
    return MEETS if all(c=='IN' for c in classes) else POSSIBLE


def quantity_status(state):
    return {RESOLVED:'CONFIRMED_QUANTITY',QUALIFIED:'QUALIFIED_QUANTITY',CONFLICT:'QUANTITY_UNDER_REVIEW',ALTERNATIVES:'QUANTITY_UNDER_REVIEW',PER_SCOPE:'QUANTITY_UNDER_REVIEW',NOT_ESTABLISHED:'NOT_ESTABLISHED'}[state['state']]


def search_match(records,basis_choice,size_min=10,size_max=None,scope_relations=()):
    """`basis_choice` APPROVED, PROPOSED or EITHER (the discovery default); the selected size range is [size_min, size_max]. Returns the class, the bases that caused it, and each causing basis's quantity status
    (a size match says nothing about quantity certainty, planning approval or buyer fit)."""
    bases=(APPROVED,PROPOSED) if basis_choice==EITHER else (basis_choice,)
    states={b:resolve_basis(records,b,scope_relations) for b in bases}
    classes={b:basis_class(s,size_min,size_max) for b,s in states.items()}
    best=MEETS if MEETS in classes.values() else POSSIBLE if POSSIBLE in classes.values() else NO_MATCH
    by=sorted(b for b,c in classes.items() if c==best and best!=NO_MATCH)
    return dict(match=best,matched_by=by,quantity_status={b:quantity_status(states[b]) for b in by})


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
    return 'up to %d'%state['maximum'] if state['state']==QUALIFIED else '%d'%state['quantity']


def headline(records,scope_relations=()):
    """The labelled headline quantity. Never silently chooses between competing figures."""
    ap=resolve_basis(records,APPROVED,scope_relations);pr=resolve_basis(records,PROPOSED,scope_relations)
    def competing(state):return [dict(record=i,value=v) for i,v in state['competing']]
    def scoped(state,label):
        parts=', '.join('%s: %s'%(name,_qty(v)) for name,v in sorted(state['scopes'].items()))
        return '%s by phase (%s; overlap not established)'%(label,parts)
    if ap['state'] in (RESOLVED,QUALIFIED):
        q=ap.get('qualifier');label='Approved%s: %s'%(' (%s)'%q if q else '',_qty(ap))
        if ap.get('combined'):label='Approved: %d (%s)'%(ap['quantity'],', '.join('%s: %d'%(n,v['quantity']) for n,v in sorted(ap['scopes'].items())))
        out=dict(kind='APPROVED',label=label)
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
        return dict(kind='PROPOSED',label=label)
    if pr['state'] in (CONFLICT,ALTERNATIVES):return dict(kind='UNDER_REVIEW',label='Unit count under review',competing=competing(pr),basis=PROPOSED)
    if pr['state']==PER_SCOPE:return dict(kind='PROPOSED_BY_PHASE',label=scoped(pr,'Proposed'))
    return dict(kind='NONE',label='Unit count not established')


def size_outcome(records,threshold=10,scope_relations=()):
    """Size eligibility only (planning status and every other admission condition are separate gates). Conflicts and qualified quantities route to assessment, never to an exact confirmed total.
    The platform threshold is a minimum with no maximum."""
    states=[resolve_basis(records,b,scope_relations) for b in (APPROVED,PROPOSED)]
    def resolved_ok(s):
        if s['state']==RESOLVED:return s['quantity']>=threshold
        if s['state']==PER_SCOPE:return any(resolved_ok(v) for v in s['scopes'].values())      # each phase is part of the scheme, so the scheme is at least as large as any phase
        return False
    if any(resolved_ok(s) for s in states):return 'ADMIT_SCHEME'
    if any(basis_class(s,threshold,None)!=NO_MATCH for s in states):return 'ADMIT_FOR_ASSESSMENT'      # qualified maximum, conflict or alternatives that reach the threshold
    if any(s['state']!=NOT_ESTABLISHED for s in states):return 'RETAIN_BELOW_THRESHOLD'
    return NOT_ESTABLISHED


def read_model(records,scope_relations=()):
    """The read model never returns a bare number. It always carries basis, qualifier and state; an exact scalar cache is offered ONLY next to them, under a NEW name, with its own semantics version.
    Legacy single-scalar columns are never fed from it implicitly (specification section 9A)."""
    hl=headline(records,scope_relations)
    bases={b:resolve_basis(records,b,scope_relations) for b in (APPROVED,PROPOSED)}
    cache=None
    for b in (APPROVED,PROPOSED):      # the headline basis: approved when established, else proposed
        s=bases[b]
        if s['state']==RESOLVED:
            cache=dict(value=s['quantity'],basis=b,qualifier=s.get('qualifier'),state=RESOLVED,semantics='residential-count-v2:headline_exact');break
        if s['state'] in (QUALIFIED,CONFLICT,ALTERNATIVES,PER_SCOPE):break      # an established-but-unresolved approval is not replaced by a proposed figure
    return dict(headline=hl,bases={b:dict(state=s['state'],qualifier=s.get('qualifier'),quantity=s.get('quantity'),maximum=s.get('maximum'),competing=s.get('competing')) for b,s in bases.items()},headline_scalar=cache)
