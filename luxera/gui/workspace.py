from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from luxera.agent.runtime import AgentRuntime
from luxera.gui.commands import (
    cmd_apply_diff,
    cmd_compare_variants,
    cmd_delete_object,
    cmd_duplicate_object,
    cmd_export_audit_bundle,
    cmd_export_report,
    cmd_place_rect_array,
    cmd_run_job,
    cmd_update_object,
)
from luxera.gui.widgets.assistant_panel import AssistantPanel
from luxera.gui.widgets.inspector import PropertiesInspector
from luxera.gui.widgets.job_manager import JobManagerWidget
from luxera.gui.widgets.log_panel import LogPanel
from luxera.gui.widgets.library_panel import PhotometryLibraryWidget
from luxera.gui.widgets.project_tree import ProjectTreeWidget
from luxera.gui.widgets.results_view import ResultsView
from luxera.gui.widgets.viewer3d import Viewer3D
from luxera.gui.widgets.viewport2d import Viewport2D
from luxera.gui.widgets.variants_panel import VariantsPanel
from luxera.gui.recent_files import add_recent_path, coerce_recent_paths
from luxera.gui.scene_node_binding import resolve_scene_node_update
from luxera.gui.theme import set_theme
from luxera.core.hashing import sha256_file
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.diff import DiffOp, ProjectDiff
from luxera.project.schema import LuminaireInstance, PhotometryAsset, Project, RotationSpec, TransformSpec
from luxera.ops.scene_ops import create_room as op_create_room, extrude_room_to_surfaces
from luxera.ops.calc_ops import create_calc_grid_from_room


