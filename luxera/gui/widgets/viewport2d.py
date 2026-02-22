from __future__ import annotations

import math
import json
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

from luxera.gui.render.scene2d import build_scene2d, scene_bounds
from luxera.project.schema import Project


SCALE = 80.0


@dataclass(frozen=True)
class DraftingState:
    snap_grid: bool = True
    snap_endpoints: bool = True
    snap_midpoints: bool = True
    orthogonal: bool = False
    parallel: bool = False
    fixed_length: bool = False
    fixed_length_value_m: float = 1.0
    grid_step_m: float = 0.25


def apply_drafting_constraints(
    original: tuple[float, float],
    candidate: tuple[float, float],
    anchor_points: list[tuple[float, float]],
    anchor_segments: list[tuple[tuple[float, float], tuple[float, float]]],
    state: DraftingState,
) -> tuple[float, float]:
    x, y = candidate
    if state.orthogonal:
        dx = abs(x - original[0])
        dy = abs(y - original[1])
        if dx >= dy:
            y = original[1]
        else:
            x = original[0]
    if state.parallel and anchor_segments:
        seg = max(anchor_segments, key=lambda s: (s[1][0] - s[0][0]) ** 2 + (s[1][1] - s[0][1]) ** 2)
        vx = seg[1][0] - seg[0][0]
        vy = seg[1][1] - seg[0][1]
        mag = math.hypot(vx, vy)
        if mag > 1e-9:
            ux, uy = vx / mag, vy / mag
            wx, wy = x - original[0], y - original[1]
            proj = wx * ux + wy * uy
            x, y = original[0] + proj * ux, original[1] + proj * uy
    if state.fixed_length:
        vx, vy = x - original[0], y - original[1]
        mag = math.hypot(vx, vy)
        if mag > 1e-9:
            scale = max(state.fixed_length_value_m, 0.0) / mag
            x, y = original[0] + vx * scale, original[1] + vy * scale
        else:
            x = original[0] + max(state.fixed_length_value_m, 0.0)
            y = original[1]
    if state.snap_grid and state.grid_step_m > 0.0:
        x = round(x / state.grid_step_m) * state.grid_step_m
        y = round(y / state.grid_step_m) * state.grid_step_m
    if (state.snap_endpoints or state.snap_midpoints) and anchor_points:
        nearest = min(anchor_points, key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)
        if (nearest[0] - x) ** 2 + (nearest[1] - y) ** 2 <= (0.35 * state.grid_step_m) ** 2:
            x, y = nearest
    return (float(x), float(y))


class _LuminaireItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, object_id: str, x: float, y: float, radius: float) -> None:
        super().__init__(-radius, -radius, radius * 2.0, radius * 2.0)
        self.object_id = object_id
        self.setPos(x, y)
        self.setBrush(QtGui.QBrush(QtGui.QColor("#f18f01")))
        self.setPen(QtGui.QPen(QtGui.QColor("#995700"), 1.0))
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsScenePositionChanges, True)


