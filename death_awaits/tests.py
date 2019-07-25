from datetime import datetime, timedelta

import pytest

from death_awaits.db import LogDb

NOW = datetime.now()


def minutes(n):
    return timedelta(seconds=n*60)


def hours(n):
    return minutes(n*60)


@pytest.fixture
def test_database():
    return LogDb(":memory:", bounds=60, units='minutes')


@pytest.fixture
def test_data():
    columns = ('activity', 'start', 'end', 'quantity')
    entries = (
        # (activity, start, end, quantity)
        ('sleep', NOW, NOW + hours(8), None),
        ('eat', NOW + hours(7), None, hours(1)),
        ('eat', NOW + hours(7.5), None, hours(1)),
    )
    return [dict(zip(columns, e)) for e in entries]


def test_insertion_start_end(test_database, test_data):
    entry = test_data[0]
    entry.update({'end': entry['start']+hours(8), 'quantity': None})
    id_ = test_database.create_entry(**entry)
    row = test_database.row(id_)
    assert row['activity'] == entry['activity']
    assert row['start'] == entry['start']
    assert row['end'] == entry['end']
    assert (
        row['quantity'] == (entry['end']-entry['start']).total_seconds() / 60
    )


def test_insertion_start_duration(test_database, test_data):
    entry = test_data[0]
    entry.update({'end': None, 'quantity': hours(8)})
    id_ = test_database.create_entry(**entry)
    row = test_database.row(id_)
    assert row['activity'] == entry['activity']
    assert row['start'] == entry['start']
    assert row['end'] == entry['start'] + entry['quantity']
    assert row['quantity'] == entry['quantity'].seconds / 60


def test_simple_overlap(test_database, test_data):
    entry_a = test_data[0]
    entry_b = test_data[1]
    id_a = test_database.create_entry(**entry_a)
    row_a = test_database.row(id_a)
    id_b = test_database.create_entry(**entry_b)
    row_a = test_database.row(id_a)
    row_b = test_database.row(id_b)
    assert row_a['quantity'] == 7 * 60
    assert row_b['quantity'] / 60 == 1
    assert row_a['start'] + timedelta(hours=7) == row_b['start']
    assert (
        row_b['start'] + timedelta(seconds=row_b['quantity'] * 60)
        == row_b['end']
    )
    assert row_b['start'] == row_a['end']
    assert row_b['end'] > row_a['end']
    assert (
        row_a['quantity'] + row_b['quantity'] ==
        (row_b['end'] - row_a['start']).total_seconds() / 60
    )


def test_simple_combine(test_database, test_data):
    entry_a = test_data[1]
    entry_b = test_data[2]
    test_database.create_entry(**entry_a)
    id_b = test_database.create_entry(**entry_b)
    row_b = test_database.row(id_b)
    assert entry_a['start'] == row_b['start']
    assert entry_b['start'] + entry_b['quantity'] == row_b['end']


def test_overwrite(test_database, test_data):
    id_a = test_database.create_entry(**test_data[1])
    entry_a = dict(test_database.row(id_a))
    entry_a['quantity'] = entry_a['quantity'] / 2.0
    id_b = test_database.create_entry(**entry_a)
    entry_b = test_database.row(id_b)
    assert id_a == id_b
    assert entry_a['quantity'] == pytest.approx(entry_b['quantity'])


def test_simple_slice_contrib(test_database, test_data):
    id_ = test_database.create_entry(**test_data[0])
    entry = test_database.row(id_)
    end = entry['start'] + timedelta(minutes=entry['quantity']/2.0)
    contrib = test_database.slice_contrib(entry, entry['start'],end)
    assert entry['quantity']/2.0 == pytest.approx(contrib)


def test_slice_contrib_row_within_span(test_database, test_data):
    id_ = test_database.create_entry(**test_data[0])
    entry = test_database.row(id_)
    start = entry['start'] - timedelta(seconds=entry['quantity']/4.0)
    end = entry['end'] + timedelta(seconds=entry['quantity']/4.0)
    contrib = test_database.slice_contrib(entry, start, end)
    assert entry['quantity'] == pytest.approx(contrib)


