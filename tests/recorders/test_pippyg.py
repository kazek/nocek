import json
from datetime import datetime, time
from pathlib import Path

import pytest

from nocek.recorders.base import Location, Problem
from nocek.recorders.pippyg import Pippyg, parse_settings

# As pippyg firmware 8.15.0 writes it.
SETTINGS = {
    "uid": "e6659854e7389631",
    "fw": "8.15.0",
    "device_id": 0,
    "location": {"latitude": 50.0943679810000, "longitude": 19.9920635220000},
    "current_time": {"year": 2026, "month": 9, "day": 3, "hour": 18, "minute": 15},
    "activity": [{"wake": "18:15", "sleep": "7:30", "mode": "bat", "duration": 5}],
    "suppress_interference": 0,
    "suppress_leds": 0,
    "trigger_sensitivity": 48,
}


def settings(**changes: object) -> str:
    return json.dumps({**SETTINGS, **changes})


@pytest.fixture
def card(tmp_path: Path) -> Path:
    """A card with two hourly folders, one configuration and one empty settings file."""
    evening, night = tmp_path / "2026_03_sep_21", tmp_path / "2026_04_sep_02"
    evening.mkdir()
    night.mkdir()
    (evening / "DEV_000_20260903_213000.wav").write_bytes(b"audio")
    (night / "DEV_000_20260904_021500.wav").write_bytes(b"audio")
    (night / "latlong_50.094322_19.991842_.html").write_text("<meta>")
    (tmp_path / "device_settings_20260903_1815.json").write_text(settings())
    (tmp_path / "device_settings_20260915_2239.json").write_text("")
    (tmp_path / "notes.txt").write_text("not ours")
    return tmp_path


def test_recognises_a_pippyg_folder(card: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    (other / "song.wav").write_bytes(b"audio")

    assert Pippyg().recognises(card)
    assert not Pippyg().recognises(other)


def test_finds_recordings_with_their_times(card: Path) -> None:
    scan = Pippyg().scan(card)

    assert [(r.path.name, r.recorded_at, r.device_number) for r in scan.recordings] == [
        ("DEV_000_20260903_213000.wav", datetime(2026, 9, 3, 21, 30), 0),
        ("DEV_000_20260904_021500.wav", datetime(2026, 9, 4, 2, 15), 0),
    ]


def test_reads_the_configuration(card: Path) -> None:
    (config,) = Pippyg().scan(card).configs

    assert config.device_uid == "e6659854e7389631"
    assert config.device_number == 0
    assert config.written_at == datetime(2026, 9, 3, 18, 15)
    assert config.location == Location(50.094367981, 19.992063522)
    assert config.trigger_sensitivity == 48
    assert config.firmware == "8.15.0"
    assert config.schedules[0].wake == time(18, 15)
    assert config.schedules[0].sleep == time(7, 30)
    assert config.raw == settings()


def test_reports_an_empty_settings_file(card: Path) -> None:
    (finding,) = Pippyg().scan(card).findings

    assert finding.problem is Problem.EMPTY_SETTINGS
    assert finding.path.name == "device_settings_20260915_2239.json"


def test_reports_a_settings_file_it_cannot_read(tmp_path: Path) -> None:
    (tmp_path / "device_settings_20260903_1815.json").write_text('{"uid": "x"}')

    (finding,) = Pippyg().scan(tmp_path).findings

    assert finding.problem is Problem.UNREADABLE_SETTINGS


def test_the_configuration_in_force_at_a_moment(card: Path) -> None:
    scan = Pippyg().scan(card)

    assert scan.config_at(datetime(2026, 9, 3, 21, 30), device_number=0) is scan.configs[0]
    assert scan.config_at(datetime(2026, 9, 3, 12, 0), device_number=0) is None
    assert scan.config_at(datetime(2026, 9, 3, 21, 30), device_number=1) is None


def test_the_mode_at_a_moment() -> None:
    bird = parse_settings(
        settings(activity=[{"wake": "22:00", "sleep": "9:00", "mode": "bird", "duration": 40}])
    )

    assert bird.mode_at(datetime(2026, 9, 15, 22, 44)) == "bird"
    assert bird.mode_at(datetime(2026, 9, 16, 3, 0)) == "bird"
    assert bird.mode_at(datetime(2026, 9, 16, 12, 0)) is None
