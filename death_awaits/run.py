import sys
import platform
import ctypes

import PyQt5.QtWidgets as widgets

from death_awaits.helper import get_application_icon, configure_matplotlib
from death_awaits.main import MainWindow

ORG_NAME = "anagogical.net"
APP_NAME = "Death Awaits"

if __name__ == "__main__":
    app = widgets.QApplication.instance()
    if app is None:
        app = widgets.QApplication(sys.argv)
    if platform.system() == 'Windows' and platform.release() == '7':
        app_id = '.'.join([ORG_NAME, APP_NAME])
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    app.setWindowIcon(get_application_icon())
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    configure_matplotlib()
    w = MainWindow()
    w.show()
    w.raise_()
    sys.exit(app.exec_())
