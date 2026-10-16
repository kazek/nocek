from nyctalus.core.opinion import Abstention, Candidate, Opinion
from nyctalus.core.taxonomy import Taxon

NOCTULE = Taxon("Nyctalus noctula")
LEISLER = Taxon("Nyctalus leisleri")
SEROTINE = Taxon("Eptesicus serotinus")


def opinion(*ranking: tuple[Taxon, float], declined: Abstention | None = None) -> Opinion:
    return Opinion(
        source="test",
        ranking=tuple(Candidate(frozenset({t}), score) for t, score in ranking),
        min_score=0.5,
        shortlist_ratio=0.9,
        declined=declined,
    )


def test_names_the_leader_and_everything_close_to_it() -> None:
    o = opinion((NOCTULE, 1.0), (LEISLER, 0.95), (SEROTINE, 0.6))

    assert o.leader is not None
    assert o.leader.taxa == {NOCTULE}
    assert o.taxa == frozenset({NOCTULE, LEISLER})
    assert o.abstention is None


def test_declined_before_scoring() -> None:
    o = opinion(declined=Abstention.TOO_FEW_PULSES)

    assert o.abstention is Abstention.TOO_FEW_PULSES
    assert o.taxa is None


def test_nothing_left_is_ruled_out() -> None:
    o = opinion()

    assert o.leader is None
    assert o.abstention is Abstention.RULED_OUT
    assert o.taxa is None


def test_a_weak_leader_is_no_match() -> None:
    o = opinion((NOCTULE, 0.4))

    assert o.abstention is Abstention.NO_MATCH
    assert o.taxa is None


def test_excluding_redraws_the_conclusion() -> None:
    o = opinion((NOCTULE, 1.0), (LEISLER, 0.8), (SEROTINE, 0.75))

    without = o.excluding(lambda c: NOCTULE in c.taxa)

    assert without.taxa == frozenset({LEISLER, SEROTINE})
    assert o.taxa == frozenset({NOCTULE})
