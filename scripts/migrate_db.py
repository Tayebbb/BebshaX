"""Plan or explicitly apply Alembic migrations to a confirmed direct PostgreSQL target."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops.artifacts import ArtifactError
from scripts.ops.recovery import DatabaseTarget, database_target


class MigrationArguments(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("Invalid migration arguments; use --help and URL variable names, never URL values")


def migration_target(
    variable: str, confirmation: str, environment: Mapping[str, str], *, allow_remote: bool = False,
) -> DatabaseTarget:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*_URL", variable) or not environment.get(variable):
        raise ValueError("An explicitly selected nonempty URL variable is required")
    target = database_target(environment[variable], confirmation, restore=False)
    if re.search(r"(?:^|[.-])(?:pooler|pgbouncer)(?:[.-]|$)", target.host) or target.port in {6432, 6543}:
        raise ValueError("Migrations require a direct connection, not a known transaction-pooler endpoint")
    if target.host not in {"localhost", "127.0.0.1", "::1"} and not allow_remote:
        raise ValueError("Remote migrations require separate --allow-remote-target approval")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = MigrationArguments(description=__doc__)
    parser.add_argument("--url-env", required=True, help="name of the process variable containing the direct PostgreSQL URL")
    parser.add_argument("--confirm-target", required=True, help="exact host:port/database; contains no credentials")
    parser.add_argument("--allow-remote-target", action="store_true")
    parser.add_argument("--apply", action="store_true", help="apply the single repository head; omitted means validation only")
    try:
        arguments = parser.parse_args(argv)
        target = migration_target(arguments.url_env, arguments.confirm_target, os.environ,
                                  allow_remote=arguments.allow_remote_target)
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy.engine import URL

        config = Config()
        config.set_main_option("script_location", str(ROOT / "apps/backend/alembic"))
        config.attributes["database_url"] = URL.create(
            "postgresql+asyncpg", username=target.username, password=target.password,
            host=target.host, port=target.port, database=target.database, query={"sslmode": target.sslmode},
        ).render_as_string(hide_password=False)
        if len(ScriptDirectory.from_config(config).get_heads()) != 1:
            raise ValueError("Migrations require exactly one reviewed repository head")
        if not arguments.apply:
            print("PASS: direct target and single head validated; no database connection or migrations applied")
            return 0
        command.upgrade(config, "head")
        print("PASS: the selected Alembic head was applied; no demo seeding or readiness certification")
        return 0
    except (ArtifactError, ValueError):
        print("Migration blocked: invalid arguments, target, TLS, approval or revision graph; see --help", file=sys.stderr)
    except Exception as error:
        print(f"Migration failed: {type(error).__name__}; database diagnostics are not printed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
