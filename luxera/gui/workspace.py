from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

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


class LuxeraWorkspaceWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Luxera Workspace")
        self.resize(1200, 800)

        self.project_path: Optional[Path] = None
        self.project: Optional[Project] = None

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
        run_menu.addAction(self.act_run_job)

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
        self.act_report_en12464.triggered.connect(self.export_en12464)
        self.act_report_en13032.triggered.connect(self.export_en13032)

        self.tree.itemSelectionChanged.connect(self.on_selection_changed)

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
        ref = run_job(self.project, job_id)
        self.save_project()
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
        add_group("Luminaires", [(l.name, "luminaire", l.id) for l in self.project.luminaires])
        add_group("Grids", [(g.name, "grid", g.id) for g in self.project.grids])
        add_group("Jobs", [(j.id, "job", j.id) for j in self.project.jobs])
        add_group("Results", [(r.job_id, "result", r.job_id) for r in self.project.results])

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
        elif role == "grid":
            grid = next(g for g in self.project.grids if g.id == role_id)
            add_row("Name", grid.name)
            add_row("Size", f"{grid.width} x {grid.height} m")
            add_row("Elevation", grid.elevation)
            add_row("Resolution", f"{grid.nx} x {grid.ny}")
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


def run() -> int:
    app = QtWidgets.QApplication([])
    win = LuxeraWorkspaceWindow()
    win.show()
    return int(app.exec())
