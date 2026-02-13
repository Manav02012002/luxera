from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from luxera.project.schema import Project


@dataclass(frozen=True)
class CameraState:
    yaw_deg: float = -35.0
    pitch_deg: float = 28.0
    zoom: float = 45.0


def project_point(
    point: tuple[float, float, float],
    center: tuple[float, float, float],
    width_px: int,
    height_px: int,
    camera: CameraState,
) -> tuple[float, float]:
    x = point[0] - center[0]
    y = point[1] - center[1]
    z = point[2] - center[2]

    yaw = math.radians(camera.yaw_deg)
    pitch = math.radians(camera.pitch_deg)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)

    xr = cy * x - sy * y
    yr = sy * x + cy * y
    zr = z

    y2 = cp * yr - sp * zr
    z2 = sp * yr + cp * zr
    scale = max(camera.zoom, 1.0)
    sx = width_px * 0.5 + xr * scale
    sy2 = height_px * 0.5 - (y2 + 0.1 * z2) * scale
    return (float(sx), float(sy2))


class Viewer3D(QtWidgets.QWidget):
    object_selected = QtCore.Signal(str, str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 220)
        self._project: Project | None = None
        self._camera = CameraState()
        self._drag_last: QtCore.QPoint | None = None
        self._center = (0.0, 0.0, 0.0)

    def set_project(self, project: Project | None) -> None:
        self._project = project
        self._center = self._compute_center(project)
        self.update()

    def _compute_center(self, project: Project | None) -> tuple[float, float, float]:
        if project is None or not project.geometry.rooms:
            return (0.0, 0.0, 0.0)
        xs: List[float] = []
        ys: List[float] = []
        zs: List[float] = []
        for room in project.geometry.rooms:
            x0, y0, z0 = room.origin
            xs.extend([x0, x0 + room.width])
            ys.extend([y0, y0 + room.length])
            zs.extend([z0, z0 + room.height])
        return ((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5, (min(zs) + max(zs)) * 0.5)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        self._drag_last = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_last is None:
            super().mouseMoveEvent(event)
            return
        now = event.position().toPoint()
        dx = now.x() - self._drag_last.x()
        dy = now.y() - self._drag_last.y()
        self._drag_last = now
        self._camera = CameraState(
            yaw_deg=self._camera.yaw_deg + dx * 0.6,
            pitch_deg=max(-80.0, min(80.0, self._camera.pitch_deg + dy * 0.5)),
            zoom=self._camera.zoom,
        )
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._drag_last = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 1.0 / 1.1
        self._camera = CameraState(
            yaw_deg=self._camera.yaw_deg,
            pitch_deg=self._camera.pitch_deg,
            zoom=max(10.0, min(240.0, self._camera.zoom * factor)),
        )
        self.update()
        super().wheelEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: ARG002
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QtGui.QColor("#10151d"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#4f5d75"), 1.1))

        if self._project is None:
            painter.setPen(QtGui.QPen(QtGui.QColor("#93a5be"), 1.0))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "No project loaded")
            painter.end()
            return

        self._draw_world_axes(painter)
        self._draw_rooms(painter, self._project.geometry.rooms)
        self._draw_luminaires(painter)
        painter.end()

    def _p(self, pt: tuple[float, float, float]) -> tuple[float, float]:
        return project_point(pt, self._center, self.width(), self.height(), self._camera)

    def _draw_world_axes(self, painter: QtGui.QPainter) -> None:
        origin = (self._center[0], self._center[1], self._center[2])
        axes = [
            ((origin[0], origin[1], origin[2]), (origin[0] + 2.0, origin[1], origin[2]), QtGui.QColor("#ff595e")),
            ((origin[0], origin[1], origin[2]), (origin[0], origin[1] + 2.0, origin[2]), QtGui.QColor("#8ac926")),
            ((origin[0], origin[1], origin[2]), (origin[0], origin[1], origin[2] + 2.0), QtGui.QColor("#1982c4")),
        ]
        for a, b, color in axes:
            painter.setPen(QtGui.QPen(color, 1.6))
            ax, ay = self._p(a)
            bx, by = self._p(b)
            painter.drawLine(QtCore.QPointF(ax, ay), QtCore.QPointF(bx, by))

    def _draw_rooms(self, painter: QtGui.QPainter, rooms: Iterable) -> None:  # noqa: ANN401
        painter.setPen(QtGui.QPen(QtGui.QColor("#cad2e2"), 1.2))
        for room in rooms:
            x0, y0, z0 = room.origin
            x1, y1, z1 = x0 + room.width, y0 + room.length, z0 + room.height
            corners = [
                (x0, y0, z0),
                (x1, y0, z0),
                (x1, y1, z0),
                (x0, y1, z0),
                (x0, y0, z1),
                (x1, y0, z1),
                (x1, y1, z1),
                (x0, y1, z1),
            ]
            edges = [
                (0, 1),
                (1, 2),
                (2, 3),
                (3, 0),
                (4, 5),
                (5, 6),
                (6, 7),
                (7, 4),
                (0, 4),
                (1, 5),
                (2, 6),
                (3, 7),
            ]
            for ia, ib in edges:
                ax, ay = self._p(corners[ia])
                bx, by = self._p(corners[ib])
                painter.drawLine(QtCore.QPointF(ax, ay), QtCore.QPointF(bx, by))

    def _draw_luminaires(self, painter: QtGui.QPainter) -> None:
        if not self._project:
            return
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#f4a261")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#f4a261"), 1.0))
        for lum in self._project.luminaires:
            sx, sy = self._p(lum.transform.position)
            painter.drawEllipse(QtCore.QPointF(sx, sy), 3.5, 3.5)
