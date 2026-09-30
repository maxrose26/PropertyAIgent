"""Controlled local import/review boundary; no extraction or production engine."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from contextlib import contextmanager
import hashlib
import json
import re
from sqlalchemy import select, or_
from app.db.ah_claim_schema import claims, events, local_transaction, verify_schema
from app.db.models import Application, Document

NUMBERS = ('value','lower_bound','upper_bound')
GENERATED = {'id','recorded_at','payload_hash','passage_hash'}
PROVENANCE = {'origin_kind','origin_reference','extractor_version','created_by'}
LINKS = {'CORRECT','SUPERSEDE','CONFLICT'}
STATUSES = {'ACCEPT','REJECT','NEEDS_REVIEW','WITHDRAW'}


def canonical(value):
    def encode(v):
        if isinstance(v, Decimal):
            return format(v.normalize(), 'f')
        if isinstance(v, datetime):
            return v.replace(tzinfo=timezone.utc).isoformat() if v.tzinfo is None else v.astimezone(timezone.utc).isoformat()
        if isinstance(v, date):
            return v.isoformat()
        raise TypeError(type(v).__name__)
    return json.dumps(value, default=encode, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text_hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class ClaimError(ValueError):
    def __init__(self, code, **details):
        super().__init__(code)
        self.code, self.details = code, details


def payload(row, *, identity=False):
    omit = GENERATED | {'import_key','created_by'}
    if identity:
        omit |= PROVENANCE
    return {k: v for k, v in row.items() if k not in omit}


def prepare(raw):
    unknown = set(raw) - (set(claims.c.keys()) - GENERATED)
    if unknown:
        raise ClaimError('unsupported_fields', fields=sorted(unknown))
    data = {c.name: None for c in claims.c if c.name not in GENERATED}
    data.update(schema_version=1, planning_stage='unresolved')
    data.update(raw)
    for c in claims.c:
        if c.name in GENERATED:
            continue
        v = data[c.name]
        if not c.nullable and v is None:
            raise ClaimError('required_field', field=c.name)
        if v is not None and getattr(c.type, 'length', None) and (not isinstance(v,str) or len(v)>c.type.length):
            raise ClaimError('invalid_string', field=c.name)
    for name in ('application_id','scheme_application_id','site_id','document_id','stage_document_id','page_start','page_end','passage_start','passage_end','schema_version'):
        if data[name] is not None and (type(data[name]) is not int or data[name] < (0 if name=='passage_start' else 1)):
            raise ClaimError('invalid_integer', field=name)
    if data['schema_version'] != 1:
        raise ClaimError('unsupported_schema')
    for name in ('scope_key','scope_label','scope_basis','passage_text','passage_locator','origin_reference','created_by','import_key'):
        if not isinstance(data[name], str) or not data[name].strip():
            raise ClaimError('empty_field', field=name)
    if data['scope_kind'] not in ('whole_scheme','component','phase','unclear'):
        raise ClaimError('invalid_scope')
    reserved = {'whole_scheme':'WHOLE_SCHEME','unclear':'UNRESOLVED'}
    if (data['scope_kind'] in reserved and data['scope_key'] != reserved[data['scope_kind']]) or (data['scope_kind'] not in reserved and data['scope_key'] in reserved.values()):
        raise ClaimError('invalid_scope_key')
    if data['metric'] not in ('affordable_count','tenure_count') or ((data['metric']=='tenure_count') != bool(data['tenure_name'] and data['tenure_name'].strip())) or (data['metric']=='affordable_count' and data['tenure_name'] is not None):
        raise ClaimError('invalid_metric_tenure')
    if data['planning_stage'] not in ('proposed','approved','legally_secured','unresolved') or data['origin_kind'] not in ('reviewed_import','extraction'):
        raise ClaimError('invalid_stage_origin')
    for name in NUMBERS:
        if data[name] is None:
            continue
        try:
            v = Decimal(str(data[name]))
        except InvalidOperation:
            raise ClaimError('invalid_quantity', field=name)
        if not v.is_finite() or v<0 or v>=Decimal('1e12') or v != v.quantize(Decimal('.000001')):
            raise ClaimError('invalid_quantity', field=name)
        data[name] = v
    shape = {'exact':(1,0,0),'approximate':(1,0,0),'range':(0,1,1),'at_least':(0,1,0),'up_to':(0,0,1),'unknown':(0,0,0)}
    if tuple(int(data[n] is not None) for n in NUMBERS) != shape.get(data['qualifier']):
        raise ClaimError('invalid_quantity_shape')
    if data['qualifier']=='range' and data['lower_bound']>data['upper_bound']:
        raise ClaimError('invalid_range')
    if (data['qualifier']=='unknown' and not (data['unknown_reason'] or '').strip()) or (data['qualifier']!='unknown' and data['unknown_reason'] is not None):
        raise ClaimError('invalid_unknown')
    if data['document_date'] is not None:
        data['document_date'] = date.fromisoformat(str(data['document_date']))
        if data['document_date_missing_reason'] is not None:
            raise ClaimError('date_reason_exclusive')
    elif not (data['document_date_missing_reason'] or '').strip():
        raise ClaimError('date_missing_reason_required')
    for n in ('document_content_hash','extracted_text_hash'):
        if data[n] is not None and not re.fullmatch('[0-9a-f]{64}',data[n]):
            raise ClaimError('invalid_hash', field=n)
    for start, end in (('page_start','page_end'),('passage_start','passage_end')):
        a,b=data[start],data[end]
        if (a is None)!=(b is None) or (a is not None and b<a+(start=='passage_start')):
            raise ClaimError('invalid_locator_bounds')
    stage = [data[n] is not None for n in ('stage_document_id','stage_passage_text','stage_passage_locator')]
    if any(stage) and (not all(stage) or not data['stage_passage_text'].strip() or not data['stage_passage_locator'].strip()):
        raise ClaimError('incomplete_stage_source')
    data['passage_hash'] = text_hash(data['passage_text'])
    data['payload_hash'] = digest(payload(data))
    return data


def rows(conn, table, condition=None):
    stmt = select(table)
    if condition is not None:
        stmt = stmt.where(condition)
    return [dict(r) for r in conn.execute(stmt).mappings()]


def source_valid(conn, claim, *, accepting=False):
    apps = {r['id']:r for r in rows(conn, Application.__table__, Application.id.in_([claim['application_id'],claim['scheme_application_id']]))}
    app, root = apps.get(claim['application_id']), apps.get(claim['scheme_application_id'])
    if not app or not root:
        raise ClaimError('application_missing')
    if claim['site_id'] is not None and (app['site_id'] != claim['site_id'] or root['site_id'] != claim['site_id']):
        raise ClaimError('site_link_changed_or_invalid')
    if accepting and (claim['site_id'] is None or claim['scope_kind']=='unclear'):
        raise ClaimError('scope_requires_corrected_claim')
    for prefix in ('','stage_'):
        docid = claim[prefix+'document_id']
        if docid is None:
            continue
        docs=rows(conn, Document.__table__, Document.id==docid)
        if not docs:
            raise ClaimError('document_missing')
        doc=docs[0]
        # Cross-application source requires same reviewed scheme context; raw
        # site membership alone is never used by the selector to merge roots.
        if doc['application_id'] not in apps:
            raise ClaimError('document_application_mismatch')
        if not prefix:
            captured = claim['extracted_text_hash']
            if captured is not None and (doc['extracted_text'] is None or text_hash(doc['extracted_text']) != captured):
                raise ClaimError('source_text_version_changed')
            if claim['passage_start'] is not None:
                if not captured or doc['extracted_text'][claim['passage_start']:claim['passage_end']] != claim['passage_text']:
                    raise ClaimError('passage_offset_mismatch')
    return apps


def context(conn, roots):
    cr = rows(conn, claims, claims.c.scheme_application_id.in_(roots))
    # Include incoming links from other roots so a correction remains visible
    # when viewed from either its old or new context.
    ids = {r['id'] for r in cr}
    while True:
        all_events = rows(conn, events, or_(events.c.claim_id.in_(ids),events.c.related_claim_id.in_(ids))) if ids else []
        linked = {e['claim_id'] for e in all_events} | {e['related_claim_id'] for e in all_events if e['related_claim_id']}
        missing=linked-ids
        if not missing:
            break
        neighbours=rows(conn, claims, claims.c.id.in_(missing))
        neighbours=rows(conn, claims, claims.c.scheme_application_id.in_({c['scheme_application_id'] for c in neighbours}))
        cr += [c for c in neighbours if c['id'] not in ids]
        ids.update(c['id'] for c in neighbours)
    cr.sort(key=lambda r:r['id'])
    ids = {r['id'] for r in cr}
    ev=sorted([e for e in all_events if e['claim_id'] in ids], key=lambda e:(e['claim_id'],e['sequence']))
    appids=set(roots) | {r['application_id'] for r in cr} | {r['scheme_application_id'] for r in cr}
    app_rows=rows(conn, Application.__table__, Application.id.in_(appids))
    # App phase/status changes invalidate previews, but cannot establish a
    # count's source-checked legal stage.
    links=[{k:r.get(k) for k in ('id','site_id','status','decision','phase_code','phase_type')} for r in app_rows]
    docids={r[n] for r in cr for n in ('document_id','stage_document_id') if r[n] is not None}
    docs=rows(conn, Document.__table__, Document.id.in_(docids)) if docids else []
    versions=[(r['id'],r['application_id'],text_hash(r['extracted_text'] or ''),r['content_hash']) for r in docs]
    token=digest({'claims':cr,'events':ev,'links':sorted(links,key=lambda r:r['id']),'documents':sorted(versions)})
    return cr,ev,token


def fold(cr, ev):
    state={c['id']:{'status':'PENDING','head':0,'head_id':None,'accept':None} for c in cr}
    reversed_ids={e['reversed_event_id'] for e in ev if e['action']=='REVERSE_LINK'}
    for e in sorted(ev,key=lambda r:(r['claim_id'],r['sequence'])):
        s=state[e['claim_id']]
        if e['sequence'] != s['head']+1 or e['previous_event_id']!=s['head_id']:
            raise ClaimError('invalid_event_chain')
        s.update(head=e['sequence'],head_id=e['id'])
        if e['action'] in STATUSES:
            s['status']=e['action']
            s['accept']=e if e['action']=='ACCEPT' else None
    links=[e for e in ev if e['action'] in LINKS and e['id'] not in reversed_ids]
    return state,links


def lock_apps(conn, ids):
    if conn.dialect.name=='postgresql':
        list(conn.execute(select(Application.id).where(Application.id.in_(ids)).order_by(Application.id).with_for_update()))


@contextmanager
def read_snapshot(engine):
    """Independent read transaction: cannot flush an ORM session's pending work."""
    if engine.dialect.name == 'postgresql':
        from app.db.ah_disposable_postgres import require_engine
        require_engine(engine)
    with engine.connect() as conn:
        if conn.dialect.name == 'postgresql':
            conn = conn.execution_options(isolation_level='REPEATABLE READ')
            conn.begin()
            conn.exec_driver_sql('SET TRANSACTION READ ONLY')
        else:
            conn.exec_driver_sql('BEGIN')
        try:
            yield conn
        finally:
            conn.rollback()


