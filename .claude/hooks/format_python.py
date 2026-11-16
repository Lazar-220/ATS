"""PostToolUse hook: format and lint the Python file Claude Code just edited.

Reads the hook event from stdin. Exits 0 when there is nothing to do or the file
is clean. Exits 2 with the remaining ruff findings on stderr, which Claude Code feeds
back to the model. Does nothing until the project has a pyproject.toml with ruff
installed, and skips files under .claude/.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def ruff(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--quiet", "ruff", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=50,
        check=False,
    )


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    file_path = (event.get("tool_input") or {}).get("file_path")
    if not file_path or not str(file_path).endswith(".py"):
        return 0

    root = project_root().resolve()
    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_file() or not path.is_relative_to(root):
        return 0
    if ".claude" in path.relative_to(root).parts:
        return 0
    if not (root / "pyproject.toml").is_file() or shutil.which("uv") is None:
        return 0
    try:
        if ruff(root, "--version").returncode != 0:
            return 0
        ruff(root, "check", "--fix", "--quiet", str(path))
        ruff(root, "format", str(path))
        remaining = ruff(root, "check", "--output-format", "concise", str(path))
    except (subprocess.TimeoutExpired, OSError):
        return 0

    if remaining.returncode != 0:
        sys.stderr.write("ruff found problems it could not fix automatically:\n")
        sys.stderr.write(remaining.stdout[-3000:] or remaining.stderr[-3000:])
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
