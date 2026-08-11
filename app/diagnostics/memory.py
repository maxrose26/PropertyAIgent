"""Lightweight production memory instrumentation (Render Daily Discovery
memory instrumentation & architecture diagnosis).

Two prior audits (Starter/512Mi, then Standard/2Gi) both ended in an
out-of-memory kill, and a local, blank-page Chromium measurement
(scripts/diagnose_browser_memory.py, ~332 MiB) proved insufficient to
predict the real production failure - a real Daily Discovery run visits
real portal pages, downloads real PDFs, and accumulates ORM state across
potentially hundreds of Applications per council, none of which a blank
page exercises. This module exists to answer, from REAL production
evidence rather than a local approximation, exactly where memory grows.

Deliberately minimal - not a monitoring platform, not a metrics backend,
just structured print() lines Render's own log viewer already captures.
Reads only process/memory metadata via psutil - never touches request
bodies, document content, database rows, or any secret. Every function
here MUST NOT raise: a diagnostic that crashes the pipeline it's meant to
observe would be worse than no diagnostic at all.

    from app.diagnostics.memory import log_memory
    log_memory("stage_documents.before", council="bury")
    ... do the actual work ...
    log_memory("stage_documents.after", council="bury")

Produces lines like:
    [mem] council=bury stage=stage_documents.before self=210MiB children=0MiB total=210MiB
    [mem-warning] council=bury stage=stage_documents.after total=1612MiB exceeds 1536MiB warning threshold
"""
from __future__ import annotations

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:  # pragma: no cover - psutil is in requirements.txt, but diagnostics must degrade, never crash
    _PSUTIL_AVAILABLE = False

MiB = 1024 * 1024

# Above this process-tree total, an extra [mem-warning] line is printed in
# addition to the normal [mem] line - purely informational (Part 16: "Do
# not attempt to self-kill/restart yet... the purpose is diagnosis"). Set
# comfortably below a 2Gi container limit so a warning has a chance to
# reach Render's logs before an OOM kill removes the chance to log anything
# at all.
DEFAULT_WARNING_THRESHOLD_MIB = 1536


def process_tree_rss_mib(pid: int | None = None) -> tuple[float, float]:
    """Returns (self_rss_mib, children_rss_mib) for the given process
    (default: the current process) - self is that one process alone,
    children is the SUM of every live descendant (for run_weekly.py this
    is the Playwright Node driver plus its entire Chromium process tree;
    for the orchestrator inspecting a council subprocess by pid, self is
    that subprocess's own Python interpreter and children is everything
    IT spawned). Returns (0.0, 0.0) - never raises - if the process has
    already exited or psutil isn't available."""
    if not _PSUTIL_AVAILABLE:
        return 0.0, 0.0
    try:
        root = psutil.Process(pid) if pid is not None else psutil.Process()
        self_rss = root.memory_info().rss
    except psutil.NoSuchProcess:
        return 0.0, 0.0

    children_rss = 0
    try:
        for child in root.children(recursive=True):
            try:
                children_rss += child.memory_info().rss
            except psutil.NoSuchProcess:
                continue  # exited between listing and measuring - not consuming memory anymore
    except psutil.NoSuchProcess:
        pass  # root itself exited mid-enumeration

    return self_rss / MiB, children_rss / MiB


def log_memory(
    stage: str,
    *,
    council: str | None = None,
    pid: int | None = None,
    warn_threshold_mib: float = DEFAULT_WARNING_THRESHOLD_MIB,
) -> None:
    """Prints one concise structured [mem] line for the given stage
    boundary, plus a [mem-warning] line if the process-tree total crosses
    warn_threshold_mib. Never raises - any failure to measure is silently
    swallowed rather than breaking the actual scraping pipeline this is
    observing (diagnostics must never become a new source of production
    failures). Contains no secrets - only a stage label, an optional
    council code (already public - a council code, not a credential), and
    memory figures."""
    try:
        self_mib, children_mib = process_tree_rss_mib(pid)
        total_mib = self_mib + children_mib
        council_part = f"council={council} " if council else ""
        # flush=True (Render Daily Discovery missing-runtime-logs diagnosis,
        # "Do not rely on only one fragile buffering assumption"): this is
        # called from BOTH the orchestrator and each run_weekly.py council
        # subprocess. The orchestrator's own launch command and
        # PYTHONUNBUFFERED already fix the buffering issue at the process
        # level, but a diagnostic print that survives a hard OOM SIGKILL
        # should not also depend on that external configuration staying
        # correct forever - flush explicitly here too, redundantly but
        # cheaply (one syscall per stage boundary, not per line of a busy
        # loop).
        print(
            f"[mem] {council_part}stage={stage} self={self_mib:.0f}MiB children={children_mib:.0f}MiB total={total_mib:.0f}MiB",
            flush=True,
        )
        if total_mib > warn_threshold_mib:
            print(
                f"[mem-warning] {council_part}stage={stage} total={total_mib:.0f}MiB "
                f"exceeds {warn_threshold_mib:.0f}MiB warning threshold",
                flush=True,
            )
    except Exception:  # noqa: BLE001 - a diagnostic must never take the real pipeline down with it
        pass
