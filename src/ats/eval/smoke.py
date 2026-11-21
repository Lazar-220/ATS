"""The CI smoke eval: 20 golden CVs judged from a committed cache, never from a model (§5.4).

CI runs `replay`: the variant A judge (parse and judge call per CV, the production functions)
behind a client whose only way to answer is the committed cache in `eval/smoke_cache/`. A cache
miss raises `CacheMissError`; there is no transport that could reach a provider and no API key
is read. Accuracy and quote validity are compared with the thresholds in the manifest, and the
run exits non-zero below them.

The cache is its own directory, never `LLM_CACHE_DIR`, so a later real run cannot be served a
demo answer. Until the owner records a real run, the committed cache is made with the demo
provider (`LLM_PROVIDER=fake`, a keyword match): its manifest says `demo` and `non-baseline`, and
its numbers measure the plumbing (extraction, masking, parsing, quote check), not a model.
`record` rebuilds the cache; `--real` records the configured model instead (about 40 calls).
"""

import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from pydantic import BaseModel as _Schema
from pydantic import ValidationError as PydanticValidationError

from ats.eval.golden import DEFAULT_ROOT, GOLDEN_AS_OF, GoldSet
from ats.eval.pipeline_judge import PipelineJudge
from ats.eval.stub import JudgedVerdict
from ats.llm.cache import ResponseCache
from ats.llm.demo import create_demo_client
from ats.llm.managed import ManagedLLMClient
from ats.llm.ratelimit import RateLimiter
from ats.llm.types import LLMClient, LLMError, LLMRequest, RawCompletion
from ats.pipeline import judge as judge_module
from ats.pipeline import parsing as parsing_module
from ats.pipeline.extract import extract_text
from ats.settings import Settings

SMOKE_DIR = DEFAULT_ROOT.parent / "smoke_cache"
MANIFEST = "manifest.json"
CASES = 20
DEMO_MODEL = "demo-fake"
# Fixed here and not read from settings: the smoke must not depend on the environment.
MIN_CHARS_PER_PAGE = 100
QUOTE_THRESHOLD = 90


class CacheMissError(LLMError):
    """The smoke cache has no answer for this request. CI never falls back to a model."""


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict_accuracy: float
    quote_validity: float


class SmokeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Where the cached answers came from: "fake" (the demo provider) or a real provider.
    provider: str
    model: str
    demo: bool
    # A smoke subset is never a baseline, demo or real.
    baseline: bool
    note: str
    created: str
    prompt_versions: dict[str, str]
    cv_ids: list[str]
    thresholds: Thresholds
    # What the recording run measured, for the record; the thresholds are set below it.
    measured: Thresholds


class ReplayTransport:
    """The transport of a client that cannot call anything."""

    def complete(self, model: str, request: LLMRequest, schema: type[_Schema]) -> RawCompletion:
        raise CacheMissError(
            f"no cached answer for {request.prompt_version} ({schema.__name__}, model {model}): "
            "the smoke cache is stale or incomplete. Rebuild it with `make smoke-cache`."
        )


class DemoTransport:
    """Answers like the demo provider and reports invented token counts (about 4 characters)."""

    def __init__(self) -> None:
        self._demo = create_demo_client()

    def complete(self, model: str, request: LLMRequest, schema: type[_Schema]) -> RawCompletion:
        del model
        assert self._demo.responder is not None
        output = self._demo.responder(request, schema)
        text = output.model_dump_json()
        return RawCompletion(
            text=text,
            input_tokens=(len(request.system) + len(request.user)) // 4,
            output_tokens=len(text) // 4,
        )


def load_manifest(directory: Path = SMOKE_DIR) -> SmokeManifest:
    path = directory / MANIFEST
    try:
        return SmokeManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, PydanticValidationError) as exc:
        raise CacheMissError(
            f"{path} is missing or invalid. Rebuild the smoke cache with `make smoke-cache`."
        ) from exc


def replay_client(manifest: SmokeManifest, directory: Path = SMOKE_DIR) -> LLMClient:
    """A client that answers from the committed cache only. Every miss raises."""
    return ManagedLLMClient(
        ReplayTransport(),
        model=manifest.model,
        limiter=RateLimiter(60_000),
        cache=ResponseCache(directory),
        max_429_retries=0,
        max_server_retries=0,
    )


