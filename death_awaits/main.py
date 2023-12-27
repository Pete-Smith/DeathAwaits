# Standard library imports
import os
import sys
import datetime
import calendar
from functools import partial
import shutil
import platform
import ctypes
import re

import PyQt6.QtGui as gui
import PyQt6.QtCore as core
import PyQt6.QtWidgets as widgets
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
import matplotlib.pyplot as plt

from death_awaits.db import LogModel, LogDb
from death_awaits.helper import (
    iso_to_gregorian,
    get_application_icon,
    get_icon,
    stringify_datetime,
    em_dist,
    configure_matplotlib,
)
from death_awaits.plots import PLOTTERS
from death_awaits.palettes import get_application_palette

ORG_NAME = "anagogical.net"
APP_NAME = "Death Awaits"

DEBUG = True
LIST_EM = 50


class MainWindow(widgets.QMainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        # Actions
        self.open_preferences_action = gui.QAction("Preferences...", self)
        self.quit_action = gui.QAction("Quit", self)
        self.quit_action.setShortcut(gui.QKeySequence("Ctrl+Q"))
        # Set-up
        self.backup_db()
        self.clean_backups()
        self.workspace = Workspace(self.current_db, self)
        self.setCentralWidget(self.workspace)
        self._build_menu()
        self.setWindowTitle(APP_NAME)
        # Connections
        self.open_preferences_action.triggered.connect(self.open_preferences)
        self.quit_action.triggered.connect(self.close)

    def open_preferences(self):
        dlg = PreferencesDialog(self)
        dlg.exec_()

    def list_backups(self):
        backups = [
            os.path.join(self._app_directory, n)
            for n in os.listdir(self._app_directory)
            if os.path.isfile(self.current_db)
            and not os.path.samefile(
                self.current_db, os.path.join(self._app_directory, n)
            )
        ]
        backups.sort(key=lambda n: os.stat(n).st_mtime)
        return backups

    def clean_backups(self):
        settings = core.QSettings()
        backup_count = settings.value("number_of_backups", 15)
        backups = self.list_backups()
        if len(backups) > backup_count:
            for f in backups[:backup_count]:
                os.remove(f)

    def backup_db(self):
        if not os.path.isfile(self.current_db):
            return
        count = 0
        backup_name = os.path.basename(self.current_db) + ".{0}".format(count)
        while backup_name in os.listdir(self._app_directory):
            count += 1
            backup_name = os.path.basename(self.current_db) + ".{0}".format(count)
        shutil.copy(self.current_db, os.path.join(self._app_directory, backup_name))

    def revert(self, filename):
        assert os.path.isfile(filename)
        self.backup_db()
        shutil.copy(filename, self.current_db)
        self.workspace = Workspace(self.current_db, self)
        self.setCentralWidget(self.workspace)
        self._build_menu()

    def _build_revert_menu(self):
        self.revert_menu.clear()
        for fname in self.list_backups():
            if not os.path.isfile(fname):
                continue
            timestamp = datetime.datetime.fromtimestamp(os.stat(fname).st_mtime)
            label = stringify_datetime(timestamp)
            action = self.revert_menu.addAction(label)
            action.triggered.connect(partial(self.revert, fname))

    @property
    def current_db(self):
        return os.path.join(self._app_directory, "user_data.sqlite")

    @property
    def _app_directory(self):
        app_dir = core.QStandardPaths.writableLocation(
            core.QStandardPaths.StandardLocation.AppDataLocation
        )
        if not os.path.isdir(app_dir):
            os.makedirs(app_dir)
        return app_dir

    def _build_menu(self):
        self.menuBar().clear()
        file_menu = self.menuBar().addMenu("&File")
        self.revert_menu = file_menu.addMenu("Revert")
        self.revert_menu.aboutToShow.connect(self._build_revert_menu)
        file_menu.addSeparator()
        file_menu.addAction(self.workspace.graph_panel.print_action)
        file_menu.addAction(self.quit_action)
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.workspace.list_panel.undo_action)
        edit_menu.addAction(self.workspace.list_panel.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.open_preferences_action)
        list_menu = self.menuBar().addMenu("&List")
        list_menu.addAction(self.workspace.list_panel.save_action)
        list_menu.addAction(self.workspace.list_panel.cap_save_action)
        list_menu.addAction(self.workspace.list_panel.clear_action)
        list_menu.addAction(self.workspace.list_panel.match_action)
        list_menu.addSeparator()
        list_menu.addAction(self.workspace.list_panel.edit_action)
        list_menu.addAction(self.workspace.list_panel.adjust_action)
        list_menu.addAction(self.workspace.list_panel.delete_action)
        list_menu.addAction(self.workspace.list_panel.rename_action)
        graph_menu = self.menuBar().addMenu("&Graph")
        self.graph_type_menu = graph_menu.addMenu("Graph Type")
        self.graph_type_menu.aboutToShow.connect(self._build_graph_type_menu)
        graph_menu.addAction(self.workspace.graph_panel.configure_action)
        graph_menu.addAction(self.workspace.graph_panel.refresh_action)

    def _build_graph_type_menu(self):
        def set_graph_type(name):
            type_box = self.workspace.graph_panel.type_box
            type_box.setCurrentIndex(type_box.findText(name))

        menu = self.graph_type_menu
        menu.clear()
        if not hasattr(self, "workspace") or not isinstance(self.workspace, Workspace):
            return None
        for i, item in enumerate(self.workspace.graph_panel.plotters):
            action = menu.addAction(item.name)
            action.triggered.connect(partial(set_graph_type, item.name))


