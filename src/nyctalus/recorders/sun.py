"""Sunset and sunrise, to check that a recorder listens through the night.

The NOAA solar calculator's equations, good to about a minute away from the
polar regions, which is far more than a schedule check needs.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

# The sun's centre 0.833 degrees below the horizon: refraction plus its radius.
_HORIZON = math.radians(-0.833)


def sunset(day: date, latitude: float, longitude: float) -> datetime | None:
    """Sunset on that day, in UTC, or None when the sun does not set or rise."""
    return _event(day, latitude, longitude, setting=True)


def sunrise(day: date, latitude: float, longitude: float) -> datetime | None:
    return _event(day, latitude, longitude, setting=False)


def _event(day: date, latitude: float, longitude: float, setting: bool) -> datetime | None:
    noon = datetime(day.year, day.month, day.day, 12, tzinfo=UTC) - timedelta(hours=longitude / 15)
    # Two passes: the sun's position at the first estimate refines the second.
    moment = noon
    for _ in range(2):
        declination, equation_of_time = _sun(moment)
        lat = math.radians(latitude)
        cos_hour = (math.sin(_HORIZON) - math.sin(lat) * math.sin(declination)) / (
            math.cos(lat) * math.cos(declination)
        )
        if not -1 <= cos_hour <= 1:
            return None
        hour_angle = math.degrees(math.acos(cos_hour))
        solar_noon = noon - timedelta(minutes=equation_of_time)
        offset = timedelta(minutes=4 * hour_angle)
        moment = solar_noon + offset if setting else solar_noon - offset
    return moment


def _sun(moment: datetime) -> tuple[float, float]:
    """Declination (radians) and equation of time (minutes) at a moment."""
    jd = moment.timestamp() / 86400 + 2440587.5
    t = (jd - 2451545.0) / 36525
    mean_long = math.radians((280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360)
    mean_anom = math.radians(357.52911 + t * (35999.05029 - 0.0001537 * t))
    ecc = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    centre = math.radians(
        math.sin(mean_anom) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(2 * mean_anom) * (0.019993 - 0.000101 * t)
        + math.sin(3 * mean_anom) * 0.000289
    )
    omega = math.radians(125.04 - 1934.136 * t)
    apparent_long = mean_long + centre - math.radians(0.00569 + 0.00478 * math.sin(omega))
    obliquity = math.radians(
        23
        + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
        + 0.00256 * math.cos(omega)
    )
    declination = math.asin(math.sin(obliquity) * math.sin(apparent_long))
    y = math.tan(obliquity / 2) ** 2
    equation_of_time = 4 * math.degrees(
        y * math.sin(2 * mean_long)
        - 2 * ecc * math.sin(mean_anom)
        + 4 * ecc * y * math.sin(mean_anom) * math.cos(2 * mean_long)
        - 0.5 * y * y * math.sin(4 * mean_long)
        - 1.25 * ecc * ecc * math.sin(2 * mean_anom)
    )
    return declination, equation_of_time
