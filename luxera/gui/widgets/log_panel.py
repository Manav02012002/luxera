from __future__ import annotations

from PySide6 import QtWidgets


class LogPanel(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Run and assistant logs will appear here.")
        layout.addWidget(self.log)

    def append(self, text: str) -> None:
        if not text:
            return
        self.log.appendPlainText(text)

    def set_text(self, text: str) -> None:
        self.log.setPlainText(text)
