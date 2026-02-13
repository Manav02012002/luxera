from __future__ import annotations
"""Contract: docs/spec/solver_contracts.md, docs/spec/coordinate_conventions.md."""

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from luxera.calculation.illuminance import (
    CalculationGrid,
    DirectCalcSettings,
    IlluminanceResult,
    Luminaire,
    calculate_direct_illuminance,
    calculate_grid_illuminance,
)
from luxera.geometry.core import Material, Polygon, Room, Surface, Vector3
from luxera.geometry.materials import material_from_spec
from luxera.geometry.bvh import BVHNode, Triangle, build_bvh, refit_bvh, triangulate_surfaces
from luxera.geometry.accel import MeshInstance, TwoLevelBVH, build_two_level_bvh, refit_two_level_bvh
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.canonical import canonical_from_photometry
from luxera.photometry.interp import build_interpolation_lut
from luxera.cache.photometry_cache import load_lut_from_cache, save_lut_to_cache
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt
from luxera.project.schema import ArbitraryPlaneSpec, CalcGrid, LineGridSpec, PointSetSpec, Project, RoomSpec, VerticalPlaneSpec
from luxera.core.units import project_scale_to_meters


@dataclass(frozen=True)
class DirectGridResult:
    points: np.ndarray
    values: np.ndarray
    nx: int
    ny: int
    result: IlluminanceResult


@dataclass(frozen=True)
class OcclusionContext:
    surfaces: List[Surface]
    triangles: List[Triangle]
    bvh: Optional[BVHNode]
    epsilon: float = 1e-6
    two_level: Optional[TwoLevelBVH] = None


_OCCLUSION_CACHE: Dict[Tuple[str, bool], OcclusionContext] = {}


