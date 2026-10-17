from datetime import UTC, date, datetime, timedelta

import pytest

from nyctalus.recorders import sun

LONDON = (51.5074, -0.1278)


def close(a: datetime | None, b: datetime) -> bool:
    return a is not None and abs(a - b) < timedelta(minutes=3)


def test_midsummer_in_london() -> None:
    day = date(2026, 6, 21)

    assert close(sun.sunrise(day, *LONDON), datetime(2026, 6, 21, 3, 43, tzinfo=UTC))
    assert close(sun.sunset(day, *LONDON), datetime(2026, 6, 21, 20, 21, tzinfo=UTC))


def test_midwinter_in_london() -> None:
    day = date(2026, 12, 21)

    assert close(sun.sunrise(day, *LONDON), datetime(2026, 12, 21, 8, 4, tzinfo=UTC))
    assert close(sun.sunset(day, *LONDON), datetime(2026, 12, 21, 15, 54, tzinfo=UTC))


@pytest.mark.parametrize("day", [date(2026, 3, 20), date(2026, 9, 23)])
def test_equinox_days_are_twelve_hours_long(day: date) -> None:
    rise, set_ = sun.sunrise(day, 50.0, 20.0), sun.sunset(day, 50.0, 20.0)

    assert rise is not None and set_ is not None
    assert abs((set_ - rise) - timedelta(hours=12, minutes=8)) < timedelta(minutes=10)


def test_no_sunset_in_the_polar_summer() -> None:
    assert sun.sunset(date(2026, 6, 21), 78.2, 15.6) is None  # Svalbard
