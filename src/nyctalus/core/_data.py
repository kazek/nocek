"""Data files shipped inside the package."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load_json(name: str) -> Any:
    """A JSON file from ``nyctalus/core/data``."""
    path = resources.files("nyctalus.core").joinpath("data").joinpath(name)
    return json.loads(path.read_text("utf-8"))
