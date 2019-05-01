import matplotlib as mpl

from . import activity_stack, pie_chart, activity_tiles, timesheet

mpl.rcParams['figure.autolayout'] = False

PLOTTERS = (
    activity_stack.ActivityStack,
    activity_stack.ActivityStackDay,
    activity_stack.ActivityStackWeek,
    activity_tiles.ActivityTilesDaily,
    activity_tiles.ActivityTilesHourly,
    pie_chart.PieChart,
    timesheet.TimeSheet,
)