def import_claim(engine, raw, *, apply=False):
    data=prepare(raw)
    with local_transaction(engine) as conn:
        verify_schema(conn)
        lock_apps(conn, sorted({data['application_id'],data['scheme_application_id']}))
        source_valid(conn,data)
        if conn.dialect.name=='sqlite' and any(data[n] is not None and Decimal(format(float(data[n]), '.6f')) != data[n] for n in NUMBERS):
            raise ClaimError('quantity_not_losslessly_supported_by_sqlite')
        existing=rows(conn, claims, claims.c.import_key==data['import_key'])
        if existing:
            if canonical(payload(existing[0])) != canonical(payload(data)):
                raise ClaimError('import_key_content_changed')
            return {'id':existing[0]['id'],'import_key':data['import_key'],'replayed':True}
        # Different-key evidence identity intentionally excludes capture origin.
        for old in rows(conn, claims, claims.c.application_id==data['application_id']):
            if canonical(payload(old,identity=True))==canonical(payload(data,identity=True)):
                raise ClaimError('duplicate_payload_use_original_key',id=old['id'],import_key=old['import_key'])
        if not apply:
            return {'valid':True,'would_insert':True,'import_key':data['import_key']}
        result=conn.execute(claims.insert().values(**data,recorded_at=datetime.now(timezone.utc)))
        return {'id':result.inserted_primary_key[0],'import_key':data['import_key'],'replayed':False}


