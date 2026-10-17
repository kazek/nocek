"""Where the application keeps its own files, and which library it opens.

The settings file and the model weights live in the platform's usual place
for application data (on macOS ~/Library/Application Support/Nyctalus, on
Windows %LOCALAPPDATA%\\Nyctalus, on Linux ~/.local/share/nyctalus). The
library is wherever the user chose to put it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP = "Nyctalus"


@dataclass(frozen=True)
class Settings:
    library: Path | None = None


def config_dir() -> Path:
    return Path(platformdirs.user_config_dir(APP, appauthor=False))


def models_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP, appauthor=False)) / "models"


def default_library() -> Path:
    return Path(platformdirs.user_documents_dir()) / APP


def load(path: Path | None = None) -> Settings:
    """The saved settings, or the defaults when nothing is saved yet."""
    path = path or config_dir() / "settings.json"
    if not path.is_file():
        return Settings()
    data = json.loads(path.read_text("utf-8"))
    return Settings(library=Path(data["library"]) if data.get("library") else None)


def save(settings: Settings, path: Path | None = None) -> None:
    """Write the settings beside their final name first, so a crash leaves the old ones."""
    path = path or config_dir() / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"library": str(settings.library) if settings.library else None}
    partial = path.with_name(path.name + ".part")
    partial.write_text(json.dumps(data, indent=2), "utf-8")
    partial.replace(path)
