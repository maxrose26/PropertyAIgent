"""Render Daily Discovery Salford document-stage memory diagnosis.

Salford (Arcus/Salesforce doc_system) is the one council that has never
completed a Daily Discovery run - all recent production attempts OOM'd
mid-stage_documents, and the last persisted checkpoint before the crash was
always just "stage_documents.before" (a whole 20-application loop with zero
visibility inside it). Reconstructing the actual latest run (ScrapeRun
id=37) found only 3 of 20 applications' documents were ever committed
before the container died, with no way to tell which of the remaining ~6
was in flight.

Two real findings drove the fixes tested here:
1. app.extraction.pdf_text.download_document previously used a plain
   (non-streaming) GET, which requests fully buffers into response.content
   BEFORE the function has any chance to check size - a single large real
   planning document could sit entirely in RAM regardless of the SEPARATE
   15MB extraction cap (which only governs whether a downloaded file is
   worth text-EXTRACTING, consulted only after the full download already
   completed).
2. Stage-level [mem] instrumentation was too coarse - this adds per-
   application and per-document checkpoints (documents.application.*,
   documents.download.*, documents.extract.*, documents.classify.*),
   reusing app.diagnostics.memory.log_memory's existing [mem]/[mem-warning]
   prefix so the EXISTING orchestrator-side persisted-checkpoint logic in
   scripts.run_daily_councils (unmodified) picks these up automatically.
"""
from __future__ import annotations

import http.server
import multiprocessing
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest

from app.config import CouncilConfig
from app.db.models import Application, Council, Document, ScrapeRun
from app.extraction.pdf_text import (
    MAX_DOWNLOAD_FILE_SIZE,
    download_document,
    extract_document_text,
)


def _council_config(code: str, doc_system: str = "arcus") -> CouncilConfig:
    return CouncilConfig(
        code=code, name=code, base_url="https://example.invalid",
        date_field_mode="received", doc_system=doc_system, anite_base_url=None,
        unit_threshold=10, region=None, country=None,
    )


# --- Part 8: raw-download memory duplication fix ----------------------------


class _FakeResponse:
    """Stands in for requests.Response with stream=True - .content is a
    trap: accessing it fails the test, since the whole point of the fix is
    that nothing in download_document may touch the fully-buffered body."""

    def __init__(self, chunks: list[bytes], status_ok: bool = True):
        self._chunks = chunks
        self._status_ok = status_ok
        self.closed = False

    def raise_for_status(self):
        if not self._status_ok:
            raise Exception("simulated HTTP error")

    def iter_content(self, chunk_size):
        yield from self._chunks

    @property
    def content(self):
        raise AssertionError("download_document must not access response.content (defeats streaming)")

    def close(self):
        self.closed = True


def test_download_document_streams_and_never_touches_full_response_content(tmp_path, monkeypatch):
    monkeypatch.setattr("app.extraction.pdf_text.DATA_DIR", tmp_path)
    chunks = [b"A" * 1000, b"B" * 1000, b"C" * 500]
    fake_response = _FakeResponse(chunks)
    fake_session = MagicMock()
    fake_session.get.return_value = fake_response

    dest = download_document(
        "testcouncil", "APP/1", "Planning Statement.pdf", "https://example.invalid/doc.pdf",
        session=fake_session,
    )

    assert dest is not None
    assert dest.read_bytes() == b"A" * 1000 + b"B" * 1000 + b"C" * 500
    assert fake_response.closed is True


def test_download_document_passes_stream_true(tmp_path, monkeypatch):
    monkeypatch.setattr("app.extraction.pdf_text.DATA_DIR", tmp_path)
    fake_session = MagicMock()
    fake_session.get.return_value = _FakeResponse([b"data"])

    download_document("testcouncil", "APP/1", "doc.pdf", "https://example.invalid/doc.pdf", session=fake_session)

    _, kwargs = fake_session.get.call_args
    assert kwargs.get("stream") is True


