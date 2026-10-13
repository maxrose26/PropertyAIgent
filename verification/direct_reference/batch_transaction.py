"""Manifest-scoped adapter around the existing B2; no factual writer here."""
import datetime as dt
import inspect
from .oldham_production import (COUPLED,EVENT_FIELDS,WRITE_FIELDS,EVENT_TYPES,
                               validate_snapshot,check_consequences)

class Meter:
    """Actual driver statement/transaction events; excludes seed/setup work."""
    def __init__(self,engine):
        from sqlalchemy import event
        self.engine=engine;self.active=0
        self.counts=dict(reads=0,writes=0,other=0,commits=0,rollbacks=0,connections=0,peak_connections=0)
        self.listeners=[('before_cursor_execute',self.statement),('commit',self.commit),
                        ('rollback',self.rollback),('checkout',self.checkout),('checkin',self.checkin)]
        for name,fn in self.listeners:event.listen(engine,name,fn)
    def statement(self,c,cursor,sql,params,context,many):
        word=sql.lstrip().split()[0].upper()
        key='reads' if word in {'SELECT','SHOW'} else 'writes' if word in {'UPDATE','INSERT','DELETE'} else 'other'
        self.counts[key]+=1
    def commit(self,*a):self.counts['commits']+=1
    def rollback(self,*a):self.counts['rollbacks']+=1
    def checkout(self,*a):
        self.active+=1;self.counts['connections']+=1
        self.counts['peak_connections']=max(self.active,self.counts['peak_connections'])
        if self.active>1:raise ValueError('CONNECTION_BOUND')
    def checkin(self,*a):self.active-=1
    def close(self):
        from sqlalchemy import event
        for name,fn in self.listeners:event.remove(self.engine,name,fn)
        if self.active:raise ValueError('CONNECTION_LEAK')
def snapshot(session,row):
    from sqlalchemy import select
    from app.db.models import Application,ApplicationLifecycleEvent as E
    values=session.execute(select(*(getattr(Application,k) for k in COUPLED)).where(
      Application.id==row['application_id'],Application.reference==row['reference'],Application.council_code==row['council']).limit(1)).one()
    facts={k:(v.isoformat() if isinstance(v,dt.datetime) else v) for k,v in zip(COUPLED,values)}
    events=[dict(zip(EVENT_FIELDS,r)) for r in session.execute(select(*(getattr(E,k) for k in EVENT_FIELDS)).where(E.application_id==row['application_id']).order_by(E.id).limit(17))]
    out=dict(facts=facts,events=events);validate_snapshot(out);return out


def install_guards(engine,row):
    """Deny DDL/text/bulk writes. Actual B2 call stack and bound row ID required."""
    from sqlalchemy import event
    from sqlalchemy.sql.dml import Insert,Update
    from sqlalchemy.sql.selectable import Select
    def guard(conn,clause,multi,params,options):
        if isinstance(clause,Select):return
        if not isinstance(clause,(Insert,Update)):raise ValueError('SQL_DENIED')
        if not any(f.function=='verify_application_status' and f.filename.endswith('/app/pipeline/status_verification.py') for f in inspect.stack()):raise ValueError('B2_ONLY')
        if len(multi)>1:raise ValueError('BULK_DENIED')
        bound=dict(clause.compile().params);bound.update(params or (multi[0] if multi else {}))
        if isinstance(clause,Update):
            if clause.table.name!='applications':raise ValueError('TABLE_DENIED')
            assignments={getattr(k,'key',str(k)) for k in (clause._values or {})} or (set(params or (multi[0] if multi else {}))-{'applications_id'})
            if not assignments<=WRITE_FIELDS:raise ValueError('COLUMN_DENIED')
            # B2 CAS binds id_1; ORM flush binds applications_id. Neither is caller input.
            if bound.get('id_1',bound.get('applications_id'))!=row['application_id']:raise ValueError('ROW_DENIED')
        else:
            if clause.table.name!='application_lifecycle_events' or bound.get('application_id')!=row['application_id'] or bound.get('authoritative_source')!='status_verification':raise ValueError('EVENT_DENIED')
    event.listen(engine,'before_execute',guard)
    return guard


def session_type(row):
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from app.db.models import Application,ApplicationLifecycleEvent as E
    class BoundedSession(Session):pass
    @event.listens_for(BoundedSession,'do_orm_execute')
    def scope(state):
        if not state.is_select:return
        stmt=state.statement
        tables={getattr(t,'name',None) for t in stmt.get_final_froms()}
        if tables=={'applications'}:state.statement=stmt.where(Application.id==row['application_id']).limit(2)
        elif tables=={'application_lifecycle_events'}:state.statement=stmt.where(E.application_id==row['application_id']).limit(17)
        else:raise ValueError('READ_SCOPE')
    @event.listens_for(BoundedSession,'before_flush')
    def flush(s,*args):
        from sqlalchemy import inspect as sa_inspect
        if s.deleted:raise ValueError('DELETE_DENIED')
        for obj in s.new:
            if not isinstance(obj,E) or obj.application_id!=row['application_id'] or obj.authoritative_source!='status_verification':raise ValueError('INSERT_DENIED')
        for obj in s.dirty:
            if not isinstance(obj,Application) or obj.id!=row['application_id']:raise ValueError('UPDATE_DENIED')
            if {a.key for a in sa_inspect(obj).attrs if a.history.has_changes()}-WRITE_FIELDS:raise ValueError('COLUMN_DENIED')
    return BoundedSession


