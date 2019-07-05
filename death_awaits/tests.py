import sys
import unittest
from datetime import datetime, timedelta

import PyQt5.QtWidgets as widgets
from PyQt5.QtCore import Qt

from death_awaits.db import LogDb
from death_awaits.main import FilterPanel
from death_awaits.helper import iso_to_gregorian

NOW = datetime.now()


def minutes(n):
    return timedelta(seconds=n*60)


def hours(n):
    return minutes(n*60)


COLUMNS = ('activity', 'start', 'end', 'duration')

ENTRIES = (
    # (activity, start, end, duration)
    ('sleep', NOW, NOW + hours(8), None),
    ('eat', NOW + hours(7), None, hours(1).seconds),
    ('eat', NOW + hours(7.5), None, hours(1).seconds),
)


class TestLogDb(unittest.TestCase):
    def setUp(self,):
        self.db = LogDb(":memory:")
        self.test_data = [dict(zip(COLUMNS, e)) for e in ENTRIES]

    def test_insertion_start_end(self):
        entry = self.test_data[0]
        entry.update({'end': entry['start']+hours(8), 'duration': None})
        id_ = self.db.create_entry(**entry)
        row = self.db.row(id_)
        self.assertEqual(row['activity'], entry['activity'])
        self.assertEqual(row['start'], entry['start'])
        self.assertEqual(row['end'], entry['end'])
        self.assertEqual(
            row['duration'], (entry['end']-entry['start']).seconds
        )

    def test_insertion_start_duration(self):
        entry = self.test_data[0]
        entry.update({'end': None, 'duration': hours(8)})
        id_ = self.db.create_entry(**entry)
        row = self.db.row(id_)
        self.assertEqual(row['activity'], entry['activity'])
        self.assertEqual(row['start'], entry['start'])
        self.assertEqual(row['end'], entry['start']+entry['duration'])
        self.assertEqual(row['duration'], entry['duration'].seconds)

    def test_simple_overlap(self):
        entry_a = self.test_data[0]
        entry_b = self.test_data[1]
        id_a = self.db.create_entry(**entry_a)
        row_a = self.db.row(id_a)
        initial_duration = row_a['duration'] / 60 / 60
        id_b = self.db.create_entry(**entry_b)
        row_a = self.db.row(id_a)
        current_duration = row_a['duration'] / 60 / 60
        row_b = self.db.row(id_b)
        self.assertEqual(row_a['duration'] / 60 / 60, 7)
        self.assertEqual(row_b['duration'] / 60 / 60, 1)
        self.assertEqual(row_a['start'] + timedelta(hours=7), row_b['start'])
        self.assertEqual(
            row_b['start'] + timedelta(seconds=row_b['duration']), row_b['end']
        )
        self.assertLess(row_b['start'], row_a['end'])
        self.assertEqual(row_b['end'], row_a['end'])
        self.assertEqual(
            (row_a['duration']+row_b['duration']) / 60 / 60,
            (row_b['end'] - row_a['start']).total_seconds() / 60 / 60
        )

    def test_simple_combine(self):
        entry_a = self.test_data[1]
        entry_b = self.test_data[2]
        self.db.create_entry(**entry_a)
        id_b = self.db.create_entry(**entry_b)
        row_b = self.db.row(id_b)
        self.assertEqual(entry_a['start'], row_b['start'])
        self.assertEqual(
            entry_b['start'] + timedelta(seconds=entry_b['duration']),
            row_b['end']
        )

    def test_overwrite(self):
        id_a = self.db.create_entry(**self.test_data[1])
        entry_a = dict(self.db.row(id_a))
        entry_a['duration'] = entry_a['duration'] / 2.0
        id_b = self.db.create_entry(**entry_a)
        entry_b = self.db.row(id_b)
        self.assertEqual(id_a, id_b)
        self.assertAlmostEqual(entry_a['duration'], entry_b['duration'])

    def test_simple_slice_contrib(self):
        id_ = self.db.create_entry(**self.test_data[0])
        entry = self.db.row(id_)
        end = entry['start'] + timedelta(seconds=entry['duration']/2.0)
        contrib = self.db.slice_contrib(entry, entry['start'],end)
        self.assertAlmostEqual(entry['duration']/2.0, contrib)

    def test_slice_contrib_row_within_span(self):
        id_ = self.db.create_entry(**self.test_data[0])
        entry = self.db.row(id_)
        start = entry['start'] - timedelta(seconds=entry['duration']/4.0)
        end = entry['end'] + timedelta(seconds=entry['duration']/4.0)
        contrib = self.db.slice_contrib(entry, start, end)
        self.assertAlmostEqual(entry['duration'], contrib)

    def test_slice_contrib_span_within_row(self):
        id_ = self.db.create_entry(**self.test_data[0])
        entry = self.db.row(id_)
        start = entry['start'] + timedelta(seconds=entry['duration']/4.0)
        end = entry['end'] - timedelta(seconds=entry['duration']/4.0)
        contrib = self.db.slice_contrib(entry, start, end)
        self.assertAlmostEqual(entry['duration']/2.0, contrib)

    def test_slice_contrib_span_outside_row(self):
        id_ = self.db.create_entry(**self.test_data[0])
        entry = self.db.row(id_)
        start = entry['start'] - timedelta(seconds=entry['duration'] * 2)
        end = entry['end'] - timedelta(seconds=entry['duration'] * 1.5)
        contrib = self.db.slice_contrib(entry, start, end)
        self.assertAlmostEqual(0, contrib)

    def test_simple_slice_activities(self):
        id_ = self.db.create_entry(**self.test_data[0])
        entry = self.db.row(id_)
        activities = self.db.slice_activities(
            start=entry['start'],
            end=(
                entry['start']
                + timedelta(seconds=entry['duration'] * 2.0)
            ),
            level=1,
            unrecorded=True
        )
        self.assertEqual(activities['unrecorded'], 0.5)
        self.assertEqual(activities[entry['activity']], 0.5)

    def test_simple_span_slices(self):
        id_ = self.db.create_entry(**self.test_data[0])
        entry = self.db.row(id_)
        chunks, activities = self.db.span_slices(
            start=entry['start'],
            span=entry['duration'] * 2.0,
            chunk_size=entry['duration'] * 2.0,
            level=0,
            unrecorded=True,
        )
        self.assertAlmostEqual(activities['unrecorded'][0], 0.5)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(
            chunks[0],
            entry['start'] + timedelta(seconds=entry['duration'])
        )

    def test_entry_trimming_with_truncate(self):
        self.db.create_entry(
            'sleep', datetime(2013, 8, 28, 0, 41), datetime(2013, 8, 28, 6, 0)
        )
        self.db.create_entry(
            'bathroom',
            datetime(2013, 8, 28, 6, 28),
            datetime(2013, 8, 28, 7, 11)
        )
        self.db.create_entry(
            'sleep', datetime(2013, 8, 28, 0, 33), datetime(2013, 8, 28, 6, 41)
        )
        self.assertAlmostEqual(
            sum(self.db.slice_activities(
                datetime(2013, 8, 28, 6, 30),
                datetime(2013, 8, 28, 6, 45),
                unrecorded=False,
            ).values()
            ), 1.0
        )

    def test_entry_trimming_with_split(self):
        self.db.create_entry(
            'sleep', datetime(2013, 8, 28, 1, 0), datetime(2013, 8, 28, 4, 0)
        )
        self.db.create_entry(
            'bathroom', datetime(2013, 8, 28, 1, 30), datetime(2013, 8, 28, 2, 0)
        )
        self.assertEqual(len(self.db.filter()), 3)
        self.assertAlmostEqual(
            sum(self.db.slice_activities(
                datetime(2013, 8, 28, 1, 0),
                datetime(2013, 8, 28, 4, 0),
                unrecorded=False,
            ).values()
            ), 1.0
        )

    def test_simple_undo_redo(self):
        self.db.create_entry(
            'sleep', datetime(2013, 8, 28, 1, 0), datetime(2013, 8, 28, 4, 0)
        )
        self.db.save_changes()
        self.assertEqual(len(self.db.filter()), 1)
        self.assertTrue(self.db.undo_possible())
        self.db.undo()
        self.assertEqual(len(self.db.filter()), 0)
        self.assertFalse(self.db.undo_possible())
        self.db.redo()
        self.assertEqual(len(self.db.filter()), 1)
        self.assertTrue(self.db.undo_possible())

    def test_compound_undo_redo(self):
        # Create two entries, then create an entry that overwrites.
        self.db.create_entry(
            'sleep', datetime(2013, 8, 28, 1, 0), datetime(2013, 8, 28, 4, 0)
        )
        self.db.create_entry(
            'bathroom', datetime(2013, 8, 28, 4, 0), datetime(2013, 8, 28, 5, 0)
        )
        self.db.save_changes()
        self.assertEqual(len(self.db.filter()), 2)
        self.db.create_entry(
            'sleep', datetime(2013, 8, 28, 1, 0), datetime(2013, 8, 28, 6, 0)
        )
        self.db.save_changes()
        self.assertEqual(len(self.db.filter()), 1)
        self.db.undo()
        self.assertEqual(len(self.db.filter()), 2)
        self.db.redo()
        self.assertEqual(len(self.db.filter()), 1)

    def test_first_last(self):
        self.db.create_entry(
            'sleep', datetime(2013, 8, 27, 22, 0), datetime(2013, 8, 28, 6, 0)
        )
        self.db.create_entry(
            'bathroom', datetime(2013, 8, 28, 6, 0), datetime(2013, 8, 28, 7, 0)
        )
        self.db.create_entry(
            'commute', datetime(2013, 8, 28, 8, 0), datetime(2013, 8, 28, 9, 0)
        )
        self.db.create_entry(
            'work', datetime(2013, 8, 28, 9, 0), datetime(2013, 8, 28, 17, 0)
        )
        self.assertEqual(self.db.filter(first=True)['activity'], 'sleep')
        self.assertEqual(self.db.filter(last=True)['activity'], 'work')

    def test_fill_unrecorded_first(self):
        """
        When adding an activity to a span, we want to use up the unrecorded
        time before decreasing the other activities.
        """
        duration = timedelta(minutes=15).total_seconds()
        span = (NOW, NOW + timedelta(seconds=duration * 4))
        id_a = self.db.create_entry('activity a', span[0], span[1], duration)
        id_b = self.db.create_entry('activity b', span[0], span[1], duration)
        id_c = self.db.create_entry('activity c', span[0], span[1], duration)
        row_a = self.db.row(id_a)
        row_b = self.db.row(id_b)
        row_c = self.db.row(id_c)
        self.assertAlmostEqual(row_a['duration'], duration)
        self.assertAlmostEqual(row_b['duration'], duration)
        self.assertAlmostEqual(row_c['duration'], duration)
        self.assertAlmostEqual(
            self.db.slice_activities(span[0], span[1], 1, True)['unrecorded'],
            0.25
        )

    def test_shift_row_forward(self):
        initial_time = datetime(2013, 8, 27, 22, 0)
        length = timedelta(hours=8)
        shift_by = timedelta(hours=4)
        id_ = self.db.create_entry('sleep', initial_time, initial_time + length)
        self.db.shift_rows([id_,], shift_by)
        new_row = self.db.row(id_)
        assert new_row['start'] == initial_time + shift_by
        assert new_row['end'] == initial_time + length + shift_by
        assert new_row['duration'] == length.total_seconds()

    def test_shift_row_backward(self):
        initial_time = datetime(2013, 8, 27, 22, 0)
        length = timedelta(hours=8)
        shift_by = timedelta(hours=-4)
        id_ = self.db.create_entry('sleep', initial_time, initial_time + length)
        self.db.shift_rows([id_, ], shift_by)
        new_row = self.db.row(id_)
        assert new_row['start'] == initial_time + shift_by
        assert new_row['end'] == initial_time + length + shift_by
        assert new_row['duration'] == length.total_seconds()

    def test_unmerged_subcategories(self):
        """
        Regression test for a bug where sub-categories got swallowed merged
        with parent categories.
        """
        entry_a = ('org : clean', NOW, NOW + hours(1), None)
        entry_b = ('org', NOW + hours(1), NOW + hours(2), None)
        self.db.create_entry(*entry_a)
        self.db.create_entry(*entry_b)
        self.assertEqual(len(self.db.filter()), 2)

    def test_activity_normalize(self):
        """
        Activity text should be case insensitive and allow for an arbitrary
        number of spaces.
        """
        entry_a = ('  Org :   Clean', NOW, NOW + hours(1), None)
        entry_b = ('org : clean', NOW + hours(1), NOW + hours(2), None)
        self.db.create_entry(*entry_a)
        self.db.create_entry(*entry_b)
        self.assertEqual(len(self.db.filter()), 1)


