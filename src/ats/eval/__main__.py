import argparse
import logging
import sys
from pathlib import Path

from ats.eval.fallback import create_eval_llm_client
from ats.eval.golden import (
    DEFAULT_ROOT,
    GOLDEN_AS_OF,
    GoldSet,
    GoldSetError,
    build_labels,
    load_golden,
)
from ats.eval.harness import (
    MAX_CALLS_WITHOUT_CONFIRMATION,
    EvalError,
    RunResult,
    Stage,
    count_prior_runs,
    format_report,
    plan_run,
    run_eval,
    write_result,
)
from ats.eval.langfuse_export import export_run
from ats.eval.pipeline_judge import PipelineJudge
from ats.eval.render import LineTooWideError, render_golden
from ats.eval.split import DEFAULT_SEED
from ats.eval.stages import StageError, SubsetError, load_contacts, load_uncertain
from ats.eval.stub import StubJudge
from ats.llm.cache import ResponseCache
from ats.llm.types import LLMError
from ats.observability import LangfuseTracer, get_tracer
from ats.settings import get_settings

log = logging.getLogger(__name__)
RESULTS_DIR = DEFAULT_ROOT.parent / "results"
STAGES_BY_NAME: dict[str, Stage] = {
    "extraction": "extraction",
    "verdicts": "verdicts",
    "masking": "masking",
    "parsing": "parsing",
    "judge": "judge",
}


def _build(args: argparse.Namespace) -> int:
    golden = build_labels(Path(args.golden), args.seed)
    test = len(golden.cv_ids("test"))
    print(
        f"{len(golden.positions)} positions, {len(golden.cvs)} CVs "
        f"({len(golden.cv_ids('dev'))} dev, {test} test), {len(golden.verdicts)} verdicts"
    )
    return 0


def _render(args: argparse.Namespace) -> int:
    changed = render_golden(Path(args.golden))
    print(f"{len(changed)} PDFs written or changed")
    for path in changed:
        print(f"  {path.name}")
    return 0


def _run(args: argparse.Namespace) -> int:
    stages: list[Stage] = []
    for name in str(args.stages).split(","):
        stage = STAGES_BY_NAME.get(name.strip())
        if stage is None:
            raise EvalError(f"unknown stage {name!r}; choose from {', '.join(STAGES_BY_NAME)}")
        stages.append(stage)
    settings = get_settings()
    if args.require_real and settings.llm_provider == "fake":
        raise EvalError(
            "LLM_PROVIDER=fake: this command is the real-model check and would use the demo "
            "client. Unset LLM_PROVIDER (or set it to gemini) and try again."
        )
    fallback = str(args.fallback or settings.llm_fallback)
    if fallback not in ("", "openrouter"):
        raise EvalError(f"unknown fallback {fallback!r}; only openrouter exists")
    fallback_model = settings.openrouter_model if fallback else None
    golden = load_golden(Path(args.golden))
    plan = plan_run(
        golden,
        stages,
        model=settings.llm_model,
        cache=ResponseCache(settings.llm_cache_dir),
        min_chars_per_page=settings.min_chars_per_page,
        fallback_model=fallback_model,
        split=args.split,
        limit=args.limit,
    )
    if args.dry_run:
        print(plan.describe())
        return 0
    if plan.uncached_calls > MAX_CALLS_WITHOUT_CONFIRMATION and not args.yes:
        print(plan.describe())
        print(
            f"This run would call the model {plan.uncached_calls} times. Read the estimate "
            "above, then repeat the command with --yes (make: YES=1) to go ahead.",
            file=sys.stderr,
        )
        return 2
    needs_model = "extraction" in stages or "parsing" in stages or "judge" in stages
    client = create_eval_llm_client(settings, fallback) if needs_model else None
    judge: PipelineJudge | StubJudge = StubJudge(golden)
    if "judge" in stages:
        assert client is not None
        judge = PipelineJudge(
            client, as_of=GOLDEN_AS_OF, quote_threshold=settings.quote_fuzzy_threshold
        )
    result = run_eval(
        golden,
        variant=args.variant,
        split=args.split,
        limit=args.limit,
        stages=stages,
        judge=judge,
        client=client,
        model=settings.llm_model,
        min_chars_per_page=settings.min_chars_per_page,
        contacts=load_contacts(Path(args.golden)) if "masking" in stages else None,
        fallback_model=fallback_model,
        uncertain=load_uncertain(Path(args.golden), golden),
        llm_provider=settings.llm_provider if needs_model else None,
    )
    result.run_count = count_prior_runs(RESULTS_DIR, result) + 1
    print(format_report(result))
    print()
    print(f"Result written to {write_result(result, RESULTS_DIR)}")
    _export_to_langfuse(result, golden)
    return 0


def _export_to_langfuse(result: RunResult, golden: GoldSet) -> None:
    """With tracing on, the run also goes to Langfuse. A failure there never fails the eval."""
    tracer = get_tracer()
    if not isinstance(tracer, LangfuseTracer):
        return
    try:
        outcome = export_run(result, golden, tracer.client)
    except Exception as exc:
        print(f"Langfuse export failed ({type(exc).__name__}); the result file is written.")
        log.warning("langfuse export failed", exc_info=True)
        return
    finally:
        tracer.flush()
    if outcome is None:
        print("Langfuse: this run has no verdicts, nothing exported.")
    else:
        print(
            f"Langfuse: dataset {outcome.dataset}, experiment run {outcome.run_name} "
            f"({outcome.items} items)" + (f", {outcome.url}" if outcome.url else "")
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ats.eval", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="validate profiles, write label files and the split")
    build.add_argument("--golden", default=str(DEFAULT_ROOT), help="golden set directory")
    build.add_argument("--seed", type=int, default=DEFAULT_SEED, help="split seed")
    build.set_defaults(run=_build)

    run = sub.add_parser("run", help="run the evaluation and print the metrics table")
    run.add_argument("--golden", default=str(DEFAULT_ROOT), help="golden set directory")
    run.add_argument("--variant", default="A", help="A (B, C and D arrive in phase 3)")
    run.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    run.add_argument("--limit", type=int, default=None, help="only the first n CVs of the split")
    run.add_argument(
        "--stages",
        default="verdicts",
        help="comma list: extraction, parsing and judge call the model; verdicts (a stub "
        "judge) and masking do not. judge is variant A: parse and judge call per CV of the "
        "split. parsing runs a seeded subset of the dev split only",
    )
    run.add_argument("--dry-run", action="store_true", help="print calls and cost, call nothing")
    run.add_argument(
        "--fallback",
        choices=["openrouter"],
        default=None,
        help="opt in: after a Gemini daily quota continue on an OpenRouter free model "
        "(needs OPENROUTER_API_KEY; the result is labelled dev-smoke, non-baseline)",
    )
    run.add_argument(
        "--require-real",
        action="store_true",
        help="refuse to run when LLM_PROVIDER=fake (make smoke-real passes it)",
    )
    run.add_argument("--yes", action="store_true", help="confirm a run of more than 5 model calls")
    run.set_defaults(run=_run)

    render = sub.add_parser("render", help="render posting and CV sources to PDF")
    render.add_argument("--golden", default=str(DEFAULT_ROOT), help="golden set directory")
    render.set_defaults(run=_render)

    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (EvalError, StageError, SubsetError, LLMError, RuntimeError) as exc:
        print(f"Eval failed: {exc}", file=sys.stderr)
        return 1
    except LineTooWideError as exc:
        print(f"A line does not fit its column: {exc}", file=sys.stderr)
        return 1
    except GoldSetError as exc:
        print("The golden set has problems:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
