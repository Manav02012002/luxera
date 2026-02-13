from __future__ import annotations

from PySide6 import QtWidgets


class CopilotPanel(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        v = QtWidgets.QVBoxLayout(self)

        self.input = QtWidgets.QLineEdit()
        self.input.setPlaceholderText("Ask Luxera Copilot: /place panels target 500 lux")
        self.run = QtWidgets.QPushButton("Plan / Preview")
        self.apply_only = QtWidgets.QPushButton("Apply Diff (Approve)")
        self.run_only = QtWidgets.QPushButton("Run Job (Approve)")
        self.apply_run = QtWidgets.QPushButton("Apply + Run (Approve)")
        self.undo_assistant = QtWidgets.QPushButton("Undo Assistant Change")
        self.redo_assistant = QtWidgets.QPushButton("Redo Assistant Change")

        self.plan_view = QtWidgets.QPlainTextEdit()
        self.plan_view.setReadOnly(True)
        self.plan_view.setPlaceholderText("Plan will appear here.")

        self.diff = QtWidgets.QListWidget()
        self.diff.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.diff_details = QtWidgets.QPlainTextEdit()
        self.diff_details.setReadOnly(True)
        self.diff_details.setPlaceholderText("Selected diff operation details.")
        self.select_all = QtWidgets.QPushButton("Select All")
        self.select_none = QtWidgets.QPushButton("Select None")

        self.output = QtWidgets.QPlainTextEdit()
        self.output.setReadOnly(True)
        self.audit = QtWidgets.QPlainTextEdit()
        self.audit.setReadOnly(True)
        self.audit.setPlaceholderText("Latest audit events will appear here.")

        v.addWidget(self.input)
        v.addWidget(self.run)
        v.addWidget(self.apply_only)
        v.addWidget(self.run_only)
        v.addWidget(self.apply_run)
        v.addWidget(self.undo_assistant)
        v.addWidget(self.redo_assistant)
        v.addWidget(QtWidgets.QLabel("Plan"))
        v.addWidget(self.plan_view)
        v.addWidget(QtWidgets.QLabel("Diff Preview (check approved changes)"))
        v.addWidget(self.diff)
        v.addWidget(self.diff_details)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.select_all)
        row.addWidget(self.select_none)
        v.addLayout(row)
        v.addWidget(QtWidgets.QLabel("Run / Artifact Output"))
        v.addWidget(self.output)
        v.addWidget(QtWidgets.QLabel("Audit Log"))
        v.addWidget(self.audit)
