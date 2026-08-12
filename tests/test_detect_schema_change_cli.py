"""CLI wrapper for app.deployment.schema_release_detection - exit codes and
$GITHUB_OUTPUT integration. Real throwaway git repo, same precedent as
tests/test_schema_release_detection.py.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.detect_schema_change import main


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _write(repo: Path, relative_path: str, content: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    _write(tmp_path, "app/db/models.py", "# baseline models\n")
    _write(tmp_path, "app/reporting/scheme_summary.py", "# baseline reporting\n")
    _commit(tmp_path, "baseline")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_exit_code_1_when_migration_required(repo: Path, capsys):
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, "app/db/models.py", "# baseline models\nnew_column = 1\n")
    head = _commit(repo, "add column")

    exit_code = main(["--base", base, "--head", head])

    assert exit_code == 1
    assert "migration_required=true" in capsys.readouterr().out


def test_exit_code_0_when_no_migration_required(repo: Path, capsys):
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, "app/reporting/scheme_summary.py", "# baseline reporting\n# tweak\n")
    head = _commit(repo, "tweak")

    exit_code = main(["--base", base, "--head", head])

    assert exit_code == 0
    assert "migration_required=false" in capsys.readouterr().out


def test_writes_github_output_when_env_var_set(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output_file = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, "app/db/models.py", "# baseline models\nnew_column = 1\n")
    head = _commit(repo, "add column")

    main(["--base", base, "--head", head])

    assert output_file.read_text(encoding="utf-8") == "migration_required=true\n"


def test_does_not_write_github_output_when_env_var_unset(repo: Path, monkeypatch: pytest.MonkeyPatch):
    """No GITHUB_OUTPUT write attempt (which would raise FileNotFoundError
    against a nonexistent path) when the variable is genuinely absent -
    proves the write is conditional, not assumed."""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    base = _git(repo, "rev-parse", "HEAD")

    exit_code = main(["--base", base, "--head", base])

    assert exit_code == 0
