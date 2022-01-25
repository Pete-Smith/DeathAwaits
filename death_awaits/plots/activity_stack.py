import datetime
import re

import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widgets
import matplotlib as mpl
from matplotlib.patches import Rectangle

from death_awaits.db import LogDb
from death_awaits.palettes import get_application_palette
from death_awaits.widgets import WeekdaySelector
from death_awaits.plots.base import PlotDialogBase
from death_awaits.helper import stringify_date


def activitystack_onpick(event):
    """
    Display the gid of the item under the cursor as a tooltip.
    """
    gid = event.artist.get_gid()
    axes = event.mouseevent.inaxes
    print(repr(gid))
    if axes:
        axes.text(
            event.mouseevent.xdata, event.mouseevent.ydata, gid,
            size='small', multialignment='center', gid="pick_label",
        )
    event.canvas.draw()

def activitystack_onmove(event):
    x = event.x
    axes = event.inaxes
    if axes:
        for a in axes.artists:
            if a.clipbox.xmin < x < a.clipbox.xmax:
                axes.text(
                    a.clipbox.minx + ((a.clipbox.maxx - a.clipbox.minx) / 2.0),
                    a.clipbox.miny + ((a.clipbox.maxy - a.clipbox.miny) / 2.0),
                    a.gid,
                    size='small', multialignment='center', gid="pick_label",
                )
    else:
        print('No axes.')


class ActivityStack(PlotDialogBase):
    name = "Activity Stack, Continuous"
    unrecorded = False
    def additional_widgets(self):
        self.sample_field = widgets.QLineEdit(self)
        self.sample_field.setText("1d")
        sample_label = widgets.QLabel("Sample Size:",self)
        sample_label.setBuddy(self.sample_field)
        self.reverse_sort = widgets.QCheckBox("Reverse Sort?", self)
        self.sample_field.editingFinished.connect(self._sample_edited)
        self.show_legend = widgets.QCheckBox("Show legend?",self)
        self.show_legend.setChecked(False)
        self.day_boundary_lines = widgets.QCheckBox(
            "Day boundary lines.", self
        )
        output = super(ActivityStack,self).additional_widgets()
        output.extend([
            (sample_label, self.sample_field),
            (self.show_legend,),
            (self.reverse_sort,),
            (self.day_boundary_lines,),
        ])
        return output

    def sample(self):
        return LogDb.parse_duration(self.sample_field.text())

    @staticmethod
    def _sort_first(data,reverse=False):
        def find_first_item(values):
            for i in enumerate(values[1]):
                if i != 0.0:
                    return i
            else:
                return len(values)
        return sorted(data, key=find_first_item, reverse=reverse)

    @staticmethod
    def _sort_largest(data,reverse=False):
        def values_sum(values):
            return sum(values[1])
        return sorted(data, key=values_sum, reverse=reverse)

    def _sample_edited(self):
        new = LogDb.parse_duration(self.sample_field.text())
        self.sample_field.setText(LogDb.format_duration(new))

    def _plot(self, figure, database, activity, start, end):
        axes = figure.add_subplot(111)
        start, end = self.bracket(database, '', start, end)
        chunk_size = LogDb.parse_duration(self.sample_field.text())
        level = self.level.value()
        ranked_activities = self.ranked_activities(
            database, activity, start, end
        )
        allowed_activities = [n[0] for n in ranked_activities]
        midpoints, activities = database.span_slices(
            start=start,
            span=end - start,
            chunk_size=chunk_size,
            level=level,
            unrecorded= False,
        )
        # Mutate chunk_size so it's understandable by matplotlib
        chunk_size =  chunk_size / datetime.timedelta(days=1).total_seconds()
        self._graph_data(
            activities, figure, axes, allowed_activities, midpoints,
            chunk_size, activity
        )
        axes.xaxis.set_ticks(
            [datetime.datetime(start.year,start.month,start.day,0,0,0)
             + datetime.timedelta(days=n) for n in range(
                 int(round((end - start) / datetime.timedelta(days=1)))
             )
            ], minor=True
        )
        axes.grid(self.day_boundary_lines.isChecked(),'minor','x')
        figure.autofmt_xdate()

    def _graph_data(
        self, activities, figure, axes, allowed_activities, midpoints,
        chunk_size, activity
    ):
        """
        Draw data on axes using the activity data handed in.
        This is does the data processing and drawing that is common to the
        different activity pattern classes.
        """
        reg = re.compile(activity,re.IGNORECASE)
        other = None
        new_activities = list()
        #figure.canvas.mpl_connect('pick_event', activitystack_onpick)
        figure.canvas.mpl_connect('motion_notify_event', activitystack_onmove)
        for name, values in activities.items():
            if (name in allowed_activities
                and name.strip().lower() != 'other'):
                new_activities.append((name,values))
            elif self.inclusive_other.isChecked() or reg.search(name):
                if other:
                    for i,v in enumerate(values):
                        other[i] += v
                else:
                    other = values
        if other:
            new_activities.append(('other',other))
        new_activities = self._sort_largest(
            new_activities, reverse = self.reverse_sort.isChecked()
        )
        palette = get_application_palette()
        colors = [palette.get_color(k) for k,v in new_activities]
        axes.set_ylim((0,1))
        base_values = [0,] * len(midpoints)
        for i, label in enumerate(new_activities):
            kwparams = {
                'left' : midpoints,
                'height' : label[1],
                'width' : chunk_size,
                'bottom' : base_values,
                'color' : colors[i],
                'linewidth' : 0,
                'align' : 'center',
                'gid' : label[0],
                'picker' : True,
            }
            axes.bar(**kwparams)
            base_values = [
                sum((a,b)) for a,b in zip(base_values, label[1])
            ]
        self._draw_legend(new_activities, figure, axes, colors)

    def _draw_legend(self, new_activities, figure, axes, colors):
        if self.show_legend.isChecked():
            figure.subplots_adjust(
                left=mpl.rcParams['figure.subplot.left'],
                right=mpl.rcParams['figure.subplot.right'],
                bottom=mpl.rcParams['figure.subplot.bottom'],
                top=mpl.rcParams['figure.subplot.top'],
                wspace=mpl.rcParams['figure.subplot.wspace'],
                hspace=mpl.rcParams['figure.subplot.hspace'],
            )
            box = axes.get_position()
            axes.set_position([box.x0, box.y0, box.width * 0.8, box.height])
            axes.legend(
                [Rectangle((0,0),1,1,fc=color) for color in colors],
                [n[0] for n in new_activities],
                bbox_to_anchor=(1.0, 0.5),
                loc='center left',
            )
        else:
            figure.tight_layout()