class Workspace(widgets.QWidget):
    filter_changed = core.pyqtSignal(str, datetime.datetime, datetime.datetime)

    def __init__(self, filename=None, parent=None):
        super(Workspace, self).__init__(parent)
        self.setWindowTitle(APP_NAME)
        if filename is None:
            filename = ":memory:"
        self._db = LogDb(filename, bounds=60 * 60, units="seconds")
        # Widgets
        self.filter_panel = FilterPanel(self)
        self.list_panel = ListPanel(self._db, self)
        self.graph_panel = GraphPanel(self._db, self)
        self.tabs = widgets.QTabWidget()
        # self.tabs.setTabPosition(widgets.QTabWidget.TabPosition.West)
        self.tabs.addTab(self.list_panel, get_icon("list.png"), "List")
        self.tabs.addTab(self.graph_panel, get_icon("pie.png"), "Matplotlib")
        # Layout
        main = widgets.QVBoxLayout()
        top_section = widgets.QHBoxLayout()
        top_section.addStretch(0)
        top_section.addWidget(self.filter_panel, 1)
        top_section.addStretch(0)
        main.addLayout(top_section)
        main.addWidget(self.tabs, 1)
        self.setLayout(main)
        # Connections
        self.filter_panel.apply_filter.connect(self.apply_filter)
        # self.tabs.currentChanged.connect(self.tab_change)
        # Initialize
        last_entry = self._db.filter(last=True)
        if last_entry is not None:
            last_entry = last_entry["start"]
        self.filter_panel.initial_state(last_entry)

    @property
    def current_filter(self):
        return self.filter_panel.current_filter

    @core.pyqtSlot(str, datetime.datetime, datetime.datetime)
    def apply_filter(self, activity, start, end):
        self.list_panel.update_filter(
            activity, start, end, self.tabs.currentWidget() is self.list_panel
        )
        self.graph_panel.update_filter(
            activity, start, end, self.tabs.currentWidget() is self.graph_panel
        )


