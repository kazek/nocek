import pytest

from nyctalus.core import region
from nyctalus.core.opinion import Candidate, Opinion
from nyctalus.core.region import Region, Status, restrict
from nyctalus.core.taxonomy import Taxon

NOCTULE = Taxon("Nyctalus noctula")
LEISLER = Taxon("Nyctalus leisleri")
MURINUS = Taxon("Vespertilio murinus")
HORSESHOE = Taxon("Rhinolophus hipposideros")


def ranked(*candidates: tuple[set[Taxon], float]) -> Opinion:
    return Opinion(
        source="test",
        ranking=tuple(Candidate(frozenset(t), s) for t, s in candidates),
        min_score=0.5,
        shortlist_ratio=0.9,
    )


def test_picks_a_profile_by_location() -> None:
    assert region.profile_for(50.09, 19.99).id == "central-europe"  # Kraków
    assert region.profile_for(40.4, -3.7).id == "europe"  # Madrid
    assert region.profile_for(None, None).id == "europe"


def test_a_site_overrides_its_profile() -> None:
    base = region.profile_for(50.09, 19.99).region
    site = base.overridden({HORSESHOE: Status.RARE, NOCTULE: Status.ABSENT})

    assert base.status(HORSESHOE) is Status.RARE  # horseshoe bats are rare by default
    assert site.status(HORSESHOE) is Status.RARE
    assert base.status(NOCTULE) is Status.OCCURS
    assert site.status(NOCTULE) is Status.ABSENT


def test_a_genus_is_present_while_any_species_is() -> None:
    plecotus = Taxon("Plecotus")
    one_gone = Region("test", statuses={Taxon("Plecotus austriacus"): Status.ABSENT})
    both_gone = one_gone.overridden({Taxon("Plecotus auritus"): Status.ABSENT})

    assert one_gone.present(plecotus)
    assert not both_gone.present(plecotus)


def test_absent_species_leave_a_group() -> None:
    opinion = ranked(({LEISLER, MURINUS}, 0.9))

    restricted = restrict(opinion, Region("test", statuses={MURINUS: Status.ABSENT}), 0.95)

    assert restricted.taxa == frozenset({LEISLER})


def test_a_rare_species_needs_a_high_score() -> None:
    opinion = ranked(({HORSESHOE}, 0.9), ({NOCTULE}, 0.6))
    rare = Region("test", statuses={HORSESHOE: Status.RARE})

    assert restrict(opinion, rare, rare_min_score=0.95).taxa == frozenset({NOCTULE})
    assert restrict(opinion, rare, rare_min_score=0.8).taxa == frozenset({HORSESHOE})


def test_a_group_with_a_common_member_is_not_rare() -> None:
    rare = Region("test", statuses={MURINUS: Status.RARE})

    assert not rare.rare(frozenset({LEISLER, MURINUS}))
    assert rare.rare(frozenset({MURINUS}))


def test_statuses_are_given_per_species(monkeypatch: pytest.MonkeyPatch) -> None:
    profiles = {
        "profiles": [
            {
                "id": "x",
                "name": "X",
                "bounds": None,
                "default": "occurs",
                "species": {"Myotis": "rare"},
            }
        ]
    }
    monkeypatch.setattr(region, "load_json", lambda name: profiles)
    region.profiles.cache_clear()
    try:
        with pytest.raises(ValueError, match="per species"):
            region.profiles()
    finally:
        region.profiles.cache_clear()
