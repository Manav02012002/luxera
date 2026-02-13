from __future__ import annotations

import numpy as np

from luxera.geometry.views.cutplane import ElevationView, PlanView, SectionView, view_basis


def _is_orthonormal(u: np.ndarray, v: np.ndarray, n: np.ndarray) -> bool:
    return (
        abs(float(np.dot(u, v))) < 1e-9
        and abs(float(np.dot(u, n))) < 1e-9
        and abs(float(np.dot(v, n))) < 1e-9
        and abs(float(np.linalg.norm(u)) - 1.0) < 1e-9
        and abs(float(np.linalg.norm(v)) - 1.0) < 1e-9
        and abs(float(np.linalg.norm(n)) - 1.0) < 1e-9
    )


def test_plan_view_basis_is_stable_world_xy() -> None:
    origin, u, v, n = view_basis(PlanView(cut_z=1.25, range_zmin=0.0, range_zmax=3.0))
    assert tuple(origin.tolist()) == (0.0, 0.0, 1.25)
    assert tuple(u.tolist()) == (1.0, 0.0, 0.0)
    assert tuple(v.tolist()) == (0.0, 1.0, 0.0)
    assert tuple(n.tolist()) == (0.0, 0.0, 1.0)


def test_section_view_basis_is_orthonormal_and_deterministic() -> None:
    view = SectionView(plane_origin=(2.0, 3.0, 1.0), plane_normal=(1.0, 1.0, 0.0), thickness=0.2)
    o1, u1, v1, n1 = view_basis(view)
    o2, u2, v2, n2 = view_basis(view)
    assert tuple(o1.tolist()) == tuple(o2.tolist())
    assert tuple(u1.tolist()) == tuple(u2.tolist())
    assert tuple(v1.tolist()) == tuple(v2.tolist())
    assert tuple(n1.tolist()) == tuple(n2.tolist())
    assert _is_orthonormal(u1, v1, n1)


def test_elevation_view_basis_is_orthonormal() -> None:
    _o, u, v, n = view_basis(ElevationView(plane_origin=(0.0, 0.0, 0.0), plane_normal=(0.0, -1.0, 0.0)))
    assert _is_orthonormal(u, v, n)
