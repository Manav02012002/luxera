from __future__ import annotations

import numpy as np

from luxera.geometry.lod import build_lod, mesh_bounds
from luxera.geometry.mesh import TriMesh
from luxera.viewer.mesh import mesh_from_trimesh


def test_lod_preserves_mesh_bounds() -> None:
    mesh = TriMesh(
        vertices=[
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (2.0, 2.0, 0.0),
            (0.0, 2.0, 0.0),
            (0.0, 0.0, 2.0),
            (2.0, 0.0, 2.0),
            (2.0, 2.0, 2.0),
            (0.0, 2.0, 2.0),
        ],
        faces=[
            (0, 1, 2), (0, 2, 3),
            (4, 5, 6), (4, 6, 7),
            (0, 1, 5), (0, 5, 4),
            (1, 2, 6), (1, 6, 5),
            (2, 3, 7), (2, 7, 6),
            (3, 0, 4), (3, 4, 7),
        ],
    )
    lod = build_lod(mesh, viewport_ratio=0.25)
    mn0, mx0 = mesh_bounds(lod.full)
    mn1, mx1 = mesh_bounds(lod.simplified)
    assert np.allclose(mn0, mn1)
    assert np.allclose(mx0, mx1)
    assert len(lod.simplified.faces) <= len(lod.full.faces)


def test_viewer_hook_uses_lod_mesh() -> None:
    mesh = TriMesh(
        vertices=[(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 2.0, 0.0), (0.0, 2.0, 0.0)],
        faces=[(0, 1, 2), (0, 2, 3)],
    )
    full = mesh_from_trimesh(mesh, use_lod=False)
    lod = mesh_from_trimesh(mesh, use_lod=True, lod_ratio=0.5)
    assert lod.indices.shape[0] <= full.indices.shape[0]
