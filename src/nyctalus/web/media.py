"""Recordings made audible and visible.

Ultrasound is slowed down to be heard: the samples stay as recorded and only
the rate in the header changes, so ten times slower is ten times lower, the
way time-expansion bat detectors have always done it.

The spectrogram is computed with the detector's own window, so what the page
shows is what the detector measured. It is cut to the frequencies asked for
and squeezed to the width asked for by keeping each column's loudest frame,
so a call a few milliseconds long is never averaged away. Long recordings are
processed a block at a time, so memory does not grow with their length.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

from nyctalus.core import detection, spectrogram
from nyctalus.core.audio import Audio, load

MAX_SLOWDOWN = 40
COLUMNS_PER_BLOCK = 256
# Header subtypes kept as recorded; anything else is written as 16-bit PCM.
_KEPT_SUBTYPES = {"PCM_16", "PCM_24", "PCM_32", "FLOAT"}


def slowed_wav(path: Path, slowdown: int) -> bytes:
    """The recording as a WAV file played `slowdown` times slower."""
    if not 1 <= slowdown <= MAX_SLOWDOWN:
        raise ValueError(f"slowdown must be between 1 and {MAX_SLOWDOWN}")
    info = sf.info(path)
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    out = io.BytesIO()
    subtype = info.subtype if info.subtype in _KEPT_SUBTYPES else "PCM_16"
    sf.write(out, data, max(1, round(rate / slowdown)), format="WAV", subtype=subtype)
    return out.getvalue()


@dataclass(frozen=True, eq=False)
class Image:
    """Loudness per column (time) and row (frequency, lowest first), 0 to 255."""

    pixels: npt.NDArray[np.uint8]
    seconds_per_column: float
    min_khz: float
    khz_per_row: float
    duration_s: float  # of the whole recording
    start_s: float  # where the picture begins in it
    # The loudness shown white, in dB of the recording's own scale, and the
    # range below it that fades to black.
    top_db: float
    range_db: float


# Black is the recording's own background noise, a little below its typical
# level; white is its loudest moments, but never closer than this to black,
# so a recording of nothing but noise stays dark instead of being stretched.
NOISE_MARGIN_DB = 3.0


def image(
    path: Path,
    width: int = 1600,
    min_khz: float = 10.0,
    max_khz: float | None = None,
    range_db: float = 30.0,
    start_s: float = 0.0,
    end_s: float | None = None,
) -> Image:
    """The spectrogram of the recording, or of the stretch from start_s to end_s.

    range_db is the least distance from black to white, in dB.
    """
    whole = load(path)
    begin = max(0, round(start_s * whole.sample_rate))
    stop = len(whole.samples) if end_s is None else round(end_s * whole.sample_rate)
    sound = Audio(whole.samples[begin:stop], whole.sample_rate)
    params = detection.DEFAULT_PARAMS
    nfft = round(sound.sample_rate * params.window_ms / 1000)
    hop = nfft // 4
    freqs = np.fft.rfftfreq(nfft, 1.0 / sound.sample_rate) / 1000.0
    top = min(max_khz or freqs[-1], freqs[-1])
    rows = np.flatnonzero((freqs >= min_khz) & (freqs <= top))
    total = 0 if len(sound.samples) < nfft else 1 + (len(sound.samples) - nfft) // hop
    per_column = max(1, math.ceil(total / max(1, width)))
    columns = math.ceil(total / per_column) if total else 0

    power = np.zeros((columns, len(rows)), dtype=np.float32)
    for first in range(0, columns, COLUMNS_PER_BLOCK):
        last = min(columns, first + COLUMNS_PER_BLOCK)
        frame_a, frame_b = first * per_column, min(total, last * per_column)
        segment = sound.samples[frame_a * hop : (frame_b - 1) * hop + nfft]
        spec = spectrogram.compute(Audio(segment, sound.sample_rate), nfft=nfft, hop=hop)
        block = spec.power[: frame_b - frame_a][:, rows]
        starts = np.arange(0, len(block), per_column)
        power[first:last] = np.maximum.reduceat(block, starts, axis=0)

    db = 10 * np.log10(np.maximum(power, 1e-20))
    floor_db = float(np.median(db)) - NOISE_MARGIN_DB if db.size else 0.0
    top_db = max(float(np.percentile(db, 99.9)) if db.size else 0.0, floor_db + range_db)
    span = top_db - floor_db
    scaled = np.clip((db - floor_db) / span, 0, 1) * 255
    return Image(
        pixels=scaled.astype(np.uint8),
        seconds_per_column=per_column * hop / sound.sample_rate,
        min_khz=float(freqs[rows[0]]) if len(rows) else min_khz,
        khz_per_row=float(freqs[1] - freqs[0]),
        duration_s=whole.duration_s,
        start_s=begin / whole.sample_rate,
        top_db=top_db,
        range_db=span,
    )
