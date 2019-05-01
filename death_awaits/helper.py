""" Helper Functions """
import sys
import datetime
import pdb

from pkg_resources import resource_filename
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widgets
import PyQt5.QtCore as core
import matplotlib as mpl


def iso_year_start(iso_year):
    """
    The gregorian calendar date of the first day of the given ISO year

    http://stackoverflow.com/questions/304256/whats-the-best-way-to-find-the-inverse-of-datetime-isocalendar
    """
    fourth_jan = datetime.date(iso_year, 1, 4)
    delta = datetime.timedelta(fourth_jan.isoweekday()-1)
    return fourth_jan - delta


def iso_to_gregorian(iso_year, iso_week, iso_day):
    """
    Gregorian calendar date for the given ISO year, week and day

    http://stackoverflow.com/questions/304256/whats-the-best-way-to-find-the-inverse-of-datetime-isocalendar
    """
    year_start = iso_year_start(iso_year)
    return year_start + datetime.timedelta(days=iso_day-1, weeks=iso_week-1)


def get_icon(name):
    return gui.QIcon(
        resource_filename('death_awaits', 'icons/{0}'.format(name))
    )


def get_application_icon():
    icon = get_icon('pixel_skull_512.png')
    return icon


def stringify_datetime(value, date=False):
    if isinstance(value, (datetime.datetime)):
        value = core.QDateTime(value)
    if not isinstance(value, core.QDateTime):
        raise TypeError('Expected a Qt or Python datetime object.')
    if date:
        fmt_string = core.QLocale().dateFormat(core.QLocale.ShortFormat)
    else:
        fmt_string = core.QLocale().dateTimeFormat(core.QLocale.ShortFormat)
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
    mpl.rcParams['backend'] = 'Qt4Agg'
    mpl.rcParams['interactive'] = True
    mpl.rcParams['font.family'] = ", ".join((
        font.family(), font.defaultFamily(),
    ))
    mpl.rcParams['font.size'] = font.pointSizeF()
    mpl.rcParams['figure.facecolor'] = palette.color(palette.Window).name()
    mpl.rcParams['figure.dpi'] = app.desktop().physicalDpiX()
    #TODO
    #mpl.rcParams['axes.facecolor'] = palette.color(palette.Base).name()
    mpl.rcParams['axes.facecolor'] = '#ffffff'
    foreground_colors = (
        'text.color','axes.edgecolor', 'figure.edgecolor', 'xtick.color',
        'ytick.color'
    )
    for k in foreground_colors:
        mpl.rcParams[k] = palette.color(palette.WindowText).name()


def run_pdb():
    """ Interrupts the Qt event loop and runs pdb.set_trace.  """
    core.pyqtRemoveInputHook()
    try:
        pdb.set_trace()
    finally:
        core.pyqtRestoreInputHook()
