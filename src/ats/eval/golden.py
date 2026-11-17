"""Loads and validates the golden set under `eval/golden/`, and derives its label files.

    positions/<id>/position.json, posting.txt, posting.pdf
    profiles/<cv_id>.json         what is true of the candidate, with the quote that shows it
    cvs/<cv_id>.txt, <cv_id>.pdf  written from the profile
    labels/verdicts.jsonl         derived from the profiles by `python -m ats.eval build`
    labels/relevance.jsonl        derived the same way
    split.json                    derived from the seed, then frozen once the set is complete

The profile is the one place a verdict is written by hand. The JSONL files are what the harness
reads, and the loader refuses a set whose files disagree with the profiles, so the two cannot
drift apart.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ValidationError

from ats.eval.cvsource import CvSource, CvSourceError, parse_cv_source
from ats.eval.schemas import (
    Position,
    Profile,
    RelevanceLabel,
    SplitFile,
    SplitName,
    VerdictLabel,
)
from ats.eval.split import DEFAULT_SEED, TEST_FRACTION, assign_split, strata_of

# The date "present" means in every golden CV. Tenure code takes it as an `as_of` argument; the
# eval passes this, production passes today's date. Nothing may read the clock for it.
GOLDEN_AS_OF = date(2026, 11, 17)

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "eval" / "golden"


class GoldSetError(Exception):
    """The golden set is inconsistent. `problems` lists every defect found, not only the first."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


@dataclass(frozen=True)
class GoldPosition:
    meta: Position
    posting_text: str
    posting_pdf: Path


@dataclass(frozen=True)
class GoldCv:
    profile: Profile
    source: CvSource
    pdf: Path
    split: SplitName | None  # None until `build` has written split.json


@dataclass(frozen=True)
class GoldSet:
    positions: dict[str, GoldPosition]
    cvs: dict[str, GoldCv]
    verdicts: list[VerdictLabel]
    relevance: list[RelevanceLabel]
    seed: int

    def cv_ids(self, split: SplitName | None = None) -> list[str]:
        return [cv_id for cv_id, cv in sorted(self.cvs.items()) if split in (None, cv.split)]

    def verdicts_for(self, cv_id: str) -> list[VerdictLabel]:
        return [row for row in self.verdicts if row.cv_id == cv_id]


@dataclass(frozen=True)
class _Parts:
    """What `build` can work from: everything except the derived files."""

    positions: dict[str, GoldPosition]
    cvs: dict[str, tuple[Profile, CvSource, Path]]


def _read_model[M: BaseModel](path: Path, model: type[M], problems: list[str]) -> M | None:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        problems.append(f"{path.name}: {exc}")
        return None


def _read_jsonl[M: BaseModel](path: Path, model: type[M], problems: list[str]) -> list[M]:
    rows: list[M] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        problems.append(f"{path.name}: {exc}")
        return rows
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            rows.append(model.model_validate_json(line))
        except ValidationError as exc:
            problems.append(f"{path.name} line {number}: {exc}")
    return rows


def _load_positions(root: Path, problems: list[str]) -> dict[str, GoldPosition]:
    positions: dict[str, GoldPosition] = {}
    for folder in sorted(p for p in (root / "positions").glob("*") if p.is_dir()):
        meta = _read_model(folder / "position.json", Position, problems)
        if meta is None:
            continue
        if meta.id != folder.name:
            problems.append(f"positions/{folder.name}: position.json says id {meta.id!r}")
            continue
        text_path, pdf_path = folder / "posting.txt", folder / "posting.pdf"
        if not text_path.is_file() or not pdf_path.is_file():
            problems.append(f"positions/{folder.name}: posting.txt or posting.pdf is missing")
            continue
        positions[meta.id] = GoldPosition(meta, text_path.read_text(encoding="utf-8"), pdf_path)
    return positions


def _load_parts(root: Path, problems: list[str]) -> _Parts:
    positions = _load_positions(root, problems)
    cvs: dict[str, tuple[Profile, CvSource, Path]] = {}
    for path in sorted((root / "profiles").glob("*.json")):
        profile = _read_model(path, Profile, problems)
        if profile is None:
            continue
        if profile.cv_id != path.stem:
            problems.append(f"profiles/{path.name}: cv_id is {profile.cv_id!r}")
            continue
        text_path, pdf_path = root / "cvs" / f"{path.stem}.txt", root / "cvs" / f"{path.stem}.pdf"
        if not text_path.is_file() or not pdf_path.is_file():
            problems.append(f"{profile.cv_id}: cvs/{path.stem}.txt or .pdf is missing")
            continue
        try:
            source = parse_cv_source(text_path.read_text(encoding="utf-8"), profile.template)
        except CvSourceError as exc:
            problems.append(f"{profile.cv_id}: {exc}")
            continue
        cvs[profile.cv_id] = (profile, source, pdf_path)
    problems.extend(_check_profiles(positions, cvs))
    return _Parts(positions, cvs)


