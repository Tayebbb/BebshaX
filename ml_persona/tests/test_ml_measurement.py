import importlib.util
from pathlib import Path

import pytest
from bebshax_persona_ml.model import PersonaModel


@pytest.fixture
def measurement_tool():
    path = Path(__file__).resolve().parents[1] / "tools/modernization_experiment.py"
    specification = importlib.util.spec_from_file_location("ml_measurement_tool", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.mark.parametrize("label", ["lexical", "reference"])
def test_measurement_evaluation_explicitly_uses_validation_and_new_report(
    measurement_tool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str,
) -> None:
    monkeypatch.setattr(measurement_tool, "ROOT", tmp_path)
    arguments = []
    monkeypatch.setattr(measurement_tool, "cli_step", lambda values: arguments.extend(values))
    output = tmp_path / "ml_persona/.verification/new/validation.json"

    measurement_tool.evaluate(tmp_path / "experiment-existing", label, report_path=output)

    assert arguments[arguments.index("--split") + 1] == "validation"
    assert arguments[arguments.index("--threads") + 1] == "2"
    assert arguments[arguments.index("--report") + 1] == output.relative_to(tmp_path).as_posix()
    assert "--force" not in arguments


def test_measurement_revalidation_refuses_fitting_and_preserves_existing_evidence(
    measurement_tool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(measurement_tool, "ROOT", tmp_path)
    directory = tmp_path / "experiment-frozen"
    directory.mkdir()
    saved = directory / "experiment.json"
    saved.write_bytes(b"historical experiment bytes")
    evaluated = []
    measured = []

    def evaluate(path, label, *, report_path):
        with pytest.raises(AssertionError, match="cannot retrain"):
            PersonaModel.fit([])
        evaluated.append((path, label, report_path))
        return {"response": {"result": {"model_version": label}}}

    def resources(path, label, *, verify_recorded_code, fresh_process):
        measured.append((label, verify_recorded_code, fresh_process))
        return {"model_version": label}

    monkeypatch.setattr(measurement_tool, "evaluate", evaluate)
    monkeypatch.setattr(measurement_tool, "resources", resources)
    output = tmp_path / "ml_persona/.verification/new"
    report = measurement_tool.revalidate(directory, output)

    assert report["training_performed"] is False
    assert report["test_split_evaluated"] is False
    assert report["experimental_files_unchanged"] is True
    assert saved.read_bytes() == b"historical experiment bytes"
    assert measured == [("lexical", False, False), ("reference", False, False)]
    assert evaluated == [(directory, label, output / f"{label}-validation.json")
                         for label in ("lexical", "reference")]


@pytest.mark.parametrize("defect", ["model_mismatch", "artifact_changed"])
def test_measurement_revalidation_rejects_inconsistent_evidence(
    measurement_tool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str,
) -> None:
    monkeypatch.setattr(measurement_tool, "ROOT", tmp_path)
    directory = tmp_path / "experiment-frozen"
    directory.mkdir()
    saved = directory / "experiment.json"
    saved.write_bytes(b"original")
    monkeypatch.setattr(measurement_tool, "evaluate", lambda path, label, **kwargs: {
        "response": {"result": {"model_version": label}},
    })

    def resources(path, label, **kwargs):
        if defect == "artifact_changed":
            saved.write_bytes(b"changed by the test")
        return {"model_version": "wrong" if defect == "model_mismatch" else label}

    monkeypatch.setattr(measurement_tool, "resources", resources)
    with pytest.raises(ValueError, match="different models|changed the frozen"):
        measurement_tool.revalidate(directory, tmp_path / "new-reports")