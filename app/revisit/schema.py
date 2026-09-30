"""Explicit additive revisit component metadata; never mutates P0-A Base."""
from sqlalchemy import (MetaData, Table, Column as C, Integer, String, Float, Text,
                        JSON, LargeBinary, ForeignKey, UniqueConstraint, CheckConstraint)

from app.db.models import ScrapeRun

metadata = MetaData()
work = Table('revisit_work', metadata,
    C('id', Integer, primary_key=True), C('council', String(100), nullable=False),
    C('reference', String(255), nullable=False), C('stage', String(30), nullable=False),
    C('route', String(80), nullable=False), C('cursor', Text, nullable=True),
    C('generation', Integer, nullable=False), C('owner_run', ForeignKey(ScrapeRun.__table__.c.id)), C('owner_invocation', String(100)),
    C('last_attempt', Float), C('last_success', Float), C('due', Float, nullable=False),
    C('failures', Integer, nullable=False), C('outcome', String(30), nullable=False), C('reason', Text),
    UniqueConstraint('council','reference','stage','route', name='uq_revisit_work'),
    CheckConstraint("stage IN ('documents','relationships')", name='ck_revisit_stage'))
attempts = Table('revisit_attempts', metadata,
    C('id', Integer, primary_key=True), C('work_id', ForeignKey(work.c.id), nullable=False),
    C('generation', Integer, nullable=False), C('run_id', ForeignKey(ScrapeRun.__table__.c.id), nullable=False),
    C('started', Float, nullable=False), C('finished', Float), C('outcome', String(30), nullable=False),
    C('response_token', String(64)), C('report', JSON),
    UniqueConstraint('work_id','generation', name='uq_revisit_attempt'))
versions = Table('revisit_content_versions', metadata,
    C('id', Integer, primary_key=True), C('council', String(100), nullable=False),
    C('reference', String(255), nullable=False), C('url', Text, nullable=False),
    C('digest', String(64), nullable=False), C('body', LargeBinary, nullable=False),
    UniqueConstraint('council','reference','url','digest', name='uq_revisit_content'))
observations = Table('revisit_document_observations', metadata,
    C('id', Integer, primary_key=True), C('attempt_id', ForeignKey(attempts.c.id), nullable=False),
    C('version_id', ForeignKey(versions.c.id), nullable=False),
    C('item', String(64), nullable=False), C('observed', Float, nullable=False),
    C('provenance', JSON, nullable=False),
    UniqueConstraint('attempt_id','item', name='uq_revisit_document_observation'))
relationships = Table('revisit_relationship_observations', metadata,
    C('id', Integer, primary_key=True), C('attempt_id', ForeignKey(attempts.c.id), nullable=False),
    C('item', String(64), nullable=False), C('source_council', String(100), nullable=False),
    C('source_reference', String(255), nullable=False), C('target_council', String(100), nullable=False),
    C('target_reference', String(255), nullable=False), C('kind', String(40), nullable=False),
    C('route', String(80), nullable=False), C('confidence', String(40), nullable=False),
    C('review', String(40), nullable=False), C('citation', Text), C('observed', Float, nullable=False),
    UniqueConstraint('attempt_id','item', name='uq_revisit_relationship_observation'))
TABLE_NAMES = frozenset(metadata.tables)
IMMUTABLE = (versions, observations, relationships)
