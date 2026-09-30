"""Explicit, local-only AH migration. Deliberately NOT in Base.metadata.

Importing this module or starting the app never creates schema. Keeping separate
metadata also prevents the platform's broad migration from creating these tables
without their append-only protections.
"""
from contextlib import contextmanager
from sqlalchemy import (MetaData, Table, Column as C, Integer as I, String as S,
                        Text as T, Numeric, Date, DateTime, Boolean, ForeignKey,
                        CheckConstraint as Check, UniqueConstraint, Index, inspect, text)
from sqlalchemy.schema import CreateTable, CreateIndex

metadata = MetaData()
for name in ('applications', 'sites', 'documents'):
    Table(name, metadata, C('id', I, primary_key=True))


def fk(name, table, nullable=False):
    return C(name, I, ForeignKey(table + '.id', ondelete='RESTRICT'), nullable=nullable)


def string(name, length=200, nullable=False):
    return C(name, S(length), nullable=nullable)


claims = Table('ah_source_claims', metadata,
    C('id', I, primary_key=True), C('schema_version', I, nullable=False, server_default='1'),
    fk('application_id', 'applications'), fk('site_id', 'sites', True),
    fk('scheme_application_id', 'applications'),
    string('scope_kind', 20), string('scope_key'), string('scope_label', 300),
    C('scope_basis', T, nullable=False), string('metric', 30), string('tenure_name', 100, True),
    string('qualifier', 20),
    *[C(n, Numeric(18, 6)) for n in ('value', 'lower_bound', 'upper_bound')],
    C('unknown_reason', T), fk('document_id', 'documents'),
    C('document_url_snapshot', T), C('document_title_snapshot', T),
    string('document_content_hash', 64, True), C('document_date', Date),
    C('document_date_missing_reason', T), C('passage_text', T, nullable=False),
    C('passage_locator', T, nullable=False), C('page_start', I), C('page_end', I),
    string('extracted_text_hash', 64, True), C('passage_start', I), C('passage_end', I),
    string('passage_hash', 64), string('planning_stage', 20),
    fk('stage_document_id', 'documents', True), C('stage_passage_text', T), C('stage_passage_locator', T),
    string('origin_kind', 20), string('origin_reference'), string('extractor_version', 200, True),
    string('created_by'), C('recorded_at', DateTime(timezone=True), nullable=False),
    string('import_key'), string('payload_hash', 64),
    UniqueConstraint('import_key', name='uq_ah_import_key'),
    Check('schema_version = 1', name='ah_schema_v1'),
    Check("metric IN ('affordable_count','tenure_count')", name='ah_metric'),
    Check("(metric='tenure_count' AND tenure_name IS NOT NULL AND length(trim(tenure_name))>0) OR (metric='affordable_count' AND tenure_name IS NULL)", name='ah_tenure'),
    Check("scope_kind IN ('whole_scheme','component','phase','unclear')", name='ah_scope_kind'),
    Check("(scope_kind='whole_scheme' AND scope_key='WHOLE_SCHEME') OR (scope_kind='unclear' AND scope_key='UNRESOLVED') OR (scope_kind IN ('component','phase') AND scope_key NOT IN ('WHOLE_SCHEME','UNRESOLVED'))", name='ah_scope_key'),
    Check("planning_stage IN ('proposed','approved','legally_secured','unresolved')", name='ah_stage'),
    Check("origin_kind IN ('reviewed_import','extraction')", name='ah_origin'),
    Check("(qualifier IN ('exact','approximate') AND value IS NOT NULL AND lower_bound IS NULL AND upper_bound IS NULL AND unknown_reason IS NULL) OR (qualifier='range' AND value IS NULL AND lower_bound IS NOT NULL AND upper_bound IS NOT NULL AND lower_bound<=upper_bound AND unknown_reason IS NULL) OR (qualifier='at_least' AND value IS NULL AND lower_bound IS NOT NULL AND upper_bound IS NULL AND unknown_reason IS NULL) OR (qualifier='up_to' AND value IS NULL AND lower_bound IS NULL AND upper_bound IS NOT NULL AND unknown_reason IS NULL) OR (qualifier='unknown' AND value IS NULL AND lower_bound IS NULL AND upper_bound IS NULL AND unknown_reason IS NOT NULL AND length(trim(unknown_reason))>0)", name='ah_quantity_shape'),
    *[Check(f'{n} IS NULL OR ({n} >= 0 AND {n} < 1000000000000)', name='ah_' + n) for n in ('value','lower_bound','upper_bound')],
    Check('(document_date IS NULL AND document_date_missing_reason IS NOT NULL AND length(trim(document_date_missing_reason))>0) OR (document_date IS NOT NULL AND document_date_missing_reason IS NULL)', name='ah_date'),
    Check('(page_start IS NULL AND page_end IS NULL) OR (page_start IS NOT NULL AND page_end IS NOT NULL AND page_start>0 AND page_end>=page_start)', name='ah_pages'),
    Check('(passage_start IS NULL AND passage_end IS NULL) OR (passage_start IS NOT NULL AND passage_end IS NOT NULL AND extracted_text_hash IS NOT NULL AND passage_start>=0 AND passage_end>passage_start)', name='ah_offsets'),
    Check('(stage_document_id IS NULL AND stage_passage_text IS NULL AND stage_passage_locator IS NULL) OR (stage_document_id IS NOT NULL AND stage_passage_text IS NOT NULL AND stage_passage_locator IS NOT NULL AND length(trim(stage_passage_text))>0 AND length(trim(stage_passage_locator))>0)', name='ah_stage_source'),
)
for n in ('scope_key','scope_label','scope_basis','passage_text','passage_locator','origin_reference','created_by','import_key'):
    claims.append_constraint(Check(f'length(trim({n}))>0', name='ah_nonempty_' + n))