class LuxeraWorkspaceWindow(QtWidgets.QMainWindow):
    _MAX_RECENT_FILES = 10
    _SETTINGS_ORG = "Luxera"
    _SETTINGS_APP = "Luxera"
    _SETTINGS_RECENT_KEY = "workspace/recent_projects"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Luxera Workspace")
        self.resize(1500, 940)

        self.project_path: Path | None = None
        self.project: Project | None = None
        self.agent_runtime = AgentRuntime()
        self.recent_project_paths: list[str] = []
        self._recent_actions: list[QtGui.QAction] = []

        self._run_thread: threading.Thread | None = None
        self._run_cancel_requested = False
        self._copilot_preview_ops: dict[str, dict[str, Any]] = {}

        self._build_ui()
        self._wire_actions()
        self._load_recent_projects()
        self._refresh_recent_projects_menu()

    def _build_ui(self) -> None:
        self._build_menu()

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        self._build_workflow_toolbar(root)

        top_split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        bottom_tabs = QtWidgets.QTabWidget()

        self.project_tree = ProjectTreeWidget()
        self.project_tree.setMinimumWidth(280)
        top_split.addWidget(self.project_tree)

        self.center_stack = QtWidgets.QStackedWidget()
        self.viewport = Viewport2D()
        self.center_stack.addWidget(self.viewport)
        self.viewer3d = Viewer3D()
        self.center_stack.addWidget(self.viewer3d)
        top_split.addWidget(self.center_stack)

        self.inspector = PropertiesInspector()
        self.inspector.setMinimumWidth(300)
        top_split.addWidget(self.inspector)

        top_split.setStretchFactor(0, 1)
        top_split.setStretchFactor(1, 4)
        top_split.setStretchFactor(2, 2)

        self.job_manager = JobManagerWidget()
        self.results_view = ResultsView()
        self.log_panel = LogPanel()
        self.variants_panel = VariantsPanel()
        self.library_panel = PhotometryLibraryWidget()

        bottom_tabs.addTab(self.job_manager, "Job Manager")
        bottom_tabs.addTab(self.results_view, "Results")
        bottom_tabs.addTab(self.variants_panel, "Variants")
        bottom_tabs.addTab(self.library_panel, "Photometry Library")
        bottom_tabs.addTab(self.log_panel, "Logs")

        outer_split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        outer_split.addWidget(top_split)
        outer_split.addWidget(bottom_tabs)
        outer_split.setStretchFactor(0, 7)
        outer_split.setStretchFactor(1, 3)

        root.addWidget(outer_split)

        self.assistant_dock = QtWidgets.QDockWidget("Assistant", self)
        self.assistant_dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        self.assistant_dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable
            | QtWidgets.QDockWidget.DockWidgetFloatable
            | QtWidgets.QDockWidget.DockWidgetClosable
        )
        self.assistant_panel = AssistantPanel(self)
        self.assistant_dock.setWidget(self.assistant_panel)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.assistant_dock)

        # Compatibility aliases used by current copilot handlers.
        self.copilot_input = self.assistant_panel.input
        self.copilot_run = self.assistant_panel.run
        self.copilot_apply_only = self.assistant_panel.apply_only
        self.copilot_run_only = self.assistant_panel.run_only
        self.copilot_apply_run = self.assistant_panel.apply_run
        self.copilot_undo_assistant = self.assistant_panel.undo_assistant
        self.copilot_redo_assistant = self.assistant_panel.redo_assistant
        self.copilot_plan_view = self.assistant_panel.plan_view
        self.copilot_diff = self.assistant_panel.diff
        self.copilot_diff_details = self.assistant_panel.diff_details
        self.copilot_select_all = self.assistant_panel.select_all
        self.copilot_select_none = self.assistant_panel.select_none
        self.copilot_output = self.assistant_panel.output
        self.copilot_audit = self.assistant_panel.audit
        self.copilot_activity_log = self.assistant_panel.activity_log
        self.copilot_design_options = self.assistant_panel.design_options
        self.copilot_design_iterate = self.assistant_panel.design_iterate
        self.copilot_design_max_iters = self.assistant_panel.design_max_iters

        self.status = self.statusBar()
        self.status.showMessage("No project open")

    def _build_workflow_toolbar(self, root: QtWidgets.QVBoxLayout) -> None:
        row = QtWidgets.QHBoxLayout()
        self.mode_2d_btn = QtWidgets.QPushButton("2D Plan")
        self.mode_2d_btn.setCheckable(True)
        self.mode_2d_btn.setChecked(True)
        self.mode_3d_btn = QtWidgets.QPushButton("3D View")
        self.mode_3d_btn.setCheckable(True)
        self._mode_group = QtWidgets.QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self.mode_2d_btn)
        self._mode_group.addButton(self.mode_3d_btn)
        self.btn_draw_room = QtWidgets.QPushButton("Draw Room")
        self.btn_add_luminaire = QtWidgets.QPushButton("Add Luminaire")
        self.btn_array_luminaires = QtWidgets.QPushButton("Array")
        self.btn_create_grid = QtWidgets.QPushButton("Create Grid")
        self.btn_view_overlay = QtWidgets.QPushButton("View Overlay")
        self.btn_run_calc = QtWidgets.QPushButton("Run Calculation")
        for w in (
            self.mode_2d_btn,
            self.mode_3d_btn,
            self.btn_draw_room,
            self.btn_add_luminaire,
            self.btn_array_luminaires,
            self.btn_create_grid,
            self.btn_view_overlay,
            self.btn_run_calc,
        ):
            row.addWidget(w)
        row.addStretch(1)
        root.addLayout(row)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        run_menu = menubar.addMenu("&Run")
        view_menu = menubar.addMenu("&View")

        self.act_new = QtGui.QAction("New Project...", self)
        self.act_open = QtGui.QAction("Open Project...", self)
        self.act_save = QtGui.QAction("Save", self)
        self.act_save_as = QtGui.QAction("Save As...", self)
        self.act_quit = QtGui.QAction("Quit", self)
        self.act_clear_recent = QtGui.QAction("Clear Recent", self)

        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_open)
        self.recent_menu = file_menu.addMenu("Open Recent")
        file_menu.addAction(self.act_clear_recent)
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        self.act_run_selected = QtGui.QAction("Run Selected Job", self)
        self.act_cancel_run = QtGui.QAction("Cancel Running Job", self)
        self.act_toggle_assistant = QtGui.QAction("Toggle Assistant", self)
        self.act_toggle_assistant.setCheckable(True)
        self.act_toggle_assistant.setChecked(True)

        run_menu.addAction(self.act_run_selected)
        run_menu.addAction(self.act_cancel_run)
        run_menu.addSeparator()
        run_menu.addAction(self.act_toggle_assistant)

        self.act_theme_dark = QtGui.QAction("Dark Theme", self)
        self.act_theme_dark.setCheckable(True)
        view_menu.addAction(self.act_theme_dark)

    def _wire_actions(self) -> None:
        self.act_new.triggered.connect(self.new_project)
        self.act_open.triggered.connect(self.open_project)
        self.act_clear_recent.triggered.connect(self.clear_recent_projects)
        self.act_save.triggered.connect(self.save_project)
        self.act_save_as.triggered.connect(self.save_project_as)
        self.act_quit.triggered.connect(self.close)

        self.act_run_selected.triggered.connect(self.run_selected_job)
        self.act_cancel_run.triggered.connect(self.cancel_running_job)
        self.act_toggle_assistant.toggled.connect(self.assistant_dock.setVisible)
        self.assistant_dock.visibilityChanged.connect(self.act_toggle_assistant.setChecked)
        self.act_theme_dark.toggled.connect(self._on_toggle_dark_theme)

        self.project_tree.selection_changed.connect(self.on_tree_selection_changed)
        self.project_tree.action_requested.connect(self.on_tree_action_requested)
        self.viewport.object_selected.connect(self.on_viewport_selected)
        self.viewer3d.object_selected.connect(self.on_viewport_selected)
        self.viewport.luminaire_moved.connect(self.on_luminaire_dragged)
        self.viewport.layer_visibility_changed.connect(self.on_layer_visibility_changed)
        self.viewport.library_asset_dropped.connect(self.on_library_asset_dropped)
        self.inspector.apply_requested.connect(self.on_inspector_apply)

        self.job_manager.run_requested.connect(self.run_job_by_id)
        self.job_manager.cancel_requested.connect(lambda _job_id: self.cancel_running_job())
        self.job_manager.view_requested.connect(self.results_view.select_job)
        self.job_manager.export_requested.connect(self.export_report_for_job)

        self.results_view.open_report_requested.connect(self.open_report_for_job)
        self.results_view.open_bundle_requested.connect(self.open_bundle_for_job)
        self.variants_panel.compare_requested.connect(self.compare_variants)

        self.copilot_run.clicked.connect(self.copilot_plan_preview)
        self.copilot_apply_only.clicked.connect(self.copilot_apply_only_action)
        self.copilot_run_only.clicked.connect(self.copilot_run_only_action)
        self.copilot_apply_run.clicked.connect(self.copilot_apply_run_action)
        self.copilot_undo_assistant.clicked.connect(self.copilot_undo_assistant_action)
        self.copilot_redo_assistant.clicked.connect(self.copilot_redo_assistant_action)
        self.copilot_select_all.clicked.connect(lambda: self._set_all_diff_checks(True))
        self.copilot_select_none.clicked.connect(lambda: self._set_all_diff_checks(False))
        self.copilot_diff.currentItemChanged.connect(self._on_diff_item_changed)
        self.assistant_panel.export_report.clicked.connect(self.copilot_export_report_action)
        self.assistant_panel.export_audit_bundle.clicked.connect(self.copilot_export_audit_bundle_action)
        self.copilot_design_iterate.clicked.connect(self.copilot_design_iterate_action)
        self.library_panel.status_message.connect(lambda msg: self.status.showMessage(msg, 3000))
        self.mode_2d_btn.clicked.connect(lambda: self.center_stack.setCurrentIndex(0))
        self.mode_3d_btn.clicked.connect(lambda: self.center_stack.setCurrentIndex(1))
        self.btn_draw_room.clicked.connect(self.draw_room_polygon)
        self.btn_add_luminaire.clicked.connect(self.add_luminaire)
        self.btn_array_luminaires.clicked.connect(self.array_luminaires)
        self.btn_create_grid.clicked.connect(self.create_workplane_grid)
        self.btn_run_calc.clicked.connect(self.run_primary_job)
        self.btn_view_overlay.clicked.connect(self.view_latest_overlay)

    def new_project(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "New Project", "", "Luxera Project (*.json)")
        if not path:
            return
        self.project = Project(name=Path(path).stem, root_dir=str(Path(path).parent))
        self.project_path = Path(path)
        save_project_schema(self.project, self.project_path)
        self._remember_recent_project(self.project_path)
        self.refresh_workspace()

    def open_project(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Project", "", "Luxera Project (*.json)")
        if not path:
            return
        self._open_project_path(Path(path))

    def save_project(self) -> None:
        if not self.project or not self.project_path:
            return
        save_project_schema(self.project, self.project_path)
        self.status.showMessage("Project saved", 2000)

    def save_project_as(self) -> None:
        if not self.project:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Project As", "", "Luxera Project (*.json)")
        if not path:
            return
        self.project_path = Path(path)
        self.project.root_dir = str(self.project_path.parent)
        save_project_schema(self.project, self.project_path)
        self._remember_recent_project(self.project_path)
        self.refresh_workspace()

    def _open_project_path(self, path: Path) -> None:
        if not path.exists():
            QtWidgets.QMessageBox.warning(self, "Open Project", f"Project file not found:\n{path}")
            self._drop_recent_project(path)
            return
        try:
            self.project_path = path
            self.project = load_project_schema(self.project_path)
            self._remember_recent_project(self.project_path)
            self.refresh_workspace()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Open Project", str(exc))

    def _load_recent_projects(self) -> None:
        settings = QtCore.QSettings(self._SETTINGS_ORG, self._SETTINGS_APP)
        raw = settings.value(self._SETTINGS_RECENT_KEY, [])
        self.recent_project_paths = coerce_recent_paths(raw)[: self._MAX_RECENT_FILES]

    def _save_recent_projects(self) -> None:
        settings = QtCore.QSettings(self._SETTINGS_ORG, self._SETTINGS_APP)
        settings.setValue(self._SETTINGS_RECENT_KEY, list(self.recent_project_paths))

    def _remember_recent_project(self, path: Path) -> None:
        self.recent_project_paths = add_recent_path(
            self.recent_project_paths,
            str(path),
            max_items=self._MAX_RECENT_FILES,
        )
        self._save_recent_projects()
        self._refresh_recent_projects_menu()

    def _drop_recent_project(self, path: Path) -> None:
        resolved = str(path.expanduser().resolve())
        self.recent_project_paths = [p for p in self.recent_project_paths if p != resolved]
        self._save_recent_projects()
        self._refresh_recent_projects_menu()

    def clear_recent_projects(self) -> None:
        self.recent_project_paths = []
        self._save_recent_projects()
        self._refresh_recent_projects_menu()

    def _refresh_recent_projects_menu(self) -> None:
        self.recent_menu.clear()
        self._recent_actions = []
        existing: list[str] = []
        for p in self.recent_project_paths:
            if Path(p).exists():
                existing.append(p)
        if existing != self.recent_project_paths:
            self.recent_project_paths = existing[: self._MAX_RECENT_FILES]
            self._save_recent_projects()
        if not self.recent_project_paths:
            action = QtGui.QAction("(No recent projects)", self)
            action.setEnabled(False)
            self.recent_menu.addAction(action)
            self._recent_actions.append(action)
            return
        for p in self.recent_project_paths:
            path = Path(p)
            action = QtGui.QAction(path.name, self)
            action.setToolTip(p)
            action.triggered.connect(lambda _checked=False, pp=path: self._open_project_path(pp))
            self.recent_menu.addAction(action)
            self._recent_actions.append(action)

    def refresh_workspace(self) -> None:
        if self.project_path and self.project is None:
            self.project = load_project_schema(self.project_path)
        self.project_tree.set_project(self.project)
        self.viewport.set_project(self.project)
        self.viewer3d.set_project(self.project)
        self.job_manager.set_project(self.project)
        self.results_view.set_project(self.project)
        self.variants_panel.set_project(self.project)
        self.inspector.clear()
        name = self.project.name if self.project else "No project open"
        self.status.showMessage(name)
        self._refresh_audit_view()

    def _reload_project(self) -> None:
        if self.project_path:
            self.project = load_project_schema(self.project_path)
            self.refresh_workspace()

    def on_tree_selection_changed(self, node_type: str, object_id: str) -> None:
        if not self.project:
            return
        self.inspector.set_context(self.project, node_type, object_id)
        if node_type == "result":
            self.results_view.select_job(object_id)

    def on_viewport_selected(self, node_type: str, object_id: str) -> None:
        if self.project:
            self.inspector.set_context(self.project, node_type, object_id)

    def on_layer_visibility_changed(self, layer_id: str, visible: bool) -> None:
        if not self.project or not self.project_path:
            return
        layer = next((l for l in self.project.layers if l.id == layer_id), None)
        if layer is None:
            return
        layer.visible = bool(visible)
        save_project_schema(self.project, self.project_path)

    def on_library_asset_dropped(self, payload: dict, x: float, y: float) -> None:
        if not self.project_path:
            return
        self._reload_project()
        if not self.project:
            return
        file_path = str(payload.get("file_path", "")).strip()
        if not file_path:
            return
        p = Path(file_path).expanduser().resolve()
        if not p.exists():
            QtWidgets.QMessageBox.warning(self, "Place Luminaire", f"Photometry file not found:\n{p}")
            return
        ext = p.suffix.lower().lstrip(".")
        if ext not in {"ies", "ldt"}:
            QtWidgets.QMessageBox.warning(self, "Place Luminaire", f"Unsupported photometry format: {p.suffix}")
            return

        existing = next((a for a in self.project.photometry_assets if (a.path and Path(a.path).expanduser().resolve() == p)), None)
        if existing is None:
            aid = f"asset_{len(self.project.photometry_assets) + 1}"
            while any(a.id == aid for a in self.project.photometry_assets):
                aid = f"{aid}_x"
            asset = PhotometryAsset(
                id=aid,
                format=ext.upper(),  # type: ignore[arg-type]
                path=str(p),
                content_hash=sha256_file(str(p)),
                metadata={k: v for k, v in payload.items() if k != "metadata"},
            )
            self.project.photometry_assets.append(asset)
            save_project_schema(self.project, self.project_path)
            asset_id = aid
        else:
            asset_id = existing.id

        mount_z = 2.7
        if self.project.geometry.rooms:
            room = self.project.geometry.rooms[0]
            mount_z = float(room.origin[2]) + max(float(room.height) - 0.2, 2.5)

        lum_id = f"lum_{len(self.project.luminaires) + 1}"
        while any(l.id == lum_id for l in self.project.luminaires):
            lum_id = f"{lum_id}_x"
        payload_l = LuminaireInstance(
            id=lum_id,
            name=str(payload.get("name") or f"Luminaire {len(self.project.luminaires) + 1}"),
            photometry_asset_id=asset_id,
            transform=TransformSpec(
                position=(float(x), float(y), float(mount_z)),
                rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0)),
            ),
        )
        diff = ProjectDiff(ops=[DiffOp(op="add", kind="luminaire", id=lum_id, payload=payload_l)])
        cmd_apply_diff(str(self.project_path), diff)
        self.log_panel.append(f"Luminaire placed from library: {lum_id}")
        self._reload_project()

    def on_inspector_apply(self, node_type: str, object_id: str, payload: dict) -> None:
        if not self.project_path:
            return
        try:
            if node_type == "scene_node":
                if not self.project:
                    return
                kind, oid, mapped = resolve_scene_node_update(self.project, object_id, payload)
                cmd_update_object(str(self.project_path), kind, oid, mapped)
                self.log_panel.append(f"Updated scene_node:{object_id} -> {kind}:{oid}")
            else:
                cmd_update_object(str(self.project_path), node_type, object_id, payload)
                self.log_panel.append(f"Updated {node_type}:{object_id}")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Update Failed", str(exc))
            return
        self._reload_project()

    def on_luminaire_dragged(self, luminaire_id: str, x: float, y: float) -> None:
        if not self.project_path or not self.project:
            return
        lum = next((l for l in self.project.luminaires if l.id == luminaire_id), None)
        if lum is None:
            return
        pos = lum.transform.position
        transform = TransformSpec(position=(x, y, float(pos[2])), rotation=lum.transform.rotation)
        try:
            cmd_update_object(str(self.project_path), "luminaire", luminaire_id, {"transform": transform})
            self.log_panel.append(f"Moved luminaire {luminaire_id} -> ({x:.3f}, {y:.3f}, {pos[2]:.3f})")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Move Failed", str(exc))
            return
        self._reload_project()

    def on_tree_action_requested(self, action: str, node_type: str, object_id: str) -> None:
        if not self.project_path:
            return
        if action == "run_job" and node_type == "job":
            self.run_job_by_id(object_id)
            return
        if action == "view_results" and node_type == "result":
            self.results_view.select_job(object_id)
            return
        if action == "export_report":
            self.export_report_for_job(object_id)
            return
        if action == "edit":
            if self.project:
                self.inspector.set_context(self.project, node_type, object_id)
            return
        if action == "duplicate":
            try:
                cmd_duplicate_object(str(self.project_path), node_type, object_id)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Duplicate Failed", str(exc))
                return
            self._reload_project()
            return
        if action == "delete":
            ok = QtWidgets.QMessageBox.question(
                self,
                "Delete Item",
                f"Delete {node_type}:{object_id}?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if ok != QtWidgets.QMessageBox.Yes:
                return
            try:
                cmd_delete_object(str(self.project_path), node_type, object_id)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Delete Failed", str(exc))
                return
            self._reload_project()

    def run_selected_job(self) -> None:
        if not self.project:
            return
        selected = self.project_tree.view.currentIndex()
        if not selected.isValid() or str(selected.data(QtCore.Qt.UserRole + 1) or "") == "":
            self.status.showMessage("Select a job in the tree", 3000)
            return
        node_type = selected.data(QtCore.Qt.UserRole + 1)
        object_id = selected.data(QtCore.Qt.UserRole + 2)
        if str(node_type) != "job":
            self.status.showMessage("Select a job in the tree", 3000)
            return
        self.run_job_by_id(str(object_id))

    def run_job_by_id(self, job_id: str) -> None:
        if not self.project_path:
            return
        if self._run_thread is not None and self._run_thread.is_alive():
            self.status.showMessage("A job is already running", 3000)
            return
        self._run_cancel_requested = False
        self.status.showMessage(f"Running job: {job_id}")
        self.log_panel.append(f"Run requested: {job_id}")

        def _worker() -> None:
            try:
                ref = cmd_run_job(str(self.project_path), job_id)
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_on_job_finished",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(str, ref.job_id),
                )
            except Exception as exc:
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_on_job_failed",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(str, str(exc)),
                )

        self._run_thread = threading.Thread(target=_worker, daemon=True)
        self._run_thread.start()

    @QtCore.Slot(str)
    def _on_job_finished(self, job_id: str) -> None:
        self._run_thread = None
        self._reload_project()
        self.results_view.select_job(job_id)
        self.status.showMessage(f"Job completed: {job_id}", 5000)
        self.log_panel.append(f"Job completed: {job_id}")

    @QtCore.Slot(str)
    def _on_job_failed(self, err: str) -> None:
        self._run_thread = None
        self.status.showMessage(f"Job failed: {err}", 5000)
        self.log_panel.append(f"Job failed: {err}")

    def cancel_running_job(self) -> None:
        if self._run_thread is None or not self._run_thread.is_alive():
            self.status.showMessage("No running job", 3000)
            return
        self._run_cancel_requested = True
        self.status.showMessage("Cancel requested (best effort)", 3000)
        self.log_panel.append("Cancel requested")

    def export_report_for_job(self, job_id: str) -> None:
        if not self.project_path:
            return
        out, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export Report", f"{job_id}_report.pdf", "PDF (*.pdf)")
        if not out:
            return
        template = "en12464"
        if self.project is not None:
            job = next((j for j in self.project.jobs if j.id == job_id), None)
            if job is not None and job.type in {"roadway", "daylight", "emergency"}:
                template = "auto"
        try:
            cmd_export_report(str(self.project_path), job_id, template, out_path=out)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Export Failed", str(exc))
            return
        self.status.showMessage("Report exported", 3000)

    def open_report_for_job(self, job_id: str) -> None:
        if not self.project:
            return
        ref = next((r for r in self.project.results if r.job_id == job_id), None)
        if ref is None:
            return
        path = Path(ref.result_dir) / "report.pdf"
        if path.exists():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    def open_bundle_for_job(self, job_id: str) -> None:
        if not self.project:
            return
        ref = next((r for r in self.project.results if r.job_id == job_id), None)
        if ref is None:
            return
        path = Path(ref.result_dir) / "audit_bundle.zip"
        if path.exists():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))
            return
        if not self.project_path:
            return
        try:
            bundle = cmd_export_audit_bundle(str(self.project_path), job_id)
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(bundle)))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Audit Bundle", str(exc))

    # ----- Assistant integration -----
    def _copilot_execute(self, approve_apply: bool, approve_run: bool) -> None:
        if not self.project_path:
            self.status.showMessage("Open a project first", 3000)
            return
        intent = self.copilot_input.text().strip()
        if not intent:
            return
        if approve_run and "run" not in intent.lower():
            intent = f"{intent} run"
        approvals: dict[str, Any] = {"apply_diff": approve_apply, "run_job": approve_run}
        selected_option_index = self.copilot_design_options.currentData()
        if isinstance(selected_option_index, int):
            approvals["selected_option_index"] = selected_option_index
        if approve_apply:
            approvals["selected_diff_ops"] = self._selected_diff_keys()

        res = self.agent_runtime.execute(str(self.project_path), intent, approvals=approvals)
        self.copilot_plan_view.setPlainText(res.plan)
        self._populate_diff_preview(res.diff_preview.get("ops", []))

        lines = [
            f"Diff ops: {res.diff_preview.get('count', 0)}",
            f"Selected diff ops: {len(self._selected_diff_keys())}",
            f"Actions: {[a.kind + ('*' if a.requires_approval else '') for a in res.actions]}",
            f"Artifacts: {res.produced_artifacts}",
            f"Warnings: {res.warnings}",
        ]
        self._populate_design_options(res.run_manifest)
        self.copilot_output.setPlainText("\n".join(lines))

        self._reload_project()

    def copilot_plan_preview(self) -> None:
        self._copilot_execute(approve_apply=False, approve_run=False)

    def copilot_apply_only_action(self) -> None:
        self._copilot_execute(approve_apply=True, approve_run=False)

    def copilot_run_only_action(self) -> None:
        self._copilot_execute(approve_apply=False, approve_run=True)

    def copilot_apply_run_action(self) -> None:
        self._copilot_execute(approve_apply=True, approve_run=True)

    def copilot_design_iterate_action(self) -> None:
        if not self.project_path:
            return
        intent = self.copilot_input.text().strip()
        if "design solve" not in intent.lower():
            intent = f"design solve {intent}".strip()
            self.copilot_input.setText(intent)
        max_iters = int(self.copilot_design_max_iters.value())
        for _ in range(max_iters):
            approvals: dict[str, Any] = {"apply_diff": True, "run_job": True}
            selected_option_index = self.copilot_design_options.currentData()
            if isinstance(selected_option_index, int):
                approvals["selected_option_index"] = selected_option_index
            res = self.agent_runtime.execute(str(self.project_path), intent, approvals=approvals)
            self._populate_design_options(res.run_manifest)
            self._reload_project()
            if self._latest_result_is_pass():
                break
        self.status.showMessage("Design iteration complete", 3000)

    def copilot_undo_assistant_action(self) -> None:
        if not self.project_path:
            return
        project = load_project_schema(self.project_path)
        if not project.assistant_undo_stack:
            self.status.showMessage("No assistant change to undo", 3000)
            return
        from luxera.project.history import undo as undo_project_history

        if not undo_project_history(project):
            self.status.showMessage("Undo failed", 3000)
            return
        save_project_schema(project, self.project_path)
        self._reload_project()

    def copilot_redo_assistant_action(self) -> None:
        if not self.project_path:
            return
        project = load_project_schema(self.project_path)
        if not project.assistant_redo_stack:
            self.status.showMessage("No assistant change to redo", 3000)
            return
        from luxera.project.history import redo as redo_project_history

        if not redo_project_history(project):
            self.status.showMessage("Redo failed", 3000)
            return
        save_project_schema(project, self.project_path)
        self._reload_project()

    def _populate_diff_preview(self, ops: list[dict[str, Any]]) -> None:
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

    def _selected_diff_keys(self) -> list[str]:
        out: list[str] = []
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

    def _on_diff_item_changed(self, current: QtWidgets.QListWidgetItem | None, previous: QtWidgets.QListWidgetItem | None) -> None:  # noqa: ARG002
        if current is None:
            self.copilot_diff_details.setPlainText("")
            return
        key = current.data(QtCore.Qt.UserRole)
        op = self._copilot_preview_ops.get(str(key), {})
        self.copilot_diff_details.setPlainText(json.dumps(op, indent=2, sort_keys=True))

    def _populate_design_options(self, run_manifest: dict[str, Any]) -> None:
        info = run_manifest.get("design_solve")
        if not isinstance(info, dict):
            return
        options = info.get("options") or []
        self.copilot_design_options.blockSignals(True)
        self.copilot_design_options.clear()
        for i, option in enumerate(options):
            if not isinstance(option, dict):
                continue
            label = (
                f"#{i+1} {int(option.get('rows', 0))}x{int(option.get('cols', 0))}, "
                f"dim {float(option.get('dimming', 1.0)):.2f}, "
                f"Eavg {float(option.get('mean_lux', 0.0)):.1f}"
            )
            self.copilot_design_options.addItem(label, i)
        selected = int(info.get("selected_option_index", 0) or 0)
        if self.copilot_design_options.count() > 0:
            self.copilot_design_options.setCurrentIndex(max(0, min(selected, self.copilot_design_options.count() - 1)))
        self.copilot_design_options.blockSignals(False)

    def _latest_result_is_pass(self) -> bool:
        if not self.project or not self.project.results:
            return False
        summary = self.project.results[-1].summary or {}
        comp = summary.get("compliance")
        if isinstance(comp, str):
            txt = comp.lower()
            return ("pass" in txt) and ("non-compliant" not in txt)
        if isinstance(comp, dict):
            return all(bool(v) for v in comp.values() if isinstance(v, bool)) if comp else False
        return False

    def _refresh_audit_view(self) -> None:
        if not self.project:
            self.copilot_audit.setPlainText("")
            self.copilot_activity_log.setPlainText("")
            self.assistant_panel.card_avg.setText("-")
            self.assistant_panel.card_u0.setText("-")
            self.assistant_panel.card_status.setText("No project")
            return

        events = self.project.agent_history[-10:]
        lines = [json.dumps(e, sort_keys=True) for e in events]
        txt = "\n".join(lines)
        self.copilot_audit.setPlainText(txt)
        self.copilot_activity_log.setPlainText(txt)

        if self.project.results:
            summary = self.project.results[-1].summary or {}
            avg = summary.get("avg_lux", summary.get("avg", "-"))
            u0 = summary.get("u0", summary.get("uniformity", "-"))
            self.assistant_panel.card_avg.setText(str(avg))
            self.assistant_panel.card_u0.setText(str(u0))
            self.assistant_panel.card_status.setText("Ready")
        else:
            self.assistant_panel.card_avg.setText("-")
            self.assistant_panel.card_u0.setText("-")
            self.assistant_panel.card_status.setText("No results")

    def copilot_export_report_action(self) -> None:
        if not self.project or not self.project.results:
            self.status.showMessage("No result to export", 3000)
            return
        self.export_report_for_job(self.project.results[-1].job_id)

    def copilot_export_audit_bundle_action(self) -> None:
        if not self.project or not self.project.results:
            self.status.showMessage("No result to export", 3000)
            return
        self.open_bundle_for_job(self.project.results[-1].job_id)

    def _on_toggle_dark_theme(self, enabled: bool) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        set_theme(app, "dark" if enabled else "light")

    def compare_variants(self, job_id: str, variant_ids: list[str], baseline: str) -> None:
        if not self.project_path:
            return
        try:
            out = cmd_compare_variants(str(self.project_path), job_id, variant_ids, baseline_variant_id=baseline or None)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Compare Variants", str(exc))
            return
        self.variants_panel.output.setPlainText(json.dumps(out, indent=2, sort_keys=True))
        self.log_panel.append(f"Variants compared: job={job_id}, variants={variant_ids}, baseline={baseline}")

    # ----- Workflow actions -----
    def draw_room_polygon(self) -> None:
        if not self.project_path or not self.project:
            return
        room_name, ok = QtWidgets.QInputDialog.getText(self, "Draw Room", "Room name:")
        if not ok or not room_name.strip():
            return
        width, ok = QtWidgets.QInputDialog.getDouble(self, "Draw Room", "Width (m):", 6.0, 1.0, 200.0, 2)
        if not ok:
            return
        length, ok = QtWidgets.QInputDialog.getDouble(self, "Draw Room", "Length (m):", 8.0, 1.0, 200.0, 2)
        if not ok:
            return
        height, ok = QtWidgets.QInputDialog.getDouble(self, "Draw Room", "Height (m):", 3.0, 2.0, 20.0, 2)
        if not ok:
            return
        room_id = f"room_{len(self.project.geometry.rooms) + 1}"
        op_create_room(self.project, room_id=room_id, name=room_name.strip(), width=width, length=length, height=height)
        extrude_room_to_surfaces(self.project, room_id, replace_existing=False)
        save_project_schema(self.project, self.project_path)
        self.log_panel.append(f"Room created: {room_id}")
        self._reload_project()

    def add_luminaire(self) -> None:
        if not self.project_path or not self.project or not self.project.photometry_assets:
            return
        asset_ids = [asset.id for asset in self.project.photometry_assets]
        aid, ok = QtWidgets.QInputDialog.getItem(self, "Add Luminaire", "Photometry asset:", asset_ids, 0, False)
        if not ok:
            return
        room = self.project.geometry.rooms[0] if self.project.geometry.rooms else None
        if room is None:
            QtWidgets.QMessageBox.warning(self, "Add Luminaire", "Create a room first.")
            return
        x = room.origin[0] + room.width / 2.0
        y = room.origin[1] + room.length / 2.0
        z = room.origin[2] + max(room.height - 0.2, 2.5)
        lum_id = f"lum_{len(self.project.luminaires) + 1}"
        payload = LuminaireInstance(
            id=lum_id,
            name=f"Luminaire {len(self.project.luminaires) + 1}",
            photometry_asset_id=aid,
            transform=TransformSpec(position=(x, y, z), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
        diff = ProjectDiff(ops=[DiffOp(op="add", kind="luminaire", id=lum_id, payload=payload)])
        cmd_apply_diff(str(self.project_path), diff)
        self.log_panel.append(f"Luminaire placed: {lum_id}")
        self._reload_project()

    def array_luminaires(self) -> None:
        if not self.project_path or not self.project:
            return
        if not self.project.geometry.rooms:
            QtWidgets.QMessageBox.warning(self, "Array Luminaires", "Create a room first.")
            return
        if not self.project.photometry_assets:
            QtWidgets.QMessageBox.warning(self, "Array Luminaires", "Import at least one photometry asset first.")
            return
        room = self.project.geometry.rooms[0]
        asset_id = self.project.photometry_assets[0].id
        rows, ok = QtWidgets.QInputDialog.getInt(self, "Array Luminaires", "Rows:", 2, 1, 20, 1)
        if not ok:
            return
        cols, ok = QtWidgets.QInputDialog.getInt(self, "Array Luminaires", "Cols:", 2, 1, 20, 1)
        if not ok:
            return
        diff = cmd_place_rect_array(str(self.project_path), room.id, asset_id=asset_id, nx=cols, ny=rows, margins=0.5, mount_height=max(room.height - 0.2, 2.5))
        cmd_apply_diff(str(self.project_path), diff)
        self.log_panel.append(f"Luminaire array updated ({rows}x{cols})")
        self._reload_project()

    def create_workplane_grid(self) -> None:
        if not self.project_path or not self.project:
            return
        if not self.project.geometry.rooms:
            QtWidgets.QMessageBox.warning(self, "Create Grid", "Create a room first.")
            return
        room = self.project.geometry.rooms[0]
        elevation, ok = QtWidgets.QInputDialog.getDouble(self, "Create Grid", "Workplane elevation (m):", 0.8, 0.0, 5.0, 2)
        if not ok:
            return
        spacing, ok = QtWidgets.QInputDialog.getDouble(self, "Create Grid", "Grid spacing (m):", 0.25, 0.05, 5.0, 2)
        if not ok:
            return
        grid = create_calc_grid_from_room(
            self.project,
            grid_id=f"grid_{room.id}_{len(self.project.grids) + 1}",
            name=f"Workplane {room.name}",
            room_id=room.id,
            elevation=elevation,
            spacing=spacing,
            margin=0.0,
        )
        self.project.grids = [g for g in self.project.grids if g.id != grid.id]
        diff = ProjectDiff(ops=[DiffOp(op="add", kind="grid", id=grid.id, payload=grid)])
        cmd_apply_diff(str(self.project_path), diff)
        self.log_panel.append(f"Grid created: {grid.id}")
        self._reload_project()

    def run_primary_job(self) -> None:
        if not self.project or not self.project.jobs:
            self.status.showMessage("No jobs available", 3000)
            return
        self.run_job_by_id(self.project.jobs[0].id)

    def view_latest_overlay(self) -> None:
        if not self.project or not self.project.results:
            self.status.showMessage("No results to view", 3000)
            return
        self.results_view.select_job(self.project.results[-1].job_id)
        self.status.showMessage("Showing latest result overlay", 3000)


def run() -> int:
    app = QtWidgets.QApplication([])
    win = LuxeraWorkspaceWindow()
    win.show()
    return int(app.exec())
