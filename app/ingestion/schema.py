"""Explicit additive operational schema, deliberately outside application Base.

No page-load/init_db migration. No Application or buyer FK is required to retain
an application identity. PostgreSQL tables are deny-by-default under RLS.
"""
from sqlalchemy import MetaData, Table, Column, String, Integer, Float, JSON, ForeignKey, CheckConstraint
metadata=MetaData()
WorkItem=Table('ingestion_work_items',metadata,
    Column('key',String(64),primary_key=True),Column('subject',JSON,nullable=False),
    Column('task',String(32),nullable=False),Column('contract',String(100),nullable=False),
    Column('revision',String(100),nullable=False),Column('dependencies',JSON,nullable=False),
    Column('priority',Integer,nullable=False),Column('eligible_at',Float,nullable=False),
    Column('state',String(32),nullable=False),Column('reason',String(200),nullable=True),
    Column('next_action',String(100),nullable=False),Column('limits',JSON,nullable=False),
    Column('authority',String(100),nullable=True),Column('attempt_count',Integer,nullable=False),
    Column('max_attempts',Integer,nullable=False),Column('fence',Integer,nullable=False),
    Column('owner',String(100),nullable=True),Column('lease_until',Float,nullable=True),
    Column('phase',String(32),nullable=False),Column('checkpoint',JSON,nullable=True),
    Column('outcome',JSON,nullable=True),
    CheckConstraint('attempt_count >= 0 AND max_attempts BETWEEN 1 AND 3'),
    CheckConstraint('priority BETWEEN 0 AND 100'),
)
WorkAttempt=Table('ingestion_work_attempts',metadata,
    Column('work_key',String(64),ForeignKey(WorkItem.c.key),primary_key=True),
    Column('fence',Integer,primary_key=True),Column('owner',String(100),nullable=False),
    Column('started_at',Float,nullable=False),Column('finished_at',Float,nullable=True),
    Column('authority',String(100),nullable=False),Column('phase',String(32),nullable=False),
    Column('outcome',JSON,nullable=True),Column('checkpoint',JSON,nullable=True),
)
CONTROL='0'*64


def install(engine):
    """Explicit migration only. Production execution requires separate approval.

    Existing tables are verified, not repaired. No production roles are granted.
    """
    from sqlalchemy import inspect,text
    existing=inspect(engine)
    for table in metadata.tables.values():
        if existing.has_table(table.name):
            actual={c['name'] for c in existing.get_columns(table.name)}
            if actual!={c.name for c in table.columns}:raise ValueError('LEDGER_SCHEMA_MISMATCH')
    with engine.begin() as c:
        metadata.create_all(c)
        if engine.dialect.name=='postgresql':
            for name in metadata.tables:
                c.execute(text(f'REVOKE ALL ON TABLE {name} FROM PUBLIC'))
                for role in ('anon','authenticated','service_role'):
                    if c.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:r'),dict(r=role)).scalar():
                        c.execute(text(f'REVOKE ALL ON TABLE {name} FROM "{role}"'))
                c.execute(text(f'ALTER TABLE {name} ENABLE ROW LEVEL SECURITY'))
                c.execute(text(f'ALTER TABLE {name} FORCE ROW LEVEL SECURITY'))
        if c.execute(WorkItem.select().where(WorkItem.c.key==CONTROL)).first() is None:
            c.execute(WorkItem.insert().values(key=CONTROL,subject={'kind':'CONTROL'},task='CONTROL',contract='v1',revision='v1',dependencies=[],priority=0,eligible_at=0,state='CONTROL',reason=None,next_action='OPERATOR_REVIEW',limits={},authority=None,attempt_count=0,max_attempts=1,fence=0,phase='IDLE',checkpoint=None,outcome={'global_stop':None,'grants':{}}))


def uninstall_empty(engine):
    """Disposable rollback demonstration; never destroys populated evidence."""
    from sqlalchemy import select,func
    with engine.begin() as c:
        if c.scalar(select(func.count()).select_from(WorkAttempt)) or c.scalar(select(func.count()).select_from(WorkItem).where(WorkItem.c.key!=CONTROL)):
            raise ValueError('PRESERVE_POPULATED_LEDGER')
        metadata.drop_all(c)
