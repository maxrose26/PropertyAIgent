"""Append-only application history over listing evidence (specification 033). Pure functions over plain data: nothing here reads or writes a database, calls a council or advances any watermark.

* IDENTITY of an application is (council, reference). Observations are never merged away: every observation of an application is kept with its UTC timestamp, source kind and per-record digest.
* A change between observations is classified UNCHANGED, NORMAL_UPDATE (a descriptive field changed, or a later-published field appeared) or CONFLICT (identity-defining or immutable evidence disagrees). A conflict is flagged and
  both sides stay; neither is overwritten.
* `first_observed_at` is when THIS PLATFORM first observed the application. It is NOT when the council received or published it, and nothing here can say an application is "newly submitted": that needs a window claim.
* A later COMPLETE capture is LINKED to earlier observations; links are separate records and neither side's evidence is replaced or deleted."""
import copy
import json
from datetime import datetime,timezone
from .ledger import Denied,digest

IDENTITY_FIELDS=('received_date',)      # immutable once published
DESCRIPTIVE_FIELDS=('proposal','address','application_type')      # may legitimately be amended or completed
LATER_PUBLISHED_FIELDS=('validated_date',)      # absent -> present is normal; present -> different/absent is a conflict
SOURCE_KINDS=('LISTING_OBSERVATION_V1','LISTING_RECEIPT_V1')


def stored(evidence):
    """Evidence is digested in its STORED (JSON) form, exactly as the ledger keeps it, so an in-memory receipt (whose window evidence holds dates) and its stored copy give the same digest."""
    return json.loads(json.dumps(evidence,default=str))


def _require(condition,code):
    """Explicit invariant check (not `assert`, which `python -O` removes)."""
    if not condition:raise Denied(code)


def empty_history():
    return dict(applications={},links=[],conflicts=[])


def _utc(stamp):
    try:
        value=datetime.fromisoformat(stamp)
        if value.tzinfo is None or value.utcoffset()!=timezone.utc.utcoffset(None):raise ValueError
    except (TypeError,ValueError):raise Denied('OBSERVATION_TIMESTAMP_UTC_REQUIRED') from None
    return value


def _value(record,name):
    f=record['fields'].get(name) or {}
    return f.get('value') if f.get('state')=='PRESENT_VALUE' else None


def classify_change(previous,current):
    """Compare two records of the SAME application. Returns (kind, detail)."""
    if previous['source_record_id']!=current['source_record_id']:return 'CONFLICT',dict(reason='SOURCE_KEY_CHANGED')
    for name in IDENTITY_FIELDS:
        if _value(previous,name)!=_value(current,name):return 'CONFLICT',dict(reason='IDENTITY_FIELD_CHANGED',field=name)
    for name in LATER_PUBLISHED_FIELDS:
        a,b=_value(previous,name),_value(current,name)
        if a is not None and a!=b:return 'CONFLICT',dict(reason='PUBLISHED_FIELD_CHANGED_OR_WITHDRAWN',field=name)
    changed=[n for n in (*DESCRIPTIVE_FIELDS,*LATER_PUBLISHED_FIELDS) if _value(previous,n)!=_value(current,n)]
    return ('NORMAL_UPDATE',dict(changed=changed)) if changed else ('UNCHANGED',dict(changed=[]))


