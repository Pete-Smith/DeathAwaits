""" Helper Functions """
import sys
import datetime
import pdb
from enum import Enum

from pkg_resources import resource_filename
import PyQt6.QtGui as gui
import PyQt6.QtWidgets as widgets
import PyQt6.QtCore as core
import matplotlib as mpl
from dateutil.relativedelta import relativedelta, MO, SU, TU, WE, TH, FR, SA


class Weekday(Enum):
    monday = 0
    tuesday = 1
    wednesday = 2
    thursday = 3
    friday = 4
    saturday = 5
    sunday = 6


class SegmentSize(Enum):
    minute = 0
    hour = 1
    day = 2
    week = 3
    month = 4
    year = 5


class SortStrategy(Enum):
    largest_first = 0
    smallest_first = 1
    largest_first_by_segment = 2
    smallest_first_by_segment = 3


class OtherSort(Enum):
    hide_other = 0
    sort_as_activity = 1
    after_activities = 2


class UnrecordedSort(Enum):
    hide_unrecorded = 0
    sort_as_activity = 1
    after_activities = 2


def get_icon(name):
    return gui.QIcon(resource_filename("death_awaits", "icons/{0}".format(name)))


def get_application_icon():
    icon = get_icon("pixel_skull_512.png")
    return icon


def stringify_datetime(value, date=False):
    if isinstance(value, (datetime.datetime)):
        value = core.QDateTime(value)
    if not isinstance(value, core.QDateTime):
        raise TypeError("Expected a Qt or Python datetime object.")
    if date:
        fmt_string = core.QLocale().dateFormat(core.QLocale.FormatType.ShortFormat)
    else:
        fmt_string = core.QLocale().dateTimeFormat(core.QLocale.FormatType.ShortFormat)
    return value.toString(fmt_string)


def stringify_date(value):
    return stringify_datetime(value, True)


def em_dist(em):
    """
    Return the pixel distance of a given number of em's using the default font.
    """
    app = widgets.QApplication.instance() or widgets.QApplication(sys.argv)
    fm = gui.QFontMetrics(app.font())
    char_height = fm.height()
    return em * char_height


def configure_matplotlib():
    app = widgets.QApplication.instance() or widgets.QApplication(sys.argv)
    font = app.font()
    palette = app.palette()
    mpl.rcParams["backend"] = "QtAgg"
    mpl.rcParams["interactive"] = True
    mpl.rcParams["font.family"] = ", ".join(
        (
            font.family(),
            font.defaultFamily(),
        )
    )
    mpl.rcParams["font.size"] = font.pointSizeF()
    mpl.rcParams["figure.facecolor"] = palette.color(palette.ColorRole.Window).name()
    # TODO: app.desktop no longer accessible?
    # mpl.rcParams["figure.dpi"] = app.desktop().physicalDpiX()
    # TODO
    # mpl.rcParams['axes.facecolor'] = palette.color(palette.ColorRole.Base).name()
    mpl.rcParams["axes.facecolor"] = "#ffffff"
    foreground_colors = (
        "text.color",
        "axes.edgecolor",
        "figure.edgecolor",
        "xtick.color",
        "ytick.color",
    )
    for k in foreground_colors:
        mpl.rcParams[k] = palette.color(palette.ColorRole.WindowText).name()


def run_pdb():
    """Interrupts the Qt event loop and runs pdb.set_trace."""
    core.pyqtRemoveInputHook()
    try:
        pdb.set_trace()
    finally:
        core.pyqtRestoreInputHook()


def snap_to_segment(
    value: datetime.datetime, segment_size: SegmentSize, first_day_of_week: Weekday
):
    """Return a datetime value that is on the nearest segment boundary."""
    if segment_size >= SegmentSize.minute:
        if value.second > 30:
            value = value + datetime.timedelta(seconds=60 - value.second)
        else:
            value = value - datetime.timedelta(seconds=value.second)
    if segment_size >= SegmentSize.hour:
        if value.minute > 30:
            value = value + datetime.timedelta(minutes=60 - value.minute)
        else:
            value = value - datetime.timedelta(minutes=value.minute)
    if segment_size >= SegmentSize.day:
        if value.hour > 12:
            value = value + datetime.timedelta(hours=24 - value.hour)
        else:
            value = value - datetime.timedelta(hours=value.hour)
    if segment_size <= SegmentSize.week:
        if SegmentSize.month == segment_size:
            previous_boundary = value - datetime.timedelta(days=value.day)
            next_boundary = previous_boundary + relativedelta(months=+1)
        else:
            if first_day_of_week == value.weekday():
                return value
            weekday_func = None
            if first_day_of_week == Weekday.sunday:
                weekday_func = SU
            elif first_day_of_week == Weekday.monday:
                weekday_func = MO
            elif first_day_of_week == Weekday.tuesday:
                weekday_func = TU
            elif first_day_of_week == Weekday.wednesday:
                weekday_func = WE
            elif first_day_of_week == Weekday.thursday:
                weekday_func = TH
            elif first_day_of_week == Weekday.friday:
                weekday_func = FR
            elif first_day_of_week == Weekday.saturday:
                weekday_func = SA
            if weekday_func is not None:
                previous_boundary = value + relativedelta(weekday_func(-1))
                next_boundary = value + relativedelta(weekday_func(1))
            else:
                raise ValueError(f"Unknown weekday definition : {first_day_of_week}")
        seconds_to_previous = abs((value - previous_boundary).total_seconds())
        seconds_to_next = abs((next_boundary - value).total_seconds())
        if seconds_to_previous <= seconds_to_next:
            value = value - datetime.timedelta(seconds_to_previous)
        else:
            value = value + datetime.timedelta(seconds_to_next)
    return value
