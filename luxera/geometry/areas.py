from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from luxera.project.schema import Project, SurfaceSpec


def _triangle_area(a: Tuple[float, float, float], b: Tuple[float, float, float], c: Tuple[float, float, float]) -> float:
    va = np.array(a, dtype=float)
    vb = np.array(b, dtype=float)
    vc = np.array(c, dtype=float)
    return 0.5 * float(np.linalg.norm(np.cross(vb - va, vc - va)))


def surface_area(surface: SurfaceSpec) -> float:
    verts = [tuple(float(x) for x in v) for v in surface.vertices]
    if len(verts) < 3:
        return 0.0
    # Fan triangulation from first vertex for deterministic repeatable area.
    area = 0.0
    a0 = verts[0]
    for i in range(1, len(verts) - 1):
        area += _triangle_area(a0, verts[i], verts[i + 1])
    return float(area)


def area_by_surface_group(project: Project, surface_ids: Sequence[str]) -> float:
    sid = set(surface_ids)
    return float(sum(surface_area(s) for s in project.geometry.surfaces if s.id in sid))


def area_by_room(project: Project) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for room in project.geometry.rooms:
        total = 0.0
        for s in project.geometry.surfaces:
            if s.room_id == room.id:
                total += surface_area(s)
        out[room.id] = float(total)
    return out


def area_by_kind(project: Project, room_id: Optional[str] = None) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for s in project.geometry.surfaces:
        if room_id is not None and s.room_id != room_id:
            continue
        out[s.kind] = out.get(s.kind, 0.0) + surface_area(s)
    return {k: float(v) for k, v in out.items()}

