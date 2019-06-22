from collections import namedtuple
import datetime
import re

import PyQt5.QtCore as Core
from PyQt5.QtCore import Qt

from death_awaits.db import LogDb
from death_awaits.palettes import BasePalette
from helper import (
    Weekday, SegmentSize, SortStrategy, OtherSort, UnrecordedSort, snap_to_segment
)

chunk = namedtuple('Chunk', ('name', 'proportion'))


class LinearQuantizedModel(Core.QAbstractItemModel):
    """
    This model will digest the contents of a LogDb into a series of
    quantized segments. Each segment will contain zero or more activities.
    For a given model index, the row is the segment offset from the beginning of
    the series, and the column index is an activity.
    """
    def __init__(self, database: LogDb, activity: str,
                 start: datetime.datetime, end: datetime.datetime,
                 level: int, segment_size: SegmentSize,
                 sort_strategy: SortStrategy,
                 sort_other: OtherSort, sort_unrecorded: UnrecordedSort,
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
        self._cache = list()
        self._ranked_activities = list()

    def update_ranked_activities(self):
        category_count = len(self.palette)
        show_unrecorded = self.sort_unrecorded != UnrecordedSort.hide_unrecorded
        show_other = self.sort_other != OtherSort.hide_other
        activities = self.database.slice_activities(
            start=self.start, end=self.end, level=self.level,
            unrecorded=show_unrecorded
        )
        items_shown = list()
        other = list()
        filter_ = re.compile(self.activity, re.IGNORECASE)
        for k, v in activities.items():
            m = filter_.search(k)
            if m:
                items_shown.append((k, v),)
            elif show_other:
                other.append(v)
        if len(items_shown) > category_count:
            items_shown.sort(key=lambda i: i[1], reverse=True)
            for item in items_shown[category_count:]:
                if self.show_other:
                    other.append(item[1])
            items_shown = items_shown[:category_count]
        if other and show_other:
            items_shown.append(('other', sum(other)))
        if self.sort_strategy in (
                SortStrategy.largest_first,
                SortStrategy.largest_first_by_segment):
            items_shown.sort(key=lambda i: i[1], reverse=True)
        else:
            items_shown.sort(key=lambda i: i[1], reverse=False)
        ranked_activities = [i[0] for i in items_shown]
        if self.sort_other == OtherSort.after_activities:
            i = ranked_activities.index('unrecorded')
            ranked_activities.pop(i)
        elif self.sort_other == OtherSort.before_activities:
            pass
        if self.sort_unrecorded == UnrecordedSort.before_other:
            pass
        elif self.sort_unrecorded == UnrecordedSort.after_other:
            pass
        if ranked_activities != self._ranked_activities:
            self._ranked_activities = ranked_activities
            #TODO: Provide a signal here.

    def update_segments(self, start, end):
        pass

    def rowCount(self, parent=None):
        return len(self._cache)

    def columnCount(self, parent=None):
        return len(self._ranked_activities)

    def data(self, index, role=Qt.DisplayRole):
        pass

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        pass


class CyclicalQuantizedModel(LinearQuantizedModel):
    def rowCount(self, parent=None):
        pass
