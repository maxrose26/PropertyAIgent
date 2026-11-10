"""Pure canonical selection/capacity checks for the existing source launcher. No authority or I/O."""
import math
from datetime import date
from . import finite_acceptance as finite

VERSION='FINITE_MANIFEST_SOURCE_RELEASE_V1'
PERMIT='OWNER_APPROVED_FINITE_MANIFEST_SOURCE_ONLY_STOP_TREATMENT'
COUNCILS=frozenset({'bury','oldham','rochdale','tameside'})
INPUT_KEYS={'finite_manifest','finite_manifest_sha256','selected_ordinals'}


def require_row(row, *, profiled=False):
    if not isinstance(row,dict) or set(row)!={'council','semantics','start','end'}:raise ValueError('CAMPAIGN_ROW')
    if row['council'] not in (finite.COUNCILS if profiled else COUNCILS) or row['semantics']!=finite.SEMANTICS[row['council']]:raise ValueError('CAMPAIGN_COUNCIL_OR_BASIS')
    for key in ('start','end'):
        if type(row[key]) is not str or date.fromisoformat(row[key]).isoformat()!=row[key]:raise ValueError('CAMPAIGN_DATE')
    days=(date.fromisoformat(row['end'])-date.fromisoformat(row['start'])).days
    if not 0<=days<=6:raise ValueError('CAMPAIGN_WINDOW')
    return row


def reservation(row, *, profiled=False):
    require_row(row,profiled=profiled);arc=row['council'] in finite.ARCUS
    return dict(requests=80 if arc else 10,bytes=20*1024**2 if arc else 3_000_000,
                worker_seconds=75 if arc else 45,active_seconds=90,job_seconds=480)


def select(value, *, profiled=False):
    if not isinstance(value,dict) or set(value)!=(INPUT_KEYS|{'collection_mode'} if profiled else INPUT_KEYS):raise ValueError('CAMPAIGN_INPUT_SCHEMA')
    if profiled:
        from .source_profiles import MODES
        if value['collection_mode'] not in MODES:raise ValueError('COLLECTION_MODE')
    plan=value['finite_manifest']
    if not isinstance(plan,dict) or set(plan)!={'purpose','start','end','rule','limits','rows'}:raise ValueError('CAMPAIGN_PLAN_SCHEMA')
    # The generator is authoritative for purposes, basis, partitions and ordering.
    canonical=finite.manifest(plan['start'],plan['end'],plan['purpose'])
    if plan!=canonical or finite.digest(plan)!=finite.digest(canonical) or value['finite_manifest_sha256']!=finite.digest(canonical):raise ValueError('CAMPAIGN_PLAN_BINDING')
    indexes=value['selected_ordinals']
    if not isinstance(indexes,list) or not indexes or any(type(i) is not int or not 0<=i<len(plan['rows']) for i in indexes):raise ValueError('CAMPAIGN_SELECTION')
    if indexes!=sorted(set(indexes)):raise ValueError('CAMPAIGN_ORDER_OR_DUPLICATE')
    rows=[dict(plan['rows'][i]) for i in indexes]
    for row in rows:require_row(row,profiled=profiled)
    for i,row in enumerate(rows):
        if any(other['council']==row['council'] and other['end']>=row['start'] for other in rows[:i]):raise ValueError('CAMPAIGN_OVERLAP')
    return rows


def capacity(rows,limits, *, profiled=False):
    costs=[reservation(row,profiled=profiled) for row in rows];n=len(rows)
    # Existing publisher: claim (2 files)=10, slot (3 files)=12, final reserve=24.
    publication=10+12*n+24
    # Include per-slot visible control polling plus fixed history/control/readback headroom.
    github=publication+16+n*(math.ceil(90/2)+4)
    totals=dict(observations=n,requests=sum(c['requests'] for c in costs),
        mixed_source_bytes=sum(c['bytes'] for c in costs),worker_seconds=sum(c['worker_seconds'] for c in costs),
        active_seconds=sum(c['active_seconds'] for c in costs),package_seconds=sum(c['job_seconds'] for c in costs),
        publication_requests=publication,github_requests=github,exported_bytes=n*512*1024+512*1024)
    if any(totals[k]>limits[k] for k in totals):raise ValueError('CAMPAIGN_CAPACITY')
    return totals


def input_from_manifest(value):
    return {k:value[k] for k in (INPUT_KEYS|{'collection_mode'} if 'collection_mode' in value else INPUT_KEYS)}


INITIAL_TWO_SLOT_VERSION='NINE_COUNCIL_INITIAL_28D_TWO_SLOT_SOURCE_PROOF_V1'


def initial_two_slot_packages(plan, expected_sha256):
    """Pure, NON-AUTHORISING nine-council source-package compatibility proof.

    No PostgreSQL issuance, collection permission, source qualification or
    retention is established by this structural proof.
    """
    from .four_council_release import SUCCESSOR_V2_LIMITS
    try:
        if not isinstance(plan,dict) or set(plan)!={'purpose','start','end','rule','limits','rows'}:
            raise ValueError()
        first,last=date.fromisoformat(plan['start']),date.fromisoformat(plan['end'])
        if (last-first).days!=27 or plan['purpose']!='PROSPECTIVE':raise ValueError()
        canonical=finite.manifest(plan['start'],plan['end'],'PROSPECTIVE')
        if plan!=canonical or expected_sha256!=finite.digest(canonical):raise ValueError()
        if len(finite.SEMANTICS)!=9 or 'bolton' not in finite.SEMANTICS or len(plan['rows'])!=36:
            raise ValueError()
        if any(sum(row['council']==c for row in plan['rows'])!=4 for c in finite.SEMANTICS):
            raise ValueError()
    except (ValueError,KeyError,TypeError,OverflowError):
        raise ValueError('INITIAL_28_MANIFEST_UNVERIFIED') from None
    arcus=[i for i,row in enumerate(plan['rows']) if row['council'] in finite.ARCUS]
    idox=[i for i,row in enumerate(plan['rows']) if row['council'] not in finite.ARCUS]
    if len(arcus)!=12 or len(idox)!=24:raise ValueError('INITIAL_28_FAMILY_COUNTS')
    groups=[[arcus[i],idox[i]] for i in range(12)]
    groups += [idox[i:i+2] for i in range(12,24,2)]
    if len(groups)!=18 or sorted(i for g in groups for i in g)!=list(range(36)):
        raise ValueError('INITIAL_28_PARTITION')
    packages=[]
    for ordinal,group in enumerate(groups,1):
        payload=dict(finite_manifest=plan,finite_manifest_sha256=expected_sha256,
                     selected_ordinals=sorted(group),collection_mode='SCREENING_METADATA')
        rows=select(payload,profiled=True)
        reservation=capacity(rows,SUCCESSOR_V2_LIMITS,profiled=True)
        if len(rows)!=2 or reservation['observations']!=2 or reservation['requests']>100:
            raise ValueError('INITIAL_28_TWO_SOURCE_CAP')
        packages.append(dict(ordinal=ordinal,selected_ordinals=payload['selected_ordinals'],
                             reservation=reservation))
    return dict(version=INITIAL_TWO_SLOT_VERSION,manifest_sha256=expected_sha256,
                window=[plan['start'],plan['end']],packages=packages,
                sql_issuer_qualified=False,source_qualified=False,
                initial_capture_authorised=False,operationally_usable=False)
