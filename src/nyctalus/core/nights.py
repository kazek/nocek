"""Which night a recording belongs to.

Nights run from noon to noon, so a bat recorded at 02:00 belongs to the
evening before rather than starting a night of its own. Times are the
recorder's local clock, as it writes them into file names.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta


def night_of(moment: datetime) -> date:
    """The date the night began."""
    return (moment - timedelta(hours=12)).date()
