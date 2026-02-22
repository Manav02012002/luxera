from __future__ import annotations

import json
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from luxera.database.library_manager import index_folder, search_db


class _LibraryTable(QtWidgets.QTableWidget):
    MIME_TYPE = "application/x-luxera-library-entry"

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setColumnCount(7)
        self.setHorizontalHeaderLabels(["Manufacturer", "Name", "Lumens", "CCT", "Beam", "Type", "Path"])
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)

    def startDrag(self, supported_actions: QtCore.Qt.DropActions) -> None:  # type: ignore[override]
        row = self.currentRow()
        if row < 0:
            return
        payload = self.item(row, 0).data(QtCore.Qt.UserRole) if self.item(row, 0) else None
        if not isinstance(payload, dict):
            return
        mime = QtCore.QMimeData()
        mime.setData(self.MIME_TYPE, json.dumps(payload, sort_keys=True).encode("utf-8"))
        drag = QtGui.QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supported_actions)


class PhotometryLibraryWidget(QtWidgets.QWidget):
    status_message = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._db_path: Path | None = None
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        row1 = QtWidgets.QHBoxLayout()
        self.db_path = QtWidgets.QLineEdit()
        self.db_path.setPlaceholderText("Library DB path")
        self.pick_db = QtWidgets.QPushButton("Open DB...")
        row1.addWidget(self.db_path, 1)
        row1.addWidget(self.pick_db)
        root.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        self.index_folder = QtWidgets.QLineEdit()
        self.index_folder.setPlaceholderText("Folder to index")
        self.pick_folder = QtWidgets.QPushButton("Folder...")
        self.index_btn = QtWidgets.QPushButton("Index")
        row2.addWidget(self.index_folder, 1)
        row2.addWidget(self.pick_folder)
        row2.addWidget(self.index_btn)
        root.addLayout(row2)

        row3 = QtWidgets.QHBoxLayout()
        self.query = QtWidgets.QLineEdit()
        self.query.setPlaceholderText("Search query: manufacturer:acme lumens>=1000 cct=4000 beam<80")
        self.search_btn = QtWidgets.QPushButton("Search")
        row3.addWidget(self.query, 1)
        row3.addWidget(self.search_btn)
        root.addLayout(row3)

        self.table = _LibraryTable()
        root.addWidget(self.table, 1)

        self.help = QtWidgets.QLabel("Drag a row into 2D view to place luminaire at drop point.")
        root.addWidget(self.help)

        self.pick_db.clicked.connect(self._pick_db)
        self.pick_folder.clicked.connect(self._pick_folder)
        self.index_btn.clicked.connect(self._index)
        self.search_btn.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)

    @property
    def db_file(self) -> Path | None:
        raw = self.db_path.text().strip()
        if not raw:
            return self._db_path
        return Path(raw).expanduser().resolve()

    def _pick_db(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Library DB", "", "SQLite (*.db *.sqlite *.sqlite3)")
        if not path:
            return
        self._db_path = Path(path).expanduser().resolve()
        self.db_path.setText(str(self._db_path))
        self.search()

    def _pick_folder(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose Folder To Index")
        if path:
            self.index_folder.setText(path)

    def _index(self) -> None:
        folder = self.index_folder.text().strip()
        db = self.db_file
        if not folder or db is None:
            self.status_message.emit("Provide both index folder and DB path.")
            return
        try:
            stats = index_folder(Path(folder), db)
        except Exception as exc:
            self.status_message.emit(f"Library index failed: {exc}")
            return
        self.status_message.emit(
            f"Library indexed: {stats.indexed_files} file(s), parse errors={stats.parse_errors}, db={stats.db_path}"
        )
        self.search()

    def search(self) -> None:
        db = self.db_file
        if db is None:
            self.status_message.emit("Set a DB path to search.")
            return
        try:
            rows = search_db(db, self.query.text().strip(), limit=500)
        except Exception as exc:
            self.status_message.emit(f"Library search failed: {exc}")
            return
        self._populate(rows)
        self.status_message.emit(f"Library results: {len(rows)}")

    def _populate(self, rows) -> None:  # noqa: ANN001
        self.table.setRowCount(0)
        for row in rows:
            payload = row.to_dict()
            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [
                payload["manufacturer"] or "",
                payload["name"] or payload["file_name"] or "",
                "" if payload["lumens"] is None else f"{float(payload['lumens']):.2f}",
                "" if payload["cct"] is None else f"{float(payload['cct']):.1f}",
                "" if payload["beam_angle"] is None else f"{float(payload['beam_angle']):.1f}",
                payload["file_ext"].upper(),
                payload["file_path"],
            ]
            for c, val in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(val))
                if c == 0:
                    item.setData(QtCore.Qt.UserRole, payload)
                self.table.setItem(r, c, item)

