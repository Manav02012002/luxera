from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from luxera.engine.direct_illuminance import build_polygon_workplane_points, build_vertical_plane_points
from luxera.geometry.spatial import point_in_polygon
from luxera.project.io import save_project_schema
from luxera.project.schema import (
    JobSpec,
    LineGridSpec,
    LuminaireInstance,
    PhotometryAsset,
    PolygonWorkplaneSpec,
    Project,
    RoomSpec,
    RotationSpec,
    TransformSpec,
    VerticalPlaneSpec,
)
from luxera.runner import run_job


def _uv_of_point(spec: PolygonWorkplaneSpec, p: np.ndarray) -> tuple[float, float]:
    o = np.asarray(spec.origin, dtype=float)
    u = np.asarray(spec.axis_u, dtype=float)
    v = np.asarray(spec.axis_v, dtype=float)
    u = u / max(float(np.linalg.norm(u)), 1e-12)
    v = v / max(float(np.linalg.norm(v)), 1e-12)
    d = np.asarray(p, dtype=float) - o
    return float(np.dot(d, u)), float(np.dot(d, v))


def test_polygon_sampling_deterministic_and_boundary_masking() -> None:
    spec = PolygonWorkplaneSpec(
        id="pw1",
        name="poly",
        origin=(0.0, 0.0, 0.8),
        axis_u=(1.0, 0.0, 0.0),
        axis_v=(0.0, 1.0, 0.0),
        polygon_uv=[(0.0, 0.0), (3.0, 0.0), (3.0, 3.0), (0.0, 3.0)],
        holes_uv=[[(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)]],
        sample_count=80,
        room_id="r1",
    )
    pts_a, _ = build_polygon_workplane_points(spec, seed=42)
    pts_b, _ = build_polygon_workplane_points(spec, seed=42)
    assert pts_a.shape == pts_b.shape
    assert np.allclose(pts_a, pts_b, rtol=0.0, atol=0.0)

    for p in pts_a:
        uv = _uv_of_point(spec, p)
        assert point_in_polygon(uv, spec.polygon_uv)
        assert not point_in_polygon(uv, spec.holes_uv[0])


def test_route_sampling_symmetric_results(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/photometry/synthetic_basic.ies").resolve()
    p = Project(name="route-sym", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="R", width=4.0, length=4.0, height=3.0, origin=(-2.0, -2.0, 0.0)))
    p.line_grids.append(
        LineGridSpec(
            id="route_1",
            name="Route",
            polyline=[(-1.0, 0.0, 0.8), (1.0, 0.0, 0.8)],
            spacing=0.5,
            room_id="r1",
        )
    )
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(fixture)))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L",
            photometry_asset_id="a1",
            transform=TransformSpec(
                position=(-1.0, 0.0, 2.8),
                rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0)),
            ),
        )
    )
    p.luminaires.append(
        LuminaireInstance(
            id="l2",
            name="L2",
            photometry_asset_id="a1",
            transform=TransformSpec(
                position=(1.0, 0.0, 2.8),
                rotation=RotationSpec(type="euler_zyx", euler_deg=(180.0, 0.0, 0.0)),
            ),
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", backend="cpu", seed=42))

    proj = tmp_path / "route_sym.json"
    save_project_schema(p, proj)
    ref = run_job(proj, "j1")
    _ = json.loads((Path(ref.result_dir) / "result.json").read_text(encoding="utf-8"))
    csv_path = Path(ref.result_dir) / "line_route_1.csv"
    arr = np.loadtxt(csv_path, delimiter=",", skiprows=1, dtype=float)
    points = np.asarray(arr[:, :3], dtype=float)
    values = np.asarray(arr[:, 3], dtype=float)

    # Endpoints must be included and mirrored values should match in symmetric setup.
    assert any(np.allclose(pt, np.array([-1.0, 0.0, 0.8]), atol=1e-9) for pt in points)
    assert any(np.allclose(pt, np.array([1.0, 0.0, 0.8]), atol=1e-9) for pt in points)

    by_x = {round(float(pt[0]), 6): float(v) for pt, v in zip(points, values)}
    assert abs(by_x[-1.0] - by_x[1.0]) <= 1e-5
    assert abs(by_x[-0.5] - by_x[0.5]) <= 1e-5


def test_vertical_plane_offset_shifts_points_along_normal() -> None:
    base = VerticalPlaneSpec(
        id="vp0",
        name="VP0",
        origin=(0.0, 0.0, 0.0),
        width=2.0,
        height=2.0,
        nx=2,
        ny=2,
        azimuth_deg=0.0,
        room_id="r1",
        offset_m=0.0,
    )
    off = VerticalPlaneSpec(
        id="vp1",
        name="VP1",
        origin=(0.0, 0.0, 0.0),
        width=2.0,
        height=2.0,
        nx=2,
        ny=2,
        azimuth_deg=0.0,
        room_id="r1",
        offset_m=0.2,
    )
    p0, n0, _, _ = build_vertical_plane_points(base)
    p1, n1, _, _ = build_vertical_plane_points(off)
    assert np.allclose(np.asarray(n0.to_tuple()), np.asarray(n1.to_tuple()), atol=1e-12)
    shift = p1 - p0
    expected = np.asarray(n0.to_tuple()).reshape(1, 3) * 0.2
    assert np.allclose(shift, expected, atol=1e-9)
