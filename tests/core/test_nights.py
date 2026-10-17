from datetime import date, datetime

from nyctalus.core.nights import night_of


def test_an_evening_belongs_to_its_own_night() -> None:
    assert night_of(datetime(2026, 9, 2, 21, 30)) == date(2026, 9, 2)


def test_after_midnight_belongs_to_the_evening_before() -> None:
    assert night_of(datetime(2026, 9, 3, 2, 0)) == date(2026, 9, 2)


def test_the_night_turns_at_noon() -> None:
    assert night_of(datetime(2026, 9, 3, 11, 59)) == date(2026, 9, 2)
    assert night_of(datetime(2026, 9, 3, 12, 0)) == date(2026, 9, 3)