def _check_profiles(
    positions: dict[str, GoldPosition], cvs: dict[str, tuple[Profile, CvSource, Path]]
) -> list[str]:
    problems: list[str] = []
    for cv_id, (profile, source, _pdf) in cvs.items():
        position = positions.get(profile.position_id)
        if position is None:
            problems.append(f"{cv_id}: unknown position {profile.position_id!r}")
            continue
        wanted = {req.id for req in position.meta.requirements}
        answered = {claim.requirement_id for claim in profile.claims}
        if answered != wanted:
            problems.append(
                f"{cv_id}: claims answer {sorted(answered)} but {position.meta.id} "
                f"has requirements {sorted(wanted)}"
            )
        if set(profile.relevance) != set(positions):
            problems.append(
                f"{cv_id}: relevance must name exactly the positions {sorted(positions)}"
            )
        for claim in profile.claims:
            # A gold quote is a verbatim substring of the CV source, inside one line (§5.1).
            if claim.quote is not None and not source.contains_quote(claim.quote):
                problems.append(
                    f"{cv_id} requirement {claim.requirement_id}: quote is not a verbatim "
                    f"substring of one line of the CV: {claim.quote!r}"
                )
    return problems


def derive_verdicts(cvs: dict[str, tuple[Profile, CvSource, Path]]) -> list[VerdictLabel]:
    return [
        VerdictLabel(
            cv_id=cv_id,
            position_id=profile.position_id,
            requirement_id=claim.requirement_id,
            verdict=claim.verdict,
            quote=claim.quote,
        )
        for cv_id, (profile, _source, _pdf) in sorted(cvs.items())
        for claim in sorted(profile.claims, key=lambda c: c.requirement_id)
    ]


def derive_relevance(cvs: dict[str, tuple[Profile, CvSource, Path]]) -> list[RelevanceLabel]:
    return [
        RelevanceLabel(cv_id=cv_id, position_id=position_id, relevance=value)
        for cv_id, (profile, _source, _pdf) in sorted(cvs.items())
        for position_id, value in sorted(profile.relevance.items())
    ]


def derive_split(
    cvs: dict[str, tuple[Profile, CvSource, Path]], seed: int, test_fraction: float = TEST_FRACTION
) -> SplitFile:
    strata = strata_of({cv_id: (p.position_id, p.style) for cv_id, (p, _s, _f) in cvs.items()})
    return SplitFile(
        seed=seed,
        test_fraction=test_fraction,
        assignment=dict(sorted(assign_split(strata, seed, test_fraction).items())),
    )


def _jsonl(rows: Sequence[BaseModel]) -> str:
    return "".join(json.dumps(row.model_dump(), ensure_ascii=False) + "\n" for row in rows)


def build_labels(root: Path = DEFAULT_ROOT, seed: int = DEFAULT_SEED) -> GoldSet:
    """Validate the profiles and CVs, write the label files and the split, and load the result."""
    problems: list[str] = []
    parts = _load_parts(root, problems)
    if problems:
        raise GoldSetError(problems)
    labels = root / "labels"
    labels.mkdir(exist_ok=True)
    (labels / "verdicts.jsonl").write_text(
        _jsonl(derive_verdicts(parts.cvs)), encoding="utf-8", newline="\n"
    )
    (labels / "relevance.jsonl").write_text(
        _jsonl(derive_relevance(parts.cvs)), encoding="utf-8", newline="\n"
    )
    split = derive_split(parts.cvs, seed)
    (root / "split.json").write_text(
        json.dumps(split.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return load_golden(root)


def _check_references(
    rows: Sequence[VerdictLabel | RelevanceLabel], parts: _Parts, file: str
) -> list[str]:
    problems: list[str] = []
    for row in rows:
        where = f"{file}: {row.cv_id}/{row.position_id}"
        if row.cv_id not in parts.cvs:
            problems.append(f"{where}: no such CV")
        if row.position_id not in parts.positions:
            problems.append(f"{where}: no such position")
        elif isinstance(row, VerdictLabel) and row.requirement_id not in {
            req.id for req in parts.positions[row.position_id].meta.requirements
        }:
            problems.append(f"{where}: no such requirement {row.requirement_id}")
    return problems


def load_golden(root: Path = DEFAULT_ROOT) -> GoldSet:
    """Load the whole set. Raises `GoldSetError` listing every inconsistency."""
    problems: list[str] = []
    parts = _load_parts(root, problems)
    verdicts = _read_jsonl(root / "labels" / "verdicts.jsonl", VerdictLabel, problems)
    relevance = _read_jsonl(root / "labels" / "relevance.jsonl", RelevanceLabel, problems)
    split = _read_model(root / "split.json", SplitFile, problems)
    problems.extend(_check_references(verdicts, parts, "verdicts.jsonl"))
    problems.extend(_check_references(relevance, parts, "relevance.jsonl"))
    if problems:
        raise GoldSetError(problems)
    assert split is not None  # a missing file was reported above

    # The files must be exactly what the profiles imply.
    if verdicts != derive_verdicts(parts.cvs):
        problems.append("verdicts.jsonl differs from the profiles; run `python -m ats.eval build`")
    if relevance != derive_relevance(parts.cvs):
        problems.append("relevance.jsonl differs from the profiles; run `python -m ats.eval build`")
    if split != derive_split(parts.cvs, split.seed, split.test_fraction):
        problems.append("split.json is not what its seed gives for these CVs; run `build`")
    if problems:
        raise GoldSetError(problems)

    cvs = {
        cv_id: GoldCv(profile, source, pdf, split.assignment[cv_id])
        for cv_id, (profile, source, pdf) in parts.cvs.items()
    }
    return GoldSet(parts.positions, cvs, verdicts, relevance, split.seed)
