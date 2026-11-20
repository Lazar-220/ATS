"""A run on the fake provider is labelled, unpriced, and never counted with real runs."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

import ats.eval.__main__ as eval_cli
from ats.eval.harness import RunResult, count_prior_runs
from ats.observability import set_tracer
from ats.settings import get_settings

ARGS = ["run", "--split", "dev", "--limit", "1", "--stages", "judge"]


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    get_settings.cache_clear()
    set_tracer(None)
    yield
    get_settings.cache_clear()
    set_tracer(None)


def _only_result(directory: Path) -> RunResult:
    (path,) = directory.glob("*.json")
    return RunResult.model_validate_json(path.read_text(encoding="utf-8"))


def test_a_fake_run_records_its_provider_is_labelled_and_has_no_price(
    fake_provider: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(eval_cli, "RESULTS_DIR", tmp_path)
    assert eval_cli.main(ARGS) == 0
    result = _only_result(tmp_path)
    assert result.llm_provider == "fake"
    assert result.label == "demo, non-baseline"
    assert result.usage.cost_usd is None and result.usage.rate is None
    out = capsys.readouterr().out
    assert "demo, non-baseline" in out and "not priced (fake provider)" in out


def test_the_run_count_never_mixes_fake_and_real_runs(
    fake_provider: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(eval_cli, "RESULTS_DIR", tmp_path)
    assert eval_cli.main(ARGS) == 0
    fake = _only_result(tmp_path)
    real = fake.model_copy(update={"llm_provider": "gemini", "label": None})
    assert count_prior_runs(tmp_path, fake) == 1
    assert count_prior_runs(tmp_path, real) == 0  # the fake file is not a real run
    # A file without the field (written before this fix) counts as real.
    old = json.loads((next(tmp_path.glob("*.json"))).read_text(encoding="utf-8"))
    del old["llm_provider"]
    old["label"] = None
    (tmp_path / "old.json").write_text(json.dumps(old), encoding="utf-8")
    assert count_prior_runs(tmp_path, real) == 1
    assert count_prior_runs(tmp_path, fake) == 1


def test_the_demo_folder_is_not_read_by_the_counter(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    assert count_prior_runs(tmp_path / "demo", _stub_result()) == 0
    assert count_prior_runs(tmp_path, _stub_result()) == 0


def _stub_result() -> RunResult:
    from ats.eval.golden import load_golden
    from ats.eval.harness import run_eval
    from ats.eval.stub import StubJudge

    golden = load_golden()
    return run_eval(
        golden, variant="A", split="dev", limit=1, stages=["verdicts"],
        judge=StubJudge(golden), client=None, model="m", min_chars_per_page=100,
    )  # fmt: skip


def test_smoke_real_refuses_the_fake_provider(
    fake_provider: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(eval_cli, "RESULTS_DIR", tmp_path)
    assert eval_cli.main([*ARGS, "--require-real", "--dry-run"]) == 1
    assert "LLM_PROVIDER=fake" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_the_make_target_passes_require_real() -> None:
    makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")
    assert "--stages judge --require-real" in makefile


def test_the_experiment_name_and_metadata_say_demo(fake_provider: None, tmp_path: Path) -> None:
    from ats.eval.langfuse_export import run_name

    result = _stub_result().model_copy(update={"llm_provider": "fake"})
    assert run_name(result).startswith("demo-")
