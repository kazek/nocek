"""The SQLite database inside a library, and its migrations.

Migrations are the numbered SQL files in storage/migrations, applied in order
and each in its own transaction. The number of the last one applied is the
database's user_version, so opening a database brings it up to date, and a
database written by a newer version of the application is refused rather
than misread.
"""

from __future__ import annotations

import re
import sqlite3
from importlib import resources
from pathlib import Path


class DatabaseError(Exception):
    """A database this version of the application cannot use."""


def connect(path: Path, shared: bool = False) -> sqlite3.Connection:
    """Open, and migrate, the database at path.

    A shared connection may be used from several threads; the caller must
    then make sure only one uses it at a time.
    """
    # isolation_level=None: transactions are begun and ended explicitly by the
    # repository, never implicitly by the driver.
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=not shared)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Lets the interface read while an analysis is writing.
    conn.execute("PRAGMA journal_mode = WAL")
    # A write that meets another connection's write waits for it instead of
    # failing at once: the server and the worker share the database.
    conn.execute("PRAGMA busy_timeout = 5000")
    migrate(conn)
    return conn


def migrations() -> list[tuple[int, str]]:
    """(number, SQL) for every migration, in order."""
    folder = resources.files("nocek.storage").joinpath("migrations")
    found = []
    for entry in folder.iterdir():
        match = re.fullmatch(r"(\d{4})_.+\.sql", entry.name)
        if match:
            found.append((int(match.group(1)), entry.read_text("utf-8")))
    found.sort()
    if [n for n, _ in found] != list(range(1, len(found) + 1)):
        raise DatabaseError("migrations must be numbered 0001, 0002, ... without gaps")
    return found


def version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection) -> None:
    current, available = version(conn), migrations()
    latest = available[-1][0] if available else 0
    if current > latest:
        raise DatabaseError(
            f"the database is at version {current}, newer than this application ({latest})"
        )
    for number, sql in available:
        if number <= current:
            continue
        # executescript commits first; the explicit transaction keeps each
        # migration all or nothing.
        conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
