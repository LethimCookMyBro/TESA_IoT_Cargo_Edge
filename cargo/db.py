"""PostgreSQL connection settings and the versioned migration runner.

Credentials come from the environment only. Nothing here is ever sent to a browser: the dashboard
talks to the read-only history API, never to this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database: str
    user: str
    password: str

    @property
    def conninfo(self) -> str:
        from psycopg.conninfo import make_conninfo

        return make_conninfo(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
        )

    def redacted(self) -> str:
        """Safe to log or return from an API: identifies the database without leaking the password."""
        return f"postgresql://{self.user}@{self.host}:{self.port}/{self.database}"


def settings_from_env(*, database: str | None = None) -> Settings:
    """Read connection settings. These are the variables `.env.example` documents."""
    return Settings(
        host=os.environ.get("CARGOSHIELD_PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("CARGOSHIELD_PG_PORT", "5433")),
        database=database or os.environ.get("CARGOSHIELD_PG_DATABASE", "cargoshield"),
        user=os.environ.get("CARGOSHIELD_PG_USER", "cargoshield"),
        password=os.environ.get("CARGOSHIELD_PG_PASSWORD", "cargoshield-local-dev"),
    )


def readonly_settings_from_env() -> Settings:
    """Credentials for the SELECT-only role the maintenance copilot uses."""
    base = settings_from_env()
    return Settings(
        host=base.host, port=base.port, database=base.database,
        user=os.environ.get("CARGOSHIELD_PG_READONLY_USER", "cargoshield_readonly"),
        password=os.environ.get("CARGOSHIELD_PG_READONLY_PASSWORD", "cargoshield-readonly-local"),
    )


def ensure_readonly_role(settings: Settings | None = None, readonly: Settings | None = None) -> str:
    """Create or update the SELECT-only role. The boundary is enforced by PostgreSQL, not by hope.

    Done in Python rather than in a migration file so the password comes from the environment and
    is never committed. Safe to run repeatedly.
    """
    import psycopg
    from psycopg import sql

    owner, reader = settings or settings_from_env(), readonly or readonly_settings_from_env()
    role = sql.Identifier(reader.user)
    with connect(owner) as connection:
        connection.autocommit = True
        exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (reader.user,)).fetchone()
        statement = sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}") if exists else \
            sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}")
        connection.execute(statement.format(role, sql.Literal(reader.password)))
        connection.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(owner.database), role))
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        connection.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(role))
        # Explicitly take away everything else, including on tables added by later migrations.
        connection.execute(sql.SQL("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM {}").format(role))
        connection.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}").format(role))
        connection.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {}").format(role))
        connection.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE INSERT, UPDATE, DELETE ON TABLES FROM {}").format(role))
    return reader.user


def connect(settings: Settings | None = None, **kwargs):
    """Open one connection. Import is local so the whole project runs without psycopg installed."""
    import psycopg

    return psycopg.connect((settings or settings_from_env()).conninfo, **kwargs)


def available(settings: Settings | None = None) -> tuple[bool, str]:
    """Is the historian reachable? Returns (ok, reason). Never raises — callers use it to degrade."""
    try:
        import psycopg  # noqa: F401
    except ImportError as exc:
        return False, f"psycopg is not installed: {exc}"
    try:
        with connect(settings, connect_timeout=3) as connection:
            connection.execute("SELECT 1")
        return True, "reachable"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def migrate(settings: Settings | None = None, *, migrations_dir: Path | None = None) -> list[str]:
    """Apply every unapplied migration in filename order. Returns the versions applied this run.

    Repeatable by construction: applied versions are recorded, and each file is itself written with
    guarded statements, so running this twice is a no-op the second time.
    """
    directory = migrations_dir or MIGRATIONS_DIR
    applied: list[str] = []
    with connect(settings) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version text PRIMARY KEY,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
        connection.commit()
        done = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        for path in sorted(directory.glob("*.sql")):
            version = path.stem
            if version in done:
                continue
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            connection.commit()
            applied.append(version)
    return applied


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Apply CargoShield historian migrations")
    parser.add_argument("--check", action="store_true", help="only report reachability, change nothing")
    args = parser.parse_args()

    settings = settings_from_env()
    ok, reason = available(settings)
    if args.check or not ok:
        print(json.dumps({"database": settings.redacted(), "reachable": ok, "reason": reason}, indent=2))
        raise SystemExit(0 if ok else 1)
    applied = migrate(settings)
    # The read-only role is refreshed after every migration so tables added later are covered too.
    role = ensure_readonly_role(settings)
    print(json.dumps({"database": settings.redacted(), "applied": applied, "readonly_role": role}, indent=2))


if __name__ == "__main__":
    main()
