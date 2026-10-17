from datetime import datetime
from pathlib import Path

import pytest
import soundfile as sf

from nocek.recorders.checks import Issue
from nocek.storage.importer import Notice, Skip, import_folder
from nocek.storage.library import Library
from tests import synth
from tests.recorders.test_pippyg import settings

NOW = datetime(2026, 10, 1, 12, 0)
UID = "e6659854e7389631"


def wav(path: Path, seconds: float = 0.05, seed: float = 40) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, synth.tone(seed, seconds), synth.SAMPLE_RATE, subtype="PCM_16")
    return path


@pytest.fixture
def library(tmp_path: Path) -> Library:
    return Library.create(tmp_path / "library")


@pytest.fixture
def card(tmp_path: Path) -> Path:
    """Two bat-mode recordings on a night in September, and one configuration."""
    card = tmp_path / "card"
    wav(card / "2026_03_sep_21" / "DEV_000_20260903_213000.wav", seed=40)
    wav(card / "2026_04_sep_02" / "DEV_000_20260904_021500.wav", seed=45)
    (card / "device_settings_20260903_1815.json").write_text(settings())
    return card


def test_copies_new_recordings_into_the_library(library: Library, card: Path) -> None:
    report = import_folder(library, card, now=NOW)

    assert report.copied == 2
    assert report.new_configs == 1
    recordings = sorted(library.recordings_dir.rglob("*.wav"))
    assert [p.relative_to(library.recordings_dir).as_posix() for p in recordings] == [
        f"pippyg-{UID}/2026-09-03/DEV_000_20260903_213000.wav",
        f"pippyg-{UID}/2026-09-03/DEV_000_20260904_021500.wav",
    ]
    assert not list(library.recordings_dir.rglob("*.part"))


def test_records_each_recording_with_its_device_and_night(library: Library, card: Path) -> None:
    import_folder(library, card, now=NOW)

    (device,) = library.repository.devices("pippyg")
    recordings = library.repository.recordings_without_result()
    assert {r.device_id for r in recordings} == {device.id}
    assert [r.night.isoformat() for r in recordings if r.night] == ["2026-09-03"] * 2
    assert {r.sample_rate for r in recordings} == {synth.SAMPLE_RATE}
    assert all(r.duration_s == pytest.approx(0.05) for r in recordings)


def test_never_changes_the_card(library: Library, card: Path) -> None:
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in card.rglob("*") if p.is_file()}

    import_folder(library, card, now=NOW)

    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in card.rglob("*") if p.is_file()}
    assert after == before


def test_a_second_import_copies_nothing(library: Library, card: Path) -> None:
    import_folder(library, card, now=NOW)

    again = import_folder(library, card, now=NOW)

    assert again.copied == 0
    assert again.skipped == {Skip.KNOWN: 2}
    assert again.new_configs == 0


def test_a_nested_copy_of_the_same_files_is_known(library: Library, card: Path) -> None:
    copy = card / "backup" / "2026_03_sep_21"
    copy.mkdir(parents=True)
    source = card / "2026_03_sep_21" / "DEV_000_20260903_213000.wav"
    (copy / source.name).write_bytes(source.read_bytes())

    report = import_folder(library, card, now=NOW)

    assert report.copied == 2
    assert report.skipped == {Skip.KNOWN: 1}


def test_skips_recordings_made_in_bird_mode(library: Library, card: Path) -> None:
    bird = {"wake": "22:00", "sleep": "9:00", "mode": "bird"}
    (card / "device_settings_20260915_2200.json").write_text(
        settings(
            activity=[bird],
            current_time={"year": 2026, "month": 9, "day": 15, "hour": 22, "minute": 0},
        )
    )
    wav(card / "2026_15_sep_22" / "DEV_000_20260915_224436.wav")

    report = import_folder(library, card, now=NOW)

    assert report.copied == 2
    assert report.skipped == {Skip.NOT_BAT_MODE: 1}
    assert [i.issue for i in report.issues] == [Issue.NOT_BAT_MODE]


def test_skips_empty_and_broken_files(library: Library, card: Path) -> None:
    (card / "2026_04_sep_02" / "DEV_000_20260904_030000.wav").write_bytes(b"")
    (card / "2026_04_sep_02" / "DEV_000_20260904_031000.wav").write_bytes(b"RIFF" + b"x" * 4000)
    (card / "device_settings_20260915_2239.json").write_text("")

    report = import_folder(library, card, now=NOW)

    assert report.copied == 2
    assert report.skipped == {Skip.UNREADABLE: 2}
    assert [f.path.name for f in report.findings] == ["device_settings_20260915_2239.json"]


def test_uses_configurations_from_earlier_imports(
    library: Library, card: Path, tmp_path: Path
) -> None:
    import_folder(library, card, now=NOW)
    later = tmp_path / "later"  # a card with recordings but no settings file
    wav(later / "2026_05_sep_22" / "DEV_000_20260905_220000.wav", seed=50)

    report = import_folder(library, later, now=NOW)

    assert report.copied == 1
    assert Notice.NO_DEVICE not in {n.notice for n in report.notices}
    (device,) = library.repository.devices("pippyg")
    assert {r.device_id for r in library.repository.recordings_without_result()} == {device.id}


def test_a_recording_with_no_device_is_reported(library: Library, tmp_path: Path) -> None:
    bare = tmp_path / "bare"
    wav(bare / "DEV_000_20260905_220000.wav")

    report = import_folder(library, bare, now=NOW)

    assert report.copied == 1
    notices = {n.notice: n.count for n in report.notices}
    assert notices == {Notice.NO_DEVICE: 1, Notice.NO_SITE: 1}
    assert next(library.recordings_dir.rglob("*.wav")).parent.parent.name == "pippyg-unknown"


def test_a_recording_goes_to_the_site_it_was_made_at(library: Library, card: Path) -> None:
    near = library.repository.add_site("Balcony", 50.0950, 19.9925)  # about 100 m away
    library.repository.add_site("Allotment", 50.1100, 20.0300)  # a few km away

    report = import_folder(library, card, now=NOW)

    assert all(n.notice is not Notice.NO_SITE for n in report.notices)
    assert {r.site_id for r in library.repository.recordings_without_result()} == {near.id}


def test_a_new_place_is_reported_with_its_position(library: Library, card: Path) -> None:
    library.repository.add_site("Allotment", 50.1100, 20.0300)

    report = import_folder(library, card, now=NOW)

    (notice,) = [n for n in report.notices if n.notice is Notice.NO_SITE]
    assert notice.count == 2
    assert notice.location is not None
    assert notice.location.latitude == pytest.approx(50.0944, abs=1e-3)


def test_a_chosen_site_wins(library: Library, card: Path) -> None:
    chosen = library.repository.add_site("Garden")

    import_folder(library, card, site=chosen, now=NOW)

    assert {r.site_id for r in library.repository.recordings_without_result()} == {chosen.id}


def test_a_clock_running_fast_is_reported(library: Library, card: Path) -> None:
    report = import_folder(library, card, now=datetime(2026, 9, 3, 12, 0))

    (notice,) = [n for n in report.notices if n.notice is Notice.CLOCK_AHEAD]
    assert notice.count == 2


def test_reports_progress(library: Library, card: Path) -> None:
    seen: list[tuple[int, int]] = []

    import_folder(
        library, card, progress=lambda done, total, name: seen.append((done, total)), now=NOW
    )

    assert seen == [(1, 2), (2, 2)]
