"""Deterministic exact nominees from retained captures under ONE frozen screening rule. Pure: no I/O, no database, no source, no authority.

A nominee is a retained record whose frozen-rule routing outcome is identity-eligible (v3: ADMIT_SCHEME or ADMIT_FOR_ASSESSMENT, `IDENTITY_ELIGIBLE`). The set is a pure
function of the receipts and the rule, so it can be sealed with a hash before anything is registered and re-derived and compared at execution. Observations that
disagree about the same reference are WITHHELD and reported, never resolved first-wins or last-wins (specification 029: duplicate conflicting observations are withheld).
Nomination grants no authority and creates no work item; the existing exact bindings and gates still decide every effect.
"""
from dataclasses import dataclass,asdict
from .ledger import Denied,digest
from .listing_screening import RULE_V3,IDENTITY_ELIGIBLE,assessment_identity,routing_of


@dataclass(frozen=True)
class Nominee:
    council:str
    reference:str
    source_url:str
    source_record_id:str
    listing_revision:str      # digest of the retained record, as AcceptanceBinding.listing_revision
    screening_revision:str    # the v3 assessment identity of that record under the frozen configuration
    capture_sha256:str        # digest of the exact retained receipt that supplies the record
    outcome:str


@dataclass(frozen=True)
class NomineeSet:
    nominees:tuple
    retained:tuple      # (council, reference, outcome) for every identity-ineligible record: kept as evidence, nominated for nothing
    conflicts:tuple     # same reference observed with different content: withheld
    sha256:str
    completeness_bases:tuple=()      # (council, capture_sha256, basis, owner_acceptance_sha256) for every receipt whose completeness is OWNER-accepted rather than source-terminal; empty means every receipt is source-terminal


def derive_nominees(receipts,rule,*,allow_test_evidence=False):
    if rule.rule_version!=RULE_V3:raise Denied('V3_RULE_REQUIRED')
    receipts=list(receipts)
    for rc in receipts:
        if (rc.get('kind')!='LISTING_RECEIPT_V1' or not rc.get('durable_archive') or rc.get('cleanup')!='CLOSED'
            or rc.get('accounting_complete') is not True):raise Denied('RETAINED_CAPTURE_REQUIRED')
        if rc.get('evidence_label') and not allow_test_evidence:raise Denied('TEST_EVIDENCE_NOT_LIVE')      # a labelled test artefact is never live evidence unless a test explicitly opts in
    observations={}
    for rc in sorted(receipts,key=digest):
        capture=digest(rc)
        for r in rc['records']:
            content=digest({k:v for k,v in r.items() if k!='provenance'})      # provenance names the capture; it is not the observed content
            observations.setdefault((rc['council'],r['reference']),[]).append((content,capture,r))
    nominees=[];retained=[];conflicts=[]
    for (council,reference),seen in sorted(observations.items()):
        if len({content for content,_,_ in seen})>1:
            conflicts.append(dict(council=council,reference=reference,observations=sorted({(content,capture) for content,capture,_ in seen})))
            continue
        _,capture,r=seen[0]      # identical observations: the lexicographically first capture digest binds, so the choice is deterministic
        outcome=routing_of(rule.screen(r))[1]
        if outcome in IDENTITY_ELIGIBLE[RULE_V3]:
            nominees.append(Nominee(council,reference,r['source_url'],r['source_record_id'],digest(r),assessment_identity(r,rule)[3],capture,outcome))
        else:retained.append((council,reference,outcome))
    sealed=dict(configuration=digest(rule.config()),nominees=[asdict(n) for n in nominees],retained=[list(x) for x in retained],conflicts=conflicts)
    bases=tuple(sorted({(rc['council'],digest(rc),rc['completeness_basis'],rc['owner_acceptance']['sha256']) for rc in receipts if rc.get('completeness_basis')}))
    if bases:sealed['completeness_bases']=[list(b) for b in bases]      # named in the seal only when non-default, so every historical nominee-set digest is unchanged
    return NomineeSet(tuple(nominees),tuple(retained),tuple(conflicts),digest(sealed),bases)
