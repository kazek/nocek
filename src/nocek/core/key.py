"""Identify species from measurements, the way a field key does.

The key never looks at a spectrogram or at any model's answer. It compares
the dominant group's end frequency, call duration and call interval with
published ranges for European bats. It shares no code and no training data
with the neural networks, so where it agrees with them the answer is worth
more, and where it disagrees there is something to look at.

Where published ranges overlap, the key names every species that fits rather
than picking one: Myotis and Plecotus only to genus, Pipistrellus kuhlii and
P. nathusii often together.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from types import MappingProxyType

from nocek.core import taxonomy
from nocek.core._data import load_json
from nocek.core.detection import Detection, DominantGroup
from nocek.core.opinion import Abstention, Candidate, Opinion
from nocek.core.taxonomy import Taxon

SOURCE = "key"

Band = tuple[float, float]


@dataclass(frozen=True)
class Bands:
    end_khz: Band
    duration_ms: Band
    interval_ms: Band


@dataclass(frozen=True)
class Params:
    # How far outside a band a value may fall, as a fraction of the band's
    # width, before it counts for nothing. Roughly the spread between a
    # reference recording and the same species at field range.
    tolerance: float = 0.25
    # Published keys lead on frequency and treat the interval as supporting
    # evidence.
    end_weight: float = 3.0
    duration_weight: float = 1.5
    interval_weight: float = 1.0
    # Below this no published range comes close: usually a feeding buzz, a
    # social call, or not a bat at all.
    min_score: float = 0.55
    shortlist_ratio: float = 0.90
    # A median needs at least three values, and the dominant group must hold
    # more energy than everything else together, or the medians describe
    # whichever source happened to win.
    min_pulses: int = 3
    min_energy_share: float = 0.5
    # A species that rarely occurs in a region must score at least this. The
    # horseshoe-bat reference recording fits all three ranges and scores 1.0;
    # the archive recordings that reached the name scored 0.67 to 0.68.
    rare_min_score: float = 0.95


DEFAULT_PARAMS = Params()


def identify(detection: Detection, params: Params = DEFAULT_PARAMS) -> Opinion:
    group = detection.dominant

    def opinion(ranking: tuple[Candidate, ...] = (), declined: Abstention | None = None) -> Opinion:
        return Opinion(
            source=SOURCE,
            ranking=ranking,
            min_score=params.min_score,
            shortlist_ratio=params.shortlist_ratio,
            declined=declined,
        )

    if group is None or group.n_pulses < params.min_pulses:
        return opinion(declined=Abstention.TOO_FEW_PULSES)
    if group.energy_share <= params.min_energy_share:
        return opinion(declined=Abstention.MIXED_SOURCES)

    candidates = (_score(taxon, b, group, params) for taxon, b in bands().items())
    ranked = sorted((c for c in candidates if c is not None), key=lambda c: -c.score)
    return opinion(ranking=tuple(ranked))


@cache
def bands() -> Mapping[Taxon, Bands]:
    """Published ranges per taxon."""
    return MappingProxyType(
        {
            taxonomy.get(name): Bands(
                end_khz=_band(name, b["end_khz"]),
                duration_ms=_band(name, b["duration_ms"]),
                interval_ms=_band(name, b["interval_ms"]),
            )
            for name, b in load_json("key_bands.json")["taxa"].items()
        }
    )


def fit(value: float, band: Band, tolerance: float) -> float:
    """1 inside the band, falling linearly to 0 across the tolerance outside it."""
    low, high = band
    if low <= value <= high:
        return 1.0
    slack = max((high - low) * tolerance, 1e-9)
    miss = low - value if value < low else value - high
    return max(0.0, 1.0 - miss / slack)


def _score(taxon: Taxon, b: Bands, group: DominantGroup, params: Params) -> Candidate | None:
    """Weighted mean of the fits, or None if the call itself rules the taxon out."""
    end = fit(group.end_khz, b.end_khz, params.tolerance)
    duration = fit(group.duration_ms, b.duration_ms, params.tolerance)
    interval = _interval_fit(group.interval_ms, b, params)
    evidence: dict[str, float | None] = {
        "end_khz": end,
        "duration_ms": duration,
        "interval_ms": interval,
    }
    # Frequency or duration far outside the band rules a species out however
    # well the rest fits: a 3 ms pulse is not a horseshoe bat, at any
    # frequency. The interval only lowers the score. It depends on what the
    # bat was doing and on how many pulses reached the microphone, so on its
    # own it is not enough to exclude a species.
    if end == 0.0 or duration == 0.0:
        return None
    weighted = [
        (params.end_weight, end),
        (params.duration_weight, duration),
        (params.interval_weight, interval),
    ]
    measured = [(weight, value) for weight, value in weighted if value is not None]
    score = sum(w * v for w, v in measured) / sum(w for w, _ in measured)
    return Candidate(taxa=frozenset({taxon}), score=score, evidence=evidence)


def _interval_fit(interval: float | None, b: Bands, params: Params) -> float | None:
    """The interval's fit, or None when the interval is no evidence either way.

    An interval shorter than the published one says the bat was closing on
    prey, not which bat it was. Nothing lengthens intervals in the same way,
    so a longer one remains evidence. The spread of the intervals is not used:
    clean reference recordings of a single bat range from 0.3 to 1.6, so it
    does not separate a regular sequence from an irregular one.
    """
    if interval is None or interval < b.interval_ms[0]:
        return None
    return fit(interval, b.interval_ms, params.tolerance)


def _band(name: str, values: list[float]) -> Band:
    if len(values) != 2 or not values[0] <= values[1]:
        raise ValueError(f"{name}: a band is [low, high], got {values}")
    return float(values[0]), float(values[1])
