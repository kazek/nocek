from pathlib import Path

import pytest
import soundfile as sf

from nocek.core import battybird
from nocek.core.batdetect import interpret
from nocek.core.pipeline import Analyser, RecordingResult
from nocek.core.region import Region
from tests import synth
from tests.core.factories import FakeBatDetect, FakeBattyBird, calls, opinion


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
