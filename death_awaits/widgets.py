import PyQt5.QtCore as core
import PyQt5.QtWidgets as widgets



class DayRangeSelector(widgets.QWidget):
    def __init__(self, show_sample=True, parent=None):
        super(DayRangeSelector, self).__init__(show_sample, parent)
        # Widgets
        self.start = widgets.QDateEdit(self)
        self.start.setDate(core.QDate.currentDate().addMonths(-1))
        self.start.setCalendarPopup(True)
        start_label = widgets.QLabel("Start:",self)
        start_label.setBuddy(self.start)
        self.end = widgets.QDateEdit(self)
        self.end.setDate(core.QDate.currentDate())
        self.end.setCalendarPopup(True)
        end_label = widgets.QLabel("End:",self)
        end_label.setBuddy(self.end)
        # Layouts
        main = widgets.QHBoxLayout()
        main.addWidget(start_label)
        main.addWidget(self.start)
        main.addWidget(end_label)
        main.addWidget(self.end)
        self.setLayout(main)
        # Connections
        self.start.editingFinished.connect(self._range_changed)
        self.end.editingFinished.connect(self._range_changed)

    def _range_changed(self):
        start = self.start.dateTime()
        end = self.end.dateTime()
        if end < start:
            self.start.setDate(end.date().addDays(-1))
        elif start > end:
            self.end.setDate(start.date().addDays(1))

    def range(self):
        self._range_changed()
        start = self.start.dateTime().toPyDateTime()
        end = self.end.dateTime().toPyDateTime()
        return start, end, self.sample()


class WeekdaySelector(widgets.QWidget):
    def __init__(self, initial_state= None, parent=None):
        super(WeekdaySelector, self).__init__(parent)
        self._days = []
        layout = widgets.QHBoxLayout()
        self.setLayout(layout)
        for i in range(1, 8):
            day_name = core.QDate.shortDayName(i)
            day = widgets.QCheckBox(day_name,self)
            layout.addWidget(day)
            if initial_state is None or i in initial_state:
                day.setChecked(True)
            else:
                day.setChecked(False)
            self._days.append(day)

    def __str__(self):
        days = self.selection()
        result = str()
        for i, num in enumerate(days):
            if i > 0 and i < len(days) - 1:
                if days[i-1] + 1 == num and days[i+1] - 1 == num:
                    if len(result) and result[-1] != '-':
                        result += '-'
                    continue
                elif len(result) and result[-1] != '-':
                    result += ', '
            result += core.QDate.shortDayName(num)
        return result

    def selection(self):
        result = [
            n+1 for n in range(len(self._days))
            if self._days[n].isChecked()
        ]
        if len(result) == 0:
            return list(range(1,8))
        return result
