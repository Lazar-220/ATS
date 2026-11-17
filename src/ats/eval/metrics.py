"""Metrics of §5.2 that exist before the judge does: extraction and verdict agreement."""

import re
import warnings
from collections.abc import Sequence

from pydantic import BaseModel
from sklearn.exceptions import UndefinedMetricWarning  # pyright: ignore[reportMissingTypeStubs]
from sklearn.metrics import (  # pyright: ignore[reportMissingTypeStubs]
    accuracy_score,  # pyright: ignore[reportUnknownVariableType]
    cohen_kappa_score,  # pyright: ignore[reportUnknownVariableType]
    confusion_matrix,  # pyright: ignore[reportUnknownVariableType]
    f1_score,  # pyright: ignore[reportUnknownVariableType]
)

from ats.eval.matching import MatchResult
from ats.eval.schemas import Verdict

# Ordinal: a `partial` is nearer to either end than they are to each other, so the kappa weights
# the distance between classes (§5.2).
VERDICT_ORDER: tuple[Verdict, ...] = ("not_met", "partial", "met")


class ExtractionMetrics(BaseModel):
    extracted: int
    gold: int
    matched: int
    kind_correct: int
    precision: float
    recall: float
    f1: float
    # Of the matched requirements, the share whose mandatory / nice-to-have label is right.
    label_accuracy: float | None


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def extraction_metrics(
    *, extracted: int, gold: int, matched: int, kind_correct: int
) -> ExtractionMetrics:
    precision = _ratio(matched, extracted)
    recall = _ratio(matched, gold)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return ExtractionMetrics(
        extracted=extracted,
        gold=gold,
        matched=matched,
        kind_correct=kind_correct,
        precision=precision,
        recall=recall,
        f1=f1,
        label_accuracy=kind_correct / matched if matched else None,
    )


def extraction_metrics_from(result: MatchResult) -> ExtractionMetrics:
    matched = len(result.matches)
    return extraction_metrics(
        extracted=matched + len(result.unmatched_extracted),
        gold=matched + len(result.unmatched_gold),
        matched=matched,
        kind_correct=sum(m.kind_correct for m in result.matches),
    )


def pool_extraction(parts: Sequence[ExtractionMetrics]) -> ExtractionMetrics:
    """Micro average: counts are added before the ratios are taken."""
    return extraction_metrics(
        extracted=sum(p.extracted for p in parts),
        gold=sum(p.gold for p in parts),
        matched=sum(p.matched for p in parts),
        kind_correct=sum(p.kind_correct for p in parts),
    )


class VerdictMetrics(BaseModel):
    n: int
    accuracy: float
    macro_f1: float
    # Rows are the gold verdict, columns the predicted one, both in `VERDICT_ORDER`.
    labels: list[str]
    confusion: list[list[int]]
    # Quadratic-weighted kappa. None when it is undefined: one class only, on both sides.
    weighted_kappa: float | None


def verdict_metrics(pairs: Sequence[tuple[Verdict, Verdict]]) -> VerdictMetrics:
    """`pairs` holds (gold, predicted) per CV-requirement pair."""
    gold: list[str] = [g for g, _ in pairs]
    predicted: list[str] = [p for _, p in pairs]
    labels: list[str] = list(VERDICT_ORDER)
    matrix = confusion_matrix(gold, predicted, labels=labels).tolist()
    with warnings.catch_warnings():
        # One class on both sides leaves kappa undefined. It is reported as None below, so the
        # library's warning would only repeat that.
        warnings.simplefilter("ignore", UndefinedMetricWarning)
        kappa = float(cohen_kappa_score(gold, predicted, labels=labels, weights="quadratic"))
    return VerdictMetrics(
        n=len(pairs),
        accuracy=float(accuracy_score(gold, predicted)),
        macro_f1=float(f1_score(gold, predicted, labels=labels, average="macro", zero_division=0)),  # pyright: ignore[reportArgumentType]
        labels=labels,
        confusion=matrix,
        weighted_kappa=None if kappa != kappa else kappa,  # NaN is the only value unequal to itself
    )


_WHITESPACE = re.compile(r"\s+")


def quote_exists(quote: str, cv_text: str) -> bool:
    """The quote is a substring of the CV once runs of whitespace are collapsed on both sides.

    Plan §3.2 adds a fuzzy match at 90 for the judge's quotes; that arrives with the judge (1.4b).
    """
    return _WHITESPACE.sub(" ", quote).strip() in _WHITESPACE.sub(" ", cv_text)


class GroundingMetrics(BaseModel):
    # Verdicts met or partial that carry a quote, and how many of those quotes exist in the CV.
    quoted: int
    quote_exists: int
    quote_exists_share: float | None
    # Verdicts met or partial with no quote at all: flagged `no_evidence` in 1.4b.
    unquoted: int


def grounding_metrics(items: Sequence[tuple[Verdict, str | None, str]]) -> GroundingMetrics:
    """`items` holds (predicted verdict, predicted quote, CV text) per pair."""
    quotes = [(q, text) for verdict, q, text in items if verdict != "not_met" and q]
    unquoted = sum(1 for verdict, q, _ in items if verdict != "not_met" and not q)
    found = sum(1 for q, text in quotes if quote_exists(q, text))
    return GroundingMetrics(
        quoted=len(quotes),
        quote_exists=found,
        quote_exists_share=found / len(quotes) if quotes else None,
        unquoted=unquoted,
    )
