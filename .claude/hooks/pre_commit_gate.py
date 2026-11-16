"""PreToolUse hook: block `git commit` while lint or unit tests fail.

Runs ruff, pyright and the unit tests (no Postgres, no real LLM; the web checks are left
to `make check`). Exits 2 with the failure on
stderr, which blocks the commit and tells Claude Code what to fix. Does nothing until
the project has a pyproject.toml with ruff installed.

The owner can bypass it for one session by starting Claude Code with ATS_SKIP_GATE=1.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

UNIT_TESTS = "not integration and not llm"
NO_TESTS_COLLECTED = 5


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def run(root: Path, *args: str, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--quiet", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def main() -> int:
    if os.environ.get("ATS_SKIP_GATE") == "1":
        return 0
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = (event.get("tool_input") or {}).get("command") or ""
    if "git commit" not in command:
        return 0

    root = project_root().resolve()
    if not (root / "pyproject.toml").is_file() or shutil.which("uv") is None:
        return 0

    try:
        if run(root, "ruff", "--version", timeout=30).returncode != 0:
            return 0
        steps: list[tuple[str, tuple[str, ...]]] = [
            ("ruff check", ("ruff", "check", "--output-format", "concise", ".")),
            ("ruff format --check", ("ruff", "format", "--check", ".")),
        ]
        if run(root, "pyright", "--version", timeout=60).returncode == 0:
            steps.append(("pyright", ("pyright",)))
        if run(root, "pytest", "--version", timeout=30).returncode == 0:
            steps.append(("pytest (unit)", ("pytest", "-q", "-x", "-m", UNIT_TESTS)))

        for name, args in steps:
            result = run(root, *args)
            ok = result.returncode == 0 or (
                args[0] == "pytest" and result.returncode == NO_TESTS_COLLECTED
            )
            if not ok:
                output = (result.stdout + "\n" + result.stderr).strip()
                sys.stderr.write(f"Commit blocked: `{name}` failed. Fix it first.\n")
                sys.stderr.write(output[-4000:] + "\n")
                return 2
    except subprocess.TimeoutExpired:
        sys.stderr.write("Commit blocked: the pre-commit checks timed out.\n")
        return 2
    except OSError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
