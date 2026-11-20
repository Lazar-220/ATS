"""The eval's Langfuse export, against a fake client (the live stack is a manual check)."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import ats.eval.__main__ as eval_cli
from ats.eval.golden import GoldSet, load_golden
from ats.eval.harness import RunResult, run_eval
from ats.eval.langfuse_export import EXPERIMENT_NAME, dataset_name, export_run
from ats.eval.stub import StubJudge
from ats.observability import LangfuseTracer, set_tracer


@pytest.fixture(scope="module")
def golden() -> GoldSet:
    return load_golden()


class FakeLangfuse:
    """Remembers what it is sent; its experiment runs the task and the evaluators like the SDK."""

    def __init__(self) -> None:
        self.datasets: dict[str, dict[str, Any]] = {}
        self.runs: list[dict[str, Any]] = []
        self.flushes = 0
        self.fail = False

    def create_dataset(self, *, name: str, description: str | None = None, **kwargs: Any) -> Any:
        self.datasets.setdefault(name, {})  # create is an upsert by name

    def create_dataset_item(
        self, *, dataset_name: str, input: Any, expected_output: Any, id: str, **kwargs: Any
    ) -> Any:
        self.datasets[dataset_name][id] = SimpleNamespace(
            id=id, input=input, expected_output=expected_output
        )

    def get_dataset(self, name: str, **kwargs: Any) -> Any:
        return SimpleNamespace(name=name, items=list(self.datasets[name].values()))

    def run_experiment(self, **kwargs: Any) -> Any:
        if self.fail:
            raise ConnectionError("langfuse is down")
        outputs = {item.id: kwargs["task"](item=item) for item in kwargs["data"]}
        item_evaluations = {
            item.id: kwargs["evaluators"][0](
                input=item.input,
                output=outputs[item.id],
                expected_output=item.expected_output,
                metadata=None,
            )
            for item in kwargs["data"]
        }
        results = [SimpleNamespace(item=item, output=outputs[item.id]) for item in kwargs["data"]]
        run_evaluations = kwargs["run_evaluators"][0](item_results=results)
        self.runs.append(
            {**kwargs, "outputs": outputs, "items": item_evaluations, "run": run_evaluations}
        )
        return SimpleNamespace(dataset_run_url=f"http://langfuse.test/runs/{kwargs['run_name']}")

    def flush(self) -> None:
        self.flushes += 1


def _run(golden: GoldSet, *, limit: int | None, started: str, wrong: float = 0.2) -> RunResult:
    result = run_eval(
        golden, variant="A", split="dev", limit=limit, stages=["verdicts"],
        judge=StubJudge(golden, wrong_verdict_rate=wrong), client=None, model="m",
        min_chars_per_page=100,
    )  # fmt: skip
    result.started_at = started
    return result


def test_the_dataset_is_the_split_with_gold_verdicts_as_expected_output(golden: GoldSet) -> None:
    fake = FakeLangfuse()
    outcome = export_run(_run(golden, limit=3, started="2026-11-20T10:00:00"), golden, fake)
    assert outcome is not None and outcome.dataset == dataset_name("dev")
    items = fake.datasets["ats-golden-dev"]
    assert sorted(item.input["cv_id"] for item in items.values()) == golden.cv_ids("dev")
    sample = next(iter(items.values()))
    gold = {str(r.requirement_id): r.verdict for r in golden.verdicts_for(sample.input["cv_id"])}
    assert sample.expected_output == gold
    assert all("text" in r for r in sample.input["requirements"])


def test_two_runs_are_two_experiments_on_one_dataset_with_the_same_items(golden: GoldSet) -> None:
    fake = FakeLangfuse()
    first = export_run(_run(golden, limit=3, started="2026-11-20T10:00:00"), golden, fake)
    ids = set(fake.datasets["ats-golden-dev"])
    second = export_run(
        _run(golden, limit=3, started="2026-11-20T10:05:00", wrong=0.5), golden, fake
    )
    assert first is not None and second is not None
    assert len(fake.datasets) == 1 and set(fake.datasets["ats-golden-dev"]) == ids  # no duplicates
    assert [run["name"] for run in fake.runs] == [EXPERIMENT_NAME, EXPERIMENT_NAME]
    assert fake.runs[0]["run_name"] != fake.runs[1]["run_name"]
    # Same items in both runs, so each can be compared per item.
    assert set(fake.runs[0]["outputs"]) == set(fake.runs[1]["outputs"])
    assert fake.runs[0]["outputs"] != fake.runs[1]["outputs"]
    assert fake.flushes == 2
    assert first.url and second.url and first.url != second.url


def test_a_limited_run_covers_only_its_cvs_and_the_evaluators_score_them(golden: GoldSet) -> None:
    fake = FakeLangfuse()
    result = _run(golden, limit=2, started="2026-11-20T10:00:00", wrong=0.0)
    export_run(result, golden, fake)
    run = fake.runs[0]
    assert len(run["data"]) == 2
    for evaluations in run["items"].values():
        by_name = {e.name: e.value for e in evaluations}
        assert by_name["verdict_accuracy"] == 1.0  # a judge with no spoiled verdicts
    assert [e.name for e in run["run"]] == ["verdict_accuracy"] and run["run"][0].value == 1.0
    assert run["metadata"]["model"] == "m" and run["metadata"]["limit"] == "2"


def test_nothing_but_ids_requirements_and_labels_is_sent(golden: GoldSet) -> None:
    fake = FakeLangfuse()
    export_run(_run(golden, limit=3, started="2026-11-20T10:00:00"), golden, fake)
    sent = json.dumps(
        [
            [vars(item) for item in fake.datasets["ats-golden-dev"].values()],
            fake.runs[0]["outputs"],
        ]
    )
    # A CV line can repeat a requirement's wording, which is rightly sent; anything longer and
    # not in the requirements is CV text, and must not be.
    requirements = " ".join(
        r.text for p in golden.positions.values() for r in p.meta.requirements
    ).casefold()
    cv_text = [row.quote for row in golden.verdicts if row.quote] + [
        claim.fact for cv in golden.cvs.values() for claim in cv.profile.claims
    ]
    checked = [t for t in cv_text if len(t) > 25 and t.casefold() not in requirements]
    assert checked
    for text in checked:
        assert text not in sent


def test_a_run_without_verdicts_exports_nothing(golden: GoldSet) -> None:
    fake = FakeLangfuse()
    result = _run(golden, limit=1, started="2026-11-20T10:00:00")
    result.verdicts = None
    assert export_run(result, golden, fake) is None
    assert not fake.datasets and not fake.runs


def test_the_cli_exports_when_tracing_is_on_and_survives_a_langfuse_that_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(eval_cli, "RESULTS_DIR", tmp_path)
    fake = FakeLangfuse()
    fake_sdk: Any = fake
    set_tracer(LangfuseTracer(fake_sdk))
    try:
        assert eval_cli.main(["run", "--split", "dev", "--limit", "2"]) == 0
        assert len(fake.runs) == 1
        assert "Langfuse: dataset ats-golden-dev" in capsys.readouterr().out
        fake.fail = True
        assert eval_cli.main(["run", "--split", "dev", "--limit", "2"]) == 0
        assert "Langfuse export failed (ConnectionError)" in capsys.readouterr().out
    finally:
        set_tracer(None)


def test_with_tracing_off_the_cli_does_not_touch_langfuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from ats.observability import NoopTracer

    monkeypatch.setattr(eval_cli, "RESULTS_DIR", tmp_path)
    set_tracer(NoopTracer())
    try:
        assert eval_cli.main(["run", "--split", "dev", "--limit", "2"]) == 0
    finally:
        set_tracer(None)
    assert "Langfuse" not in capsys.readouterr().out
