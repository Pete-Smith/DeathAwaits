import datetime
import re

import PyQt6.QtWidgets as widgets

from death_awaits.palettes import get_application_palette


class PlotDialogBase(widgets.QWidget):
    name = "*** A VERBOSE NAME ***"

    def __init__(self, parent=None):
        super(PlotDialogBase, self).__init__(parent)
        # Layout
        layout = widgets.QGridLayout()
        row = 0
        max_column = 0
        for aw in self.additional_widgets():
            if len(aw) == 1:
                layout.addWidget(aw[0], row, 0, 1, max_column)
            for column, w in enumerate(aw):
                layout.addWidget(w, row, column)
                if column > max_column:
                    max_column = column
            row += 1
        self.setLayout(layout)

    def additional_widgets(self):
        """
        Return a 2d array of widgets. Rows of widgets.
        Subclasses should call this method with super,
        then extend the result with their own widgets
        and return everything.
        """
        self.level = widgets.QSpinBox(self)
        self.level.setMinimum(1)
        self.level.setMaximum(12)
        self.level.setValue(1)
        level_label = widgets.QLabel("Level:", self)
        level_label.setBuddy(self.level)
        self.categories = widgets.QSpinBox(self)
        self.categories.setMinimum(1)
        self.categories.setMaximum(len(get_application_palette()))
        self.categories.setValue(10)
        categories_label = widgets.QLabel("Number of Categories:", self)
        categories_label.setBuddy(self.categories)
        self.inclusive_other = widgets.QCheckBox(
            "Other category includes non-matching activities.", self
        )
        return [
            (level_label, self.level),
            (categories_label, self.categories),
            (self.inclusive_other,),
        ]

    def plot(self, figure, database, activity, start, end):
        if (
            database.filter(activity=activity, start=start, end=end, first=True)
            and activity != "unrecorded"
        ):
            self._plot(figure, database, activity, start, end)

    def _plot(self, figure, database, activity, start, end):
        """Private plot method to be overridden."""
        raise NotImplementedError()

    @staticmethod
    def bracket(database, activity, start, end):
        """
        Return modified start and end datetime instances -
        the day boundaries of the entry range that is extent in the
        database.
        """
        first = database.filter(activity, start, end, first=True)
        if first:
            if first["start"] > start:
                start = first["start"]
        last = database.filter(activity, start, end, last=True)
        if last:
            if last["end"] < end:
                end = last["end"]
                end = end + datetime.timedelta(days=1)
        start = datetime.datetime(start.year, start.month, start.day, 0, 0, 0)
        end = datetime.datetime(end.year, end.month, end.day, 0, 0, 0)
        return start, end

    def ranked_activities(self, database, activity, start, end):
        """
        Return a list of activity, proportion tuples,
        sorted largest-to-smallest, taking into account the number of
        categories and the activity filter.
        """
        level = self.level.value()
        category_count = self.categories.value()
        activities = database.slice_activities(
            start=start,
            end=end,
            level=level,
            unrecorded=getattr(self, "unrecorded", True),
        )
        items_shown = list(activities.items())
        if activity:
            reg = re.compile(activity, re.IGNORECASE)
            new_items = []
            other = []
            for k, v in items_shown:
                m = reg.search(k)
                if m:
                    new_items.append(
                        (k, v),
                    )
                elif self.inclusive_other.isChecked():
                    other.append(v)
            if other:
                new_items.append(
                    ("other", sum(other)),
                )
            items_shown = new_items
        items_shown.sort(key=lambda i: i[1], reverse=True)
        if len(items_shown) > category_count:
            other = sum([n[1] for n in items_shown[category_count:]])
            items_shown = items_shown[:category_count]
            other_value = sum([n[1] for n in items_shown if n[0] == "other"]) or 0
            items_shown.append(
                ("other", other + other_value),
            )
        return items_shown

    @property
    def name(self):
        """This can simply be a string attribute on the subclass."""
        raise NotImplementedError()
