"""The interface's texts in each language.

Every text lives in web/locales/<language>.json, English being the complete
one the others are checked against; a text missing from a translation falls
back to English rather than showing a key. A value is either a string, with
{name} or {0} placeholders, or an object of plural forms (one, few, many,
other, ...) for the browser's Intl.PluralRules to choose from.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

FOLDER = Path(__file__).parent / "locales"
SOURCE = "en"
# The plural categories Intl.PluralRules can name; an object of these is one text.
PLURAL_FORMS = frozenset({"zero", "one", "two", "few", "many", "other"})


@cache
def available() -> tuple[str, ...]:
    return tuple(sorted(p.stem for p in FOLDER.glob("*.json")))


@cache
def raw(language: str) -> dict[str, Any]:
    """One language's file as written, without the English fallback."""
    if language not in available():
        raise KeyError(language)
    data: dict[str, Any] = json.loads((FOLDER / f"{language}.json").read_text("utf-8"))
    return data


def texts(language: str) -> dict[str, Any]:
    """A language's texts, with English for anything it does not translate."""
    return _merge(raw(SOURCE), raw(language))


def names() -> dict[str, str]:
    """Each available language in its own name."""
    return {lang: str(raw(lang).get("language", {}).get("name", lang)) for lang in available()}


def choose(setting: str | None, accept_language: str | None) -> str:
    """The language to show: the user's choice, else the browser's, else English."""
    if setting and setting in available():
        return setting
    for wanted in _preferences(accept_language or ""):
        primary = wanted.split("-")[0].lower()
        if primary in available():
            return primary
    return SOURCE


def _preferences(header: str) -> list[str]:
    """An Accept-Language header's languages, most wanted first."""
    ranked = []
    for position, part in enumerate(header.split(",")):
        tag, _, params = part.strip().partition(";")
        quality = 1.0
        if params.strip().startswith("q="):
            try:
                quality = float(params.strip()[2:])
            except ValueError:
                quality = 0.0
        if tag and tag != "*" and quality > 0:
            ranked.append((-quality, position, tag))
    return [tag for _, _, tag in sorted(ranked)]


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict) and not plural(base[key]):
            out[key] = _merge(base[key], value)
        else:
            out[key] = value
    return out


def plural(value: Any) -> bool:
    """Whether a value is one text in plural forms rather than a section of texts."""
    return (
        isinstance(value, dict)
        and "other" in value
        and value.keys() <= PLURAL_FORMS
        and all(isinstance(v, str) for v in value.values())
    )
