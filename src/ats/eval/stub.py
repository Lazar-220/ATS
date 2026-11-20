"""A judge that is not one: it proves the harness plumbing before the real judge exists (1.4b).

It answers with the gold verdict and quote, then spoils a fixed share of them in a way that is a
pure function of the CV, the requirement and the seed. So the metrics have something to measure:
a verdict a step away from the gold, now and then a quote that is not in the CV, and a `met`
without any quote. Its numbers say nothing about the model.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ats.eval.golden import GoldSet
from ats.eval.metrics import VERDICT_ORDER
from ats.eval.schemas import Position, Verdict


@dataclass(frozen=True)
class JudgedVerdict:
    requirement_id: int
    verdict: Verdict
    quote: str | None
    # Quote-check flags (quote_not_found, no_evidence). A flagged quote is not evidence.
    flags: tuple[str, ...] = ()


class Judge(Protocol):
    name: str

    def judge(self, cv_id: str, cv_text: str, position: Position) -> Sequence[JudgedVerdict]: ...


class StubJudge:
    name = "stub"

    def __init__(
        self,
        golden: GoldSet,
        *,
        wrong_verdict_rate: float = 0.2,
        invented_quote_rate: float = 0.1,
        seed: int = 1,
    ) -> None:
        self._golden = golden
        self._wrong = wrong_verdict_rate
        self._invented = invented_quote_rate
        self._seed = seed

    def _unit(self, cv_id: str, requirement_id: int) -> float:
        digest = hashlib.sha256(f"{self._seed}:{cv_id}:{requirement_id}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

    def judge(self, cv_id: str, cv_text: str, position: Position) -> list[JudgedVerdict]:
        # `cv_text` is unused: the stub reads the gold labels, which is the point of a stub.
        del cv_text, position
        answers: list[JudgedVerdict] = []
        for row in self._golden.verdicts_for(cv_id):
            draw = self._unit(cv_id, row.requirement_id)
            verdict, quote = row.verdict, row.quote
            if draw < self._wrong:
                # One class along the ordinal scale, wrapping at the end.
                verdict = VERDICT_ORDER[(VERDICT_ORDER.index(verdict) + 1) % len(VERDICT_ORDER)]
            elif draw < self._wrong + self._invented and quote:
                quote = f"{quote} (invented)"
            answers.append(JudgedVerdict(row.requirement_id, verdict, quote))
        return answers
