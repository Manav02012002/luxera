from __future__ import annotations

import traceback
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from luxera.parser.pipeline import LuxeraViewResult, parse_and_analyse_ies
from luxera.plotting.plots import save_default_plots, PlotPaths
from luxera.export.pdf_report import build_pdf_report


def _fmt(val) -> str:
    if val is None:
        return "-"
    if isinstance(val, float):
        return f"{val:g}"
    return str(val)


class LuxeraMainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Luxera View")
        self.resize(1100, 750)

        self.current_file: Optional[Path] = None
        self.current_result: Optional[LuxeraViewResult] = None
        self.current_plots: Optional[PlotPaths] = None

        self._build_ui()
        self._wire_actions()

        # Enable drag & drop
        self.setAcceptDrops(True)
        self.status.showMessage("Ready (tip: drag & drop a .ies file here)", 5000)

    # ---------- Drag & Drop ----------
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        md = event.mimeData()
        if md.hasUrls():
            urls = md.urls()
            if any(self._is_ies_url(u) for u in urls):
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        # Accept move if it contains an .ies URL
        md = event.mimeData()
        if md.hasUrls() and any(self._is_ies_url(u) for u in md.urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        md = event.mimeData()
        if not md.hasUrls():
            event.ignore()
            return

        # Pick first .ies file from dropped URLs
        for url in md.urls():
            if not self._is_ies_url(url):
                continue
            local = url.toLocalFile()
            if not local:
                continue
            p = Path(local)
            if p.exists() and p.is_file():
                self.load_ies(p)
                event.acceptProposedAction()
                return

        self.status.showMessage("Drop ignored: please drop a local .ies file", 5000)
        event.ignore()

    @staticmethod
    def _is_ies_url(url: QtCore.QUrl) -> bool:
        # Accept local files only; require .ies extension (case-insensitive)
        if not url.isLocalFile():
            return False
        p = url.toLocalFile()
        if not p:
            return False
        return p.lower().endswith(".ies")

    # ---------- UI ----------
    def _build_ui(self) -> None:
        # Menu
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        self.act_open = QtGui.QAction("&Open IES…", self)
        self.act_open.setShortcut(QtGui.QKeySequence.Open)
        file_menu.addAction(self.act_open)

        self.act_export_pdf = QtGui.QAction("&Export PDF…", self)
        self.act_export_pdf.setShortcut("Ctrl+E")
        file_menu.addAction(self.act_export_pdf)

        file_menu.addSeparator()

        self.act_quit = QtGui.QAction("&Quit", self)
        self.act_quit.setShortcut(QtGui.QKeySequence.Quit)
        file_menu.addAction(self.act_quit)

        # Central layout
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Left: info panels
        left = QtWidgets.QVBoxLayout()
        left.setSpacing(10)

        self.lbl_file = QtWidgets.QLabel("No file loaded.\n(Drag & drop a .ies file here)")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        left.addWidget(self._card("Loaded file", self.lbl_file))

        self.tbl_meta = QtWidgets.QTableWidget(0, 2)
        self.tbl_meta.setHorizontalHeaderLabels(["Field", "Value"])
        self.tbl_meta.horizontalHeader().setStretchLastSection(True)
        self.tbl_meta.verticalHeader().setVisible(False)
        self.tbl_meta.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tbl_meta.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)

        left.addWidget(self._card("Metadata", self.tbl_meta))

        self.tbl_derived = QtWidgets.QTableWidget(0, 2)
        self.tbl_derived.setHorizontalHeaderLabels(["Metric", "Value"])
        self.tbl_derived.horizontalHeader().setStretchLastSection(True)
        self.tbl_derived.verticalHeader().setVisible(False)
        self.tbl_derived.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tbl_derived.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)

        left.addWidget(self._card("Derived metrics", self.tbl_derived))

        self.tbl_findings = QtWidgets.QTableWidget(0, 4)
        self.tbl_findings.setHorizontalHeaderLabels(["Severity", "Rule", "Title", "Message"])
        self.tbl_findings.horizontalHeader().setStretchLastSection(True)
        self.tbl_findings.verticalHeader().setVisible(False)
        self.tbl_findings.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tbl_findings.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tbl_findings.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        left.addWidget(self._card("Validation findings", self.tbl_findings))

        left_wrap = QtWidgets.QWidget()
        left_wrap.setLayout(left)

        # Right: plot previews
        right = QtWidgets.QVBoxLayout()
        right.setSpacing(10)

        self.img_intensity = QtWidgets.QLabel("No plot yet.\n(Open or drop an IES file.)")
        self.img_intensity.setAlignment(QtCore.Qt.AlignCenter)
        self.img_intensity.setMinimumHeight(250)
        self.img_intensity.setStyleSheet("QLabel { background: #f7f7f7; border: 1px solid #ddd; }")
        right.addWidget(self._card("Intensity curves", self.img_intensity))

        self.img_polar = QtWidgets.QLabel("No plot yet.\n(Open or drop an IES file.)")
        self.img_polar.setAlignment(QtCore.Qt.AlignCenter)
        self.img_polar.setMinimumHeight(250)
        self.img_polar.setStyleSheet("QLabel { background: #f7f7f7; border: 1px solid #ddd; }")
        right.addWidget(self._card("Polar plot", self.img_polar))

        right_wrap = QtWidgets.QWidget()
        right_wrap.setLayout(right)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(left_wrap)
        splitter.addWidget(right_wrap)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter)

        # Status bar
        self.status = self.statusBar()
        self.status.showMessage("Ready")

        # Disable export until file loaded
        self.act_export_pdf.setEnabled(False)

    def _card(self, title: str, widget: QtWidgets.QWidget) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox(title)
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(widget)
        return box

    def _wire_actions(self) -> None:
        self.act_open.triggered.connect(self.open_file_dialog)
        self.act_export_pdf.triggered.connect(self.export_pdf_dialog)
        self.act_quit.triggered.connect(self.close)

    # ---------- Actions ----------
    def open_file_dialog(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open IES file",
            str(Path.cwd()),
            "IES files (*.ies *.IES);;All files (*.*)",
        )
        if not path:
            return
        self.load_ies(Path(path))

    def export_pdf_dialog(self) -> None:
        if self.current_file is None or self.current_result is None or self.current_plots is None:
            return

        default_name = self.current_file.with_suffix("").name + "_report.pdf"
        out_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export PDF report",
            str((Path.cwd() / default_name).resolve()),
            "PDF (*.pdf)",
        )
        if not out_path:
            return

        try:
            build_pdf_report(self.current_result, self.current_plots, Path(out_path), source_file=self.current_file)
            self.status.showMessage(f"Saved PDF: {out_path}", 6000)
        except Exception as e:
            self._show_error("PDF export failed", e)

    # ---------- Core ----------
    def load_ies(self, path: Path) -> None:
        try:
            if path.suffix.lower() != ".ies":
                raise RuntimeError("Not an .ies file")

            text = path.read_text(encoding="utf-8", errors="replace")
            res = parse_and_analyse_ies(text)

            # Require photometry blocks for GUI plots/report
            if res.doc.photometry is None or res.doc.angles is None or res.doc.candela is None:
                raise RuntimeError("Failed to parse photometry/angles/candela from IES file.")

            # Save plots into a per-file cache folder under out/gui_cache/
            cache_dir = (Path.cwd() / "out" / "gui_cache" / path.with_suffix("").name).resolve()
            plots = save_default_plots(res.doc, cache_dir, stem="view")

            self.current_file = path
            self.current_result = res
            self.current_plots = plots

            self._render_all()
            self.act_export_pdf.setEnabled(True)

            self.status.showMessage("Loaded and analysed successfully", 4000)

        except Exception as e:
            self._show_error("Failed to load IES", e)

    def _render_all(self) -> None:
        assert self.current_file is not None
        assert self.current_result is not None
        assert self.current_plots is not None

        self.lbl_file.setText(str(self.current_file))

        self._fill_metadata_table()
        self._fill_derived_table()
        self._fill_findings_table()
        self._set_image(self.img_intensity, self.current_plots.intensity_png)
        self._set_image(self.img_polar, self.current_plots.polar_png)

    # ---------- Rendering helpers ----------
    def _fill_metadata_table(self) -> None:
        doc = self.current_result.doc  # type: ignore[union-attr]
        ph = doc.photometry
        ang = doc.angles

        def first(key: str) -> str:
            vals = doc.keywords.get(key, [])
            return vals[0] if vals else "-"

        rows = [
            ("Standard", doc.standard_line or "-"),
            ("TILT", doc.tilt_line or "-"),
            ("Manufacturer", first("MANUFAC")),
            ("Luminaire Catalog", first("LUMCAT")),
            ("Luminaire", first("LUMINAIRE")),
            ("Date", first("DATE")),
        ]
        if ph and ang:
            units = "m" if ph.units_type == 2 else "ft"
            rows += [
                ("# Lamps", _fmt(ph.num_lamps)),
                ("Lumens/lamp", _fmt(ph.lumens_per_lamp)),
                ("Candela multiplier", _fmt(ph.candela_multiplier)),
                ("Units", units),
                ("Width", f"{_fmt(ph.width)} {units}"),
                ("Length", f"{_fmt(ph.length)} {units}"),
                ("Height", f"{_fmt(ph.height)} {units}"),
                ("Vertical range", f"{ang.vertical_deg[0]:g}° → {ang.vertical_deg[-1]:g}°"),
                ("Horizontal range", f"{ang.horizontal_deg[0]:g}° → {ang.horizontal_deg[-1]:g}°"),
            ]

        self._set_table_2col(self.tbl_meta, rows)

    def _fill_derived_table(self) -> None:
        res = self.current_result  # type: ignore[assignment]
        rows = []
        if res.derived is None:
            rows = [("Derived", "Unavailable")]
        else:
            dm = res.derived
            rows = [
                ("Peak candela", _fmt(dm.peak_candela)),
                ("Peak location (H,V)", f"({dm.peak_location[0]:g}°, {dm.peak_location[1]:g}°)"),
                ("Symmetry inferred", dm.symmetry_inferred),
                ("Candela min", _fmt(dm.candela_stats.get("min"))),
                ("Candela max", _fmt(dm.candela_stats.get("max"))),
                ("Candela mean", _fmt(dm.candela_stats.get("mean"))),
                ("Candela p95", _fmt(dm.candela_stats.get("p95"))),
            ]
        self._set_table_2col(self.tbl_derived, rows)

    def _fill_findings_table(self) -> None:
        res = self.current_result  # type: ignore[assignment]
        self.tbl_findings.setRowCount(0)

        if res.report is None or not res.report.findings:
            self.tbl_findings.setRowCount(1)
            self._set_cell(self.tbl_findings, 0, 0, "INFO")
            self._set_cell(self.tbl_findings, 0, 1, "-")
            self._set_cell(self.tbl_findings, 0, 2, "No findings")
            self._set_cell(self.tbl_findings, 0, 3, "No validation findings were produced.")
            self.tbl_findings.resizeColumnsToContents()
            return

        for f in res.report.findings:
            r = self.tbl_findings.rowCount()
            self.tbl_findings.insertRow(r)
            self._set_cell(self.tbl_findings, r, 0, f.severity)
            self._set_cell(self.tbl_findings, r, 1, f.id)
            self._set_cell(self.tbl_findings, r, 2, f.title)
            self._set_cell(self.tbl_findings, r, 3, f.message)

        self.tbl_findings.resizeColumnsToContents()
        self.tbl_findings.horizontalHeader().setStretchLastSection(True)

    def _set_table_2col(self, table: QtWidgets.QTableWidget, rows) -> None:
        table.setRowCount(0)
        for (k, v) in rows:
            r = table.rowCount()
            table.insertRow(r)
            self._set_cell(table, r, 0, str(k))
            self._set_cell(table, r, 1, str(v))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)

    def _set_cell(self, table: QtWidgets.QTableWidget, r: int, c: int, text: str) -> None:
        item = QtWidgets.QTableWidgetItem(text)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        table.setItem(r, c, item)

    def _set_image(self, label: QtWidgets.QLabel, path: Path) -> None:
        pix = QtGui.QPixmap(str(path))
        if pix.isNull():
            label.setText(f"Failed to load image:\n{path}")
            return
        w = max(label.width(), 500)
        scaled = pix.scaledToWidth(w, QtCore.Qt.SmoothTransformation)
        label.setPixmap(scaled)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.current_plots is not None:
            self._set_image(self.img_intensity, self.current_plots.intensity_png)
            self._set_image(self.img_polar, self.current_plots.polar_png)

    # ---------- Error handling ----------
    def _show_error(self, title: str, exc: Exception) -> None:
        msg = QtWidgets.QMessageBox(self)
        msg.setIcon(QtWidgets.QMessageBox.Critical)
        msg.setWindowTitle(title)
        msg.setText(str(exc))
        msg.setDetailedText(traceback.format_exc())
        msg.exec()
        self.status.showMessage(title, 6000)


def run() -> int:
    app = QtWidgets.QApplication([])
    w = LuxeraMainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
