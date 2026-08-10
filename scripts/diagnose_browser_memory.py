"""Lightweight local memory diagnostic (Render Daily Discovery memory audit).

Reproduces app.pipeline.run_weekly.main()'s exact Playwright lifecycle
(sync_playwright() -> chromium.launch(headless=True) -> new_context(same
user_agent/viewport) -> new_page() -> ... -> browser.close()) and records
whole-PROCESS-TREE RSS (this process + every descendant - Playwright's own
Node-based driver process, Chromium's browser process, and Chromium's own
internal multi-process tree: GPU/renderer/zygote/utility processes) at each
lifecycle stage, using psutil. This is the number that actually matters for
a container memory ceiling (Render's 512Mi limit is enforced at the cgroup/
container level - the SUM of every process inside it, not any single PID).

Never contacts a real council portal - navigates to about:blank only, so
this measures the FLOOR every single council run pays regardless of
portal-specific content (page weight, document downloads, etc. would only
ever add to this, never subtract from it).

    python -m scripts.diagnose_browser_memory

Requires psutil (dev/diagnostic-only dependency - see requirements.txt).
"""
from __future__ import annotations

import os
import time

import psutil
from playwright.sync_api import sync_playwright

MiB = 1024 * 1024


def _tree_rss_mib() -> float:
    """Sum of RSS across this process and every live descendant - the
    figure a container cgroup memory limit actually enforces, not just
    this one Python interpreter's own footprint."""
    root = psutil.Process(os.getpid())
    total = root.memory_info().rss
    for child in root.children(recursive=True):
        try:
            total += child.memory_info().rss
        except psutil.NoSuchProcess:
            continue  # child exited between listing and measuring - fine, it's not consuming memory anymore
    return total / MiB


def _report(label: str) -> None:
    root = psutil.Process(os.getpid())
    children = root.children(recursive=True)
    print(f"[diagnose-browser-memory] {label}")
    print(f"  process tree RSS: {_tree_rss_mib():.1f} MiB ({len(children)} descendant process(es))")
    for child in children:
        try:
            name = child.name()
            rss = child.memory_info().rss / MiB
            print(f"    - pid={child.pid} {name}: {rss:.1f} MiB")
        except psutil.NoSuchProcess:
            continue


def main() -> None:
    _report("baseline (before sync_playwright())")

    with sync_playwright() as p:
        time.sleep(0.5)  # let the driver process fully start before measuring
        _report("after sync_playwright() driver started")

        browser = p.chromium.launch(headless=True)
        time.sleep(0.5)
        _report("after chromium.launch(headless=True)")

        # Same context config as run_weekly.py's own main() - the desktop
        # UA/viewport themselves have no material memory cost, but this
        # keeps the reproduction faithful.
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        time.sleep(0.5)
        _report("after new_context() + new_page()")

        # about:blank only - never a real council portal. This is the same
        # single page object run_weekly.py reuses across every stage of one
        # council's run, so this is the representative steady-state figure,
        # not a one-off spike.
        page.goto("about:blank")
        time.sleep(0.5)
        _report("after page.goto('about:blank')")

        peak_before_close = _tree_rss_mib()
        browser.close()
        time.sleep(0.5)
        _report("after browser.close() (still inside `with sync_playwright()`)")

    time.sleep(0.5)
    _report("after `with sync_playwright()` block exits")

    print(f"\n[diagnose-browser-memory] Peak process-tree RSS observed: {peak_before_close:.1f} MiB")
    print(
        "[diagnose-browser-memory] This is the FLOOR for one council's Chromium lifecycle on this "
        "machine - real council portals (larger pages, PDF documents, more DOM content) would only "
        "ever add to this, never reduce it. Linux/Render's actual figure may differ from this Windows "
        "measurement - see this audit's final report for that caveat."
    )


if __name__ == "__main__":
    main()
