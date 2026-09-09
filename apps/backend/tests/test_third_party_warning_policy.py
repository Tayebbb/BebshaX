"""Regression tests for the backend's third-party warning exemptions."""

import subprocess
import sys
from pathlib import Path

import pytest


ANYIO_ALIAS_WARNING = (
    "The anyio.abc.BlockingPortal alias is deprecated, "
    "use anyio.from_thread.BlockingPortal instead."
)


@pytest.mark.parametrize(
    ("message", "expected_exit_code"),
    [
        pytest.param(
            ANYIO_ALIAS_WARNING,
            pytest.ExitCode.OK,
            id="known-anyio-alias-is-ignored",
        ),
        pytest.param(
            "An unrelated API is deprecated.",
            pytest.ExitCode.TESTS_FAILED,
            id="unrelated-deprecation-is-fatal",
        ),
        pytest.param(
            f"{ANYIO_ALIAS_WARNING} Additional warning details.",
            pytest.ExitCode.TESTS_FAILED,
            id="alias-message-with-suffix-is-fatal",
        ),
    ],
)
def test_pytest_enforces_third_party_warning_policy(
    tmp_path: Path, message: str, expected_exit_code: pytest.ExitCode
) -> None:
    probe_file = tmp_path / "test_warning_probe.py"
    probe_file.write_text(
        "import warnings\n\n"
        "def test_warning():\n"
        f"    warnings.warn({message!r}, DeprecationWarning)\n",
        encoding="utf-8",
    )
    backend_config = Path(__file__).resolve().parents[1] / "pyproject.toml"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(backend_config),
            str(probe_file),
            "--noconftest",
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = result.stdout + result.stderr

    assert result.returncode == expected_exit_code, output
    if expected_exit_code == pytest.ExitCode.OK:
        assert "1 passed" in output, output
        assert "DeprecationWarning" not in output, output
    else:
        assert f"DeprecationWarning: {message}" in output, output