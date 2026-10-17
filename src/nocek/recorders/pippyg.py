"""The pippyg recorder (Apodemus), configured by an ultrasonic chirp from a phone.

On its card, pippyg writes recordings named DEV_<device>_<date>_<time>.wav in
one folder per hour, a device_settings_<date>_<time>.json each time it is
configured, and latlong_<lat>_<lon>_.html markers with the phone's position.
Settings files are sometimes empty, so they are read defensively and an
empty one is reported, not trusted.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, time
from pathlib import Path
from typing import Any

from nocek.recorders.base import (
    Config,
    Finding,
    Location,
    Problem,
    RecordingFile,
    Scan,
    Schedule,
)

KIND = "pippyg"

RECORDING = re.compile(r"DEV_(?P<device>\d+)_(?P<date>\d{8})_(?P<time>\d{6})\.wav", re.IGNORECASE)
SETTINGS = re.compile(r"device_settings_(?P<date>\d{8})_(?P<time>\d{4})\.json", re.IGNORECASE)


class Pippyg:
    kind = KIND

    def recognises(self, folder: Path) -> bool:
        return any(RECORDING.fullmatch(p.name) for p in folder.rglob("*.wav"))

    def scan(self, folder: Path) -> Scan:
        recordings = []
        for path in sorted(folder.rglob("*")):
            match = RECORDING.fullmatch(path.name)
            if match and path.is_file():
                recordings.append(
                    RecordingFile(
                        path=path,
                        recorded_at=datetime.strptime(
                            match["date"] + match["time"], "%Y%m%d%H%M%S"
                        ),
                        device_number=int(match["device"]),
                    )
                )

        configs, findings = [], []
        for path in sorted(folder.rglob("device_settings_*.json")):
            if not SETTINGS.fullmatch(path.name):
                continue
            raw = path.read_text("utf-8", errors="replace")
            if not raw.strip():
                findings.append(Finding(Problem.EMPTY_SETTINGS, path))
                continue
            try:
                configs.append(parse_settings(raw))
            except (ValueError, KeyError, TypeError):
                findings.append(Finding(Problem.UNREADABLE_SETTINGS, path))
        configs.sort(key=lambda c: c.written_at)
        return Scan(recordings=tuple(recordings), configs=tuple(configs), findings=tuple(findings))

    def parse_config(self, raw: str) -> Config:
        return parse_settings(raw)


def parse_settings(raw: str) -> Config:
    """A device_settings file. Raises ValueError, KeyError or TypeError if malformed."""
    d: dict[str, Any] = json.loads(raw)
    t = d["current_time"]
    location = d.get("location")
    return Config(
        device_uid=str(d["uid"]),
        device_number=int(d["device_id"]),
        written_at=datetime(t["year"], t["month"], t["day"], t["hour"], t["minute"]),
        location=Location(float(location["latitude"]), float(location["longitude"]))
        if location
        else None,
        schedules=tuple(
            Schedule(wake=_clock(a["wake"]), sleep=_clock(a["sleep"]), mode=str(a["mode"]))
            for a in d.get("activity", [])
        ),
        trigger_sensitivity=d.get("trigger_sensitivity"),
        firmware=d.get("fw"),
        raw=raw,
    )


def _clock(text: str) -> time:
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))
