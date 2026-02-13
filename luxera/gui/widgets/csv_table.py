from __future__ import annotations

import csv
from pathlib import Path

from PySide6 import QtWidgets


class CsvTableWidget(QtWidgets.QTableWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(0, 0, parent)
        self.horizontalHeader().setStretchLastSection(True)
        self.setAlternatingRowColors(True)

    def load_csv(self, path: Path) -> None:
        self.setRowCount(0)
        self.setColumnCount(0)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        if not rows:
            return
        headers = rows[0]
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        for row_data in rows[1:]:
            row = self.rowCount()
            self.insertRow(row)
            for col, value in enumerate(row_data):
                self.setItem(row, col, QtWidgets.QTableWidgetItem(value))
