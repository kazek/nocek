from pathlib import Path

import pytest
import soundfile as sf

from nyctalus.core import batdetect, taxonomy
from nyctalus.core.batdetect import Call, interpret
from nyctalus.core.opinion import Abstention
from nyctalus.core.taxonomy import Taxon
from tests import synth


def calls(model_class: str, low_khz: float, n: int = 10, prob: float = 0.8) -> list[Call]:
    """n calls one tenth of a second apart, boxed from low_khz to 15 kHz above."""
    return [
        Call(
            start_s=i * 0.1,
            end_s=i * 0.1 + 0.005,
            low_khz=low_khz,
            high_khz=low_khz + 15,
            model_class=model_class,
            class_prob=prob,
            det_prob=0.9,
        )
        for i in range(n)
    ]


def test_every_class_stands_for_catalogued_taxa() -> None:
    known = set(taxonomy.species()) | set(taxonomy.genera())

    for info in batdetect.classes().values():
        assert info.taxa <= known
        assert info.low_khz[0] < info.low_khz[1]


def test_no_calls_no_sources() -> None:
    analysis = interpret([])

    assert analysis.sources == ()
    assert analysis.n_calls == 0


def test_names_one_bat() -> None:
    analysis = interpret(calls("Pipistrellus pipistrellus", low_khz=45, prob=0.9))

    (source,) = analysis.sources
    assert source.opinion.source == batdetect.SOURCE
    assert source.opinion.taxa == frozenset({Taxon("Pipistrellus pipistrellus")})
    assert source.opinion.leader is not None
    assert source.opinion.leader.score == pytest.approx(0.9)
    assert source.agreement == pytest.approx(1.0)
    assert len(source.calls) == 10


def test_a_class_stands_for_the_species_the_model_lacks() -> None:
    (source,) = interpret(calls("Pipistrellus nathusii", low_khz=38)).sources

    assert source.opinion.taxa == frozenset(
        {Taxon("Pipistrellus nathusii"), Taxon("Pipistrellus kuhlii")}
    )


def test_jitter_between_classes_is_one_bat() -> None:
    noctule = calls("Nyctalus noctula", low_khz=20, n=10)
    jitter = calls("Nyctalus leisleri", low_khz=20, n=2, prob=0.5)

    (source,) = interpret(noctule + jitter).sources

    assert source.model_class == "Nyctalus noctula"
    assert len(source.calls) == 12
    assert source.agreement == pytest.approx(8.0 / 9.0)


def test_separates_two_bats_by_frequency() -> None:
    analysis = interpret(
        calls("Pipistrellus pipistrellus", low_khz=45) + calls("Nyctalus noctula", low_khz=20)
    )

    assert {s.model_class for s in analysis.sources} == {
        "Pipistrellus pipistrellus",
        "Nyctalus noctula",
    }
    assert analysis.n_calls == 20


def test_plecotus_is_reported_to_genus() -> None:
    mixed = calls("Plecotus auritus", low_khz=25, n=6) + calls(
        "Plecotus austriacus", low_khz=25, n=4
    )

    (source,) = interpret(mixed).sources

    assert source.opinion.taxa == frozenset({Taxon("Plecotus")})
    assert source.agreement == pytest.approx(1.0)


def test_a_label_its_frequency_contradicts_is_withheld() -> None:
    (source,) = interpret(calls("Nyctalus noctula", low_khz=45)).sources

    assert source.opinion.abstention is Abstention.OUT_OF_BAND
    assert source.opinion.taxa is None
    assert source.opinion.leader is not None  # still shown, just not named


def test_a_split_vote_is_inconclusive() -> None:
    # No label carries half the votes: 4 / 4 / 3.
    split = (
        calls("Eptesicus serotinus", low_khz=25, n=4)
        + calls("Nyctalus leisleri", low_khz=25, n=4)
        + calls("Nyctalus noctula", low_khz=25, n=3)
    )

    (source,) = interpret(split).sources

    assert source.agreement < 0.5
    assert source.opinion.abstention is Abstention.INCONCLUSIVE


def test_an_unknown_class_is_an_error() -> None:
    with pytest.raises(ValueError, match="Pteropus"):
        interpret(calls("Pteropus vampyrus", low_khz=30))


@pytest.mark.slow
def test_runs_the_real_model(tmp_path: Path) -> None:
    path = tmp_path / "pipistrelle.wav"
    sf.write(path, synth.sequence(synth.sweep(60, 46, 0.006), n=20), synth.SAMPLE_RATE)

    analysis = batdetect.Model(device="cpu").analyse(path)

    assert isinstance(analysis, batdetect.Analysis)
