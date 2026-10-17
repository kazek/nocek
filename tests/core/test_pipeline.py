import os
from pathlib import Path

import pytest
import soundfile as sf

from nyctalus.core import batdetect, battybird
from nyctalus.core.audio import Audio, Samples
from nyctalus.core.batdetect import interpret
from nyctalus.core.pipeline import DEFAULT_SETTINGS, Analyser, Pass, Settings, Skipped
from nyctalus.core.region import Region
from nyctalus.core.taxonomy import Taxon
from tests import synth
from tests.core.factories import calls, opinion

ANYWHERE = Region("anywhere")
NOCTULE = frozenset({Taxon("Nyctalus noctula")})


class FakeBatDetect:
    def __init__(self, result: batdetect.Analysis | Exception) -> None:
        self.result = result
        self.seen: list[Path] = []

    def analyse(self, path: Path) -> batdetect.Analysis:
        self.seen.append(path)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeBattyBird:
    def __init__(self, result: battybird.Analysis | Exception) -> None:
        self.result = result
        self.seen = 0

    def analyse(self, audio: Audio) -> battybird.Analysis:
        self.seen += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


NOCTULE_SOURCES = interpret(calls("Nyctalus noctula", low_khz=20))
NOCTULE_SECOND = battybird.Analysis(
    opinion=opinion("Nyctalus noctula", score=0.9), not_a_bat=(), windows=()
)


def write(path: Path, samples: Samples) -> Path:
    sf.write(path, samples, synth.SAMPLE_RATE)
    return path


@pytest.fixture
def noctule_file(tmp_path: Path) -> Path:
    return write(
        tmp_path / "noctule.wav", synth.sequence(synth.sweep(28, 19, 0.015), n=10, interval_s=0.3)
    )


@pytest.fixture
def quiet_file(tmp_path: Path) -> Path:
    return write(tmp_path / "quiet.wav", synth.noise(1.0))


def analyser(
    bd: FakeBatDetect | None = None,
    bb: FakeBattyBird | None = None,
    settings: Settings = DEFAULT_SETTINGS,
) -> Analyser:
    return Analyser(
        Path("unused"),
        ANYWHERE,
        settings,
        batdetect_model=bd or FakeBatDetect(NOCTULE_SOURCES),
        battybird_model=bb or FakeBattyBird(NOCTULE_SECOND),
    )


def test_runs_every_pass_and_names_the_bat(noctule_file: Path) -> None:
    bd, bb = FakeBatDetect(NOCTULE_SOURCES), FakeBattyBird(NOCTULE_SECOND)

    result = analyser(bd, bb).analyse(noctule_file)

    assert result.failures == ()
    assert result.skipped == {}
    assert result.detection is not None and result.detection.has_calls
    assert result.key is not None
    assert bd.seen == [noctule_file] and bb.seen == 1
    assert result.verdict is not None
    assert result.verdict.named == (NOCTULE,)
    assert result.verdict.sources[0].battybird is not None


def test_the_sieve_keeps_quiet_recordings_from_the_networks(quiet_file: Path) -> None:
    bd, bb = FakeBatDetect(NOCTULE_SOURCES), FakeBattyBird(NOCTULE_SECOND)

    result = analyser(bd, bb).analyse(quiet_file)

    assert bd.seen == [] and bb.seen == 0
    assert result.skipped == {
        Pass.BATDETECT2: Skipped.NO_PULSES,
        Pass.BATTYBIRDNET: Skipped.NO_PULSES,
    }
    assert result.verdict is None


def test_without_the_sieve_the_networks_see_everything(quiet_file: Path) -> None:
    bd = FakeBatDetect(NOCTULE_SOURCES)

    result = analyser(bd, settings=Settings(sieve=False)).analyse(quiet_file)

    assert bd.seen == [quiet_file]
    assert result.verdict is not None
    # Named by the network, but the detector did not confirm it.
    assert result.verdict.named == ()


def test_battybird_waits_for_a_source(noctule_file: Path) -> None:
    bb = FakeBattyBird(NOCTULE_SECOND)

    result = analyser(FakeBatDetect(interpret([])), bb).analyse(noctule_file)

    assert bb.seen == 0
    assert result.skipped == {Pass.BATTYBIRDNET: Skipped.NO_SOURCES}


def test_a_disabled_pass_does_not_run(noctule_file: Path) -> None:
    bb = FakeBattyBird(NOCTULE_SECOND)
    settings = Settings(passes=frozenset({Pass.KEY, Pass.BATDETECT2}))

    result = analyser(bb=bb, settings=settings).analyse(noctule_file)

    assert bb.seen == 0
    assert result.skipped == {Pass.BATTYBIRDNET: Skipped.DISABLED}
    assert result.verdict is not None and result.verdict.named == (NOCTULE,)
    assert Pass.BATTYBIRDNET not in result.versions


def test_a_failed_network_leaves_the_rest(noctule_file: Path) -> None:
    result = analyser(bb=FakeBattyBird(battybird.ModelError("weights missing"))).analyse(
        noctule_file
    )

    assert [f.stage for f in result.failures] == [Pass.BATTYBIRDNET]
    assert result.verdict is not None and result.verdict.named == (NOCTULE,)


def test_without_batdetect2_there_is_no_verdict(noctule_file: Path) -> None:
    bb = FakeBattyBird(NOCTULE_SECOND)

    result = analyser(FakeBatDetect(batdetect.BatDetectError("torch says no")), bb).analyse(
        noctule_file
    )

    assert [f.message for f in result.failures] == ["torch says no"]
    assert result.skipped == {Pass.BATTYBIRDNET: Skipped.FAILED_EARLIER}
    assert result.key is not None
    assert result.verdict is None


def test_an_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"not audio")

    result = analyser().analyse(path)

    assert [f.stage for f in result.failures] == ["audio"]
    assert result.detection is None and result.verdict is None
    assert set(result.skipped.values()) == {Skipped.FAILED_EARLIER}


def test_records_what_produced_the_result(noctule_file: Path) -> None:
    versions = analyser().analyse(noctule_file).versions

    assert set(versions) == {"nyctalus", Pass.BATDETECT2, Pass.BATTYBIRDNET}
    assert versions[Pass.BATDETECT2] == "1.3.1"
    assert versions[Pass.BATTYBIRDNET].endswith("/Bavaria")


@pytest.mark.slow
@pytest.mark.skipif(
    "NYCTALUS_TEST_MODELS" not in os.environ,
    reason="set NYCTALUS_TEST_MODELS to a directory with the BattyBirdNET files",
)
def test_runs_the_real_models(noctule_file: Path) -> None:
    result = Analyser(Path(os.environ["NYCTALUS_TEST_MODELS"]), ANYWHERE).analyse(noctule_file)

    assert result.failures == ()
    assert result.batdetect is not None
