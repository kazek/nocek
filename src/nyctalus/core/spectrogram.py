"""Short-time power spectra of a recording."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from numpy.lib.stride_tricks import sliding_window_view

from nyctalus.core.audio import Audio

Power = npt.NDArray[np.float32]
Frequencies = npt.NDArray[np.float64]

# At 384 kHz a 512-sample window lasts 1.33 ms: short enough to follow the
# sweep of a 5 ms call, long enough for 750 Hz frequency bins. A hop of a
# quarter window places pulse edges to within a third of a millisecond.
DEFAULT_NFFT = 512
DEFAULT_HOP = 128


@dataclass(frozen=True)
class Spectrogram:
    """Power per frame (rows) and frequency bin (columns)."""

    power: Power
    freqs_khz: Frequencies
    sample_rate: int
    hop: int

    @property
    def n_frames(self) -> int:
        return int(self.power.shape[0])

    @property
    def frame_ms(self) -> float:
        """Time between the starts of consecutive frames."""
        return self.hop / self.sample_rate * 1000.0

    def frame_time_s(self, frame: int) -> float:
        return frame * self.hop / self.sample_rate

    def above(self, low_khz: float) -> Spectrogram:
        """Only the bins at or above a frequency."""
        keep = self.freqs_khz >= low_khz
        return Spectrogram(
            power=self.power[:, keep],
            freqs_khz=self.freqs_khz[keep],
            sample_rate=self.sample_rate,
            hop=self.hop,
        )


def compute(audio: Audio, nfft: int = DEFAULT_NFFT, hop: int = DEFAULT_HOP) -> Spectrogram:
    """Hann-windowed power spectrogram.

    A recording shorter than one window yields a spectrogram with no frames.
    """
    freqs_khz = np.fft.rfftfreq(nfft, 1.0 / audio.sample_rate) / 1000.0
    if len(audio.samples) < nfft:
        power = np.zeros((0, nfft // 2 + 1), dtype=np.float32)
    else:
        frames = sliding_window_view(audio.samples, nfft)[::hop]
        window = np.hanning(nfft).astype(np.float32)
        power = (np.abs(np.fft.rfft(frames * window, axis=1)) ** 2).astype(np.float32)
    return Spectrogram(power=power, freqs_khz=freqs_khz, sample_rate=audio.sample_rate, hop=hop)
