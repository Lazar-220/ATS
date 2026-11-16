"""Versioned prompt files. A new version is a new file; the old one stays for old results."""

from importlib.resources import files


def load_prompt(version: str) -> str:
    """Read `<version>.md`, for example `requirements_v1`."""
    return files(__package__).joinpath(f"{version}.md").read_text(encoding="utf-8")
