import datetime
import csv
import os

import matplotlib as mpl
import PyQt5.QtWidgets as widgets

from death_awaits.db import LogDb
from death_awaits.palettes import get_application_palette
from death_awaits.plots.base import PlotDialogBase
from death_awaits.helper import stringify_date, run_pdb

class TimeSheet(PlotDialogBase):
    """

    """
    name = "Daily Time Sheet"
    def additional_widgets(self):
        self.verbose_times = widgets.QCheckBox('Show verbose times?', self)
        self.verbose_times.setChecked(True)
        output = super(TimeSheet, self).additional_widgets()
        output.extend([[self.verbose_times,],])
        return output

    def _plot(self, figure, database, activity, start, end):
        figure.set_tight_layout(False)
        start = datetime.datetime.fromordinal(start.date().toordinal())
        end = datetime.datetime.fromordinal(
            (end + datetime.timedelta(days=1)).date().toordinal()
        )
        level = self.level.value()
        if activity != 'unrecorded':
            start, end = self.bracket(database, '', start, end)
        activities = dict()
        day_labels = list()
        day_count = (end-start).days
        seconds_per_day = datetime.timedelta(days=1).total_seconds()
        day_totals = [0,] * day_count
        for day_offset in range(day_count):
            chunk_start = start + datetime.timedelta(days=day_offset)
            day_labels.append(stringify_date(chunk_start))
            chunk_activities = database.slice_activities(
                start=chunk_start,
                end=chunk_start + datetime.timedelta(days=1),
                level=level,
                unrecorded=False,
                activity=activity,
            )
            for k, v in chunk_activities.items():
                if k not in activities.keys():
                    activities[k] = [0,] * day_count
                activities[k][day_offset] = v * seconds_per_day
            day_totals[day_offset] = sum(
                [v[day_offset] for v in activities.values()]
            )
        activity_totals = dict(
            [(k, sum(v)) for k,v in activities.items()]
        )
        activity_labels = sorted(
            list(activity_totals.keys()),
            key=lambda k: activity_totals[k],
            reverse=True
        )
        #run_pdb()
        axes = figure.add_subplot('111')
        celltext = list()
        for k in activity_labels:
            if self.verbose_times.isChecked():
                celltext.append(
                    [LogDb.format_duration(v) for v in activities[k]]
                    + [LogDb.format_duration(activity_totals[k]),]
                )
            else:
                data = activities[k] + [activity_totals[k]]
                data = [int(round(n/60.0)) for n in data]
                celltext.append(data)
        if self.verbose_times.isChecked():
            celltext.append(
                [LogDb.format_duration(v) for v in day_totals]
                + [LogDb.format_duration(sum(day_totals))]
            )
        else:
            data = day_totals + [sum(day_totals),]
            data = [int(round(n/60.0)) for n in data]
            celltext.append(data)
        with open(os.path.expanduser('~/Desktop/debug.csv'), 'w', newline='') as fout:
            writer = csv.writer(fout)
            writer.writerow(['',] + day_labels + ['TOTALS',])
            for i, row in enumerate(celltext):
                if i < len(activity_labels):
                    writer.writerow([activity_labels[i],] + row)
                else:
                    writer.writerow([''] + row)
            #writer.writerows(celltext)
        bg_color = mpl.rcParams['axes.facecolor']
        axes.table(
            cellText=celltext,
            rowLabels=activity_labels + ['TOTALS',],
            colLabels= day_labels + ['TOTALS',],
            cellColours=[[bg_color,] * (day_count + 1)] * len(celltext),
            rowColours=[bg_color,] * (len(activity_labels) + 1),
            colColours=[bg_color,] * (len(day_labels) + 1),
            loc='center'
        )
