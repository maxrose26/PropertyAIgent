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


# Coarse process classes (Render Daily Discovery Salford child-process
# memory diagnosis, Part 3): "children RSS" as measured above sums EVERY
# descendant indiscriminately - Playwright's own Node driver process, the
# entire Chromium multi-process tree (browser main + any renderer/utility/
# GPU/zygote/crashpad-handler processes it spawns), AND any
# multiprocessing-spawned PDF/DOCX extraction worker - so a rising
# "children" figure alone cannot say WHICH of those is actually growing.
# Classified by process name + full command line (more reliable than name
# alone - Chromium's own sub-process ROLE is only visible via its
# --type=... command-line flag, and a plain "chrome"/"headless_shell" name
# match doesn't distinguish the browser-main process from a renderer).
_CHROME_NAME_HINTS = ("chrome", "chromium", "headless_shell")


def _classify_descendant(proc: "psutil.Process") -> str:  # noqa: F821 - psutil only imported if available
    """Returns one of: chromium-browser-main, chromium-renderer,
    chromium-gpu, chromium-utility, chromium-zygote, chromium-crashpad,
    chromium-other, playwright-node, python-extraction-worker, other.
    Never raises - a descendant that exits or becomes inaccessible mid-
    classification (permission, already gone) is classified as "other"
    rather than blowing up the whole checkpoint."""
    try:
        name = (proc.name() or "").lower()
    except Exception:  # noqa: BLE001 - psutil.NoSuchProcess/AccessDenied/ZombieProcess, or platform quirks
        return "other"
    try:
        cmdline = " ".join(proc.cmdline()).lower()
    except Exception:  # noqa: BLE001
        cmdline = ""

    if any(hint in name for hint in _CHROME_NAME_HINTS) or any(hint in cmdline for hint in _CHROME_NAME_HINTS):
        if "--type=renderer" in cmdline:
            return "chromium-renderer"
        if "--type=gpu-process" in cmdline:
            return "chromium-gpu"
        if "--type=utility" in cmdline:
            return "chromium-utility"
        if "--type=zygote" in cmdline:
            return "chromium-zygote"
        if "--type=crashpad-handler" in cmdline:
            return "chromium-crashpad"
        if "--type=" in cmdline:
            return "chromium-other"
        return "chromium-browser-main"  # the one Chromium process with no --type= flag

    if "node" in name and ("playwright" in cmdline or "driver" in cmdline):
        return "playwright-node"

    # Our own multiprocessing.get_context("spawn") extraction workers
    # (app.extraction.pdf_text) re-exec the SAME Python interpreter with a
    # multiprocessing bootstrap command line - distinguishable from an
    # unrelated Python process by that bootstrap marker, not just "is
    # python.exe running".
    if "python" in name and "multiprocessing.spawn" in cmdline:
        return "python-extraction-worker"

    return "other"


# The 4 buckets always reported in a breakdown line (Part 3's own example
# format), aggregating the finer chromium-* sub-classes above into one
# "chromium" figure for a glanceable line while _classify_descendant's own
# finer distinction remains available to anything calling it directly
# (e.g. tests, or a future deeper dive).
_CHROMIUM_CLASSES = (
    "chromium-browser-main", "chromium-renderer", "chromium-gpu",
    "chromium-utility", "chromium-zygote", "chromium-crashpad", "chromium-other",
)


def process_tree_breakdown(pid: int | None = None) -> tuple[float, dict[str, float], dict[str, int]]:
    """Returns (self_rss_mib, {class: rss_mib}, {class: count}) - the same
    descendant enumeration as process_tree_rss_mib, but bucketed by
    _classify_descendant instead of summed into one "children" figure.
    Returns (0.0, {}, {}) - never raises - under the same conditions
    process_tree_rss_mib does."""
    if not _PSUTIL_AVAILABLE:
        return 0.0, {}, {}
    try:
        root = psutil.Process(pid) if pid is not None else psutil.Process()
        self_rss = root.memory_info().rss
    except psutil.NoSuchProcess:
        return 0.0, {}, {}

    mib_by_class: dict[str, float] = {}
    count_by_class: dict[str, int] = {}
    try:
        children = root.children(recursive=True)
    except psutil.NoSuchProcess:
        children = []
    for child in children:
        try:
            rss = child.memory_info().rss
        except Exception:  # noqa: BLE001 - exited/inaccessible between listing and measuring
            continue
        cls = _classify_descendant(child)
        mib_by_class[cls] = mib_by_class.get(cls, 0.0) + rss / MiB
        count_by_class[cls] = count_by_class.get(cls, 0) + 1

    return self_rss / MiB, mib_by_class, count_by_class


# Any single identifier value longer than this is truncated (Render Daily
# Discovery Salford document-stage memory diagnosis, Part 3: "keep
# identifiers concise" / "do not print full document content") - a
# document/application title is a public planning-portal listing value, not
# a secret, but a [mem] line must stay a one-line, glanceable diagnostic,
# not a dumping ground for arbitrary portal-supplied text.
_EXTRA_VALUE_MAX_CHARS = 80


