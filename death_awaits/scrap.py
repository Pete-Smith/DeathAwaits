import datetime
import calendar

import PyQt5.QtGui as gui
import PyQt5.QtCore as core
import PyQt5.QtWidgets as widgets

from .helper import iso_to_gregorian



class WeekRangeSelector(RangeSelectorBase):
    def __init__(self,show_sample=True,parent=None):
        super(WeekRangeSelector,self).__init__(show_sample, parent)
        now = datetime.datetime.now()
        # Widgets
        week_label = widgets.QLabel('Week:')
        year_label = widgets.QLabel('Year:')
        start_panel = widgets.QGroupBox("Start:", self)
        end_panel = widgets.QGroupBox("End:", self)
        self.start_label = widgets.QLabel()
        self.end_label = widgets.QLabel()
        # Start Panel : Year
        self.start_year = widgets.QSpinBox(self)
        self.start_year.setMaximum(datetime.MINYEAR)
        self.start_year.setMaximum(datetime.MAXYEAR)
        self.start_year.setValue(now.year)
        # Start Panel : Month
        self.start_week = widgets.QSpinBox(self)
        self.start_week.setMinimum(1)
        self.start_week.setMaximum(52)
        self.start_week.setValue(
            (now + datetime.timedelta(days=30)).isocalendar()[1]
        )
        # End Panel : Year
        self.end_year = widgets.QSpinBox(self)
        self.end_year.setMaximum(datetime.MINYEAR)
        self.end_year.setMaximum(datetime.MAXYEAR)
        self.end_year.setValue(now.year)
        # End Panel : Month
        self.end_week = widgets.QSpinBox(self)
        self.end_week.setMinimum(1)
        self.end_week.setMaximum(52)
        self.end_week.setValue(now.isocalendar()[1])
        self.week_label = widgets.QLabel('Week:')
        # Layout
        main = widgets.QHBoxLayout()
        start_layout = widgets.QGridLayout()
        start_layout.addWidget(year_label,0,0)
        start_layout.addWidget(self.start_year,0,1)
        start_layout.addWidget(week_label,1,0)
        start_layout.addWidget(self.start_week,1,1)
        start_layout.addWidget(self.start_label,2,0,1,2)
        start_panel.setLayout(start_layout)
        main.addWidget(start_panel)
        end_layout = widgets.QGridLayout()
        end_layout.addWidget(year_label,0,0)
        end_layout.addWidget(self.end_year,0,1)
        end_layout.addWidget(week_label,1,0)
        end_layout.addWidget(self.end_week,1,1)
        start_layout.addWidget(self.end_label,2,0,1,2)
        end_panel.setLayout(end_layout)
        main.addWidget(end_panel)
        self.setLayout(main)
        # Connection
        self.start_year.valueChanged.connect(self._range_changed)
        self.start_week.valueChanged.connect(self._range_changed)
        self.end_year.valueChanged.connect(self._range_changed)
        self.end_week.valueChanged.connect(self._range_changed)
        # Set-up
        self._update_labels()

    def _update_labels(self):
        start = iso_to_gregorian(self.start_year.value(),self.start_week.value(),1)
        end = iso_to_gregorian(self.end_year.value(),self.end_week.value(),1)
        self.start_label.setText(
            "{0} to {1}".format(
                start.strftime("%B %d, %Y"),
                (start + datetime.timedelta(days=6)).strftime("%B %d, %Y")
            )
        )
        self.end_label.setText(
            "{0} to {1}".format(
                end.strftime("%B %d, %Y"),
                (end + datetime.timedelta(days=6)).strftime("%B %d, %Y")
            )
        )

    def _range_changed(self):
        start = iso_to_gregorian(self.start_year.value(),self.start_week.value(),1)
        end = iso_to_gregorian(self.end_year.value(),self.end_week.value(),1)
        if end < start:
            year, week = (start + datetime.timedelta(days=-7)).isocalendar()[:2]
            self.start_year.setValue(year)
            self.start_week.setValue(week)
        if start > end:
            year, week = (end + datetime.timedelta(days=7)).isocalendar()[:2]
            self.end_year.setValue(year)
            self.end_week.setValue(week)
        self._update_labels()

    def range(self):
        """
        Return a triple: start datetime, end datetime, and sample timedelta.
        """
        start = iso_to_gregorian(self.start_year.value(),self.start_week.value(),1)
        end = iso_to_gregorian(self.end_year.value(),self.end_week.value(),1)
        return start, end, self.sample()


