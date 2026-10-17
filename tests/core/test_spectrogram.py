import numpy as np
import pytest

from nocek.core import spectrogram
from tests import synth


def test_finds_the_frequency_of_a_tone() -> None:
    spec = spectrogram.compute(synth.audio(synth.tone(45, 0.02)))

    loudest = spec.freqs_khz[np.argmax(spec.power.mean(axis=0))]

    assert loudest == pytest.approx(45, abs=0.75)


def test_follows_a_downward_sweep() -> None:
    spec = spectrogram.compute(synth.audio(synth.sweep(60, 30, 0.01)))

    peaks = spec.freqs_khz[np.argmax(spec.power, axis=1)]

    assert peaks[0] > peaks[-1]
    assert peaks[0] == pytest.approx(60, abs=3)
    assert peaks[-1] == pytest.approx(30, abs=3)


def test_frame_timing() -> None:
    spec = spectrogram.compute(synth.audio(synth.silence(0.01)), nfft=512, hop=128)

    assert spec.n_frames == 1 + (3840 - 512) // 128
    assert spec.frame_ms == pytest.approx(128 / 384)
    assert spec.frame_time_s(3) == pytest.approx(3 * 128 / synth.SAMPLE_RATE)


def test_shorter_than_one_window_has_no_frames() -> None:
    spec = spectrogram.compute(synth.audio(synth.silence(0.0001)))

    assert spec.n_frames == 0
    assert spec.power.shape[1] == len(spec.freqs_khz)


def test_above_keeps_only_higher_bins() -> None:
    spec = spectrogram.compute(synth.audio(synth.tone(45, 0.01))).above(12)

    assert spec.freqs_khz[0] >= 12
    assert spec.power.shape[1] == len(spec.freqs_khz)


@pytest.mark.parametrize(("nfft", "hop"), [(0, 1), (4, 0)])
def test_rejects_an_empty_window_or_hop(nfft: int, hop: int) -> None:
    with pytest.raises(ValueError):
        spectrogram.compute(synth.audio(synth.silence(0.01)), nfft=nfft, hop=hop)