def log_memory(
    stage: str,
    *,
    council: str | None = None,
    pid: int | None = None,
    extra: dict[str, object] | None = None,
    breakdown: bool = False,
    warn_threshold_mib: float = DEFAULT_WARNING_THRESHOLD_MIB,
) -> None:
    """Prints one concise structured [mem] line for the given stage/
    checkpoint, plus a [mem-warning] line if the process-tree total crosses
    warn_threshold_mib. Never raises - any failure to measure is silently
    swallowed rather than breaking the actual scraping pipeline this is
    observing (diagnostics must never become a new source of production
    failures). Contains no secrets - only a stage label, an optional
    council code, optional short identifying context (e.g. an application
    reference or document name/size - see `extra`), and memory figures.

    `extra` (Render Daily Discovery Salford document-stage memory
    diagnosis, Part 3): optional short key=value identifiers appended to
    the line, for finer-grained checkpoints than a whole pipeline stage -
    e.g. log_memory("documents.download.after", council="salford",
    extra={"application": "PA/2026/0642", "document": "Plan.pdf", "size_kib": 340}).
    Each value is stringified and truncated to _EXTRA_VALUE_MAX_CHARS -
    never the full extracted text or any document content, just enough to
    identify WHICH item was being processed. Reuses the exact same [mem]/
    [mem-warning] prefix as every other call, so the existing orchestrator-
    side persisted-checkpoint logic (scripts.run_daily_councils, matching on
    that prefix) picks these up automatically - no separate persistence
    path was needed.

    `breakdown` (Render Daily Discovery Salford CHILD-PROCESS memory
    diagnosis): when True, replaces the single "children=NMiB" figure with
    process_tree_breakdown's per-class figures (playwright/chromium/
    extraction/other, each with a process count) plus total descendant/
    Chromium/extraction-worker counts - answering "which class of
    descendant is actually growing", not just "children grew". Off by
    default (extra cmdline() calls per descendant have a real, if small,
    cost) - only worth paying at the per-document checkpoints where the
    question actually matters, not at every coarse pipeline-stage boundary."""
    try:
        council_part = f"council={council} " if council else ""
        extra_part = ""
        if extra:
            pairs = []
            for key, value in extra.items():
                text = str(value).replace("\n", " ").replace("\r", " ")
                if len(text) > _EXTRA_VALUE_MAX_CHARS:
                    text = text[:_EXTRA_VALUE_MAX_CHARS] + "..."
                pairs.append(f"{key}={text}")
            extra_part = " ".join(pairs) + " "

        if breakdown:
            self_mib, mib_by_class, count_by_class = process_tree_breakdown(pid)
            playwright_mib = mib_by_class.get("playwright-node", 0.0)
            chromium_mib = sum(mib_by_class.get(c, 0.0) for c in _CHROMIUM_CLASSES)
            extraction_mib = mib_by_class.get("python-extraction-worker", 0.0)
            other_mib = mib_by_class.get("other", 0.0)
            total_mib = self_mib + playwright_mib + chromium_mib + extraction_mib + other_mib
            chromium_count = sum(count_by_class.get(c, 0) for c in _CHROMIUM_CLASSES)
            extraction_count = count_by_class.get("python-extraction-worker", 0)
            descendant_count = sum(count_by_class.values())
            body = (
                f"self={self_mib:.0f}MiB playwright={playwright_mib:.0f}MiB "
                f"chromium={chromium_mib:.0f}MiB extraction={extraction_mib:.0f}MiB "
                f"other={other_mib:.0f}MiB total={total_mib:.0f}MiB "
                f"descendants={descendant_count} chromium_count={chromium_count} "
                f"extraction_count={extraction_count}"
            )
        else:
            self_mib, children_mib = process_tree_rss_mib(pid)
            total_mib = self_mib + children_mib
            body = f"self={self_mib:.0f}MiB children={children_mib:.0f}MiB total={total_mib:.0f}MiB"

        # flush=True (Render Daily Discovery missing-runtime-logs diagnosis,
        # "Do not rely on only one fragile buffering assumption"): this is
        # called from BOTH the orchestrator and each run_weekly.py council
        # subprocess. The orchestrator's own launch command and
        # PYTHONUNBUFFERED already fix the buffering issue at the process
        # level, but a diagnostic print that survives a hard OOM SIGKILL
        # should not also depend on that external configuration staying
        # correct forever - flush explicitly here too, redundantly but
        # cheaply (one syscall per checkpoint, not per line of a busy loop).
        print(f"[mem] {council_part}stage={stage} {extra_part}{body}", flush=True)
        if total_mib > warn_threshold_mib:
            print(
                f"[mem-warning] {council_part}stage={stage} {extra_part}total={total_mib:.0f}MiB "
                f"exceeds {warn_threshold_mib:.0f}MiB warning threshold",
                flush=True,
            )
    except Exception:  # noqa: BLE001 - a diagnostic must never take the real pipeline down with it
        pass
