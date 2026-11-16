"""Which code is running, for the first log line of a process.

A process keeps running the code it started with, so after a branch switch or a pull an old
worker is easy to mistake for a current one. The startup line makes the difference visible.
"""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, timeout=5, check=True
    )
    return result.stdout.strip()


def code_version(repo: Path = REPO_ROOT) -> str:
    """`branch@commit`, with `-dirty` when tracked files have uncommitted changes.

    `GIT_COMMIT` overrides it: a container has no `.git`, so whoever builds the image can pass
    the commit in. Without either, `unknown`.
    """
    override = os.environ.get("GIT_COMMIT")
    if override:
        return override
    try:
        commit = _git(repo, "rev-parse", "--short", "HEAD")
        branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        dirty = _git(repo, "status", "--porcelain", "--untracked-files=no") != ""
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return f"{branch}@{commit}" + ("-dirty" if dirty else "")
