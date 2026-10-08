import os
import sqlite3
from pathlib import Path

MIGRATIONS = Path(__file__).parent / "migrations"


def database_path() -> str:
    return os.getenv("SOCIAL_STUDIO_DATABASE", "social_studio.sqlite3")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(database_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    path = database_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    with connect() as connection:
        applied = set()
        try:
            applied = {
                row[0]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
        except sqlite3.OperationalError:
            pass

        for migration in sorted(MIGRATIONS.glob("*.sql")):
            if migration.stem in applied:
                continue
            connection.executescript(migration.read_text())
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
                (migration.stem,),
            )
