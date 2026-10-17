import re
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nyctalus.core import consensus, opinion, pipeline, region, taxonomy
from nyctalus.recorders import base, checks
from nyctalus.storage import importer
from nyctalus.web import i18n, jobs

SOURCE = Path(i18n.__file__).parents[1]
ENGLISH = i18n.raw("en")

# Where each kind of code the backend sends finds its text.
SECTIONS: list[tuple[type[StrEnum], str]] = [
    (opinion.Abstention, "abstention"),
    (consensus.Note, "note"),
    (importer.Skip, "import.skip"),
    (importer.Notice, "import.notice"),
    (base.Problem, "import.problem"),
    (checks.Issue, "config_issue"),
    (jobs.Kind, "job.kind"),
    (jobs.Status, "job.status"),
    (jobs.Phase, "job.phase"),
    (region.Status, "status"),
    (pipeline.Pass, "recording.method"),
    (pipeline.Skipped, "recording.skipped"),
]


def section(data: dict[str, Any], dotted: str) -> dict[str, Any]:
    for part in dotted.split("."):
        data = data[part]
    return data


def error_codes() -> set[str]:
    """Every error code the source can send, found by reading it."""
    pattern = re.compile(r'(?:ApiError\(\d+, |JobError\(|error_response\(\d+, |error=)"([a-z-]+)"')
    codes = set()
    for path in SOURCE.rglob("*.py"):
        codes |= set(pattern.findall(path.read_text("utf-8")))
    return codes


def keys(data: dict[str, Any], prefix: str = "") -> Iterator[str]:
    for key, value in data.items():
        if isinstance(value, dict) and "other" not in value:
            yield from keys(value, f"{prefix}{key}.")
        else:
            yield prefix + key


@pytest.mark.parametrize(("codes", "where"), SECTIONS, ids=[w for _, w in SECTIONS])
def test_every_code_has_an_english_text(codes: type[StrEnum], where: str) -> None:
    assert {str(c) for c in codes} <= section(ENGLISH, where).keys()


def test_every_error_has_an_english_text() -> None:
    found = error_codes()

    assert len(found) > 20  # the search itself works
    assert found <= ENGLISH["error"].keys()


def test_every_taxon_has_an_english_name() -> None:
    assert {t.name for t in taxonomy.species()} <= ENGLISH["species"].keys()
    assert {t.name for t in taxonomy.genera()} <= ENGLISH["genus"].keys()


def test_plural_forms_always_include_other() -> None:
    for language in i18n.available():
        for value in _values(i18n.raw(language)):
            if isinstance(value, dict):
                assert "other" in value


@pytest.mark.parametrize("language", [lang for lang in i18n.available() if lang != "en"])
def test_translations_use_only_english_keys_and_placeholders(language: str) -> None:
    translated = i18n.raw(language)

    assert set(keys(translated)) <= set(keys(ENGLISH))
    for key in keys(translated):
        english, other = _at(ENGLISH, key), _at(translated, key)
        assert _placeholders(other) == _placeholders(english), key


def test_a_missing_translation_falls_back_to_english(monkeypatch: pytest.MonkeyPatch) -> None:
    partial = {"language": {"name": "Polski"}, "job": {"status": {"done": "Gotowe"}}}
    monkeypatch.setattr(i18n, "available", lambda: ("en", "pl"))
    monkeypatch.setattr(i18n, "raw", lambda lang: ENGLISH if lang == "en" else partial)

    polish = i18n.texts("pl")

    assert polish["job"]["status"]["done"] == "Gotowe"
    assert polish["job"]["status"]["failed"] == "Failed"
    assert polish["species"]["Nyctalus noctula"] == "Common noctule"
    assert i18n.names() == {"en": "English", "pl": "Polski"}


@pytest.mark.parametrize(
    ("setting", "header", "chosen"),
    [
        ("pl", "de-DE,de;q=0.9", "pl"),  # the user's choice wins
        (None, "pl-PL,pl;q=0.9,en;q=0.8", "pl"),
        (None, "fr-FR,fr;q=0.9,de;q=0.8", "de"),
        (None, "de;q=0.2,pl;q=0.8", "pl"),  # by quality, not by order
        (None, "pl;q=0", "en"),  # q=0 means not wanted
        (None, "*", "en"),
        (None, None, "en"),
        ("xx", "nonsense;;;", "en"),
    ],
)
def test_chooses_a_language(
    monkeypatch: pytest.MonkeyPatch, setting: str | None, header: str | None, chosen: str
) -> None:
    monkeypatch.setattr(i18n, "available", lambda: ("de", "en", "pl"))

    assert i18n.choose(setting, header) == chosen


def test_the_api_serves_languages(client: TestClient) -> None:
    listing = client.get("/api/locales", headers={"accept-language": "en-GB"}).json()

    assert listing == {"available": {"en": "English"}, "chosen": "en"}
    assert client.get("/api/locales/en").json()["species"]["Nyctalus noctula"] == "Common noctule"
    assert client.get("/api/locales/xx").json()["error"] == "no-such-language"


def _values(data: dict[str, Any]) -> Iterator[Any]:
    for value in data.values():
        if isinstance(value, dict) and "other" not in value:
            yield from _values(value)
        else:
            yield value


def _at(data: dict[str, Any], dotted: str) -> Any:
    for part in dotted.split("."):
        data = data[part]
    return data


def _placeholders(value: Any) -> set[str]:
    texts = value.values() if isinstance(value, dict) else [value]
    return {p for t in texts for p in re.findall(r"\{(\w+)\}", t)}


def test_every_text_the_page_asks_for_exists() -> None:
    static = SOURCE / "web" / "static"
    pattern = re.compile(r"""\bt\(\s*["']([\w.-]+)["']""")
    wanted = {key for js in static.rglob("*.js") for key in pattern.findall(js.read_text("utf-8"))}
    wanted |= set(re.findall(r'data-text="([\w.-]+)"', (static / "index.html").read_text("utf-8")))

    assert len(wanted) > 20  # the search itself works
    missing = {key for key in wanted if _find(ENGLISH, key) is None}
    assert missing == set()


def _find(data: dict[str, Any], dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def test_every_sound_battybirdnet_can_report_has_a_text() -> None:
    from nyctalus.core import battybird

    sounds = {label for head in battybird.heads().values() for label in head.not_a_bat}
    assert sounds <= ENGLISH["recording"]["sound"].keys()
