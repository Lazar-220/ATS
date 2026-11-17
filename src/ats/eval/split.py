"""The fixed dev/test split (§5.1): stratified, and a pure function of the ids and the seed."""

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence

from ats.eval.schemas import SplitName

DEFAULT_SEED = 20261117
TEST_FRACTION = 0.3

type Stratum = tuple[str, str]


def _order_key(seed: int, cv_id: str) -> str:
    # A hash, not random.shuffle: the order must not depend on the Python version.
    return hashlib.sha256(f"{seed}:{cv_id}".encode()).hexdigest()


def assign_split(
    strata: Mapping[Stratum, Sequence[str]], seed: int, test_fraction: float = TEST_FRACTION
) -> dict[str, SplitName]:
    """Put about `test_fraction` of every stratum in the test part.

    Rounding each stratum alone would drift far from 30% when strata hold two or three CVs, so
    the total is fixed first and the spare test slots go to the strata with the largest
    fractional remainder (ties by stratum key).
    """
    total = sum(len(ids) for ids in strata.values())
    keys = sorted(strata)
    floors = {key: int(len(strata[key]) * test_fraction) for key in keys}
    spare = int(total * test_fraction + 0.5) - sum(floors.values())
    by_remainder = sorted(keys, key=lambda k: (-(len(strata[k]) * test_fraction - floors[k]), k))
    quota = dict(floors)
    for key in by_remainder:
        if spare <= 0:
            break
        if quota[key] < len(strata[key]):
            quota[key] += 1
            spare -= 1

    assignment: dict[str, SplitName] = {}
    for key in keys:
        ordered = sorted(strata[key], key=lambda cv_id: _order_key(seed, cv_id))
        for position, cv_id in enumerate(ordered):
            assignment[cv_id] = "test" if position < quota[key] else "dev"
    return assignment


def strata_of(cvs: Mapping[str, Stratum]) -> dict[Stratum, list[str]]:
    """Group CV ids by (position, style)."""
    groups: dict[Stratum, list[str]] = defaultdict(list)
    for cv_id, stratum in cvs.items():
        groups[stratum].append(cv_id)
    return dict(groups)
