"""CI/CD Phase 1 pre-merge amendment - schema-change detection.

Uses a REAL, throwaway git repository per test (not a mocked subprocess) -
"genuine evidence, not a mock" is this repo's own established precedent
for behaviour that depends on an external tool's actual semantics (see
tests/test_salford_child_process_memory_diagnosis.py's own real-Chromium
reproduction). git diff's exact handling of merge commits is precisely
the kind of thing worth proving for real rather than assuming.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.deployment.schema_release_detection import (
    SCHEMA_DEFINING_FILES,
    changed_files_between,
    detect_schema_change,
    schema_change_required,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _write(repo: Path, relative_path: str, content: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    _write(tmp_path, "app/db/models.py", "# baseline models\n")
    _write(tmp_path, "app/reporting/scheme_summary.py", "# baseline reporting\n")
    _write(tmp_path, "app/db/session.py", "# baseline session\n")
    _write(tmp_path, "scripts/migrate_schema.py", "# baseline migrate\n")
    _write(tmp_path, "scripts/verify_schema.py", "# baseline verify\n")
    _commit(tmp_path, "baseline")
    return tmp_path


# --- Part 15, item 1: known schema-changing model diff -----------------------


def test_models_py_change_is_detected_as_schema_change(repo: Path):
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, "app/db/models.py", "# baseline models\nnew_column = 1\n")
    head = _commit(repo, "add column")

    migration_required, matched = detect_schema_change(base, head, cwd=repo)

    assert migration_required is True
    assert matched == {"app/db/models.py"}


# --- Part 15, item 2: ordinary non-schema code change -------------------------


def test_ordinary_reporting_change_is_not_a_schema_change(repo: Path):
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, "app/reporting/scheme_summary.py", "# baseline reporting\nprint('tweak')\n")
    head = _commit(repo, "tweak reporting")

    migration_required, matched = detect_schema_change(base, head, cwd=repo)

    assert migration_required is False
    assert matched == set()


# --- Part 15, item 3: migration helper change is conservatively flagged ------


@pytest.mark.parametrize("schema_file", sorted(SCHEMA_DEFINING_FILES))
def test_each_schema_defining_file_change_is_individually_detected(repo: Path, schema_file: str):
    """Part 15, item 5: the detector cannot silently ignore any approved
    schema-defining file - proven individually for all four, not just
    models.py."""
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, schema_file, f"# baseline\n# changed {schema_file}\n")
    head = _commit(repo, f"change {schema_file}")

    migration_required, matched = detect_schema_change(base, head, cwd=repo)

    assert migration_required is True
    assert schema_file in matched


def test_schema_defining_file_set_has_exactly_the_expected_four_entries():
    """Content-pinned so any future addition/removal is a deliberate,
    reviewed diff to this test, not a silent scope change."""
    assert SCHEMA_DEFINING_FILES == {
        "app/db/models.py", "app/db/session.py",
        "scripts/migrate_schema.py", "scripts/verify_schema.py",
    }


# --- Part 15, item 4: merge commit diff semantics -----------------------------


def test_no_ff_merge_commit_correctly_surfaces_a_schema_change_brought_in_by_the_branch(repo: Path):
    """A --no-ff merge commit's diff against the true starting point must
    still surface a schema change introduced on the merged-in branch, even
    when unrelated commits also landed on master in the meantime - proving
    the two-dot `base..head` comparison this module uses does not depend
    on merge-commit parent ordering the way a naive `HEAD^` diff would."""
    base = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-b", "feature")
    _write(repo, "app/db/models.py", "# baseline models\nnew_column = 1\n")
    _commit(repo, "feature: add column")
    _git(repo, "checkout", "master")

    _write(repo, "app/reporting/scheme_summary.py", "# baseline reporting\n# unrelated master work\n")
    _commit(repo, "master: unrelated work")

    _git(repo, "merge", "--no-ff", "feature", "-m", "merge feature")
    merge_commit = _git(repo, "rev-parse", "HEAD")

    migration_required, matched = detect_schema_change(base, merge_commit, cwd=repo)

    assert migration_required is True
    assert "app/db/models.py" in matched


def test_no_ff_merge_with_no_schema_change_on_either_side_is_not_flagged(repo: Path):
    base = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-b", "feature")
    _write(repo, "app/reporting/scheme_summary.py", "# baseline reporting\n# feature work\n")
    _commit(repo, "feature: reporting only")
    _git(repo, "checkout", "master")
    _git(repo, "merge", "--no-ff", "feature", "-m", "merge feature")
    merge_commit = _git(repo, "rev-parse", "HEAD")

    migration_required, matched = detect_schema_change(base, merge_commit, cwd=repo)

    assert migration_required is False
    assert matched == set()


def test_undeployed_schema_change_still_flagged_across_a_later_non_schema_commit(repo: Path):
    """Part 8's own core scenario: commit B (schema change) has not yet
    been deployed; commit C (no further schema change) arrives afterwards.
    Comparing C against the TRUE last-deployed base (still A, the
    fixture's baseline) must still report migration_required=True -
    proving the detector is correctly base-agnostic rather than silently
    only comparing against the immediately preceding commit."""
    last_deployed = _git(repo, "rev-parse", "HEAD")  # commit A

    _write(repo, "app/db/models.py", "# baseline models\nnew_column = 1\n")
    _commit(repo, "B: schema change, not yet deployed")

    _write(repo, "app/reporting/scheme_summary.py", "# baseline reporting\n# C: unrelated fix\n")
    commit_c = _commit(repo, "C: unrelated fix, no further schema change")

    migration_required, matched = detect_schema_change(last_deployed, commit_c, cwd=repo)

    assert migration_required is True
    assert "app/db/models.py" in matched


# --- schema_change_required / changed_files_between as pure units ------------


def test_schema_change_required_is_a_pure_predicate():
    assert schema_change_required({"app/db/models.py"}) is True
    assert schema_change_required({"app/reporting/scheme_summary.py"}) is False
    assert schema_change_required(set()) is False


def test_changed_files_between_returns_repo_relative_paths(repo: Path):
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, "app/db/models.py", "# baseline models\nnew_column = 1\n")
    head = _commit(repo, "add column")

    changed = changed_files_between(base, head, cwd=repo)

    assert changed == {"app/db/models.py"}
