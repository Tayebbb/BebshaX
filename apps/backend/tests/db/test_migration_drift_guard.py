import pytest
from unittest.mock import patch, MagicMock


def test_check_migrations_current_raises_when_behind_head():
    """H6 regression guard: a DB behind head must fail loudly, not 500 later."""
    from bebshax.main import check_migrations_current

    with patch("bebshax.main.ScriptDirectory") as mock_script_dir, \
         patch("bebshax.main.create_engine") as mock_engine, \
         patch("bebshax.main.MigrationContext") as mock_ctx:
        mock_script_dir.from_config.return_value.get_heads.return_value = ["head_rev_abc"]
        mock_ctx.configure.return_value.get_current_heads.return_value = ["old_rev_xyz"]

        with pytest.raises(SystemExit):
            check_migrations_current("sqlite:///:memory:")


def test_check_migrations_current_passes_when_at_head():
    from bebshax.main import check_migrations_current

    with patch("bebshax.main.ScriptDirectory") as mock_script_dir, \
         patch("bebshax.main.create_engine") as mock_engine, \
         patch("bebshax.main.MigrationContext") as mock_ctx:
        mock_script_dir.from_config.return_value.get_heads.return_value = ["head_rev_abc"]
        mock_ctx.configure.return_value.get_current_heads.return_value = ["head_rev_abc"]

        check_migrations_current("sqlite:///:memory:")  # should not raise
