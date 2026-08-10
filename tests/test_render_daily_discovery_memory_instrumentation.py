"""Tests for app/diagnostics/memory.py (Render Daily Discovery production
memory instrumentation & architecture diagnosis, Part 17): the memory
sampler must never raise (a diagnostic helper crashing the real pipeline
would be worse than having no diagnostics at all), must handle a missing/
exited process gracefully, must never leak secrets into its log lines, and
must emit a warning line only once memory crosses the threshold."""
from __future__ import annotations

import subprocess
import sys

import psutil
import pytest

from app.diagnostics.memory import DEFAULT_WARNING_THRESHOLD_MIB, log_memory, process_tree_rss_mib


def test_process_tree_rss_mib_reports_positive_values_for_the_current_process():
    self_mib, children_mib = process_tree_rss_mib()
    assert self_mib > 0
    assert children_mib >= 0


def test_process_tree_rss_mib_handles_a_pid_that_no_longer_exists():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    dead_pid = proc.pid

    self_mib, children_mib = process_tree_rss_mib(dead_pid)

    assert self_mib == 0.0
    assert children_mib == 0.0


def test_process_tree_rss_mib_skips_a_child_that_exits_mid_scan(monkeypatch):
    class _VanishingChild:
        def memory_info(self):
            raise psutil.NoSuchProcess(pid=99999)

    class _FakeRoot:
        def memory_info(self):
            class _Info:
                rss = 10 * 1024 * 1024
            return _Info()

        def children(self, recursive=True):
            return [_VanishingChild()]

    monkeypatch.setattr("app.diagnostics.memory.psutil.Process", lambda *a, **k: _FakeRoot())

    self_mib, children_mib = process_tree_rss_mib(1234)

    assert self_mib == 10.0
    assert children_mib == 0.0


def test_log_memory_never_raises_even_if_psutil_blows_up(monkeypatch, capsys):
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated psutil failure")

    monkeypatch.setattr("app.diagnostics.memory.process_tree_rss_mib", _boom)

    log_memory("some.stage", council="bury")  # must not raise

    assert capsys.readouterr().out == ""


def test_log_memory_line_contains_no_secret_looking_content(capsys, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:supersecret@host/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-appear")

    log_memory("stage_documents.before", council="oldham")

    out = capsys.readouterr().out
    assert "supersecret" not in out
    assert "sk-should-never-appear" not in out
    assert "postgres://" not in out
    assert "DATABASE_URL" not in out


def test_log_memory_line_only_contains_operational_metadata(capsys):
    log_memory("bootstrap.after", council="bury")

    out = capsys.readouterr().out
    assert "[mem]" in out
    assert "council=bury" in out
    assert "stage=bootstrap.after" in out
    assert "self=" in out and "children=" in out and "total=" in out


def test_log_memory_omits_council_segment_when_none_given(capsys):
    log_memory("orchestrator.before_council")

    out = capsys.readouterr().out
    assert "council=" not in out
    assert "stage=orchestrator.before_council" in out


@pytest.mark.parametrize("total_mib,should_warn", [(100.0, False), (DEFAULT_WARNING_THRESHOLD_MIB + 1, True)])
def test_log_memory_warns_only_once_threshold_is_crossed(monkeypatch, capsys, total_mib, should_warn):
    monkeypatch.setattr(
        "app.diagnostics.memory.process_tree_rss_mib", lambda pid=None: (total_mib, 0.0)
    )

    log_memory("stage_documents.after", council="rochdale")

    out = capsys.readouterr().out
    assert ("[mem-warning]" in out) == should_warn


def test_log_memory_warning_threshold_is_configurable(capsys, monkeypatch):
    monkeypatch.setattr(
        "app.diagnostics.memory.process_tree_rss_mib", lambda pid=None: (50.0, 0.0)
    )

    log_memory("stage_scrape.after", council="salford", warn_threshold_mib=10.0)

    out = capsys.readouterr().out
    assert "[mem-warning]" in out
