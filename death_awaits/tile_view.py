from collections import namedtuple

import PyQt5.QtWidgets as Widgets
import PyQt5.QtGui as Gui
import PyQt5.QtCore as Core
from PyQt5.QtCore import Qt

from death_awaits.db import LogDb

chunk = namedtuple(
    'Chunk',
    ('name', 'proportion', 'color', '')
)



class QuantizedModelBase(Core.QAbstractItemModel):
    """
    This model will digest the contents of a LogDb into a series of
    quantized chunks.
    For a given model index, the row is the chunk offset from the beginning of
    the series, and the column index is an activity.
    """
    hourly = 0
    daily = 1
    weekly = 2

    def __init__(
            self, activity=None, start=None, end=None,
            categories=12, chunk_size=None, show_other=True, parent=None):
        super(QuantizedModelBase, self).__init__(parent=parent)
        pass

    def rowCount(self, parent=None):
        pass

    def columnCount(self, parent=None):
        pass

    def data(self, index, role=Qt.DisplayRole):
        pass

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        pass



class LinearModel(QuantizedModelBase):
    pass


class CyclicModel(QuantizedModelBase):
    pass
