"""Render Cron Job Playwright build hotfix - focused tests.

Root cause: propertyaigent-daily-scrape's Render build was running
`playwright install --with-deps chromium`, whose --with-deps flag tries to
apt-get install Chromium's OS-level shared libraries via a root/sudo/su
escalation Render's native Python build container does not support
interactively - "Switching to root user to install dependencies... su:
Authentication failure". Fix: drop --with-deps (plain `playwright install
chromium` only downloads the binary over HTTP, no root ever invoked),
immediately followed by a build-time canary (scripts.verify_browser_
runtime) that launches and closes headless Chromium, turning any
still-missing shared library into an explicit BUILD failure rather than a
cryptic scrape failure discovered at the next scheduled run.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDER_YAML = REPO_ROOT / "render.yaml"
RENDER_YAML_TEXT = RENDER_YAML.read_text(encoding="utf-8")


def _service(name: str) -> dict:
    config = yaml.safe_load(RENDER_YAML_TEXT)
    return next(s for s in config["services"] if s["name"] == name)


# --- Root-cause elimination --------------------------------------------


def _all_build_and_start_commands() -> list[str]:
    """Only the actual EXECUTABLE strings Render runs - buildCommand/
    startCommand - not this file's own explanatory comments (which
    legitimately name --with-deps/sudo/su/apt-get to document the root
    cause and must not be scrubbed of that explanation)."""
    config = yaml.safe_load(RENDER_YAML_TEXT)
    commands = []
    for service in config["services"]:
        commands.append(service.get("buildCommand", ""))
        commands.append(service.get("startCommand", ""))
    return commands


def test_render_yaml_contains_no_with_deps_flag():
    """The exact offending flag must be gone from every actual command
    Render executes (comments explaining the old, removed command are
    fine and expected - see this file's own header)."""
    for command in _all_build_and_start_commands():
        assert "--with-deps" not in command


def test_render_yaml_contains_no_sudo_su_or_root_password_approach():
    import re

    for command in _all_build_and_start_commands():
        lowered = command.lower()
        assert "sudo" not in lowered
        assert re.search(r"(?<![a-z])su(?![a-z])", lowered) is None
        assert "password" not in lowered
        assert "apt-get" not in lowered
        assert "apt install" not in lowered


def test_render_yaml_still_installs_chromium_binary_for_daily_discovery():
    """Removing --with-deps must not silently remove the browser install
    altogether - the binary download itself is still required and still
    happens, just without the OS-dependency escalation."""
    discovery = _service("propertyaigent-daily-scrape")
    assert "playwright install chromium" in discovery["buildCommand"]


# --- Build-time runtime validation --------------------------------------


def test_render_yaml_daily_discovery_build_includes_browser_runtime_canary():
    discovery = _service("propertyaigent-daily-scrape")
    assert "scripts.verify_browser_runtime" in discovery["buildCommand"]


def test_verify_browser_runtime_script_exists_and_launches_chromium():
    """Real functional proof (on this machine, not Render's Linux
    container - see this repo's own docstring for that limitation) that
    the canary script itself correctly launches and closes headless
    Chromium and reports success."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "scripts.verify_browser_runtime"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout
    assert "launched and closed successfully" in result.stdout


def test_verify_browser_runtime_never_touches_database_or_network_secrets():
    """The canary must not actually USE DATABASE_URL/OPENAI_API_KEY/a
    database session - it is a pure browser-runtime check, safe to run
    before any secret is even configured. (The module's own docstring
    mentions DATABASE_URL in prose, explaining that it is NOT required -
    that mention is expected and fine; only real usage is disallowed.)"""
    source = (REPO_ROOT / "scripts" / "verify_browser_runtime.py").read_text(encoding="utf-8")
    assert "os.getenv" not in source
    assert "os.environ" not in source
    assert "get_session" not in source
    assert "init_db" not in source
    assert "OpenAI(" not in source


def test_verify_browser_runtime_never_scrapes_a_real_council():
    source = (REPO_ROOT / "scripts" / "verify_browser_runtime.py").read_text(encoding="utf-8")
    for council_hint in ("idox_portal", "arcus_portal", "scrape_month", "councils.yaml"):
        assert council_hint not in source


# --- Intelligence Processing must stay Playwright-free -------------------


def test_intelligence_processing_build_has_no_playwright_install_step():
    """Challenge from the hotfix instructions: Intelligence Processing
    never launches a browser (it only calls run_weekly.py's extraction/
    summary stages), so its build must not pay for a browser binary
    download it will never use."""
    intelligence = _service("propertyaigent-intelligence-processing")
    assert "playwright install" not in intelligence["buildCommand"]
    assert "verify_browser_runtime" not in intelligence["buildCommand"]


def test_run_intelligence_processing_module_never_launches_a_browser():
    source = (REPO_ROOT / "scripts" / "run_intelligence_processing.py").read_text(encoding="utf-8")
    assert "playwright" not in source.lower()
    assert "chromium" not in source.lower()
    assert "sync_playwright" not in source


# --- Nothing else about the two cron jobs changed ------------------------


def test_daily_discovery_schedule_and_start_command_unchanged():
    discovery = _service("propertyaigent-daily-scrape")
    assert discovery["schedule"] == "0 5 * * *"
    assert discovery["startCommand"] == "python -m scripts.run_daily_councils"
    env_keys = {e["key"] for e in discovery.get("envVars", [])}
    assert env_keys == {"DATABASE_URL"}


def test_intelligence_processing_schedule_and_start_command_unchanged():
    intelligence = _service("propertyaigent-intelligence-processing")
    assert intelligence["schedule"] == "0 7 * * *"
    assert intelligence["startCommand"] == "python -m scripts.run_intelligence_processing"
    env_keys = {e["key"] for e in intelligence.get("envVars", [])}
    assert env_keys == {"DATABASE_URL", "OPENAI_API_KEY"}


def test_render_yaml_still_declares_exactly_two_cron_jobs_no_web_service():
    config = yaml.safe_load(RENDER_YAML_TEXT)
    services = config["services"]
    assert len(services) == 2
    assert all(s["type"] == "cron" for s in services)
    names = {s["name"] for s in services}
    assert names == {"propertyaigent-daily-scrape", "propertyaigent-intelligence-processing"}


def test_render_yaml_no_service_commits_an_actual_secret_value():
    config = yaml.safe_load(RENDER_YAML_TEXT)
    for service in config["services"]:
        for env_var in service.get("envVars", []):
            assert env_var.get("sync") is False
            assert "value" not in env_var


# --- Every council actually needs Playwright (documents the "why") -------


def test_every_scraper_portal_module_uses_playwright():
    """Confirms the report's own claim: idox_portal.py and arcus_portal.py
    (covering doc_system idox/idox_anite/arcus - every council in config/
    councils.yaml) both take a Playwright Page, so Playwright is required
    unconditionally for Daily Discovery, not just for some councils."""
    for module_name in ("idox_portal", "arcus_portal", "documents"):
        source = (REPO_ROOT / "app" / "scrapers" / f"{module_name}.py").read_text(encoding="utf-8")
        assert "playwright" in source.lower()


def test_run_weekly_opens_one_shared_chromium_session_for_every_council():
    source = (REPO_ROOT / "app" / "pipeline" / "run_weekly.py").read_text(encoding="utf-8")
    assert "sync_playwright()" in source
    assert "p.chromium.launch(" in source