class _SceneView(QtWidgets.QGraphicsView):
    mouse_released = QtCore.Signal()
    library_asset_dropped = QtCore.Signal(str, float, float)

    def __init__(self, scene: QtWidgets.QGraphicsScene, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setAcceptDrops(True)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        self.mouse_released.emit()

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat("application/x-luxera-library-entry"):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat("application/x-luxera-library-entry"):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # type: ignore[override]
        if not event.mimeData().hasFormat("application/x-luxera-library-entry"):
            super().dropEvent(event)
            return
        data = bytes(event.mimeData().data("application/x-luxera-library-entry")).decode("utf-8", errors="replace")
        pos = event.position().toPoint()
        scene_pos = self.mapToScene(pos)
        self.library_asset_dropped.emit(data, float(scene_pos.x()), float(scene_pos.y()))
        event.acceptProposedAction()


class Viewport2D(QtWidgets.QWidget):
    object_selected = QtCore.Signal(str, str)
    luminaire_moved = QtCore.Signal(str, float, float)
    layer_visibility_changed = QtCore.Signal(str, bool)
    library_asset_dropped = QtCore.Signal(dict, float, float)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QtWidgets.QHBoxLayout()
        self.show_grids = QtWidgets.QCheckBox("Show grids")
        self.show_grids.setChecked(True)
        self.show_grids.toggled.connect(self._rerender)
        controls.addWidget(self.show_grids)
        self.layer_rooms = QtWidgets.QCheckBox("Rooms")
        self.layer_rooms.setChecked(True)
        self.layer_rooms.toggled.connect(lambda v: self._on_layer_toggle("room", v))
        controls.addWidget(self.layer_rooms)
        self.layer_walls = QtWidgets.QCheckBox("Walls")
        self.layer_walls.setChecked(True)
        self.layer_walls.toggled.connect(lambda v: self._on_layer_toggle("wall", v))
        controls.addWidget(self.layer_walls)
        self.layer_ceiling = QtWidgets.QCheckBox("Ceiling Grid")
        self.layer_ceiling.setChecked(True)
        self.layer_ceiling.toggled.connect(lambda v: self._on_layer_toggle("ceiling_grid", v))
        controls.addWidget(self.layer_ceiling)
        self.layer_luminaires = QtWidgets.QCheckBox("Luminaires")
        self.layer_luminaires.setChecked(True)
        self.layer_luminaires.toggled.connect(lambda v: self._on_layer_toggle("luminaire", v))
        controls.addWidget(self.layer_luminaires)
        self.layer_grids = QtWidgets.QCheckBox("Calc grids")
        self.layer_grids.setChecked(True)
        self.layer_grids.toggled.connect(lambda v: self._on_layer_toggle("grid", v))
        controls.addWidget(self.layer_grids)
        self.layer_openings = QtWidgets.QCheckBox("Openings")
        self.layer_openings.setChecked(True)
        self.layer_openings.toggled.connect(lambda v: self._on_layer_toggle("opening", v))
        controls.addWidget(self.layer_openings)

        self.snap_grid = QtWidgets.QCheckBox("Snap grid")
        self.snap_grid.setChecked(True)
        controls.addWidget(self.snap_grid)
        self.snap_endpoint = QtWidgets.QCheckBox("Snap endpoints")
        self.snap_endpoint.setChecked(True)
        controls.addWidget(self.snap_endpoint)
        self.snap_midpoint = QtWidgets.QCheckBox("Snap midpoints")
        self.snap_midpoint.setChecked(True)
        controls.addWidget(self.snap_midpoint)
        self.constraint_orthogonal = QtWidgets.QCheckBox("Orthogonal")
        self.constraint_orthogonal.setChecked(False)
        controls.addWidget(self.constraint_orthogonal)
        self.constraint_parallel = QtWidgets.QCheckBox("Parallel")
        self.constraint_parallel.setChecked(False)
        controls.addWidget(self.constraint_parallel)
        self.constraint_fixed_length = QtWidgets.QCheckBox("Fixed L")
        self.constraint_fixed_length.setChecked(False)
        controls.addWidget(self.constraint_fixed_length)
        self.fixed_length_spin = QtWidgets.QDoubleSpinBox()
        self.fixed_length_spin.setRange(0.05, 100.0)
        self.fixed_length_spin.setSingleStep(0.05)
        self.fixed_length_spin.setValue(1.0)
        self.fixed_length_spin.setDecimals(2)
        self.fixed_length_spin.setSuffix(" m")
        controls.addWidget(self.fixed_length_spin)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.scene = QtWidgets.QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._on_selection)
        self.view = _SceneView(self.scene)
        self.view.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing)
        self.view.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self.view.mouse_released.connect(self._on_mouse_release)
        self.view.library_asset_dropped.connect(self._on_library_asset_drop)
        layout.addWidget(self.view, 1)

        self._project: Project | None = None
        self._lum_items: dict[_LuminaireItem, tuple[float, float]] = {}
        self._draft_anchor_points: list[tuple[float, float]] = []
        self._draft_anchor_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []

    def set_project(self, project: Project | None) -> None:
        self._project = project
        if project is not None and getattr(project, "layers", None):
            by_id = {layer.id: bool(layer.visible) for layer in project.layers}
            self.layer_rooms.setChecked(by_id.get("room", True))
            self.layer_walls.setChecked(by_id.get("wall", True))
            self.layer_ceiling.setChecked(by_id.get("ceiling_grid", True))
            self.layer_luminaires.setChecked(by_id.get("luminaire", True))
            self.layer_grids.setChecked(by_id.get("grid", True))
            self.layer_openings.setChecked(by_id.get("opening", True))
        self._rerender()

    def _to_scene(self, x: float, y: float) -> tuple[float, float]:
        return (x * SCALE, -y * SCALE)

    def _to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return (sx / SCALE, -sy / SCALE)

    def _rerender(self) -> None:
        self.scene.clear()
        self._lum_items.clear()
        self._draft_anchor_points = []
        self._draft_anchor_segments = []
        if self._project is None:
            return
        s2d = build_scene2d(
            self._project,
            show_grids=bool(self.show_grids.isChecked()),
            layers={
                "room": bool(self.layer_rooms.isChecked()),
                "wall": bool(self.layer_walls.isChecked()),
                "ceiling_grid": bool(self.layer_ceiling.isChecked()),
                "opening": bool(self.layer_openings.isChecked()),
                "luminaire": bool(self.layer_luminaires.isChecked()),
                "grid": bool(self.layer_grids.isChecked()),
            },
        )

        points_for_bounds: list[tuple[float, float]] = []

        for polyline in s2d.polylines:
            if len(polyline.points) < 2:
                continue
            pen = QtGui.QPen(QtGui.QColor(polyline.color), polyline.width)
            path = QtGui.QPainterPath()
            x0, y0 = self._to_scene(polyline.points[0][0], polyline.points[0][1])
            path.moveTo(x0, y0)
            points_for_bounds.append((polyline.points[0][0], polyline.points[0][1]))
            for x, y in polyline.points[1:]:
                sx, sy = self._to_scene(x, y)
                path.lineTo(sx, sy)
                points_for_bounds.append((x, y))
            self._ingest_anchor_points(polyline.points)
            item = self.scene.addPath(path, pen)
            item.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
            item.setData(0, polyline.node_type)
            item.setData(1, polyline.object_id)

        for symbol in s2d.symbols:
            sx, sy = self._to_scene(symbol.x, symbol.y)
            radius = max(4.0, symbol.size * SCALE)
            lum = _LuminaireItem(symbol.object_id, sx, sy, radius)
            self.scene.addItem(lum)
            self._lum_items[lum] = (sx, sy)

            yaw_rad = math.radians(symbol.yaw_deg)
            dx = math.cos(yaw_rad) * radius * 1.4
            dy = -math.sin(yaw_rad) * radius * 1.4
            ray = self.scene.addLine(sx, sy, sx + dx, sy + dy, QtGui.QPen(QtGui.QColor("#2b2d42"), 1.3))
            ray.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
            ray.setData(0, "luminaire")
            ray.setData(1, symbol.object_id)
            lum.setData(0, "luminaire")
            lum.setData(1, symbol.object_id)
            points_for_bounds.append((symbol.x, symbol.y))

        if points_for_bounds:
            x0, y0, x1, y1 = scene_bounds(points_for_bounds)
            sx0, sy0 = self._to_scene(x0, y1)
            sx1, sy1 = self._to_scene(x1, y0)
            rect = QtCore.QRectF(min(sx0, sx1), min(sy0, sy1), abs(sx1 - sx0), abs(sy1 - sy0)).adjusted(-50, -50, 50, 50)
            self.view.fitInView(rect, QtCore.Qt.KeepAspectRatio)

    def _on_selection(self) -> None:
        items = self.scene.selectedItems()
        if not items:
            return
        item = items[0]
        node_type = item.data(0)
        obj_id = item.data(1)
        if node_type and obj_id:
            self.object_selected.emit(str(node_type), str(obj_id))

    def _on_mouse_release(self) -> None:
        for item, original in list(self._lum_items.items()):
            if item.pos() == QtCore.QPointF(*original):
                continue
            cand = self._to_world(item.pos().x(), item.pos().y())
            original_world = self._to_world(original[0], original[1])
            snapped = apply_drafting_constraints(
                original_world,
                cand,
                self._draft_anchor_points,
                self._draft_anchor_segments,
                self._drafting_state(),
            )
            wx, wy = snapped
            sx, sy = self._to_scene(wx, wy)
            item.setPos(sx, sy)
            self._lum_items[item] = (item.pos().x(), item.pos().y())
            self.luminaire_moved.emit(item.object_id, float(wx), float(wy))

    def _ingest_anchor_points(self, polyline_points: list[tuple[float, float]]) -> None:
        if not polyline_points:
            return
        if self.snap_endpoint.isChecked():
            self._draft_anchor_points.extend((float(x), float(y)) for x, y in polyline_points)
        if self.snap_midpoint.isChecked() and len(polyline_points) >= 2:
            for p0, p1 in zip(polyline_points[:-1], polyline_points[1:]):
                mx = 0.5 * (float(p0[0]) + float(p1[0]))
                my = 0.5 * (float(p0[1]) + float(p1[1]))
                self._draft_anchor_points.append((mx, my))
        if len(polyline_points) >= 2:
            for p0, p1 in zip(polyline_points[:-1], polyline_points[1:]):
                self._draft_anchor_segments.append(((float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1]))))

    def _drafting_state(self) -> DraftingState:
        return DraftingState(
            snap_grid=bool(self.snap_grid.isChecked()),
            snap_endpoints=bool(self.snap_endpoint.isChecked()),
            snap_midpoints=bool(self.snap_midpoint.isChecked()),
            orthogonal=bool(self.constraint_orthogonal.isChecked()),
            parallel=bool(self.constraint_parallel.isChecked()),
            fixed_length=bool(self.constraint_fixed_length.isChecked()),
            fixed_length_value_m=float(self.fixed_length_spin.value()),
            grid_step_m=0.25,
        )

    def _on_layer_toggle(self, layer_id: str, visible: bool) -> None:
        self.layer_visibility_changed.emit(str(layer_id), bool(visible))
        self._rerender()

    def _on_library_asset_drop(self, payload_json: str, sx: float, sy: float) -> None:
        try:
            payload = json.loads(payload_json)
            if not isinstance(payload, dict):
                return
        except Exception:
            return
        wx, wy = self._to_world(sx, sy)
        self.library_asset_dropped.emit(payload, float(wx), float(wy))
