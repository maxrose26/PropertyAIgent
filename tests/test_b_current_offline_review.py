"""Independent offline compatibility check for one version-pinned B inspection.

This never connects to a live database. PostgreSQL fixture is disposable only.
The historical fixed-B oracle/client remain unchanged and intentionally red.
"""
import hashlib
import re
from pathlib import Path
from tests.test_b_readonly_inspection import world

ROOT = Path("docs/design/daily-intake-20261029")
HISTORICAL = ROOT / "b-readonly.sql"
CANDIDATE = ROOT / "b-readonly-stage4-6bc3ae0-review.sql"
OLD_SHA = "dba6b809c50b9bd937b2f509fc05c20de9d69499ca4394e9007ef3af196b481c"
NEW_SHA = "1d05b3f4476a8ad2a14aa083eb15396c9d157265dc19254df738777673cd995d"
POLICY_SOURCE_HEAD = "6bc3ae04bccc5c01a2083bac8a1dbff7a12a54b0"
HEADER = (
    "-- OFFLINE REVIEW CANDIDATE ONLY; NOT AUTHORISED FOR EXECUTION.\n"
    "-- Source policy inventory: stacked PR #221 at " + POLICY_SOURCE_HEAD + ".\n"
    "-- This is NOT the historical B approval; separate independent review and explicit\n"
    "-- execution approval required. Historical b-readonly.sql and its fixed client stay\n"
    "-- unchanged; the original client intentionally rejects this version.\n"
)


def statements(sql):
    return [s.strip() for s in re.sub(r"--[^\n]*", "", sql).split(";") if s.strip()]


def inspect(c, sql):
    records = []
    try:
        for statement in statements(sql):
            cur = c.execute(statement)
            if cur.description:
                records.append(cur.fetchall())
    finally:
        if c.info.transaction_status:
            c.execute("ROLLBACK")
    return records


def test_review_candidate_is_exactly_one_versioned_function_hash():
    from verification.ingestion_storage.operational_owner import Owner
    from importlib.util import spec_from_file_location, module_from_spec
    original = HISTORICAL.read_text()
    candidate = CANDIDATE.read_text()
    spec = spec_from_file_location("frozen_b_client_for_compare", ROOT / "b-readonly-client.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hashlib.sha256(original.encode()).hexdigest() == module.SQL_SHA
    assert original.count(OLD_SHA) == 1
    assert candidate == HEADER + original.replace(OLD_SHA, NEW_SHA)
    expected = {k: hashlib.sha256(v.encode()).hexdigest()
                for k, v in Owner.daily_intake_inventory().items()}
    assert expected["ingestion_register_bolton_exception"] == NEW_SHA
    assert len(expected) == 6
    assert sorted([name for name, sha in expected.items()
                   if "('%s','%s')" % (name, sha) not in original]) == [
                       "ingestion_register_bolton_exception"]
    assert all("('%s','%s')" % (name, sha) in candidate for name, sha in expected.items())
    prepared = statements(candidate)
    assert len(prepared) == 16
    assert prepared[0].endswith("READ ONLY") and prepared[-1] == "ROLLBACK"
    assert all(x.strip().startswith(("BEGIN", "SET LOCAL", "SELECT", "WITH", "ROLLBACK"))
               for x in prepared)
    assert not re.search(r"\b(GRANT|SET ROLE|CREATE|INSERT|UPDATE|DELETE|TRUNCATE|CALL|DO)\b",
                         re.sub(r"'[^']*'", "", "\n".join(prepared)), re.I)


def test_current_and_historical_b_observations_discriminate_in_disposable_postgres(world):
    current = inspect(world["boot"], CANDIDATE.read_text())
    original = inspect(world["boot"], HISTORICAL.read_text())
    assert len(current) == len(original) == 10
    assert len(current[5]) == len(original[5]) == 6
    for a, b in zip(current[5], original[5]):
        assert a[0] == b[0]
        assert a[2] == b[2]   # observed body hash must not change across read-only inspections
        assert a[4:] == b[4:]
        assert (a[3] is True)  # every function matches the proposed, current inventory
        assert (b[3] is False) == (b[0] == "ingestion_register_bolton_exception")
    assert all(r[7] == 1 for r in current[5])  # no overload
    assert current[0][0][3] == "on"
    assert len(current[1]) == 2 and len(current[6]) == 12 and len(current[7]) == 4

    # A different expected body must still be flagged, never silently accepted.
    tampered = CANDIDATE.read_text().replace(NEW_SHA, "0" * 64)
    assert tampered != CANDIDATE.read_text()
    rejected = inspect(world["boot"], tampered)
    assert [(r[0], r[3]) for r in rejected[5] if r[3] is False] == [
        ("ingestion_register_bolton_exception", False)
    ]