class GraphPanel(widgets.QWidget):
    def __init__(self, database, parent=None):
        super(GraphPanel, self).__init__(parent)
        assert isinstance(database, LogDb)
        self._db = database
        # Misc Attributes
        self.plotters = [plotter() for plotter in PLOTTERS]
        # Actions
        self.configure_action = gui.QAction("Configure Graph", self)
        self.configure_action.setIcon(get_icon("cog.png"))
        self.configure_action.setCheckable(True)
        self.refresh_action = gui.QAction("Refresh Graph", self)
        self.refresh_action.setIcon(get_icon("refresh.png"))
        self.print_action = gui.QAction("Save Graph to SVG", self)
        self.print_action.setIcon(get_icon("print.png"))
        self.shuffle_color_action = gui.QAction("Shuffle Colors", self)
        self.shuffle_color_action.setIcon(get_icon("shuffle.png"))
        # TODO: Find an icon. Create the action.
        # Widgets
        self.type_box = widgets.QComboBox(self)
        self.type_box.setEditable(False)
        type_label = widgets.QLabel("Graph Type:", self)
        config_stack = widgets.QStackedWidget(self)
        for item in self.plotters:
            self.type_box.addItem(item.name)
            config_stack.addWidget(item)
        type_label.setBuddy(self.type_box)
        self.figure = plt.Figure()
        # self.figure.set_tight_layout(True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setParent(self)
        configure_btn = widgets.QToolButton(self)
        configure_btn.setDefaultAction(self.configure_action)
        refresh_btn = widgets.QToolButton(self)
        refresh_btn.setDefaultAction(self.refresh_action)
        # Widgets : Containers
        config_panel = widgets.QWidget(self)
        display_stack = widgets.QStackedWidget(self)
        display_stack.addWidget(self.canvas)
        display_stack.addWidget(config_panel)
        # Layout
        main = widgets.QVBoxLayout()
        row1 = widgets.QHBoxLayout()
        row1.addWidget(type_label)
        row1.addWidget(self.type_box)
        row1.addStretch(1)
        row1.addWidget(configure_btn)
        row1.addWidget(refresh_btn)
        main.addLayout(row1)
        config_outer = widgets.QVBoxLayout()
        config_outer.addStretch(1)
        config_inner = widgets.QHBoxLayout()
        config_inner.addStretch(1)
        config_inner.addWidget(config_stack)
        config_inner.addStretch(1)
        config_outer.addLayout(config_inner)
        config_outer.addStretch(1)
        config_panel.setLayout(config_outer)
        main.addWidget(display_stack, 1)
        self.setLayout(main)
        # Connections
        self.type_box.currentIndexChanged.connect(self.refresh_plot)
        self.type_box.currentIndexChanged.connect(config_stack.setCurrentIndex)
        self.configure_action.toggled.connect(self.check_config_update)
        self.configure_action.toggled.connect(display_stack.setCurrentIndex)
        self.refresh_action.triggered.connect(self.refresh_plot)
        self.print_action.triggered.connect(self.graph_to_svg)

    def graph_to_svg(self):
        filename, _ = widgets.QFileDialog.getSaveFileName(
            self,
            "Save SVG",
            os.path.expanduser("~"),
            filter="SVG (*.svg);",
        )
        self.figure.savefig(filename)

    @core.pyqtSlot(str, datetime.datetime, datetime.datetime, bool)
    def update_filter(self, activity, start, end, visible):
        self.activity = activity
        self.start = start
        self.end = end
        if visible:
            self.refresh_plot()

    def refresh_plot(self):
        if DEBUG:
            sys.stderr.write("Updating graph..." + os.linesep)
        if gui.QGuiApplication.queryKeyboardModifiers() == Qt.KeyboardModifier.ControlModifier:
            palette = get_application_palette()
            palette._past_assignments = dict()
        self.figure.clf(keep_observers=True)
        i = self.type_box.currentIndex()
        plotter = self.plotters[i]
        activity = getattr(self, "activity", None)
        start = getattr(self, "start", None)
        end = getattr(self, "end", None)
        if None not in (activity, start, end):
            plotter.plot(self.figure, self._db, activity, start, end)
        self.canvas.draw()
        self.update()

    def check_config_update(self, toggled):
        if not toggled:
            self.refresh_plot()


