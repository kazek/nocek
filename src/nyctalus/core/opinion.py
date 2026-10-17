"""What one identification pass says about a recording.

Every pass returns the same shape: candidates ranked by score, each standing
for a set of taxa, and the rules the pass uses to turn that ranking into an
answer. Keeping the whole ranking lets a later step remove candidates, for
example species that do not occur in the region, and draw the conclusion the
pass would have drawn without them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from nyctalus.core.taxonomy import Taxon


class Abstention(StrEnum):
    """Why a pass gives no answer."""

    TOO_SHORT = "too-short"  # the recording is shorter than the model can read
    TOO_FEW_PULSES = "too-few-pulses"  # not enough calls to measure
    MIXED_SOURCES = "mixed-sources"  # several animals or noise calling at once
    RULED_OUT = "ruled-out"  # every candidate was excluded
    NO_MATCH = "no-match"  # the best candidate scores too low
    OUT_OF_BAND = "out-of-band"  # the calls' frequency contradicts their label
    INCONCLUSIVE = "inconclusive"  # the calls vote evenly between labels
    UNCORROBORATED = "uncorroborated"  # the detector found too little to confirm a bat
    CONTRADICTED = "contradicted"  # two other passes agree on a different animal


@dataclass(frozen=True)
class Candidate:
    taxa: frozenset[Taxon]
    score: float
    # How the score was made up, for display: evidence name to its value.
    evidence: Mapping[str, float | None] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class Opinion:
    source: str
    ranking: tuple[Candidate, ...]
    # The leader must score at least this to be named.
    min_score: float
    # Candidates scoring at least this fraction of the leader, and at least
    # min_score, are named with it.
    shortlist_ratio: float
    # Set when the pass declined before scoring anything.
    declined: Abstention | None = None

    @property
    def leader(self) -> Candidate | None:
        return self.ranking[0] if self.ranking else None

    @property
    def abstention(self) -> Abstention | None:
        if self.declined:
            return self.declined
        if self.leader is None:
            return Abstention.RULED_OUT
        if self.leader.score < self.min_score:
            return Abstention.NO_MATCH
        return None

    @property
    def taxa(self) -> frozenset[Taxon] | None:
        """Everything the pass considers as likely as its leader, or None."""
        if self.leader is None or self.abstention:
            return None
        # A candidate too weak to be named on its own is not named alongside.
        cut = max(self.leader.score * self.shortlist_ratio, self.min_score)
        return frozenset().union(*(c.taxa for c in self.ranking if c.score >= cut))

    def excluding(self, rule: Callable[[Candidate], bool]) -> Opinion:
        """The same opinion with the candidates matching the rule removed."""
        return replace(self, ranking=tuple(c for c in self.ranking if not rule(c)))
