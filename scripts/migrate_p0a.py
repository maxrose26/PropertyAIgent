"""Exact P0-A additive migration. No backfills, evidence writes or generic repair.

Default is read-only preflight. --apply requires separate operator approval.
All DDL and definition verification share one PostgreSQL transaction. Existing
objects are verified, never silently accepted solely because their names exist.
"""
from __future__ import annotations
import argparse
from sqlalchemy import inspect, text
from app.db.models import Base
from app.db.session import get_engine

TABLE = 'parent_lookup_work'
COLUMN = ('scrape_runs', 'progress')


def _type(column_type, dialect):
    value = str(column_type.compile(dialect=dialect)).upper()
    return 'DOUBLE PRECISION' if value == 'FLOAT' else value


def verify_definitions(connection, *, allow_missing):
    if connection.dialect.name != 'postgresql':
        raise RuntimeError('P0-A migration requires PostgreSQL')
    inspector = inspect(connection)
    existing = set(inspector.get_table_names(schema='public'))
    missing = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            if allow_missing and table.name == TABLE:
                missing.append(TABLE)
                continue
            raise RuntimeError(f'unexpected missing table: {table.name}')
        actual = {c['name']: c for c in inspector.get_columns(table.name, schema='public')}
        expected = {c.name: c for c in table.columns}
        extra = set(actual) - set(expected)
        if extra:
            raise RuntimeError(f'unexpected columns: {table.name} {sorted(extra)}')
        for name, column in expected.items():
            if name not in actual:
                if allow_missing and (table.name, name) == COLUMN:
                    missing.append('scrape_runs.progress')
                    continue
                raise RuntimeError(f'unexpected missing column: {table.name}.{name}')
            observed = actual[name]
            if (_type(observed['type'], connection.dialect) != _type(column.type, connection.dialect)
                    or observed['nullable'] != column.nullable):
                raise RuntimeError(f'column definition drift: {table.name}.{name}')
            if table.name == TABLE or (table.name, name) == COLUMN:
                # SERIAL PK's nextval is expected; other model defaults are Python-only.
                default = observed.get('default')
                if column.primary_key:
                    if not default or not default.startswith('nextval('):
                        raise RuntimeError('P0-A primary key generation drift')
                elif default is not None or observed.get('identity') or observed.get('computed'):
                    raise RuntimeError(f'P0-A default/generated definition drift: {name}')
        if table.name != TABLE:
            continue
        if inspector.get_pk_constraint(TABLE, schema='public')['constrained_columns'] != ['id']:
            raise RuntimeError('P0-A primary key drift')
        unique = {(u['name'], tuple(u['column_names'])) for u in inspector.get_unique_constraints(TABLE, schema='public')}
        if unique != {('uq_parent_lookup_reference', ('council_code', 'reference_key'))}:
            raise RuntimeError('P0-A unique constraint drift')
        foreign = inspector.get_foreign_keys(TABLE, schema='public')
        targets = {(tuple(f['constrained_columns']), f['referred_table'], tuple(f['referred_columns'])) for f in foreign}
        if targets != {(('council_code',), 'councils', ('code',)),
                       (('owner_scrape_run_id',), 'scrape_runs', ('id',)),
                       (('resolved_application_id',), 'applications', ('id',))}:
            raise RuntimeError('P0-A foreign key drift')
        if any(f.get('options') or f.get('referred_schema') not in (None, 'public') for f in foreign):
            raise RuntimeError('P0-A foreign key options drift')
        indexes = [i for i in inspector.get_indexes(TABLE, schema='public') if not i.get('duplicates_constraint')]
        if len(indexes) != 1 or indexes[0]['name'] != 'ix_parent_lookup_due' or indexes[0]['unique'] or indexes[0]['column_names'] != ['council_code','next_eligible_at','last_started_at'] or any(indexes[0].get('dialect_options', {}).values()):
            raise RuntimeError('P0-A due index drift')
        if inspector.get_check_constraints(TABLE, schema='public'):
            raise RuntimeError('unexpected P0-A check constraint')
    return missing


def migrate_p0a(engine, *, apply=False):
    with engine.begin() as connection:
        if connection.dialect.name != 'postgresql':
            raise RuntimeError('P0-A migration requires PostgreSQL')
        if not apply:
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
        connection.exec_driver_sql("SET LOCAL search_path = public")
        connection.exec_driver_sql("SET LOCAL statement_timeout = '30s'")
        connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
        missing = verify_definitions(connection, allow_missing=True)
        if apply:
            if 'scrape_runs.progress' in missing:
                connection.execute(text('ALTER TABLE public.scrape_runs ADD COLUMN progress TEXT NULL'))
            if TABLE in missing:
                Base.metadata.tables[TABLE].create(connection, checkfirst=False)
            verify_definitions(connection, allow_missing=False)
        return missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Execute ONLY after explicit release approval')
    args = parser.parse_args()
    changes = migrate_p0a(get_engine(), apply=args.apply)
    print({'mode': 'applied' if args.apply else 'read-only preflight', 'p0a_changes': changes})


if __name__ == '__main__':
    main()
