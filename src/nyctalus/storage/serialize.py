"""A recording's result as plain JSON-compatible data, and back.

The format is written out field by field rather than derived from the
classes, so renaming something in the code cannot silently change what is
stored, and results saved by an older version stay readable. FORMAT goes up
whenever the shape changes; `result_from_dict` refuses formats it does not
know.

Taxa are stored by scientific name and enums by value. A verdict refers to
BatDetect2's sources by position instead of repeating them.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any

from nyctalus.core import batdetect, battybird
from nyctalus.core.consensus import Agreement, Note, SourceVerdict, Verdict
from nyctalus.core.detection import Detection, DominantGroup, Pulse, Shape
from nyctalus.core.opinion import Abstention, Candidate, Opinion
from nyctalus.core.pipeline import Failure, Pass, RecordingResult, Skipped
from nyctalus.core.taxonomy import Taxon

FORMAT = 1

Data = dict[str, Any]


class FormatError(ValueError):
    """Stored data this version cannot read."""


def result_to_dict(r: RecordingResult) -> Data:
    sources = r.batdetect.sources if r.batdetect else ()
    return {
        "format": FORMAT,
        "path": str(r.path),
        "versions": dict(r.versions),
        "sample_rate": r.sample_rate,
        "duration_s": r.duration_s,
        "detection": _detection(r.detection) if r.detection else None,
        "key": _opinion(r.key) if r.key else None,
        "batdetect": [_source(s) for s in sources] if r.batdetect else None,
        "battybird": _battybird(r.battybird) if r.battybird else None,
        "verdict": [_source_verdict(v, sources) for v in r.verdict.sources] if r.verdict else None,
        "skipped": {str(p): str(why) for p, why in r.skipped.items()},
        "failures": [{"stage": f.stage, "message": f.message} for f in r.failures],
    }


def result_from_dict(d: Data) -> RecordingResult:
    if d.get("format") != FORMAT:
        raise FormatError(f"result format {d.get('format')!r}, this version reads {FORMAT}")
    sources = (
        batdetect.Analysis(sources=tuple(_source_from(s) for s in d["batdetect"]))
        if d["batdetect"] is not None
        else None
    )
    verdict = None
    if d["verdict"] is not None:
        if sources is None:
            raise FormatError("a verdict without BatDetect2 sources")
        verdict = Verdict(
            sources=tuple(_source_verdict_from(v, sources.sources) for v in d["verdict"])
        )
    return RecordingResult(
        path=Path(d["path"]),
        versions=MappingProxyType(dict(d["versions"])),
        sample_rate=d["sample_rate"],
        duration_s=d["duration_s"],
        detection=_detection_from(d["detection"]) if d["detection"] else None,
        key=_opinion_from(d["key"]) if d["key"] else None,
        batdetect=sources,
        battybird=_battybird_from(d["battybird"]) if d["battybird"] else None,
        verdict=verdict,
        skipped=MappingProxyType({Pass(p): Skipped(w) for p, w in d["skipped"].items()}),
        failures=tuple(Failure(f["stage"], f["message"]) for f in d["failures"]),
    )


# --- Detection ---------------------------------------------------------------


def _detection(x: Detection) -> Data:
    return {
        "sample_rate": x.sample_rate,
        "duration_s": x.duration_s,
        "pulses": [_pulse(p) for p in x.pulses],
        "dominant": _dominant(x.dominant) if x.dominant else None,
    }


def _detection_from(d: Data) -> Detection:
    return Detection(
        sample_rate=d["sample_rate"],
        duration_s=d["duration_s"],
        pulses=tuple(_pulse_from(p) for p in d["pulses"]),
        dominant=_dominant_from(d["dominant"]) if d["dominant"] else None,
    )


def _pulse(p: Pulse) -> Data:
    return {
        "start_s": p.start_s,
        "duration_ms": p.duration_ms,
        "peak_khz": p.peak_khz,
        "start_khz": p.start_khz,
        "end_khz": p.end_khz,
        "low_khz": p.low_khz,
        "high_khz": p.high_khz,
        "snr_db": p.snr_db,
        "narrowness": p.narrowness,
        "shape": str(p.shape),
    }


def _pulse_from(d: Data) -> Pulse:
    return Pulse(
        start_s=d["start_s"],
        duration_ms=d["duration_ms"],
        peak_khz=d["peak_khz"],
        start_khz=d["start_khz"],
        end_khz=d["end_khz"],
        low_khz=d["low_khz"],
        high_khz=d["high_khz"],
        snr_db=d["snr_db"],
        narrowness=d["narrowness"],
        shape=Shape(d["shape"]),
    )


def _dominant(g: DominantGroup) -> Data:
    return {
        "n_pulses": g.n_pulses,
        "energy_share": g.energy_share,
        "peak_khz": g.peak_khz,
        "end_khz": g.end_khz,
        "duration_ms": g.duration_ms,
        "best_snr_db": g.best_snr_db,
        "interval_ms": g.interval_ms,
        "interval_spread": g.interval_spread,
    }


def _dominant_from(d: Data) -> DominantGroup:
    return DominantGroup(
        n_pulses=d["n_pulses"],
        energy_share=d["energy_share"],
        peak_khz=d["peak_khz"],
        end_khz=d["end_khz"],
        duration_ms=d["duration_ms"],
        best_snr_db=d["best_snr_db"],
        interval_ms=d["interval_ms"],
        interval_spread=d["interval_spread"],
    )


# --- Opinions ----------------------------------------------------------------


def _taxa(taxa: frozenset[Taxon]) -> list[str]:
    return sorted(t.name for t in taxa)


def _taxa_from(names: list[str]) -> frozenset[Taxon]:
    # Not checked against the catalogue: a stored result records what was
    # said, even about a name the catalogue has since dropped.
    return frozenset(Taxon(n) for n in names)


def _candidate(c: Candidate) -> Data:
    return {"taxa": _taxa(c.taxa), "score": c.score, "evidence": dict(c.evidence)}


def _candidate_from(d: Data) -> Candidate:
    return Candidate(taxa=_taxa_from(d["taxa"]), score=d["score"], evidence=d["evidence"])


def _opinion(o: Opinion) -> Data:
    return {
        "source": o.source,
        "ranking": [_candidate(c) for c in o.ranking],
        "min_score": o.min_score,
        "shortlist_ratio": o.shortlist_ratio,
        "declined": str(o.declined) if o.declined else None,
    }


def _opinion_from(d: Data) -> Opinion:
    return Opinion(
        source=d["source"],
        ranking=tuple(_candidate_from(c) for c in d["ranking"]),
        min_score=d["min_score"],
        shortlist_ratio=d["shortlist_ratio"],
        declined=Abstention(d["declined"]) if d["declined"] else None,
    )


# --- BatDetect2 --------------------------------------------------------------


def _call(c: batdetect.Call) -> Data:
    return {
        "start_s": c.start_s,
        "end_s": c.end_s,
        "low_khz": c.low_khz,
        "high_khz": c.high_khz,
        "model_class": c.model_class,
        "class_prob": c.class_prob,
        "det_prob": c.det_prob,
    }


def _call_from(d: Data) -> batdetect.Call:
    return batdetect.Call(
        start_s=d["start_s"],
        end_s=d["end_s"],
        low_khz=d["low_khz"],
        high_khz=d["high_khz"],
        model_class=d["model_class"],
        class_prob=d["class_prob"],
        det_prob=d["det_prob"],
    )


def _source(s: batdetect.Source) -> Data:
    return {
        "calls": [_call(c) for c in s.calls],
        "model_class": s.model_class,
        "centre_khz": s.centre_khz,
        "low_khz": s.low_khz,
        "spread_khz": s.spread_khz,
        "agreement": s.agreement,
        "opinion": _opinion(s.opinion),
    }


def _source_from(d: Data) -> batdetect.Source:
    return batdetect.Source(
        calls=tuple(_call_from(c) for c in d["calls"]),
        model_class=d["model_class"],
        centre_khz=d["centre_khz"],
        low_khz=d["low_khz"],
        spread_khz=d["spread_khz"],
        agreement=d["agreement"],
        opinion=_opinion_from(d["opinion"]),
    )


# --- BattyBirdNET ------------------------------------------------------------


def _battybird(a: battybird.Analysis) -> Data:
    return {
        "opinion": _opinion(a.opinion),
        "not_a_bat": [{"label": s.label, "score": s.score} for s in a.not_a_bat],
        "windows": [
            {"start_s": w.start_s, "leader": _candidate(w.leader) if w.leader else None}
            for w in a.windows
        ],
    }


def _battybird_from(d: Data) -> battybird.Analysis:
    return battybird.Analysis(
        opinion=_opinion_from(d["opinion"]),
        not_a_bat=tuple(battybird.Sound(s["label"], s["score"]) for s in d["not_a_bat"]),
        windows=tuple(
            battybird.Window(
                start_s=w["start_s"],
                leader=_candidate_from(w["leader"]) if w["leader"] else None,
            )
            for w in d["windows"]
        ),
    )


# --- Verdict -----------------------------------------------------------------


def _source_verdict(v: SourceVerdict, sources: tuple[batdetect.Source, ...]) -> Data:
    return {
        "source": next(i for i, s in enumerate(sources) if s is v.source),
        "taxa": _taxa(v.taxa) if v.taxa is not None else None,
        "reasons": [str(r) for r in v.reasons],
        "notes": [str(n) for n in v.notes],
        "agreement": {"agreeing": v.agreement.agreeing, "named": v.agreement.named},
        "key": _opinion(v.key) if v.key else None,
        "battybird": _opinion(v.battybird) if v.battybird else None,
    }


def _source_verdict_from(d: Data, sources: tuple[batdetect.Source, ...]) -> SourceVerdict:
    return SourceVerdict(
        source=sources[d["source"]],
        taxa=_taxa_from(d["taxa"]) if d["taxa"] is not None else None,
        reasons=tuple(Abstention(r) for r in d["reasons"]),
        notes=tuple(Note(n) for n in d["notes"]),
        agreement=Agreement(d["agreement"]["agreeing"], d["agreement"]["named"]),
        key=_opinion_from(d["key"]) if d["key"] else None,
        battybird=_opinion_from(d["battybird"]) if d["battybird"] else None,
    )
