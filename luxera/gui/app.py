from __future__ import annotations

from PySide6 import QtWidgets

from luxera.gui.workspace import LuxeraWorkspaceWindow


def run() -> int:
    app = QtWidgets.QApplication([])
    win = LuxeraWorkspaceWindow()
    win.show()
    return int(app.exec())
