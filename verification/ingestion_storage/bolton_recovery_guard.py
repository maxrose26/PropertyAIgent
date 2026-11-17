"""Narrow adapter around unchanged #213 recovery; no connection or retry.

The pinned recovery takes table/controller locks BEFORE pending(), which is
where its OTHER_WORK query runs. Strengthen that one predicate under the same
locks. Every original prerequisite, mutation, cleanup and readback is retained.
"""
import hashlib
from pathlib import Path

SOURCE_SHA256 = '5bd306a86bc8b273d3bd0d778e7fc7803e737d7a589828f9f0405bc844a18d4a'
OLD = "SELECT count(*) FROM public.ingestion_work_items WHERE key<>%s AND (phase IN ('SOURCE_INTENT','WRITE_INTENT') OR state='PERSISTENCE_UNCERTAIN' OR authority=%s)"
NEW = OLD.replace("state='PERSISTENCE_UNCERTAIN'", "state IN ('CLAIMED','PERSISTENCE_UNCERTAIN')")


def recover(connection, binding, *, pinned_module):
    if hashlib.sha256(Path(pinned_module.__file__).read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('BOLTON_PINNED_RECOVERY_SOURCE_DRIFT')

    class Guarded:
        def __getattr__(self, name):
            return getattr(connection, name)

        def execute(self, query, params=None):
            return connection.execute(NEW if query == OLD else query, params)

    return pinned_module.recover(Guarded(), binding)
