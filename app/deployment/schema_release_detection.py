"""Deployment-safety: which repository files, if changed, mean a release
candidate requires a controlled production schema migration BEFORE it may
be deployed (CI/CD Phase 1 pre-merge amendment, "Schema Change Detection").

Read-only, no network/database access, no Render/OpenAI calls - this
module only ever runs `git diff --name-only` against the local checkout
and compares the result to a fixed, conservative file set.

CONSERVATIVE BY DESIGN (Part 7 of the amendment: "False positive:
acceptable... False negative: unacceptable"): SCHEMA_DEFINING_FILES below
is deliberately not limited to "did app/db/models.py's Column/mapped_column
definitions actually change" (a fragile AST-diff), but simply "did this
whole file change at all". A models.py edit that turns out to be comment-
only still trips the gate - an unnecessary manual migration check is a
minor inconvenience; a missed one is a production incident.

Why exactly these four files (confirmed by a repo-wide audit before this
module was written, not assumed):
  - app/db/models.py is the SOLE place any SQLAlchemy Base-derived model
    declares a mapped_column()/Column() in this entire codebase - grepping
    `mapped_column(` / `Column(` across app/ turns up matches in
    app/ui/common.py, app/ui/pages/0_Explore.py, and
    app/ui/site_profile_view.py too, but every one of those is Streamlit's
    own unrelated st.column_config.Column(...) UI helper, not an ORM
    schema declaration. This means "did models.py change" is already a
    structurally SUFFICIENT signal for "did the declared schema change" in
    this specific codebase today - not merely a convenient guess.
  - app/db/session.py is included even though it declares no columns
    itself, because it is where migrate_schema()/_add_missing_columns()/
    verify_schema() actually live - a change to HOW migration is applied
    (e.g. a future ADD COLUMN gaining a DEFAULT/NOT NULL clause, or a new
    backfill function) is itself migration-safety-relevant even when it
    introduces no new column.
  - scripts/migrate_schema.py and scripts/verify_schema.py are the two
    operator-facing entry points for schema evolution - conservatively
    included so an edit to either always prompts a human to double-check
    before an automatic deploy, cheap insurance with no real downside.

If this codebase ever gains a second file that declares ORM schema (e.g. a
models.py split into multiple modules), THIS SET MUST BE UPDATED - it is
not automatically derived from Base.metadata, by design (deriving it from
metadata would require importing the package at diff time, which is not
meaningfully more correct than this explicit, auditable, version-
controlled list and is considerably more fragile across a wide git diff
range)."""
from __future__ import annotations

import subprocess
from pathlib import Path

SCHEMA_DEFINING_FILES = frozenset({
    "app/db/models.py",
    "app/db/session.py",
    "scripts/migrate_schema.py",
    "scripts/verify_schema.py",
})


def changed_files_between(base_ref: str, head_ref: str, *, cwd: str | Path | None = None) -> set[str]:
    """Every file that differs between base_ref and head_ref, as repo-
    relative POSIX paths (git's own --name-only output). A two-dot
    `base..head` tree comparison - NOT `base...head` (the three-dot
    merge-base form) - so this always reflects the FULL accumulated diff
    between the two exact commits given, including everything a --no-ff
    merge commit brought in, regardless of how many commits or branches
    were involved in producing head_ref. This function is deliberately
    base-agnostic: it does not decide what a correct base_ref IS (see this
    module's own top docstring and scripts/detect_schema_change.py's
    docstring for why the correct base for release-gating purposes is
    "the last commit actually deployed to production", not simply
    HEAD^ or the previous git push - a choice that belongs to the CALLER,
    not this reusable diff primitive)."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}..{head_ref}"],
        cwd=cwd, capture_output=True, text=True, check=True,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def schema_change_required(changed_files: set[str]) -> bool:
    """Pure predicate - True iff ANY changed file is in the conservative
    SCHEMA_DEFINING_FILES set above. Split out from detect_schema_change
    so the decision logic itself is testable without invoking git."""
    return bool(changed_files & SCHEMA_DEFINING_FILES)


def detect_schema_change(base_ref: str, head_ref: str, *, cwd: str | Path | None = None) -> tuple[bool, set[str]]:
    """Convenience wrapper combining the two functions above. Returns
    (migration_required, matching_changed_files) - the second element is
    always a subset of SCHEMA_DEFINING_FILES, never the full changed-file
    set, so a caller printing it gets a short, actionable list."""
    changed = changed_files_between(base_ref, head_ref, cwd=cwd)
    matched = changed & SCHEMA_DEFINING_FILES
    return bool(matched), matched
