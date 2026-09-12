import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from bebshax.config import Settings


@pytest.mark.parametrize("backend", ["auto", "ollama", "unknown"])
def test_removed_embedding_modes_are_rejected(backend):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embedding_backend=backend)


def test_remote_embeddings_require_a_pinned_model():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embedding_backend="freellmpool")
    settings = Settings(_env_file=None, embedding_backend="freellmpool", embedding_model="approved-model")
    assert settings.embedding_model == "approved-model"


def test_relative_provider_config_is_absolute_and_repository_anchored(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None, provider_config_path="providers.toml")
    assert settings.provider_config_path == Path(__file__).resolve().parents[3] / "providers.toml"
    assert settings.provider_config_path.is_absolute()
    assert Settings(_env_file=None).embedding_backend == "local"


def test_expected_ml_manifest_is_validated_and_immutable():
    settings = Settings(_env_file=None, ml_persona_manifest_sha256="a" * 64)
    expected = settings.expected_ml_persona_manifest
    assert expected.metadata_sha256 == "a" * 64
    with pytest.raises(ValidationError):
        expected.metadata_sha256 = "b" * 64
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ml_persona_manifest_sha256="not-a-digest")


def test_required_persona_feature_cannot_be_disabled():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ml_persona_enabled=False, ml_persona_required=True)


def test_config_import_does_not_read_dotenv_or_construct_settings():
    program = (
        "import dotenv; "
        "from pydantic_settings import DotEnvSettingsSource; "
        "from unittest.mock import Mock; "
        "dotenv.load_dotenv=Mock(side_effect=AssertionError('import read dotenv')); "
        "DotEnvSettingsSource._read_env_files=Mock(side_effect=AssertionError('import built settings')); "
        "import bebshax.config; "
        "assert not hasattr(bebshax.config, 'settings')"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        env={"SystemRoot": os.environ.get("SystemRoot", "C:/Windows")},
        cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True,
    )
    assert result.returncode == 0, "config import performed settings or dotenv work"