import re

import PyQt6.QtGui as gui
import PyQt6.QtWidgets as widgets

from death_awaits.palettes import get_application_palette
from death_awaits.plots.base import PlotDialogBase
from death_awaits.helper import stringify_date


class PieChart(PlotDialogBase):
    """
    A simple pie chart showing the proportion of time spent on each activity.
    """
    name = "Pie Chart"
    totals_options = (
        ('', ''),
        ('Hours-per-day', 'day'),
        ('Hours-per-week', 'week'),
        ('Total Hours', 'total'),
    )

    def additional_widgets(self):
        self.show_percentages = widgets.QCheckBox("Show Percentages?", self)
        self.show_percentages.setChecked(True)
        self.totals_box = widgets.QComboBox(self)
        totals_label = widgets.QLabel('Totals:', self)
        totals_label.setBuddy(self.totals_box)
        for label, data in self.totals_options:
            self.totals_box.addItem(label, data)
        self.totals_box.setCurrentIndex(2)
        output = super(PieChart, self).additional_widgets()
        output.extend([
            (totals_label, self.totals_box),
            (self.show_percentages, ),
        ])
        return output

    def _plot(self, figure, database, activity, start, end):

        def pct_format(val):
            if self.show_percentages.isChecked() and val > 8:
                return "{0:.1f}%".format(val)
            return ''

        axes = figure.add_subplot(111)
        axes.set_aspect('equal')
        if activity != 'unrecorded':
            start, end = self.bracket(database, '', start, end)
        items_shown = self.ranked_activities(database, activity, start, end)
        palette = get_application_palette()
        colors = [palette.get_color(k) for k, v in items_shown]
        labels = [n[0] for n in items_shown]
        totals_option = self.totals_box.itemData(
            self.totals_box.currentIndex())
        if totals_option:
            for i in range(len(labels)):
                if totals_option == 'week':
                    labels[i] += " ({0:.1f} hrs/wk)".format(items_shown[i][1] *
                                                            7 * 24)
                elif totals_option == 'day':
                    labels[i] += " ({0:.1f} hrs/day)".format(
                        items_shown[i][1] * 24)
                elif totals_option == 'total':
                    labels[i] += " ({0:.1f} hrs)".format(
                        items_shown[i][1] *
                        ((end - start).total_seconds() / 60.0 / 60.0))
        sizes = [n[1] for n in items_shown]
        if (activity and not self.inclusive_other.isChecked()
                and sum(sizes) != 0.0):
            multiplier = abs(1.0 / float(sum(sizes)))
            sizes = [n * multiplier for n in sizes]
        axes.set_title("Time Spent Between {0} and {1}".format(
            stringify_date(start),
            stringify_date(end),
        ))
        axes.pie(sizes, labels=labels, colors=colors, autopct=pct_format)
