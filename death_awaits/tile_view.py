from collections import namedtuple
import datetime
import re
from copy import copy

import PyQt6.QtCore as core
from PyQt6.QtCore import Qt
from dateutil.relativedelta import relativedelta

from death_awaits.db import LogDb
from death_awaits.palettes import BasePalette
from helper import (
    Weekday,
    SegmentSize,
    SortStrategy,
    OtherSort,
    UnrecordedSort,
    snap_to_segment,
)

chunk = namedtuple("Chunk", ("name", "proportion"))


class LinearQuantizedModel(core.QAbstractItemModel):
    """
    This model will digest the contents of a LogDb into a series of
    quantized segments. Each segment will contain zero or more activities.
    For a given model index,
    the row is the segment offset from the beginning of the series,
    and the column index is an activity.
    """

    def __init__(
        self,
        database: LogDb,
        activity: str,
        start: datetime.datetime,
        end: datetime.datetime,
        level: int,
        segment_size: SegmentSize,
        sort_strategy: SortStrategy,
        sort_other: OtherSort,
        sort_unrecorded: UnrecordedSort,
        palette: BasePalette,
        first_day_of_week: Weekday,
        parent=None,
    ):
        super(LinearQuantizedModel, self).__init__(parent=parent)
        self.database = database
        self.activity = activity
        self.start = start
        self.end = end
        self.level = abs(level)
        self.segment_size = segment_size
        self.sort_strategy = sort_strategy
        self.palette = palette
        self.sort_other = sort_other
        self.sort_unrecorded = sort_unrecorded
        if first_day_of_week not in (Weekday.sunday, Weekday.monday):
            raise ValueError("First day of week must be Sunday or Monday.")
        self.first_day_of_week = first_day_of_week
        self._cache = None
        self._ranked_activities = list()

    @property
    def start(self):
        return getattr(self, "_start", None)

    @start.setter
    def start(self, value):
        value = snap_to_segment(value, self.segment_size, self.first_day_of_week)
        if self.end and value > self.end:
            raise ValueError("Tried to set a start time after current end time.")
        setattr(self, "_start", value)
        self._cache = None

    @property
    def end(self):
        return getattr(self, "_end", None)

    @end.setter
    def end(self, value):
        value = snap_to_segment(value, self.segment_size, self.first_day_of_week)
        if self.start and value < self.start:
            raise ValueError("Tried to set a end time before current start time.")
        setattr(self, "_end", value)
        self._cache = None

    def segment_size_in_seconds(self):
        if self.segment_size == SegmentSize.minute:
            return 60
        elif self.segment_size == SegmentSize.hour:
            return 60 * 60
        elif self.segment_size == SegmentSize.day:
            return 24 * 60 * 60
        elif self.segment_size == SegmentSize.week:
            return 7 * 24 * 60 * 60
        elif self.segment_size == SegmentSize.month:
            raise AttributeError("There are a variable number of days per month.")
        else:
            raise ValueError(f"Invalid segment_size attribute: f{self.segment_size}")

    def update_ranked_activities(self):
        category_count = len(self.palette)
        show_unrecorded = self.sort_unrecorded != UnrecordedSort.hide_unrecorded
        show_other = self.sort_other != OtherSort.hide_other
        activities = self.database.slice_activities(
            start=self.start, end=self.end, level=self.level, unrecorded=show_unrecorded
        )
        items_shown = list()
        other = list()
        filter_ = re.compile(self.activity, re.IGNORECASE)
        for k, v in activities.items():
            m = filter_.search(k)
            if m:
                items_shown.append(
                    (k, v),
                )
            elif show_other:
                other.append(v)
        if len(items_shown) > category_count:
            items_shown.sort(key=lambda i: i[1], reverse=True)
            for item in items_shown[category_count:]:
                if self.show_other:
                    other.append(item[1])
            items_shown = items_shown[:category_count]
        if other and show_other:
            items_shown.append(("other", sum(other)))
        if self.sort_strategy in (
            SortStrategy.largest_first,
            SortStrategy.largest_first_by_segment,
        ):
            items_shown.sort(key=lambda i: i[1], reverse=True)
        else:
            items_shown.sort(key=lambda i: i[1], reverse=False)
        ranked_activities = [i[0] for i in items_shown]
        if self.sort_other == OtherSort.after_activities:
            try:
                i = ranked_activities.index("other")
                del ranked_activities[i]
                ranked_activities.pop(i)
                ranked_activities.append("other")
            except ValueError:
                pass
        elif self.sort_other == OtherSort.before_activities:
            try:
                i = ranked_activities.index("other")
                del ranked_activities[i]
                ranked_activities.insert(0, "other")
            except ValueError:
                pass
        if self.sort_unrecorded == UnrecordedSort.before_other:
            pass
        elif self.sort_unrecorded == UnrecordedSort.after_other:
            pass
        if ranked_activities != self._ranked_activities:
            self._ranked_activities = ranked_activities
            self._cache = None

    def rowCount(self, parent=None):
        if self.segment_size != SegmentSize.month:
            total_seconds = (self.end - self.start).total_seconds()
            return int(total_seconds / self.segment_size_in_seconds())
        else:
            scan = copy(self.start)
            count = 0
            while scan <= self.end:
                count += 1
                scan = scan + relativedelta(months=+1)
            return count

    def columnCount(self, parent=None):
        return len(self._ranked_activities)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if self._cache is None:
            self._cache = [
                None,
            ] * self.rowCount()
        if self.segment_size != SegmentSize.month:
            segment_start = self.start + datetime.timedelta(
                seconds=self.segment_size_in_seconds() * index.row()
            )
            segment_end = segment_start + datetime.timedelta(
                seconds=self.segment_size_in_seconds()
            )
            # TODO
        else:
            pass

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        pass


class CyclicalQuantizedModel(LinearQuantizedModel):
    def rowCount(self, parent=None):
        pass

    # TODO
