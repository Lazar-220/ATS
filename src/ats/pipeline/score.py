"""The score and the ranking order, computed by code from the verdicts (§2.4 step 8).

met 1, partial 0.5, not_met 0. Coverage is `Σ wᵢ·sᵢ / Σ wᵢ`, separately for mandatory and
nice-to-have requirements, and the score is `100 × (0.7 × mandatory + 0.3 × nice-to-have)`.

Two rules the plan leaves open (owner decisions, docs/PROGRESS.md):

- A requirement with refinements (§1.1: "not counted twice") and all its descendants form one
  unit. The unit has the root's weight and kind, and its score is the mean of the members'
  scores; the members' own weights are ignored. Every member still has its verdict.
- A posting without requirements of one kind renormalizes over the kinds present, so a posting
  with no nice-to-have requirements is not capped at 70.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

MANDATORY_SHARE = 0.7
NICE_TO_HAVE_SHARE = 0.3
VERDICT_POINTS = {"met": 1.0, "partial": 0.5, "not_met": 0.0}


@dataclass(frozen=True)
class ScoredRequirement:
    key: int
    parent_key: int | None
    kind: Literal["mandatory", "nice_to_have"]
    weight: float


@dataclass(frozen=True)
class Score:
    score: float
    mandatory_coverage: float | None
    nice_to_have_coverage: float | None
    # Some mandatory requirement, parent or refinement, is `not_met`. `partial` does not fail it.
    mandatory_failed: bool


def _unit_scores(
    requirements: Sequence[ScoredRequirement], points: Mapping[int, float]
) -> list[tuple[ScoredRequirement, float]]:
    """One (root, mean score of the root and its descendants) per unit."""
    keys = {r.key for r in requirements}
    children: dict[int, list[int]] = {}
    for req in requirements:
        if req.parent_key is not None and req.parent_key in keys:
            children.setdefault(req.parent_key, []).append(req.key)

    def members(key: int) -> list[int]:
        found = [key]
        for child in children.get(key, []):
            found += members(child)
        return found

    units: list[tuple[ScoredRequirement, float]] = []
    for req in requirements:
        if req.parent_key is not None and req.parent_key in keys:
            continue
        ids = members(req.key)
        units.append((req, sum(points[i] for i in ids) / len(ids)))
    return units


def compute_score(requirements: Sequence[ScoredRequirement], verdicts: Mapping[int, str]) -> Score:
    points = {req.key: VERDICT_POINTS[verdicts[req.key]] for req in requirements}
    units = _unit_scores(requirements, points)
    coverage: dict[str, float | None] = {}
    for kind in ("mandatory", "nice_to_have"):
        of_kind = [(req, value) for req, value in units if req.kind == kind]
        total = sum(req.weight for req, _ in of_kind)
        coverage[kind] = (
            sum(req.weight * value for req, value in of_kind) / total if total else None
        )
    shares = {"mandatory": MANDATORY_SHARE, "nice_to_have": NICE_TO_HAVE_SHARE}
    present = {kind: share for kind, share in shares.items() if coverage[kind] is not None}
    if not present:
        raise ValueError("a score needs at least one requirement with a positive weight")
    weighted = sum(share * (coverage[kind] or 0.0) for kind, share in present.items())
    return Score(
        score=round(100 * weighted / sum(present.values()), 2),
        mandatory_coverage=coverage["mandatory"],
        nice_to_have_coverage=coverage["nice_to_have"],
        mandatory_failed=any(
            req.kind == "mandatory" and verdicts[req.key] == "not_met" for req in requirements
        ),
    )


def ranking_key(mandatory_failed: bool, score: float) -> tuple[bool, float]:
    """Sort ascending: candidates without a failed mandatory requirement first, then by score."""
    return (mandatory_failed, -score)