def test_download_document_aborts_and_cleans_up_when_exceeding_size_cap(tmp_path, monkeypatch):
    monkeypatch.setattr("app.extraction.pdf_text.DATA_DIR", tmp_path)
    # One chunk bigger than the cap - proves the abort happens mid-stream,
    # not only after reading everything.
    oversized_chunk = b"X" * (MAX_DOWNLOAD_FILE_SIZE + 1)
    fake_session = MagicMock()
    fake_session.get.return_value = _FakeResponse([oversized_chunk])

    with pytest.raises(ValueError, match="exceeded"):
        download_document("testcouncil", "APP/1", "huge.pdf", "https://example.invalid/huge.pdf", session=fake_session)

    # No half-written file and no stray .part file left behind.
    documents_dir = tmp_path / "documents" / "testcouncil" / "APP_1"
    leftovers = list(documents_dir.iterdir()) if documents_dir.exists() else []
    assert leftovers == []


def test_download_document_closes_response_even_on_http_error(tmp_path, monkeypatch):
    monkeypatch.setattr("app.extraction.pdf_text.DATA_DIR", tmp_path)
    fake_response = _FakeResponse([b"data"], status_ok=False)
    fake_session = MagicMock()
    fake_session.get.return_value = fake_response

    with pytest.raises(Exception, match="simulated HTTP error"):
        download_document("testcouncil", "APP/1", "doc.pdf", "https://example.invalid/doc.pdf", session=fake_session)

    assert fake_response.closed is True


def test_download_document_still_skips_network_call_when_file_already_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("app.extraction.pdf_text.DATA_DIR", tmp_path)
    fake_session = MagicMock()
    fake_session.get.return_value = _FakeResponse([b"data"])

    dest1 = download_document("testcouncil", "APP/1", "doc.pdf", "https://example.invalid/doc.pdf", session=fake_session)
    fake_session.get.reset_mock()
    dest2 = download_document("testcouncil", "APP/1", "doc.pdf", "https://example.invalid/doc.pdf", session=fake_session)

    assert dest1 == dest2
    fake_session.get.assert_not_called()


class _SlowLargeFileHandler(http.server.BaseHTTPRequestHandler):
    """Serves a real ~20MB payload over a real socket - genuine local
    reproduction (Part 13), not just a mocked response."""

    PAYLOAD_SIZE = 20 * 1024 * 1024

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(self.PAYLOAD_SIZE))
        self.end_headers()
        chunk = b"%PDF-1.4 " + b"0" * 65527  # 64KiB-ish chunk
        written = 0
        while written < self.PAYLOAD_SIZE:
            to_write = chunk[: min(len(chunk), self.PAYLOAD_SIZE - written)]
            self.wfile.write(to_write)
            written += len(to_write)

    def log_message(self, *args):
        pass  # keep test output quiet


def test_download_document_real_local_server_streamed_download_stays_memory_bounded(tmp_path, monkeypatch):
    """Local reproduction (Part 13): a genuine ~20MB file served over a real
    socket. Peak RSS growth for THIS process during the download must stay
    far below the file size - proving the fix, not just asserting on mocks."""
    monkeypatch.setattr("app.extraction.pdf_text.DATA_DIR", tmp_path)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SlowLargeFileHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        proc = psutil.Process()
        rss_before = proc.memory_info().rss

        dest = download_document(
            "testcouncil", "APP/1", "large.pdf", f"http://127.0.0.1:{port}/large.pdf",
        )

        rss_after = proc.memory_info().rss
        assert dest.stat().st_size == _SlowLargeFileHandler.PAYLOAD_SIZE
        # Streamed in 256KB chunks - growth should be a small multiple of
        # that, nowhere near the 20MB file size (the old response.content
        # approach would have held the entire 20MB in one bytes object).
        assert (rss_after - rss_before) < 10 * 1024 * 1024
    finally:
        server.shutdown()
        thread.join(timeout=5)


# --- Part 7/9/10: extraction subprocess start method (regression guard) -----