class TestFilterPanel(unittest.TestCase):
    def setUp(self):
        self.panel = FilterPanel(None)

    def select_type(self, filter_type):
        i = self.panel.type_selector.findText(filter_type, Qt.MatchExactly)
        if i == -1:
            raise NameError(
                "'{0}' is not a valid mode for "
                "FilterPanel instance.".format(filter_type)
            )
        self.panel.type_selector.setCurrentIndex(i)

    def test_year(self):
        self.select_type("Year")
        year = 2013
        self.panel.year.setValue(year)
        activity, start, end = self.panel.current_filter
        self.assertEqual(
            start, datetime(year, 1, 1, 0, 0, 0)
        )
        self.assertEqual(
            end, datetime(year + 1, 1, 1, 0, 0, 0)
        )

    def test_month(self):
        self.select_type("Month")
        year = 2013
        m = self.panel.month.findText("January")
        self.panel.year.setValue(year)
        self.panel.month.setCurrentIndex(m)
        activity, start, end = self.panel.current_filter
        self.assertEqual(
            start, datetime(year, 1, 1, 0, 0, 0)
        )
        self.assertEqual(
            end, datetime(year, 2, 1, 0, 0, 0)
        )

    def test_week(self):
        self.select_type("Week")
        year = 2013
        self.panel.year.setValue(year)
        base_day = iso_to_gregorian(year, 1, 1)
        base = datetime(base_day.year, base_day.month, base_day.day, 0, 0)
        for w in range(52):
            start = base + (w * timedelta(days=7))
            end = base + ((w + 1) * timedelta(days=7))
            self.panel.week.setValue(w + 1)
            activity, check_start, check_end = self.panel.current_filter
            self.assertEqual(check_start, start)
            self.assertEqual(check_end, end)


if __name__ == '__main__':
    app = widgets.QApplication(sys.argv)
    unittest.main()
