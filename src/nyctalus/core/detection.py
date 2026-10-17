"""Find bat calls in a recording and measure each one.

The detector only measures: it finds short, narrowband ultrasonic pulses and
reports their frequencies, length and rhythm. Naming a species is left to the
identification passes. Because these numbers come from no model, they can be
used to check what a model says.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

import numpy as np
import numpy.typing as npt

from nyctalus.core import spectrogram
from nyctalus.core.audio import Audio, Samples

Matrix = npt.NDArray[np.float32]


@dataclass(frozen=True)
class Params:
    # 1.33 ms: 512 samples at 384 kHz. Follows the sweep of a 5 ms call with
    # 750 Hz bins, and keeps the same duration at any other sample rate.
    window_ms: float = 512 / 384
    # The analysis starts below the lowest bat so that a pulse can be seen to
    # be bounded: a call's energy starts and stops inside the ultrasonic band,
    # while traffic and footsteps run on down to the floor.
    floor_khz: float = 12.0
    min_low_khz: float = 16.0
    min_peak_khz: float = 17.0
    # A pulse opens where a bin rises this far above its own background and
    # closes where it falls below the lower value.
    enter_db: float = 18.0
    exit_db: float = 12.0
    # Shorter is a click; longer is a machine or several calls run together.
    # The longest calls, Rhinolophus CF calls, last 30-60 ms.
    min_ms: float = 0.8
    max_ms: float = 70.0
    # Gaps this short are one pulse fading in and out, not two pulses.
    join_ms: float = 0.4
    # A call is narrowband at any instant; rain and rustle are not. Share of
    # the loudest frame's energy within three bins of its peak.
    min_narrowness: float = 0.30
    # Frequencies, bandwidth and duration are read this far below the peak,
    # the conventional field measurement point.
    extent_db: float = 20.0
    # Width of the frequency bins used to find the dominant group.
    group_bin_khz: float = 5.0
    # Files longer than this are analysed in blocks, so memory stays bounded
    # and the background estimate follows changing noise.
    long_file_s: float = 30.0
    block_s: float = 10.0


class Shape(StrEnum):
    """Call architecture, from the measurements alone."""

    CF = "cf"  # flat and long: Rhinolophus
    FM = "fm"  # steep and broad: Myotis, Plecotus
    FM_QCF = "fm-qcf"  # sweep into a flat tail: Pipistrellus, Nyctalus, Eptesicus
    UNCLEAR = "unclear"


@dataclass(frozen=True)
class Pulse:
    start_s: float
    duration_ms: float
    peak_khz: float
    start_khz: float
    end_khz: float
    low_khz: float
    high_khz: float
    snr_db: float
    narrowness: float
    shape: Shape


@dataclass(frozen=True)
class DominantGroup:
    """The pulses at the frequency that carries most of the recording's energy.

    Measuring only these keeps a second animal or a burst of noise out of the
    medians and the rhythm.
    """

    n_pulses: int
    energy_share: float
    peak_khz: float
    end_khz: float
    duration_ms: float
    best_snr_db: float
    interval_ms: float | None
    interval_spread: float | None


@dataclass(frozen=True)
class Detection:
    sample_rate: int
    duration_s: float
    pulses: tuple[Pulse, ...]
    dominant: DominantGroup | None

    @property
    def nyquist_khz(self) -> float:
        """Calls above this frequency cannot appear in the recording."""
        return self.sample_rate / 2000.0

    @property
    def has_calls(self) -> bool:
        return bool(self.pulses)


DEFAULT_PARAMS = Params()


def detect(audio: Audio, params: Params = DEFAULT_PARAMS) -> Detection:
    pulses = tuple(_pulses(audio, params))
    return Detection(
        sample_rate=audio.sample_rate,
        duration_s=audio.duration_s,
        pulses=pulses,
        dominant=_dominant_group(pulses, params) if pulses else None,
    )


def shape_of(sweep_khz: float, width_khz: float, duration_ms: float) -> Shape:
    """Conventional field cut-offs, meant to sort rather than to decide."""
    if width_khz < 5 and duration_ms > 15:
        return Shape.CF
    if width_khz > 25 and duration_ms < 6 and sweep_khz > 15:
        return Shape.FM
    if sweep_khz > 4 and duration_ms >= 4:
        return Shape.FM_QCF
    return Shape.UNCLEAR


def _pulses(audio: Audio, params: Params) -> list[Pulse]:
    if audio.sample_rate / 2000.0 <= params.floor_khz:
        return []  # nothing above the analysis floor can have been recorded
    if audio.duration_s <= params.long_file_s:
        return _find(audio.samples, audio.sample_rate, 0.0, params)

    # Each block is padded on both sides by more than the longest pulse, and
    # keeps only the pulses that start inside it: a pulse on a boundary is
    # seen whole by one block and dropped by its neighbour.
    rate = audio.sample_rate
    block = round(params.block_s * rate)
    margin = round(2 * params.max_ms / 1000 * rate)
    found: list[Pulse] = []
    for start in range(0, len(audio.samples), block):
        lead = min(margin, start)
        segment = audio.samples[start - lead : start + block + margin]
        offset_s = (start - lead) / rate
        block_start_s, block_end_s = start / rate, (start + block) / rate
        found.extend(
            pulse
            for pulse in _find(segment, rate, offset_s, params)
            if block_start_s <= pulse.start_s < block_end_s
        )
    return found


def _find(samples: Samples, rate: int, offset_s: float, params: Params) -> list[Pulse]:
    """Pulses in one stretch of audio, timed from the start of the recording."""
    nfft = round(rate * params.window_ms / 1000)
    spec = spectrogram.compute(Audio(samples, rate), nfft=nfft, hop=nfft // 4).above(
        params.floor_khz
    )
    if spec.n_frames == 0 or not spec.power.any():
        return []

    white = _whiten(spec.power)
    level_db = 10 * np.log10(np.maximum(white.max(axis=1), 1e-12))
    spans = _merge(_spans(level_db, params), spec.frame_ms, params)

    pulses = []
    for first, last in spans:
        if (last - first + 1) * spec.frame_ms > 2 * params.max_ms:
            continue
        pulse = _measure(white[first : last + 1], spec, first, params)
        if pulse is not None:
            pulses.append(pulse)
    return [_shifted(p, offset_s) for p in pulses]


def _whiten(power: Matrix) -> Matrix:
    """Each bin divided by its own median over time.

    The background is not flat: the microphone hisses more at 20 kHz than at
    90 kHz, and insects hold whole bands. A pulse has to stand out from the
    background at its own frequency.
    """
    floor = np.median(power, axis=0)
    floor = np.maximum(floor, max(float(np.max(power)) * 1e-9, np.finfo(np.float32).tiny))
    return (power / floor).astype(np.float32)


def _spans(level_db: npt.NDArray[np.float32], params: Params) -> list[tuple[int, int]]:
    """Runs of frames above the exit level that reach the entry level somewhere."""
    above = level_db > params.exit_db
    seeds = level_db > params.enter_db
    spans = []
    i, n = 0, len(level_db)
    while i < n:
        if not seeds[i]:
            i += 1
            continue
        first = i
        while first > 0 and above[first - 1]:
            first -= 1
        last = i
        while last + 1 < n and above[last + 1]:
            last += 1
        spans.append((first, last))
        i = last + 1
    return spans


def _merge(spans: list[tuple[int, int]], frame_ms: float, params: Params) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for first, last in spans:
        if merged and (first - merged[-1][1]) * frame_ms < params.join_ms:
            merged[-1] = (merged[-1][0], last)
        else:
            merged.append((first, last))
    return merged


def _measure(
    span: Matrix,
    spec: spectrogram.Spectrogram,
    first_frame: int,
    params: Params,
) -> Pulse | None:
    """Measure one span, or reject it as not a call."""
    loudness = span.max(axis=1)
    peak_frame = int(np.argmax(loudness))

    # The pulse is the contiguous run of frames around the peak within the
    # extent level, so a second call in the same span is not annexed to it.
    relative_db = 10 * np.log10(
        np.maximum(loudness, 1e-12) / max(float(loudness[peak_frame]), 1e-12)
    )
    inside = relative_db > -params.extent_db
    start = peak_frame
    while start > 0 and inside[start - 1]:
        start -= 1
    end = peak_frame
    while end + 1 < len(inside) and inside[end + 1]:
        end += 1

    # Duration is the extent above the -20 dB level, so it depends on the
    # call's envelope as well as its length: the analysis window lengthens a
    # call with abrupt edges by up to a millisecond, while the quiet ends of a
    # tapered call fall below the level and shorten it. No fixed correction
    # fits both, and none improved the key on the reference recordings.
    duration_ms = (end - start + 1) * spec.frame_ms
    if not params.min_ms <= duration_ms <= params.max_ms:
        return None

    spectrum = span[peak_frame]
    peak_bin = int(np.argmax(spectrum))
    near = spectrum[max(0, peak_bin - 3) : peak_bin + 4]
    narrowness = float(near.sum() / max(float(spectrum.sum()), 1e-12))
    if narrowness < params.min_narrowness:
        return None

    freqs = spec.freqs_khz
    occupied = np.flatnonzero(spectrum > spectrum[peak_bin] * 10 ** (-params.extent_db / 10))
    low_khz, high_khz = float(freqs[occupied[0]]), float(freqs[occupied[-1]])
    peak_khz = float(freqs[peak_bin])
    # A pulse whose low edge sits on the floor is the top of something that
    # continues below it, and below is where the road is.
    if low_khz < params.min_low_khz or peak_khz < params.min_peak_khz:
        return None

    start_khz = float(freqs[int(np.argmax(span[start]))])
    end_khz = float(freqs[int(np.argmax(span[end]))])
    snr_db = float(10 * np.log10(max(float(loudness[peak_frame]), 1e-12)))
    return Pulse(
        start_s=spec.frame_time_s(first_frame + start),
        duration_ms=duration_ms,
        peak_khz=peak_khz,
        start_khz=start_khz,
        end_khz=end_khz,
        low_khz=low_khz,
        high_khz=high_khz,
        snr_db=snr_db,
        narrowness=narrowness,
        shape=shape_of(start_khz - end_khz, high_khz - low_khz, duration_ms),
    )


def _shifted(pulse: Pulse, offset_s: float) -> Pulse:
    if not offset_s:
        return pulse
    return replace(pulse, start_s=pulse.start_s + offset_s)


def _dominant_group(pulses: tuple[Pulse, ...], params: Params) -> DominantGroup:
    """Group pulses by end frequency and keep the group with most energy.

    Weighting by power and length rather than counting pulses matters: a few
    long, loud horseshoe-bat calls must outvote many scraps of noise.
    """
    weight = np.array([10 ** (p.snr_db / 10) * p.duration_ms for p in pulses])
    end_khz = np.array([p.end_khz for p in pulses])
    edges = np.arange(
        params.floor_khz, end_khz.max() + 2 * params.group_bin_khz, params.group_bin_khz
    )
    bins = np.clip(np.digitize(end_khz, edges) - 1, 0, len(edges) - 2)
    energy = np.bincount(bins, weights=weight, minlength=len(edges) - 1)
    in_group = np.abs(bins - int(np.argmax(energy))) <= 1  # the best bin and its neighbours
    group = [p for p, keep in zip(pulses, in_group, strict=True) if keep]

    interval_ms = interval_spread = None
    # A search sequence from one bat is regular; echoes and insects are not.
    if len(group) >= 3:
        gaps_ms = np.diff([p.start_s for p in group]) * 1000
        q1, median, q3 = np.percentile(gaps_ms, [25, 50, 75])
        interval_ms = float(median)
        interval_spread = float((q3 - q1) / max(float(median), 1e-9))

    return DominantGroup(
        n_pulses=len(group),
        energy_share=float(weight[in_group].sum() / max(float(weight.sum()), 1e-30)),
        peak_khz=float(np.median([p.peak_khz for p in group])),
        end_khz=float(np.median([p.end_khz for p in group])),
        duration_ms=float(np.median([p.duration_ms for p in group])),
        best_snr_db=max(p.snr_db for p in group),
        interval_ms=interval_ms,
        interval_spread=interval_spread,
    )
