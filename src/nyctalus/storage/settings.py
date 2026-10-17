"""Where the application keeps its own files, and how the user set it up.

The settings file, the access token and the model weights live in the
platform's usual place for application data (on macOS ~/Library/Application
Support/Nyctalus, on Windows %LOCALAPPDATA%\\Nyctalus, on Linux
~/.local/share/nyctalus). The library is wherever the user chose to put it.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import platformdirs

APP = "Nyctalus"

PASSES = ("key", "batdetect2", "battybirdnet")
DEVICES = ("auto", "cpu", "mps", "cuda")
LANGUAGE = re.compile(r"[a-z]{2,3}(-[A-Z]{2})?")


class SettingsError(ValueError):
    """A setting with a value the application does not accept."""


@dataclass(frozen=True)
class Settings:
    library: Path | None = None
    # None follows the browser's language.
    language: str | None = None
    passes: tuple[str, ...] = field(default=PASSES)
    sieve: bool = True
    # Where BatDetect2 runs; "auto" picks a GPU when there is one.
    device: str = "auto"

    def __post_init__(self) -> None:
        if self.language is not None and not LANGUAGE.fullmatch(self.language):
            raise SettingsError(f"language {self.language!r}")
        if not set(self.passes) <= set(PASSES):
            raise SettingsError(f"passes {self.passes!r}")
        if self.device not in DEVICES:
            raise SettingsError(f"device {self.device!r}")


def config_dir() -> Path:
    return Path(platformdirs.user_config_dir(APP, appauthor=False))


def models_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP, appauthor=False)) / "models"


def log_dir() -> Path:
    return Path(platformdirs.user_log_dir(APP, appauthor=False))


def default_library() -> Path:
    return Path(platformdirs.user_documents_dir()) / APP


def load(path: Path | None = None) -> Settings:
    """The saved settings, or the defaults for anything not saved yet."""
    path = path or config_dir() / "settings.json"
    if not path.is_file():
        return Settings()
    data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    defaults = Settings()
    return Settings(
        library=Path(data["library"]) if data.get("library") else None,
        language=data.get("language"),
        passes=tuple(data.get("passes", defaults.passes)),
        sieve=bool(data.get("sieve", defaults.sieve)),
        device=data.get("device", defaults.device),
    )


def save(settings: Settings, path: Path | None = None) -> None:
    """Write the settings beside their final name first, so a crash leaves the old ones."""
    path = path or config_dir() / "settings.json"
    data = {
        "library": str(settings.library) if settings.library else None,
        "language": settings.language,
        "passes": list(settings.passes),
        "sieve": settings.sieve,
        "device": settings.device,
    }
    _write(path, json.dumps(data, indent=2))


def token(path: Path | None = None) -> str:
    """The secret the browser must present to change anything, made once and kept.

    Kept rather than made per start, so a bookmarked page still works after
    the application restarts.
    """
    path = path or config_dir() / "token"
    if path.is_file():
        return path.read_text("utf-8").strip()
    value = secrets.token_urlsafe(32)
    _write(path, value)
    os.chmod(path, 0o600)
    return value


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_text(text, "utf-8")
    partial.replace(path)