for n in ('document_content_hash','extracted_text_hash','passage_hash','payload_hash'):
    # Portable hex validation (NULL is explicitly allowed only on nullable columns).
    expr = n
    for ch in '0123456789abcdef':
        expr = f"replace({expr},'{ch}','')"
    claims.append_constraint(Check(f'{n} IS NULL OR (length({n})=64 AND length({expr})=0)', name='ah_hex_' + n))
Index('ix_ah_application_metric', claims.c.application_id, claims.c.metric)
Index('ix_ah_context', claims.c.site_id, claims.c.scheme_application_id, claims.c.scope_kind, claims.c.scope_key, claims.c.metric)
Index('ix_ah_document', claims.c.document_id)
Index('ix_ah_payload', claims.c.payload_hash)

events = Table('ah_claim_events', metadata,
    C('id', I, primary_key=True), fk('claim_id', 'ah_source_claims'), C('sequence', I, nullable=False),
    fk('previous_event_id', 'ah_claim_events', True), string('action', 20),
    fk('related_claim_id', 'ah_source_claims', True), fk('reversed_event_id', 'ah_claim_events', True),
    *[C(n, Boolean(create_constraint=True, name='ah_bool_' + n), nullable=False) for n in ('source_checked','scope_checked','stage_checked')],
    string('actor_id'), C('reason', T, nullable=False), C('recorded_at', DateTime(timezone=True), nullable=False),
    string('request_key'), string('request_hash', 64),
    UniqueConstraint('claim_id','sequence', name='uq_ah_sequence'),
    UniqueConstraint('request_key', name='uq_ah_request'),
    Check('sequence>0', name='ah_sequence'),
    Check('(sequence=1 AND previous_event_id IS NULL) OR (sequence>1 AND previous_event_id IS NOT NULL)', name='ah_previous'),
    Check("action IN ('ACCEPT','REJECT','NEEDS_REVIEW','WITHDRAW','CORRECT','SUPERSEDE','CONFLICT','REVERSE_LINK')", name='ah_action'),
    Check("(action IN ('CORRECT','SUPERSEDE','CONFLICT') AND related_claim_id IS NOT NULL AND related_claim_id<>claim_id AND reversed_event_id IS NULL) OR (action='REVERSE_LINK' AND reversed_event_id IS NOT NULL AND related_claim_id IS NULL) OR (action IN ('ACCEPT','REJECT','NEEDS_REVIEW','WITHDRAW') AND related_claim_id IS NULL AND reversed_event_id IS NULL)", name='ah_relation'),
    Check("(action='ACCEPT' AND source_checked AND scope_checked) OR (action<>'ACCEPT' AND NOT source_checked AND NOT scope_checked AND NOT stage_checked)", name='ah_check_flags'),
    Check('length(trim(actor_id))>0 AND length(trim(reason))>0 AND length(trim(request_key))>0', name='ah_event_nonempty'),
    Check('length(request_hash)=64', name='ah_request_hash'),
)
Index('ix_ah_related', events.c.related_claim_id)
Index('ix_ah_reversed', events.c.reversed_event_id)
TABLES = (claims, events)