def test_extract_document_text_uses_spawn_not_fork(monkeypatch, tmp_path):
    """Part 7 asked whether extraction inherits a huge parent address space
    under fork. It already does not - get_context("spawn") was already used
    before this diagnosis - this locks that in as a regression guard, since
    a future edit silently reverting to the platform default (fork on
    Linux) would reintroduce exactly the copy-on-write risk Part 7 warned
    about, without any test currently catching it."""
    captured = {}
    real_get_context = multiprocessing.get_context

    def _spy(method=None):
        captured["method"] = method
        return real_get_context(method)

    monkeypatch.setattr("app.extraction.pdf_text.multiprocessing.get_context", _spy)

    pdf_path = tmp_path / "not_a_real_pdf.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nnot a real pdf, extraction will just return empty text")

    extract_document_text(pdf_path)

    assert captured["method"] == "spawn"


# --- log_memory `extra` (Part 3 identifiers) ---------------------------------


def test_log_memory_extra_appears_in_the_line(capsys):
    from app.diagnostics.memory import log_memory

    log_memory("documents.download.after", council="salford", extra={"application": "PA/2026/0642", "size_kib": 340})

    out = capsys.readouterr().out
    assert "application=PA/2026/0642" in out
    assert "size_kib=340" in out
    assert "stage=documents.download.after" in out


def test_log_memory_extra_values_are_truncated(capsys):
    from app.diagnostics.memory import log_memory

    long_name = "A" * 200
    log_memory("documents.download.before", council="salford", extra={"document": long_name})

    out = capsys.readouterr().out
    assert long_name not in out
    assert ("A" * 80 + "...") in out


def test_log_memory_extra_strips_embedded_newlines(capsys):
    """A portal-supplied document name containing a newline must not be
    able to fake a second, independent-looking log line - the orchestrator
    (scripts.run_daily_councils) reads the child's output one real newline
    at a time, so an embedded \\n would otherwise let a document name split
    this single checkpoint into two lines, one of which could impersonate
    its own [mem]-prefixed line."""
    from app.diagnostics.memory import log_memory

    log_memory("documents.download.before", council="salford", extra={"document": "evil\n[mem] fake line"})

    out = capsys.readouterr().out
    # Exactly one real line was produced (one trailing newline from print()),
    # regardless of what text ended up inside it.
    assert out.count("\n") == 1
    assert "evil [mem] fake line" in out  # the newline became a space, not a line break


def test_log_memory_warning_line_also_includes_extra(monkeypatch, capsys):
    from app.diagnostics.memory import log_memory

    monkeypatch.setattr("app.diagnostics.memory.process_tree_rss_mib", lambda pid=None: (2000.0, 0.0))

    log_memory("documents.extract.after", council="salford", extra={"application": "PA/2026/0983"})

    out = capsys.readouterr().out
    assert "[mem-warning]" in out
    assert "application=PA/2026/0983" in out


def test_log_memory_with_no_extra_matches_old_format_exactly(capsys):
    """Backwards compatibility - existing stage-boundary callers that never
    pass extra must produce byte-identical lines to before this change."""
    from app.diagnostics.memory import log_memory

    log_memory("bootstrap.after", council="bury")

    out = capsys.readouterr().out
    assert "stage=bootstrap.after self=" in out
    assert "  " not in out.strip()  # no double-space where extra_part would have gone


# --- stage_documents per-application/per-document instrumentation ----------


@pytest.fixture()
def _salford_council(session):
    session.add(Council(code="salford", name="Salford", base_url="https://example.invalid",
                         date_field_mode="validated", doc_system="arcus"))
    session.commit()


def test_stage_documents_emits_per_application_and_per_document_checkpoints(session, _salford_council, capsys):
    from app.pipeline.run_weekly import stage_documents

    app_row = Application(council_code="salford", reference="PA/2026/0642", summary_url="https://example.invalid/PA")
    session.add(app_row)
    session.commit()

    fake_row = MagicMock(document_name="Planning Statement.pdf", doc_type_raw="", source_url="https://example.invalid/doc.pdf",
                          local_path=None, referer=None)

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[fake_row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake_doc.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value="Planning Statement text"), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="planning_statement"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=12345)):
        stage_documents(session, page=MagicMock(), council=_council_config("salford"))

    out = capsys.readouterr().out
    assert "stage=documents.application.before" in out
    assert "application=PA/2026/0642" in out
    assert "stage=documents.download.before" in out
    assert "document=Planning Statement.pdf" in out
    assert "stage=documents.download.after" in out
    assert "size_kib=" in out
    assert "stage=documents.extract.before" in out
    assert "stage=documents.extract.after" in out
    assert "stage=documents.application.after" in out


