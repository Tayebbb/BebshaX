"""Safety contracts for the isolated ML measurement launcher, not quality labels."""

from pathlib import Path

import pytest

from ml_persona.tools import modernization_experiment as experiment


@pytest.mark.parametrize("name", ["model", "../model", "experiment-../model", "experiment-", "experiment-x/model", "E:/model"])
def test_experiment_refuses_arbitrary_or_frozen_artifact_paths(name: str) -> None:
    with pytest.raises(ValueError, match="experiment"):
        experiment.experiment_path(name)


def test_experiment_resolves_only_approved_ignored_namespace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(experiment, "ROOT", tmp_path)
    assert experiment.experiment_path("experiment-20260909-frozen-lexical") == (
        tmp_path / "data/processed/ml_persona/experiment-20260909-frozen-lexical"
    )


def test_experiment_evidence_never_overwrites_an_existing_report(tmp_path: Path) -> None:
    report = tmp_path / "evidence.json"
    experiment.write_evidence(report, {"exit_code": 0})
    original = report.read_bytes()
    with pytest.raises(FileExistsError):
        experiment.write_evidence(report, {"exit_code": 1})
    assert report.read_bytes() == original


def test_training_refuses_existing_experiment_before_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*arguments: object, **keywords: object) -> None:
        raise AssertionError("Existing output must not reach training")

    monkeypatch.setattr(experiment, "cli_step", forbidden)
    with pytest.raises(FileExistsError):
        experiment.train(tmp_path)