def require_local(engine):
    """No implicit DATABASE_URL; no remote write capability in this increment."""
    if engine.dialect.name == 'sqlite':
        return
    if engine.dialect.name == 'postgresql':
        from app.db.ah_disposable_postgres import require_engine
        require_engine(engine)
        return
    raise ValueError('AH writes require an explicitly supplied disposable local database')


@contextmanager
def local_transaction(engine):
    require_local(engine)
    with engine.connect() as conn:
        if conn.dialect.name == 'sqlite':
            conn.exec_driver_sql('PRAGMA foreign_keys=ON')
            conn.exec_driver_sql('PRAGMA busy_timeout=5000')
            conn.commit()
            conn.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            conn.begin()
            conn.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
            conn.exec_driver_sql("SET LOCAL statement_timeout = '15s'")
            from app.db.ah_disposable_postgres import require_connection
            require_connection(conn)
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def protections(dialect):
    result = {}
    if dialect == 'sqlite':
        for table in TABLES:
            for action in ('UPDATE','DELETE'):
                name = f'{table.name}_deny_{action.lower()}'
                result[name] = f"CREATE TRIGGER {name} BEFORE {action} ON {table.name} BEGIN SELECT RAISE(ABORT, 'AH history is append-only'); END"
            # SQLite REPLACE can bypass DELETE triggers unless recursive_triggers
            # is enabled. Guard conflicting INSERTs independently of that pragma.
            condition = 'id=NEW.id OR import_key=NEW.import_key' if table is claims else 'id=NEW.id OR request_key=NEW.request_key OR (claim_id=NEW.claim_id AND sequence=NEW.sequence)'
            name = table.name + '_deny_replace'
            result[name] = f"CREATE TRIGGER {name} BEFORE INSERT ON {table.name} WHEN EXISTS (SELECT 1 FROM {table.name} WHERE {condition}) BEGIN SELECT RAISE(ABORT, 'AH history is append-only'); END"
    else:
        result['ah_deny_mutation'] = "CREATE FUNCTION ah_deny_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'AH history is append-only'; END; $$"
        for table in TABLES:
            name = table.name + '_deny_mutation'
            result[name] = f'CREATE TRIGGER {name} BEFORE UPDATE OR DELETE OR TRUNCATE ON {table.name} FOR EACH STATEMENT EXECUTE FUNCTION ah_deny_mutation()'
    return result


