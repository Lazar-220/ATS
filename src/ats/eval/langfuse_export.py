"""Send an eval run to Langfuse as a dataset and an experiment (§5.4, phase 1.6).

The dataset is the golden set's split: one item per CV, with the requirement list as input and
the gold verdicts as the expected output. A run is one experiment on that dataset (Langfuse's
"run name"), so two runs of different prompts or models can be compared item by item. The
harness has already produced the predictions, so the experiment's task replays them: nothing
here calls a model.

Only ids, requirement texts and verdict labels go out. The golden CVs are synthetic, and their
text is not sent anyway.
"""

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from ats.eval.golden import GoldSet
from ats.eval.harness import RunResult, SplitChoice, VerdictItem, select_cvs

log = logging.getLogger(__name__)

EXPERIMENT_NAME = "ats-eval"


class LangfuseDatasets(Protocol):
    """The part of the Langfuse SDK client this module uses."""

    def create_dataset(
        self, *, name: str, description: str | None = None, **kwargs: Any
    ) -> Any: ...

    def create_dataset_item(
        self, *, dataset_name: str, input: Any, expected_output: Any, id: str, **kwargs: Any
    ) -> Any: ...

    def get_dataset(self, name: str, **kwargs: Any) -> Any: ...

    def run_experiment(self, **kwargs: Any) -> Any: ...

    def flush(self) -> None: ...


@dataclass(frozen=True)
class ExportOutcome:
    dataset: str
    run_name: str
    items: int
    url: str | None


def dataset_name(split: str) -> str:
    return f"ats-golden-{split}"


def run_name(result: RunResult) -> str:
    """Unique per run: two runs of one configuration are still two experiments."""
    limit = "all" if result.limit is None else f"limit{result.limit}"
    demo = "demo-" if result.llm_provider == "fake" else ""
    return f"{demo}{result.variant}-{result.split}-{limit}-{result.started_at}"


def _accuracy(items: Sequence[VerdictItem]) -> float:
    return sum(1 for item in items if item.gold == item.predicted) / len(items) if items else 0.0


def export_run(
    result: RunResult, golden: GoldSet, client: LangfuseDatasets
) -> ExportOutcome | None:
    """Upload the dataset (idempotent) and the run. None when the run has no verdicts."""
    if result.verdicts is None:
        return None
    name = dataset_name(result.split)
    client.create_dataset(
        name=name,
        description=f"Golden set, {result.split} split. Gold labels not manually verified.",
    )
    for cv_id in select_cvs(golden, cast(SplitChoice, result.split), None):
        position_id = golden.cvs[cv_id].profile.position_id
        client.create_dataset_item(
            dataset_name=name,
            # A fixed id makes a second export an update, not a duplicate item.
            id=f"{name}:{cv_id}",
            input={
                "cv_id": cv_id,
                "position_id": position_id,
                "requirements": [
                    {"id": r.id, "text": r.text}
                    for r in golden.positions[position_id].meta.requirements
                ],
            },
            expected_output={
                str(row.requirement_id): row.verdict for row in golden.verdicts_for(cv_id)
            },
        )

    predicted: dict[str, dict[str, Any]] = defaultdict(dict)
    by_cv: dict[str, list[VerdictItem]] = defaultdict(list)
    for item in result.verdicts.items:
        predicted[item.cv_id][str(item.requirement_id)] = {
            "verdict": item.predicted,
            "flags": item.flags,
        }
        by_cv[item.cv_id].append(item)

    dataset = client.get_dataset(name)
    # A run with a LIMIT, or one that could not answer some CV, covers part of the dataset.
    data = [item for item in dataset.items if item.input["cv_id"] in predicted]

    def task(*, item: Any, **kwargs: Any) -> dict[str, Any]:
        return predicted[item.input["cv_id"]]

    def item_evaluator(
        *, input: Any, output: Any, expected_output: Any, metadata: Any = None, **kwargs: Any
    ) -> list[Any]:
        from langfuse import Evaluation

        cv_items = by_cv[input["cv_id"]]
        return [
            Evaluation(name="verdict_accuracy", value=_accuracy(cv_items)),
            Evaluation(name="flagged_verdicts", value=sum(1 for item in cv_items if item.flags)),
        ]

    def run_evaluator(*, item_results: Any, **kwargs: Any) -> list[Any]:
        from langfuse import Evaluation

        every = [item for items in by_cv.values() for item in items]
        return [Evaluation(name="verdict_accuracy", value=_accuracy(every))]

    name_of_run = run_name(result)
    outcome = client.run_experiment(
        name=EXPERIMENT_NAME,
        run_name=name_of_run,
        description=f"{result.pipeline_version.judge}, model {result.pipeline_version.model}",
        data=data,
        task=task,
        evaluators=[item_evaluator],
        run_evaluators=[run_evaluator],
        metadata={
            "code": result.pipeline_version.code,
            "model": result.pipeline_version.model,
            "prompts": ",".join(
                f"{k}={v}" for k, v in sorted(result.pipeline_version.prompts.items())
            ),
            "limit": str(result.limit),
            "label": result.label or "",
            "llm_provider": result.llm_provider or "",
        },
    )
    client.flush()
    return ExportOutcome(
        dataset=name,
        run_name=name_of_run,
        items=len(data),
        url=getattr(outcome, "dataset_run_url", None),
    )
