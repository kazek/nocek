from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from nyctalus.core.audio import AudioError, load
from tests import synth


def test_loads_16_bit_mono(tmp_path: Path) -> None:
    path = tmp_path / "call.wav"
    samples = synth.tone(40, 0.01)
    sf.write(path, samples, synth.SAMPLE_RATE, subtype="PCM_16")

    audio = load(path)

    assert audio.sample_rate == synth.SAMPLE_RATE
    assert audio.samples.dtype == np.float32
    assert audio.duration_s == pytest.approx(0.01)
    np.testing.assert_allclose(audio.samples, samples, atol=1 / 32768)


def test_mixes_channels_down_to_mono(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    left = synth.tone(40, 0.01, amplitude=0.4)
    sf.write(path, np.stack([left, np.zeros_like(left)], axis=1), synth.SAMPLE_RATE)

    audio = load(path)

    assert audio.samples.ndim == 1
    np.testing.assert_allclose(audio.samples, left / 2, atol=1 / 32768)


def test_loads_24_bit(tmp_path: Path) -> None:
    path = tmp_path / "deep.wav"
    sf.write(path, synth.tone(40, 0.01), synth.SAMPLE_RATE, subtype="PCM_24")

    assert load(path).sample_rate == synth.SAMPLE_RATE


def test_rejects_a_file_that_is_not_audio(tmp_path: Path) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"not a recording")

    with pytest.raises(AudioError, match=r"broken\.wav"):
        load(path)


def test_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AudioError):
        load(tmp_path / "missing.wav")


def test_compares_by_identity() -> None:
    audio = synth.audio(synth.tone(40, 0.01))

    assert audio == audio
    assert audio != synth.audio(synth.tone(40, 0.01))
