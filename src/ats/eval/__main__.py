import argparse
import sys
from pathlib import Path

from ats.eval.golden import DEFAULT_ROOT, GoldSetError, build_labels
from ats.eval.render import LineTooWideError, render_golden
from ats.eval.split import DEFAULT_SEED


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ats.eval", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="validate profiles, write label files and the split")
    build.add_argument("--golden", default=str(DEFAULT_ROOT), help="golden set directory")
    build.add_argument("--seed", type=int, default=DEFAULT_SEED, help="split seed")
    build.set_defaults(run=_build)

    render = sub.add_parser("render", help="render posting and CV sources to PDF")
    render.add_argument("--golden", default=str(DEFAULT_ROOT), help="golden set directory")
    render.set_defaults(run=_render)

    args = parser.parse_args(argv)
    try:
        return args.run(args)
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
