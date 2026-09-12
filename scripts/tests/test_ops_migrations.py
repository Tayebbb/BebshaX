import contextlib
import io
import os
import unittest
from unittest.mock import patch

from sqlalchemy.engine import make_url

from scripts.migrate_db import main, migration_target
from scripts.ops.artifacts import ArtifactError


class MigrationPolicyTests(unittest.TestCase):
    variable = "BEBSHAX_MIGRATION_DATABASE_URL"
    local = "postgresql://fixture:synthetic-sentinel@127.0.0.1:5433/ops_fixture"

    def arguments(self) -> list[str]:
        return ["--url-env", self.variable, "--confirm-target", "127.0.0.1:5433/ops_fixture"]

    def test_no_default_database_or_raw_url_argument_is_accepted(self) -> None:
        for arguments in ([], ["--url", self.local]):
            with self.subTest(arguments=arguments[:1]), contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(main(arguments), 1)
                self.assertNotIn("synthetic-sentinel", output.getvalue())

    def test_empty_variable_and_mismatched_target_are_rejected(self) -> None:
        for environment, confirmation in (({}, "127.0.0.1:5433/ops_fixture"),
                                         ({self.variable: self.local}, "127.0.0.1:5433/another_database")):
            with self.subTest(confirmation=confirmation), self.assertRaises((ArtifactError, ValueError)):
                migration_target(self.variable, confirmation, environment)

    def test_known_poolers_are_rejected_even_with_remote_approval(self) -> None:
        for host, port in (("ep-fixture-pooler.example.test", 5432), ("pooler.example.test", 5432),
                           ("db.example.test", 6432), ("db.example.test", 6543)):
            url = f"postgresql://fixture:synthetic-sentinel@{host}:{port}/ops_fixture?sslmode=verify-full"
            with self.subTest(host=host, port=port), self.assertRaises(ValueError):
                migration_target(self.variable, f"{host}:{port}/ops_fixture", {self.variable: url}, allow_remote=True)

    def test_remote_target_requires_separate_approval_and_verified_tls(self) -> None:
        origin = "postgresql://fixture:synthetic-sentinel@db.example.test/ops_fixture"
        for suffix, consent in (("?sslmode=verify-full", False), ("?sslmode=require", True),
                                ("?sslmode=disable", True), ("?sslmode=verify-ca", True)):
            with self.subTest(tls=suffix, consent=consent), self.assertRaises((ArtifactError, ValueError)):
                migration_target(self.variable, "db.example.test:5432/ops_fixture",
                                 {self.variable: origin + suffix}, allow_remote=consent)
        target = migration_target(self.variable, "db.example.test:5432/ops_fixture",
                                  {self.variable: origin}, allow_remote=True)
        self.assertEqual(target.sslmode, "verify-full")

    def test_validated_plan_never_connects_or_applies_migrations(self) -> None:
        with patch.dict(os.environ, {self.variable: self.local}, clear=True), \
                patch("alembic.script.ScriptDirectory.from_config") as scripts, \
                patch("alembic.command.upgrade") as upgrade, contextlib.redirect_stdout(io.StringIO()) as output:
            scripts.return_value.get_heads.return_value = ["fixture_head"]
            self.assertEqual(main(self.arguments()), 0)
            upgrade.assert_not_called()
            self.assertIn("no database connection", output.getvalue())
            self.assertNotIn("synthetic-sentinel", output.getvalue())

    def test_apply_supplies_explicit_url_to_alembic_without_settings_or_seeding(self) -> None:
        with patch.dict(os.environ, {self.variable: self.local}, clear=True), \
                patch("alembic.script.ScriptDirectory.from_config") as scripts, \
                patch("alembic.command.upgrade") as upgrade, contextlib.redirect_stdout(io.StringIO()) as output:
            scripts.return_value.get_heads.return_value = ["fixture_head"]
            self.assertEqual(main([*self.arguments(), "--apply"]), 0)
            upgrade.assert_called_once()
            configuration, revision = upgrade.call_args.args
            self.assertIsNone(configuration.config_file_name)
            self.assertEqual(revision, "head")
            url = make_url(configuration.attributes["database_url"])
            self.assertEqual(url.host, "127.0.0.1")
            self.assertEqual(url.password, "synthetic-sentinel")
            self.assertNotIn("synthetic-sentinel", output.getvalue())

    def test_multiple_heads_block_before_apply_and_errors_hide_database_values(self) -> None:
        with patch.dict(os.environ, {self.variable: self.local}, clear=True), \
                patch("alembic.script.ScriptDirectory.from_config") as scripts, \
                patch("alembic.command.upgrade") as upgrade, contextlib.redirect_stderr(io.StringIO()) as output:
            scripts.return_value.get_heads.return_value = ["first", "second"]
            self.assertEqual(main([*self.arguments(), "--apply"]), 1)
            upgrade.assert_not_called()
            scripts.return_value.get_heads.return_value = ["fixture_head"]
            upgrade.side_effect = RuntimeError("synthetic-sentinel")
            self.assertEqual(main([*self.arguments(), "--apply"]), 1)
            self.assertNotIn("synthetic-sentinel", output.getvalue())


if __name__ == "__main__":
    unittest.main()