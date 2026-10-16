import pytest

from nyctalus.core import key, taxonomy
from nyctalus.core.detection import Detection, DominantGroup
from nyctalus.core.opinion import Abstention
from nyctalus.core.taxonomy import Taxon


def measured(
    end_khz: float,
    duration_ms: float,
    interval_ms: float | None,
    n_pulses: int = 10,
    energy_share: float = 1.0,
) -> Detection:
    group = DominantGroup(
        n_pulses=n_pulses,
        energy_share=energy_share,
        peak_khz=end_khz,
        end_khz=end_khz,
        duration_ms=duration_ms,
        best_snr_db=30.0,
        interval_ms=interval_ms,
        interval_spread=0.1,
    )
    return Detection(sample_rate=384_000, duration_s=5.0, pulses=(), dominant=group)


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
