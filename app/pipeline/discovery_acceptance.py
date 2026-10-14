"""Pure independent-denominator accounting, separate from source enumeration.

Inputs must be frozen/reviewed by the acceptance caller. This module does not
construct a denominator, certify its independence, access sources or write data.
A manual committee addition is never counted as a primary discovery detection.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from app.pipeline.discovery_contract import COUNCILS, account_identity, latency_seconds

MATERIALITIES=frozenset({'CONFIRMED_MATERIAL','POTENTIALLY_MATERIAL'})


@dataclass(frozen=True)
class ReferenceEntry:
    council: str
    reference: str
    materiality: str
    in_interval: bool
    evidence_id: str
    public_available_at: datetime | None = None

    def __post_init__(self):
        if account_identity(self.council,(self.reference,),frozenset())[1]!=self.reference:
            raise ValueError('denominator identity')
        if self.materiality not in MATERIALITIES or type(self.in_interval) is not bool or not self.evidence_id:
            raise ValueError('denominator evidence')
        if self.public_available_at is not None and self.public_available_at.tzinfo is None:
            raise ValueError('publication clock')


@dataclass(frozen=True)
class DetectionEntry:
    council: str
    reference: str
    detected_at: datetime
    run_id: str
    primary_source: bool
    withheld: bool
    admitted: bool

    def __post_init__(self):
        if account_identity(self.council,(self.reference,),frozenset())[1]!=self.reference:
            raise ValueError('detection identity')
        if self.detected_at.tzinfo is None or not self.run_id:
            raise ValueError('detection provenance')
        if any(type(v) is not bool for v in (self.primary_source,self.withheld,self.admitted)) or (self.withheld and self.admitted):
            raise ValueError('admission classification')


def reconcile(entries, detections, known, *, complete_councils, comparison_at):
    """Reconcile independently supplied scope; incomplete denominator -> UNKNOWN.

    Detection/admission are deliberately separate. Overlap detections use the
    earliest primary observation for latency and any prior successful admission.
    The caller freezes admission flags as of comparison_at, not at a later time.
    Invalid/inconsistent input is not quietly repaired or normalised.
    """
    if comparison_at.tzinfo is None or not set(complete_councils)<=COUNCILS:
        raise ValueError('comparison scope')
    indexed={}
    for row in entries:
        key=(row.council,row.reference)
        if key in indexed: raise ValueError('duplicate denominator identity')
        indexed[key]=row
    observations={}
    for row in detections:
        if row.detected_at.astimezone(timezone.utc)>comparison_at.astimezone(timezone.utc): raise ValueError('post-comparison detection')
        if row.primary_source:
            observations.setdefault((row.council,row.reference),[]).append(row)
    rows=[]
    for key,entry in sorted(indexed.items()):
        seen=sorted(observations.get(key,()),key=lambda d:d.detected_at.astimezone(timezone.utc))
        if not entry.in_interval: outcome='OUTSIDE_INTERVAL'
        elif key in known: outcome='ALREADY_KNOWN'
        elif not seen: outcome='MISSED'
        elif all(d.withheld for d in seen): outcome='WITHHELD_AFTER_DETECTION'
        else: outcome='DETECTED'
        latency=None; within=None
        if seen and entry.in_interval:
            latency=latency_seconds(seen[0].detected_at,entry.public_available_at)
            if entry.public_available_at is not None:
                deadline=entry.public_available_at.astimezone(ZoneInfo('Europe/London'))+timedelta(days=7)
                within=seen[0].detected_at.astimezone(timezone.utc)<=deadline.astimezone(timezone.utc)
        rows.append({'council':entry.council,'reference':entry.reference,
            'materiality':entry.materiality,'outcome':outcome,'evidence_id':entry.evidence_id,
            'detected':bool(seen),'admitted':any(d.admitted for d in seen),
            'latency_seconds':latency,'within_seven_days':within})
    totals={}
    for council in sorted(COUNCILS):
        by_category={}
        for category in sorted(MATERIALITIES):
            selected=[r for r in rows if r['council']==council and r['materiality']==category
                and r['outcome'] not in {'OUTSIDE_INTERVAL','ALREADY_KNOWN'}]
            complete=council in complete_councils
            detected=sum(r['detected'] for r in selected)
            by_category[category]={'denominator_state':'COMPLETE' if complete else 'UNKNOWN',
                'audited_eligible':len(selected),'detected':detected,
                'withheld_after_detection':sum(r['outcome']=='WITHHELD_AFTER_DETECTION' for r in selected),
                'admitted':sum(r['admitted'] for r in selected),
                'missed':sum(r['outcome']=='MISSED' for r in selected),
                'recall':detected/len(selected) if complete and selected else None}
        totals[council]=by_category
    return {'references':rows,'councils':totals,
        'observed_material_misses':sum(r['outcome']=='MISSED' for r in rows),
        'unexplained_material_misses':sum(r['outcome']=='MISSED' for r in rows) if set(complete_councils)==COUNCILS else None,
        'denominator_complete':set(complete_councils)==COUNCILS,
        # This is an accounting result, never a Stage4 gate decision.
        'acceptance_claim':False}
