import pytest

from nyctalus.core import taxonomy
from nyctalus.core.taxonomy import Rank, Taxon


def test_catalogue_has_species_and_their_genera() -> None:
    names = {t.name for t in taxonomy.species()}

    assert "Nyctalus noctula" in names
    assert "Pipistrellus kuhlii" in names
    assert {t.name for t in taxonomy.genera()} >= {"Myotis", "Plecotus", "Nyctalus"}


def test_catalogue_is_sorted_and_unique() -> None:
    species = taxonomy.species()

    assert list(species) == sorted(set(species))


def test_rank_and_genus() -> None:
    noctule = taxonomy.get("Nyctalus noctula")
    myotis = taxonomy.get("Myotis")

    assert noctule.rank is Rank.SPECIES
    assert noctule.genus == "Nyctalus"
    assert myotis.rank is Rank.GENUS
    assert myotis.genus == "Myotis"


def test_unknown_names_are_rejected() -> None:
    with pytest.raises(taxonomy.UnknownTaxonError):
        taxonomy.get("Pteropus vampyrus")


def test_a_genus_stands_for_all_its_species() -> None:
    plecotus = taxonomy.species_of(taxonomy.get("Plecotus"))

    assert plecotus == {Taxon("Plecotus auritus"), Taxon("Plecotus austriacus")}


def test_a_species_stands_for_itself() -> None:
    noctule = taxonomy.get("Nyctalus noctula")

    assert taxonomy.species_of(noctule) == {noctule}


def test_expand_unions_species() -> None:
    taxa = [taxonomy.get("Plecotus"), taxonomy.get("Nyctalus noctula")]

    assert taxonomy.expand(taxa) == {
        Taxon("Plecotus auritus"),
        Taxon("Plecotus austriacus"),
        Taxon("Nyctalus noctula"),
    }
    assert taxonomy.expand([]) == frozenset()
