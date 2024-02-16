""" Database functionality. """

from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional
import copy
import os
import re
import sqlite3


from death_awaits.helper import iso_to_gregorian
from death_awaits.types import (
    datetime_adapter_factory,
    datetime_converter_factory,
    Activity,
)


class LogDb:
    """On-disk data store."""

    log_table_def = (
        ("id", "integer PRIMARY KEY"),
        ("activity", "activity"),
        ("start", "datetime"),
        ("end", "datetime"),
        ("quantity", "int"),  # minutes as default
    )
    settings_table_def = (
        ("id", "integer PRIMARY KEY"),
        ("units", "text"),
        ("overflow", "bool"),  # Allow overloaded time spans.
        ("timezone", "text"),  # IANA time zone name
    )

    def __init__(
        self,
        filename: str = ":memory:",
        units: Optional[str] = None,
        overflow: Optional[bool] = None,
        ui_timezone: Optional[str] = None,
        storage_timezone: Optional[str] = None,
        signaling_fixture=None,
    ):
        """
        Open or initialize a Death Awaits Time Series Database.

        The following are initialization parameters and are not expected to be
        passed when opening an existing file: units, overflow, and
        storage_timezone.
        These are set once when creating a file, and can not be changed
        retroactively.

        The storage_timezone will default to UTC, if not specified.
        The user-facing timezone will default to the local timezone, if not
        specified.

        The signaling_fixture is an intermediary object we can call Qt signals from.
        """
        self._signaling_fixture = signaling_fixture
        sqlite3.register_adapter(
            datetime, datetime_adapter_factory(ui_timezone, storage_timezone)
        )
        sqlite3.register_converter(
            "datetime", datetime_converter_factory(ui_timezone, storage_timezone)
        )
        sqlite3.register_adapter(Activity, Activity.adapter)
        sqlite3.register_converter("activity", Activity.converter)
        self._undo_stack = list()
        self._redo_stack = list()
        self._current_action = None
        self._filename = filename
        new_file = not os.path.isfile(self._filename)
        self.connection = sqlite3.connect(
            self._filename,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.create_function("REGEXP", 2, LogDb.regexp)
        if new_file:
            if None in (units, overflow):
                raise ValueError(
                    "The units and overflow parameters need to be set to create a new database."
                )
            if not (
                units.lower().startswith("second")
                or units.lower().startswith("minute")
                or units.lower().startswith("hour")
                or units.lower().startswith("day")
            ) and bool(overflow):
                raise ValueError(
                    "Overflow behavior will only work with the following units: "
                    "days, hours, minutes, seconds."
                )
            cursor = self.connection.cursor()
            try:
                self._create_activitylog_table(cursor)
                self._create_settings_table(cursor, units, overflow, storage_timezone)
            finally:
                cursor.close()
                self.connection.commit()
            self.units = units
            self.overflow = overflow
        else:  # if new_file == False
            cursor = self.connection.cursor()
            try:
                cursor.execute("SELECT units, overflow, timezone FROM settings")
                row = cursor.fetchone()
                self.units = row[0]
                self.overflow = row[1]
                if (units is not None and units != self.units) or (
                    units is not None and units != self.units
                ):
                    raise ValueError(
                        "Passed mismatching bounds and/or units parameters "
                        "to existing database."
                    )
            except sqlite3.OperationalError as e:
                if str(e).lower() == "no such table: settings":
                    self._create_settings_table(
                        cursor, units, overflow, storage_timezone
                    )
                    self.bounds = bounds
                    self.units = units
                else:
                    raise e
            finally:
                cursor.close()
                self.connection.commit()

    def signal(self, verb: str, row: int):
        if self._signaling_fixture is not None:
            if hasattr(self._signaling_fixture, verb):
                if hasattr(self.signaling_fixture.verb, "emit"):
                    self.signaling_fixture.verb.emit(row)
                else:
                    raise AttributeError()
            else:
                raise AttributeError()

    def _create_activitylog_table(self, cursor):
        cursor.execute("DROP INDEX IF EXISTS start_times")
        cursor.execute("DROP INDEX IF EXISTS end_times")
        cursor.execute(
            "CREATE TABLE activitylog ("
            + (", ".join(["{0} {1}".format(k, t) for k, t in LogDb.log_table_def]))
            + ")"
        )
        cursor.execute("CREATE INDEX start_times ON activitylog (start)")
        cursor.execute("CREATE INDEX end_times ON activitylog (end)")

    def _create_settings_table(self, cursor, units, overflow, storage_timezone):
        cursor.execute(
            "CREATE TABLE settings ("
            + (", ".join(["{0} {1}".format(k, t) for k, t in LogDb.settings_table_def]))
            + ")"
        )
        cursor.execute(
            "INSERT INTO settings (units, overflow, storage_timezone)"
            " VALUES (?, ?, ?)",
            (units, overflow, storage_timezone),
        )

    def _timedelta_to_quantity(self, delta: timedelta) -> float:
        if self.units.lower().startswith("second"):
            return int(delta.total_seconds())
        elif self.units.lower().startswith("minute"):
            return int(round(delta.total_seconds() / 60))
        elif self.units.lower().startswith("hour"):
            return int(round(delta.total_seconds() / 60 / 60))
        elif self.units.lower().startswith("day"):
            return int(round(delta.total_seconds() / 60 / 60 / 24))
        else:
            return int(delta.total_seconds() / 60)

    def _quantity_to_timedelta(self, quantity: int) -> timedelta:
        if self.units.lower().startswith("second"):
            return timedelta(seconds=quantity)
        elif self.units.lower().startswith("minute"):
            return timedelta(minutes=quantity)
        elif self.units.lower().startswith("hour"):
            return timedelta(hours=quantity)
        elif self.units.lower().startswith("day"):
            return timedelta(hours=quantity * 24)
        else:
            return timedelta(minutes=quantity)

    @staticmethod
    def regexp(expr: str, item: str) -> bool:
        """
        http://stackoverflow.com/questions/5365451/problem-with-regexp-python-and-sqlite
        """
        if item is None:
            item = ""
        reg = re.compile(expr, re.IGNORECASE)
        result = reg.search(item)
        return result is not None

    def filter(
        self,
        activity=None,
        start=None,
        end=None,
        first: bool = False,
        last: bool = False,
    ):
        """
        The activity, start and end parameters are filters.
        The first and last parameters will filter out everything but the first
        and last entries.
        """
        statement = "SELECT * FROM activitylog "
        values = []
        clauses = []
        if None not in (start, end):
            clauses.append(
                "((start BETWEEN ? AND ? OR end BETWEEN ? AND ?) "
                "OR (start <= ? AND end >= ?))"
            )
            values.extend([start, end] * 3)
        elif end is None and isinstance(start, datetime):
            clauses.append("? <= end")
            values.append(start)
        elif start is None and isinstance(end, datetime):
            clauses.append("? >= start")
            values.append(start)
        if activity is not None:
            clauses.append("activity REGEXP ?")
            values.append(activity)
        if clauses:
            statement += "WHERE " + (" AND ".join(clauses)) + " "
        if last and not first:
            statement += "ORDER BY end DESC"
        else:
            statement += "ORDER BY start"
        c = self.connection.cursor()
        try:
            c.execute(statement, values)
            if (first and not last) or (last and not first):
                return c.fetchone()
            elif first and last:
                first = c.fetchone()
                last = self.filter(activity, start, end, False, True)
                return first, last
            else:
                return c.fetchall()
        finally:
            c.close()

    def create_entry(
        self,
        activity,
        start=None,
        end=None,
        quantity=None,
        id=None,
        apply_capitalization: bool = False,
    ):
        """Return the id of the inserted entry."""
        if isinstance(quantity, timedelta):
            quantity = self._timedelta_to_quantity(quantity)
        if id is not None:
            self.remove_entry(id)
        activity = self._check_activity(activity, apply_capitalization)
        start, end, quantity = self._normalize_range(start, end, quantity)
        activity, start, end, quantity = self._merge_common(
            activity, start, end, quantity
        )
        self._modify_overlaps(start, end, quantity)
        c = self.connection.cursor()
        try:
            statement = (
                "INSERT INTO activitylog (activity, start, end, quantity) "
                "VALUES (?, ?, ?, ?)"
            )
            values = (activity, start, end, quantity)
            c.execute(statement, values)
            row_id = c.lastrowid
            new_entry = {
                "id": row_id,
                "activity": activity,
                "start": start,
                "end": end,
                "quantity": quantity,
            }
            self.record_change(new_entry, "add")
            return row_id
        finally:
            c.close()
            self.connection.commit()
            self.signal("entry_added", c.lastrowid)

    def rename_entry(self, activity, ids, apply_capitalization=False):
        if isinstance(ids, int):
            ids = [
                ids,
            ]
        elif isinstance(ids, (list, tuple)):
            non_compliant = [n for n in ids if not isinstance(n, int)]
            if non_compliant:
                raise TypeError(
                    "Non-integer id parameter{0}: {1}".format(
                        "s" if len(non_compliant) > 1 else "", ", ".join(non_compliant)
                    )
                )
        activity = self._check_activity(activity, apply_capitalization)
        effected_rows = list()
        for id_ in ids:
            entry = dict(self.row(id_))
            if entry["activity"] != activity:
                self.record_change(entry, "modify")
                effected_rows.append(id_)
        statement = "UPDATE activitylog SET activity = ? WHERE "
        statement += " OR ".join(["id = ?" for n in ids])
        c = self.connection.cursor()
        try:
            values = [
                activity,
            ]
            values.extend(ids)
            c.execute(statement, values)
        finally:
            c.close()
            self.connection.commit()
        for id_ in effected_rows:
            self.signal("entry_modified", id_)

    def shift_rows(self, ids, amount):
        if isinstance(amount, (float, int)):
            amount = timedelta(seconds=amount)
        assert isinstance(amount, timedelta)
        data = list()
        for id_ in ids:
            assert isinstance(id_, int)
            data.append(dict(self.row(id_)))
            self.remove_entry(id_)
        for i in range(len(data)):
            data[i]["start"] += amount
            data[i]["end"] += amount
        data.sort(key=lambda n: n["start"])
        for row in data:
            self.create_entry(**row)

    @staticmethod
    def _row_density(quantity: int, start: datetime, end: datetime) -> float:
        assert isinstance(start, datetime)
        assert isinstance(end, datetime)
        span = float((start - end).total_seconds()) / 60 / 60
        if span == 0:
            return 0
        return quantity / span

    def _merge_common(
        self, activity: str, start: datetime, end: datetime, quantity: int
    ):
        rows = self.filter(activity, start, end)
        ids_to_delete = []
        new_density = self._row_density(quantity, start, end)
        for row in rows:
            if activity != row["activity"]:
                continue
            row_density = self._row_density(row["quantity"], row["start"], row["end"])
            if abs(new_density - row_density) < 0.0000001 or (
                start == row["start"] and end == row["end"]
            ):
                start = min(start, row["start"])
                end = max(end, row["end"])
                span = end - start
                target_quantity = self.bounded_quantity(span)
                if self.bounds > 0 and quantity + row["quantity"] > target_quantity:
                    quantity = target_quantity
                else:
                    quantity = quantity + row["quantity"]
                ids_to_delete.append(row["id"])
        for id_ in ids_to_delete:
            entry = self.row(id_)
            if entry:
                self.record_change(dict(entry), "remove")
        if ids_to_delete:
            statement = "DELETE FROM activitylog WHERE "
            statement += " OR ".join(("id = ?",) * len(ids_to_delete))
            c = self.connection.cursor()
            try:
                c.execute(statement, ids_to_delete)
            finally:
                c.close()
                self.connection.commit()
        for id_ in ids_to_delete:
            self.signal("entry_removed", id_)
        return activity, start, end, quantity

    def _check_activity(self, activity, apply_capitalization=False):
        activity = " : ".join(n.strip() for n in activity.split(":"))
        preexisting = None
        for item in self.activities():
            if activity.lower() == item.lower():
                preexisting = item
                break
        if apply_capitalization and activity != preexisting:
            pattern = r"^{0}$".format(re.escape(activity))
            ids = list()
            for row in self.filter(activity=pattern):
                if row["activity"] != activity:
                    ids.append(row["id"])
                    self.record_change(dict(row), "modify")
            c = self.connection.cursor()
            try:
                statement = "UPDATE activitylog SET activity = ? WHERE "
                statement += "OR ".join(
                    [
                        "id=?",
                    ]
                    * len(ids)
                )
                variables = [
                    activity,
                ] + ids
                c.execute(statement, variables)
            finally:
                c.close()
                self.connection.commit()
            for id_ in ids:
                self.signal("entry_modified", id_)
        elif preexisting:
            activity = preexisting
        return activity

    def _normalize_range(
        self,
        start: datetime = None,
        end: datetime = None,
        quantity: int = None,
    ):
        """
        If one of the time parameters (start, end, quantity) are not given,
        this method will infer it from the other two.

        The databases bounds settings will be used in the following way:
            If all three parameters are given, the quantity will be clamped
                to bounds parameter, if it is greater than zero.
            If the start and end times are given, but not the quantity,
                the maximum quantity for that time range will be returned,
                or zero if bounds is also zero.
            If either the start or end time is given, along with a quantity,
                the other end of the time-span will be given by using the
                bounds as a quantity/hour measure.
            If bounds is zero, in this instance, it simply returns an hour,
            forward or backward.
        """
        if None not in (start, end):
            if start > end:
                raise ValueError("The end value may not be less than the start value.")
            span = end - start
            target_quantity = self.bounded_quantity(span)
            if quantity is None or quantity > target_quantity:
                quantity = target_quantity
        else:
            adjustment = self._quantity_to_timedelta(quantity)
            if None not in (start, adjustment):
                end = start + adjustment
            elif None not in (end, adjustment):
                start = end - adjustment
            else:
                raise ValueError(
                    "Two of the three following parameters must be provided: "
                    "start, end, and quantity. "
                )
        return start, end, quantity

    def bounded_quantity(self, span: timedelta) -> int:
        """
        Return a pro-rated quantity given a timedelta and the bounds setting,
        which represents units per hour.
        """
        hours = span.total_seconds() / 60 / 60
        return int(round(hours * self.bounds))

    def _modify_overlaps(self, start, end, quantity):
        """
        Modify the database contents so that the sum of the overlaps for any
        range of time do not exceed the bounds.
        """
        # A bounds setting of zero means that the quantities are unbounded.
        if self.bounds == 0:
            return None
        if isinstance(quantity, timedelta):
            quantity = self._timedelta_to_quantity(quantity)
        overlaps = list()
        new_rows = list()
        # Load the overlapping rows
        for row in self.filter(start=start, end=end):
            overlaps.append(
                dict([(LogDb.log_table_def[i][0], val) for i, val in enumerate(row)])
            )
        # Create a list of times within our range of interest.
        # We're going to sort these then iterate through the time slices.
        times = {start, end}
        for row in overlaps:
            if start < row["start"] < end:
                times.add(row["start"])
            if start < row["end"] < end:
                times.add(row["end"])
        times = sorted(times)
        previous = None
        # Iterate through the time slices.
        for time in times:
            if previous is None:
                previous = time
                continue
            # Calculate the maximum allowable in the time slice.
            slice_max = self.bounded_quantity(time - previous)
            candidate_contrib = self.slice_contrib(
                {"start": start, "end": end, "quantity": quantity}, previous, time
            )
            if candidate_contrib > slice_max:
                raise ValueError(
                    "Failed sanity check. Inserted quantity is greater than "
                    "size of slice to be inserted into."
                )
            iteration = 0
            while True:
                iteration += 1
                if iteration > 1000000:
                    raise OverflowError("Max iterations.")
                contrib = [self.slice_contrib(row, previous, time) for row in overlaps]
                contrib_scale = sorted(set(contrib))
                contrib_sum = sum(contrib)
                current_total = contrib_sum + candidate_contrib
                overrun = current_total - slice_max
                if overrun <= 0.0 or len(contrib_scale) == 0:
                    break
                # What's the largest and next largest contrib?
                max_contrib = contrib_scale[-1]
                if len(contrib_scale) > 1:
                    next_largest_contrib = contrib_scale[-2]
                else:
                    next_largest_contrib = 0
                # The adjustment opportunity for this step.
                max_adjustment = contrib.count(max_contrib) * (
                    max_contrib - next_largest_contrib
                )
                if overrun >= max_adjustment:
                    subtraction_step = max_adjustment / contrib.count(max_contrib)
                else:
                    subtraction_step = overrun / contrib.count(max_contrib)
                for i, amount in enumerate(contrib):
                    if amount == max_contrib:
                        overlaps[i]["quantity"] -= subtraction_step
                        overlaps[i]["_touched"] = True
                        if subtraction_step >= amount and overlaps[i]["quantity"] > 0:
                            # We need a trim not a shave
                            entry_a = overlaps[i]
                            if entry_a["start"] < previous and entry_a["end"] > time:
                                # Entry spans beyond previous & time,
                                # Split it in two.
                                entry_b = copy.deepcopy(entry_a)
                                entry_b["id"] = None
                                del entry_b["_touched"]
                                entry_b["end"] = previous
                                entry_a["start"] = time
                                # We can use seconds here because we're
                                # using them to compare the quantity of the
                                # two slices. Not using them as the entry's
                                # quantity.
                                a_seconds = (
                                    entry_a["end"] - entry_a["start"]
                                ).total_seconds()
                                b_seconds = (
                                    entry_b["end"] - entry_b["start"]
                                ).total_seconds()
                                entry_b["quantity"] = entry_b["quantity"] * (
                                    b_seconds / (a_seconds + b_seconds)
                                )
                                entry_a["quantity"] = entry_a["quantity"] * (
                                    a_seconds / (a_seconds + b_seconds)
                                )
                                new_rows.append(entry_b)
                            elif previous <= entry_a["start"] <= time:
                                entry_a["start"] = time
                            elif previous <= entry_a["end"] <= time:
                                entry_a["end"] = previous
            previous = time  # (for time in times)
        modified_ids = []
        removed_ids = []
        created_ids = []
        c = self.connection.cursor()
        try:
            for i, row in enumerate(overlaps):
                if "_touched" in row:
                    if row["quantity"] == 0:
                        orig_entry = self.row(row["id"])
                        if orig_entry:
                            self.record_change(dict(orig_entry), "remove")
                        c.execute(
                            "DELETE FROM activitylog WHERE id=?",
                            [
                                row["id"],
                            ],
                        )
                        removed_ids.append(row["id"])
                    else:
                        orig_entry = self.row(row["id"])
                        if orig_entry:
                            self.record_change(dict(orig_entry), "modify")
                        statement = (
                            "UPDATE activitylog "
                            "SET start = ?, end = ?, quantity = ? "
                            "WHERE id = ?"
                        )
                        values = (row["start"], row["end"], row["quantity"], row["id"])
                        c.execute(statement, values)
                        modified_ids.append(row["id"])
            for row in new_rows:
                statement = (
                    "INSERT INTO activitylog (activity, start, end, quantity) "
                    "VALUES (?, ?, ?, ?)"
                )
                values = (row["activity"], row["start"], row["end"], row["quantity"])
                c.execute(statement, values)
                last_id = c.lastrowid
                created_ids.append(last_id)
                row["id"] = last_id
                self.record_change(row, "add")
        finally:
            c.close()
            self.connection.commit()
        for id_ in modified_ids:
            self.signal("entry_modified", id_)
        for id_ in removed_ids:
            self.signal("entry_removed", id_)
        for id_ in created_ids:
            self.signal("entry_added", id_)

    def slice_activities(self, start, end, level=None, unrecorded=True, activity=None):
        """
        Return a dictionary of activity names to proportional time spent.

        Parameters:
        level determines the depth of activity names used.
        unrecorded will add an unrecorded entry.
        """
        assert start < end
        assert isinstance(start, datetime)
        assert isinstance(end, datetime)
        overlap = self.filter(start=start, end=end, activity=activity)
        # span = (end-start).total_seconds()
        span = self._timedelta_to_quantity(end - start)
        output = OrderedDict()
        for row in overlap:
            contrib = self.slice_contrib(row, start, end)
            if contrib and span:
                proportion = contrib / span
                split_activity = [n.strip() for n in row["activity"].split(":")]
                if level is None or level >= len(split_activity):
                    piece = " : ".join(split_activity)
                else:
                    piece = " : ".join(split_activity[:level])
                if piece in output.keys():
                    output[piece] += proportion
                else:
                    output[piece] = proportion
        if unrecorded:
            amount = 1.0 - sum(output.values())
            output.update({"unrecorded": amount})
        return output

    def span_slices(
        self,
        start,
        span=timedelta(days=1),
        slice_size=timedelta(minutes=15),
        level=None,
        unrecorded=None,
    ):
        """
        Return a list of slice midpoints as datetime instances,
        and a dictionary whose keys are activity names and whose values
        lists of proportions, with the same length as the number of slices.
        """
        if isinstance(span, (float, int)):
            span = self._quantity_to_timedelta(span)
        if isinstance(slice_size, (float, int)):
            slice_size = self._quantity_to_timedelta(slice_size)
        if isinstance(slice_size, timedelta):
            slice_size = slice_size.total_seconds()
        if isinstance(span, timedelta):
            span = span.total_seconds()
        if span % slice_size:
            slice_size = span / round(span / float(slice_size))
        if not isinstance(start, datetime) and isinstance(start, datetime.date):
            start = datetime(start.year, start.month, start.day, 0, 0, 0)
        slices_in_span = int(span / slice_size)
        slice_midpoints = []
        activity_series = {}
        for i in range(slices_in_span):
            slice_start = start + timedelta(seconds=(i * slice_size))
            slice_midpoint = slice_start + timedelta(seconds=slice_size / 2.0)
            slice_midpoints.append(slice_midpoint)
            slice_end = slice_start + timedelta(seconds=slice_size)
            activities = self.slice_activities(
                slice_start, slice_end, level, unrecorded
            )
            for k, v in activities.items():
                if k not in activity_series.keys():
                    activity_series[k] = [
                        0,
                    ] * slices_in_span
                activity_series[k][i] = v
        return slice_midpoints, activity_series

    def stacked_slices(
        self,
        start,
        span=timedelta(days=1),
        slice_size=timedelta(minutes=15),
        level=None,
        unrecorded=None,
        weekdays=None,
        weekly=False,
    ):
        """
        Stack the span_slices of a range by time-of-day or calendar week.

        Return a list of seconds since start of day/week and an activity series
        like span slices does.

        weekdays parameter parameter is only applied to daily stack.
        """
        # TODO : Filter weekdays for weekly
        if isinstance(span, timedelta):
            end = start + span
        elif isinstance(span, (float, int)):
            end = start + timedelta(seconds=span)
        if weekly:
            year, week, weekday = start.isocalendar()
            start_date = iso_to_gregorian(year, week, 1)
            increment_count = max(
                1,
                round(
                    (end - start).total_seconds() / timedelta(days=7).total_seconds()
                ),
            )
        else:
            increment_count = int(
                round((end - start).total_seconds() / timedelta(days=1).total_seconds())
            )
        midpoints = None
        activity_series = dict()
        if weekly:
            current = datetime(
                start_date.year, start_date.month, start_date.day, 0, 0, 0
            )
            step = timedelta(days=7)
        else:
            current = datetime(start.year, start.month, start.day, 0, 0, 0)
            step = timedelta(days=1)
        for increment in range(increment_count):
            if (
                not weekly
                and weekdays is not None
                and current.weekday() not in weekdays
            ):
                current = current + timedelta(days=1)
                continue
            current_midpoints, current_activities = self.span_slices(
                current,
                step,
                slice_size,
                level,
                unrecorded=True,
            )
            if midpoints is None:
                midpoints = [
                    (entry - current).total_seconds() for entry in current_midpoints
                ]
            for k in current_activities.keys():
                if k not in activity_series:
                    # Initialize 2d array for this activity
                    activity_series[k] = [[] for n in range(len(midpoints))]
                for i in range(len(current_activities[k])):
                    activity_series[k][i].append(current_activities[k][i])
            current = current + step
        # Get the sum of the activity_series entries.
        for k in activity_series.keys():
            for i in range(len(activity_series[k])):
                activity_series[k][i] = sum(activity_series[k][i])
            assert len(midpoints) == len(activity_series[k])
        # Normalize the values laterally to be 1.0.
        for i in range(len(midpoints)):
            lateral_sum = float(
                sum([activity_series[k][i] for k in activity_series.keys()])
            )
            for k in activity_series.keys():
                activity_series[k][i] = activity_series[k][i] / lateral_sum
        if not unrecorded and "unrecorded" in activity_series:
            del activity_series["unrecorded"]
        return midpoints, activity_series

    def remove_entry(self, id_):
        removed_entry = self.row(id_)
        if removed_entry:
            self.record_change(dict(removed_entry), "remove")
        c = self.connection.cursor()
        try:
            c.execute(
                "DELETE FROM activitylog WHERE id=?",
                [
                    id_,
                ],
            )
        finally:
            c.close()
            self.connection.commit()
        self.signal("entry_removed", id_)

    def row(self, id_):
        """Singleton row look-up by id."""
        c = self.connection.cursor()
        try:
            c.execute(
                "SELECT * FROM activitylog WHERE id=?",
                [
                    id_,
                ],
            )
            return c.fetchone()
        finally:
            c.close()

    def activities(self):
        c = self.connection.cursor()
        try:
            c.execute(
                "SELECT DISTINCT activity FROM activitylog",
            )
            result = c.fetchall()
        finally:
            c.close()
        return [row["activity"] for row in result]

    @staticmethod
    def format_duration(seconds):
        """
        Return an aproximate string representation for a given number of
        seconds.
        """
        minutes = int(round(seconds / 60))
        hours = int(minutes / 60)
        if hours:
            minutes = minutes % (hours * 60)
        days = int(hours / 24)
        if days:
            hours = hours % (days * 24)
        output = []
        for num, suffix in ((days, "d"), (hours, "h"), (minutes, "m")):
            if num:
                output.append("{0}{1}".format(num, suffix))
        output_string = " ".join(output)
        return output_string

    @staticmethod
    def _seconds_from_strings(days, hours, minutes):
        seconds = 0
        if days:
            seconds += float(days) * 24 * 3600
        if hours:
            seconds += float(hours) * 3600
        if minutes:
            seconds += float(minutes) * 60
        return seconds

    @staticmethod
    def parse_duration(raw: str) -> float:
        """
        Return the number of seconds a duration string represents,
        or None if there is an error parsing it.
        """
        if raw is None or not raw.strip():
            return None

        try:
            hours = float(raw.strip())
            return hours * 3600
        except ValueError:
            pass
        style_a = re.compile(
            r"\s*(?P<days>[\d.]+\s*:)?"
            r"\s*(?P<hours>[\d.]+)\s*:\s*(?P<minutes>[\d.]+)\s*",
            re.IGNORECASE,
        )
        style_b_days = re.compile(r"(?P<days>[\d.]+)?\s*d(ays?)?", re.IGNORECASE)
        style_b_hours = re.compile(r"(?P<hours>[\d.]+)?\s*h(ours?)?", re.IGNORECASE)
        style_b_minutes = re.compile(
            r"(?P<minutes>[\d.]+)?\s*m(inutes?)?", re.IGNORECASE
        )
        match = style_a.search(raw)
        if match:
            days = match.group("days")
            hours = match.group("hours")
            minutes = match.group("minutes")
            return LogDb._seconds_from_strings(days, hours, minutes)
        style_b = [style_b_days, style_b_hours, style_b_minutes]
        for i, finder in enumerate(style_b):
            m = finder.search(raw)
            if m and m.groups()[0]:
                style_b[i] = m.groups()[0]
            else:
                style_b[i] = None
        if style_b != (None, None, None):
            return LogDb._seconds_from_strings(*style_b)

    def slice_contrib(self, row, start: datetime, end: datetime) -> int:
        """
        Return the quantity that a row contains within a given time span.
        """
        if (
            start <= row["start"] <= end
            or start <= row["end"] <= end
            or (start > row["start"] and end < row["end"])
        ):
            slice_start = max(start, row["start"])
            slice_end = min(end, row["end"])
            proportion = (slice_end - slice_start).total_seconds() / float(
                (row["end"] - row["start"]).total_seconds()
            )
            quantity = row["quantity"]
            if quantity is None:
                quantity = self.bounded_quantity(row["end"] - row["start"])
            return int(round(quantity * proportion))
        else:
            return 0

    def record_change(self, entry: dict, action: str = "add"):
        """
        Record the old version of a modified or deleted entry.
        Or the added version of a created entry.
        The action parameter may be 'add', 'modify', or 'remove'
        This will clear the redo stack, as well.
        """
        assert action in ("add", "modify", "remove")
        if self._current_action is None:
            self._current_action = {
                "add": [],
                "modify": [],
                "remove": [],
            }
        self._current_action[action].append(entry)

    def save_changes(self):
        """
        Save the current set of changes recorded with the record_change
        method to the undo stack.
        """
        self._undo_stack.append(self._current_action)
        self._current_action = None

    def apply_change_entry(self, change_entry):
        """
        Apply the contents of change_entry to the database and return a change
        entry that reverses it.
        This bypasses the normalization & checks of the create_entry method.
        """
        inverse_entry = {
            "add": change_entry["remove"],
            "remove": change_entry["add"],
            "modify": [],
        }
        ids_to_delete = [
            entry["id"] for entry in change_entry["add"] if entry["id"] is not None
        ]
        if ids_to_delete:
            statement = "DELETE FROM activitylog WHERE "
            statement += " OR ".join(("id = ?",) * len(ids_to_delete))
            c = self.connection.cursor()
            try:
                c.execute(statement, ids_to_delete)
            finally:
                c.close()
        for id_ in ids_to_delete:
            self.signal("entry_removed", id_)
        for entry in change_entry["remove"]:
            statement = (
                "INSERT INTO activitylog (id, activity, start, end, quantity) "
                "VALUES (?, ?, ?, ?, ?)"
            )
            values = [entry[r] for r in ("id", "activity", "start", "end", "quantity")]
            c = self.connection.cursor()
            try:
                c.execute(statement, values)
            finally:
                c.close()
                self.signal("entry_added", c.lastrowid)
        for entry in change_entry["modify"]:
            if "id" in entry:
                unchanged = self.row(entry["id"])
                if unchanged:
                    inverse_entry["modify"].append(unchanged)
            c = self.connection.cursor()
            try:
                statement = (
                    "UPDATE activitylog "
                    "SET start = ?, end = ?, quantity = ? "
                    "WHERE id = ?"
                )
                values = (entry["start"], entry["end"], entry["quantity"], entry["id"])
                c.execute(statement, values)
            finally:
                c.close()
                self.entry_modified.emit(entry["id"])
        self.connection.commit()
        return inverse_entry

    def undo(self):
        """Reverse the changes in the most recent undo action."""
        if self._current_action:
            self.save_changes()
        if not self._undo_stack:
            return
        last_changes = self._undo_stack.pop()
        redo_entry = self.apply_change_entry(last_changes)
        self._redo_stack.append(redo_entry)

    def redo(self):
        """Apply the most recent redo action."""
        if self._current_action:
            self.save_changes()
        if not self._redo_stack:
            return
        last_changes = self._redo_stack.pop()
        undo_entry = self.apply_change_entry(last_changes)
        self._undo_stack.append(undo_entry)

    def undo_possible(self):
        return bool(self._undo_stack)

    def redo_possible(self):
        return bool(self._redo_stack)
