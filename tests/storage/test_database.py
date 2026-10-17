import sqlite3
from pathlib import Path

import pytest

from nocek.storage import database


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


def test_recordings_already_there_get_their_number(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "db.sqlite", isolation_level=None)
    first_number, first = database.migrations()[0]
    conn.executescript(f"{first}\nPRAGMA user_version = {first_number};")
    conn.execute("INSERT INTO device (id, kind, uid) VALUES (1, 'pippyg', 'x'), (2, 'other', 'y')")
    for i, (name, device) in enumerate(
        [("DEV_002_20260903_213000.wav", 1), ("rec.wav", 1), ("DEV_002_20260903_213000.wav", 2)]
    ):
        conn.execute(
            "INSERT INTO recording (sha256, path, file_name, size_bytes, device_id, added_at)"
            " VALUES (?, ?, ?, 1, ?, 'now')",
            (str(i), f"{i}/{name}", name, device),
        )

    database.migrate(conn)

    numbers = [r[0] for r in conn.execute("SELECT device_number FROM recording ORDER BY id")]
    assert numbers == [2, None, None]  # only pippyg's own names say a number


def test_a_number_already_at_one_site_stands_for_it(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "db.sqlite", isolation_level=None)
    first_number, first = database.migrations()[0]
    conn.executescript(f"{first}\nPRAGMA user_version = {first_number};")
    conn.execute("INSERT INTO device (id, kind, uid) VALUES (1, 'pippyg', 'x')")
    conn.execute(
        "INSERT INTO site (id, name, created_at) VALUES (1, 'Balcony', 'now'), (2, 'Garden', 'now')"
    )
    # 0: all at the balcony; 1: split between two sites; 2: one without a site.
    for i, (number, site) in enumerate([(0, 1), (0, 1), (1, 1), (1, 2), (2, 1), (2, None)]):
        name = f"DEV_00{number}_20260903_2130{i:02d}.wav"
        conn.execute(
            "INSERT INTO recording (sha256, path, file_name, size_bytes, device_id, site_id,"
            " added_at) VALUES (?, ?, ?, 1, 1, ?, 'now')",
            (str(i), name, name, site),
        )

    database.migrate(conn)

    assert conn.execute("SELECT device_number, site_id FROM site_number").fetchall() == [(0, 1)]
