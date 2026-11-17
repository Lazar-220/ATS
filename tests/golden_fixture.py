"""Writes a tiny golden set into a directory, for tests of the loader and the harness."""

import json
from pathlib import Path
from typing import Any

from pdfs import make_pdf

POSITION: dict[str, Any] = {
    "id": "backend",
    "title": "Backend developer",
    "lang": "en",
    "requirements": [
        {"id": 1, "text": "Python", "kind": "mandatory", "weight": 1, "min_months": None,
         "parent": None, "aliases": []},
        {"id": 2, "text": "3 years of experience in Python", "kind": "mandatory", "weight": 3,
         "min_months": 36, "parent": 1, "aliases": []},
        {"id": 3, "text": "Docker", "kind": "nice_to_have", "weight": 1, "min_months": None,
         "parent": None, "aliases": []},
    ],
}  # fmt: skip

CV_TEXT = "Skills\nPython, SQL\nWork\n2019-2023 Backend developer, Python services\n"


def profile(cv_id: str, style: str = "en", **changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "cv_id": cv_id,
        "position_id": "backend",
        "style": style,
        "template": "single",
        "hard_case": None,
        "claims": [
            {"requirement_id": 1, "verdict": "met", "fact": "lists Python",
             "quote": "Python, SQL"},
            {"requirement_id": 2, "verdict": "met", "fact": "four years of Python",
             "quote": "2019-2023 Backend developer"},
            {"requirement_id": 3, "verdict": "not_met", "fact": "no Docker", "quote": None},
        ],
        "relevance": {"backend": 3, "analyst": 1},
    }  # fmt: skip
    data.update(changes)
    return data


def write_set(root: Path, cv_ids: list[str], *, styles: list[str] | None = None) -> None:
    """Two positions and the given CVs, all targeting `backend`. Label files are not written."""
    for position_id, base in (("backend", POSITION), ("analyst", None)):
        folder = root / "positions" / position_id
        folder.mkdir(parents=True)
        data = dict(base) if base else {**POSITION, "id": position_id, "title": "Analyst"}
        (folder / "position.json").write_text(json.dumps(data), encoding="utf-8")
        (folder / "posting.txt").write_text("Posting text", encoding="utf-8")
        (folder / "posting.pdf").write_bytes(make_pdf("Posting text"))
    (root / "profiles").mkdir()
    (root / "cvs").mkdir()
    for index, cv_id in enumerate(cv_ids):
        style = styles[index] if styles else "en"
        (root / "profiles" / f"{cv_id}.json").write_text(
            json.dumps(profile(cv_id, style)), encoding="utf-8"
        )
        (root / "cvs" / f"{cv_id}.txt").write_text(CV_TEXT, encoding="utf-8")
        (root / "cvs" / f"{cv_id}.pdf").write_bytes(make_pdf(CV_TEXT))
