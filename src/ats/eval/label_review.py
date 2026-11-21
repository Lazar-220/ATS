"""Read-only listing of test-split verdicts for a human to check the gold labels (gate 1.8).

Lists every verdict of the gate proposal's frozen list, every `uncertain.json` pair in the test
split, and every verdict a result file got wrong or flagged. It reads the golden set and one
result file and writes nothing; no model is called.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ats.eval.golden import GoldSet

# The eight pairs of docs/review/gate_1_8_proposal.md, "Frozen exclusion list".
FROZEN_PAIRS: tuple[tuple[str, int], ...] = (
    ("ba_06", 5),
    ("be_07", 1),
    ("be_07", 2),
    ("da_05", 2),
    ("fc_10", 3),
    ("pm_07", 4),
    ("sm_08", 3),
    ("sm_09", 6),
)


@dataclass(frozen=True)
class ReviewRow:
    cv_id: str
    requirement_id: int
    requirement: str
    gold: str
    gold_quote: str | None
    predicted: str | None
    reasons: tuple[str, ...]


def review_rows(
    golden: GoldSet, uncertain: frozenset[tuple[str, int]], result: dict[str, Any]
) -> list[ReviewRow]:
    test = set(golden.cv_ids("test"))
    items: dict[tuple[str, int], dict[str, Any]] = {
        (i["cv_id"], int(i["requirement_id"])): i for i in result["verdicts"]["items"]
    }
    reasons: dict[tuple[str, int], list[str]] = {}

    def add(pair: tuple[str, int], why: str) -> None:
        if pair[0] in test:
            reasons.setdefault(pair, []).append(why)

    for pair in FROZEN_PAIRS:
        add(pair, "frozen list (gate proposal)")
    for pair in sorted(uncertain):
        add(pair, "uncertain.json")
    for pair, item in items.items():
        if item["predicted"] != item["gold"]:
            add(pair, f"wrong: judged {item['predicted']}")
        if item["flags"]:
            add(pair, "flagged: " + ", ".join(item["flags"]))

    rows: list[ReviewRow] = []
    for (cv_id, requirement_id), why in sorted(reasons.items()):
        label = next(r for r in golden.verdicts_for(cv_id) if r.requirement_id == requirement_id)
        position = golden.positions[label.position_id].meta
        text = next(r.text for r in position.requirements if r.id == requirement_id)
        item = items.get((cv_id, requirement_id))
        rows.append(
            ReviewRow(
                cv_id,
                requirement_id,
                text,
                label.verdict,
                label.quote,
                item["predicted"] if item else None,
                tuple(why),
            )
        )
    return rows


def format_rows(rows: list[ReviewRow]) -> str:
    lines = [f"{len(rows)} test-split verdicts to review (gold labels are not manually verified)"]
    for row in rows:
        lines += [
            "",
            f"{row.cv_id}  requirement {row.requirement_id}: {row.requirement}",
            f"  gold: {row.gold}   gold quote: {row.gold_quote!r}",
            f"  judge: {row.predicted}",
            f"  listed because: {'; '.join(row.reasons)}",
        ]
    return "\n".join(lines)


def load_result(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