def verify_schema(conn):
    if conn.dialect.name != 'sqlite':
        from app.db.ah_disposable_postgres import verify_postgres
        return verify_postgres(conn)
    inspector = inspect(conn)
    for table in TABLES:
        if not inspector.has_table(table.name):
            raise ValueError('AH schema missing: ' + table.name)
        actual = inspector.get_columns(table.name)
        expected = list(table.columns)
        if [c['name'] for c in actual] != [c.name for c in expected]:
            raise ValueError('AH incompatible columns: ' + table.name)
        if inspector.get_pk_constraint(table.name)['constrained_columns'] != ['id']:
            raise ValueError('AH incompatible primary key')
        for a, e in zip(actual, expected):
            if str(a['type'].compile(dialect=conn.dialect)).upper() != str(e.type.compile(dialect=conn.dialect)).upper() or (not e.primary_key and a['nullable'] != e.nullable):
                raise ValueError('AH incompatible type/nullability: ' + e.name)
        unique = {tuple(x['column_names']) for x in inspector.get_unique_constraints(table.name)}
        if unique != {tuple(c.name for c in u.columns) for u in table.constraints if isinstance(u, UniqueConstraint)}:
            raise ValueError('AH incompatible unique constraints')
        actual_checks = {c['name']: ''.join(c['sqltext'].split()).replace('"','') for c in inspector.get_check_constraints(table.name)}
        expected_checks = {c.name for c in table.constraints if isinstance(c, Check) and
                           (conn.dialect.name=='sqlite' or not str(c.name).startswith('ah_bool_'))}
        if set(actual_checks) != expected_checks:
            raise ValueError('AH incompatible check inventory')
        for c in table.constraints:
            if isinstance(c, Check):
                expected_sql = ''.join(str(c.sqltext.compile(dialect=conn.dialect,compile_kwargs={'literal_binds':True})).split()).replace('"','').replace(table.name + '.', '')
                if conn.dialect.name == 'sqlite' and actual_checks.get(c.name) != expected_sql:
                    raise ValueError('AH incompatible check: ' + str(c.name))
        actual_fk = {(tuple(f['constrained_columns']), f['referred_table'], tuple(f['referred_columns']), f.get('options',{}).get('ondelete')) for f in inspector.get_foreign_keys(table.name)}
        expected_fk = {(tuple(c.name for c in f.columns), f.elements[0].column.table.name, tuple(e.column.name for e in f.elements), 'RESTRICT') for f in table.foreign_key_constraints}
        if actual_fk != expected_fk:
            raise ValueError('AH incompatible foreign keys')
        if {(i['name'],tuple(i['column_names']),bool(i['unique'])) for i in inspector.get_indexes(table.name) if not i.get('duplicates_constraint')} != {(i.name,tuple(c.name for c in i.columns),i.unique) for i in table.indexes}:
            raise ValueError('AH incompatible indexes')
    if conn.dialect.name == 'sqlite':
        stored = {r[0]:r[1] for r in conn.execute(text("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))}
        for name, sql in protections('sqlite').items():
            if stored.get(name, '').rstrip(';') != sql:
                raise ValueError('AH missing/incompatible append-only protection: ' + name)
    else:
        names = set(conn.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN ('ah_source_claims'::regclass,'ah_claim_events'::regclass)")).scalars())
        if names != {t.name + '_deny_mutation' for t in TABLES}:
            raise ValueError('AH missing append-only protections')


def migrate_local(engine):
    """Same canonical schema path; ordinary PostgreSQL remains disabled."""
    authority = None
    if engine.dialect.name != 'sqlite':
        from app.db.ah_disposable_postgres import require_engine
        authority = require_engine(engine)
    previous = authority.signature if authority else None
    try:
        with local_transaction(engine) as conn:
            present = [inspect(conn).has_table(t.name) for t in TABLES]
            if any(present):
                verify_schema(conn)  # Never adopt untrusted/pre-existing PostgreSQL objects.
                return False
            for name in ('applications','sites','documents'):
                if not inspect(conn).has_table(name):
                    raise ValueError('Missing existing table: ' + name)
            for table in TABLES:
                table.create(conn)
            for sql in protections(conn.dialect.name).values():
                conn.exec_driver_sql(sql)
            if authority:
                from app.db.ah_disposable_postgres import attest_created_schema
                attest_created_schema(conn)
            verify_schema(conn)
        return True
    except BaseException:
        if authority:
            authority.signature = previous
        raise
