"""Identify species with BatDetect2, a neural network that finds and labels calls.

BatDetect2 (Mac Aodha et al., UCL) boxes every echolocation call in a
recording and gives each a class. It was trained on British bats, so two
things are added here. Each class stands for the set of taxa it can mean
locally (see data/batdetect2_classes.json), and a recording's calls are
split by frequency into sources, one per animal, each with its own opinion:
one file often holds more than one bat.

The model itself is loaded on first use and only through `Model`; everything
else works on plain call lists and needs no network to test.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from nocek.core import taxonomy
from nocek.core._data import load_json
from nocek.core.opinion import Abstention, Candidate, Opinion
from nocek.core.taxonomy import Taxon

SOURCE = "batdetect2"


@dataclass(frozen=True)
class Params:
    # Below about 0.3 noise floods in.
    detection_threshold: float = 0.4
    # Sources are found as peaks in a histogram of call centre frequencies.
    cluster_floor_khz: float = 10.0
    cluster_bin_khz: float = 5.0
    # Peaks closer than this cannot be told from one bat's own spread.
    cluster_min_separation_khz: float = 8.0
    cluster_min_calls: int = 3
    cluster_min_share: float = 0.10
    # Calls voting this evenly between labels are one animal the model cannot
    # place, not two animals.
    min_agreement: float = 0.5
    # A species that rarely occurs in a region must score at least this. On
    # clean reference recordings the model's best call scores at worst 0.657,
    # so a rare bat has to look as convincing as a known one.
    rare_min_score: float = 0.65


DEFAULT_PARAMS = Params()


@dataclass(frozen=True)
class ClassInfo:
    taxa: frozenset[Taxon]
    low_khz: tuple[float, float]


@dataclass(frozen=True)
class Call:
    """One call as the model boxed and labelled it."""

    start_s: float
    end_s: float
    low_khz: float
    high_khz: float
    model_class: str
    class_prob: float
    det_prob: float

    @property
    def centre_khz(self) -> float:
        return (self.low_khz + self.high_khz) / 2


@dataclass(frozen=True)
class Source:
    """The calls of one animal, as far as frequency can tell, and their opinion."""

    calls: tuple[Call, ...]
    model_class: str
    centre_khz: float
    # Median low edge of the call boxes, close to the end frequency.
    low_khz: float
    # Distance between the frequency peaks merged into this source.
    spread_khz: float
    agreement: float
    opinion: Opinion


@dataclass(frozen=True)
class Analysis:
    sources: tuple[Source, ...]

    @property
    def n_calls(self) -> int:
        return sum(len(s.calls) for s in self.sources)


class BatDetectError(Exception):
    """The model failed on a recording."""


@cache
def classes() -> Mapping[str, ClassInfo]:
    """What each model class stands for."""
    return MappingProxyType(
        {
            name: ClassInfo(
                taxa=frozenset(taxonomy.get(t) for t in info["taxa"]),
                low_khz=(float(info["low_khz"][0]), float(info["low_khz"][1])),
            )
            for name, info in load_json("batdetect2_classes.json")["classes"].items()
        }
    )


def interpret(calls: Sequence[Call], params: Params = DEFAULT_PARAMS) -> Analysis:
    """Split calls into sources and give each an opinion."""
    unknown = {c.model_class for c in calls} - classes().keys()
    if unknown:
        raise ValueError(f"model classes missing from batdetect2_classes.json: {sorted(unknown)}")

    sources = _merge([_summarise(cluster) for cluster in _cluster(calls, params)], params)
    # Named sources first, then the ones with most calls.
    sources.sort(key=lambda s: (s.opinion.abstention is not None, -len(s.calls)))
    return Analysis(sources=tuple(sources))


class Model:
    """BatDetect2, loaded on first use."""

    def __init__(self, params: Params = DEFAULT_PARAMS, device: str | None = None) -> None:
        self.params = params
        self._device_name = device
        self._loaded: tuple[Any, Any, Any] | None = None

    @property
    def device(self) -> str:
        return str(self._load()[2])

    def analyse(self, path: Path) -> Analysis:
        from batdetect2.utils import detector_utils

        model, config, device = self._load()
        try:
            run = detector_utils.process_file(str(path), model, config, device)
        except Exception as error:  # the model raises anything from torch to librosa
            raise BatDetectError(f"{path.name}: {error}") from error
        calls = [
            Call(
                start_s=float(a["start_time"]),
                end_s=float(a["end_time"]),
                low_khz=float(a["low_freq"]) / 1000,
                high_khz=float(a["high_freq"]) / 1000,
                model_class=str(a["class"]),
                class_prob=float(a["class_prob"]),
                det_prob=float(a["det_prob"]),
            )
            for a in run["pred_dict"]["annotation"]
            if a.get("event", "Echolocation") == "Echolocation"
        ]
        return interpret(calls, self.params)

    def _load(self) -> tuple[Any, Any, Any]:
        if self._loaded is None:
            import torch
            from batdetect2.detector import parameters
            from batdetect2.utils import detector_utils

            device = torch.device(self._device_name or _best_device())
            model, model_params = detector_utils.load_model(
                parameters.DEFAULT_MODEL_PATH, device=device
            )
            config = {
                **parameters.DEFAULT_PROCESSING_CONFIGURATIONS,
                **model_params,
                "detection_threshold": self.params.detection_threshold,
                "max_duration": None,
            }
            self._loaded = (model, config, device)
        return self._loaded


def _best_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    # Apple GPUs: about four times faster than the CPU, with the same calls.
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _cluster(calls: Sequence[Call], params: Params) -> list[list[Call]]:
    """Split calls into one group per animal, by centre frequency.

    Labels alone do not separate animals: the model jitters between
    neighbouring classes on a single bat. Frequency does, because jitter does
    not move a call and a second animal does.
    """
    if not calls:
        return []
    n = len(calls)
    counts: dict[int, int] = {}
    for c in calls:
        b = _bin(c.centre_khz, params)
        counts[b] = counts.get(b, 0) + 1

    peaks = [
        (count, params.cluster_floor_khz + (b + 0.5) * params.cluster_bin_khz)
        for b, count in counts.items()
        if count >= params.cluster_min_calls
        and count / n >= params.cluster_min_share
        and count >= counts.get(b - 1, 0)
        and count >= counts.get(b + 1, 0)
    ]
    centres: list[float] = []
    for _, centre in sorted(peaks, reverse=True):
        if all(abs(centre - k) >= params.cluster_min_separation_khz for k in centres):
            centres.append(centre)
    if not centres:
        centres = [_upper_median([c.centre_khz for c in calls])]

    groups: list[list[Call]] = [[] for _ in centres]
    for c in calls:
        nearest = min(range(len(centres)), key=lambda k: abs(c.centre_khz - centres[k]))
        groups[nearest].append(c)
    return [g for g in groups if g]


def _bin(khz: float, params: Params) -> int:
    return int((khz - params.cluster_floor_khz) // params.cluster_bin_khz)


@dataclass
class _Summary:
    calls: list[Call]
    taxa: frozenset[Taxon]
    model_class: str
    centres_khz: list[float]
    low_khz: float
    max_prob: float
    agreement: float


def _summarise(calls: list[Call]) -> _Summary:
    """The label one cluster votes for, weighted by class probability."""
    votes: dict[frozenset[Taxon], float] = {}
    for c in calls:
        taxa = classes()[c.model_class].taxa
        votes[taxa] = votes.get(taxa, 0.0) + c.class_prob
    best = max(votes, key=lambda t: votes[t])
    in_best = [c for c in calls if classes()[c.model_class].taxa == best]
    by_class: dict[str, float] = {}
    for c in in_best:
        by_class[c.model_class] = by_class.get(c.model_class, 0.0) + c.class_prob
    return _Summary(
        calls=calls,
        taxa=best,
        model_class=max(by_class, key=lambda k: by_class[k]),
        centres_khz=[_upper_median([c.centre_khz for c in calls])],
        low_khz=_upper_median([c.low_khz for c in calls]),
        max_prob=max(c.class_prob for c in calls),
        agreement=votes[best] / sum(votes.values()),
    )


def _merge(summaries: list[_Summary], params: Params) -> list[Source]:
    """Clusters with the same label are one source: two individuals, or one bat
    boxed inconsistently, and the data cannot tell which."""
    merged: dict[frozenset[Taxon], _Summary] = {}
    for s in summaries:
        m = merged.get(s.taxa)
        if m is None:
            merged[s.taxa] = s
            continue
        n_m, n_s = len(m.calls), len(s.calls)
        m.agreement = (m.agreement * n_m + s.agreement * n_s) / (n_m + n_s)
        m.low_khz = (m.low_khz * n_m + s.low_khz * n_s) / (n_m + n_s)
        m.max_prob = max(m.max_prob, s.max_prob)
        m.centres_khz += s.centres_khz
        m.calls = m.calls + s.calls
    return [_source(s, params) for s in merged.values()]


def _source(s: _Summary, params: Params) -> Source:
    low, high = classes()[s.model_class].low_khz
    declined = None
    if not low <= s.low_khz <= high:
        declined = Abstention.OUT_OF_BAND
    elif s.agreement < params.min_agreement:
        declined = Abstention.INCONCLUSIVE
    candidate = Candidate(
        taxa=s.taxa,
        score=s.max_prob,
        evidence={"agreement": s.agreement, "low_khz": s.low_khz},
    )
    return Source(
        calls=tuple(sorted(s.calls, key=lambda c: c.start_s)),
        model_class=s.model_class,
        centre_khz=s.centres_khz[0],
        low_khz=s.low_khz,
        spread_khz=max(s.centres_khz) - min(s.centres_khz),
        agreement=s.agreement,
        opinion=Opinion(
            source=SOURCE,
            ranking=(candidate,),
            min_score=0.0,
            shortlist_ratio=1.0,
            declined=declined,
        ),
    )


def _upper_median(values: list[float]) -> float:
    """The middle value, or the upper of the two middle ones."""
    return sorted(values)[len(values) // 2]
