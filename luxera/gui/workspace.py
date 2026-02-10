from __future__ import annotations

import uuid
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import (
    Project,
    PhotometryAsset,
    RoomSpec,
    LuminaireInstance,
    CalcGrid,
    JobSpec,
    TransformSpec,
    RotationSpec,
)
from luxera.project.presets import en12464_direct_job, en13032_radiosity_job
from luxera.runner import run_job
from luxera.export.report_model import build_en13032_report_model
from luxera.export.en13032_pdf import render_en13032_pdf
from luxera.export.en12464_report import build_en12464_report_model
from luxera.export.en12464_pdf import render_en12464_pdf
from luxera.core.hashing import sha256_file
from luxera.agent.runtime import AgentRuntime
from luxera.results.compare import compare_job_results


class LuxeraWorkspaceWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Luxera Workspace")
        self.resize(1200, 800)

        self.project_path: Optional[Path] = None
        self.project: Optional[Project] = None
        self.agent_runtime = AgentRuntime()
        self._copilot_preview_ops: Dict[str, Dict[str, Any]] = {}

        self._build_ui()
        self._wire_actions()

    def _build_ui(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        self.act_new = QtGui.QAction("&New Project…", self)
        self.act_open = QtGui.QAction("&Open Project…", self)
        self.act_save = QtGui.QAction("&Save", self)
        self.act_save_as = QtGui.QAction("Save &As…", self)
        self.act_quit = QtGui.QAction("&Quit", self)

        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_open)
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        add_menu = menubar.addMenu("&Add")
        self.act_add_photometry = QtGui.QAction("Photometry Asset…", self)
        self.act_add_room = QtGui.QAction("Room…", self)
        self.act_add_luminaire = QtGui.QAction("Luminaire…", self)
        self.act_add_grid = QtGui.QAction("Grid…", self)
        self.act_add_job = QtGui.QAction("Job…", self)
        add_menu.addAction(self.act_add_photometry)
        add_menu.addAction(self.act_add_room)
        add_menu.addAction(self.act_add_luminaire)
        add_menu.addAction(self.act_add_grid)
        add_menu.addAction(self.act_add_job)

        run_menu = menubar.addMenu("&Run")
        self.act_run_job = QtGui.QAction("Run Selected Job", self)
        self.act_compare_last_two = QtGui.QAction("Compare Last Two Results", self)
        run_menu.addAction(self.act_run_job)
        run_menu.addAction(self.act_compare_last_two)

        agent_menu = menubar.addMenu("&Agent")
        self.act_command_palette = QtGui.QAction("Command Palette…", self)
        self.act_command_palette.setShortcut(QtGui.QKeySequence("Ctrl+K"))
        agent_menu.addAction(self.act_command_palette)

        report_menu = menubar.addMenu("&Report")
        self.act_report_en12464 = QtGui.QAction("Export EN 12464 PDF…", self)
        self.act_report_en13032 = QtGui.QAction("Export EN 13032 PDF…", self)
        report_menu.addAction(self.act_report_en12464)
        report_menu.addAction(self.act_report_en13032)

        # Central layout
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Project Items"])
        self.tree.setMinimumWidth(280)

        self.details = QtWidgets.QTableWidget(0, 2)
        self.details.setHorizontalHeaderLabels(["Field", "Value"])
        self.details.horizontalHeader().setStretchLastSection(True)
        self.details.verticalHeader().setVisible(False)
        self.details.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

        self.status = self.statusBar()
        self.status.showMessage("Ready")

        # Copilot dock
        self.copilot = QtWidgets.QDockWidget("Copilot", self)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.copilot)
        cwrap = QtWidgets.QWidget()
        cv = QtWidgets.QVBoxLayout(cwrap)
        self.copilot_input = QtWidgets.QLineEdit()
        self.copilot_input.setPlaceholderText("Ask Luxera Copilot: /place panels target 500 lux")
        self.copilot_run = QtWidgets.QPushButton("Plan / Preview")
        self.copilot_apply_only = QtWidgets.QPushButton("Apply Diff (Approve)")
        self.copilot_run_only = QtWidgets.QPushButton("Run Job (Approve)")
        self.copilot_apply_run = QtWidgets.QPushButton("Apply + Run (Approve)")
        self.copilot_plan_view = QtWidgets.QPlainTextEdit()
        self.copilot_plan_view.setReadOnly(True)
        self.copilot_plan_view.setPlaceholderText("Plan will appear here.")
        self.copilot_diff = QtWidgets.QListWidget()
        self.copilot_diff.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.copilot_diff_details = QtWidgets.QPlainTextEdit()
        self.copilot_diff_details.setReadOnly(True)
        self.copilot_diff_details.setPlaceholderText("Selected diff operation details.")
        self.copilot_select_all = QtWidgets.QPushButton("Select All")
        self.copilot_select_none = QtWidgets.QPushButton("Select None")
        self.copilot_output = QtWidgets.QPlainTextEdit()
        self.copilot_output.setReadOnly(True)
        self.copilot_audit = QtWidgets.QPlainTextEdit()
        self.copilot_audit.setReadOnly(True)
        self.copilot_audit.setPlaceholderText("Latest audit events will appear here.")
        cv.addWidget(self.copilot_input)
        cv.addWidget(self.copilot_run)
        cv.addWidget(self.copilot_apply_only)
        cv.addWidget(self.copilot_run_only)
        cv.addWidget(self.copilot_apply_run)
        cv.addWidget(QtWidgets.QLabel("Plan"))
        cv.addWidget(self.copilot_plan_view)
        cv.addWidget(QtWidgets.QLabel("Diff Preview (check approved changes)"))
        cv.addWidget(self.copilot_diff)
        cv.addWidget(self.copilot_diff_details)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.copilot_select_all)
        row.addWidget(self.copilot_select_none)
        cv.addLayout(row)
        cv.addWidget(QtWidgets.QLabel("Run / Artifact Output"))
        cv.addWidget(self.copilot_output)
        cv.addWidget(QtWidgets.QLabel("Audit Log"))
        cv.addWidget(self.copilot_audit)
        self.copilot.setWidget(cwrap)

    def _wire_actions(self) -> None:
        self.act_new.triggered.connect(self.new_project)
        self.act_open.triggered.connect(self.open_project)
        self.act_save.triggered.connect(self.save_project)
        self.act_save_as.triggered.connect(self.save_project_as)
        self.act_quit.triggered.connect(self.close)

        self.act_add_photometry.triggered.connect(self.add_photometry)
        self.act_add_room.triggered.connect(self.add_room)
        self.act_add_luminaire.triggered.connect(self.add_luminaire)
        self.act_add_grid.triggered.connect(self.add_grid)
        self.act_add_job.triggered.connect(self.add_job)

        self.act_run_job.triggered.connect(self.run_selected_job)
        self.act_compare_last_two.triggered.connect(self.compare_last_two_results)
        self.act_report_en12464.triggered.connect(self.export_en12464)
        self.act_report_en13032.triggered.connect(self.export_en13032)
        self.act_command_palette.triggered.connect(self.command_palette)

        self.tree.itemSelectionChanged.connect(self.on_selection_changed)
        self.copilot_run.clicked.connect(self.copilot_plan_preview)
        self.copilot_apply_only.clicked.connect(self.copilot_apply_only_action)
        self.copilot_run_only.clicked.connect(self.copilot_run_only_action)
        self.copilot_apply_run.clicked.connect(self.copilot_apply_run_action)
        self.copilot_select_all.clicked.connect(lambda: self._set_all_diff_checks(True))
        self.copilot_select_none.clicked.connect(lambda: self._set_all_diff_checks(False))
        self.copilot_diff.currentItemChanged.connect(self._on_diff_item_changed)

    # ----- Project IO -----
    def new_project(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "New Project", "", "Luxera Project (*.json)")
        if not path:
            return
        self.project = Project(name=Path(path).stem, root_dir=str(Path(path).parent))
        self.project_path = Path(path)
        save_project_schema(self.project, self.project_path)
        self.refresh_tree()

    def open_project(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Project", "", "Luxera Project (*.json)")
        if not path:
            return
        self.project_path = Path(path)
        self.project = load_project_schema(self.project_path)
        self.refresh_tree()

    def save_project(self) -> None:
        if not self.project or not self.project_path:
            return
        save_project_schema(self.project, self.project_path)
        self.status.showMessage("Project saved", 3000)

    def save_project_as(self) -> None:
        if not self.project:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Project As", "", "Luxera Project (*.json)")
        if not path:
            return
        self.project_path = Path(path)
        self.project.root_dir = str(self.project_path.parent)
        save_project_schema(self.project, self.project_path)
        self.refresh_tree()

    # ----- Add items -----
    def add_photometry(self) -> None:
        if not self.project:
            return
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Add Photometry", "", "Photometry (*.ies *.ldt)")
        if not file_path:
            return
        p = Path(file_path)
        fmt = p.suffix.replace(".", "").upper()
        asset = PhotometryAsset(
            id=str(uuid.uuid4()),
            format=fmt,
            path=str(p),
            content_hash=sha256_file(str(p)),
            metadata={"filename": p.name},
        )
        self.project.photometry_assets.append(asset)
        self.save_project()
        self.refresh_tree()

    def add_room(self) -> None:
        if not self.project:
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "Room Name", "Room name:")
        if not ok or not name:
            return
        width, ok = QtWidgets.QInputDialog.getDouble(self, "Room Width", "Width (m):", 6.0, 0.1, 200.0, 2)
        if not ok:
            return
        length, ok = QtWidgets.QInputDialog.getDouble(self, "Room Length", "Length (m):", 8.0, 0.1, 200.0, 2)
        if not ok:
            return
        height, ok = QtWidgets.QInputDialog.getDouble(self, "Room Height", "Height (m):", 3.0, 0.1, 50.0, 2)
        if not ok:
            return
        activity, ok = QtWidgets.QInputDialog.getText(self, "Activity Type", "EN 12464 ActivityType (optional):")
        if not ok:
            activity = None
        room = RoomSpec(
            id=str(uuid.uuid4()),
            name=name,
            width=width,
            length=length,
            height=height,
            activity_type=activity or None,
        )
        self.project.geometry.rooms.append(room)
        self.save_project()
        self.refresh_tree()

    def add_luminaire(self) -> None:
        if not self.project or not self.project.photometry_assets:
            return
        items = [a.id for a in self.project.photometry_assets]
        asset_id, ok = QtWidgets.QInputDialog.getItem(self, "Photometry Asset", "Select asset:", items, 0, False)
        if not ok:
            return
        x, ok = QtWidgets.QInputDialog.getDouble(self, "Luminaire X", "X (m):", 2.0, -1000, 1000, 2)
        if not ok:
            return
        y, ok = QtWidgets.QInputDialog.getDouble(self, "Luminaire Y", "Y (m):", 2.0, -1000, 1000, 2)
        if not ok:
            return
        z, ok = QtWidgets.QInputDialog.getDouble(self, "Luminaire Z", "Z (m):", 2.8, -1000, 1000, 2)
        if not ok:
            return
        rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
        lum = LuminaireInstance(
            id=str(uuid.uuid4()),
            name="Luminaire",
            photometry_asset_id=asset_id,
            transform=TransformSpec(position=(x, y, z), rotation=rot),
        )
        self.project.luminaires.append(lum)
        self.save_project()
        self.refresh_tree()

    def add_grid(self) -> None:
        if not self.project:
            return
        width, ok = QtWidgets.QInputDialog.getDouble(self, "Grid Width", "Width (m):", 6.0, 0.1, 200.0, 2)
        if not ok:
            return
        height, ok = QtWidgets.QInputDialog.getDouble(self, "Grid Height", "Height (m):", 8.0, 0.1, 200.0, 2)
        if not ok:
            return
        elevation, ok = QtWidgets.QInputDialog.getDouble(self, "Grid Elevation", "Elevation (m):", 0.8, -10, 10, 2)
        if not ok:
            return
        nx, ok = QtWidgets.QInputDialog.getInt(self, "Grid NX", "NX:", 10, 2, 200)
        if not ok:
            return
        ny, ok = QtWidgets.QInputDialog.getInt(self, "Grid NY", "NY:", 10, 2, 200)
        if not ok:
            return
        grid = CalcGrid(
            id=str(uuid.uuid4()),
            name="Grid",
            origin=(0.0, 0.0, 0.0),
            width=width,
            height=height,
            elevation=elevation,
            nx=nx,
            ny=ny,
        )
        self.project.grids.append(grid)
        self.save_project()
        self.refresh_tree()

    def add_job(self) -> None:
        if not self.project:
            return
        choices = ["en12464_direct", "en13032_radiosity", "direct", "radiosity"]
        choice, ok = QtWidgets.QInputDialog.getItem(self, "Job Preset", "Select job type:", choices, 0, False)
        if not ok:
            return
        job_id = str(uuid.uuid4())
        if choice == "en12464_direct":
            job = en12464_direct_job(job_id)
        elif choice == "en13032_radiosity":
            job = en13032_radiosity_job(job_id)
        elif choice == "radiosity":
            job = JobSpec(id=job_id, type="radiosity")
        else:
            job = JobSpec(id=job_id, type="direct")
        self.project.jobs.append(job)
        self.save_project()
        self.refresh_tree()

    # ----- Run / Export -----
    def run_selected_job(self) -> None:
        if not self.project or not self.project_path:
            return
        item = self.tree.currentItem()
        if not item or item.data(0, QtCore.Qt.UserRole) != "job":
            self.status.showMessage("Select a job to run", 3000)
            return
        job_id = item.data(0, QtCore.Qt.UserRole + 1)
        ref = run_job(self.project_path, job_id)
        self.project = load_project_schema(self.project_path)
        self.refresh_tree()
        self.status.showMessage(f"Job completed: {ref.job_id}", 5000)

    def export_en12464(self) -> None:
        if not self.project or not self.project.results:
            return
        ref = self.project.results[-1]
        model = build_en12464_report_model(self.project, ref)
        out, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export EN 12464 PDF", "", "PDF (*.pdf)")
        if not out:
            return
        render_en12464_pdf(model, Path(out))
        self.status.showMessage("EN 12464 PDF exported", 3000)

    def export_en13032(self) -> None:
        if not self.project or not self.project.results:
            return
        ref = self.project.results[-1]
        model = build_en13032_report_model(self.project, ref)
        out, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export EN 13032 PDF", "", "PDF (*.pdf)")
        if not out:
            return
        render_en13032_pdf(model, Path(out))
        self.status.showMessage("EN 13032 PDF exported", 3000)

    def compare_last_two_results(self) -> None:
        if not self.project or len(self.project.results) < 2:
            self.status.showMessage("Need at least two results to compare", 3000)
            return
        a = self.project.results[-2].job_id
        b = self.project.results[-1].job_id
        try:
            cmp = compare_job_results(self.project, a, b)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Compare Failed", str(e))
            return
        txt = json.dumps(cmp, indent=2, sort_keys=True)
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Compare Results: {a} -> {b}")
        dlg.resize(800, 500)
        lay = QtWidgets.QVBoxLayout(dlg)
        edit = QtWidgets.QPlainTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(txt)
        lay.addWidget(edit)
        dlg.exec()

    # ----- UI helpers -----
    def refresh_tree(self) -> None:
        self.tree.clear()
        if not self.project:
            return

        root = self.tree.invisibleRootItem()
        def add_group(name: str, items):
            group = QtWidgets.QTreeWidgetItem([name])
            root.addChild(group)
            for label, role, role_id in items:
                item = QtWidgets.QTreeWidgetItem([label])
                item.setData(0, QtCore.Qt.UserRole, role)
                item.setData(0, QtCore.Qt.UserRole + 1, role_id)
                group.addChild(item)

        add_group("Photometry", [(a.metadata.get("filename", a.id), "asset", a.id) for a in self.project.photometry_assets])
        add_group("Rooms", [(r.name, "room", r.id) for r in self.project.geometry.rooms])
        add_group("Zones", [(z.name, "zone", z.id) for z in self.project.geometry.zones])
        add_group("Surfaces", [(s.name, "surface", s.id) for s in self.project.geometry.surfaces])
        add_group("Luminaires", [(l.name, "luminaire", l.id) for l in self.project.luminaires])
        add_group("Grids", [(g.name, "grid", g.id) for g in self.project.grids])
        add_group("Workplanes", [(w.name, "workplane", w.id) for w in self.project.workplanes])
        add_group("Vertical Planes", [(v.name, "vplane", v.id) for v in self.project.vertical_planes])
        add_group("Point Sets", [(ps.name, "pointset", ps.id) for ps in self.project.point_sets])
        add_group("Glare Views", [(gv.name, "glareview", gv.id) for gv in self.project.glare_views])
        add_group("Compliance Profiles", [(cp.name, "cprofile", cp.id) for cp in self.project.compliance_profiles])
        add_group("Variants", [(v.name, "variant", v.id) for v in self.project.variants])
        add_group("Jobs", [(j.id, "job", j.id) for j in self.project.jobs])
        add_group("Results", [(r.job_id, "result", r.job_id) for r in self.project.results])
        add_group(
            "Agent Log",
            [
                (f"{e.get('action', e.get('kind', 'event'))} @ {int(e.get('created_at', 0))}", "agent_event", str(i))
                for i, e in enumerate(self.project.agent_history)
            ],
        )

        self.tree.expandAll()

    def on_selection_changed(self) -> None:
        item = self.tree.currentItem()
        if not item or not self.project:
            return
        role = item.data(0, QtCore.Qt.UserRole)
        role_id = item.data(0, QtCore.Qt.UserRole + 1)
        self.details.setRowCount(0)

        def add_row(k, v):
            row = self.details.rowCount()
            self.details.insertRow(row)
            self.details.setItem(row, 0, QtWidgets.QTableWidgetItem(str(k)))
            self.details.setItem(row, 1, QtWidgets.QTableWidgetItem(str(v)))

        if role == "asset":
            asset = next(a for a in self.project.photometry_assets if a.id == role_id)
            add_row("ID", asset.id)
            add_row("Format", asset.format)
            add_row("Path", asset.path)
            add_row("Hash", asset.content_hash)
        elif role == "room":
            room = next(r for r in self.project.geometry.rooms if r.id == role_id)
            add_row("Name", room.name)
            add_row("Size", f"{room.width} x {room.length} x {room.height} m")
            add_row("Reflectance", f"{room.floor_reflectance}/{room.wall_reflectance}/{room.ceiling_reflectance}")
            add_row("Activity", room.activity_type)
        elif role == "luminaire":
            lum = next(l for l in self.project.luminaires if l.id == role_id)
            add_row("Name", lum.name)
            add_row("Asset", lum.photometry_asset_id)
            add_row("Position", lum.transform.position)
        elif role == "zone":
            zone = next(z for z in self.project.geometry.zones if z.id == role_id)
            add_row("Name", zone.name)
            add_row("Rooms", zone.room_ids)
            add_row("Tags", zone.tags)
        elif role == "surface":
            surf = next(s for s in self.project.geometry.surfaces if s.id == role_id)
            add_row("Name", surf.name)
            add_row("Kind", surf.kind)
            add_row("Vertices", len(surf.vertices))
            add_row("Room", surf.room_id)
        elif role == "grid":
            grid = next(g for g in self.project.grids if g.id == role_id)
            add_row("Name", grid.name)
            add_row("Size", f"{grid.width} x {grid.height} m")
            add_row("Elevation", grid.elevation)
            add_row("Resolution", f"{grid.nx} x {grid.ny}")
        elif role == "workplane":
            wp = next(w for w in self.project.workplanes if w.id == role_id)
            add_row("Name", wp.name)
            add_row("Elevation", wp.elevation)
            add_row("Spacing", wp.spacing)
            add_row("Margin", wp.margin)
            add_row("Room/Zone", wp.room_id or wp.zone_id)
        elif role == "vplane":
            vp = next(v for v in self.project.vertical_planes if v.id == role_id)
            add_row("Name", vp.name)
            add_row("Size", f"{vp.width} x {vp.height} m")
            add_row("Resolution", f"{vp.nx} x {vp.ny}")
            add_row("Azimuth", vp.azimuth_deg)
        elif role == "pointset":
            ps = next(p for p in self.project.point_sets if p.id == role_id)
            add_row("Name", ps.name)
            add_row("Points", len(ps.points))
            add_row("Room/Zone", ps.room_id or ps.zone_id)
        elif role == "glareview":
            gv = next(g for g in self.project.glare_views if g.id == role_id)
            add_row("Name", gv.name)
            add_row("Observer", gv.observer)
            add_row("View Dir", gv.view_dir)
        elif role == "cprofile":
            cp = next(c for c in self.project.compliance_profiles if c.id == role_id)
            add_row("Name", cp.name)
            add_row("Domain", cp.domain)
            add_row("Standard", cp.standard_ref)
            add_row("Thresholds", cp.thresholds)
        elif role == "variant":
            var = next(v for v in self.project.variants if v.id == role_id)
            add_row("Name", var.name)
            add_row("Description", var.description)
            add_row("Dimming schemes", var.dimming_schemes)
        elif role == "job":
            job = next(j for j in self.project.jobs if j.id == role_id)
            add_row("ID", job.id)
            add_row("Type", job.type)
            add_row("Seed", job.seed)
            add_row("Settings", job.settings)
        elif role == "result":
            res = next(r for r in self.project.results if r.job_id == role_id)
            add_row("Job ID", res.job_id)
            add_row("Hash", res.job_hash)
            add_row("Dir", res.result_dir)
            for k, v in (res.summary or {}).items():
                add_row(f"summary.{k}", v)
        elif role == "agent_event":
            idx = int(role_id)
            if 0 <= idx < len(self.project.agent_history):
                event = self.project.agent_history[idx]
                for k, v in event.items():
                    add_row(k, v)

    # ----- Copilot -----
    def _copilot_execute(self, approve_apply: bool, approve_run: bool) -> None:
        if not self.project_path:
            self.status.showMessage("Open a project first", 3000)
            return
        intent = self.copilot_input.text().strip()
        if not intent:
            return
        if approve_run and "run" not in intent.lower():
            intent = f"{intent} run"
        approvals: Dict[str, Any] = {"apply_diff": approve_apply, "run_job": approve_run}
        if approve_apply:
            approvals["selected_diff_ops"] = self._selected_diff_keys()
        res = self.agent_runtime.execute(str(self.project_path), intent, approvals=approvals)
        self.copilot_plan_view.setPlainText(res.plan)
        self._populate_diff_preview(res.diff_preview.get("ops", []))
        lines = [
            f"Diff ops: {res.diff_preview.get('count', 0)}",
            f"Selected diff ops: {len(self._selected_diff_keys())}",
            f"Actions: {[a.kind + ('*' if a.requires_approval else '') for a in res.actions]}",
            f"Run manifest: {res.run_manifest}",
            f"Artifacts: {res.produced_artifacts}",
            f"Warnings: {res.warnings}",
        ]
        suggestions = self._inline_suggestions()
        if suggestions:
            lines.append("Suggestions:")
            lines.extend([f"- {s}" for s in suggestions])
        self.copilot_output.setPlainText("\n".join(lines))
        # Reload project after runtime mutations.
        self.project = load_project_schema(self.project_path)
        self.refresh_tree()
        self._refresh_audit_view()

    def copilot_plan_preview(self) -> None:
        self._copilot_execute(approve_apply=False, approve_run=False)

    def copilot_apply_only_action(self) -> None:
        msg = QtWidgets.QMessageBox.question(
            self,
            "Approve Diff Apply",
            "Approve applying selected diff ops?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if msg != QtWidgets.QMessageBox.Yes:
            return
        self._copilot_execute(approve_apply=True, approve_run=False)

    def copilot_apply_run_action(self) -> None:
        msg = QtWidgets.QMessageBox.question(
            self,
            "Approve Actions",
            "Approve applying diff and running job?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if msg != QtWidgets.QMessageBox.Yes:
            return
        self._copilot_execute(approve_apply=True, approve_run=True)

    def copilot_run_only_action(self) -> None:
        msg = QtWidgets.QMessageBox.question(
            self,
            "Approve Job Run",
            "Approve running job?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if msg != QtWidgets.QMessageBox.Yes:
            return
        self._copilot_execute(approve_apply=False, approve_run=True)

    def command_palette(self) -> None:
        commands = [
            "/place panels target 500 lux",
            "/grid 0.8 0.25",
            "/run illuminance",
            "/report client",
            "import ./model.ifc detect rooms create grid",
            "hit 500 lux uniformity",
            "generate client report and audit bundle",
            "check compliance",
            "render heatmap",
        ]
        cmd, ok = QtWidgets.QInputDialog.getItem(self, "Command Palette", "Command:", commands, 0, False)
        if not ok or not cmd:
            return
        self.copilot_input.setText(cmd)
        self.copilot_input.setFocus()

    def _inline_suggestions(self) -> list[str]:
        if not self.project:
            return []
        out: list[str] = []
        if not self.project.photometry_assets:
            out.append("No photometry assets: import IES/LDT before running jobs.")
        if not self.project.luminaires:
            out.append("No luminaires placed: use /place panels target 500 lux.")
        if not self.project.jobs:
            out.append("No jobs configured: add a direct job to compute illuminance.")
        if not self.project.grids:
            out.append("No grids found: use /grid 0.8 0.25 to create a workplane grid.")
        else:
            g = self.project.grids[0]
            sx = g.width / max(g.nx - 1, 1)
            sy = g.height / max(g.ny - 1, 1)
            spacing = max(sx, sy)
            if spacing > 0.5:
                out.append(f"Grid spacing is coarse (~{spacing:.2f} m): consider 0.25 m for office compliance studies.")
        has_radiosity = any(j.type == "radiosity" for j in self.project.jobs)
        if has_radiosity and not self.project.glare_views:
            out.append("UGR risk: define glare views for observer-specific glare tables.")
        return out[:5]

    def _populate_diff_preview(self, ops: List[Dict[str, Any]]) -> None:
        previous = set(self._selected_diff_keys())
        self.copilot_diff.clear()
        self._copilot_preview_ops = {}
        for op in ops:
            key = str(op.get("key", ""))
            if not key:
                continue
            self._copilot_preview_ops[key] = op
            payload = op.get("payload_summary", "")
            suffix = f" [{payload}]" if payload else ""
            label = f"{op.get('op', '?')} {op.get('kind', '?')} {op.get('id', '?')}{suffix}"
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.UserRole, key)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if (not previous or key in previous) else QtCore.Qt.Unchecked)
            self.copilot_diff.addItem(item)
        if self.copilot_diff.count() > 0:
            self.copilot_diff.setCurrentRow(0)
        else:
            self.copilot_diff_details.setPlainText("")

    def _selected_diff_keys(self) -> List[str]:
        out: List[str] = []
        for i in range(self.copilot_diff.count()):
            item = self.copilot_diff.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                key = item.data(QtCore.Qt.UserRole)
                if key:
                    out.append(str(key))
        return out

    def _set_all_diff_checks(self, checked: bool) -> None:
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        for i in range(self.copilot_diff.count()):
            self.copilot_diff.item(i).setCheckState(state)

    def _on_diff_item_changed(self, current: Optional[QtWidgets.QListWidgetItem], previous: Optional[QtWidgets.QListWidgetItem]) -> None:  # noqa: ARG002
        if current is None:
            self.copilot_diff_details.setPlainText("")
            return
        key = current.data(QtCore.Qt.UserRole)
        op = self._copilot_preview_ops.get(str(key), {})
        self.copilot_diff_details.setPlainText(json.dumps(op, indent=2, sort_keys=True))

    def _refresh_audit_view(self) -> None:
        if not self.project:
            self.copilot_audit.setPlainText("")
            return
        events = self.project.agent_history[-5:]
        lines: List[str] = []
        for e in events:
            action = e.get("action", e.get("kind", "event"))
            ts = int(e.get("created_at", 0))
            warns = e.get("warnings", [])
            lines.append(f"{ts} {action}")
            if warns:
                lines.append(f"  warnings={warns}")
        self.copilot_audit.setPlainText("\n".join(lines))


def run() -> int:
    app = QtWidgets.QApplication([])
    win = LuxeraWorkspaceWindow()
    win.show()
    return int(app.exec())
