import numpy as np
import pytest

from nyctalus.core.detection import Shape, detect, shape_of
from tests import synth

PIPISTRELLE = synth.sweep(60, 46, 0.006)


def test_background_noise_has_no_calls() -> None:
    detection = detect(synth.audio(synth.noise(1)))

    assert not detection.has_calls
    assert detection.dominant is None


def test_measures_a_search_sequence() -> None:
    detection = detect(synth.audio(synth.sequence(PIPISTRELLE, n=10, interval_s=0.1)))

    assert len(detection.pulses) == 10
    assert {p.shape for p in detection.pulses} == {Shape.FM_QCF}
    group = detection.dominant
    assert group is not None
    assert group.n_pulses == 10
    assert group.energy_share == pytest.approx(1.0)
    assert group.end_khz == pytest.approx(46, abs=1)
    assert group.duration_ms == pytest.approx(6, abs=1)
    assert group.interval_ms == pytest.approx(100, abs=0.5)
    assert group.interval_spread == pytest.approx(0, abs=0.05)


def test_recognises_a_constant_frequency_call() -> None:
    detection = detect(synth.audio(synth.sequence(synth.tone(110, 0.04))))

    assert {p.shape for p in detection.pulses} == {Shape.CF}
    assert detection.dominant is not None
    assert detection.dominant.peak_khz == pytest.approx(110, abs=1)


def test_rejects_low_frequency_sound() -> None:
    # Traffic and footsteps: energy that reaches down to the analysis floor.
    detection = detect(synth.audio(synth.sequence(synth.tone(14, 0.01))))

    assert not detection.has_calls


def test_rejects_clicks() -> None:
    click = np.zeros(400, dtype=np.float32)
    click[200] = 0.9

    assert not detect(synth.audio(synth.sequence(click))).has_calls


def test_rhythm_needs_three_pulses() -> None:
    detection = detect(synth.audio(synth.sequence(PIPISTRELLE, n=2)))

    assert detection.dominant is not None
    assert detection.dominant.interval_ms is None


def test_measures_the_same_at_another_sample_rate() -> None:
    rate = 256_000
    call = synth.sweep(60, 46, 0.006, sample_rate=rate)
    detection = detect(synth.audio(synth.sequence(call, sample_rate=rate), sample_rate=rate))

    assert detection.nyquist_khz == 128
    assert len(detection.pulses) == 10
    assert detection.dominant is not None
    assert detection.dominant.duration_ms == pytest.approx(6, abs=1)
    assert detection.dominant.interval_ms == pytest.approx(100, abs=0.5)


def test_long_file_counts_every_call_once() -> None:
    # 10 s blocks: calls just before, on and after each boundary.
    starts = [5.0, 9.997, 15.0, 19.99, 25.0, 30.0, 35.0]
    detection = detect(synth.audio(synth.calls_at(PIPISTRELLE, starts, duration_s=40)))

    found = [p.start_s for p in detection.pulses]
    assert found == pytest.approx(starts, abs=0.005)


def test_shorter_than_one_window() -> None:
    detection = detect(synth.audio(synth.silence(0.0001)))

    assert not detection.has_calls
    assert detection.duration_s == pytest.approx(0.0001, abs=1 / synth.SAMPLE_RATE)


@pytest.mark.parametrize(
    ("sweep_khz", "width_khz", "duration_ms", "shape"),
    [
        (0, 2, 40, Shape.CF),
        (40, 40, 3, Shape.FM),
        (10, 8, 6, Shape.FM_QCF),
        (2, 3, 2, Shape.UNCLEAR),
    ],
)
def test_shape_cut_offs(
    sweep_khz: float, width_khz: float, duration_ms: float, shape: Shape
) -> None:
    assert shape_of(sweep_khz, width_khz, duration_ms) is shape


def test_a_rate_too_low_for_bats_has_no_calls() -> None:
    rate = 2_000
    detection = detect(synth.audio(synth.noise(1, sample_rate=rate), sample_rate=rate))

    assert not detection.has_calls
