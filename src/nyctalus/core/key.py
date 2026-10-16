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

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from types import MappingProxyType

from nyctalus.core import taxonomy
from nyctalus.core.detection import Detection, DominantGroup
from nyctalus.core.opinion import Abstention, Candidate, Opinion
from nyctalus.core.taxonomy import Taxon

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
    weights: Mapping[str, float] = field(
        default_factory=lambda: MappingProxyType(
            {"end_khz": 3.0, "duration_ms": 1.5, "interval_ms": 1.0}
        )
    )
    # Below this no published range comes close: usually a feeding buzz, a
    # social call, or not a bat at all.
    min_score: float = 0.55
    shortlist_ratio: float = 0.90
    # A median needs at least three values, and the dominant group must hold
    # more energy than everything else together, or the medians describe
    # whichever source happened to win.
    min_pulses: int = 3
    min_energy_share: float = 0.5


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
    text = resources.files("nyctalus.core").joinpath("data/key_bands.json").read_text("utf-8")
    return MappingProxyType(
        {
            taxonomy.get(name): Bands(
                end_khz=_band(b["end_khz"]),
                duration_ms=_band(b["duration_ms"]),
                interval_ms=_band(b["interval_ms"]),
            )
            for name, b in json.loads(text)["taxa"].items()
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
    """Weighted mean of the fits, or None if any measurement rules the taxon out."""
    # An interval shorter than the published one says the bat was closing on
    # prey, not which bat it was, so it is left out rather than counted against
    # the species. Nothing lengthens intervals in the same way, so a longer one
    # remains evidence.
    interval = group.interval_ms
    evidence: dict[str, float | None] = {
        "end_khz": fit(group.end_khz, b.end_khz, params.tolerance),
        "duration_ms": fit(group.duration_ms, b.duration_ms, params.tolerance),
        "interval_ms": (
            None
            if interval is None or interval < b.interval_ms[0]
            else fit(interval, b.interval_ms, params.tolerance)
        ),
    }
    measured = {name: value for name, value in evidence.items() if value is not None}
    # One measurement far outside its band rules a species out however well
    # the rest fits: a 3 ms pulse is not a horseshoe bat, at any frequency.
    if any(value == 0.0 for value in measured.values()):
        return None
    total = sum(params.weights[name] for name in measured)
    score = sum(params.weights[name] * value for name, value in measured.items()) / total
    return Candidate(taxa=frozenset({taxon}), score=score, evidence=evidence)


def _band(values: list[float]) -> Band:
    low, high = values
    return float(low), float(high)
