from __future__ import annotations

from typing import Tuple


def _load_qt() -> Tuple[object, object, object, object, object, str]:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets

        return QtCore, QtGui, QtWidgets, QtCore.Signal, QtCore.Slot, "PySide6"
    except ImportError:
        from PyQt5 import QtCore, QtGui, QtWidgets

        return QtCore, QtGui, QtWidgets, QtCore.pyqtSignal, QtCore.pyqtSlot, "PyQt5"


QtCore, QtGui, QtWidgets, Signal, Slot, QT_LIB = _load_qt()

__all__ = ["QtCore", "QtGui", "QtWidgets", "Signal", "Slot", "QT_LIB"]
