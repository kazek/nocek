"""What every recorder adapter reports about a folder of its files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Location:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Schedule:
    """One period the recorder listens in each day."""

    wake: time
    sleep: time  # before wake means the next morning
    mode: str  # e.g. "bat" or "bird"


@dataclass(frozen=True)
class Config:
    """The recorder's settings as they were written at one moment."""

    device_uid: str
    device_number: int
    written_at: datetime  # the recorder's local clock
    location: Location | None
    schedules: tuple[Schedule, ...]
    trigger_sensitivity: int | None
    firmware: str | None
    raw: str  # exactly what the recorder wrote

    def mode_at(self, moment: datetime) -> str | None:
        """The mode of the schedule that covers a moment, if one does."""
        t = moment.time()
        for s in self.schedules:
            overnight = s.sleep <= s.wake
            if (s.wake <= t or t < s.sleep) if overnight else (s.wake <= t < s.sleep):
                return s.mode
        return None


@dataclass(frozen=True)
class RecordingFile:
    path: Path
    recorded_at: datetime  # the recorder's local clock, from the file name
    device_number: int


class Problem(StrEnum):
    """Something found while scanning that the user should hear about."""

    EMPTY_SETTINGS = "empty-settings"  # a settings file with nothing readable in it
    UNREADABLE_SETTINGS = "unreadable-settings"


@dataclass(frozen=True)
class Finding:
    problem: Problem
    path: Path


@dataclass(frozen=True)
class Scan:
    recordings: tuple[RecordingFile, ...]
    configs: tuple[Config, ...]  # oldest first
    findings: tuple[Finding, ...]

    def config_at(self, moment: datetime, device_number: int) -> Config | None:
        """The latest configuration of that device written before a moment."""
        earlier = [
            c for c in self.configs if c.device_number == device_number and c.written_at <= moment
        ]
        return earlier[-1] if earlier else None


class Recorder(Protocol):
    kind: str

    def recognises(self, folder: Path) -> bool:
        """Whether the folder holds this recorder's files."""
        ...

    def scan(self, folder: Path) -> Scan: ...
