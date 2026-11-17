import argparse
import sys
from pathlib import Path

from ats.eval.golden import DEFAULT_ROOT, GoldSetError, build_labels, load_golden
from ats.eval.harness import (
    MAX_CALLS_WITHOUT_CONFIRMATION,
    EvalError,
    Stage,
    format_report,
    plan_run,
    run_eval,
    write_result,
)
from ats.eval.render import LineTooWideError, render_golden
from ats.eval.split import DEFAULT_SEED
from ats.eval.stub import StubJudge
from ats.llm.cache import ResponseCache
from ats.llm.factory import create_llm_client
from ats.llm.types import LLMError
from ats.settings import get_settings

RESULTS_DIR = DEFAULT_ROOT.parent / "results"
STAGES_BY_NAME: dict[str, Stage] = {"extraction": "extraction", "verdicts": "verdicts"}


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
    golden = load_golden(Path(args.golden))
    plan = plan_run(
        golden,
        stages,
        model=settings.llm_model,
        cache=ResponseCache(settings.llm_cache_dir),
        min_chars_per_page=settings.min_chars_per_page,
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
    client = create_llm_client(settings) if "extraction" in stages else None
    result = run_eval(
        golden,
        variant=args.variant,
        split=args.split,
        limit=args.limit,
        stages=stages,
        judge=StubJudge(golden),
        client=client,
        model=settings.llm_model,
        min_chars_per_page=settings.min_chars_per_page,
    )
    print(format_report(result))
    print()
    print(f"Result written to {write_result(result, RESULTS_DIR)}")
    return 0


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
        help="comma list of extraction (calls the model) and verdicts (stub judge until 1.4b)",
    )
    run.add_argument("--dry-run", action="store_true", help="print calls and cost, call nothing")
    run.add_argument("--yes", action="store_true", help="confirm a run of more than 5 model calls")
    run.set_defaults(run=_run)

    render = sub.add_parser("render", help="render posting and CV sources to PDF")
    render.add_argument("--golden", default=str(DEFAULT_ROOT), help="golden set directory")
    render.set_defaults(run=_render)

    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (EvalError, LLMError, RuntimeError) as exc:
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
