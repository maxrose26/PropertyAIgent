"""GitHub Actions CI deployment-safety invariant.

Not a general YAML-diffing test suite (deliberately no assertions on step
order, exact command text, or formatting - see this repo's own precedent
in tests/test_pr2_premerge_ai_cost_and_migration_safety.py for why brittle
text-comparison tests are avoided). The one invariant worth protecting
automatically: this workflow must never come to require a production
secret (DATABASE_URL, OPENAI_API_KEY, or any Render/Supabase credential),
since the whole point of running CI without them is that a leaked/misused
GitHub Actions secret can reach production credentials no other way if
none are ever configured here in the first place.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

_PRODUCTION_SECRET_NAMES = (
    "DATABASE_URL", "OPENAI_API_KEY", "RENDER_API_KEY", "RENDER_DEPLOY_HOOK",
    "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_ROLE_KEY",
)


def test_ci_workflow_file_exists():
    assert WORKFLOW_PATH.exists()


def test_ci_workflow_is_valid_yaml():
    config = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    assert "jobs" in config


def test_ci_workflow_triggers_on_master_push_and_pull_request():
    config = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = config.get("on") or config.get(True)  # PyYAML parses bare `on:` as boolean True
    assert "master" in triggers["push"]["branches"]
    assert "master" in triggers["pull_request"]["branches"]


def test_ci_workflow_runs_pytest():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "pytest" in text


def test_ci_workflow_never_references_a_production_secret():
    """The deployment-safety invariant this file exists to protect (Part 6
    of the CI task: "CI must NOT require production DATABASE_URL/
    OPENAI_API_KEY/Render/Supabase credentials unless the test suite
    genuinely cannot operate without one" - confirmed it doesn't, by
    inspection, when this workflow was written).

    Checks actual USAGE (a `${{ secrets.NAME }}` interpolation, or an
    `env:`/`with:` key literally named after one of these secrets) - not a
    bare substring match against the whole file text, since this file's
    own explanatory comment legitimately names DATABASE_URL/OPENAI_API_KEY
    in prose to document why they are NOT required (the same "mention in
    prose is fine, only real usage is disallowed" distinction this repo's
    own tests/test_render_cron_playwright_build_hotfix.py already applies
    to scripts/verify_browser_runtime.py)."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    for secret_name in _PRODUCTION_SECRET_NAMES:
        assert f"secrets.{secret_name}" not in text, f"secrets.{secret_name} must not be interpolated in the CI workflow"

    config = yaml.safe_load(text)
    for job in config["jobs"].values():
        env_keys = set(job.get("env", {}).keys())
        for step in job.get("steps", []):
            env_keys |= set(step.get("env", {}).keys())
            env_keys |= set(step.get("with", {}).keys())
        for secret_name in _PRODUCTION_SECRET_NAMES:
            assert secret_name not in env_keys, f"{secret_name} must not be declared as a workflow env/with key"


def test_ci_workflow_does_not_deploy_anything():
    """This workflow's only job runs tests - it must never itself contain a
    deploy step (curl to a deploy hook, render CLI invocation, etc.). Real
    deployment is Render's own responsibility, triggered separately from
    outside this repository."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("render.com", "deploy_hook", "render-deploy", "render_api_key"):
        assert forbidden not in text
