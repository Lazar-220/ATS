"""The CI smoke eval: 20 golden CVs from a committed cache, no model, no key, no network."""

import json
import socket
from pathlib import Path
from typing import NoReturn

import pytest

from ats.eval.__main__ import main
from ats.eval.golden import load_golden
from ats.eval.smoke import (
    CASES,
    DEMO_MODEL,
    MANIFEST,
    SMOKE_DIR,
    CacheMissError,
    SmokeResult,
    Thresholds,
    check,
    load_manifest,
    record_demo,
    replay_client,
    run_smoke,
    select_cases,
)
from ats.pipeline.parsing import ParsedCV, build_request
from ats.settings import Settings, get_settings


def _no_network(*_args: object, **_kwargs: object) -> NoReturn:
    raise AssertionError("the smoke eval opened a network socket")


@pytest.fixture
def no_key_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CI environment: no API key, no provider setting, and the network is closed."""
    for name in ("LLM_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(socket, "socket", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    get_settings.cache_clear()


def test_the_committed_cache_passes_without_a_key_or_a_network(
    no_key_no_network: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["smoke"]) == 0
    out = capsys.readouterr().out
    assert "no model was called" in out and "DEMO, non-baseline" in out


def test_a_threshold_above_the_measured_value_fails_the_run(
    no_key_no_network: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["smoke", "--min-accuracy", "0.99"]) == 1
    assert "SMOKE FAILED: verdict accuracy" in capsys.readouterr().err
    assert main(["smoke", "--min-quote-validity", "1.01"]) == 1


def test_the_committed_cache_is_demo_data_in_its_own_directory() -> None:
    manifest = load_manifest()
    assert manifest.provider == "fake" and manifest.demo and not manifest.baseline
    assert manifest.model == DEMO_MODEL
    assert "DEMO" in manifest.note
    golden = load_golden()
    assert len(manifest.cv_ids) == CASES == len(set(manifest.cv_ids))
    assert set(manifest.cv_ids) <= set(golden.cvs)  # synthetic golden CVs only
    assert manifest.cv_ids == select_cases(golden)
    # Never the directory a real run writes to, so a demo answer cannot be served to one.
    assert SMOKE_DIR.resolve() != Settings().llm_cache_dir.resolve()
    assert SMOKE_DIR.name == "smoke_cache"
    # One parse and one judge answer per CV, each a JSON document.
    entries = [p for p in SMOKE_DIR.rglob("*.json") if p.name != MANIFEST]
    assert len(entries) == 2 * CASES
    for entry in entries:
        assert isinstance(json.loads(entry.read_text(encoding="utf-8"))["text"], str)


def test_a_cache_miss_raises_and_never_reaches_a_provider(
    no_key_no_network: None, tmp_path: Path
) -> None:
    client = replay_client(load_manifest(), tmp_path)  # an empty cache
    with pytest.raises(CacheMissError, match="make smoke-cache"):
        client.generate(build_request("Python developer 2019-2024"), ParsedCV)


def test_a_cv_that_is_not_in_the_cache_stops_the_run(no_key_no_network: None) -> None:
    golden = load_golden()
    manifest = load_manifest()
    other = next(cv_id for cv_id in golden.cv_ids() if cv_id not in manifest.cv_ids)
    with pytest.raises(CacheMissError):
        run_smoke(golden, replay_client(manifest), [other])


def test_a_stale_cache_fails_the_command_with_a_nonzero_exit(
    no_key_no_network: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A prompt change moves every cache key: the smoke must fail, not call a model."""
    monkeypatch.setattr("ats.pipeline.judge.load_prompt", lambda _version: "changed prompt text")
    assert main(["smoke"]) == 1
    assert "make smoke-cache" in capsys.readouterr().err


def test_recording_the_demo_cache_gives_a_cache_that_replays_to_the_same_numbers(
    no_key_no_network: None, tmp_path: Path
) -> None:
    golden = load_golden()
    manifest = record_demo(golden, tmp_path)
    assert (tmp_path / MANIFEST).is_file() and manifest.demo
    result = run_smoke(golden, replay_client(manifest, tmp_path), manifest.cv_ids)
    assert round(result.verdict_accuracy, 4) == manifest.measured.verdict_accuracy
    # The recorded thresholds sit below the measurement, so a run never fails on its own cache.
    assert not check(result, manifest.thresholds)
    # And the answers it recorded are the committed ones: same keys, so same files.
    committed = {p.name for p in SMOKE_DIR.rglob("*.json") if p.name != MANIFEST}
    assert committed == {p.name for p in tmp_path.rglob("*.json") if p.name != MANIFEST}


def test_check_names_each_threshold_that_is_missed() -> None:
    result = SmokeResult(cases=2, verdicts=10, correct=5, quoted=4, valid_quotes=3)
    both = check(result, Thresholds(verdict_accuracy=0.6, quote_validity=0.9))
    assert len(both) == 2
    assert check(result, Thresholds(verdict_accuracy=0.5, quote_validity=0.75)) == []


def test_recording_the_real_model_with_the_demo_provider_selected_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    get_settings.cache_clear()
    try:
        assert main(["smoke-cache", "--real", "--yes"]) == 1
    finally:
        get_settings.cache_clear()
    assert "LLM_PROVIDER=fake" in capsys.readouterr().err
