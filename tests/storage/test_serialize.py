import json
from pathlib import Path

import pytest
import soundfile as sf

from nyctalus.core import battybird
from nyctalus.core.batdetect import interpret
from nyctalus.core.pipeline import Analyser, Pass, RecordingResult, Settings
from nyctalus.core.region import Region
from nyctalus.storage.serialize import FORMAT, FormatError, result_from_dict, result_to_dict
from tests import synth
from tests.core.factories import FakeBatDetect, FakeBattyBird, calls, opinion


def roundtrip(result: RecordingResult) -> RecordingResult:
    return result_from_dict(json.loads(json.dumps(result_to_dict(result))))


@pytest.fixture
def two_bats(tmp_path: Path) -> RecordingResult:
    """A full result: every pass ran, two sources, BattyBirdNET with windows."""
    path = tmp_path / "two.wav"
    sf.write(path, synth.sequence(synth.sweep(60, 46, 0.006), n=10), synth.SAMPLE_RATE)
    sources = interpret(
        calls("Pipistrellus pipistrellus", low_khz=45) + calls("Nyctalus noctula", low_khz=20)
    )
    second = battybird.Analysis(
        opinion=opinion("Pipistrellus pipistrellus", score=0.9),
        not_a_bat=(battybird.Sound("insect", 0.3),),
        windows=(battybird.Window(0.0, None), battybird.Window(0.42, None)),
    )
    analyser = Analyser(
        Path("unused"),
        Region("anywhere"),
        batdetect_model=FakeBatDetect(sources),
        battybird_model=FakeBattyBird(second),
    )
    return analyser.analyse(path)


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
