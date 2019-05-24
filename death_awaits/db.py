import os
import sqlite3
import datetime
import re
from collections import OrderedDict
import copy


import dateutil
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widgets
import PyQt5.QtCore as core
from PyQt5.QtCore import Qt

from .helper import iso_to_gregorian, stringify_datetime


class LogDb(core.QObject):
    """ On-disk data store.  """
    table_def = (
        ('id', 'integer PRIMARY KEY'),
        ('activity', 'text'),
        ('start', 'timestamp'),
        ('end', 'timestamp'),
        ('duration', 'real'),  # seconds
    )
    entry_added = core.pyqtSignal(int)
    entry_modified = core.pyqtSignal(int)
    entry_removed = core.pyqtSignal(int)

    def __init__(self, filename=None, parent=None):
        super(LogDb, self).__init__(parent)
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
        self.connection.create_function(
            "contains_weekday", 3, LogDb.contains_weekday
        )
        if new_file:
            c = self.connection.cursor()
            try:
                c.execute(
                    "CREATE TABLE activitylog (" + (
                        ", ".join(
                            ["{0} {1}".format(k,t)
                             for k,t in LogDb.table_def
                            ]
                        )
                    ) + ")"
                )
                c.execute("CREATE INDEX start_times ON activitylog (start)")
                c.execute("CREATE INDEX end_times ON activitylog (end)")
            finally:
                c.close()
                self.connection.commit()

    @staticmethod
    def regexp(expr, item):
        """
        http://stackoverflow.com/questions/5365451/problem-with-regexp-python-and-sqlite
        """
        if item is None:
            item = ''
        reg = re.compile(expr,re.IGNORECASE)
        result = reg.search(item)
        return result is not None

    @staticmethod
    def contains_weekday(start,end,day):
        """
        SQLite registered function takes two ISO datetimes and a weekday
        integer.

        Return True if start-end span includes a weekday.
        """
        start_day = dateutil.parser.parse(start).weekday()
        end_day = dateutil.parser.parse(end).weekday()
        return day in range(start_day, end_day + 1)

    def filter(
        self, activity=None, start=None, end=None,
        first=False, last=False, weekdays=None
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
            values.extend([start, end,] * 3)
        elif end is None and isinstance(start, datetime.datetime):
            clauses.append("? <= end")
            values.append(start)
        elif start is None and isinstance(end, datetime.datetime):
            clauses.append("? >= start")
            values.append(start)
        if activity is not None:
            clauses.append("activity REGEXP ?")
            values.append(activity)
        if weekdays:
            clauses.append(
                "("+(" OR ".join(
                    ['contains_weekday(start, end, ?)'] * len(weekdays)
                ))+")"
            )
            values.extend(weekdays)
        if clauses:
            statement += "WHERE "+(" AND ".join(clauses))+" "
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

    def print_(self, *args, **kwargs):
        """
        Print a table of rows, arguments are passed to the filter method.
        """
        rows = self.filter(*args,**kwargs)
        if len(rows) == 0:
            print("{0}({1}) is empty.".format(
                self.__class__.__name__, repr(self._filename)
            ))
            return None
        headers = [n[0] for n in LogDb.table_def]
        data = []
        for row in rows:
            entry = []
            for k in headers:
                if isinstance(row[k],datetime.datetime):
                    entry.append(row[k].strftime("%a %Y-%m-%d %I:%M %p"))
                elif k == 'duration':
                    entry.append(LogDb.format_duration(row[k]))
                else:
                    entry.append(str(row[k]))
            data.append(entry)
        column_widths = [
            max([len(e[i]) for e in data])
            for i in range(len(headers))
        ]
        column_widths = [
            max(column_widths[i],len(headers[i]))
            for i in range(len(headers))
        ]
        lines = list()
        lines.append(
            " | ".join(
                [" {0:<{1}s}".format(headers[i], column_widths[i])
                 for i in range(len(headers))
                ]
            )
        )
        lines.append("_"*len(lines[0]))
        for entry in data:
            lines.append(
                " | ".join(
                    [" {0:<{1}}".format(entry[i], column_widths[i])
                     for i in range(len(entry))
                    ]
                )
            )
        for line in lines:
            print(line)

    def create_entry(
        self, activity, start=None, end=None, duration=None, id=None,
        apply_capitalization=False,
    ):
        """ Return the id of the inserted entry.  """
        if id is not None:
            self.remove_entry(id)
        activity = self._check_activity(activity, apply_capitalization)
        start, end, duration = self._normalize_range(start, end, duration)
        activity, start, end, duration = self._merge_common(
            activity, start, end, duration
        )
        self._modify_overlaps(start, end, duration)
        if isinstance(duration,datetime.timedelta):
            duration = duration.total_seconds()
        c = self.connection.cursor()
        try:
            statement = (
                "INSERT INTO activitylog (activity, start, end, duration) "
                "VALUES (?, ?, ?, ?)"
            )
            values = (activity, start, end, duration)
            c.execute(statement, values)
            row_id =  c.lastrowid
            new_entry = {
                'id' : row_id,
                'activity' : activity,
                'start' : start,
                'end' : end,
                'duration' : duration,
            }
            self.record_change(new_entry, 'add')
            return row_id
        finally:
            c.close()
            self.connection.commit()
            self.entry_added.emit(c.lastrowid)

    def rename_entry(self, activity, ids, apply_capitalization=False):
        if isinstance(ids, int):
            ids = [ids, ]
        elif isinstance(ids, (list, tuple)):
            non_compliant = [n for n in ids if not isinstance(n, int)]
            if non_compliant:
                raise TypeError(
                    'Non-integer id parameter{0}: {1}'.format(
                        's' if len(non_compliant) > 1 else '',
                        ', '.join(non_compliant)
                    )
                )
        activity = self._check_activity(activity, apply_capitalization)
        effected_rows = list()
        for id in ids:
            entry = dict(self.row(id))
            if entry['activity'] != activity:
                self.record_change(entry, 'modify')
                effected_rows.append(id)
        statement = "UPDATE activitylog SET activity = ? WHERE "
        statement += " OR ".join(["id = ?" for n in ids])
        c = self.connection.cursor()
        try:
            values = [activity,]
            values.extend(ids)
            c.execute(statement, values)
        finally:
            c.close()
            self.connection.commit()
        for id in effected_rows:
            self.entry_modified.emit(id)

    def shift_rows(self, ids, amount):
        if isinstance(amount, (float, int)):
            amount = datetime.timedelta(seconds=amount)
        assert isinstance(amount, datetime.timedelta)
        data = list()
        for id in ids:
            assert isinstance(id, int)
            data.append(dict(self.row(id)))
            self.remove_entry(id)
        for i in range(len(data)):
            data[i]['start'] += amount
            data[i]['end'] += amount
        data.sort(key=lambda n: n['start'])
        for row in data:
            self.create_entry(**row)

    @staticmethod
    def _row_density(duration, start, end):
        assert isinstance(start, datetime.datetime)
        assert isinstance(end, datetime.datetime)
        if isinstance(duration,datetime.timedelta):
            duration = duration.total_seconds()
        span = float((start - end).total_seconds())
        if span == 0:
            return 0
        return duration / span

    def _merge_common(self, activity, start, end, duration):
        rows = self.filter(activity, start, end)
        ids_to_delete = []
        if isinstance(duration, datetime.timedelta):
            duration = duration.total_seconds()
        new_density = self._row_density(duration, start, end)
        for row in rows:
            if activity != row['activity']:
                continue
            row_density = self._row_density(
                row['duration'], row['start'], row['end']
            )
            if abs(new_density - row_density) < 0.0001 or (
                start == row['start'] and end == row['end']
            ):
                start = min(start, row['start'])
                end = max(end, row['end'])
                span = end - start
                if duration + row['duration'] > span.total_seconds():
                    duration = span.total_seconds()
                else:
                    duration = duration + row['duration']
                ids_to_delete.append(row['id'])
        for id in ids_to_delete:
            entry = self.row(id)
            if entry:
                self.record_change(dict(entry), 'remove')
        if ids_to_delete:
            statement = "DELETE FROM activitylog WHERE "
            statement += " OR ".join(("id = ?",) * len(ids_to_delete))
            c = self.connection.cursor()
            try:
                c.execute(statement, ids_to_delete)
            finally:
                c.close()
                self.connection.commit()
        for id in ids_to_delete:
            self.entry_removed.emit(id)
        return activity, start, end, duration

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
                if row['activity'] != activity:
                    ids.append(row['id'])
                    self.record_change(dict(row),'modify')
            c = self.connection.cursor()
            try:
                statement = "UPDATE activitylog SET activity = ? WHERE "
                statement += "OR ".join(['id=?',]*len(ids))
                variables = [activity,] + ids
                c.execute(statement, variables)
            finally:
                c.close()
                self.connection.commit()
            for id in ids:
                self.entry_modified.emit(id)
        elif preexisting:
            activity = preexisting
        return activity

    @staticmethod
    def _normalize_range(start=None, end=None, duration=None):
        """
        If one of the time parameters (start, end, duration) are not given,
        this method will infer it from the other two.
        """
        if isinstance(duration,datetime.timedelta):
            duration = duration.total_seconds()
        if None not in (start, end):
            assert start < end
            span = end - start
            if duration is None or duration > span.total_seconds():
                duration = span.total_seconds()
        elif None not in (start, duration):
            end = start + datetime.timedelta(seconds=duration)
        elif None not in (end, duration):
            start = end - datetime.timedelta(seconds=duration)
        else:
            raise ValueError(
                "Two of the three following parameters must be provided: "
                "start, end, and duration. "
            )
        return start, end, duration

    def _modify_overlaps(self, start, end, duration):
        """
        Modify the database contents so that the sum of the overlaps for any
        range of time do not exceed the duration of the range.
        """
        overlaps = list()
        new_rows = list()
        for row in self.filter(start=start,end=end):
            overlaps.append(
                dict([
                    (LogDb.table_def[i][0],val) for i, val in enumerate(row)
                ])
            )
        times = set((start,end))
        for row in overlaps:
            if start < row['start'] and end > row['start']:
                times.add(row['start'])
            if start < row['end'] and end > row['end']:
                times.add(row['end'])
        times = sorted(times)
        previous = None
        for time in times:
            if previous is None:
                previous = time
                continue
            slice_total = (time - previous).total_seconds()
            contrib = [
                self.slice_contrib(row, previous, time)
                for row in overlaps
            ]
            candidate_contrib = self.slice_contrib(
                {'start':start, 'end':end, 'duration':duration},
                previous, time
            )
            contrib_sum = sum(contrib)
            current_total = contrib_sum + candidate_contrib
            if current_total > slice_total:
                overrun = current_total - slice_total
                for i, amount in enumerate(contrib):
                    if amount <= 0:
                        continue
                    shave = overrun * (amount / float(contrib_sum))
                    overlaps[i]['duration'] -= shave
                    overlaps[i]['_touched'] = True
                    if shave >= amount and overlaps[i]['duration'] > 0:
                        # We need a trim not a shave
                        entry_a = overlaps[i]
                        if (entry_a['start'] < previous
                            and entry_a['end'] > time
                           ):
                            # Entry spans beyond previous & time, split it in two.
                            entry_b = copy.deepcopy(entry_a)
                            entry_b['id'] = None
                            del entry_b['_touched']
                            entry_b['end'] = previous
                            entry_a['start'] = time
                            a_seconds = (
                                entry_a['end'] - entry_a['start']
                            ).total_seconds()
                            b_seconds = (
                                entry_b['end'] - entry_b['start']
                            ).total_seconds()
                            entry_b['duration'] = (
                                entry_b['duration']
                                * (b_seconds / (a_seconds + b_seconds))
                            )
                            entry_a['duration'] = (
                                entry_a['duration']
                                * (a_seconds / (a_seconds + b_seconds))
                            )
                            new_rows.append(entry_b)
                        elif previous <= entry_a['start'] < time:
                            entry_a['start'] = time
                        elif previous <= entry_a['end'] < time:
                            entry_a['end'] = previous
            previous = time
        modified_ids = []
        removed_ids = []
        created_ids = []
        c = self.connection.cursor()
        try:
            for i, row in enumerate(overlaps):
                if '_touched' in row:
                    if row['duration'] == 0:
                        orig_entry = self.row(row['id'])
                        if orig_entry:
                            self.record_change(dict(orig_entry),'remove')
                        c.execute(
                            "DELETE FROM activitylog WHERE id=?",
                            [row['id'],]
                        )
                        removed_ids.append(row['id'])
                    else:
                        orig_entry = self.row(row['id'])
                        if orig_entry:
                            self.record_change(dict(orig_entry),'modify')
                        statement = (
                            'UPDATE activitylog '
                            'SET start = ?, end = ?, duration = ? '
                            'WHERE id = ?'
                        )
                        values = (
                            row['start'], row['end'],
                            row['duration'], row['id']
                        )
                        c.execute(statement, values)
                        modified_ids.append(row['id'])
            for row in new_rows:
                statement = (
                    "INSERT INTO activitylog (activity, start, end, duration) "
                    "VALUES (?, ?, ?, ?)"
                )
                values = (
                    row['activity'], row['start'], row['end'], row['duration']
                )
                c.execute(statement, values)
                last_id = c.lastrowid
                created_ids.append(last_id)
                row['id'] = last_id
                self.record_change(row,'add')
        finally:
            c.close()
            self.connection.commit()
        for id in modified_ids:
            self.entry_modified.emit(id)
        for id in removed_ids:
            self.entry_removed.emit(id)
        for id in created_ids:
            self.entry_added.emit(id)

    def print_daily_totals(self, date, level=None):
        assert isinstance(date, datetime.date)
        start = datetime.datetime.fromordinal(date.toordinal())
        day = datetime.timedelta(days=1)
        end = start + day
        activities = self.slice_activities(start, end, level)
        for k, v in activities.items():
            print("{0} : {1}".format(
                k, self.format_duration(v * day.total_seconds())
            ))

    def slice_activities(
        self, start, end, level=None, unrecorded=True, weekdays=None,
        activity=None
    ):
        """
        Return a dictionary of activity names to proportional time spent.

        Parameters:
        level determines the depth of activity names used.
        unrecorded will add an unrecorded entry.
        """
        assert start < end
        assert isinstance(start, datetime.datetime)
        assert isinstance(end, datetime.datetime)
        overlap = self.filter(start=start, end=end, activity=activity)
        span = (end-start).total_seconds()
        output = OrderedDict()
        for row in overlap:
            contrib = self.slice_contrib(row,start,end)
            if contrib and span:
                proportion = contrib / span
                split_activity = [n.strip() for n in row['activity'].split(":")]
                if level is None or level >= len(split_activity):
                    piece = ' : '.join(split_activity)
                else:
                    piece = ' : '.join(split_activity[:level])
                if piece in output.keys():
                    output[piece] += proportion
                else:
                    output[piece] = proportion
        if unrecorded:
            amount = 1.0 - sum(output.values())
            output.update({'unrecorded':amount})
        return output

    def span_slices(
        self, start, span=datetime.timedelta(days=1),
        chunk_size=datetime.timedelta(minutes=15), level=None, unrecorded=None,
    ):
        """
        Return a list of chunk midpoints,
        and a dictionary whose keys are activity names and whose values are
        proportions.
        """
        if isinstance(chunk_size,datetime.timedelta):
            chunk_size = chunk_size.total_seconds()
        if isinstance(span,datetime.timedelta):
            span = span.total_seconds()
        if span % chunk_size:
            chunk_size = span / round(span / float(chunk_size))
        if not isinstance(start,datetime.datetime) and isinstance(start,datetime.date):
            start = datetime.datetime(start.year, start.month, start.day, 0, 0, 0)
        chunks_in_span = int(span / chunk_size)
        chunk_midpoints = []
        activity_series = {}
        for i in range(chunks_in_span):
            chunk_start = start + datetime.timedelta(seconds=(i * chunk_size))
            chunk_midpoint = chunk_start + datetime.timedelta(
                seconds=chunk_size / 2.0
            )
            chunk_midpoints.append(chunk_midpoint)
            chunk_end = chunk_start + datetime.timedelta(seconds=chunk_size)
            activities = self.slice_activities(
                chunk_start, chunk_end, level, unrecorded
            )
            for k, v in activities.items():
                if k not in activity_series.keys():
                    activity_series[k] = [0,] * chunks_in_span
                activity_series[k][i] = v
        return chunk_midpoints, activity_series

    def stacked_slices(
        self, start, span=datetime.timedelta(days=1),
        chunk_size=datetime.timedelta(minutes=15), level=None, unrecorded=None,
        weekdays=None, weekly=False
    ):
        """
        Stack the span_slices of a range by time-of-day or calendar week.

        Return a list of seconds since start of day/week and an activity series
        like span slices does.

        weekdays parameter parameter is only applied to daily stack.
        """
        #TODO : Filter weekdays for weekly
        if isinstance(span,datetime.timedelta):
            end = start + span
        elif isinstance(span, (float,int)):
            end = start + datetime.timedelta(seconds=span)
        if weekly:
            year, week, weekday = start.isocalendar()
            start_date = iso_to_gregorian(year, week, 1)
            increment_count = max(
                1,
                round(
                    (end-start).total_seconds()
                    / datetime.timedelta(days=7).total_seconds()
                ),
            )
        else:
            increment_count = int(round(
                (end - start).total_seconds()
                / datetime.timedelta(days=1).total_seconds()
            ))
        midpoints = None
        activity_series = dict()
        if weekly:
            current = datetime.datetime(
                start_date.year, start_date.month, start_date.day, 0, 0, 0
            )
            step = datetime.timedelta(days=7)
        else:
            current = datetime.datetime(start.year, start.month, start.day, 0, 0, 0)
            step = datetime.timedelta(days=1)
        for increment in range(increment_count):
            if (not weekly and
                weekdays is not None
                and current.weekday() not in weekdays):
                current = current + datetime.timedelta(days=1)
                continue
            current_midpoints, current_activities = self.span_slices(
                current, step, chunk_size, level, unrecorded=True,
            )
            if midpoints is None:
                midpoints = [
                    (entry - current).total_seconds()
                    for entry in current_midpoints
                ]
            for k in current_activities.keys():
                if k not in activity_series:
                    # Initialize 2d array for this activity
                    activity_series[k] = [
                        [] for n in range(len(midpoints))
                    ]
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
            lateral_sum = float(sum(
                [activity_series[k][i] for k in activity_series.keys()]
            ))
            for k in activity_series.keys():
                activity_series[k][i] = activity_series[k][i] / lateral_sum
        if not unrecorded and 'unrecorded' in activity_series:
            del activity_series['unrecorded']
        #import pdb; pdb.set_trace()
        return midpoints, activity_series

    def remove_entry(self,id):
        removed_entry = self.row(id)
        if removed_entry:
            self.record_change(dict(removed_entry), 'remove')
        c = self.connection.cursor()
        try:
            c.execute("DELETE FROM activitylog WHERE id=?", [id,])
        finally:
            c.close()
            self.connection.commit()
        self.entry_removed.emit(id)

    def row(self,id):
        """ Singleton row look-up by id.  """
        c = self.connection.cursor()
        try:
            c.execute("SELECT * FROM activitylog WHERE id=?", [id,])
            return c.fetchone()
        finally:
            c.close()

    def activities(self):
        c = self.connection.cursor()
        try:
            c.execute("SELECT DISTINCT activity FROM activitylog",)
            result = c.fetchall()
        finally:
            c.close()
        return [row['activity'] for row in result]

    @staticmethod
    def format_duration(seconds):
        """
        Return an aproximate string representation for a given number of
        seconds.
        """
        minutes = int(round(seconds / 60))
        hours = int(minutes/60)
        if hours:
            minutes = minutes % (hours * 60)
        days = int(hours/24)
        if days:
            hours = hours % (days * 24)
        output = []
        for num, suffix in ((days,'d'),(hours,'h'),(minutes,'m')):
            if num:
                output.append("{0}{1}".format(num,suffix))
        output_string = ' '.join(output)
        return output_string

    @staticmethod
    def parse_duration(raw):
        """
        Return the number of seconds a duration string represents,
        or None if there is an error parsing it.
        """
        if raw is None or not raw.strip():
            return None
        def _seconds_from_strings(days,hours,minutes):
            seconds = 0
            if days:
                seconds += float(days) * 24 * 3600
            if hours:
                seconds += float(hours) * 3600
            if minutes:
                seconds += float(minutes) * 60
            return seconds
        try:
            hours = float(raw.strip())
            return hours * 3600
        except ValueError:
            pass
        style_a = re.compile(
            r'\s*(?P<days>[\d.]+\s*:)?'
            r'\s*(?P<hours>[\d.]+)\s*:\s*(?P<minutes>[\d.]+)\s*'
            , re.IGNORECASE
        )
        style_b_days = re.compile(
            r'(?P<days>[\d.]+)?\s*d(ays?)?', re.IGNORECASE
        )
        style_b_hours = re.compile(
            r'(?P<hours>[\d.]+)?\s*h(ours?)?', re.IGNORECASE
        )
        style_b_minutes = re.compile(
            r'(?P<minutes>[\d.]+)?\s*m(inutes?)?', re.IGNORECASE
        )
        match = style_a.search(raw)
        if match:
            days = match.group('days')
            hours = match.group('hours')
            minutes = match.group('minutes')
            return _seconds_from_strings(days,hours,minutes)
        style_b = [style_b_days, style_b_hours, style_b_minutes ]
        for i, finder in enumerate(style_b):
            m = finder.search(raw)
            if m and m.groups()[0]:
                style_b[i] = m.groups()[0]
            else:
                style_b[i] = None
        if style_b != (None,None,None):
            return _seconds_from_strings(*style_b)

    @staticmethod
    def slice_contrib(row,start,end):
        """
        Return the number of seconds the row has within the given time span.
        """
        if (start <= row['start'] <= end
            or start <= row['end'] <= end
            or (start > row['start'] and end < row['end'])
           ):
            slice_start = max(start, row['start'])
            slice_end = min(end, row['end'])
            proportion = (
                (slice_end - slice_start).total_seconds()
                / float((row['end'] - row['start']).total_seconds())
            )
            duration = row['duration']
            if isinstance(duration,datetime.timedelta):
                duration = duration.total_seconds()
            elif duration is None:
                duration = (row['end'] - row['start']).total_seconds()
            return duration * proportion
        else:
            return 0

    def record_change(self, entry, action='add'):
        """
        Record the old version of a modified or deleted entry.
        Or the added verson of a created entry.
        The action parameter may be 'add', 'modify', or 'remove'
        This will clear the redo stack, as well.
        """
        assert action in ('add','modify','remove')
        if self._current_action is None:
            self._current_action = {
                'add' : [], 'modify' : [], 'remove' : [],
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
            'add' : change_entry['remove'],
            'remove' : change_entry['add'],
            'modify' : [],
        }
        ids_to_delete = [
            entry['id'] for entry in change_entry['add']
            if entry['id'] is not None
        ]
        if ids_to_delete:
            statement =  "DELETE FROM activitylog WHERE "
            statement += " OR ".join(("id = ?",) * len(ids_to_delete))
            c = self.connection.cursor()
            try:
                c.execute(statement, ids_to_delete)
            finally:
                c.close()
        for id in ids_to_delete:
            self.entry_removed.emit(id)
        for entry in change_entry['remove']:
            statement = (
                "INSERT INTO activitylog (id, activity, start, end, duration) "
                "VALUES (?, ?, ?, ?, ?)"
            )
            values = [
                entry[r] for r in
                ('id', 'activity', 'start', 'end', 'duration')
            ]
            c = self.connection.cursor()
            try:
                c.execute(statement, values)
            finally:
                c.close()
                self.entry_added.emit(c.lastrowid)
        for entry in change_entry['modify']:
            if 'id' in entry:
                unchanged = self.row(entry['id'])
                if unchanged:
                    inverse_entry['modify'].append(unchanged)
            c = self.connection.cursor()
            try:
                statement = (
                    'UPDATE activitylog '
                    'SET start = ?, end = ?, duration = ? '
                    'WHERE id = ?'
                )
                values = (
                    entry['start'], entry['end'],
                    entry['duration'], entry['id']
                )
                c.execute(statement, values)
            finally:
                c.close()
                self.entry_modified.emit(entry['id'])
        self.connection.commit()
        return inverse_entry

    def undo(self):
        """ Reverse the changes in the most recent undo action.  """
        if self._current_action:
            self.save_changes()
        if not self._undo_stack:
            return
        last_changes = self._undo_stack.pop()
        redo_entry = self.apply_change_entry(last_changes)
        self._redo_stack.append(redo_entry)

    def redo(self):
        """ Apply the most recent redo action.  """
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


class LogModel(core.QAbstractTableModel):
    """ In-memory data store. """
    def __init__(self, database, activity=None,start=None,end=None,parent=None):
        super(LogModel,self).__init__(parent)
        assert isinstance(database, LogDb)
        self._db = database
        self._cache = []
        self.update_cache(activity=None, start=None,end=None)
        # Connections
        self._db.entry_added.connect(self._handle_addition)
        self._db.entry_modified.connect(self._handle_modification)
        self._db.entry_removed.connect(self._handle_deletion)

    def update_cache(self,activity=None,start=None,end=None):
        if isinstance(activity, str) and activity.strip() == '':
            activity = None
        self.beginResetModel()
        self._cache = self._db.filter(activity, start, end)
        self._current_filter = (activity,start,end)
        self.endResetModel()

    def rowCount(self,parent=None):
        return len(self._cache)

    def columnCount(self, parent=None):
        return len(LogDb.table_def)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        column_name = LogDb.table_def[index.column()][0]
        if role == Qt.DisplayRole:
            data = self._cache[index.row()][column_name]
            if isinstance(data, datetime.datetime):
                data = stringify_datetime(data)
            elif column_name == 'duration':
                data = LogDb.format_duration(data)
            return data
        elif role == Qt.UserRole:
            return self._cache[index.row()]
        elif role == Qt.BackgroundRole:
            if index.row() % 2:
                return gui.QBrush(
                    widgets.QApplication.instance().palette().color(
                        gui.QPalette.AlternateBase
                    )
                )
            else:
                return gui.QBrush(
                    widgets.QApplication.instance().palette().color(
                        gui.QPalette.Base
                    )
                )

    def headerData(self,section,orientation,role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return LogDb.table_def[section][0].title()

    def create_entry(
        self, activity, start, end, duration=None, id=None,
        apply_capitalization=False
    ):
        """ Create an entry and return the new id.  """
        return self._db.create_entry(
            activity, start, end, duration, id, apply_capitalization
        )

    def delete_entry(self, id):
        self._db.remove_entry(id)

    def adjust_entries(self, ids, amount):
        self._db.shift_rows(ids, amount)

    def _handle_deletion(self, id):
        for r in range(self.rowCount()):
            entry = self.data(self.index(r,0),Qt.UserRole)
            if entry is not None and entry['id'] == id:
                self.beginRemoveRows(core.QModelIndex(), r, r)
                del self._cache[r]
                self.endRemoveRows()
                break

    def _handle_addition(self, id):
        row = self._db.row(id)
        if self._fits_filter(row):
            for i, current in enumerate(self._cache):
                if current['start'] > row['start']:
                    self.beginInsertRows(core.QModelIndex(), i, i)
                    self._cache.insert(i,row)
                    self.endInsertRows()
                    break
            else:
                i = len(self._cache)
                self.beginInsertRows(core.QModelIndex(), i, i)
                self._cache.append(row)
                self.endInsertRows()

    def _handle_modification(self, id):
        row = self._db.row(id)
        if self._fits_filter(row):
            for i, current in enumerate(self._cache):
                if current['id'] == row['id']:
                    self._cache[i] = row
                    left_index = self.index(i,0)
                    right_index = self.index(i,self.columnCount()-1)
                    self.dataChanged.emit(left_index,right_index)
                    break

    def _fits_filter(self, entry):
        """ Check entry parameter against the current filter.  """
        time_ok, activity_ok = False, False
        activity, start, end = self._current_filter
        if None not in (start, end):
            try:
                if (start <= entry['start'] <= end
                    or start <= entry['end'] <= end
                    or (entry['start'] <= start and  entry['end'] >= end)
                   ):
                    time_ok = True
            except TypeError:
                print(
                    "start : {0}, end : {1},"
                    "\nentry['start'] : {2}, entry['end'] : {3}".format(
                        repr(start), repr(end),
                        repr(entry['start']), repr(entry['end']),
                    )
                )
                raise
        elif end is not None and isinstance(start,datetime.datetime):
            if entry['start'] <= end:
                time_ok = True
        elif start is not None and isinstance(end,datetime.datetime):
            if entry['end'] >= start:
                time_ok = True
        else:
            time_ok = True
        if activity is None:
            activity_ok = True
        else:
            reg = re.compile(activity, re.IGNORECASE)
            activity_ok = reg.search(entry['activity']) is not None
        return time_ok and activity_ok

