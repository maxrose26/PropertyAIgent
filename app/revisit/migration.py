"""Separate fail-closed local migration; P0-A artifact/allowance unchanged."""
from sqlalchemy import inspect, text, UniqueConstraint, CheckConstraint
from app.db.models import Base
from app.db.ah_disposable_postgres import require_connection
from app.revisit.schema import metadata, TABLE_NAMES, IMMUTABLE
from scripts.migrate_p0a import verify_definitions

FUNCTION = """CREATE FUNCTION public.revisit_deny_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'revisit evidence is immutable'; END $$"""


STAGE_EXPRESSION = "(stage)::text = ANY ((ARRAY['documents'::character varying, 'relationships'::character varying])::text[])"


def validate_stage_check(rows):
    # Only remove enclosing expression parentheses; do not strip casts,
    # operators, literals or internal parentheses. SQLAlchemy's inspector
    # uses pretty=True, which is deliberately not the representation queried.
    from sqlalchemy.util import strip_outer_parens
    if (len(rows) != 1 or rows[0]['name'] != 'ck_revisit_stage'
            or not rows[0]['validated'] or rows[0]['no_inherit']
            or strip_outer_parens(rows[0]['expression']) != STAGE_EXPRESSION):
        raise RuntimeError('revisit stage check drift: ' + repr([dict(r) for r in rows]))


def verify(conn, allow_missing=False):
    require_connection(conn)
    inspector = inspect(conn)
    tables = set(inspector.get_table_names(schema='public'))
    extra = tables - set(Base.metadata.tables) - TABLE_NAMES
    if extra:
        raise RuntimeError('unrelated schema tables: ' + ','.join(sorted(extra)))
    p0a_missing = verify_definitions(conn, allow_missing=allow_missing)
    present = tables & TABLE_NAMES
    if not present and allow_missing:
        return {'p0a_missing': p0a_missing, 'revisit_missing': True}
    if present != TABLE_NAMES:
        raise RuntimeError('partial/missing revisit schema')
    for table in metadata.sorted_tables:
        columns = {c['name']: c for c in inspector.get_columns(table.name, schema='public')}
        if set(columns) != set(table.c.keys()):
            raise RuntimeError('revisit column drift')
        for c in table.c:
            actual = columns[c.name]
            expected = str(c.type.compile(dialect=conn.dialect)).replace('FLOAT', 'DOUBLE PRECISION')
            if str(actual['type'].compile(dialect=conn.dialect)) != expected or actual['nullable'] != c.nullable:
                raise RuntimeError('revisit type/nullability drift')
            default = actual.get('default')
            if c.primary_key:
                if not default or not default.startswith('nextval('):
                    raise RuntimeError('revisit identity drift')
            elif default is not None:
                raise RuntimeError('revisit default drift')
        if inspector.get_pk_constraint(table.name)['constrained_columns'] != ['id']:
            raise RuntimeError('revisit primary key drift')
        expected_uq = {(c.name, tuple(x.name for x in c.columns)) for c in table.constraints if isinstance(c, UniqueConstraint)}
        actual_uq = {(c['name'], tuple(c['column_names'])) for c in inspector.get_unique_constraints(table.name)}
        if actual_uq != expected_uq:
            raise RuntimeError('revisit unique drift')
        expected_fk = {(fk.parent.name, fk.column.table.name, fk.column.name) for fk in table.foreign_keys}
        actual_fk = {(f['constrained_columns'][0], f['referred_table'], f['referred_columns'][0]) for f in inspector.get_foreign_keys(table.name)}
        if actual_fk != expected_fk or any(f.get('options') for f in inspector.get_foreign_keys(table.name)):
            raise RuntimeError('revisit foreign key drift')
        if any(not i.get('duplicates_constraint') for i in inspector.get_indexes(table.name)):
            raise RuntimeError('revisit index drift')
        # PostgreSQL rewrites IN checks; compare against its canonical expression.
        checks = inspector.get_check_constraints(table.name)
        if table.name == 'revisit_work':
            canonical = conn.execute(text("""SELECT k.conname AS name,
                pg_get_expr(k.conbin,k.conrelid,false) AS expression,
                k.convalidated AS validated, k.connoinherit AS no_inherit
                FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relname='revisit_work'
                  AND k.contype='c' ORDER BY k.conname""")).mappings().all()
            validate_stage_check(canonical)
        elif checks:
            raise RuntimeError('unexpected revisit check')
    triggers = list(conn.execute(text("""SELECT c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid)
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname LIKE 'revisit_%' AND NOT t.tgisinternal""")))
    expected_triggers = {(t.name, 'revisit_immutable_' + t.name, 'O',
        'CREATE TRIGGER revisit_immutable_' + t.name + ' BEFORE DELETE OR UPDATE OR TRUNCATE ON public.' + t.name + ' FOR EACH STATEMENT EXECUTE FUNCTION revisit_deny_mutation()') for t in IMMUTABLE}
    if set(map(tuple, triggers)) != expected_triggers:
        raise RuntimeError('revisit trigger drift')
    function_body = conn.execute(text("SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='revisit_deny_mutation'")).scalars().all()
    if function_body != [" BEGIN RAISE EXCEPTION 'revisit evidence is immutable'; END "]:
        raise RuntimeError('revisit function drift')
    return {'p0a_missing': p0a_missing, 'revisit_missing': False}


def migrate(conn):
    """Caller owns one transaction. Ordinary/unattested engines rejected."""
    state = verify(conn, allow_missing=True)
    if state['p0a_missing']:
        raise RuntimeError('install approved P0-A artifact first')
    if state['revisit_missing']:
        metadata.create_all(conn, checkfirst=False)
        conn.execute(text(FUNCTION))
        for table in IMMUTABLE:
            conn.execute(text(f'CREATE TRIGGER revisit_immutable_{table.name} BEFORE UPDATE OR DELETE OR TRUNCATE ON public.{table.name} FOR EACH STATEMENT EXECUTE FUNCTION public.revisit_deny_mutation()'))
    verify(conn)


def apply_local(engine):
    from app.db.ah_disposable_postgres import require_engine
    require_engine(engine)
    with engine.begin() as conn:
        migrate(conn)
