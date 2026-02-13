from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


class ImageViewer(QtWidgets.QScrollArea):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = QtWidgets.QLabel("No image")
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.setWidget(self.label)
        self.setWidgetResizable(True)

    def load_image(self, path: Path) -> None:
        if not path.exists():
            self.label.setText("No image")
            self.label.setPixmap(QtGui.QPixmap())
            return
        pix = QtGui.QPixmap(str(path))
        if pix.isNull():
            self.label.setText(f"Unable to load {path.name}")
            return
        self.label.setPixmap(pix)
