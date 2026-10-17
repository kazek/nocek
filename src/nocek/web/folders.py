"""Browsing folders, so the user can point at a card or a library from the page.

A browser does not tell a page where a chosen folder is on disk. Where the
system's own dialog cannot be opened (dialog.py), the server lists folders
itself.
It lists folders only, never file contents, and counts the recordings in each.
"""

from __future__ import annotations

import os
import string
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Folder:
    name: str
    path: Path
    recordings: int  # .wav files directly inside


@dataclass(frozen=True)
class Listing:
    path: Path
    parent: Path | None
    folders: tuple[Folder, ...]
    recordings: int


def roots() -> list[Folder]:
    """Where browsing can start: the home folder and every mounted volume."""
    places = [Path.home()]
    if sys.platform == "win32":
        places += [Path(f"{d}:\\") for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    else:
        user = os.environ.get("USER", "")
        for base in (
            Path("/Volumes"),
            Path("/media") / user,
            Path("/run/media") / user,
            Path("/mnt"),
        ):
            if base.is_dir():
                places += sorted(p for p in _subfolders(base))
    return [Folder(p.name or str(p), p, _count(p)) for p in dict.fromkeys(places)]


def listing(path: Path, deep: bool = False) -> Listing:
    """The folders inside one folder. Raises NotADirectoryError or PermissionError.

    deep counts the recordings in every folder below this one too, as a
    recorder's card keeps them in a folder per hour.
    """
    if not path.is_absolute():
        raise NotADirectoryError(f"{path} is not an absolute path")
    if not path.is_dir():
        raise NotADirectoryError(str(path))
    folders = tuple(Folder(p.name, p, _count(p)) for p in sorted(_subfolders(path)))
    return Listing(
        path=path,
        parent=path.parent if path.parent != path else None,
        folders=folders,
        recordings=_count_deep(path) if deep else _count(path),
    )


def _subfolders(path: Path) -> list[Path]:
    out = []
    try:
        for entry in os.scandir(path):
            if not entry.name.startswith(".") and entry.is_dir(follow_symlinks=False):
                out.append(Path(entry.path))
    except PermissionError:
        pass
    return out


def _count(path: Path) -> int:
    try:
        return sum(
            1
            for e in os.scandir(path)
            if e.name.lower().endswith(".wav") and e.is_file(follow_symlinks=False)
        )
    except (PermissionError, FileNotFoundError, NotADirectoryError):
        return 0


def _count_deep(path: Path) -> int:
    total = 0
    for _, folders, files in os.walk(path, onerror=lambda _: None):
        folders[:] = [f for f in folders if not f.startswith(".")]  # never into hidden ones
        total += sum(1 for f in files if f.lower().endswith(".wav"))
    return total
