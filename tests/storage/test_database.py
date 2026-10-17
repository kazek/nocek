import sqlite3
from pathlib import Path

import pytest

from nyctalus.storage import database


def test_a_new_database_gets_every_migration(tmp_path: Path) -> None:
    conn = database.connect(tmp_path / "db.sqlite")

    latest = database.migrations()[-1][0]
    assert database.version(conn) == latest
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"site", "device", "recording", "result", "source_verdict"} <= tables


def test_reopening_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    database.connect(path).close()

    conn = database.connect(path)

    assert database.version(conn) == database.migrations()[-1][0]


def test_uses_wal_and_foreign_keys(tmp_path: Path) -> None:
    conn = database.connect(tmp_path / "db.sqlite")

    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_refuses_a_database_from_a_newer_version(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 999")
    conn.close()

    with pytest.raises(database.DatabaseError, match="newer"):
        database.connect(path)


def test_migrations_are_numbered_without_gaps() -> None:
    numbers = [n for n, _ in database.migrations()]

    assert numbers == list(range(1, len(numbers) + 1))
