"""Which species occur where a recording was made.

A region gives every species a status. Absent species are removed from every
answer; rare ones may be named only on exceptionally strong evidence, since a
classifier with no "none of these" class will reach for whichever class best
matches what it heard, rare or not. Regions come from profiles chosen by
location, and a site can override any status.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from functools import cache
from types import MappingProxyType

from nocek.core import taxonomy
from nocek.core._data import load_json
from nocek.core.opinion import Opinion
from nocek.core.taxonomy import Rank, Taxon


class Status(StrEnum):
    OCCURS = "occurs"
    RARE = "rare"
    ABSENT = "absent"


@dataclass(frozen=True)
class Bounds:
    south: float
    north: float
    west: float
    east: float

    def contain(self, latitude: float, longitude: float) -> bool:
        return self.south <= latitude <= self.north and self.west <= longitude <= self.east


@dataclass(frozen=True)
class Region:
    name: str
    default: Status = Status.OCCURS
    statuses: Mapping[Taxon, Status] = field(default_factory=dict)

    def status(self, species: Taxon) -> Status:
        return self.statuses.get(species, self.default)

    def overridden(self, overrides: Mapping[Taxon, Status]) -> Region:
        """The region with a site's own statuses applied on top."""
        return replace(self, statuses=MappingProxyType({**self.statuses, **overrides}))

    def present(self, taxon: Taxon) -> bool:
        """A species that is not absent, or a genus with such a species."""
        return any(self.status(s) is not Status.ABSENT for s in taxonomy.species_of(taxon))

    def rare(self, taxa: frozenset[Taxon]) -> bool:
        """Every present species the taxa stand for is rare."""
        species = [s for s in taxonomy.expand(taxa) if self.status(s) is not Status.ABSENT]
        return bool(species) and all(self.status(s) is Status.RARE for s in species)


@dataclass(frozen=True)
class Profile:
    id: str
    region: Region
    bounds: Bounds | None


@cache
def profiles() -> tuple[Profile, ...]:
    out = []
    for p in load_json("regions.json")["profiles"]:
        statuses = {taxonomy.get(name): Status(s) for name, s in p["species"].items()}
        if any(t.rank is not Rank.SPECIES for t in statuses):
            raise ValueError(f"{p['id']}: statuses are given per species")
        bounds = p["bounds"]
        out.append(
            Profile(
                id=p["id"],
                region=Region(
                    name=p["name"],
                    default=Status(p["default"]),
                    statuses=MappingProxyType(statuses),
                ),
                bounds=Bounds(**bounds) if bounds else None,
            )
        )
    return tuple(out)


def profile_for(latitude: float | None, longitude: float | None) -> Profile:
    """The first profile containing the location, or the fallback profile."""
    if latitude is not None and longitude is not None:
        for p in profiles():
            if p.bounds and p.bounds.contain(latitude, longitude):
                return p
    return next(p for p in profiles() if p.bounds is None)


def restrict(opinion: Opinion, region: Region, rare_min_score: float) -> Opinion:
    """The opinion as it stands in a region.

    Absent species leave every candidate's taxa, and a candidate with none
    left is dropped. A candidate standing only for rare species is dropped
    unless it scores at least rare_min_score. The conclusion is then drawn
    again from what remains.
    """
    ranking = []
    for c in opinion.ranking:
        taxa = frozenset(t for t in c.taxa if region.present(t))
        if not taxa or (region.rare(taxa) and c.score < rare_min_score):
            continue
        ranking.append(replace(c, taxa=taxa))
    return replace(opinion, ranking=tuple(ranking))
