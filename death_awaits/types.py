""" Base Types """

import re
from enum import Enum
from typing import Optional, Callable
from datetime import datetime, timedelta
from dateutil import tz


def _resolve_timezone(timezone: Optional[str] = None, default_utc: bool = True):
    """
    Resolve an IANA string to a timezone object,
    if None is passed it will return UTC or the local time
    based on the default_utc parameter.
    """
    if timezone is None:
        if default_utc:
            return tz.tzutc()
        return tz.tzlocal()
    return tz.gettz(timezone)


def datetime_adapter_factory(
    ui_timezone: Optional[str] = None, storage_timezone: Optional[str] = None
) -> Callable[[datetime], bytes]:
    """
    SQLite database adapter factory for datetime objects.

    The returned function will transform Python datetime objects
    into byte strings for storage.
    During this transformation, the function handles the timezone conversion
    from the UI timezone to the storage timezone.
    It will also round microseconds to the nearest second,
    and resolve ambiguous or non-existent values.

    The ui_timezone parameter will default to the local timezone.
    The storage_timezone parameter will default to UTC.
    """
    ui_tz = _resolve_timezone(ui_timezone, False)
    storage_tz = _resolve_timezone(storage_timezone, True)

    def _adapter(value: datetime) -> bytes:
        if value.tzinfo is None:
            value = value.replace(tzinfo=ui_tz)
        if value.microsecond != 0:
            second_to_add = int(round(value.microsecond / 1_000_000))
            if second_to_add:
                value += timedelta(seconds=1)
            value = value.replace(microsecond=0)
        value = value.astimezone(storage_tz)
        return (
            tz.resolve_imaginary(value).replace(tzinfo=None).isoformat().encode("ascii")
        )

    return _adapter


def datetime_converter_factory(
    ui_timezone: Optional[str] = None, storage_timezone: Optional[str] = None
) -> Callable[[bytes], datetime]:
    """
    SQLite database converter factory for datetime objects.

    The returned function will transform byte strings to
    Python datetime objects for use in the application.
    During this transformation, the function handles the timezone conversion
    from the storage timezone to the UI timezone.
    It will also round microseconds to the nearest second,
    and resolve ambiguous or non-existent values.

    The ui_timezone parameter will default to the local timezone.
    The storage_timezone parameter will default to UTC.
    """
    ui_tz = _resolve_timezone(ui_timezone, False)
    storage_tz = _resolve_timezone(storage_timezone, True)

    def _converter(value: bytes) -> datetime:
        dt = datetime.fromisoformat(value.decode("ascii")).replace(tzinfo=storage_tz)
        if dt.microsecond != 0:
            dt = dt.replace(
                second=dt.second + round(dt.microsecond / 1_000_000),
                microsecond=0,
            )
        dt = dt.astimezone(ui_tz)
        return tz.resolve_imaginary(dt)

    return _converter


class TimeIncrement(Enum):

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

    def steps(self, other: "TimeIncrement", start: Optional[datetime]) -> float:
        """
        Return the number of steps this increment fits inside of another increment,
        given a specific start time.
        """
        pass

    def start(self, value: datetime):
        pass


class Activity:
    """Hierarchical text associated with each log entry. Comparisons are case insensitive."""

    delimiter = re.compile(r"(?<!:):{1}(?!:)")
    __slots__ = ("_contents", "_cursor")

    def __init__(self, value: str):
        self._contents = [
            item.strip()
            for item in re.split(self.delimiter, str(value))
            if item.strip()
        ]
        self._cursor = 0

    def __len__(self) -> int:
        return len(self._contents)

    def __bool__(self) -> bool:
        return len(self) > 0

    def __str__(self) -> str:
        return " : ".join(self._contents)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}("{str(self)}")'

    def __lt__(self, value) -> bool:
        if isinstance(value, Activity):
            return str(self).lower() < str(value).lower()
        elif isinstance(value, str):
            return str(self).lower() < value.lower()
        return str(self).lower() < value

    def __eq__(self, value) -> bool:
        if isinstance(value, Activity):
            return str(self).lower() == str(value).lower()
        elif isinstance(value, str):
            return str(self).lower() == value.lower()
        return str(self).lower() == value

    def __hash__(self) -> int:
        return hash(str(self).lower())

    def __getitem__(self, key: int) -> str:
        return self._contents[key]

    def __iter__(self):
        self._cursor = 0
        return self

    def __next__(self):
        if self._cursor < len(self):
            item = self[self._cursor]
            self._cursor += 1
            return item
        else:
            raise StopIteration()

    def case_sensitive_comparison(self, other: "Activity") -> bool:
        if isinstance(other, Activity):
            return str(self) == str(other)
        return str(self) == other

    def common(self, other: "Activity") -> Optional["Activity"]:
        """
        Return a new Activity that includes the shared items between this activity and another.
        Returns None if no items are similar.
        """
        if self is other:
            return self
        retval = list()
        for a, b in zip(self, other):
            if a.lower() == b.lower():
                retval.append(a)
            else:
                break
        if not retval:
            return None
        return Activity(" : ".join(retval))

    @staticmethod
    def adapter(value: "Activity") -> bytes:
        """Convert an Activity instance to a string for database storage."""
        return str(value).encode("utf8")

    @staticmethod
    def converter(value: bytes) -> "Activity":
        """Instantiate an Activity instance from a database string."""
        return Activity(value.decode("utf8"))


class Slice:
    """
    This contains requisite elements of a log entry, but may represent a subdivided piece of one.
    """

    __slots__ = ("_activity", "_start", "_end", "_quantity")

    def __init__(
        self, activity: Activity, start: datetime, end: datetime, quantity: int
    ):
        self._activity = activity
