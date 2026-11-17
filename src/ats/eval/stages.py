"""Eval stages for 1.4a: the masking leak check and the CV parsing run.

- `masking` needs no model. For every CV of the split it extracts the text, masks it, and looks
  for the profile's name, email and phone in what is left. The truth is `contacts.json`, which was
  read off the CV headers by a one-off script that shares no code with the masker, so the check
  cannot pass only because the masker and its yardstick agree.
- `parsing` calls the model once per CV on masked text (the response cache makes a repeat free)
  and keeps the stored form of the result: parsed items with positions, months and tenure.
"""

import json
import random
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from ats.eval.golden import GoldSet
from ats.llm.types import LLMClient, RateLimitError
from ats.pipeline.extract import extract_text
from ats.pipeline.facts import build_facts
from ats.pipeline.masking import mask_text
from ats.pipeline.normalize import normalize_for_lexical
from ats.pipeline.parsing import parse_cv

CONTACTS_FILE = "contacts.json"
MIN_NAME_TOKEN = 3


class ContactTruth(BaseModel):
    name: str
    email: str
    phone: str


class StageError(Exception):
    pass


def load_contacts(root: Path) -> dict[str, ContactTruth]:
    raw = json.loads((root / CONTACTS_FILE).read_text(encoding="utf-8"))
    return {cv_id: ContactTruth.model_validate(row) for cv_id, row in raw.items()}


# --- Masking -------------------------------------------------------------------------------


class NameLeak(BaseModel):
    cv_id: str
    tokens: list[str]


class MaskingReport(BaseModel):
    cvs: int
    email_leaks: list[str]
    phone_leaks: list[str]
    # A name leaks when any of its words of three letters or more is still in the masked text,
    # compared folded and transliterated: the strictest reading.
    name_leaks: list[NameLeak]

    @property
    def email_rate(self) -> float:
        return len(self.email_leaks) / self.cvs if self.cvs else 0.0

    @property
    def phone_rate(self) -> float:
        return len(self.phone_leaks) / self.cvs if self.cvs else 0.0

    @property
    def name_rate(self) -> float:
        return len(self.name_leaks) / self.cvs if self.cvs else 0.0


