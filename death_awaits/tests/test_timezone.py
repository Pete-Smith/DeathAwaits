"""
Working out some behavioral assumptions for time zone edge cases
such as leap years, daylight savings time, and leap seconds.
"""
from datetime import datetime, date

import pytest
from dateutil import tz, relativedelta

from death_awaits.db import LogDb

NYC = tz.gettz("America/New York")


def test_timedelta_across_leapday():
    """Demonstrate behaviour across leap year days."""
    # 2020 was a leap year
    assert (date(2020, 3, 1, tzinfo=NYC) - date(2020, 2, 28, tzinfo=NYC)).days == 2
    assert (date(2021, 3, 1, tzinfo=NYC) - date(2021, 2, 28, tzinfo=NYC)).days == 1