def _static_surface_signature(project: Project, include_room_shell: bool) -> str:
    payload = {
        "include_room_shell": bool(include_room_shell),
        "surfaces": [
            {
                "id": s.id,
                "verts": [[float(v[0]), float(v[1]), float(v[2])] for v in s.vertices],
                "material_id": s.material_id,
                "two_sided": bool(getattr(s, "two_sided", True)),
            }
            for s in project.geometry.surfaces
        ],
        "rooms": (
            [
                {
                    "id": r.id,
                    "origin": [float(r.origin[0]), float(r.origin[1]), float(r.origin[2])],
                    "w": float(r.width),
                    "l": float(r.length),
                    "h": float(r.height),
                }
                for r in project.geometry.rooms
            ]
            if include_room_shell
            else []
        ),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def update_occlusion_instance_transforms(
    ctx: OcclusionContext,
    transforms_by_instance_id: Dict[str, List[List[float]]],
) -> OcclusionContext:
    if ctx.two_level is None:
        return ctx
    two = refit_two_level_bvh(ctx.two_level, transforms_by_instance_id)
    return OcclusionContext(
        surfaces=ctx.surfaces,
        triangles=list(two.triangles_world),
        bvh=two.tlas_world,
        epsilon=ctx.epsilon,
        two_level=two,
    )


@dataclass(frozen=True)
class DirectPointResult:
    points: np.ndarray
    values: np.ndarray


def build_grid_from_spec(grid_spec: CalcGrid, length_scale: float = 1.0) -> CalculationGrid:
    return CalculationGrid(
        origin=Vector3(*(length_scale * float(v) for v in grid_spec.origin)),
        width=length_scale * float(grid_spec.width),
        height=length_scale * float(grid_spec.height),
        elevation=length_scale * float(grid_spec.elevation),
        nx=grid_spec.nx,
        ny=grid_spec.ny,
        normal=Vector3(*grid_spec.normal),
    )


def build_room_from_spec(spec: RoomSpec, length_scale: float = 1.0) -> Room:
    floor_mat = Material(name="floor", reflectance=spec.floor_reflectance)
    wall_mat = Material(name="wall", reflectance=spec.wall_reflectance)
    ceiling_mat = Material(name="ceiling", reflectance=spec.ceiling_reflectance)
    origin = Vector3(*(length_scale * float(v) for v in spec.origin))
    return Room.rectangular(
        name=spec.name,
        width=length_scale * float(spec.width),
        length=length_scale * float(spec.length),
        height=length_scale * float(spec.height),
        origin=origin,
        floor_material=floor_mat,
        wall_material=wall_mat,
        ceiling_material=ceiling_mat,
    )


def _resolve_asset_path(project: Project, raw_path: str) -> Path:
    p = Path(raw_path).expanduser()
    if p.is_absolute():
        return p
    if project.root_dir:
        return (Path(project.root_dir).expanduser() / p).resolve()
    return p.resolve()


def load_luminaires(project: Project, hash_asset_fn) -> tuple[List[Luminaire], Dict[str, str]]:
    assets_by_id = {a.id: a for a in project.photometry_assets}
    luminaires: List[Luminaire] = []
    asset_hashes: Dict[str, str] = {}
    length_scale = project_scale_to_meters(project)
    project_root = Path(project.root_dir).expanduser().resolve() if project.root_dir else Path.cwd().resolve()
    for inst in project.luminaires:
        asset = assets_by_id.get(inst.photometry_asset_id)
        if asset is None:
            raise ValueError(f"Missing photometry asset: {inst.photometry_asset_id}")
        asset_path: Optional[Path] = None
        if asset.embedded_b64:
            import base64

            text = base64.b64decode(asset.embedded_b64.encode("utf-8")).decode("utf-8", errors="replace")
        elif asset.path:
            asset_path = _resolve_asset_path(project, asset.path)
            try:
                text = asset_path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                raise ValueError(f"Failed to load photometry asset {asset.id} from {asset_path}: {e}") from e
        else:
            raise ValueError(f"Photometry asset {asset.id} has no data")
        if asset.format == "IES":
            phot = photometry_from_parsed_ies(parse_ies_text(text, source_path=asset_path))
        elif asset.format == "LDT":
            phot = photometry_from_parsed_ldt(parse_ldt_text(text))
        else:
            raise ValueError(f"Unsupported photometry format: {asset.format}")

        # Precompute/load interpolation LUT cache for deterministic runtime acceleration.
        # Cache writes are best-effort and must never fail the calculation pipeline.
        lut = None
        try:
            canonical = canonical_from_photometry(phot, source_format=asset.format)
            cache_root = project_root / ".luxera" / "cache" / "photometry"
            lut = load_lut_from_cache(cache_root, canonical.content_hash)
            if lut is None:
                lut = build_interpolation_lut(canonical)
                save_lut_to_cache(cache_root, lut)
        except Exception:
            lut = None

        tf = inst.transform.to_transform()
        tf.position = tf.position * float(length_scale)
        luminaires.append(
            Luminaire(
                photometry=phot,
                transform=tf,
                flux_multiplier=inst.flux_multiplier,
                tilt_deg=inst.tilt_deg,
                lut=lut,
            )
        )
        asset_hashes[asset.id] = asset.content_hash or hash_asset_fn(asset)
    return luminaires, asset_hashes


def build_direct_occluders(project: Project, include_room_shell: bool = False) -> List[Surface]:
    surfaces: List[Surface] = []
    material_by_id = {m.id: m for m in project.materials}
    length_scale = project_scale_to_meters(project)

    for s in project.geometry.surfaces:
        if len(s.vertices) < 3:
            continue
        verts = [Vector3(*(length_scale * float(x) for x in v)) for v in s.vertices]
        polygon = Polygon(verts)
        m_spec = material_by_id.get(s.material_id) if s.material_id else None
        material = (
            material_from_spec(m_spec, name=f"occluder:{s.id}")
            if m_spec is not None
            else Material(name=f"occluder:{s.id}", reflectance=0.5, specularity=0.0)
        )
        surfaces.append(Surface(id=s.id, polygon=polygon, material=material))
        surfaces[-1].two_sided = bool(getattr(s, "two_sided", True))

    if include_room_shell and project.geometry.rooms:
        room = build_room_from_spec(project.geometry.rooms[0], length_scale=length_scale)
        surfaces.extend(room.get_surfaces())

    return surfaces


def build_direct_occlusion_context(
    project: Project,
    include_room_shell: bool = False,
    occlusion_epsilon: float = 1e-6,
    force_rebuild: bool = False,
    allow_refit: bool = True,
) -> OcclusionContext:
    sig = _static_surface_signature(project, include_room_shell)
    key = (sig, bool(include_room_shell))
    eps = max(float(occlusion_epsilon), 1e-9)
    if not force_rebuild and key in _OCCLUSION_CACHE:
        ctx = _OCCLUSION_CACHE[key]
        if allow_refit:
            if ctx.two_level is not None:
                refit_two_level_bvh(ctx.two_level, {})
                ctx = OcclusionContext(
                    surfaces=ctx.surfaces,
                    triangles=list(ctx.two_level.triangles_world),
                    bvh=ctx.two_level.tlas_world,
                    epsilon=ctx.epsilon,
                    two_level=ctx.two_level,
                )
            elif ctx.bvh is not None:
                refit_bvh(ctx.bvh)
        if abs(ctx.epsilon - eps) <= 1e-12:
            return ctx
        ctx = OcclusionContext(surfaces=ctx.surfaces, triangles=ctx.triangles, bvh=ctx.bvh, epsilon=eps, two_level=ctx.two_level)
        _OCCLUSION_CACHE[key] = ctx
        return ctx
    surfaces = build_direct_occluders(project, include_room_shell=include_room_shell)
    triangles = triangulate_surfaces(surfaces)
    # Build a two-level acceleration structure over instance triangles.
    mesh_id = "scene_occluders"
    identity = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    two = build_two_level_bvh({mesh_id: triangles}, [MeshInstance(instance_id="scene", mesh_id=mesh_id, transform_4x4=identity)])
    t_tri = list(two.triangles_world) if two.triangles_world else triangles
    t_bvh = two.tlas_world if two.tlas_world is not None else (build_bvh(triangles) if triangles else None)
    ctx = OcclusionContext(surfaces=surfaces, triangles=t_tri, bvh=t_bvh, epsilon=eps, two_level=two)
    _OCCLUSION_CACHE[key] = ctx
    return ctx


def _orthonormal_basis(normal: Vector3, up_hint: Optional[Vector3] = None) -> tuple[Vector3, Vector3]:
    n = normal.normalize()
    up = (up_hint or Vector3.up()).normalize()
    if abs(n.dot(up)) > 0.99:
        up = Vector3(1.0, 0.0, 0.0)
    u = up.cross(n).normalize()
    v = n.cross(u).normalize()
    return u, v


def build_vertical_plane_points(spec: VerticalPlaneSpec, length_scale: float = 1.0) -> tuple[np.ndarray, Vector3, int, int]:
    az = math.radians(float(spec.azimuth_deg))
    normal = Vector3(math.cos(az), math.sin(az), 0.0).normalize()
    u, v = _orthonormal_basis(normal, up_hint=Vector3.up())
    origin = Vector3(*(length_scale * float(v) for v in spec.origin))

    nx = max(1, int(spec.nx))
    ny = max(1, int(spec.ny))
    dx = (length_scale * float(spec.width)) / max(nx - 1, 1)
    dy = (length_scale * float(spec.height)) / max(ny - 1, 1)

    pts: List[tuple[float, float, float]] = []
    for j in range(ny):
        for i in range(nx):
            p = origin + (u * (i * dx)) + (v * (j * dy))
            pts.append(p.to_tuple())
    return np.array(pts, dtype=float), normal, nx, ny


def run_direct_points(
    points: np.ndarray,
    surface_normal: Vector3,
    luminaires: List[Luminaire],
    occlusion: Optional[OcclusionContext] = None,
    use_occlusion: bool = False,
    occlusion_epsilon: float = 1e-6,
) -> DirectPointResult:
    n = surface_normal.normalize()
    vals = np.zeros((points.shape[0],), dtype=float)
    eps = max(float(occlusion_epsilon), 1e-9)
    settings = DirectCalcSettings(use_occlusion=bool(use_occlusion), occlusion_epsilon=eps)
    tris = occlusion.triangles if occlusion is not None else None
    bvh = occlusion.bvh if occlusion is not None else None
    for i in range(points.shape[0]):
        p = Vector3(float(points[i, 0]), float(points[i, 1]), float(points[i, 2]))
        total = 0.0
        for lum in luminaires:
            total += calculate_direct_illuminance(
                p,
                n,
                lum,
                occluders=tris,
                settings=settings,
                occluder_bvh=bvh,
            )
        vals[i] = total
    return DirectPointResult(points=points, values=vals)


def run_direct_vertical_plane(
    plane_spec: VerticalPlaneSpec,
    luminaires: List[Luminaire],
    occlusion: Optional[OcclusionContext] = None,
    use_occlusion: bool = False,
    occlusion_epsilon: float = 1e-6,
) -> DirectGridResult:
    points, normal, nx, ny = build_vertical_plane_points(plane_spec)
    pts = run_direct_points(
        points,
        normal,
        luminaires,
        occlusion=occlusion,
        use_occlusion=use_occlusion,
        occlusion_epsilon=occlusion_epsilon,
    )
    values_2d = pts.values.reshape(ny, nx)
    grid = CalculationGrid(
        origin=Vector3(*plane_spec.origin),
        width=plane_spec.width,
        height=plane_spec.height,
        elevation=plane_spec.origin[2],
        nx=nx,
        ny=ny,
        normal=normal,
    )
    return DirectGridResult(
        points=pts.points,
        values=pts.values,
        nx=nx,
        ny=ny,
        result=IlluminanceResult(grid=grid, values=values_2d),
    )


def run_direct_point_set(
    point_set: PointSetSpec,
    luminaires: List[Luminaire],
    occlusion: Optional[OcclusionContext] = None,
    use_occlusion: bool = False,
    occlusion_epsilon: float = 1e-6,
    normal: Vector3 = Vector3.up(),
) -> DirectPointResult:
    points = np.array(point_set.points, dtype=float)
    if points.size == 0:
        points = np.zeros((0, 3), dtype=float)
    return run_direct_points(
        points=points,
        surface_normal=normal,
        luminaires=luminaires,
        occlusion=occlusion,
        use_occlusion=use_occlusion,
        occlusion_epsilon=occlusion_epsilon,
    )


def build_arbitrary_plane_points(spec: ArbitraryPlaneSpec, length_scale: float = 1.0) -> tuple[np.ndarray, Vector3, int, int]:
    origin = Vector3(*(length_scale * float(v) for v in spec.origin))
    u = Vector3(*(float(v) for v in spec.axis_u)).normalize()
    v = Vector3(*(float(v) for v in spec.axis_v)).normalize()
    normal = u.cross(v).normalize()
    nx = max(1, int(spec.nx))
    ny = max(1, int(spec.ny))
    dx = (length_scale * float(spec.width)) / max(nx - 1, 1)
    dy = (length_scale * float(spec.height)) / max(ny - 1, 1)
    pts: List[tuple[float, float, float]] = []
    for j in range(ny):
        for i in range(nx):
            p = origin + (u * (i * dx)) + (v * (j * dy))
            pts.append(p.to_tuple())
    return np.array(pts, dtype=float), normal, nx, ny


def run_direct_arbitrary_plane(
    plane_spec: ArbitraryPlaneSpec,
    luminaires: List[Luminaire],
    occlusion: Optional[OcclusionContext] = None,
    use_occlusion: bool = False,
    occlusion_epsilon: float = 1e-6,
) -> DirectGridResult:
    points, normal, nx, ny = build_arbitrary_plane_points(plane_spec)
    pts = run_direct_points(
        points,
        normal,
        luminaires,
        occlusion=occlusion,
        use_occlusion=use_occlusion,
        occlusion_epsilon=occlusion_epsilon,
    )
    values_2d = pts.values.reshape(ny, nx)
    grid = CalculationGrid(
        origin=Vector3(*plane_spec.origin),
        width=plane_spec.width,
        height=plane_spec.height,
        elevation=plane_spec.origin[2],
        nx=nx,
        ny=ny,
        normal=normal,
    )
    return DirectGridResult(points=pts.points, values=pts.values, nx=nx, ny=ny, result=IlluminanceResult(grid=grid, values=values_2d))


def _sample_polyline(polyline: List[tuple[float, float, float]], spacing: float) -> np.ndarray:
    if len(polyline) < 2:
        return np.zeros((0, 3), dtype=float)
    pts: List[tuple[float, float, float]] = [tuple(float(v) for v in polyline[0])]
    step = max(float(spacing), 1e-6)
    for a, b in zip(polyline[:-1], polyline[1:]):
        va = Vector3(*a)
        vb = Vector3(*b)
        d = vb - va
        L = d.length()
        if L < 1e-12:
            continue
        n = max(1, int(math.floor(L / step)))
        dirn = d / L
        for i in range(1, n + 1):
            t = min(L, i * step)
            p = va + dirn * t
            pts.append(p.to_tuple())
    return np.array(pts, dtype=float)


def run_direct_line_grid(
    line_spec: LineGridSpec,
    luminaires: List[Luminaire],
    occlusion: Optional[OcclusionContext] = None,
    use_occlusion: bool = False,
    occlusion_epsilon: float = 1e-6,
    normal: Vector3 = Vector3.up(),
) -> DirectPointResult:
    points = _sample_polyline(list(line_spec.polyline), line_spec.spacing)
    return run_direct_points(
        points=points,
        surface_normal=normal,
        luminaires=luminaires,
        occlusion=occlusion,
        use_occlusion=use_occlusion,
        occlusion_epsilon=occlusion_epsilon,
    )


def run_direct_grid(
    grid_spec: CalcGrid,
    luminaires: List[Luminaire],
    occluders: Optional[List[Surface]] = None,
    occlusion: Optional[OcclusionContext] = None,
    use_occlusion: bool = False,
    occlusion_epsilon: float = 1e-6,
) -> DirectGridResult:
    grid = build_grid_from_spec(grid_spec)
    if grid_spec.sample_mask and grid_spec.sample_points:
        points_all = np.array([p.to_tuple() for p in grid.get_points()], dtype=float)
        points_in = np.asarray(grid_spec.sample_points, dtype=float)
        pts = run_direct_points(
            points=points_in,
            surface_normal=grid.normal,
            luminaires=luminaires,
            occlusion=occlusion,
            use_occlusion=use_occlusion,
            occlusion_epsilon=occlusion_epsilon,
        )
        vals = np.full((grid.nx * grid.ny,), np.nan, dtype=float)
        tcount = sum(1 for m in grid_spec.sample_mask if m)
        if tcount != pts.values.size:
            raise ValueError("Grid sample mask does not match clipped sample point count")
        src = 0
        for i, keep in enumerate(grid_spec.sample_mask[: grid.nx * grid.ny]):
            if keep:
                vals[i] = float(pts.values[src])
                src += 1
        values_2d = vals.reshape(grid.ny, grid.nx)
        return DirectGridResult(
            points=points_all,
            values=vals,
            nx=grid.nx,
            ny=grid.ny,
            result=IlluminanceResult(grid=grid, values=values_2d),
        )

    settings = DirectCalcSettings(use_occlusion=use_occlusion, occlusion_epsilon=max(float(occlusion_epsilon), 1e-9))
    tri = occlusion.triangles if occlusion is not None else None
    bvh = occlusion.bvh if occlusion is not None else None
    result = calculate_grid_illuminance(
        grid,
        luminaires,
        occluders=occluders,
        settings=settings,
        occluder_triangles=tri,
        occluder_bvh=bvh,
    )
    points = np.array([p.to_tuple() for p in grid.get_points()], dtype=float)
    return DirectGridResult(
        points=points,
        values=result.values.reshape(-1),
        nx=grid.nx,
        ny=grid.ny,
        result=result,
    )
