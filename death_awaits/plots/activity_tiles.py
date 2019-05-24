import os
import datetime
import math
import re

import matplotlib
import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widgets

from death_awaits.plots.base import PlotDialogBase
from death_awaits.palettes import get_application_palette
from death_awaits.helper import stringify_date


class ActivityTilesBase(PlotDialogBase):
    nesting_types = (
        'Largest Inside', 'Smallest Inside',
        'Largest Inside, By Tile', 'Smallest Inside, By Tile',
    )
    def __init__(self, parent=None):
        super(ActivityTilesBase, self).__init__(parent)
        self._color_assignments = dict()

    def additional_widgets(self):
        self.nesting_type =  widgets.QComboBox(self)
        self.nesting_type.setEditable(False)
        self.nesting_type.addItems(self.nesting_types)
        self.nesting_type.setCurrentIndex(1)
        self.nesting_label = widgets.QLabel("Nesting:",self)
        self.nesting_label.setBuddy(self.nesting_type)
        self.shape = widgets.QComboBox(self)
        self.shape.setEditable(False)
        self.shape.addItems(('Circle','Square'))
        self.shape.setCurrentIndex(1)
        self.shape_label = widgets.QLabel('Tile Shape:', self)
        self.shape_label.setBuddy(self.shape)
        output = super(ActivityTilesBase,self).additional_widgets()
        output.extend([
            (self.nesting_label, self.nesting_type),
            (self.shape_label, self.shape),
        ])
        return output

    @staticmethod
    def proportion_to_radius(value, full_radius=0.5):
        return (
            math.sqrt((math.pi * full_radius ** 2) * value) / math.sqrt(math.pi)
        )

    def _plot_data(self, axes, database, activity, start, end):
        raise NotImplementedError()

    def _plot(self, figure, database, activity, start, end):
        self._color_assignments.clear()
        axes = figure.add_subplot('111')
        axes.axis('scaled')
        self._plot_data(axes, database, activity, start, end)
        axes.relim()
        axes.autoscale_view(scalex=True, scaley=False)
        #TODO: Create legend
        figure.tight_layout()
        #TODO: Remove this color text file later.
        with open(os.path.expanduser('~/Desktop/colors.txt'), 'w') as f_out:
            f_out.writelines([
                '{0} : {1}\n'.format(k,v)
                for k,v in self._color_assignments.items()
            ])

    def render_cell(self, x, y, activities, axes, palette):
        """
        Return a stacked list of patches, given the cell's
        coordinates, activities and colors.
        """
        inner_proportion = 0.0
        patches = list()
        for k, v in activities:
            if k in self._color_assignments:
                color = self._color_assignments[k]
            else:
                color = palette.get_color(k)
                self._color_assignments[k] = color
            if self.shape.currentText() == 'Circle':
                radius = self.proportion_to_radius(inner_proportion + v)
                patch = matplotlib.patches.Circle(
                    (x + 0.5, y + 0.5),
                    radius=radius,
                    facecolor=color,
                    edgecolor='none',
                    linewidth=0.0,
                )
            elif self.shape.currentText() == 'Square':
                radius = math.sqrt(inner_proportion + v) / 2.0
                patch = matplotlib.patches.Rectangle(
                    xy=(
                        x + (0.5 - radius),
                        y + (0.5 - radius)
                    ),
                    width=radius * 2,
                    height=radius * 2,
                    facecolor=color,
                    edgecolor='none',
                    linewidth=0.0,
                )
            patches.append(patch)
            inner_proportion += v
        patches.reverse()
        return patches

    def process_activity_cluster(
        self, chunk_activities, allowed_activities, activity
    ):
        activities = [
            (k, v) for k,v in chunk_activities.items()
            if k in allowed_activities
        ]
        reg = re.compile(activity,re.IGNORECASE)
        other_proportion = sum(
            v for k,v in chunk_activities.items()
            if k not in allowed_activities and (
                self.inclusive_other.isChecked()
                or reg.search(k)
            )
        )
        if self.nesting_type.currentIndex() in (0, 1):
            activities.sort(
                key=lambda i: allowed_activities.index(i[0]),
                reverse=self.nesting_type.currentIndex() == 1
            )
            # Include 'other' after sort.
            activities.append(('other', other_proportion))
        elif self.nesting_type.currentIndex() in (2, 3):
            # Include 'other' before sort.
            activities.append(('other', other_proportion))
            activities.sort(
                key=lambda i: i[1],
                reverse=self.nesting_type.currentIndex() == 3
            )
        else:
            raise ValueError('Unknown nesting type.')
        return activities

