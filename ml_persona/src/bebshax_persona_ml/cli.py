"""JSON-only command line for the offline synthetic persona model lifecycle."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

from . import pipeline
from .data import fingerprint
from .model import BusinessContext, PersonaModel, Selection

COMMANDS = ("download", "prepare", "validate", "train", "evaluate", "generate", "smoke")
ERRORS = (OSError, ValueError, TypeError, KeyError, RuntimeError, ImportError, RecursionError, subprocess.SubprocessError)


class _UsageError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError("Invalid arguments; use --help for accepted options")


class _GenerationOptions(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    num_personas: int = Field(default=5, ge=1, le=50)
    seed: int = Field(default=42, ge=0, lt=2**32)
    threads: int = Field(default=2, ge=1, le=64)


def _parser() -> tuple[_Parser, dict[str, _Parser]]:
    common = _Parser(add_help=False, argument_default=argparse.SUPPRESS)
    common.add_argument("--root", type=Path, help="Explicit repository/data root; defaults to cwd")
    common.add_argument("--data-dir", type=Path, help="Prepared directory relative to root")
    common.add_argument("--model", type=Path, help="Model artifact directory relative to root")
    common.add_argument("--seed", type=int)
    common.add_argument("--threads", type=int)
    common.add_argument("--force", action="store_true", help="Explicitly allow replacing this command's outputs")
    common.add_argument("--help", "-h", action="store_true")
    parser = _Parser(prog="bebshax-persona-ml", parents=[common], add_help=False)
    subcommands = parser.add_subparsers(dest="command", parser_class=_Parser)
    command_parsers = {}
    for name in COMMANDS:
        subparser = subcommands.add_parser(name, parents=[common], add_help=False)
        command_parsers[name] = subparser
        if name == "prepare":
            subparser.add_argument("--output", type=Path, help="Prepared output directory; overrides --data-dir")
            subparser.add_argument("--validation-fraction", type=float, default=0.15)
            subparser.add_argument("--test-fraction", type=float, default=0.15)
        if name in ("train", "evaluate"):
            subparser.add_argument("--report", type=Path, help="Output JSON report path relative to root")
        if name == "train":
            subparser.add_argument("--config", type=Path, help="TrainingConfig JSON: model, topics, lexical_weights, threads")
            subparser.add_argument("--topics", type=int, nargs="+")
            subparser.add_argument("--lexical-weights", type=float, nargs="+")
        if name in ("generate", "smoke"):
            subparser.add_argument("--input", type=Path, help="Strict BusinessContext JSON; required for generate")
        if name == "smoke":
            subparser.add_argument("--backend", action="store_true", help="Also validate local backend persona conversions")
        if name == "generate":
            subparser.add_argument("--num-personas", type=int, default=5)
            subparser.add_argument("--output", type=Path, help="Optional structured JSON output file")
    return parser, command_parsers


def _error(error: BaseException) -> dict[str, str]:
    if isinstance(error, _UsageError):
        return {"code": "usage_error", "message": "Invalid arguments; use --help for accepted options."}
    if isinstance(error, FileNotFoundError):
        return {"code": "missing_input", "message": "A required local input or artifact is missing."}
    if isinstance(error, FileExistsError):
        return {"code": "output_exists", "message": "Output exists; choose another path or explicitly use --force."}
    if isinstance(error, (ValidationError, json.JSONDecodeError, UnicodeError, TypeError, KeyError)):
        return {"code": "invalid_input", "message": "Input JSON, schema, or configuration is invalid."}
    if isinstance(error, OSError):
        return {"code": "io_error", "message": "A local file could not be accessed safely."}
    if isinstance(error, ImportError):
        return {"code": "dependency_error", "message": "A required local dependency is unavailable."}
    return {"code": "lifecycle_error", "message": "Lifecycle validation failed; check local integrity, paths, and candidate eligibility."}


def _seed(arguments: argparse.Namespace) -> int:
    return 42 if arguments.seed is None else arguments.seed


def _threads(arguments: argparse.Namespace) -> int:
    return 2 if arguments.threads is None else arguments.threads


def _locations(arguments: argparse.Namespace) -> tuple[Path, Path, Path]:
    root = arguments.root.absolute()
    directory = pipeline.resolve_path(root, arguments.data_dir)
    return root, directory, pipeline.resolve_path(root, arguments.model or directory / "model")


def _training_config(arguments: argparse.Namespace) -> pipeline.TrainingConfig:
    value = pipeline.read_json(pipeline.resolve_path(arguments.root, arguments.config), 65536) if arguments.config else {}
    config = pipeline.TrainingConfig.model_validate(value)
    value = config.model_dump()
    for field in ("topics", "lexical_weights", "threads"):
        override = getattr(arguments, field)
        if override is not None:
            value[field] = override
    if arguments.seed is not None:
        value["model"]["seed"] = arguments.seed
    return pipeline.TrainingConfig.model_validate(value)


def _context(arguments: argparse.Namespace) -> BusinessContext:
    if arguments.input is not None:
        path = pipeline.resolve_path(arguments.root, arguments.input)
        return BusinessContext.model_validate(pipeline.read_json(path, 8 * 1024**2))
    if arguments.command == "generate":
        raise _UsageError("generate requires --input")
    return BusinessContext(description="Affordable food, bread recipes and cooking for students on a limited budget.")


def _persona(selection: Selection) -> dict[str, Any]:
    record = selection.record
    notes = ["Synthetic source prototype, NOT OBSERVED customer evidence.", *selection.warnings]
    if not record.name:
        notes.append("No source name established; source identifier retained without inventing a name.")
    return {
        "id": record.record_id, "synthetic": True,
        "identity": {"name": record.name or record.record_id, "description": record.description},
        "demographics": {field: getattr(record, field) for field in ("age", "occupation", "education", "location")
                         if getattr(record, field) not in (None, "")},
        "source": {"repo_id": record.source, "revision": record.revision, "record_id": record.record_id, "documents": record.documents},
        "provenance": {"kind": "synthetic_training_prototype", "observed": False, "evidence_status": "NOT_OBSERVED",
                       "record_sha256": fingerprint(record.model_dump(mode="json"))},
        "model": {"version": selection.model_version, "selection_score": selection.score, "topic": selection.topic,
                  "score_interpretation": "Retrieval similarity, not confidence, probability, or customer demand."},
        **{field: [{"text": text, "source_record_id": record.record_id, "evidence_status": "NOT_OBSERVED"}
                   for text in getattr(record, field)] for field in ("goals", "pain_points", "behaviors")},
        "warnings": notes,
    }


def _generate(arguments: argparse.Namespace, fitted: PersonaModel | None = None) -> dict[str, Any]:
    options = _GenerationOptions(num_personas=getattr(arguments, "num_personas", 5), seed=_seed(arguments), threads=_threads(arguments))
    context = _context(arguments)
    root, directory, model_path = _locations(arguments)
    model = fitted if fitted is not None else PersonaModel.load(model_path)
    with threadpool_limits(limits=options.threads), warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ConvergenceWarning)
        selections = model.generate(context, options.num_personas, seed=options.seed)
    personas = [_persona(Selection.model_validate(selection.model_dump(mode="json"), strict=True)) for selection in selections]
    result = {"schema_version": 1, "model_version": model.version, "seed": options.seed, "synthetic": True,
              "evidence_status": "NOT_OBSERVED", "personas": personas,
              "warnings": ["Synthetic source selection is not population truth or observed customer research.",
                           *dict.fromkeys(str(item.message) for item in captured)]}
    destination = getattr(arguments, "output", None)
    if destination is not None:
        target = pipeline.protect_output(root, directory, destination, {"files": {}}, model_path)
        pipeline._check(target.suffix == ".json" and target != pipeline.resolve_path(root, arguments.input),
                        "Output must be JSON and cannot overwrite the business input")
        pipeline._available([target], arguments.force)
        pipeline._write(target, pipeline._json_bytes(result), arguments.force)
    return result


def _check_backend_conversion(
    selection: Selection, generated: dict[str, Any], profile: dict[str, Any],
    draft: dict[str, Any], workflow: dict[str, Any], role_title: str,
) -> None:
    from bebshax.persona.schema import CLAIM_GROUPS
    from bebshax.personas.ml_adapter import _UNAVAILABLE_VALUE

    record = selection.record
    identity = {"name": record.name or f"Synthetic profile {record.record_id}", "age": record.age,
                "occupation": record.occupation, "location": record.location or _UNAVAILABLE_VALUE,
                "education": record.education or _UNAVAILABLE_VALUE, "income_range": _UNAVAILABLE_VALUE,
                "description": record.description, "personality": None}
    groups = (("goals", "goal", "Goals"), ("pain_points", "pain_point", "Pain Points"), ("behaviors", "behavior", "Behaviors"))
    claims = {group: [{"value": value, "provenance": "SYNTHETIC", "evidence_ids": []}
                      for value in getattr(record, group)] for group, _, _ in groups}
    provenance = {"source": record.source, "revision": record.revision, "record_id": record.record_id,
                  "model_version": selection.model_version, "selection_score": selection.score, "topic": selection.topic}
    generation_model = f"bebshax-persona-ml/{selection.model_version}"
    for converted in (generated, profile, workflow):
        pipeline._check({field: converted[field] for field in identity} == identity, "Backend changed source identity")
    for converted in (generated, profile, draft, workflow):
        details = converted["detailed_attributes"]
        pipeline._check(details["ml_provenance"] == provenance and details["source_documents"] == record.documents
                        and details["claim_provenance"] == claims
                        and set(selection.warnings).issubset(details["validation_warnings"]), "Backend changed source provenance")
    pipeline._check({group: generated[group] for group in CLAIM_GROUPS}
                    == {group: claims.get(group, []) for group in CLAIM_GROUPS}, "Backend fabricated claims or evidence")
    attributes = [{"key": key, "value": claim["value"], "provenance_class": "SYNTHETIC", "evidence_ids": [],
                   "confidence": None, "grounding_basis": None} for group, key, _ in groups for claim in claims[group]]
    pipeline._check(profile["attributes"] == attributes and profile["evidence"] == []
                    and profile["business_id"] == "ml-smoke" and profile["generation_model"] == generation_model
                    and set(selection.warnings).issubset(profile["warnings"]), "Backend profile lost synthetic provenance")
    demographics = {field: identity[field] for field in ("age", "occupation", "location", "education")}
    demographics["income_or_budget"] = identity["income_range"]
    for converted in (draft, workflow):
        pipeline._check(converted["name"] == identity["name"] and converted["bio"] == record.description
                        and converted["demographics"] == demographics
                        and all(converted[group] == getattr(record, group) for group, _, _ in groups), "Backend draft changed source identity")
        pipeline._check(converted["dataset_refs"] == [provenance] and converted["generation_model"] == generation_model
                        and converted["evidence_citations"] == [] and converted["grounding_score"] == 0.0
                        and converted["confidence"] == 0.0 and set(selection.warnings).issubset(converted["validation_warnings"]),
                        "Backend draft fabricated evidence or confidence")
    workflow_attributes = [{"category": category, "title": claim["value"], "provenance_class": "SYNTHETIC",
                            "evidence_ids": [], "evidence": None} for group, _, category in groups for claim in claims[group]]
    workflow_provenance = {"role_id": "ml-smoke", "role_title": role_title, "grounding_ratio": 0.0, "consistency_score": 0.0,
                           "grounding_basis": "synthetic_training_proxy", "evidence_claim_count": 0}
    pipeline._check(workflow["is_synthetic"] is True and workflow["attributes"] == workflow_attributes
                    and {field: workflow[field] for field in workflow_provenance} == workflow_provenance,
                    "Backend workflow lost synthetic provenance")


def _smoke_backend(arguments: argparse.Namespace) -> None:
    from bebshax.api.errors import APIError
    from bebshax.persona.schema import GeneratedPersona, PersonaProfile
    from bebshax.personas import ml_adapter
    from bebshax.personas.generator import GeneratedPersonaDraft

    options = _GenerationOptions(seed=_seed(arguments), threads=_threads(arguments))
    context = _context(arguments)
    _, _, model_path = _locations(arguments)
    adapter = ml_adapter.MLPersonaAdapter(model_path)
    try:
        with threadpool_limits(limits=options.threads), warnings.catch_warnings(record=True):
            selections = asyncio.run(adapter.generate(context, num_personas=5, seed=options.seed))
        pipeline._check(len(selections) == 5, "Backend smoke requires five selections")
        selections = [Selection.model_validate(selection.model_dump(warnings="error"), strict=True) for selection in selections]
        pipeline._check(len({selection.record.record_id for selection in selections}) == 5, "Backend repeated source identities")
        identifiers: dict[str, set[str]] = {"profile": set(), "workflow": set()}
        for selection in selections:
            generated = GeneratedPersona.model_validate(
                ml_adapter.to_generated_persona(selection).model_dump(warnings="error"), strict=True,
            ).model_dump(mode="json")
            profile = PersonaProfile.model_validate(
                ml_adapter.to_persona_profile(selection, "ml-smoke").model_dump(warnings="error"), strict=True,
            ).model_dump(mode="json")
            draft = GeneratedPersonaDraft.model_validate(
                ml_adapter.to_persona_draft(selection).model_dump(warnings="error"), strict=True,
            ).model_dump(mode="json")
            workflow = ml_adapter.to_workflow_persona(selection, role_id="ml-smoke", role_title=context.role)
            GeneratedPersonaDraft.model_validate(workflow, strict=True)
            _check_backend_conversion(selection, generated, profile, draft, workflow, context.role)
            for name, converted in (("profile", profile), ("workflow", workflow)):
                identifier = converted["id"]
                pipeline._check(isinstance(identifier, str) and bool(identifier.strip()) and identifier not in identifiers[name],
                                "Backend identifiers must be nonempty and unique")
                identifiers[name].add(identifier)
    except (APIError, AttributeError, IndexError) as error:
        raise ValueError("Backend smoke conversion failed") from error


def _smoke(arguments: argparse.Namespace) -> dict[str, Any]:
    root, directory, model_path = _locations(arguments)
    stages: list[dict[str, Any]] = []
    fitted = None
    names = ("source", "prepared", "model", "generation") + (("backend",) if arguments.backend else ())
    for name in names:
        try:
            if name == "source":
                preparation = pipeline._Preparation.model_validate(pipeline.read_json(pipeline.resolve_path(root, directory / "preparation.json")))
                for path in pipeline._source_paths(root, preparation.source).values():
                    if not path.is_file():
                        raise FileNotFoundError("Local source artifact is missing")
            elif name == "prepared":
                pipeline.validate(root, directory)
            elif name == "model":
                fitted = PersonaModel.load(model_path)
            elif name == "generation":
                result = _generate(arguments, fitted)
                pipeline._check(len(result["personas"]) == 5, "Smoke requires five structured selections")
            else:
                _smoke_backend(arguments)
            stages.append({"name": name, "ok": True})
        except ERRORS as error:
            stages.append({"name": name, "ok": False, "error": _error(error)})
    return {"stages": stages, "num_personas": 5}


def _dispatch(arguments: argparse.Namespace) -> dict[str, Any]:
    root, directory, model_path = _locations(arguments)
    if arguments.command == "download":
        script = pipeline.resolve_path(root, Path("scripts/setup_datasets.py"))
        pipeline._check(script.is_file(), "Root does not own the setup script")
        command = [sys.executable, str(script), "--profile", "ml_persona"]
        if arguments.force:
            command.append("--force")
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", check=False)
        pipeline._check(completed.returncode == 0, "Dataset setup failed")
        return {"profile": "ml_persona", "returncode": completed.returncode}
    if arguments.command == "prepare":
        return pipeline.prepare(root, arguments.output or directory, seed=_seed(arguments),
                                validation_fraction=arguments.validation_fraction, test_fraction=arguments.test_fraction, force=arguments.force)
    if arguments.command == "validate":
        return pipeline.validate(root, directory)
    if arguments.command == "train":
        if arguments.config is not None:
            config_path = pipeline.resolve_path(root, arguments.config)
            pipeline._check(not config_path.is_relative_to(model_path)
                            and (arguments.report is None or pipeline.resolve_path(root, arguments.report) != config_path),
                            "Outputs cannot overwrite the training configuration")
        return pipeline.train(root, directory, config=_training_config(arguments), model_path=model_path,
                              report_path=arguments.report, force=arguments.force)
    if arguments.command == "evaluate":
        return pipeline.evaluate(root, directory, model_path=model_path, report_path=arguments.report,
                                 seed=_seed(arguments), threads=_threads(arguments), force=arguments.force)
    if arguments.command == "generate":
        return _generate(arguments)
    return _smoke(arguments)


def main(argv: list[str] | None = None) -> int:
    command = None
    try:
        parser, command_parsers = _parser()
        arguments = parser.parse_args(argv, namespace=argparse.Namespace(
            root=Path.cwd(), data_dir=pipeline.DEFAULT_OUTPUT, model=None,
            seed=None, threads=None, force=False, help=False,
        ))
        command = arguments.command
        if arguments.help:
            result = {"usage": command_parsers.get(command, parser).format_help(), "commands": list(COMMANDS), "defaults": {
                "root": "cwd", "data_dir": pipeline.DEFAULT_OUTPUT.as_posix(), "model": "<data-dir>/model",
                "seed": 42, "training": pipeline.TrainingConfig().model_dump(),
            }}
        else:
            if command is None:
                raise _UsageError("A subcommand is required")
            result = _dispatch(arguments)
        ok = not (command == "smoke" and "stages" in result) or all(stage["ok"] for stage in result["stages"])
        response: dict[str, Any] = {"ok": ok, "command": command, "result": result}
        if not ok:
            response["error"] = {"code": "smoke_failed", "message": "One or more local smoke stages failed."}
        status = 0 if ok else 1
    except ERRORS as error:
        detail = _error(error)
        response = {"ok": False, "command": command, "error": detail}
        status = 2 if detail["code"] in ("usage_error", "invalid_input") else 1
    print(json.dumps(response, ensure_ascii=True, sort_keys=True, allow_nan=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())