def run_transaction(engine,row,source_factory,limits,*,provenance='SYNTHETIC_REHEARSAL'):
    """Fresh retrieval inside B2 snapshot; independent readback reconciles ack."""
    from sqlalchemy import event,select
    from app.db.models import Application
    from .batch import blank,validate_record,LOCAL,SAFETY
    from .refresh import Observation,refresh,admitted_row
    from .registration import observe
    from app.config import CouncilConfig
    from verification.stage26b_l1.request_boundary import BoundaryFailure
    if row!=admitted_row(row['application_id']):raise ValueError('UNADMITTED')
    a=blank(row);a.update(transaction='UNKNOWN',b2_outcome='UNKNOWN',cleanup='UNKNOWN',disposition='UNCERTAIN')
    if provenance not in {'SYNTHETIC_REHEARSAL','FRESH_OFFICIAL_SUMMARY'}:raise ValueError('PROVENANCE')
    S=session_type(row);meter=Meter(engine);guard=install_guards(engine,row)
    try:
        with S(engine,expire_on_commit=False) as s:
            app=s.execute(select(Application).where(Application.id==row['application_id'],Application.reference==row['reference'],Application.council_code==row['council']).limit(1)).scalar_one()
            a['before']=snapshot(s,row)
            def loader():
                a['source_provenance']=provenance
                a['retrieval_started_at']=dt.datetime.now(dt.timezone.utc).isoformat()
                try:
                    source=observe(row['application_id'],source_factory,identity=row,
                        limits={k:limits[k] for k in ('requests','bytes','seconds')})
                except Exception:
                    a['error']='AUDIT_REJECTED'
                    raise BoundaryFailure('PRIVACY_FAILURE','Source audit rejected')
                a['retrieval_completed_at']=dt.datetime.now(dt.timezone.utc).isoformat()
                a['source']=source
                validate_record(a,row) # privacy and accounting before watermark reservation
                if source['outcome']!='LITERAL_VERIFIED':raise BoundaryFailure(source['outcome'],'Qualified source failure')
                eligible=all(v in {'PRESENT_VALUE','PRESENT_BLANK'} for v in source['field_states'].values()) and source['semantic_qualification']!='UNKNOWN_UNMAPPED'
                return Observation(row['application_id'],row['reference'],row['source_url'],source['normalized_facts'],source['field_states'],source['semantic_qualification'],None,source['literal_facts'],b2_eligible=eligible)
            def before_commit(session):
                session.flush();a['expected']=snapshot(session,row)
                if a['expected']['events'][:len(a['before']['events'])]!=a['before']['events']:raise ValueError('EVENT_MUTATION')
                new=a['expected']['events'][len(a['before']['events']):]
                if len(new)>2 or any(e['event_type'] not in EVENT_TYPES or e['authoritative_source']!='status_verification' for e in new):raise ValueError('EVENT_BOUND')
                check_consequences(a['before'],a['expected']);validate_record(a,row)
            event.listen(s,'before_commit',before_commit)
            cfg=CouncilConfig(code=row['council'],name=row['council'],base_url=row['source_url'].split('/applicationDetails.do')[0],date_field_mode='received',doc_system='idox',anite_base_url=None,unit_threshold=10,region='GM',country='England')
            result=refresh(s,app,cfg,retrieve_evidence=loader)
            a['b2_outcome']=result['outcome']
        try:
            with S(engine) as reader:a['after']=snapshot(reader,row)
            if a['expected'] is not None and a['after']==a['expected']:a['transaction']='COMMITTED'
            elif a['after']==a['before']:a['transaction']='NOT_COMMITTED'
            else:a['error']='READBACK_MISMATCH'
        except Exception:a['error']='COMMIT_ACK_UNKNOWN'
        source=a['source']
        if a['transaction']=='COMMITTED' and a['error'] is None:
            if not source or source['outcome']!='LITERAL_VERIFIED':a['error']='AUDIT_REJECTED'
            else:a['disposition']='COMPLETED'
        elif a['transaction']=='NOT_COMMITTED':
            if a['error'] is not None:
                a['disposition']='SAFETY_STOP'
            elif a['expected'] is not None or a['b2_outcome']=='PERSISTENCE_FAILED':
                a['error']='DB_REJECTED';a['disposition']='SAFETY_STOP'
            elif a['b2_outcome'] in LOCAL:
                a['error']='SOURCE_REJECTED';a['disposition']='SAFELY_REJECTED'
            else:a['error']='SCOPE_REJECTED';a['disposition']='SAFETY_STOP'
        if source and (source['outcome'] in SAFETY or source['budget_state']=='EXHAUSTED'):
            a['disposition']='SAFETY_STOP';a['error']='SOURCE_REJECTED'
    except Exception:a['error']='DB_REJECTED';a['disposition']='UNCERTAIN'
    finally:
        event.remove(engine,'before_execute',guard)
        try:
            meter.close()
            if hasattr(engine.pool,'checkedout') and engine.pool.checkedout():raise ValueError('CONNECTION_LEAK')
            a['cleanup']='CLOSED'
        except Exception:a['cleanup']='FAILED';a['error']='CLEANUP_FAILED';a['disposition']='SAFETY_STOP'
        a['statements']=meter.counts
    validate_record(a,row);return a


