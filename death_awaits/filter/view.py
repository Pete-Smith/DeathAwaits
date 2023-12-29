import datetime
import calendar

import PyQt6.QtGui as gui
import PyQt6.QtCore as core
import PyQt6.QtWidgets as widgets

from death_awaits.helper import get_icon, em_dist, iso_to_gregorian
from death_awaits.log.view import LIST_EM


class FilterPanel(widgets.QGroupBox):
    filter_types = (
        "Year",
        "Month",
        "Week",
        "Start/End",
        "All",
    )
    apply_filter = core.pyqtSignal(str, datetime.datetime, datetime.datetime)
    responsive = True

    def __init__(self, parent=None):
        super(FilterPanel, self).__init__("Filter:", parent)
        # Actions
        self.clear_action = gui.QAction("Clear Activity Filter", self)
        self.clear_action.setIcon(get_icon("x.png"))
        # Widget
        now = datetime.datetime.now()
        self.type_selector = widgets.QComboBox(self)
        self.type_selector.addItems(FilterPanel.filter_types)
        self.type_selector.setEditable(False)
        type_label = widgets.QLabel("Range:", self)
        type_label.setBuddy(self.type_selector)
        self.start = widgets.QDateTimeEdit(self)
        self.start.setDateTime(now - datetime.timedelta(seconds=60 * 60))
        self.end = widgets.QDateTimeEdit(self)
        self.end.setDateTime(now)
        self.year = widgets.QSpinBox(self)
        self.year.setMaximum(1000)
        self.year.setMaximum(datetime.MAXYEAR)
        self.year.setValue(now.year)
        self.year_label = widgets.QLabel("Year:")
        self.month = widgets.QComboBox(self)
        self.month.addItems(list(calendar.month_name)[1:])
        self.month.setCurrentIndex(now.month - 1)
        self.month.setEditable(False)
        self.month_label = widgets.QLabel("Month:")
        self.week = widgets.QSpinBox(self)
        self.week.setMinimum(1)
        self.week.setMaximum(52)
        self.week.setValue(now.isocalendar()[1])
        self.week_label = widgets.QLabel("Week:")
        self.activity = widgets.QLineEdit(self)
        activity_label = widgets.QLabel("Activity:", self)
        blank_widget = widgets.QWidget(self)
        clear_btn = widgets.QToolButton(self)
        clear_btn.setDefaultAction(self.clear_action)
        # Layout
        main = widgets.QHBoxLayout()
        main.addWidget(type_label)
        main.addWidget(self.type_selector, 2)
        ymw_widget = widgets.QWidget(self)
        ymw_layout = widgets.QHBoxLayout()
        ymw_layout.addWidget(self.year_label)
        ymw_layout.addWidget(self.year, 2)
        ymw_layout.addWidget(self.month_label)
        ymw_layout.addWidget(self.month, 2)
        ymw_layout.addWidget(self.week_label)
        ymw_layout.addWidget(self.week, 2)
        ymw_layout.setContentsMargins(0, 0, 0, 0)
        ymw_widget.setLayout(ymw_layout)
        range_widget = widgets.QWidget(self)
        range_layout = widgets.QHBoxLayout()
        range_layout.addWidget(self.start, 2)
        range_layout.addWidget(self.end, 2)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_widget.setLayout(range_layout)
        self.stack = widgets.QStackedLayout()
        self.stack.addWidget(ymw_widget)
        self.stack.addWidget(range_widget)
        self.stack.addWidget(blank_widget)
        main.addLayout(self.stack, 2)
        main.addWidget(activity_label)
        main.addWidget(self.activity, 2)
        main.addWidget(clear_btn)
        self.setLayout(main)
        self.setMaximumWidth(em_dist(LIST_EM))
        # Connections
        self.clear_action.triggered.connect(self.clear_activity)
        self.type_selector.currentIndexChanged.connect(self.update_interface)
        self.type_selector.currentIndexChanged.connect(self.changed)
        self.year.valueChanged.connect(self.changed)
        self.month.activated.connect(self.changed)
        self.week.valueChanged.connect(self.changed)
        self.start.dateTimeChanged.connect(self.changed)
        self.end.dateTimeChanged.connect(self.changed)
        self.activity.returnPressed.connect(self.changed)
        self.activity.editingFinished.connect(self.changed)
        self.update_interface()

    def initial_state(self, anchor_time):
        if anchor_time is None:
            anchor_time = datetime.datetime.now()
        self.responsive = False
        self.type_selector.setCurrentIndex(1)
        self.month.setCurrentIndex(anchor_time.month - 1)
        self.year.setValue(anchor_time.year)
        self.week.setValue(anchor_time.isocalendar()[1] - 1)
        self.responsive = True
        self.changed()

    def changed(self):
        if self.responsive:
            activity, start, end = self.current_filter
            self.apply_filter.emit(activity, start, end)

    def clear_activity(self):
        self.activity.clear()
        self.changed()

    def update_interface(self):
        if self.type_selector.currentIndex() == 0:
            self.stack.setCurrentIndex(0)
            self.month_label.hide()
            self.month.hide()
            self.week_label.hide()
            self.week.hide()
        elif self.type_selector.currentIndex() == 1:
            self.stack.setCurrentIndex(0)
            self.month_label.show()
            self.month.show()
            self.week_label.hide()
            self.week.hide()
        elif self.type_selector.currentIndex() == 2:
            self.stack.setCurrentIndex(0)
            self.month_label.hide()
            self.month.hide()
            self.week_label.show()
            self.week.show()
        elif self.type_selector.currentIndex() == 3:
            self.stack.setCurrentIndex(1)
        elif self.type_selector.currentIndex() == 4:
            self.stack.setCurrentIndex(2)

    @property
    def current_filter(self):
        activity_text = self.activity.text().strip()
        range_ = self.current_range
        return activity_text, range_[0], range_[1]

    @property
    def current_range(self):
        year = self.year.value()
        month = self.month.currentIndex() + 1
        week = self.week.value()
        if self.type_selector.currentIndex() == 0:
            return (
                datetime.datetime(year, 1, 1, 0, 0, 0, 0),
                datetime.datetime(year + 1, 1, 1, 0, 0, 0, 0),
            )
        elif self.type_selector.currentIndex() == 1:
            if month == 12:
                next_month = datetime.datetime(year + 1, 1, 1, 0, 0, 0, 0)
            else:
                next_month = datetime.datetime(year, month + 1, 1, 0, 0, 0, 0)
            return (datetime.datetime(year, month, 1, 0, 0, 0, 0), next_month)
        elif self.type_selector.currentIndex() == 2:
            base = iso_to_gregorian(year, week, 1)
            start = datetime.datetime(base.year, base.month, base.day, 0, 0, 0)
            end = start + datetime.timedelta(days=7)
            base = core.QDate(year, 1, 1)
            return start, end
        elif self.type_selector.currentIndex() == 3:
            return (
                self.start.dateTime().toPyDateTime(),
                self.end.dateTime().toPyDateTime(),
            )
        elif self.type_selector.currentIndex() == 4:
            return (
                datetime.datetime(datetime.MINYEAR, 1, 1),
                datetime.datetime(datetime.MAXYEAR, 1, 1),
            )