def preview(engine, roots):
    with read_snapshot(engine) as conn:
        verify_schema(conn)
        cr,ev,token=context(conn,sorted(set(roots)))
        state,links=fold(cr,ev)
        return {'token':token,'heads':{str(k):s['head'] for k,s in state.items()},'claims':cr,'events':ev,'relationships':links}


def review_claim(engine, request, *, reviewer, apply=False):
    allowed={'claim_id','action','related_claim_id','reversed_event_id','source_checked','scope_checked','stage_checked','reason','request_key','expected_token','expected_heads'}
    if set(request)-allowed:
        raise ClaimError('unsupported_review_fields')
    r=dict(related_claim_id=None,reversed_event_id=None,source_checked=False,scope_checked=False,stage_checked=False,**{})
    r.update(request)
    for n in ('claim_id','action','reason','request_key','expected_token','expected_heads'):
        if n not in r:
            raise ClaimError('missing_review_field',field=n)
    if not isinstance(reviewer,str) or not reviewer.strip() or reviewer.startswith('extraction:'):
        raise ClaimError('operator_reviewer_required')
    if len(reviewer)>200:
        raise ClaimError('reviewer_identity_too_long')
    if not all(isinstance(r[n],str) and r[n].strip() for n in ('reason','request_key','expected_token')):
        raise ClaimError('review_reason_key_required')
    if len(r['request_key'])>200 or not re.fullmatch('[0-9a-f]{64}',r['expected_token']):
        raise ClaimError('invalid_review_key_or_token')
    for name in ('claim_id','related_claim_id','reversed_event_id'):
        if r[name] is not None and (type(r[name]) is not int or r[name]<=0):
            raise ClaimError('invalid_review_identity')
    if not isinstance(r['expected_heads'],dict) or any(not isinstance(k,str) or not k.isdigit() or type(v) is not int or v<0 for k,v in r['expected_heads'].items()):
        raise ClaimError('invalid_expected_heads')
    if r['action'] not in STATUSES|LINKS|{'REVERSE_LINK'}:
        raise ClaimError('invalid_review_action')
    for n in ('source_checked','scope_checked','stage_checked'):
        if type(r[n]) is not bool:
            raise ClaimError('invalid_check_flag')
    if r['action']=='ACCEPT':
        if not r['source_checked'] or not r['scope_checked']:
            raise ClaimError('source_scope_review_required')
    elif any(r[n] for n in ('source_checked','scope_checked','stage_checked')):
        raise ClaimError('check_flags_only_on_accept')
    if r['action'] in LINKS:
        if not r['related_claim_id'] or r['related_claim_id']==r['claim_id'] or r['reversed_event_id']:
            raise ClaimError('invalid_relation')
    elif r['action']=='REVERSE_LINK':
        if not r['reversed_event_id'] or r['related_claim_id']:
            raise ClaimError('invalid_reversal')
    elif r['related_claim_id'] or r['reversed_event_id']:
        raise ClaimError('unexpected_relationship')
    rh=digest(dict(r,reviewer=reviewer))
    with local_transaction(engine) as conn:
        verify_schema(conn)
        replay=rows(conn,events,events.c.request_key==r['request_key'])
        if replay:
            if replay[0]['request_hash']!=rh:
                raise ClaimError('review_key_content_changed')
            return {'id':replay[0]['id'],'replayed':True}
        touched={r['claim_id']}
        if r['related_claim_id']:
            touched.add(r['related_claim_id'])
        if r['reversed_event_id']:
            old=rows(conn,events,events.c.id==r['reversed_event_id'])
            if not old or old[0]['claim_id']!=r['claim_id'] or old[0]['action'] not in LINKS:
                raise ClaimError('invalid_reversal_target')
            touched.add(old[0]['related_claim_id'])
        initial=rows(conn,claims,claims.c.id.in_(touched))
        if len(initial)!=len(touched):
            raise ClaimError('claim_missing')
        roots=sorted({c['scheme_application_id'] for c in initial})
        before,_,_=context(conn,roots)
        locked_ids=set(roots)|{c['application_id'] for c in before}|{c['scheme_application_id'] for c in before}
        lock_apps(conn, sorted(locked_ids))
        replay=rows(conn,events,events.c.request_key==r['request_key'])
        if replay:
            if replay[0]['request_hash']!=rh:
                raise ClaimError('review_key_content_changed')
            return {'id':replay[0]['id'],'replayed':True}
        if conn.dialect.name=='postgresql':
            list(conn.execute(select(claims.c.id).where(claims.c.id.in_(touched)).order_by(claims.c.id).with_for_update()))
        cr,ev,token=context(conn,roots)
        if not ({c['application_id'] for c in cr}|{c['scheme_application_id'] for c in cr}).issubset(locked_ids):
            raise ClaimError('stale_review_preview')
        state,links=fold(cr,ev)
        if token != r['expected_token'] or r['expected_heads']!={str(k):v['head'] for k,v in state.items()}:
            raise ClaimError('stale_review_preview')
        byid={c['id']:c for c in cr}
        subject=byid[r['claim_id']]
        if r['action']=='ACCEPT':
            source_valid(conn,subject,accepting=True)
            if r['stage_checked'] and (not subject['stage_document_id'] or subject['planning_stage']=='unresolved'):
                raise ClaimError('stage_source_required')
        if r['action'] in LINKS:
            target=byid[r['related_claim_id']]
            if (subject['metric'],subject['tenure_name'])!=(target['metric'],target['tenure_name']):
                raise ClaimError('incompatible_metric')
            if r['action'] in ('CORRECT','SUPERSEDE'):
                if state[target['id']]['status']!='ACCEPT':
                    raise ClaimError('replacement_must_be_accepted')
                source_valid(conn,target,accepting=True)
                if r['action']=='CORRECT':
                    if (subject['document_id'],subject['passage_locator'])!=(target['document_id'],target['passage_locator']):
                        raise ClaimError('correction_requires_same_source_assertion')
                    scope_changed=any(subject[k]!=target[k] for k in ('site_id','scheme_application_id','scope_kind','scope_key'))
                    if scope_changed and any(subject[k]!=target[k] for k in ('qualifier','value','lower_bound','upper_bound','passage_text')):
                        raise ClaimError('scope_correction_must_preserve_source_quantity')
                else:
                    if state[subject['id']]['status']!='ACCEPT' or not state[target['id']]['accept']['stage_checked']:
                        raise ClaimError('supersession_requires_accepted_checked_stage')
                    keys=('scheme_application_id','scope_kind','scope_key')
                    if any(subject[k]!=target[k] for k in keys):
                        raise ClaimError('incompatible_supersession_scope')
                graph={}
                for e in links:
                    if e['action'] in ('CORRECT','SUPERSEDE'):
                        graph.setdefault(e['claim_id'],set()).add(e['related_claim_id'])
                todo=[target['id']]; seen=set()
                while todo:
                    n=todo.pop()
                    if n==subject['id']:
                        raise ClaimError('replacement_cycle')
                    if n not in seen:
                        seen.add(n); todo.extend(graph.get(n,()))
        if r['action']=='REVERSE_LINK' and any(e['reversed_event_id']==r['reversed_event_id'] for e in ev):
            raise ClaimError('link_already_reversed')
        if not apply:
            return {'valid':True,'would_append':True}
        values={k:r[k] for k in ('claim_id','action','related_claim_id','reversed_event_id','source_checked','scope_checked','stage_checked','reason','request_key')}
        s=state[r['claim_id']]
        values.update(sequence=s['head']+1,previous_event_id=s['head_id'],actor_id=reviewer,request_hash=rh,recorded_at=datetime.now(timezone.utc))
        result=conn.execute(events.insert().values(**values))
        return {'id':result.inserted_primary_key[0],'replayed':False}
