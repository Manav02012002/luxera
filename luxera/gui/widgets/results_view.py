from __future__ import annotations

import json
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from luxera.gui.widgets.csv_table import CsvTableWidget
from luxera.gui.widgets.image_viewer import ImageViewer
from luxera.project.schema import Project


class ResultsView(QtWidgets.QWidget):
    open_report_requested = QtCore.Signal(str)
    open_bundle_requested = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        root = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        self.result_selector = QtWidgets.QComboBox()
        self.result_selector.currentIndexChanged.connect(self._load_current)
        top.addWidget(QtWidgets.QLabel("Result"))
        top.addWidget(self.result_selector, 1)
        self.open_report = QtWidgets.QPushButton("Open Report")
        self.open_bundle = QtWidgets.QPushButton("Open Audit Bundle")
        self.open_report.clicked.connect(self._open_report)
        self.open_bundle.clicked.connect(self._open_bundle)
        top.addWidget(self.open_report)
        top.addWidget(self.open_bundle)
        root.addLayout(top)

        self.tabs = QtWidgets.QTabWidget()
        self.heatmap = ImageViewer()
        self.table = CsvTableWidget()
        self.summary = QtWidgets.QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.agent_log = QtWidgets.QPlainTextEdit()
        self.agent_log.setReadOnly(True)

        self.tabs.addTab(self.heatmap, "Heatmap")
        self.tabs.addTab(self.table, "Table")
        self.tabs.addTab(self.summary, "Summary")
        self.tabs.addTab(self.agent_log, "Agent Session")
        root.addWidget(self.tabs, 1)

        self._project: Project | None = None

    def set_project(self, project: Project | None) -> None:
        self._project = project
        self.result_selector.blockSignals(True)
        self.result_selector.clear()
        if project is not None:
            for ref in project.results:
                self.result_selector.addItem(ref.job_id, ref.job_id)
        self.result_selector.blockSignals(False)
        self._load_current()

    def select_job(self, job_id: str) -> None:
        idx = self.result_selector.findData(job_id)
        if idx >= 0:
            self.result_selector.setCurrentIndex(idx)

    def _result_dir(self, job_id: str) -> Path | None:
        if self._project is None:
            return None
        ref = next((r for r in self._project.results if r.job_id == job_id), None)
        return Path(ref.result_dir) if ref else None

    def _load_current(self) -> None:
        if self._project is None or self.result_selector.count() == 0:
            self.summary.setPlainText("No results yet")
            self.agent_log.setPlainText("")
            return
        job_id = str(self.result_selector.currentData())
        result_dir = self._result_dir(job_id)
        if result_dir is None:
            return

        heatmap = next((p for p in [result_dir / "heatmap.png", result_dir / "grid_heatmap.png"] if p.exists()), None)
        if heatmap:
            self.heatmap.load_image(heatmap)

        csv_path = next((p for p in [result_dir / "grid.csv", result_dir / "grid_g1.csv"] if p.exists()), None)
        if csv_path:
            self.table.load_csv(csv_path)

        summary = {
            "job_id": job_id,
            "result_dir": str(result_dir),
            "files": sorted([p.name for p in result_dir.glob("*") if p.is_file()]),
        }
        summary_json = result_dir / "summary.json"
        if summary_json.exists():
            try:
                summary["summary"] = json.loads(summary_json.read_text(encoding="utf-8"))
            except Exception:
                summary["summary"] = "Invalid summary.json"
        self.summary.setPlainText(json.dumps(summary, indent=2, sort_keys=True))

        events = self._project.agent_history[-20:]
        lines = [json.dumps(e, sort_keys=True) for e in events]
        self.agent_log.setPlainText("\n".join(lines))

    def _open_report(self) -> None:
        if self.result_selector.count() == 0:
            return
        self.open_report_requested.emit(str(self.result_selector.currentData()))

    def _open_bundle(self) -> None:
        if self.result_selector.count() == 0:
            return
        self.open_bundle_requested.emit(str(self.result_selector.currentData()))