def _folded_words(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", normalize_for_lexical(text))


def leaked_name_tokens(name: str, masked_text: str) -> list[str]:
    present = set(_folded_words(masked_text))
    return sorted({w for w in _folded_words(name) if len(w) >= MIN_NAME_TOKEN and w in present})


def run_masking(
    golden: GoldSet,
    contacts: dict[str, ContactTruth],
    cv_ids: Sequence[str],
    min_chars_per_page: int,
) -> MaskingReport:
    email_leaks: list[str] = []
    phone_leaks: list[str] = []
    name_leaks: list[NameLeak] = []
    for cv_id in cv_ids:
        truth = contacts.get(cv_id)
        if truth is None:
            raise StageError(f"{CONTACTS_FILE} has no entry for {cv_id}")
        text = extract_text(
            golden.cvs[cv_id].pdf.read_bytes(), min_chars_per_page=min_chars_per_page
        ).text
        masked = mask_text(text).masked_text
        if truth.email.casefold() in masked.casefold():
            email_leaks.append(cv_id)
        if re.sub(r"\D", "", truth.phone) in re.sub(r"\D", "", masked):
            phone_leaks.append(cv_id)
        tokens = leaked_name_tokens(truth.name, masked)
        if tokens:
            name_leaks.append(NameLeak(cv_id=cv_id, tokens=tokens))
    return MaskingReport(
        cvs=len(cv_ids), email_leaks=email_leaks, phone_leaks=phone_leaks, name_leaks=name_leaks
    )


# --- Parsing -------------------------------------------------------------------------------


class ParsedRecord(BaseModel):
    cv_id: str
    template: str
    is_cv: bool
    flags: list[str]
    coverage: float
    unlocated_items: int
    total_months: int
    # What the pipeline stores: masked text, and parsed JSON with positions and months.
    masked_text: str
    parsed_json: dict[str, object]


class ParsingReport(BaseModel):
    requested: int
    cvs: int  # parsed; fewer than `requested` when the provider's quota ran out
    # Set when a 429 survived the client's retries: the run stops there instead of trying on.
    stopped: str | None
    not_a_cv: list[str]
    low_coverage: list[str]
    suspected_injection: list[str]
    # Mean coverage and unlocated snippets per layout: two-column CVs extract interleaved, so
    # they are where snippet matching is most likely to fail.
    by_template: dict[str, dict[str, float]]
    records: list[ParsedRecord]


def run_parsing(
    golden: GoldSet,
    client: LLMClient,
    cv_ids: Sequence[str],
    min_chars_per_page: int,
    as_of: date,
) -> tuple[ParsingReport, list[tuple[int, int, float, bool]]]:
    records: list[ParsedRecord] = []
    usage: list[tuple[int, int, float, bool]] = []
    stopped: str | None = None
    for cv_id in cv_ids:
        cv = golden.cvs[cv_id]
        text = extract_text(cv.pdf.read_bytes(), min_chars_per_page=min_chars_per_page).text
        masked = mask_text(text)
        try:
            result = parse_cv(client, masked.masked_text)
        except RateLimitError as exc:
            # A daily quota does not come back within the run; keep what is parsed and say so.
            stopped = f"rate limit after {len(records)} of {len(cv_ids)} CVs, at {cv_id}: {exc}"
            break
        usage.append(
            (
                result.usage.input_tokens,
                result.usage.output_tokens,
                result.usage.latency_s,
                result.usage.cache_hit,
            )
        )
        facts = build_facts(result.output, masked.masked_text, masked.spans, as_of)
        records.append(
            ParsedRecord(
                cv_id=cv_id,
                template=cv.profile.template,
                is_cv=result.output.is_cv,
                flags=[flag["code"] for flag in facts.flags],
                coverage=facts.parsed_json["coverage"],
                unlocated_items=facts.parsed_json["unlocated_items"],
                total_months=facts.parsed_json["tenure"]["total_months"],
                masked_text=masked.masked_text,
                parsed_json=facts.parsed_json,
            )
        )
    by_template: dict[str, dict[str, float]] = {}
    for template in sorted({r.template for r in records}):
        rows = [r for r in records if r.template == template]
        by_template[template] = {
            "cvs": float(len(rows)),
            "mean_coverage": sum(r.coverage for r in rows) / len(rows),
            "unlocated_items": float(sum(r.unlocated_items for r in rows)),
        }
    report = ParsingReport(
        requested=len(cv_ids),
        stopped=stopped,
        cvs=len(records),
        not_a_cv=[r.cv_id for r in records if "not_a_cv" in r.flags],
        low_coverage=[r.cv_id for r in records if "low_coverage" in r.flags],
        suspected_injection=[r.cv_id for r in records if "suspected_injection" in r.flags],
        by_template=by_template,
        records=records,
    )
    return report, usage


# --- The seeded subset for the real parsing run --------------------------------------------

# One free-tier day allows about 20 requests (§6.1); 18 leaves two spare.
SUBSET_SIZE = 18
SUBSET_SEED = 20261117


class SubsetError(Exception):
    pass


class Subset(BaseModel):
    seed: int
    cv_ids: list[str]
    # dimension -> value -> the selected CVs that show it; the dry run prints this as proof.
    coverage: dict[str, dict[str, list[str]]]


def _traits(golden: GoldSet, cv_id: str) -> dict[str, str]:
    profile = golden.cvs[cv_id].profile
    traits = {
        "language_script": profile.style,
        "layout": profile.template,
        "position": profile.position_id,
    }
    if profile.hard_case:
        traits["hard_case"] = profile.hard_case.tag
    return traits


def select_subset(golden: GoldSet, seed: int = SUBSET_SEED, size: int = SUBSET_SIZE) -> Subset:
    """At most `size` dev-split CVs that together show every language/script, both layouts,
    every position and every hard case that exists in the dev split.

    Deterministic: a seeded shuffle fixes the order, then CVs that cover the most uncovered
    values are taken first, and the remaining places go to layout-by-language pairs not yet seen,
    then to the shuffle order. The test split is never read.
    """
    dev = golden.cv_ids("dev")
    traits = {cv_id: _traits(golden, cv_id) for cv_id in dev}
    needed = {(dim, value) for t in traits.values() for dim, value in t.items()}
    order = list(dev)
    random.Random(seed).shuffle(order)

    chosen: list[str] = []
    uncovered = set(needed)
    while uncovered:
        best = max(
            (c for c in order if c not in chosen),
            key=lambda c: len(uncovered & set(traits[c].items())),
        )
        if not uncovered & set(traits[best].items()):
            break
        chosen.append(best)
        uncovered -= set(traits[best].items())
    if uncovered or len(chosen) > size:
        raise SubsetError(
            f"{size} CVs cannot show every value (still missing: {sorted(uncovered)}, "
            f"{len(chosen)} needed so far)"
        )
    seen_pairs = {(traits[c]["language_script"], traits[c]["layout"]) for c in chosen}
    for c in order:
        if len(chosen) >= size:
            break
        pair = (traits[c]["language_script"], traits[c]["layout"])
        if c not in chosen and pair not in seen_pairs:
            chosen.append(c)
            seen_pairs.add(pair)
    for c in order:
        if len(chosen) >= size:
            break
        if c not in chosen:
            chosen.append(c)
    chosen.sort()

    coverage: dict[str, dict[str, list[str]]] = {}
    for dim, value in sorted(needed):
        coverage.setdefault(dim, {})[value] = [c for c in chosen if traits[c].get(dim) == value]
    return Subset(seed=seed, cv_ids=chosen, coverage=coverage)
