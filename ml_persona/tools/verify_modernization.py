"""Run explicitly scoped local tests with isolated, non-overwriting evidence."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import os
import sys
import time
import uuid
import xml.etree.ElementTree as element_tree
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
NUMERICAL_VERSIONS = {"numpy": "2.5.2", "scipy": "1.18.1", "scikit-learn": "1.9.0"}
THREAD_VARIABLES = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
)


def memory_bytes() -> dict[str, int | str | None]:
    if sys.platform != "win32":
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {"rss_bytes": None, "peak_rss_bytes": peak * (1 if sys.platform == "darwin" else 1024),
                "method": "getrusage self high-water mark"}

    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    get_process = ctypes.WinDLL("kernel32", use_last_error=True).GetCurrentProcess
    get_process.restype = wintypes.HANDLE
    get_memory = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
    get_memory.restype = wintypes.BOOL
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not get_memory(get_process(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"rss_bytes": counters.WorkingSetSize, "peak_rss_bytes": counters.PeakWorkingSetSize,
            "method": "GetProcessMemoryInfo current-process working set"}


def frozen_snapshot() -> dict[str, str]:
    directory = ROOT / "data/processed/ml_persona"
    paths = [path for path in directory.glob("*") if path.is_file()]
    paths.extend(path for path in (directory / "model").glob("*") if path.is_file())
    result = {}
    for path in sorted(paths):
        with path.open("rb") as stream:
            result[path.relative_to(ROOT).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", required=True, choices=("ml", "model", "adapter", "runtime", "schema", "adapter-contracts", "api", "root"))
    parser.add_argument("--keyword")
    parser.add_argument("--coverage", action="store_true")
    arguments = parser.parse_args()
    if os.environ.get("PYTEST_ADDOPTS") or os.environ.get("PYTEST_PLUGINS"):
        parser.error("Unexpected pytest environment options; no test scope was executed")
    versions = {name: importlib.metadata.version(name) for name in NUMERICAL_VERSIONS}
    if versions != NUMERICAL_VERSIONS or sys.version_info[:2] != (3, 12):
        parser.error("Use the unchanged repository Python 3.12 and frozen numerical versions")
    if arguments.coverage and arguments.scope != "ml":
        parser.error("Coverage is restricted to the complete isolated ML scope")
    if arguments.scope == "api" and not arguments.keyword:
        parser.error("The read-only API contract scope requires an explicit test keyword")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]
    output = ROOT / "ml_persona/.verification" / run_id
    output.mkdir(parents=True, exist_ok=False)
    temporary = output / "tmp"
    temporary.mkdir()
    for name in THREAD_VARIABLES:
        os.environ[name] = "2"
    os.environ.update({"TEMP": str(temporary), "TMP": str(temporary),
                       "PYTHONDONTWRITEBYTECODE": "1", "COVERAGE_FILE": str(output / ".coverage")})
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT / "ml_persona")

    targets = {
        "ml": [ROOT / "ml_persona/tests"],
        "model": [ROOT / "ml_persona/tests/test_ml_model.py"],
        "adapter": [ROOT / "apps/backend/tests/persona/test_ml_backend_adapter.py"],
        "runtime": sorted((ROOT / "apps/backend/tests/persona").glob("test_ml_runtime_*.py")),
        "schema": [ROOT / "apps/backend/tests/persona/test_schema.py"],
        "adapter-contracts": [ROOT / "apps/backend/tests/persona/test_modernization_ml_contract.py"],
        "api": [ROOT / "apps/backend/tests/api/test_ml_persona_generation_contracts.py"],
        "root": sorted((ROOT / "tests/persona").glob("test_modernization_ml*.py")),
    }[arguments.scope]
    if not targets or any(not path.exists() for path in targets):
        parser.error("No tests exist in the requested approved scope")
    config = ROOT / ("apps/backend/pyproject.toml" if arguments.scope in {"adapter", "runtime", "schema", "adapter-contracts", "api"}
                     else "ml_persona/pyproject.toml")
    full_ml_suite = arguments.scope == "ml" and not arguments.keyword
    junit = output / "junit.xml"
    pytest_arguments = [*(str(path) for path in targets), "-c", str(config), "-q", "--tb=short", "--durations=5",
                        "--confcutdir", str(config.parent), "--basetemp", str(temporary / "pytest"),
                        "--junitxml", str(junit), "-o", f"cache_dir={output / 'pytest-cache'}"]
    if arguments.keyword:
        pytest_arguments.extend(["-k", arguments.keyword])
    if arguments.coverage:
        pytest_arguments.extend(["--cov=bebshax_persona_ml", "--cov-branch", "--cov-fail-under=80",
                                 "--cov-report=term", f"--cov-report=json:{output / 'coverage.json'}"])
    else:
        pytest_arguments.append("--no-cov")

    frozen_before = frozen_snapshot()
    baseline_memory = memory_bytes()
    started = time.perf_counter()
    print(json.dumps({"started_run_id": run_id, "scope": arguments.scope}), flush=True)
    try:
        import pytest

        with patch("pydantic_settings.sources.DotEnvSettingsSource._read_env_files", return_value={}):
            pytest_exit_code = int(pytest.main(pytest_arguments))
    except KeyboardInterrupt:
        pytest_exit_code = 130
    except (OSError, RuntimeError, ValueError, KeyError):
        pytest_exit_code = None
    exit_code = pytest_exit_code if pytest_exit_code is not None else 1
    seconds = time.perf_counter() - started
    measured_memory = memory_bytes()
    frozen_after = frozen_snapshot()
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    if junit.exists():
        for suite in element_tree.parse(junit).getroot().iter("testsuite"):
            for name in counts:
                counts[name] += int(suite.get(name, "0"))
    else:
        exit_code = exit_code or 1
    unchanged = frozen_before == frozen_after
    exit_code = exit_code if unchanged else 1
    report = {
        "scope": arguments.scope, "run_id": run_id, "python": sys.version.split()[0],
        "keyword": arguments.keyword, "full_ml_suite_requested": full_ml_suite,
        "numerical_versions": versions, "numerical_threads": 2,
        "launcher_command": [str(Path(sys.executable).relative_to(ROOT)), *sys.argv],
        "pytest_arguments": pytest_arguments, "pytest_exit_code": pytest_exit_code, "exit_code": exit_code,
        "wall_seconds": seconds, "junit": junit.relative_to(ROOT).as_posix(), "junit_available": junit.exists(), "counts": counts,
        "memory_before_pytest": baseline_memory, "memory_after_pytest": measured_memory,
        "frozen_files_before": frozen_before, "frozen_files_after": frozen_after,
        "frozen_files_unchanged": unchanged, "application_environment_overrides": [],
        "dotenv_file_loading": "disabled_for_isolated_tests",
    }
    report_path = output / "report.json"
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"report": report_path.relative_to(ROOT).as_posix(), "exit_code": exit_code,
                      "wall_seconds": seconds, "counts": counts, "frozen_files_unchanged": unchanged}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())