def append(history,evidence,*,observed_at=None):
    """Return a NEW history with every record of `evidence` (an observation or a complete receipt) appended. Earlier entries are never altered or removed (checked)."""
    if evidence.get('kind') not in SOURCE_KINDS:raise Denied('UNSUPPORTED_EVIDENCE_KIND')
    if evidence['kind']=='LISTING_OBSERVATION_V1':
        stamp=evidence.get('observed_at')
        if observed_at is not None and observed_at!=stamp:raise Denied('OBSERVATION_TIMESTAMP_IS_THE_EVIDENCES_OWN')      # an observation carries its own observation time; a different one is refused, never ignored
    else:stamp=observed_at
    _utc(stamp)
    evidence=stored(evidence)
    out=copy.deepcopy(history);evidence_digest=digest(evidence)
    keys={}      # source key -> reference, across everything already held
    for app in out['applications'].values():
        for o in app['observations']:keys.setdefault(o['source_record_id'],app['identity']['reference'])
    for record in evidence['records']:
        ident=dict(council=evidence['council'],reference=record['reference']);k=digest(ident)
        entry=dict(evidence_digest=evidence_digest,evidence_kind=evidence['kind'],observed_at=stamp,record_digest=digest(record),source_record_id=record['source_record_id'],
                   received_date=_value(record,'received_date'),fields={n:_value(record,n) for n in (*DESCRIPTIVE_FIELDS,*LATER_PUBLISHED_FIELDS)})
        app=out['applications'].setdefault(k,dict(identity=ident,observations=[],first_observed_at=None,first_observed_in=None))
        if any(all(o[n]==entry[n] for n in ('evidence_digest','record_digest','observed_at')) for o in app['observations']):continue
        if keys.get(entry['source_record_id'],record['reference'])!=record['reference']:
            out['conflicts'].append(dict(identity=ident,reason='SOURCE_KEY_USED_BY_ANOTHER_REFERENCE',evidence_digest=evidence_digest,other_reference=keys[entry['source_record_id']]))
        keys.setdefault(entry['source_record_id'],record['reference'])
        if app['observations']:
            previous=app['observations'][-1]      # NOTE: the change label is relative to the previously APPENDED entry (delivery order); chronology is kept in `observed_at` and read through first_observed
            kind,detail=classify_change(dict(source_record_id=previous['source_record_id'],fields={'received_date':dict(state='PRESENT_VALUE' if previous['received_date'] else 'UNKNOWN',value=previous['received_date']),
                                                                                                     **{n:dict(state='PRESENT_VALUE' if previous['fields'][n] else 'UNKNOWN',value=previous['fields'][n]) for n in previous['fields']}}),record)
        else:kind,detail='FIRST_OBSERVATION',{}
        entry.update(change=kind,change_detail=detail)
        if kind=='CONFLICT':out['conflicts'].append(dict(identity=ident,reason=detail['reason'],field=detail.get('field'),evidence_digest=evidence_digest))
        app['observations'].append(entry)
        if app['first_observed_at'] is None or _utc(stamp)<_utc(app['first_observed_at']):app['first_observed_at']=stamp;app['first_observed_in']=evidence_digest
    for k,app in history['applications'].items():      # append-only invariant: every earlier observation is still there, in order, unchanged
        _require(out['applications'][k]['observations'][:len(app['observations'])]==app['observations'],'HISTORY_NOT_APPEND_ONLY')
    _require(out['conflicts'][:len(history['conflicts'])]==history['conflicts'] and out['links']==history['links'],'HISTORY_NOT_APPEND_ONLY')
    return out


def first_observed(history,council,reference):
    """When this platform first observed the application. NOT a submission, receipt or publication date."""
    app=history['applications'].get(digest(dict(council=council,reference=reference)))
    if app is None:return None
    earliest=min(app['observations'],key=lambda o:_utc(o['observed_at']))      # the earliest observation BY TIME, not by delivery order
    return dict(first_observed_at=app['first_observed_at'],first_observed_in=app['first_observed_in'],council_received_date=earliest['received_date'])


def link_complete_capture(history,receipt,*,observed_at):
    """Link a later COMPLETE capture to earlier observations without replacing anything. Returns a NEW history with `links` appended; observation entries are untouched.
    Relation PRESENT_IN_COMPLETE_CAPTURE, or OBSERVED_BUT_ABSENT_FROM_COMPLETE_CAPTURE (a flag for review: it is conflicting evidence, never a deletion)."""
    if receipt.get('kind')!='LISTING_RECEIPT_V1':raise Denied('COMPLETE_RECEIPT_REQUIRED')
    _utc(observed_at)
    receipt=stored(receipt)
    if (receipt.get('window') or {}).get('date_semantics','RECEIVED')!='RECEIVED':raise Denied('RECEIVED_SEMANTICS_REQUIRED')      # observations compare on the council's received date only
    lo,hi=receipt['interval'];present={r['reference'] for r in receipt['records']};receipt_digest=digest(receipt)
    out=copy.deepcopy(history);seen={(l['identity']['reference'],l['observation_evidence_digest'],l['complete_receipt_digest']) for l in history['links']}
    for k,app in sorted(history['applications'].items()):
        ident=app['identity']
        if ident['council']!=receipt['council']:continue
        for o in app['observations']:
            if o['evidence_kind']!='LISTING_OBSERVATION_V1' or o['received_date'] is None:continue
            day=datetime.strptime(o['received_date'],'%a %d %b %Y').date().isoformat()
            if not lo<=day<=hi:continue
            relation='PRESENT_IN_COMPLETE_CAPTURE' if ident['reference'] in present else 'OBSERVED_BUT_ABSENT_FROM_COMPLETE_CAPTURE'
            token=(ident['reference'],o['evidence_digest'],receipt_digest)
            if token in seen:continue      # idempotent: linking the same receipt twice adds nothing
            seen.add(token)
            out['links'].append(dict(identity=ident,observation_evidence_digest=o['evidence_digest'],complete_receipt_digest=receipt_digest,relation=relation,linked_at=observed_at))
            if relation!='PRESENT_IN_COMPLETE_CAPTURE':out['conflicts'].append(dict(identity=ident,reason=relation,evidence_digest=receipt_digest))
    _require(out['applications']==history['applications'],'HISTORY_NOT_APPEND_ONLY')      # linking touches only `links` and `conflicts`
    return out


def display_label(evidence):
    """The label a product surface must show for the evidence: an observation is never presented as a complete window."""
    from .idox_adapter import OBSERVATION_DISPLAY_LABEL
    return OBSERVATION_DISPLAY_LABEL if evidence.get('kind')=='LISTING_OBSERVATION_V1' else None
