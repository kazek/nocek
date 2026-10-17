"""Small builders for the values the passes exchange, so tests read as cases."""

from __future__ import annotations

from nyctalus.core.batdetect import Call
from nyctalus.core.detection import Detection, DominantGroup, Pulse, Shape
from nyctalus.core.opinion import Candidate, Opinion
from nyctalus.core.taxonomy import Taxon


def calls(model_class: str, low_khz: float, n: int = 10, prob: float = 0.8) -> list[Call]:
    """n BatDetect2 calls one tenth of a second apart, boxed from low_khz to 15 kHz above."""
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


def measured(
    end_khz: float,
    duration_ms: float = 6.0,
    interval_ms: float | None = 100.0,
    n_pulses: int = 10,
    energy_share: float = 1.0,
) -> Detection:
    """A detection whose dominant group has these medians."""
    pulse = Pulse(
        start_s=0.0,
        duration_ms=duration_ms,
        peak_khz=end_khz,
        start_khz=end_khz + 10,
        end_khz=end_khz,
        low_khz=end_khz,
        high_khz=end_khz + 10,
        snr_db=30.0,
        narrowness=0.8,
        shape=Shape.FM_QCF,
    )
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
    return Detection(
        sample_rate=384_000, duration_s=5.0, pulses=(pulse,) * n_pulses, dominant=group
    )


def opinion(*names: str, score: float = 1.0, source: str = "test") -> Opinion:
    """An opinion naming one candidate standing for the given taxa."""
    taxa = frozenset(Taxon(n) for n in names)
    return Opinion(
        source=source,
        ranking=(Candidate(taxa=taxa, score=score),) if taxa else (),
        min_score=0.5,
        shortlist_ratio=1.0,
    )
