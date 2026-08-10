"""Lightweight, deterministic browser-runtime validation command (Render
Cron Job Playwright build hotfix). Never scrapes a real council portal -
this only proves the environment CAN run a browser at all.

Root cause this exists for: Daily Discovery's Render Cron Job build was
failing with

    Switching to root user to install dependencies...
    Password: su: Authentication failure
    Failed to install browsers

`playwright install --with-deps <browser>` doesn't just download the
browser binary - it ALSO tries to apt-get install the OS-level shared
libraries Chromium needs, and Playwright's own install-deps step escalates
to root (sudo/su) to do that apt-get install. Render's native Python
runtime build container does not support interactive root authentication,
so that escalation fails outright - not a scraping bug, not a code bug,
purely a build-environment mismatch. The fix (see render.yaml's own
buildCommand) is to drop --with-deps entirely (`playwright install
chromium` only downloads the compiled binary over HTTP, no apt-get, no
root, no su/sudo involved at all) - but that shifts the open question from
"does the build succeed" (now: always) to "does Render's base image
already have the shared libraries Chromium needs to actually LAUNCH" -
something that cannot be verified from a local Windows development
machine, and would otherwise only be discovered days later when the first
05:00 UTC scheduled run fails deep inside a real scrape attempt.

This script closes that gap: run it as an explicit build-time (not
run-time) step, immediately after `playwright install chromium`. If the
OS is missing a required shared library, Chromium fails to even launch,
and THIS script's own exit code turns that into a clear, immediate BUILD
failure with an unambiguous "browser failed to launch: <reason>" message -
not a cryptic scrape failure hours into a real production run.

    python -m scripts.verify_browser_runtime

Does not scrape any council portal, does not touch the database, does not
call OpenAI, does not require DATABASE_URL or any other secret.
"""
from __future__ import annotations

import sys


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(f"[verify-browser-runtime] FAILED - playwright package not importable: {e}")
        return 1

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            version = browser.version
            browser.close()
    except Exception as e:  # noqa: BLE001 - this script's entire job is turning any launch failure into a clear message
        print(f"[verify-browser-runtime] FAILED - chromium could not launch: {e}")
        print(
            "[verify-browser-runtime] This means the build environment is missing a shared "
            "library or the browser binary itself - see this script's own module docstring "
            "for the full diagnosis path, and consider a Docker-based runtime with the "
            "official Playwright base image if this persists."
        )
        return 1

    print(f"[verify-browser-runtime] OK - chromium {version} launched and closed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