class ActivityStackDay(ActivityStack):
    name = "Activity Stack, Time of Day"
    weekly = False
    def __init__(self, parent=None):
        super(ActivityStackDay, self).__init__(parent)
        self.sample_field.setText("30m")

    def additional_widgets(self):
        output = super(ActivityStackDay,self).additional_widgets()
        #if not self.weekly:
        self.weekday_selector = WeekdaySelector(parent=self)
        weekday_label = widgets.QLabel("Weekdays:",self)
        weekday_label.setBuddy(self.weekday_selector)
        output.insert(0,[weekday_label, self.weekday_selector])
        return output

    def _plot(self, figure, database, activity, start, end):
        weekly = self.weekly
        weekdays = None
        if hasattr(self,'weekday_selector'):
            weekdays = self.weekday_selector.selection()
        axes = figure.add_subplot(111, xmargin=0, ymargin=0)
        start, end = self.bracket(database, '', start, end)
        chunk_size = LogDb.parse_duration(self.sample_field.text())
        level = self.level.value()
        ranked_activities = self.ranked_activities(
             database, activity, start, end
        )
        allowed_activities = [n[0] for n in ranked_activities]
        midpoints, activities = database.stacked_slices(
            start=start,
            span=end - start,
            chunk_size=chunk_size,
            level=level,
            unrecorded= False,
            weekdays=weekdays,
            weekly=weekly,
        )
        self._graph_data(
            activities, figure, axes, allowed_activities, midpoints,
            chunk_size, activity
        )
        if weekly:
            axes.set_xlim((0, datetime.timedelta(days=7).total_seconds()))
            axes.xaxis.set_label_text("Weekdays")
            axes.xaxis.set_ticks((
                0,
                datetime.timedelta(days=1).total_seconds(),
                datetime.timedelta(days=2).total_seconds(),
                datetime.timedelta(days=3).total_seconds(),
                datetime.timedelta(days=4).total_seconds(),
                datetime.timedelta(days=5).total_seconds(),
                datetime.timedelta(days=6).total_seconds(),
                datetime.timedelta(days=7).total_seconds(),
            ))
            axes.xaxis.set_ticklabels(
                [core.QDate.shortDayName(n) for n in range(1,8)]
                #('Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')
            )
            axes.grid(self.day_boundary_lines.isChecked(),'major','x')
        else:
            axes.set_xlim((0, datetime.timedelta(days=1).total_seconds()))
            axes.xaxis.set_label_text("Time of day")
            axes.xaxis.set_ticks(
                [
                datetime.timedelta(hours=h).total_seconds()
                for h in range(0, 30, 6)
            ]
            )
            axes.xaxis.set_ticks(
                [
                datetime.timedelta(hours=h).total_seconds()
                    for h in range(25)
                ],
                minor=True
            )
            axes.xaxis.set_ticklabels(
                ('Midnight', '6am', 'Noon', '6pm', 'Midnight')
            )
            axes.grid(True,'minor','x')
        axes.yaxis.set_ticklabels(list())
        date_fmt_string = core.QLocale().dateFormat()
        title = (
            "{0} Activities Between {1} and {2}".format(
                "Weekly" if weekly else "Daily",
                stringify_date(start), stringify_date(end)
            )
        )
        if hasattr(self,'weekday_selector'):
            if len(self.weekday_selector.selection()) < 7:
                title += "\n("+str(self.weekday_selector)+")"
        axes.set_title(title)


class ActivityStackWeek(ActivityStackDay):
    name = "Activity Stack, Day of Week"
    weekly = True
    def __init__(self, parent=None):
        super(ActivityStackWeek, self).__init__(parent)
        self.sample_field.setText("1d")
