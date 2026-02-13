from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from luxera.project.schema import Project


class VariantsPanel(QtWidgets.QWidget):
    compare_requested = QtCore.Signal(str, list, str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        root = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        self.job = QtWidgets.QComboBox()
        self.baseline = QtWidgets.QComboBox()
        row.addWidget(QtWidgets.QLabel("Job"))
        row.addWidget(self.job, 1)
        row.addWidget(QtWidgets.QLabel("Baseline"))
        row.addWidget(self.baseline, 1)
        root.addLayout(row)

        self.variants = QtWidgets.QListWidget()
        self.variants.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        root.addWidget(self.variants, 1)

        actions = QtWidgets.QHBoxLayout()
        self.select_all = QtWidgets.QPushButton("Select All")
        self.select_none = QtWidgets.QPushButton("Select None")
        self.compare = QtWidgets.QPushButton("Compare Variants")
        actions.addWidget(self.select_all)
        actions.addWidget(self.select_none)
        actions.addStretch(1)
        actions.addWidget(self.compare)
        root.addLayout(actions)

        self.output = QtWidgets.QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Compare output")
        root.addWidget(self.output, 1)

        self.select_all.clicked.connect(lambda: self._set_all(True))
        self.select_none.clicked.connect(lambda: self._set_all(False))
        self.compare.clicked.connect(self._emit_compare)

    def set_project(self, project: Project | None) -> None:
        self.job.clear()
        self.baseline.clear()
        self.variants.clear()
        if project is None:
            return
        for j in project.jobs:
            self.job.addItem(j.id, j.id)
        for v in project.variants:
            self.baseline.addItem(v.name, v.id)
            item = QtWidgets.QListWidgetItem(v.name)
            item.setData(QtCore.Qt.UserRole, v.id)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
            self.variants.addItem(item)

    def _set_all(self, checked: bool) -> None:
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        for i in range(self.variants.count()):
            self.variants.item(i).setCheckState(state)

    def _emit_compare(self) -> None:
        job_id = str(self.job.currentData() or "")
        baseline = str(self.baseline.currentData() or "")
        selected: list[str] = []
        for i in range(self.variants.count()):
            item = self.variants.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                selected.append(str(item.data(QtCore.Qt.UserRole)))
        if not job_id or len(selected) < 2:
            self.output.setPlainText("Select a job and at least two variants.")
            return
        if baseline and baseline not in selected:
            selected.append(baseline)
        self.compare_requested.emit(job_id, selected, baseline)
