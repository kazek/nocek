"""A library: a folder holding the recordings and the database that describes them.

Everything the user owns lives in one folder they chose, so it can be backed
up or moved as a whole. Model weights are not part of it; they can always be
downloaded again.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path, PurePosixPath

from nyctalus.storage import database
from nyctalus.storage.repository import Repository

DATABASE = "nyctalus.sqlite"
RECORDINGS = "recordings"


class LibraryError(Exception):
    """A folder that cannot be created or opened as a library."""


class Library:
    def __init__(self, root: Path, shared: bool = False) -> None:
        self.root = root
        self.recordings_dir = root / RECORDINGS
        self.conn = database.connect(root / DATABASE, shared=shared)
        self.repository = Repository(self.conn)

    @classmethod
    def create(cls, root: Path, shared: bool = False) -> Library:
        """A new library in an empty or missing folder."""
        if (root / DATABASE).exists():
            raise LibraryError(f"{root} is already a library")
        root.mkdir(parents=True, exist_ok=True)
        (root / RECORDINGS).mkdir(exist_ok=True)
        return cls(root, shared)

    @classmethod
    def open(cls, root: Path, shared: bool = False) -> Library:
        if not (root / DATABASE).is_file():
            raise LibraryError(f"{root} is not a library: {DATABASE} is missing")
        try:
            return cls(root, shared)
        except (database.DatabaseError, sqlite3.DatabaseError) as error:
            raise LibraryError(f"{root}: {error}") from error

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Library:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def path_of(self, relative: PurePosixPath) -> Path:
        """A recording's file on disk, from its path inside the library."""
        return self.recordings_dir.joinpath(*relative.parts)

    def relative(self, path: Path) -> PurePosixPath:
        """A file inside the recordings folder, as stored in the database."""
        return PurePosixPath(path.relative_to(self.recordings_dir).as_posix())

    def delete_recording(self, recording_id: int) -> None:
        """Remove a recording from the database and its file from the library."""
        recording = self.repository.recording(recording_id)
        if recording is None:
            return
        self.repository.delete_recording(recording_id)
        self.path_of(recording.path).unlink(missing_ok=True)