def test_slice_contrib_span_within_row(test_database, test_data):
    id_ = test_database.create_entry(**test_data[0])
    entry = test_database.row(id_)
    start = entry['start'] + timedelta(minutes=entry['quantity']/4.0)
    end = entry['end'] - timedelta(minutes=entry['quantity']/4.0)
    contrib = test_database.slice_contrib(entry, start, end)
    assert entry['quantity']/2.0 == pytest.approx(contrib)


def test_slice_contrib_span_outside_row(test_database, test_data):
    id_ = test_database.create_entry(**test_data[0])
    entry = test_database.row(id_)
    start = entry['start'] - timedelta(minutes=entry['quantity'] * 2)
    end = entry['end'] - timedelta(minutes=entry['quantity'] * 1.5)
    contrib = test_database.slice_contrib(entry, start, end)
    assert 0 == pytest.approx(contrib)


def test_simple_slice_activities(test_database, test_data):
    id_ = test_database.create_entry(**test_data[0])
    entry = test_database.row(id_)
    activities = test_database.slice_activities(
        start=entry['start'],
        end=(
            entry['start']
            + timedelta(minutes=entry['quantity'] * 2.0)
        ),
        level=1,
        unrecorded=True
    )
    assert activities['unrecorded'] == 0.5
    assert activities[entry['activity']] == 0.5


def test_simple_span_slices(test_database, test_data):
    id_ = test_database.create_entry(**test_data[0])
    entry = test_database.row(id_)
    chunks, activities = test_database.span_slices(
        start=entry['start'],
        span=entry['quantity'] * 2.0,
        chunk_size=entry['quantity'] * 2.0,
        level=0,
        unrecorded=True,
    )
    assert activities['unrecorded'][0] == pytest.approx(0.5)
    assert len(chunks) == 1
    assert chunks[0] == entry['start'] + timedelta(minutes=entry['quantity'])


def test_entry_trimming_with_truncate(test_database, test_data):
    test_database.create_entry(
        'sleep', datetime(2013, 8, 28, 0, 41), datetime(2013, 8, 28, 6, 0)
    )
    test_database.create_entry(
        'bathroom',
        datetime(2013, 8, 28, 6, 28),
        datetime(2013, 8, 28, 7, 11)
    )
    test_database.create_entry(
        'sleep', datetime(2013, 8, 28, 0, 33), datetime(2013, 8, 28, 6, 41)
    )
    assert (
        sum(test_database.slice_activities(
            datetime(2013, 8, 28, 6, 30),
            datetime(2013, 8, 28, 6, 45),
            unrecorded=False,
        ).values()
        ) == pytest.approx(1.0)
    )


def test_entry_trimming_with_split(test_database, test_data):
    test_database.create_entry(
        'sleep', datetime(2013, 8, 28, 1, 0), datetime(2013, 8, 28, 4, 0)
    )
    test_database.create_entry(
        'bathroom', datetime(2013, 8, 28, 1, 30), datetime(2013, 8, 28, 2, 0)
    )
    assert len(test_database.filter()) == 3
    assert (
        sum(test_database.slice_activities(
            datetime(2013, 8, 28, 1, 0),
            datetime(2013, 8, 28, 4, 0),
            unrecorded=False,
        ).values()
        ) == pytest.approx(1.0)
    )


def test_simple_undo_redo(test_database, test_data):
    test_database.create_entry(
        'sleep', datetime(2013, 8, 28, 1, 0), datetime(2013, 8, 28, 4, 0)
    )
    test_database.save_changes()
    assert len(test_database.filter()) == 1
    assert test_database.undo_possible() is True
    test_database.undo()
    assert len(test_database.filter()) == 0
    assert test_database.undo_possible() is False
    test_database.redo()
    assert len(test_database.filter()) == 1
    assert test_database.undo_possible() is True


