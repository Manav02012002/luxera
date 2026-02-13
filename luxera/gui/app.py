from __future__ import annotations

from PySide6 import QtWidgets

from luxera.gui.theme import apply_theme
from luxera.gui.workspace import LuxeraWorkspaceWindow


def run() -> int:
    app = QtWidgets.QApplication([])
    apply_theme(app)
    win = LuxeraWorkspaceWindow()
    win.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(run())
