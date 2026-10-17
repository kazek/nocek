from datetime import date, datetime
from pathlib import Path, PurePosixPath

import pytest

from nocek.core.batdetect import interpret
from nocek.core.consensus import combine
from nocek.core.pipeline import RecordingResult
from nocek.core.region import Region
from nocek.core.taxonomy import Taxon
from nocek.storage import database
from nocek.storage.repository import Repository
from nocek.storage.summaries import Filter, device_use, totals
from tests.core.factories import calls, measured

NOCTULE = frozenset({Taxon("Nyctalus noctula")})
PIPISTRELLE = frozenset({Taxon("Pipistrellus pipistrellus")})


def result(*sources: tuple[str, float, float], pulses: int = 10) -> RecordingResult:
    """A result whose BatDetect2 sources are (class, low kHz, best probability)."""
    found = interpret([c for cls, low, prob in sources for c in calls(cls, low, prob=prob)])
    return RecordingResult(
        path=Path("x.wav"),
        versions={},
        batdetect=found,
        verdict=combine(Region("anywhere"), found, measured(end_khz=20, n_pulses=pulses)),
    )


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    """Three nights, two sites.

    Night of 1 Sept, site A: a noctule; a noctule and a pipistrelle (after midnight).
    Night of 2 Sept, site A: a noctule the detector did not confirm; a quiet recording.
    Night of 3 Sept, site B: a pipistrelle.
    """
    repo = Repository(database.connect(tmp_path / "db.sqlite"))
    a, b = repo.add_site("A").id, repo.add_site("B").id
    recordings = [
        (a, datetime(2026, 9, 1, 21, 0), result(("Nyctalus noctula", 20, 0.8))),
        (
            a,
            datetime(2026, 9, 2, 1, 30),
            result(("Nyctalus noctula", 20, 0.9), ("Pipistrellus pipistrellus", 45, 0.7)),
        ),
        (a, datetime(2026, 9, 2, 22, 0), result(("Nyctalus noctula", 20, 0.95), pulses=1)),
        (a, datetime(2026, 9, 2, 23, 0), None),
        (b, datetime(2026, 9, 3, 20, 0), result(("Pipistrellus pipistrellus", 45, 0.6))),
    ]
    for i, (site, at, r) in enumerate(recordings):
        rec = repo.add_recording(
            f"{i:064d}", PurePosixPath(f"{i}.wav"), 1000, recorded_at=at, site_id=site
        )
        if r is not None:
            repo.save_result(rec.id, r)
    return repo


def test_counts_recordings_and_nights_per_species(repo: Repository) -> None:
    t = totals(repo.conn)

    by_taxa = {s.taxa: s for s in t.species}
    assert by_taxa[NOCTULE].recordings == 2
    assert by_taxa[NOCTULE].nights == 1
    assert by_taxa[PIPISTRELLE].recordings == 2
    assert by_taxa[PIPISTRELLE].nights == 2
    assert (by_taxa[PIPISTRELLE].first_night, by_taxa[PIPISTRELLE].last_night) == (
        date(2026, 9, 1),
        date(2026, 9, 3),
    )


def test_a_withheld_name_still_counts_as_a_recording_with_calls(repo: Repository) -> None:
    t = totals(repo.conn)

    assert (t.recordings, t.analysed, t.with_calls, t.nights) == (5, 4, 4, 3)
    # The unconfirmed noctule's 0.95 is not the species' best.
    assert {s.taxa: s.best_score for s in t.species}[NOCTULE] == pytest.approx(0.9)


def test_filters_by_site(repo: Repository) -> None:
    b = next(s for s in repo.sites() if s.name == "B")

    t = totals(repo.conn, Filter(site_id=b.id))

    assert [(s.taxa, s.recordings) for s in t.species] == [(PIPISTRELLE, 1)]
    assert t.recordings == 1


def test_filters_by_nights(repo: Repository) -> None:
    t = totals(repo.conn, Filter(first_night=date(2026, 9, 2), last_night=date(2026, 9, 2)))

    assert t.species == ()
    assert (t.recordings, t.with_calls, t.nights) == (2, 1, 1)


def test_an_empty_library(tmp_path: Path) -> None:
    t = totals(database.connect(tmp_path / "db.sqlite"))

    assert (t.species, t.recordings, t.analysed, t.with_calls, t.nights) == ((), 0, 0, 0, 0)


def test_how_much_each_recorder_was_used(tmp_path: Path) -> None:
    repo = Repository(database.connect(tmp_path / "db.sqlite"))
    garden, balcony = repo.add_site("Garden").id, repo.add_site("Balcony").id
    used, idle = repo.device("pippyg", "a").id, repo.device("pippyg", "b").id
    for i, (at, site) in enumerate(
        [(datetime(2026, 9, 1, 21), garden), (datetime(2026, 9, 5, 2), balcony)]
    ):
        repo.add_recording(
            f"{i:064d}", PurePosixPath(f"{i}.wav"), 1, recorded_at=at, site_id=site, device_id=used
        )

    use = device_use(repo.conn)

    assert idle not in use
    assert use[used].recordings == 2
    assert (use[used].first_night, use[used].last_night) == (date(2026, 9, 1), date(2026, 9, 4))
    assert use[used].last_site_id == balcony
