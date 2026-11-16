import subprocess
from pathlib import Path

import pytest

from ats.buildinfo import code_version
from ats.worker.startup import startup_summary


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_the_summary_lists_the_handlers_and_never_the_key() -> None:
    line = startup_summary(
        version="phase/1.2-requirements@abc1234",
        schema_version="0002",
        handlers=["position_setup", "ingest", "noop"],
        llm_model="gemini-3.8-flash",
        llm_rpm=5,
        llm_key_set=True,
    )

    assert line == (
        "worker starting: code=phase/1.2-requirements@abc1234 schema=0002 "
        "handlers=ingest,noop,position_setup llm_model=gemini-3.8-flash llm_rpm=5 llm_key=set"
    )


def test_a_missing_key_is_called_out() -> None:
    line = startup_summary(
        version="x", schema_version="0002", handlers=[], llm_model="m", llm_rpm=5, llm_key_set=False
    )
    assert line.endswith("llm_key=MISSING")


def test_the_code_version_names_branch_commit_and_uncommitted_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    git(tmp_path, "init", "-q", "-b", "work")
    (tmp_path / "a.txt").write_text("one")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-q", "-m", "first")

    clean = code_version(tmp_path)
    (tmp_path / "a.txt").write_text("two")

    assert clean.startswith("work@") and not clean.endswith("-dirty")
    assert code_version(tmp_path) == clean + "-dirty"


def test_without_git_the_version_is_unknown_and_an_override_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    assert code_version(tmp_path) == "unknown"  # not a repository

    monkeypatch.setenv("GIT_COMMIT", "release-7")
    assert code_version(tmp_path) == "release-7"
