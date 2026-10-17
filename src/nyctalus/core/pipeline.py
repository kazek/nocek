"""Run every pass over one recording and combine them into a verdict.

The audio is read once. The detector always runs; it is cheap and it is the
sieve: a recording in which it finds no pulse at all is not given to the
networks. BattyBirdNET, the slowest pass, runs only when BatDetect2 found a
source, since it can only bear on a verdict about one. A pass that fails is
recorded and the verdict is drawn from the passes that worked.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from importlib import metadata
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from nyctalus import __version__
from nyctalus.core import audio, batdetect, battybird, consensus, detection, key
from nyctalus.core.audio import Audio
from nyctalus.core.consensus import Verdict
from nyctalus.core.detection import Detection
from nyctalus.core.opinion import Opinion
from nyctalus.core.region import Region


class Pass(StrEnum):
    KEY = key.SOURCE
    BATDETECT2 = batdetect.SOURCE
    BATTYBIRDNET = battybird.SOURCE


class Skipped(StrEnum):
    """Why a pass did not run on a recording."""

    DISABLED = "disabled"
    NO_PULSES = "no-pulses"  # the detector found nothing for a network to look at
    NO_SOURCES = "no-sources"  # BatDetect2 found no animal for BattyBirdNET to speak about
    FAILED_EARLIER = "failed-earlier"  # a step it depends on failed


@dataclass(frozen=True)
class Failure:
    stage: str
    message: str


@dataclass(frozen=True)
class Settings:
    passes: frozenset[Pass] = frozenset(Pass)
    sieve: bool = True
    detection: detection.Params = detection.DEFAULT_PARAMS
    key: key.Params = key.DEFAULT_PARAMS
    batdetect: batdetect.Params = batdetect.DEFAULT_PARAMS
    battybird: battybird.Params = battybird.DEFAULT_PARAMS
    consensus: consensus.Params = consensus.DEFAULT_PARAMS


DEFAULT_SETTINGS = Settings()


class BatDetectModel(Protocol):
    @property
    def device(self) -> str: ...

    def analyse(self, path: Path) -> batdetect.Analysis: ...


class BattyBirdModel(Protocol):
    def analyse(self, audio: Audio) -> battybird.Analysis: ...


# eq=False: the result holds arrays deep inside and is compared by identity.
@dataclass(frozen=True, eq=False)
class RecordingResult:
    path: Path
    # What produced the result, so results from older models can be found.
    versions: Mapping[str, str]
    sample_rate: int | None = None
    duration_s: float | None = None
    detection: Detection | None = None
    key: Opinion | None = None
    batdetect: batdetect.Analysis | None = None
    battybird: battybird.Analysis | None = None
    verdict: Verdict | None = None
    skipped: Mapping[Pass, Skipped] = field(default_factory=dict)
    failures: tuple[Failure, ...] = ()


class Analyser:
    """Every pass, set up once and reused for each recording."""

    def __init__(
        self,
        models_dir: Path,
        region: Region,
        settings: Settings = DEFAULT_SETTINGS,
        batdetect_model: BatDetectModel | None = None,
        battybird_model: BattyBirdModel | None = None,
    ) -> None:
        self.region = region
        self.settings = settings
        self._batdetect = batdetect_model or batdetect.Model(settings.batdetect)
        self._battybird = battybird_model or battybird.Model(models_dir, settings.battybird)
        self.versions = MappingProxyType(_versions(settings))

    def analyse(self, path: Path) -> RecordingResult:
        s = self.settings
        failures: list[Failure] = []
        skipped = {p: Skipped.DISABLED for p in Pass if p not in s.passes}

        try:
            sound = audio.load(path)
        except audio.AudioError as error:
            failures.append(Failure("audio", str(error)))
            skipped.update({p: Skipped.FAILED_EARLIER for p in s.passes})
            return RecordingResult(
                path=path,
                versions=self.versions,
                skipped=MappingProxyType(skipped),
                failures=tuple(failures),
            )

        found = detection.detect(sound, s.detection)
        opinion = key.identify(found, s.key) if Pass.KEY in s.passes else None

        sources = None
        if Pass.BATDETECT2 in s.passes:
            if s.sieve and not found.has_calls:
                skipped[Pass.BATDETECT2] = Skipped.NO_PULSES
            else:
                try:
                    sources = self._batdetect.analyse(path)
                except batdetect.BatDetectError as error:
                    failures.append(Failure(Pass.BATDETECT2, str(error)))

        second = None
        if Pass.BATTYBIRDNET in s.passes:
            if s.sieve and not found.has_calls:
                skipped[Pass.BATTYBIRDNET] = Skipped.NO_PULSES
            elif sources is None:
                skipped[Pass.BATTYBIRDNET] = Skipped.FAILED_EARLIER
            elif not sources.sources:
                skipped[Pass.BATTYBIRDNET] = Skipped.NO_SOURCES
            else:
                try:
                    second = self._battybird.analyse(sound)
                except battybird.ModelError as error:
                    failures.append(Failure(Pass.BATTYBIRDNET, str(error)))

        versions = self.versions
        verdict = None
        if sources is not None:
            # Results can differ slightly between devices on near-tied calls.
            versions = MappingProxyType(
                {**self.versions, f"{Pass.BATDETECT2}-device": self._batdetect.device}
            )
            verdict = consensus.combine(
                self.region,
                sources,
                found,
                key_opinion=opinion,
                battybird_opinion=second.opinion if second else None,
                params=s.consensus,
            )
        return RecordingResult(
            path=path,
            versions=versions,
            sample_rate=sound.sample_rate,
            duration_s=sound.duration_s,
            detection=found,
            key=opinion,
            batdetect=sources,
            battybird=second,
            verdict=verdict,
            skipped=MappingProxyType(skipped),
            failures=tuple(failures),
        )


def _versions(settings: Settings) -> dict[str, str]:
    versions = {"nyctalus": __version__}
    if Pass.BATDETECT2 in settings.passes:
        versions[Pass.BATDETECT2] = metadata.version("batdetect2")
    if Pass.BATTYBIRDNET in settings.passes:
        commit = battybird.REPOSITORY.rsplit("/", 1)[-1][:12]
        versions[Pass.BATTYBIRDNET] = f"{commit}/{settings.battybird.head}"
    return versions
