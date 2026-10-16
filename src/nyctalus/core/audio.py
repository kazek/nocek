"""Loading recordings into memory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

Samples = npt.NDArray[np.float32]


class AudioError(Exception):
    """A file that cannot be read as audio."""


@dataclass(frozen=True)
class Audio:
    """Mono samples in the range [-1, 1] and the rate they were recorded at."""

    samples: Samples
    sample_rate: int

    @property
    def duration_s(self) -> float:
        return len(self.samples) / self.sample_rate


def load(path: Path) -> Audio:
    """Read an audio file, mixing several channels down to one.

    Any format libsndfile understands is accepted, so recordings from other
    devices load the same way as WAV files from a bat recorder.
    """
    try:
        data, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    except (sf.LibsndfileError, OSError) as error:
        raise AudioError(f"{path.name}: {error}") from error

    samples = data[:, 0] if data.shape[1] == 1 else data.mean(axis=1, dtype=np.float32)
    return Audio(samples=np.ascontiguousarray(samples), sample_rate=int(sample_rate))
