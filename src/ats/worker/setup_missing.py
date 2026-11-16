"""`make setup-missing`: enqueue position setup for positions that never got a job.

Such a position has its posting text but no requirements and no `position_setup` job, for
example because its posting was ingested before phase 1.2 existed. The command only enqueues:
the worker makes the LLM call, one per position. It lists what it would do and stops unless it
is given `--yes`, so nobody spends quota by accident.
"""

import argparse
import sys
from collections.abc import Sequence
from typing import Any

import psycopg

from ats.services.requirements import (
    PositionPrefixError,
    enqueue_setup,
    find_stranded_positions,
)
from ats.settings import get_settings


def run(conn: psycopg.Connection[Any], prefix: str | None, *, yes: bool) -> int:
    try:
        stranded = find_stranded_positions(conn, prefix)
    except PositionPrefixError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not stranded:
        print("Nothing to do: no position is missing its setup job.")
        return 0

    print(f"{len(stranded)} position(s) have posting text, no requirements and no setup job:")
    for position in stranded:
        print(f"  {position.id}  {position.filename or '(no file name)'}")
    if not yes:
        print(
            f"Dry run, nothing enqueued. The worker would make {len(stranded)} LLM call(s). "
            "Run again with YES=1 to enqueue them."
        )
        return 0

    enqueued = sum(enqueue_setup(conn, position.id) for position in stranded)
    print(f"Enqueued {enqueued} setup job(s). A running worker picks them up and makes the calls.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="setup-missing", description=__doc__)
    parser.add_argument("--position", help="only this position: its id or the start of it")
    parser.add_argument("--yes", action="store_true", help="enqueue; without it, only list")
    args = parser.parse_args(argv)
    with psycopg.connect(get_settings().database_url) as conn:  # commits on a clean exit
        return run(conn, args.position or None, yes=args.yes)


if __name__ == "__main__":
    sys.exit(main())
