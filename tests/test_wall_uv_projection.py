from __future__ import annotations

import numpy as np

from luxera.geometry.openings.project_uv import lift_uv_to_3d, project_points_to_uv, wall_basis
from luxera.project.schema import SurfaceSpec


def test_wall_uv_projection_roundtrip_on_rotated_wall() -> None:
    wall = SurfaceSpec(
        id="w1",
        name="Wall",
        kind="wall",
        vertices=[(0.0, 0.0, 0.0), (2.0, 1.0, 0.0), (2.0, 1.0, 3.0), (0.0, 0.0, 3.0)],
    )
    origin, u, v, n = wall_basis(wall)
    uv = project_points_to_uv(wall.vertices, origin, u, v)
    pts = lift_uv_to_3d(uv, origin, u, v)

    assert abs(float(np.dot(u, v))) < 1e-9
    assert abs(float(np.dot(u, n))) < 1e-9
    assert abs(float(np.dot(v, n))) < 1e-9
    assert abs(float(np.linalg.norm(u)) - 1.0) < 1e-9
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-9
    assert abs(float(np.linalg.norm(n)) - 1.0) < 1e-9
    for a, b in zip(wall.vertices, pts):
        assert abs(a[0] - b[0]) < 1e-9
        assert abs(a[1] - b[1]) < 1e-9
        assert abs(a[2] - b[2]) < 1e-9
