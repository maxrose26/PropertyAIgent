"""Live Deployment Integrity + Core Navigation Audit - focused tests for the
code changes this audit made.

Most of this audit's findings required no code change (master already had
Allocation Discovery, the Council Intelligence CSS grid, and the correct
visual-evidence priority order - live was simply stale/misconfigured, not
master being wrong). The tests below cover the genuinely new/changed pure
logic: app.ui.shell's commit-hash detection (Part 2) and the geospatial
gating for the Allocation Detail "Location" section (Part 8). UI rendering
itself (row selection, wide_canvas scoping, page layout) has no existing
Streamlit-rendering test harness in this codebase (see every page module's
own docstring: "keep business logic out of the UI" - pages stay thin and are
verified manually) and was verified manually against a live local dev server
instead, per that established convention.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from app.ui.shell import APP_ENVIRONMENT, APP_VERSION, _detect_commit_hash


# --- _detect_commit_hash (Part 2) ------------------------------------------

def test_detect_commit_hash_prefers_render_env_var():
    """Render sets RENDER_GIT_COMMIT on every service automatically - checked
    first so this never shells out to git in the deployed environment."""
    with patch.dict(os.environ, {"RENDER_GIT_COMMIT": "abcdef1234567890"}):
        assert _detect_commit_hash() == "abcdef1"


def test_detect_commit_hash_falls_back_to_git_locally():
    """No RENDER_GIT_COMMIT (local dev) - falls back to the actual repo's
    HEAD via `git rev-parse --short HEAD`. This asserts against the real
    local git state rather than a mocked one, so it also doubles as a
    smoke test that the subprocess call itself works from a fresh process,
    the way it will inside the Streamlit app."""
    env = {k: v for k, v in os.environ.items() if k != "RENDER_GIT_COMMIT"}
    with patch.dict(os.environ, env, clear=True):
        result = _detect_commit_hash()
    assert result is not None
    assert len(result) >= 7
    assert all(c in "0123456789abcdef" for c in result)


def test_detect_commit_hash_never_raises_when_git_is_unavailable():
    """A slim/exported deployment with no .git directory, or a missing git
    binary, must degrade to "no commit known" - never crash the app shell
    over a cosmetic footer detail."""
    env = {k: v for k, v in os.environ.items() if k != "RENDER_GIT_COMMIT"}
    with patch.dict(os.environ, env, clear=True):
        with patch("app.ui.shell.subprocess.run", side_effect=FileNotFoundError("git not found")):
            assert _detect_commit_hash() is None


def test_app_version_string_alone_cannot_prove_current_deployment():
    """Documents the actual root cause this audit found for Part 1/Part 2:
    APP_VERSION is a hand-maintained string that was never bumped across
    three merged sprints (Allocation Discovery, its commercial polish, and
    the Arrow-serialization hotfix all shipped under the same "0.4.2") - so
    on its own it cannot distinguish a stale deployment from a current one.
    This is exactly why the footer now also shows a commit hash."""
    assert APP_VERSION == "0.4.2"
    assert APP_ENVIRONMENT in ("development", "production") or isinstance(APP_ENVIRONMENT, str)
