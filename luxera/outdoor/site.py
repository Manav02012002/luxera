from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from luxera.project.schema import ObstructionSpec, SurfaceSpec
from luxera.io.mesh_import import import_mesh_file


Point2 = Tuple[float, float]
Point3 = Tuple[float, float, float]


@dataclass(frozen=True)
class GroundPlane:
    polygon_xy: List[Point2]
    elevation_z: float = 0.0
    reflectance: float = 0.2


@dataclass(frozen=True)
class SiteBoundary:
    polygon_xy: List[Point2]


@dataclass(frozen=True)
class RoadwayGeometry:
    centerline: List[Point3]
    lane_width: float
    num_lanes: int
    carriageway_polygon_xy: List[Point2]
    observer_positions: List[Point3] = field(default_factory=list)


def observer_spacing_for_standard(standard: str, road_class: Optional[str] = None) -> float:
    s = str(standard).strip().upper()
    rc = str(road_class or "").strip().upper()
    if "EN 13201" in s:
        # Typical engineering defaults used in roadway workflows.
        return 10.0 if rc.startswith("M") else 5.0 if rc.startswith("C") else 10.0
    if "IES RP-8" in s or "RP-8" in s:
        return 10.0
    return 10.0


def make_ground_surface(spec: GroundPlane, *, surface_id: str = "site_ground") -> SurfaceSpec:
    z = float(spec.elevation_z)
    verts = [(float(x), float(y), z) for x, y in spec.polygon_xy]
    return SurfaceSpec(
        id=surface_id,
        name="Ground Plane",
        kind="custom",
        vertices=verts,
        material_id=None,
        tags=["outdoor", "ground"],
        layer="SITE_GROUND",
        two_sided=False,
    )


def make_site_obstruction(
    *,
    obstruction_id: str,
    footprint_xy: Sequence[Point2],
    height: float,
    kind: str = "custom",
) -> ObstructionSpec:
    verts = [(float(x), float(y), 0.0) for x, y in footprint_xy]
    return ObstructionSpec(id=obstruction_id, name=obstruction_id, kind=kind, vertices=verts, height=float(height))


def roadway_edges_from_centerline(centerline: Sequence[Point3], lane_width: float, num_lanes: int) -> Tuple[List[Point3], List[Point3]]:
    if len(centerline) < 2:
        return ([], [])
    half = 0.5 * float(lane_width) * float(num_lanes)
    left: List[Point3] = []
    right: List[Point3] = []
    for i, p in enumerate(centerline):
        if i == len(centerline) - 1:
            q = centerline[i - 1]
            dx, dy = p[0] - q[0], p[1] - q[1]
        else:
            q = centerline[i + 1]
            dx, dy = q[0] - p[0], q[1] - p[1]
        ln = (dx * dx + dy * dy) ** 0.5
        if ln <= 1e-12:
            nx, ny = 0.0, 1.0
        else:
            nx, ny = -dy / ln, dx / ln
        left.append((float(p[0] + nx * half), float(p[1] + ny * half), float(p[2])))
        right.append((float(p[0] - nx * half), float(p[1] - ny * half), float(p[2])))
    return left, right


def carriageway_polygon_from_edges(left: Sequence[Point3], right: Sequence[Point3]) -> List[Point2]:
    poly = [(float(p[0]), float(p[1])) for p in left] + [(float(p[0]), float(p[1])) for p in reversed(right)]
    return poly


def roadway_observer_positions(
    centerline: Sequence[Point3],
    *,
    spacing_m: float = 10.0,
    eye_height_m: float = 1.5,
    standard: Optional[str] = None,
    road_class: Optional[str] = None,
) -> List[Point3]:
    if len(centerline) < 2:
        return []
    if standard:
        spacing_m = observer_spacing_for_standard(standard, road_class=road_class)
    out: List[Point3] = []
    for i in range(len(centerline) - 1):
        a = centerline[i]
        b = centerline[i + 1]
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        L = (dx * dx + dy * dy + dz * dz) ** 0.5
        if L <= 1e-9:
            continue
        n = max(1, int(L // float(spacing_m)))
        for k in range(n + 1):
            t = min(1.0, (k * float(spacing_m)) / L)
            out.append((float(a[0] + dx * t), float(a[1] + dy * t), float(a[2] + dz * t + float(eye_height_m))))
    return out


def luminaire_positions_along_roadway(
    centerline: Sequence[Point3],
    *,
    spacing_m: float,
    lateral_offset_m: float,
    mounting_height_m: float,
) -> List[Point3]:
    if len(centerline) < 2:
        return []
    out: List[Point3] = []
    for i in range(len(centerline) - 1):
        a = centerline[i]
        b = centerline[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = (dx * dx + dy * dy) ** 0.5
        if L <= 1e-9:
            continue
        nx, ny = -dy / L, dx / L
        n = max(1, int(L // float(spacing_m)))
        for k in range(n + 1):
            t = min(1.0, (k * float(spacing_m)) / L)
            x = a[0] + dx * t + nx * float(lateral_offset_m)
            y = a[1] + dy * t + ny * float(lateral_offset_m)
            out.append((float(x), float(y), float(mounting_height_m)))
    return out


def import_terrain_mesh(
    path: str,
    *,
    fmt: Optional[str] = None,
    length_unit: Optional[str] = None,
    scale_to_meters: Optional[float] = None,
    layer: str = "SITE_TERRAIN",
) -> List[SurfaceSpec]:
    mesh = import_mesh_file(path, fmt=fmt, length_unit=length_unit, scale_to_meters=scale_to_meters)
    out: List[SurfaceSpec] = []
    for i, tri in enumerate(mesh.triangles):
        a, b, c = tri
        pts = [mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]]
        out.append(
            SurfaceSpec(
                id=f"terrain_{i+1}",
                name=f"Terrain {i+1}",
                kind="custom",
                vertices=pts,
                layer=layer,
                tags=["outdoor", "terrain"],
                two_sided=True,
            )
        )
    return out
