import pytest

from nocek.core import key, taxonomy
from nocek.core.detection import Detection
from nocek.core.opinion import Abstention
from nocek.core.taxonomy import Taxon
from tests.core.factories import measured


def test_every_band_names_a_catalogued_taxon() -> None:
    known = set(taxonomy.species()) | set(taxonomy.genera())

    assert set(key.bands()) <= known
    assert Taxon("Myotis") in key.bands()


def test_names_a_common_pipistrelle() -> None:
    opinion = key.identify(measured(end_khz=50, duration_ms=6, interval_ms=100))

    assert opinion.source == key.SOURCE
    assert opinion.taxa == frozenset({Taxon("Pipistrellus pipistrellus")})
    assert opinion.leader is not None
    assert opinion.leader.score == pytest.approx(1.0)


def test_overlapping_bands_give_several_taxa() -> None:
    opinion = key.identify(measured(end_khz=38, duration_ms=8, interval_ms=120))

    assert opinion.taxa is not None
    assert {Taxon("Pipistrellus nathusii"), Taxon("Pipistrellus kuhlii")} <= opinion.taxa


def test_a_genus_can_share_the_lead() -> None:
    # Myotis calls overlap common pipistrelles at this frequency and length.
    opinion = key.identify(measured(end_khz=46, duration_ms=6, interval_ms=100))

    assert opinion.taxa == frozenset({Taxon("Pipistrellus pipistrellus"), Taxon("Myotis")})


def test_noctule() -> None:
    opinion = key.identify(measured(end_khz=20, duration_ms=18, interval_ms=300))

    assert opinion.leader is not None
    assert opinion.leader.taxa == {Taxon("Nyctalus noctula")}


def test_needs_three_pulses() -> None:
    opinion = key.identify(measured(end_khz=46, duration_ms=6, interval_ms=None, n_pulses=2))

    assert opinion.abstention is Abstention.TOO_FEW_PULSES


def test_no_calls_at_all() -> None:
    detection = Detection(sample_rate=384_000, duration_s=5.0, pulses=(), dominant=None)

    assert key.identify(detection).abstention is Abstention.TOO_FEW_PULSES


def test_declines_when_several_sources_call() -> None:
    opinion = key.identify(measured(end_khz=46, duration_ms=6, interval_ms=100, energy_share=0.5))

    assert opinion.abstention is Abstention.MIXED_SOURCES


def test_a_far_miss_rules_a_species_out() -> None:
    # A 3 ms pulse at a horseshoe bat's frequency is not a horseshoe bat,
    # however well the frequency fits.
    opinion = key.identify(measured(end_khz=80, duration_ms=3, interval_ms=100))

    assert all(Taxon("Rhinolophus ferrumequinum") not in c.taxa for c in opinion.ranking)


def test_nothing_fits() -> None:
    opinion = key.identify(measured(end_khz=200, duration_ms=200, interval_ms=2000))

    assert opinion.abstention is Abstention.RULED_OUT


def test_a_short_interval_is_ignored_not_counted_against() -> None:
    # Approaching prey shortens the interval, which says nothing about species.
    opinion = key.identify(measured(end_khz=50, duration_ms=6, interval_ms=20))

    assert opinion.leader is not None
    assert opinion.leader.taxa == {Taxon("Pipistrellus pipistrellus")}
    assert opinion.leader.evidence["interval_ms"] is None


def test_a_missing_interval_is_judged_on_the_rest() -> None:
    opinion = key.identify(measured(end_khz=50, duration_ms=6, interval_ms=None))

    assert opinion.leader is not None
    assert opinion.leader.score == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(25.0, 1.0), (20.0, 1.0), (30.0, 1.0), (31.25, 0.5), (32.5, 0.0), (40.0, 0.0)],
)
def test_fit(value: float, expected: float) -> None:
    assert key.fit(value, (20.0, 30.0), tolerance=0.25) == pytest.approx(expected)


def test_params_are_hashable() -> None:
    assert hash(key.Params()) == hash(key.Params())


@pytest.mark.parametrize("band", [[23, 17], [17], [17, 20, 23]])
def test_rejects_a_malformed_band(monkeypatch: pytest.MonkeyPatch, band: list[float]) -> None:
    bad = {
        "taxa": {
            "Nyctalus noctula": {
                "end_khz": band,
                "duration_ms": [10, 25],
                "interval_ms": [180, 450],
            }
        }
    }
    monkeypatch.setattr(key, "load_json", lambda name: bad)
    key.bands.cache_clear()
    try:
        with pytest.raises(ValueError, match="Nyctalus noctula"):
            key.bands()
    finally:
        key.bands.cache_clear()


def test_an_interval_alone_does_not_rule_a_species_out() -> None:
    # Missed pulses double the interval; the call itself still fits.
    opinion = key.identify(measured(end_khz=50, duration_ms=6, interval_ms=300))

    assert opinion.leader is not None
    assert opinion.leader.taxa == {Taxon("Pipistrellus pipistrellus")}
    assert opinion.leader.evidence["interval_ms"] == 0.0
    assert opinion.leader.score < 1.0
