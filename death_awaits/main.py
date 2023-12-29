import os
import sys
import datetime
from functools import partial
import shutil
import platform
import ctypes

import PyQt6.QtGui as gui
import PyQt6.QtCore as core
import PyQt6.QtWidgets as widgets
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
import matplotlib.pyplot as plt

from death_awaits.db import LogDb
from death_awaits.helper import (
    get_application_icon,
    get_icon,
    stringify_datetime,
    configure_matplotlib,
)
from death_awaits.plots import PLOTTERS
from death_awaits.palettes import get_application_palette
from death_awaits.log.view import LogPanel
from death_awaits.filter.view import FilterPanel

ORG_NAME = "anagogical.net"
APP_NAME = "Death Awaits"

DEBUG = True


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
        self.list_panel = LogPanel(self._db, self)
        self.graph_panel = GraphPanel(self._db, self)
        self.tabs = widgets.QTabWidget()
        # self.tabs.setTabPosition(widgets.QTabWidget.TabPosition.West)
        self.tabs.addTab(self.list_panel, get_icon("list.png"), "Log")
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
        if (
            gui.QGuiApplication.queryKeyboardModifiers()
            == Qt.KeyboardModifier.ControlModifier
        ):
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


# TODO: Currently empty. Shouldn't this be a panel?
class PreferencesDialog(widgets.QDialog):
    def __init__(self, parent=None):
        super(PreferencesDialog, self).__init__(parent)
        self.setWindowTitle("Preferences")
        # Widgets
        bbox = widgets.QDialogButtonBox(
            widgets.QDialogButtonBox.StandardButton.Ok
            | widgets.QDialogButtonBox.StandardButton.Cancel,
            parent=self,
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


def run(interactive=False):
    """
    Initializes the main window with the most recent database.
    If the drop_when_finished is True, this function will block until the main
    window is closed, and will call sys.exit, to boot.
    """
    app = widgets.QApplication.instance() or widgets.QApplication(sys.argv)
    # TODO: This is a temporary setting while I'm the only user.
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
    app_dir = core.QStandardPaths.writableLocation(
        core.QStandardPaths.StandardLocation.AppDataLocation
    )
    filename = os.path.join(app_dir, "user_data.sqlite")
    return LogDb(filename)


if __name__ == "__main__":
    run(interactive=False)