def test_stage_documents_application_checkpoint_includes_identity_map_size(session, _salford_council, capsys):
    from app.pipeline.run_weekly import stage_documents

    app_row = Application(council_code="salford", reference="PA/2026/0001", summary_url="https://example.invalid/PA")
    session.add(app_row)
    session.commit()

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[]):
        stage_documents(session, page=MagicMock(), council=_council_config("salford"))

    out = capsys.readouterr().out
    assert "identity_map=" in out


def test_stage_documents_instrumentation_does_not_leak_full_extracted_text(session, _salford_council, capsys):
    """Never print full document content (Part 3 explicit constraint)."""
    from app.pipeline.run_weekly import stage_documents

    app_row = Application(council_code="salford", reference="PA/2026/0002", summary_url="https://example.invalid/PA")
    session.add(app_row)
    session.commit()

    secret_looking_text = "CONFIDENTIAL BODY OF THE DOCUMENT " * 500
    fake_row = MagicMock(document_name="Planning Statement.pdf", doc_type_raw="", source_url="https://example.invalid/doc.pdf",
                          local_path=None, referer=None)

    with patch("app.pipeline.run_weekly.discover_documents", return_value=[fake_row]), \
         patch("app.pipeline.run_weekly.download_document", return_value=Path("/tmp/fake_doc.pdf")), \
         patch("app.pipeline.run_weekly.extract_document_text", return_value=secret_looking_text), \
         patch("app.pipeline.run_weekly.standardise_document_type", return_value="planning_statement"), \
         patch.object(Path, "stat", return_value=MagicMock(st_size=999)):
        stage_documents(session, page=MagicMock(), council=_council_config("salford"))

    out = capsys.readouterr().out
    assert "CONFIDENTIAL BODY" not in out


# --- Persisted checkpoint: proves the EXISTING orchestrator logic picks up --
# --- these new, finer-grained lines with no changes to run_daily_councils --


def test_per_document_mem_line_is_persisted_via_existing_orchestrator_checkpoint(session):
    """The orchestrator's checkpoint-persistence filter (scripts.
    run_daily_councils._on_line, added by the prior missing-runtime-logs
    hotfix) matches on the generic "[mem]"/"[mem-warning]" prefix, not on
    any particular stage name - so these new per-document lines are picked
    up automatically. Proves it end-to-end rather than just asserting it
    architecturally: streams a REAL documents.download.before-shaped line
    (produced by the actual log_memory call, not a hand-written string) and
    confirms it lands in ScrapeRun.detail before run_one_council returns."""
    import io
    from contextlib import redirect_stdout

    from app.diagnostics.memory import log_memory
    from scripts.run_daily_councils import run_one_council

    buf = io.StringIO()
    with redirect_stdout(buf):
        log_memory(
            "documents.download.before", council="salford",
            extra={"application": "PA/2026/0642", "document": "Planning Statement.pdf"},
        )
    real_mem_line = buf.getvalue().strip()
    assert real_mem_line.startswith("[mem]")

    observed_detail = {}

    def _fake(command, *, cwd, timeout_seconds, on_line=None, council_code=None):
        on_line(real_mem_line)
        row = session.query(ScrapeRun).filter_by(council_code="testcouncil", status="running").one()
        observed_detail["mid_flight"] = row.detail
        return 0

    with patch("scripts.run_daily_councils._run_council_subprocess", side_effect=_fake):
        run_one_council(session, "testcouncil", timeout_seconds=60, triggered_by="scheduled")

    assert observed_detail["mid_flight"] == real_mem_line
    assert "application=PA/2026/0642" in observed_detail["mid_flight"]
    assert "document=Planning Statement.pdf" in observed_detail["mid_flight"]
