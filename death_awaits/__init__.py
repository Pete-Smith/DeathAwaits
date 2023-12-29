import os

# This environment variable is used by matplotlib's QT backend
os.environ["QT_API"] = "pyqt"


# With Python 2.x we need to specify PyQt's API version 2 before we do
# anything.
# import sip
# API_NAMES = [
#    "QDate", "QDateTime", "QString",
#    "QTextStream", "QTime", "QUrl",
#    "QVariant"
# ]
# API_VERSION = 2
# for name in API_NAMES:
#    sip.setapi(name, API_VERSION)