class MonthRangeSelector(widgets.QWidget):
    def __init__(self, show_sample=True, parent=None):
        super(MonthRangeSelector,self).__init__(show_sample, parent)
        now = datetime.datetime.now()
        # Widgets
        month_label = widgets.QLabel('Month:')
        year_label = widgets.QLabel('Year:')
        start_panel = widgets.QGroupBox("Start:", self)
        end_panel = widgets.QGroupBox("End:", self)
        # Start Panel : Year
        self.start_year = widgets.QSpinBox(self)
        self.start_year.setMaximum(datetime.MINYEAR)
        self.start_year.setMaximum(datetime.MAXYEAR)
        self.start_year.setValue(now.year)
        # Start Panel : Month
        self.start_month = widgets.QComboBox(self)
        self.start_month.addItems(list(calendar.month_name)[1:])
        self.start_month.setCurrentIndex(now.month-1)
        self.start_month.setEditable(False)
        # End Panel : Year
        self.end_year = widgets.QSpinBox(self)
        self.end_year.setMaximum(datetime.MINYEAR)
        self.end_year.setMaximum(datetime.MAXYEAR)
        self.end_year.setValue(now.year)
        # End Panel : Month
        self.end_month = widgets.QComboBox(self)
        self.end_month.addItems(list(calendar.month_name)[1:])
        self.end_month.setCurrentIndex(now.month-1)
        self.end_month.setEditable(False)
        # Layout
        main = widgets.QHBoxLayout()
        start_layout = widgets.QGridLayout()
        start_layout.addWidget(year_label,0,0)
        start_layout.addWidget(self.start_year,0,1)
        start_layout.addWidget(month_label,1,0)
        start_layout.addWidget(self.start_month,1,1)
        start_panel.setLayout(start_layout)
        main.addWidget(start_panel)
        end_layout = widgets.QGridLayout()
        end_layout.addWidget(year_label,0,0)
        end_layout.addWidget(self.end_year,0,1)
        end_layout.addWidget(month_label,1,0)
        end_layout.addWidget(self.end_month,1,1)
        end_panel.setLayout(end_layout)
        main.addWidget(end_panel)
        self.setLayout(main)
        # Connection
        self.start_year.valueChanged.connect(self._range_changed)
        self.start_month.currentIndexChanged.connect(self._range_changed)
        self.end_year.valueChanged.connect(self._range_changed)
        self.end_month.currentIndexChanged.connect(self._range_changed)

    def _range_changed(self):
        start = datetime.datetime(
            self.start_year.value(), self.start_month.currentIndex(), 0, 0, 0
        )
        end = datetime.datetime(
            self.end_year.value(), self.end_month.currentIndex(), 0, 0, 0
        )
        if end < start:
            modified = start + datetime.timedelta(
                days=0 - calendar.mdays[start.month - 1]
            )
            self.start_year.setValue(modified.year)
            self.start_month.setCurrentIndex(modified.month)
        if start > end:
            modified = end + datetime.timedelta(days=calendar.mdays[end.month])
            self.end_year.setValue(modified.year)
            self.end_month.setCurrentIndex(modified.month)

    def range(self):
        """
        Return a triple: start datetime, end datetime, and sample timedelta.
        """
        start = datetime.datetime(
            self.start_year.value(), self.start_month.currentIndex(), 0, 0, 0
        )
        end = datetime.datetime(
            self.end_year.value(), self.end_month.currentIndex(), 0, 0, 0
        )
        return start, end, self.sample()