def select_cases(golden: GoldSet, count: int = CASES) -> list[str]:
    """Evenly spread over the sorted ids, so every position and style is in the subset."""
    ids = golden.cv_ids()
    return [ids[i * len(ids) // count] for i in range(count)]


@dataclass(frozen=True)
class SmokeResult:
    cases: int
    verdicts: int
    correct: int
    quoted: int
    valid_quotes: int

    @property
    def verdict_accuracy(self) -> float:
        return self.correct / self.verdicts

    @property
    def quote_validity(self) -> float:
        # Of the met and partial verdicts, the share whose quote is in the CV.
        return self.valid_quotes / self.quoted if self.quoted else 1.0


def run_smoke(golden: GoldSet, client: LLMClient, cv_ids: Sequence[str]) -> SmokeResult:
    judge = PipelineJudge(client, as_of=GOLDEN_AS_OF, quote_threshold=QUOTE_THRESHOLD)
    verdicts = correct = quoted = valid = 0
    for cv_id in cv_ids:
        cv = golden.cvs[cv_id]
        text = extract_text(cv.pdf.read_bytes(), min_chars_per_page=MIN_CHARS_PER_PAGE).text
        answers: Sequence[JudgedVerdict] = judge.judge(
            cv_id, text, golden.positions[cv.profile.position_id].meta
        )
        gold = {row.requirement_id: row.verdict for row in golden.verdicts_for(cv_id)}
        for answer in answers:
            verdicts += 1
            correct += answer.verdict == gold[answer.requirement_id]
            if answer.verdict != "not_met":
                quoted += 1
                valid += not answer.flags
    return SmokeResult(len(cv_ids), verdicts, correct, quoted, valid)


def check(result: SmokeResult, thresholds: Thresholds) -> list[str]:
    """The ways the run fell below the thresholds; empty means it passed."""
    failures: list[str] = []
    if result.verdict_accuracy < thresholds.verdict_accuracy:
        failures.append(
            f"verdict accuracy {result.verdict_accuracy:.1%} is below "
            f"{thresholds.verdict_accuracy:.1%}"
        )
    if result.quote_validity < thresholds.quote_validity:
        failures.append(
            f"quote validity {result.quote_validity:.1%} is below {thresholds.quote_validity:.1%}"
        )
    return failures


def record(
    golden: GoldSet,
    client: LLMClient,
    *,
    provider: str,
    model: str,
    demo: bool,
    directory: Path = SMOKE_DIR,
) -> SmokeManifest:
    """Run the 20 cases through `client` (whose cache is `directory`) and write the manifest.

    The thresholds are the measured values minus a margin, rounded down: the run must not fail
    on its own recording, and a real regression must.
    """
    cv_ids = select_cases(golden)
    result = run_smoke(golden, client, cv_ids)
    manifest = SmokeManifest(
        provider=provider,
        model=model,
        demo=demo,
        baseline=False,
        note=(
            "DEMO answers from the keyword-match demo provider: they measure the plumbing, not a "
            "model. Synthetic golden CVs only. Not a baseline."
            if demo
            else "Real model answers on synthetic golden CVs. A 20-CV smoke subset, not a baseline."
        ),
        created=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        prompt_versions={
            "parse": parsing_module.PROMPT_VERSION,
            "judge": judge_module.PROMPT_VERSION,
        },
        cv_ids=cv_ids,
        thresholds=Thresholds(
            verdict_accuracy=_floor(result.verdict_accuracy),
            quote_validity=_floor(result.quote_validity),
        ),
        measured=Thresholds(
            verdict_accuracy=round(result.verdict_accuracy, 4),
            quote_validity=round(result.quote_validity, 4),
        ),
    )
    (directory / MANIFEST).write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest


def _floor(value: float, margin: float = 0.05) -> float:
    return max(0.0, int((value - margin) * 100) / 100)


def reset(directory: Path = SMOKE_DIR) -> None:
    """Empty the smoke cache before a rebuild, so no stale entry stays behind."""
    if directory.is_dir():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def record_demo(golden: GoldSet, directory: Path = SMOKE_DIR) -> SmokeManifest:
    reset(directory)
    client = ManagedLLMClient(
        DemoTransport(),
        model=DEMO_MODEL,
        limiter=RateLimiter(60_000),
        cache=ResponseCache(directory),
    )
    return record(golden, client, provider="fake", model=DEMO_MODEL, demo=True, directory=directory)


def record_real(golden: GoldSet, settings: Settings) -> SmokeManifest:
    """Record the 20 cases with the configured model: about 40 calls, owner-run only."""
    from ats.llm.gemini import GeminiTransport  # not imported on the replay path

    key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
    if not key:
        raise RuntimeError("LLM_API_KEY is not set; put it in .env")
    reset()
    client = ManagedLLMClient(
        GeminiTransport(key),
        model=settings.llm_model,
        limiter=RateLimiter(settings.llm_rpm),
        cache=ResponseCache(SMOKE_DIR),
    )
    return record(
        golden, client, provider=settings.llm_provider, model=settings.llm_model, demo=False
    )


def describe(manifest: SmokeManifest, result: SmokeResult) -> str:
    return "\n".join(
        [
            f"Smoke eval: {result.cases} synthetic golden CVs, answered from the committed cache "
            f"({manifest.provider}, model {manifest.model}"
            f"{', DEMO, non-baseline' if manifest.demo else ''}); no model was called.",
            f"  verdict accuracy {result.verdict_accuracy:.1%} "
            f"({result.correct} of {result.verdicts}), threshold "
            f"{manifest.thresholds.verdict_accuracy:.1%}",
            f"  quote validity   {result.quote_validity:.1%} "
            f"({result.valid_quotes} of {result.quoted} met or partial verdicts), threshold "
            f"{manifest.thresholds.quote_validity:.1%}",
        ]
    )


def dump(manifest: SmokeManifest) -> str:
    return json.dumps(manifest.model_dump(), indent=2)
