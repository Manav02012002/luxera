from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from luxera.project.schema import Project


@dataclass
class Polyline2D:
    points: List[Tuple[float, float]]
    color: str
    width: float
    node_type: str
    object_id: str


@dataclass
class Symbol2D:
    x: float
    y: float
    yaw_deg: float
    size: float
    color: str
    node_type: str
    object_id: str


@dataclass
class Scene2D:
    polylines: List[Polyline2D]
    symbols: List[Symbol2D]


def _close_rect(x0: float, y0: float, w: float, h: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h), (x0, y0)]


def build_scene2d(project: Project, show_grids: bool = True, layers: Dict[str, bool] | None = None) -> Scene2D:
    layers = layers or {}
    polylines: List[Polyline2D] = []
    symbols: List[Symbol2D] = []

    if layers.get("room", True):
        for room in project.geometry.rooms:
            pts = _close_rect(room.origin[0], room.origin[1], room.width, room.length)
            polylines.append(Polyline2D(points=pts, color="#5c6b73", width=1.8, node_type="room", object_id=room.id))

    if layers.get("opening", True):
        for opening in project.geometry.openings:
            if len(opening.vertices) >= 2:
                pts = [(float(v[0]), float(v[1])) for v in opening.vertices]
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
                polylines.append(Polyline2D(points=pts, color="#2f8f83", width=1.4, node_type="opening", object_id=opening.id))

    if layers.get("wall", True):
        for surface in project.geometry.surfaces:
            if surface.kind != "wall" or len(surface.vertices) < 2:
                continue
            pts = [(float(v[0]), float(v[1])) for v in surface.vertices]
            if pts[0] != pts[-1]:
                pts.append(pts[0])
            polylines.append(Polyline2D(points=pts, color="#9aa6b2", width=1.2, node_type="surface", object_id=surface.id))

    if layers.get("luminaire", True):
        for luminaire in project.luminaires:
            pos = luminaire.transform.position
            yaw = (luminaire.transform.rotation.euler_deg or (0.0, 0.0, 0.0))[0]
            symbols.append(
                Symbol2D(
                    x=float(pos[0]),
                    y=float(pos[1]),
                    yaw_deg=float(yaw),
                    size=0.25,
                    color="#f18f01",
                    node_type="luminaire",
                    object_id=luminaire.id,
                )
            )

    if show_grids and layers.get("grid", True):
        for grid in project.grids:
            pts = _close_rect(grid.origin[0], grid.origin[1], grid.width, grid.height)
            polylines.append(Polyline2D(points=pts, color="#8f9aa3", width=0.9, node_type="grid", object_id=grid.id))

    if layers.get("ceiling_grid", True):
        for room in project.geometry.rooms:
            nx = max(2, int(max(room.width, 1.0)))
            ny = max(2, int(max(room.length, 1.0)))
            dx = room.width / max(nx, 1)
            dy = room.length / max(ny, 1)
            for ix in range(1, nx):
                x = room.origin[0] + ix * dx
                polylines.append(
                    Polyline2D(
                        points=[(x, room.origin[1]), (x, room.origin[1] + room.length)],
                        color="#3d5a80",
                        width=0.6,
                        node_type="ceiling_grid",
                        object_id=f"{room.id}_cgx_{ix}",
                    )
                )
            for iy in range(1, ny):
                y = room.origin[1] + iy * dy
                polylines.append(
                    Polyline2D(
                        points=[(room.origin[0], y), (room.origin[0] + room.width, y)],
                        color="#3d5a80",
                        width=0.6,
                        node_type="ceiling_grid",
                        object_id=f"{room.id}_cgy_{iy}",
                    )
                )

    for route in project.escape_routes:
        if len(route.polyline) >= 2:
            pts = [(float(p[0]), float(p[1])) for p in route.polyline]
            polylines.append(Polyline2D(points=pts, color="#d62828", width=1.8, node_type="escape_route", object_id=route.id))

    for roadway in project.roadways:
        pts = [
            (float(roadway.start[0]), float(roadway.start[1])),
            (float(roadway.end[0]), float(roadway.end[1])),
        ]
        polylines.append(Polyline2D(points=pts, color="#3a86ff", width=2.0, node_type="roadway", object_id=roadway.id))

    return Scene2D(polylines=polylines, symbols=symbols)


def scene_bounds(items: Iterable[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in items]
    ys = [p[1] for p in items]
    if not xs or not ys:
        return (0.0, 0.0, 10.0, 10.0)
    return (min(xs), min(ys), max(xs), max(ys))
