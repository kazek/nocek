import json
from pathlib import Path

import pytest

from nocek.core import battybird
from nocek.core.batdetect import interpret
from nocek.core.pipeline import Analyser, Pass, RecordingResult, Settings
from nocek.core.region import Region
from nocek.storage.serialize import FORMAT, FormatError, result_from_dict, result_to_dict
from tests.core.factories import FakeBatDetect, FakeBattyBird


def roundtrip(result: RecordingResult) -> RecordingResult:
    return result_from_dict(json.loads(json.dumps(result_to_dict(result))))


def test_a_full_result_survives_the_round_trip(two_bats: RecordingResult) -> None:
    again = roundtrip(two_bats)

    assert result_to_dict(again) == result_to_dict(two_bats)
    assert again.verdict is not None and again.batdetect is not None
    # The verdict points at the same source objects, not at copies.
    assert again.verdict.sources[0].source in again.batdetect.sources
    assert again.detection is not None and two_bats.detection is not None
    assert again.detection.pulses == two_bats.detection.pulses


def test_a_failed_recording_survives_the_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"not audio")
    failed = Analyser(
        Path("unused"),
        Region("anywhere"),
        Settings(passes=frozenset({Pass.KEY})),
        batdetect_model=FakeBatDetect(interpret([])),
        battybird_model=FakeBattyBird(battybird.ModelError("unused")),
    ).analyse(path)

    again = roundtrip(failed)

    assert result_to_dict(again) == result_to_dict(failed)
    assert again.verdict is None
    assert again.failures == failed.failures


def test_records_the_format() -> None:
    data = {"format": FORMAT + 1}

    with pytest.raises(FormatError, match=str(FORMAT + 1)):
        result_from_dict(data)


def test_stores_taxa_by_name(two_bats: RecordingResult) -> None:
    data = result_to_dict(two_bats)

    named = [v["taxa"] for v in data["verdict"] if v["taxa"]]
    assert ["Pipistrellus pipistrellus"] in named
    assert all(isinstance(v["source"], int) for v in data["verdict"])
