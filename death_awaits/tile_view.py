import PyQt5.QtWidgets as Widgets
import PyQt5.QtGui as Gui
import PyQt5.QtCore as Core
from PyQt5.QtCore import Qt

from death_awaits.db import LogDb


class AggregateModel(Core.QAbstractItemModel):
    hourly = 0
    daily = 1

    def __init__(self, parent=None):
        super(AggregateModel, self).__init__(parent=parent)

    def update_cache(
            self, activity=None, start=None, end=None,
            categories=12, chunk_size=hourly, show_other=True
    ):
        pass

    def rowCount(self, parent=None):
        pass

    def columnCount(self, parent=None):
        pass

    def data(self, index, role=Qt.DisplayRole):
        pass

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        pass
