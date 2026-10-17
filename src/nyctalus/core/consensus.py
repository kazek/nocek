"""Combine the three passes into one verdict per animal in a recording.

BatDetect2 gives the names, one per source. The field key and BattyBirdNET
can only withhold a name, never replace it: when both name the same animal
and it is not the one BatDetect2 named, the name is withheld. Two independent
passes agreeing that a name is wrong is much stronger evidence than two
passes agreeing on what the right one is, and they fail in unrelated ways, so
agreeing by accident is unlikely. A withheld source is still a bat that was
recorded; only its species is left open.

Passes are compared at the level of comparison groups (see
data/comparison_groups.json), never finer, so no pass narrows a group to a
species it has not been shown to tell apart.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from functools import cache

from nyctalus.core import batdetect, battybird, key, taxonomy
from nyctalus.core._data import load_json
from nyctalus.core.detection import Detection
from nyctalus.core.opinion import Abstention, Opinion
from nyctalus.core.region import Region, restrict
from nyctalus.core.taxonomy import Taxon

Group = frozenset[Taxon]


@dataclass(frozen=True)
class Params:
    # The detector has to find this many pulses in the file before a network's
    # name is accepted: otherwise the two disagree that anything was there.
    min_pulses: int = 3
    # The key measures the dominant group only; it speaks for the source whose
    # calls end within this distance of the measured end frequency.
    key_match_khz: float = 5.0
    # End frequency separating the common pipistrelle (above) from Nathusius'
    # and Kuhl's (below), in the gap between their published ranges.
    pipistrelle_split_khz: float = 42.5


DEFAULT_PARAMS = Params()


class Note(StrEnum):
    """Something worth a look that does not change the verdict."""

    MEASURED_LIKE_COMMON_PIPISTRELLE = "measured-like-common-pipistrelle"
    MEASURED_LIKE_NATHUSIUS_PIPISTRELLE = "measured-like-nathusius-pipistrelle"


@dataclass(frozen=True)
class Agreement:
    """How many passes that named this animal agree with the verdict."""

    agreeing: int
    named: int


@dataclass(frozen=True)
class SourceVerdict:
    source: batdetect.Source
    # The species the source is named as, or None when withheld.
    taxa: frozenset[Taxon] | None
    reasons: tuple[Abstention, ...]
    notes: tuple[Note, ...]
    agreement: Agreement
    # The other passes' opinions, as they bear on this source, in the region.
    key: Opinion | None
    battybird: Opinion | None


@dataclass(frozen=True)
class Verdict:
    sources: tuple[SourceVerdict, ...]

    @property
    def named(self) -> tuple[frozenset[Taxon], ...]:
        return tuple(s.taxa for s in self.sources if s.taxa is not None)


@cache
def _groups() -> dict[Taxon, Group]:
    """Each grouped taxon, and every species of a grouped genus, to its group."""
    out: dict[Taxon, Group] = {}
    for names in load_json("comparison_groups.json")["groups"]:
        group = frozenset(taxonomy.get(n) for n in names)
        for t in group | taxonomy.expand(group):
            out[t] = group
    return out


def group_of(taxa: Iterable[Taxon] | None) -> Group | None:
    """The one comparison group the taxa fall in, or None if they span several."""
    if taxa is None:
        return None
    groups = {_groups().get(t, frozenset({t})) for t in taxa}
    return groups.pop() if len(groups) == 1 else None


def combine(
    region: Region,
    sources: batdetect.Analysis,
    detection: Detection | None = None,
    key_opinion: Opinion | None = None,
    battybird_opinion: Opinion | None = None,
    params: Params = DEFAULT_PARAMS,
) -> Verdict:
    """One recording's verdict. A pass that did not run is passed as None."""
    regional = [
        restrict(s.opinion, region, batdetect.DEFAULT_PARAMS.rare_min_score)
        for s in sources.sources
    ]
    if key_opinion is not None:
        key_opinion = restrict(key_opinion, region, key.DEFAULT_PARAMS.rare_min_score)
    if battybird_opinion is not None:
        battybird_opinion = restrict(
            battybird_opinion, region, battybird.DEFAULT_PARAMS.rare_min_score
        )

    keyed = _key_source(sources, detection, params)
    named = [i for i, o in enumerate(regional) if o.taxa is not None]
    # BattyBirdNET answers for the whole file, so it can only be lined up with
    # a source when there is exactly one named source to line it up with.
    sole = named[0] if len(named) == 1 else None
    corroborated = detection is None or len(detection.pulses) >= params.min_pulses

    verdicts = []
    for i, (source, opinion) in enumerate(zip(sources.sources, regional, strict=True)):
        k = key_opinion if i == keyed else None
        b = battybird_opinion if i == sole else None
        reasons = [opinion.abstention] if opinion.abstention else []
        if not corroborated:
            reasons.append(Abstention.UNCORROBORATED)
        own = group_of(opinion.taxa)
        others = group_of(k.taxa if k else None), group_of(b.taxa if b else None)
        if own and others[0] and others[0] == others[1] and others[0] != own:
            reasons.append(Abstention.CONTRADICTED)
        verdicts.append(
            SourceVerdict(
                source=source,
                taxa=None if reasons else opinion.taxa,
                reasons=tuple(reasons),
                notes=_notes(source, detection, params) if i == keyed else (),
                agreement=_agreement(own, others),
                key=k,
                battybird=b,
            )
        )
    return Verdict(sources=tuple(verdicts))


def _key_source(
    sources: batdetect.Analysis, detection: Detection | None, params: Params
) -> int | None:
    """The source the detector's dominant group, and so the key, describes."""
    if detection is None or detection.dominant is None or not sources.sources:
        return None
    end = detection.dominant.end_khz
    distances = [abs(s.low_khz - end) for s in sources.sources]
    nearest = min(range(len(distances)), key=lambda i: distances[i])
    return nearest if distances[nearest] <= params.key_match_khz else None


def _agreement(own: Group | None, others: tuple[Group | None, Group | None]) -> Agreement:
    groups = [g for g in (own, *others) if g is not None]
    return Agreement(agreeing=sum(1 for g in groups if g == own) if own else 0, named=len(groups))


def _notes(
    source: batdetect.Source, detection: Detection | None, params: Params
) -> tuple[Note, ...]:
    """The measured end frequency against the model's two most confused classes.

    A flag for a person, never an override: the two disagree often enough
    that which is right stays an open question on each recording.
    """
    if detection is None or detection.dominant is None:
        return ()
    end = detection.dominant.end_khz
    split = params.pipistrelle_split_khz
    if source.model_class == "Pipistrellus nathusii" and end > split:
        return (Note.MEASURED_LIKE_COMMON_PIPISTRELLE,)
    if source.model_class == "Pipistrellus pipistrellus" and end < split:
        return (Note.MEASURED_LIKE_NATHUSIUS_PIPISTRELLE,)
    return ()
