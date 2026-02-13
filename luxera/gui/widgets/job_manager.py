from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from luxera.project.schema import Project


class JobManagerWidget(QtWidgets.QWidget):
    run_requested = QtCore.Signal(str)
    cancel_requested = QtCore.Signal(str)
    view_requested = QtCore.Signal(str)
    export_requested = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Job", "Type", "Status", "Last Run", "Job Hash"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.table, 1)

        row = QtWidgets.QHBoxLayout()
        self.run = QtWidgets.QPushButton("Run")
        self.cancel = QtWidgets.QPushButton("Cancel")
        self.view = QtWidgets.QPushButton("View Results")
        self.export = QtWidgets.QPushButton("Export Report")
        row.addWidget(self.run)
        row.addWidget(self.cancel)
        row.addWidget(self.view)
        row.addWidget(self.export)
        row.addStretch(1)
        layout.addLayout(row)

        self.run.clicked.connect(self._run)
        self.cancel.clicked.connect(self._cancel)
        self.view.clicked.connect(self._view)
        self.export.clicked.connect(self._export)

    def set_project(self, project: Project | None) -> None:
        self.table.setRowCount(0)
        if project is None:
            return
        result_by_job = {r.job_id: r for r in project.results}
        for job in project.jobs:
            row = self.table.rowCount()
            self.table.insertRow(row)
            ref = result_by_job.get(job.id)
            status = "completed" if ref else "not run"
            last_run = ref.result_dir if ref else "-"
            job_hash = ref.job_hash if ref else "-"
            cells = [job.id, str(job.type), status, last_run, job_hash]
            for col, value in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(value)
                if col == 0:
                    item.setData(QtCore.Qt.UserRole, job.id)
                self.table.setItem(row, col, item)

    def _selected_job_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        return str(item.data(QtCore.Qt.UserRole) or item.text())

    def _run(self) -> None:
        job_id = self._selected_job_id()
        if job_id:
            self.run_requested.emit(job_id)

    def _cancel(self) -> None:
        job_id = self._selected_job_id()
        if job_id:
            self.cancel_requested.emit(job_id)

    def _view(self) -> None:
        job_id = self._selected_job_id()
        if job_id:
            self.view_requested.emit(job_id)

    def _export(self) -> None:
        job_id = self._selected_job_id()
        if job_id:
            self.export_requested.emit(job_id)