class ActivityTilesHourly(ActivityTilesBase):
    name = "Activity Tiles, Hourly"
    @staticmethod
    def format_day_hours(value, pos):
        hours = int(value)
        minutes = int((value - hours) * 60)
        time = core.QTime(hours, minutes)
        fmt_string = core.QLocale().timeFormat(core.QLocale.ShortFormat)
        return time.toString(fmt_string)

    @staticmethod
    def create_date_format_func(start):
        def date_format_func(value, pos):
            dt = start + datetime.timedelta(days=value)
            return stringify_date(dt)
        return date_format_func

    def _plot_data(self, axes, database, activity, start, end):
        palette = get_application_palette()
        xaxis = axes.get_xaxis()
        yaxis = axes.get_yaxis()
        yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(self.format_day_hours)
        )
        yaxis.set_major_locator(
            matplotlib.ticker.MaxNLocator(11, integer=True)
        )
        yaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(1))
        start, end = self.bracket(database, '', start, end)
        # start and end should fall on day divisions.
        start = datetime.datetime.fromordinal(start.date().toordinal())
        end = datetime.datetime.fromordinal(
            (end.date() + datetime.timedelta(days=1)).toordinal()
        )
        xaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(self.create_date_format_func(start))
        )
        level = self.level.value()
        ranked_activities = self.ranked_activities(
            database, activity, start, end
        )
        allowed_activities = [n[0] for n in ranked_activities]
        patches = list()
        for day_offset in range((end - start).days):
            for hour_offset in range(24):
                chunk_start = (start
                    + datetime.timedelta(days=day_offset)
                    + datetime.timedelta(hours=hour_offset)
                )
                chunk_activities = database.slice_activities(
                    start=chunk_start,
                    end=chunk_start + datetime.timedelta(hours=1),
                    level=level,
                    unrecorded=False,
                )
                activities = self.process_activity_cluster(
                    chunk_activities, allowed_activities, activity
                )
                patches.extend(self.render_cell(
                    day_offset, hour_offset, activities, axes, palette
                ))
        axes.axis((0, day_offset, 0, 24))
        if patches:
            axes.add_collection(
                matplotlib.collections.PatchCollection(patches, match_original=True)
            )


class ActivityTilesDaily(ActivityTilesBase):
    name = "Activity Tiles, Daily"
    @staticmethod
    def weekday_formatter(value, pos):
        l = core.QLocale()
        days = [l.dayName(n, core.QLocale.ShortFormat) for n in range(1,8)]
        while value < 0:
            value += 7
        while value > 7:
            value -= 7
        return days[int(value)]

    @staticmethod
    def create_week_format_func(start):
        def week_format_func(value, pos):
            current =  int(start + value)
            while current > 52:
                current -= 52
            return current
        return week_format_func

    def _plot_data(self, axes, database, activity, start, end):
        palette = get_application_palette()
        xaxis = axes.get_xaxis()
        yaxis = axes.get_yaxis()
        yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(self.weekday_formatter)
        )
        yaxis.set_major_locator(
            matplotlib.ticker.FixedLocator(
                [n + 0.5 for n in range(7)], 6
            )
        )
        start, end = self.bracket(database, '', start, end)
        # start and end should fall on day divisions.
        start = datetime.datetime.fromordinal(start.date().toordinal())
        end = datetime.datetime.fromordinal(
            (end.date() + datetime.timedelta(days=1)).toordinal()
        )
        start_year, start_week, start_weekday = start.date().isocalendar()
        end_year, end_week, end_weekday = end.date().isocalendar()
        number_of_weeks = (
            ((end_year * 52) + end_week) - ((start_year * 52) + start_week)
        )
        xaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(
                self.create_week_format_func(start_week)
            )
        )
        xaxis.set_major_locator(
            matplotlib.ticker.MaxNLocator(number_of_weeks, integer=True)
        )
        level = self.level.value()
        ranked_activities = self.ranked_activities(
            database, activity, start, end
        )
        allowed_activities = [n[0] for n in ranked_activities]
        day_offset = 0
        patches = list()
        while start + datetime.timedelta(days=day_offset) < end:
            chunk_start = start + datetime.timedelta(days = day_offset)
            chunk_activities = database.slice_activities(
                start=chunk_start,
                end=chunk_start + datetime.timedelta(days=1),
                level=level,
                unrecorded=False,
            )
            activities = self.process_activity_cluster(
                chunk_activities, allowed_activities, activity
            )
            current_year, current_week = chunk_start.date().isocalendar()[:2]
            week_offset = (
                ((current_year * 52) + current_week)
                - ((start_year * 52) + start_week)
            )
            patches.extend(self.render_cell(
                week_offset, chunk_start.weekday(), activities, axes, palette
            ))
            day_offset += 1
        axes.axis((0, week_offset + 1, 0, 7))
        axes.add_collection(
            matplotlib.collections.PatchCollection(patches, match_original=True)
        )



