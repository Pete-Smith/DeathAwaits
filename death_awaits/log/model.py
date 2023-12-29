import datetime
import re

import PyQt6.QtGui as gui
import PyQt6.QtWidgets as widgets
import PyQt6.QtCore as core
from PyQt6.QtCore import Qt

from death_awaits.db import LogDb
from death_awaits.helper import stringify_datetime


class LogModel(core.QAbstractTableModel):
    """In-memory data store."""

    def __init__(self, database, activity=None, start=None, end=None, parent=None):
        super(LogModel, self).__init__(parent)
        assert isinstance(database, LogDb)
        self._db = database
        self._cache = []
        self.update_cache(activity=None, start=None, end=None)
        # Connections
        self._db.entry_added.connect(self._handle_addition)
        self._db.entry_modified.connect(self._handle_modification)
        self._db.entry_removed.connect(self._handle_deletion)

    def update_cache(self, activity=None, start=None, end=None):
        if isinstance(activity, str) and activity.strip() == "":
            activity = None
        self.beginResetModel()
        self._cache = self._db.filter(activity, start, end)
        self._current_filter = (activity, start, end)
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._cache)

    def columnCount(self, parent=None):
        return len(LogDb.log_table_def)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        column_name = LogDb.log_table_def[index.column()][0]
        if role == Qt.ItemDataRole.DisplayRole:
            data = self._cache[index.row()][column_name]
            if isinstance(data, datetime.datetime):
                data = stringify_datetime(data)
            elif column_name == "quantity":
                data = LogDb.format_duration(data)
            return data
        elif role == Qt.ItemDataRole.UserRole:
            return self._cache[index.row()]
        elif role == Qt.ItemDataRole.BackgroundRole:
            if index.row() % 2:
                return gui.QBrush(
                    widgets.QApplication.instance()
                    .palette()
                    .color(gui.QPalette.ColorRole.AlternateBase)
                )
            else:
                return gui.QBrush(
                    widgets.QApplication.instance()
                    .palette()
                    .color(gui.QPalette.ColorRole.Base)
                )

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return LogDb.log_table_def[section][0].title()

    def create_entry(
        self, activity, start, end, quantity=None, id=None, apply_capitalization=False
    ):
        """Create an entry and return the new id."""
        return self._db.create_entry(
            activity, start, end, quantity, id, apply_capitalization
        )

    def delete_entry(self, id_):
        self._db.remove_entry(id_)

    def adjust_entries(self, ids, amount):
        self._db.shift_rows(ids, amount)

    def _handle_deletion(self, id_):
        for r in range(self.rowCount()):
            entry = self.data(self.index(r, 0), Qt.ItemDataRole.UserRole)
            if entry is not None and entry["id"] == id_:
                self.beginRemoveRows(core.QModelIndex(), r, r)
                del self._cache[r]
                self.endRemoveRows()
                break

    def _handle_addition(self, id_):
        row = self._db.row(id_)
        if self._fits_filter(row):
            for i, current in enumerate(self._cache):
                if current["start"] > row["start"]:
                    self.beginInsertRows(core.QModelIndex(), i, i)
                    self._cache.insert(i, row)
                    self.endInsertRows()
                    break
            else:
                i = len(self._cache)
                self.beginInsertRows(core.QModelIndex(), i, i)
                self._cache.append(row)
                self.endInsertRows()

    def _handle_modification(self, id_):
        row = self._db.row(id_)
        if self._fits_filter(row):
            for i, current in enumerate(self._cache):
                if current["id"] == row["id"]:
                    self._cache[i] = row
                    left_index = self.index(i, 0)
                    right_index = self.index(i, self.columnCount() - 1)
                    self.dataChanged.emit(left_index, right_index)
                    break

    def _fits_filter(self, entry):
        """Check entry parameter against the current filter."""
        time_ok, activity_ok = False, False
        activity, start, end = self._current_filter
        if None not in (start, end):
            try:
                if (
                    start <= entry["start"] <= end
                    or start <= entry["end"] <= end
                    or (entry["start"] <= start and entry["end"] >= end)
                ):
                    time_ok = True
            except TypeError:
                print(
                    "start : {0}, end : {1},"
                    "\nentry['start'] : {2}, entry['end'] : {3}".format(
                        repr(start),
                        repr(end),
                        repr(entry["start"]),
                        repr(entry["end"]),
                    )
                )
                raise
        elif end is not None and isinstance(start, datetime.datetime):
            if entry["start"] <= end:
                time_ok = True
        elif start is not None and isinstance(end, datetime.datetime):
            if entry["end"] >= start:
                time_ok = True
        else:
            time_ok = True
        if activity is None:
            activity_ok = True
        else:
            reg = re.compile(activity, re.IGNORECASE)
            activity_ok = reg.search(entry["activity"]) is not None
        return time_ok and activity_ok
