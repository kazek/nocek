"""The bats the application knows, identified by scientific name.

A taxon is either a species ("Myotis daubentonii") or a genus ("Myotis"). An
identification is a set of taxa, because a call often fits several species
equally well; expanding a genus to its species makes such sets comparable.
Names in other languages belong to the interface, not to this module.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from functools import cache

from nocek.core._data import load_json


class Rank(StrEnum):
    SPECIES = "species"
    GENUS = "genus"


@dataclass(frozen=True, order=True)
class Taxon:
    name: str

    @property
    def rank(self) -> Rank:
        return Rank.SPECIES if " " in self.name else Rank.GENUS

    @property
    def genus(self) -> str:
        return self.name.split(" ", 1)[0]

    def __str__(self) -> str:
        return self.name


class UnknownTaxonError(LookupError):
    """A name that is not in the catalogue."""


@cache
def species() -> tuple[Taxon, ...]:
    """Every species in the catalogue, alphabetically."""
    return tuple(sorted(Taxon(name) for name in load_json("taxa.json")["species"]))


@cache
def genera() -> tuple[Taxon, ...]:
    return tuple(sorted({Taxon(s.genus) for s in species()}))


def get(name: str) -> Taxon:
    """The catalogued taxon with this scientific name."""
    taxon = Taxon(name)
    if taxon not in _known():
        raise UnknownTaxonError(name)
    return taxon


def species_of(taxon: Taxon) -> frozenset[Taxon]:
    """The species a taxon stands for: itself, or every species of a genus."""
    if taxon.rank is Rank.SPECIES:
        return frozenset({taxon})
    return frozenset(s for s in species() if s.genus == taxon.name)


def expand(taxa: Iterable[Taxon]) -> frozenset[Taxon]:
    """All species covered by any of the taxa."""
    return frozenset().union(*(species_of(t) for t in taxa))


@cache
def _known() -> frozenset[Taxon]:
    return frozenset(species()) | frozenset(genera())