class ListPanel(widgets.QWidget):
    def __init__(self, database, parent=None):
        super(ListPanel, self).__init__(parent)
        assert isinstance(database, LogDb)
        self._db = database
        # Actions
        self.edit_action = gui.QAction("Edit Selection", self)
        self.edit_action.setIcon(get_icon("modify.png"))
        self.adjust_action = gui.QAction("Adjust Selection...", self)
        self.adjust_action.setIcon(get_icon("plus_minus.png"))
        self.delete_action = gui.QAction("Delete Selection", self)
        self.delete_action.setIcon(get_icon("trash.png"))
        self.delete_action.setShortcut(gui.QKeySequence("Del"))
        self.rename_action = gui.QAction("Rename Selection", self)
        self.save_action = gui.QAction("Save Entry", self)
        self.save_action.setIcon(get_icon("check.png"))
        self.save_action.setShortcut(gui.QKeySequence("Ctrl+Space"))
        # self.save_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.cap_save_action = gui.QAction(
            "Save Entry && Apply Capitalization", self
        )
        self.cap_save_action.setShortcut(gui.QKeySequence("Ctrl+Shift+Space"))
        self.clear_action = gui.QAction("Clear Entry", self)
        self.clear_action.setShortcut(gui.QKeySequence("Esc"))
        # self.clear_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.clear_action.setIcon(get_icon("x.png"))
        self.match_action = gui.QAction("Clear Entry && Match Selected Range", self)
        self.match_action.setShortcut(gui.QKeySequence("Shift+Esc"))
        self.addAction(self.match_action)
        self.undo_action = gui.QAction("Undo", self)
        self.undo_action.setIcon(get_icon("undo.png"))
        self.redo_action = gui.QAction("Redo", self)
        self.redo_action.setIcon(get_icon("redo.png"))
        # Widgets
        activity, start, end = self.parent().current_filter
        self.model = LogModel(database, activity, start, end, parent=self)
        self.table = widgets.QTableView(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(widgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(widgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(widgets.QHeaderView.ResizeMode.Stretch)
        self.table.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.table.hideColumn(0)
        self.table.verticalHeader().hide()
        self.editor = EntryEditor(database, self)
        edit_btn = widgets.QToolButton(self)
        edit_btn.setDefaultAction(self.edit_action)
        clear_btn = widgets.QToolButton(self)
        clear_btn.setDefaultAction(self.clear_action)
        adjust_btn = widgets.QToolButton(self)
        adjust_btn.setDefaultAction(self.adjust_action)
        save_btn = widgets.QToolButton(self)
        save_btn.setDefaultAction(self.save_action)
        delete_btn = widgets.QToolButton(self)
        delete_btn.setDefaultAction(self.delete_action)
        undo_btn = widgets.QToolButton(self)
        undo_btn.setDefaultAction(self.undo_action)
        redo_btn = widgets.QToolButton(self)
        redo_btn.setDefaultAction(self.redo_action)
        center_widget = widgets.QWidget(self)
        center_widget.setMaximumWidth(em_dist(LIST_EM))
        # Layout
        main = widgets.QHBoxLayout()
        main.addStretch(0)
        center_layout = widgets.QVBoxLayout()
        center_widget.setLayout(center_layout)
        top_row = widgets.QHBoxLayout()
        top_row.addWidget(undo_btn)
        top_row.addWidget(redo_btn)
        top_row.addStretch(1)
        top_row.addWidget(delete_btn)
        top_row.addWidget(adjust_btn)
        top_row.addWidget(edit_btn)
        center_layout.addLayout(top_row)
        center_layout.addWidget(self.table, 1)
        center_layout.addWidget(self.editor)
        bottom_row = widgets.QHBoxLayout()
        bottom_row.addStretch(1)
        bottom_row.addWidget(clear_btn)
        bottom_row.addWidget(save_btn)
        center_layout.addLayout(bottom_row)
        main.addWidget(center_widget, 1)
        main.addStretch(0)
        self.setLayout(main)
        # Connections
        self.save_action.triggered.connect(self.save_entry)
        self.cap_save_action.triggered.connect(partial(self.save_entry, True))
        self.clear_action.triggered.connect(self.clear_entry)
        self.match_action.triggered.connect(partial(self.clear_entry, False, True))
        self.edit_action.triggered.connect(self.edit_selection)
        self.editor.changed.connect(self.update_interface)
        self.table.selectionModel().selectionChanged.connect(self.update_interface)
        self.table.doubleClicked.connect(self.edit_selection)
        self.delete_action.triggered.connect(self.delete_selection)
        self.adjust_action.triggered.connect(self.adjust_selection)
        self.undo_action.triggered.connect(self.undo)
        self.redo_action.triggered.connect(self.redo)
        self.rename_action.triggered.connect(self.rename_selection)
        core.QTimer.singleShot(0, self.clear_entry)

    def update_interface(self):
        self.save_action.setEnabled(self.editor.is_entry_valid())
        self.cap_save_action.setEnabled(self.editor.is_entry_valid())
        self.edit_action.setEnabled(
            len(self.table.selectionModel().selectedRows()) == 1
        )

        self.rename_action.setEnabled(
            len(self.table.selectionModel().selectedRows()) > 0
        )
        self.delete_action.setEnabled(
            len(self.table.selectionModel().selectedRows()) > 0
        )
        self.adjust_action.setEnabled(
            len(self.table.selectionModel().selectedRows()) > 0
        )
        self.undo_action.setEnabled(self._db.undo_possible())
        self.redo_action.setEnabled(self._db.redo_possible())

    @core.pyqtSlot(str, datetime.datetime, datetime.datetime, bool)
    def update_filter(self, activity, start, end, visible):
        self.model.update_cache(activity, start, end)
        # self.model.update_cache(*self.parent().current_filter)

    def undo(self):
        self._db.undo()
        self.update_interface()

    def redo(self):
        self._db.redo()
        self.update_interface()

    def save_entry(self, apply_capitalization=False):
        new_row = self.editor.entry()
        new_id = self.model.create_entry(
            apply_capitalization=apply_capitalization, **new_row
        )
        self.table.update()
        if DEBUG:
            sys.stdout.write(("new_id {0}".format(new_id)) + os.linesep)
        for row in range(self.model.rowCount()):
            new_index = self.table.model().index(row, 0)
            if self.model.data(new_index) == new_id:
                if DEBUG:
                    sys.stdout.write(
                        ("new_index {0}, row {1}".format(new_index, row)) + os.linesep
                    )
                break
        else:
            row = None
            if DEBUG:
                sys.stdout.write("row not found" + os.linesep)
        if row is not None:
            selection = core.QItemSelection()
            selection.append(
                core.QItemSelectionRange(
                    self.table.model().index(new_index.row(), 0),
                    self.table.model().index(
                        new_index.row(), self.table.model().columnCount() - 1
                    ),
                )
            )
            self.table.selectionModel().select(
                selection, core.QItemSelectionModel.SelectionFlag.ClearAndSelect
            )
            self.table.scrollTo(new_index)
        self.editor.update_completer(new_row["activity"])
        self._db.save_changes()
        self.update_interface()
        core.QTimer.singleShot(0, partial(self.clear_entry, False))

    def edit_selection(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if len(selected_rows) == 1:
            i = selected_rows[0].row()
            entry = self.model.data(self.model.index(i, 0), role=Qt.ItemDataRole.UserRole)
            self.editor.set_entry(entry)
        self.update_interface()

    def rename_selection(self):
        names = set(
            [
                self.model.data(row, role=Qt.ItemDataRole.UserRole)["activity"]
                for row in self.table.selectionModel().selectedRows()
            ]
        )
        name = names.pop() if len(names) == 1 else ""
        dlg = RenameDialog(self._db, name, self)
        if dlg.exec():
            ids = [
                self.model.data(row, role=Qt.ItemDataRole.UserRole)["id"]
                for row in self.table.selectionModel().selectedRows()
            ]
            self._db.rename_entry(dlg.activity.text(), ids, dlg.apply_cap.isChecked())
            self._db.save_changes()
            self.update_interface()

    def adjust_selection(self):
        # FIXME: This can mangle large amounts of data.
        # It didn't push save_changes, for one.
        dialog = AdjustDialog(self)
        if dialog.exec_():
            amount = dialog.value()
            if amount is None:
                return None
            ids = [
                self.model.data(row, role=Qt.ItemDataRole.UserRole)["id"]
                for row in self.table.selectionModel().selectedRows()
            ]
            self.model.adjust_entries(ids, amount)
            self._db.save_changes()
            self.update_interface()

    def delete_selection(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            ids = [self.model.data(self.model.index(r.row(), 0)) for r in selected_rows]
            for id in ids:
                self.model.delete_entry(id)
        self._db.save_changes()
        self.update_interface()

    def clear_entry(self, clear_selection=True, match_range=False):
        """ """
        # selected_rows = self.table.selectionModel().selectedRows()
        selected_rows = set(
            i.row() for i in self.table.selectionModel().selectedIndexes()
        )
        latest_row, min_time, max_time = None, None, None
        for row in selected_rows:
            id = self.model.data(self.model.index(row, 0))
            entry = self._db.row(id)
            if latest_row is None:
                latest_row = row
            if min_time is None or min_time > entry["start"]:
                min_time = entry["start"]
            if max_time is None or max_time < entry["end"]:
                max_time = entry["end"]
                latest_row = row
        if None not in (latest_row, min_time, max_time):
            self.editor.reset(max_time)
            if latest_row == self.table.model().rowCount() - 1:
                self.table.scrollToBottom()
            else:
                self.table.scrollTo(
                    self.model.index(latest_row, 0),
                    hint=widgets.QTableView.ScrollHint.PositionAtCenter
                    | widgets.QTableView.ScrollHint.EnsureVisible,
                )
            if match_range:
                self.editor.start.setDateTime(min_time)
                self.editor.end.setDateTime(max_time)
                self.editor.link.setChecked(False)
        else:
            self.editor.reset(datetime.datetime.now())
            self.table.scrollToBottom()
        if clear_selection:
            self.table.clearSelection()
        self.update_interface()


class AdjustDialog(widgets.QDialog):
    def __init__(self, parent=None):
        super(AdjustDialog, self).__init__(parent)
        # Widgets
        self.forward_box = widgets.QCheckBox("Forward", self)
        self.forward_box.setChecked(True)
        self.backward_box = widgets.QCheckBox("Backward", self)
        box_group = widgets.QButtonGroup(self)
        box_group.addButton(self.forward_box)
        box_group.addButton(self.backward_box)
        box_group.setExclusive(True)
        self.quantity = widgets.QLineEdit("24h", self)
        quantity_label = widgets.QLabel("Amount:", self)
        bbox = widgets.QDialogButtonBox(
            widgets.QDialogButtonBox.StandardButton.Ok | widgets.QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        # Layout
        main = widgets.QVBoxLayout()
        row1 = widgets.QHBoxLayout()
        col1 = widgets.QVBoxLayout()
        col1.addWidget(self.forward_box)
        col1.addWidget(self.backward_box)
        row1.addLayout(col1)
        row1.addWidget(quantity_label)
        row1.addWidget(self.quantity)
        main.addLayout(row1)
        row2 = widgets.QHBoxLayout()
        row2.addStretch(1)
        row2.addWidget(bbox)
        main.addLayout(row2)
        self.setLayout(main)
        # Connections
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        self.quantity.textChanged.connect(self._quantity_edited)
        self.quantity.editingFinished.connect(partial(self._quantity_edited, True))

    def _quantity_edited(self, fix=False):
        pass
        # TODO
        # seconds = LogDb.parse_duration(self.quantity.text())
        # if seconds is None:
        #     self.quantity.setStyleSheet(INVALID_STYLE)
        # else:
        #     self.quantity.setStyleSheet(VALID_STYLE)
        #     if fix:
        #         self.quantity.setText(LogDb.format_duration(seconds))

    def value(self):
        self._quantity_edited()
        seconds = LogDb.parse_duration(self.quantity.text())
        if seconds is None:
            return seconds
        elif self.forward_box.isChecked():
            return datetime.timedelta(seconds=seconds)
        elif self.backward_box.isChecked():
            return datetime.timedelta(seconds=0 - seconds)


class EntryEditor(widgets.QGroupBox):
    changed = core.pyqtSignal()
    percentile_finder = re.compile(r"^\s*(?P<number>\d+)\s*%\s*$")

    def __init__(self, database, parent=None):
        super(EntryEditor, self).__init__("Entry:", parent)
        assert isinstance(database, LogDb)
        self._db = database
        self.seconds = None
        self._id = None
        # Widgets
        self.activity = widgets.QLineEdit(self)
        activity_label = widgets.QLabel("Activity:", self)
        activity_label.setBuddy(self.activity)
        self.link = widgets.QCheckBox("Link", self)
        self.quantity_field = widgets.QLineEdit(self)
        self.quantity_field.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        quantity_label = widgets.QLabel("Duration:", self)
        quantity_label.setBuddy(self.quantity_field)
        start_box = widgets.QGroupBox("Start:", self)
        self.start_date = widgets.QDateEdit(self)
        self.start_date.setCalendarPopup(True)
        self.start = widgets.QTimeEdit(self)
        end_box = widgets.QGroupBox("End:", self)
        self.end_date = widgets.QDateEdit(self)
        self.end_date.setCalendarPopup(True)
        self.end = widgets.QTimeEdit(self)
        # Shortcuts
        start_shortcut = gui.QShortcut(gui.QKeySequence("Alt+S"), self)
        end_shortcut = gui.QShortcut(gui.QKeySequence("Alt+E"), self)
        activity_shortcut = gui.QShortcut(gui.QKeySequence("Alt+A"), self)
        link_shortcut = gui.QShortcut(gui.QKeySequence("Alt+L"), self)
        quantity_shortcut = gui.QShortcut(gui.QKeySequence("Alt+D"), self)
        # Tab Order
        self.setTabOrder(self.activity, self.quantity_field)
        self.setTabOrder(self.quantity_field, self.link)
        self.setTabOrder(self.link, self.start)
        self.setTabOrder(self.start, self.end)
        # Layout
        main = widgets.QVBoxLayout()
        top_row = widgets.QHBoxLayout()
        top_row.addWidget(activity_label)
        top_row.addWidget(self.activity, 8)
        top_row.addStretch(1)
        top_row.addWidget(quantity_label)
        top_row.addWidget(self.quantity_field, 2)
        top_row.addStretch(1)
        top_row.addWidget(self.link)
        main.addLayout(top_row)
        bottom_row = widgets.QHBoxLayout()
        start_box_layout = widgets.QVBoxLayout()
        start_box_layout.addWidget(self.start)
        start_box_layout.addWidget(self.start_date)
        start_box.setLayout(start_box_layout)
        bottom_row.addWidget(start_box, 4)
        bottom_row.addStretch(1)
        end_box_layout = widgets.QVBoxLayout()
        end_box_layout.addWidget(self.end)
        end_box_layout.addWidget(self.end_date)
        end_box.setLayout(end_box_layout)
        bottom_row.addWidget(end_box, 4)
        main.addLayout(bottom_row)
        self.setLayout(main)
        self.setMaximumWidth(em_dist(LIST_EM))
        # Connections
        self.start_date.dateChanged.connect(self.calendar_changed)
        self.end_date.dateChanged.connect(self.calendar_changed)
        self.quantity_field.editingFinished.connect(self.quantity_edited)
        self.start.dateTimeChanged.connect(self.start_end_edited)
        self.end.dateTimeChanged.connect(self.start_end_edited)
        self.start.dateTimeChanged.connect(self.update_calendars)
        self.end.dateTimeChanged.connect(self.update_calendars)
        self.quantity_field.editingFinished.connect(self.changed)
        self.start.dateTimeChanged.connect(self.changed)
        self.activity.editingFinished.connect(self.changed)
        self.end.dateTimeChanged.connect(self.changed)
        start_shortcut.activated.connect(self.start.setFocus)
        end_shortcut.activated.connect(self.end.setFocus)
        activity_shortcut.activated.connect(self.activity.setFocus)
        quantity_shortcut.activated.connect(self.quantity_field.setFocus)
        link_shortcut.activated.connect(self.link.toggle)
        # Setup
        self.update_completer()

    def update_completer(self, item=None):
        if item is None or not hasattr(self, "_activity_list"):
            self._activity_list = core.QStringListModel(self._db.activities())
            activity_completer = widgets.QCompleter(self._activity_list, self)
            activity_completer.setCompletionMode(widgets.QCompleter.CompletionMode.PopupCompletion)
            self.activity.setCompleter(activity_completer)
        if item not in self._activity_list.stringList():
            strlist = self._activity_list.stringList()
            strlist.append(item)
            self._activity_list.setStringList(strlist)

    def calendar_changed(self):
        start = core.QDateTime(self.start_date.date(), self.start.time())
        end = core.QDateTime(self.end_date.date(), self.end.time())
        self.start.setDateTime(start)
        self.end.setDateTime(end)
        self.start_end_edited()

    def update_calendars(self):
        self.start_date.setDate(self.start.date())
        self.end_date.setDate(self.end.date())

    def set_entry(self, entry):
        self._id = entry["id"]
        self.activity.setText(entry["activity"])
        self.start.setDateTime(entry["start"])
        span = (entry["end"] - entry["start"]).total_seconds()
        self.link.setChecked(abs(span - entry["quantity"]) < 0.01)
        self.end.setDateTime(entry["end"])
        self.quantity_field.setText(LogDb.format_duration(entry["quantity"]))
        self.activity.setFocus()

    def reset(self, latest):
        self._id = None
        self.start.setDateTime(latest)
        if not isinstance(latest, core.QDateTime):
            latest = core.QDateTime(latest)
        self.end.setDateTime(latest.addSecs(60 * 60))
        self.link.setChecked(True)
        self.activity.setText("")
        self.activity.setFocus()

    def is_entry_valid(self):
        return bool(
            self.activity.text()
            and self.start.dateTime() < self.end.dateTime()
            and self.seconds
        )

    @property
    def start_end_seconds(self):
        delta = abs(
            self.end.dateTime().toPyDateTime() - self.start.dateTime().toPyDateTime()
        )
        return (delta.days * 24 * 60 * 60) + delta.seconds

    def entry(self):
        if self.activity.hasFocus():
            self.activity.editingFinished.emit()
        if self.quantity_field.hasFocus():
            self.quantity_field.editingFinished.emit()
        activity = self.activity.text().strip()
        if activity == "":
            activity = None
        start = self.start.dateTime().toPyDateTime()
        end = self.end.dateTime().toPyDateTime()
        if abs((end - start).seconds - self.seconds) < 60:
            quantity = None
        else:
            quantity = LogDb.parse_duration(self.quantity_field.text())
        entry = {
            "id": self._id,
            "activity": activity,
            "start": start,
            "end": end,
            "quantity": quantity,
        }
        return entry

    def start_end_edited(self):
        current_quantity = LogDb.parse_duration(self.quantity_field.text())
        if current_quantity is None:
            current_quantity = self.seconds
        if (
            self.link.isChecked()
            or current_quantity is None
            or current_quantity > self.start_end_seconds
        ):
            self.seconds = self.start_end_seconds
        else:
            self.seconds = current_quantity
        quantity_text = LogDb.format_duration(self.seconds)
        self.quantity_field.setText(quantity_text)

    def percentile_quantity(self, text):
        m = self.percentile_finder.search(text)
        if m:
            percent = int(m.group("number"))
            self.link.setChecked(False)
            return self.seconds * (percent / 100.0)

    def quantity_edited(self):
        text = self.quantity_field.text()
        new = self.percentile_quantity(text) or LogDb.parse_duration(text)
        if new is None:
            if self.link.isChecked() or self.seconds is None:
                new = self.start_end_seconds
            else:
                new = self.seconds
        if self.link.isChecked() or new > self.start_end_seconds:
            self.end.setDateTime(
                self.start.dateTime().toPyDateTime() + datetime.timedelta(seconds=new)
            )
        self.seconds = new
        self.quantity_field.setText(LogDb.format_duration(new))


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


class PreferencesDialog(widgets.QDialog):
    def __init__(self, parent=None):
        super(PreferencesDialog, self).__init__(parent)
        self.setWindowTitle("Preferences")
        # Widgets
        bbox = widgets.QDialogButtonBox(
            widgets.QDialogButtonBox.StandardButton.Ok | widgets.QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        # Layout
        main = widgets.QVBoxLayout(self)
        main.addWidget(bbox)
        self.setLayout(main)
        # Connections
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)

    def accept(self):
        # settings = core.QSettings(ORG_NAME,APP_NAME)
        super(PreferencesDialog, self).accept()


class RenameDialog(widgets.QDialog):
    def __init__(self, database, name="", parent=None):
        super(RenameDialog, self).__init__(parent)
        self.setWindowTitle("Rename Selection")
        # Widgets
        bbox = widgets.QDialogButtonBox(
            widgets.QDialogButtonBox.StandardButton.Ok | widgets.QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        self.activity = widgets.QLineEdit(self)
        if self.activity:
            self.activity.setText(name)
            self.activity.setSelection(len(name), 0 - len(name))
        self._activity_list = core.QStringListModel(database.activities())
        activity_completer = widgets.QCompleter(self._activity_list, self)
        activity_completer.setCompletionMode(widgets.QCompleter.CompletionMode.PopupCompletion)
        self.activity.setCompleter(activity_completer)
        activity_label = widgets.QLabel("Activity:", self)
        activity_label.setBuddy(self.activity)
        self.apply_cap = widgets.QCheckBox("Apply capitalization?", self)
        self.apply_cap.setChecked(False)
        # Layout
        main = widgets.QVBoxLayout(self)
        entry_bar = widgets.QHBoxLayout()
        entry_bar.addWidget(activity_label)
        entry_bar.addWidget(self.activity)
        main.addLayout(entry_bar)
        main.addWidget(self.apply_cap)
        main.addWidget(bbox)
        self.setLayout(main)
        # Connections
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        core.QTimer.singleShot(0, partial(self.activity.setFocus, Qt.FocusPolicy.OtherFocusReason))


def run(interactive=False):
    """
    Initializes the main window with the most recent database.
    If the drop_when_finished is True, this function will block until the main
    window is closed, and will call sys.exit, to boot.
    """
    app = widgets.QApplication.instance() or widgets.QApplication(sys.argv)
    core.QLocale.setDefault(
        core.QLocale(core.QLocale.Language.English, core.QLocale.Country.UnitedStates)
    )
    if app is None:
        app = widgets.QApplication(sys.argv)
    if platform.system() == "Windows" and platform.release() in "7":
        app_id = ".".join([ORG_NAME, APP_NAME])
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    app.setWindowIcon(get_application_icon())
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    configure_matplotlib()
    w = MainWindow()
    print("Opening database: {0}".format(w.current_db))
    w.show()
    w.raise_()
    if interactive:
        return w
    else:
        sys.exit(app.exec_())


def get_database():
    """
    Return a LogDb instance based on the current user's application storage
    location.
    """
    # This can't be in the helper module because it creates circular imports.
    # So it's here.
    app = widgets.QApplication.instance() or widgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app_dir = core.QStandardPaths.writableLocation(core.QStandardPaths.StandardLocation.AppDataLocation)
    filename = os.path.join(app_dir, "user_data.sqlite")
    return LogDb(filename)


if __name__ == "__main__":
    run(interactive=False)
