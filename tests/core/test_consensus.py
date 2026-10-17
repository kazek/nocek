from nocek.core.batdetect import interpret
from nocek.core.consensus import Agreement, Note, combine, group_of
from nocek.core.opinion import Abstention
from nocek.core.region import Region, Status
from nocek.core.taxonomy import Taxon
from tests.core.factories import calls, measured, opinion

ANYWHERE = Region("anywhere")
LEISLER_GROUP = frozenset(
    {Taxon("Nyctalus leisleri"), Taxon("Vespertilio murinus"), Taxon("Eptesicus nilssonii")}
)


def test_names_what_batdetect2_names() -> None:
    sources = interpret(calls("Nyctalus noctula", low_khz=20))

    (verdict,) = combine(ANYWHERE, sources, measured(end_khz=20)).sources

    assert verdict.taxa == frozenset({Taxon("Nyctalus noctula")})
    assert verdict.reasons == ()
    assert verdict.agreement == Agreement(agreeing=1, named=1)


def test_needs_the_detector_to_have_found_calls() -> None:
    sources = interpret(calls("Nyctalus noctula", low_khz=20))

    (verdict,) = combine(ANYWHERE, sources, measured(end_khz=20, n_pulses=2)).sources

    assert verdict.taxa is None
    assert verdict.reasons == (Abstention.UNCORROBORATED,)


def test_two_passes_agreeing_on_another_animal_withhold_the_name() -> None:
    sources = interpret(calls("Nyctalus leisleri", low_khz=21))

    (verdict,) = combine(
        ANYWHERE,
        sources,
        measured(end_khz=20),
        key_opinion=opinion("Nyctalus noctula"),
        battybird_opinion=opinion("Nyctalus noctula"),
    ).sources

    assert verdict.taxa is None
    assert verdict.reasons == (Abstention.CONTRADICTED,)
    assert verdict.agreement == Agreement(agreeing=1, named=3)


def test_one_pass_against_one_is_a_disagreement_not_a_finding() -> None:
    sources = interpret(calls("Nyctalus leisleri", low_khz=21))

    (verdict,) = combine(
        ANYWHERE,
        sources,
        measured(end_khz=20),
        key_opinion=opinion("Nyctalus noctula"),
        battybird_opinion=opinion("Nyctalus leisleri"),
    ).sources

    assert verdict.taxa == LEISLER_GROUP
    assert verdict.agreement == Agreement(agreeing=2, named=3)


def test_members_of_one_group_agree() -> None:
    # No pass has shown it can tell these apart, so naming different ones is agreement.
    sources = interpret(calls("Nyctalus leisleri", low_khz=24))

    (verdict,) = combine(
        ANYWHERE,
        sources,
        measured(end_khz=24),
        key_opinion=opinion("Vespertilio murinus"),
        battybird_opinion=opinion("Eptesicus nilssonii"),
    ).sources

    assert verdict.taxa == LEISLER_GROUP
    assert verdict.agreement == Agreement(agreeing=3, named=3)


def test_battybird_speaks_only_for_a_file_with_one_animal() -> None:
    sources = interpret(
        calls("Pipistrellus pipistrellus", low_khz=45) + calls("Nyctalus noctula", low_khz=20)
    )

    verdicts = combine(
        ANYWHERE, sources, measured(end_khz=20), battybird_opinion=opinion("Nyctalus noctula")
    ).sources

    assert all(v.battybird is None for v in verdicts)
    assert len(combine(ANYWHERE, sources).named) == 2


def test_the_key_speaks_for_the_source_at_its_frequency() -> None:
    sources = interpret(
        calls("Pipistrellus pipistrellus", low_khz=45) + calls("Nyctalus noctula", low_khz=20)
    )

    verdicts = combine(
        ANYWHERE, sources, measured(end_khz=46), key_opinion=opinion("Pipistrellus pipistrellus")
    ).sources

    keyed = [v.source.model_class for v in verdicts if v.key is not None]
    assert keyed == ["Pipistrellus pipistrellus"]


def test_the_key_speaks_for_no_source_far_from_its_frequency() -> None:
    sources = interpret(calls("Nyctalus noctula", low_khz=20))

    (verdict,) = combine(
        ANYWHERE, sources, measured(end_khz=46), key_opinion=opinion("Pipistrellus pipistrellus")
    ).sources

    assert verdict.key is None


def test_a_rare_species_needs_a_confident_model() -> None:
    rare = Region("test", statuses={Taxon("Rhinolophus hipposideros"): Status.RARE})
    weak = interpret(calls("Rhinolophus hipposideros", low_khz=100, prob=0.6))
    strong = interpret(calls("Rhinolophus hipposideros", low_khz=100, prob=0.7))

    (withheld,) = combine(rare, weak).sources
    (named,) = combine(rare, strong).sources

    assert withheld.reasons == (Abstention.RULED_OUT,)
    assert named.taxa == frozenset({Taxon("Rhinolophus hipposideros")})


def test_absent_species_narrow_the_name() -> None:
    no_murinus = Region("test", statuses={Taxon("Vespertilio murinus"): Status.ABSENT})

    (verdict,) = combine(no_murinus, interpret(calls("Nyctalus leisleri", low_khz=24))).sources

    assert verdict.taxa == frozenset({Taxon("Nyctalus leisleri"), Taxon("Eptesicus nilssonii")})


def test_notes_a_measurement_that_points_to_another_pipistrelle() -> None:
    sources = interpret(calls("Pipistrellus nathusii", low_khz=45))

    (verdict,) = combine(ANYWHERE, sources, measured(end_khz=46)).sources

    assert verdict.notes == (Note.MEASURED_LIKE_COMMON_PIPISTRELLE,)
    assert verdict.taxa is not None  # a note, not a change of name


def test_group_of() -> None:
    assert group_of([Taxon("Pipistrellus kuhlii")]) == frozenset(
        {Taxon("Pipistrellus nathusii"), Taxon("Pipistrellus kuhlii")}
    )
    assert group_of([Taxon("Myotis daubentonii")]) == frozenset({Taxon("Myotis")})
    assert group_of([Taxon("Nyctalus noctula")]) == frozenset({Taxon("Nyctalus noctula")})
    assert group_of([Taxon("Nyctalus noctula"), Taxon("Nyctalus leisleri")]) is None
    assert group_of(None) is None
