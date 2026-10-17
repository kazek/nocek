"""Issues with how a recorder was configured.

Each issue is a code with the values that explain it, so the interface can
word it in any language. Times on the recorder are its local clock; the sun
is computed in UTC and brought to local time with this computer's offset on
that date, which is right as long as the computer and the recorder were set
in the same time zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum

from nyctalus.recorders import sun
from nyctalus.recorders.base import Config


class Issue(StrEnum):
    STARTS_AFTER_SUNSET = "starts-after-sunset"
    ENDS_BEFORE_SUNRISE = "ends-before-sunrise"
    NOT_BAT_MODE = "not-bat-mode"
    SENSITIVITY_CHANGED = "sensitivity-changed"


@dataclass(frozen=True)
class ConfigIssue:
    issue: Issue
    config: Config
    # What explains it: the sun's time and the schedule's, or the old and
    # new sensitivity, or the mode.
    details: tuple[str, ...]


def check(configs: tuple[Config, ...]) -> list[ConfigIssue]:
    """Issues with each configuration, oldest first."""
    found: list[ConfigIssue] = []
    previous: dict[str, Config] = {}
    for c in configs:
        found += _schedule(c)
        before = previous.get(c.device_uid)
        if before and before.trigger_sensitivity != c.trigger_sensitivity:
            found.append(
                ConfigIssue(
                    Issue.SENSITIVITY_CHANGED,
                    c,
                    (str(before.trigger_sensitivity), str(c.trigger_sensitivity)),
                )
            )
        previous[c.device_uid] = c
    return found


def _schedule(c: Config) -> list[ConfigIssue]:
    out = []
    for s in c.schedules:
        if s.mode != "bat":
            out.append(ConfigIssue(Issue.NOT_BAT_MODE, c, (s.mode,)))
    bat = [s for s in c.schedules if s.mode == "bat"]
    if not bat or c.location is None:
        return out
    day = c.written_at.date()
    lat, lon = c.location.latitude, c.location.longitude
    dusk = _local(sun.sunset(day, lat, lon), day)
    dawn = _local(sun.sunrise(date.fromordinal(day.toordinal() + 1), lat, lon), day)
    wake = min(s.wake for s in bat)
    # The latest morning end among the overnight schedules.
    mornings = [s.sleep for s in bat if s.sleep <= s.wake]
    if dusk is not None and wake > dusk:
        out.append(ConfigIssue(Issue.STARTS_AFTER_SUNSET, c, (_hhmm(dusk), _hhmm(wake))))
    if dawn is not None and mornings and max(mornings) < dawn:
        out.append(ConfigIssue(Issue.ENDS_BEFORE_SUNRISE, c, (_hhmm(dawn), _hhmm(max(mornings)))))
    return out


def _local(moment: datetime | None, day: date) -> time | None:
    if moment is None:
        return None
    return moment.astimezone(datetime(day.year, day.month, day.day, 12).astimezone().tzinfo).time()


def _hhmm(t: time) -> str:
    return t.strftime("%H:%M")
