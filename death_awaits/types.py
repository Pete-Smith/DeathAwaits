""" Base Types """
from enum import Enum


class Increment(Enum):
    """
    Increments of Time for use with .
    """

    SECOND = 0
    MINUTE = 1
    TEN_MINUTES = 2
    QUARTER_HOUR = 3
    HALF_HOUR = 4
    HOUR = 5
    DAY = 6
    YEAR_DAY = 7  # Stacks leap days with previous day.
    WEEK = 8
    FORTNIGHT = 9
    MONTH = 10
    YEAR = 11
    DECADE = 12
    CENTURY = 13
    MILLENIUM = 14