def test_compound_undo_redo(test_database, test_data):
    # Create two entries, then create an entry that overwrites.
    test_database.create_entry(
        'sleep', datetime(2013, 8, 28, 1, 0), datetime(2013, 8, 28, 4, 0)
    )
    test_database.create_entry(
        'bathroom', datetime(2013, 8, 28, 4, 0), datetime(2013, 8, 28, 5, 0)
    )
    test_database.save_changes()
    assert len(test_database.filter()) == 2
    test_database.create_entry(
        'sleep', datetime(2013, 8, 28, 1, 0), datetime(2013, 8, 28, 6, 0)
    )
    test_database.save_changes()
    assert len(test_database.filter()) == 1
    test_database.undo()
    assert len(test_database.filter()) == 2
    test_database.redo()
    assert len(test_database.filter()) == 1


def test_first_last(test_database, test_data):
    test_database.create_entry(
        'sleep', datetime(2013, 8, 27, 22, 0), datetime(2013, 8, 28, 6, 0)
    )
    test_database.create_entry(
        'bathroom', datetime(2013, 8, 28, 6, 0), datetime(2013, 8, 28, 7, 0)
    )
    test_database.create_entry(
        'commute', datetime(2013, 8, 28, 8, 0), datetime(2013, 8, 28, 9, 0)
    )
    test_database.create_entry(
        'work', datetime(2013, 8, 28, 9, 0), datetime(2013, 8, 28, 17, 0)
    )
    assert test_database.filter(first=True)['activity'] == 'sleep'
    assert test_database.filter(last=True)['activity'] == 'work'


def test_fill_unrecorded_first(test_database, test_data):
    """
    When adding an activity to a span, we want to use up the unrecorded
    time before decreasing the other activities.
    """
    quantity = 15
    span = (NOW, NOW + timedelta(minutes=quantity * 4))
    id_a = test_database.create_entry('activity a', span[0], span[1], quantity)
    id_b = test_database.create_entry('activity b', span[0], span[1], quantity)
    id_c = test_database.create_entry('activity c', span[0], span[1], quantity)
    row_a = test_database.row(id_a)
    row_b = test_database.row(id_b)
    row_c = test_database.row(id_c)
    assert row_a['quantity'] == pytest.approx(quantity)
    assert row_b['quantity'] == pytest.approx(quantity)
    assert row_c['quantity'] == pytest.approx(quantity)
    assert (
        test_database.slice_activities(span[0], span[1], 1, True)['unrecorded']
        == pytest.approx(0.25)
    )


def test_shift_row_forward(test_database, test_data):
    initial_time = datetime(2013, 8, 27, 22, 0)
    length = timedelta(hours=8)
    shift_by = timedelta(hours=4)
    id_ = test_database.create_entry('sleep', initial_time, initial_time + length)
    test_database.shift_rows([id_,], shift_by)
    new_row = test_database.row(id_)
    assert new_row['start'] == initial_time + shift_by
    assert new_row['end'] == initial_time + length + shift_by
    assert new_row['quantity'] == length.total_seconds() / 60


def test_shift_row_backward(test_database, test_data):
    initial_time = datetime(2013, 8, 27, 22, 0)
    length = timedelta(hours=8)
    shift_by = timedelta(hours=-4)
    id_ = test_database.create_entry('sleep', initial_time, initial_time + length)
    test_database.shift_rows([id_, ], shift_by)
    new_row = test_database.row(id_)
    assert new_row['start'] == initial_time + shift_by
    assert new_row['end'] == initial_time + length + shift_by
    assert new_row['quantity'] == length.total_seconds() / 60


def test_unmerged_subcategories(test_database, test_data):
    """
    Regression test for a bug where sub-categories got swallowed merged
    with parent categories.
    """
    entry_a = ('org : clean', NOW, NOW + hours(1), None)
    entry_b = ('org', NOW + hours(1), NOW + hours(2), None)
    test_database.create_entry(*entry_a)
    test_database.create_entry(*entry_b)
    assert len(test_database.filter()) == 2


def test_activity_normalize(test_database, test_data):
    """
    Activity text should be case insensitive and allow for an arbitrary
    number of spaces.
    """
    entry_a = ('  Org :   Clean', NOW, NOW + hours(1), None)
    entry_b = ('org : clean', NOW + hours(1), NOW + hours(2), None)
    test_database.create_entry(*entry_a)
    test_database.create_entry(*entry_b)
    assert len(test_database.filter()) == 1
