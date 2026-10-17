from nyctalus.recorders.checks import Issue, check
from nyctalus.recorders.pippyg import parse_settings
from tests.recorders.test_pippyg import settings


def issues(*raw: str) -> list[tuple[Issue, tuple[str, ...]]]:
    return [(i.issue, i.details) for i in check(tuple(parse_settings(r) for r in raw))]


def test_a_dusk_to_dawn_schedule_is_fine() -> None:
    assert issues(settings()) == []


def test_starting_after_sunset() -> None:
    late = settings(activity=[{"wake": "22:00", "sleep": "7:30", "mode": "bat"}])

    ((issue, (sunset, wake)),) = issues(late)

    assert issue is Issue.STARTS_AFTER_SUNSET
    assert wake == "22:00"
    assert "18:30" < sunset < "20:30"  # Kraków, early September


def test_ending_before_sunrise() -> None:
    early = settings(activity=[{"wake": "18:15", "sleep": "4:00", "mode": "bat"}])

    ((issue, (sunrise, sleep)),) = issues(early)

    assert issue is Issue.ENDS_BEFORE_SUNRISE
    assert sleep == "04:00"
    assert "05:00" < sunrise < "07:30"


def test_a_mode_other_than_bat() -> None:
    bird = settings(activity=[{"wake": "22:00", "sleep": "9:00", "mode": "bird"}])

    assert issues(bird) == [(Issue.NOT_BAT_MODE, ("bird",))]


def test_a_changed_trigger_sensitivity() -> None:
    later = settings(
        trigger_sensitivity=30,
        current_time={"year": 2026, "month": 9, "day": 4, "hour": 18, "minute": 15},
    )

    assert issues(settings(), later) == [(Issue.SENSITIVITY_CHANGED, ("48", "30"))]


def test_no_location_no_sun_check() -> None:
    late = settings(location=None, activity=[{"wake": "23:00", "sleep": "2:00", "mode": "bat"}])

    assert issues(late) == []
