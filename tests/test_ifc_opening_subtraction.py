from __future__ import annotations

from luxera.io.ifc_import import _apply_opening_subtractions
from luxera.project.schema import OpeningSpec, SurfaceSpec


def test_ifc_opening_subtracts_from_axis_aligned_host_wall() -> None:
    host = SurfaceSpec(
        id="wall_1",
        name="Wall",
        kind="wall",
        vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, 3.0), (0.0, 0.0, 3.0)],
    )
    opening = OpeningSpec(
        id="op_1",
        name="Window",
        opening_type="window",
        kind="window",
        host_surface_id="wall_1",
        vertices=[(1.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 0.0, 2.0), (1.0, 0.0, 2.0)],
    )
    out, warnings = _apply_opening_subtractions([host], [opening])
    assert not warnings
    assert len(out) >= 2
    # Host id remains present for stable host references.
    assert any(s.id == "wall_1" for s in out)


def test_ifc_opening_subtracts_non_rect_host_with_triangulated_hole_mesh() -> None:
    host = SurfaceSpec(
        id="wall_poly",
        name="Wall Poly",
        kind="wall",
        vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 1.5, 0.0), (2.5, 3.0, 0.0), (0.0, 3.0, 0.0)],
    )
    opening = OpeningSpec(
        id="op_hole",
        name="Window",
        opening_type="window",
        kind="window",
        host_surface_id="wall_poly",
        vertices=[(1.5, 1.0, 0.0), (2.5, 1.0, 0.0), (2.5, 2.0, 0.0), (1.5, 2.0, 0.0)],
    )
    out, warnings = _apply_opening_subtractions([host], [opening])
    assert not warnings
    assert any(s.id == "wall_poly" for s in out)
    assert len(out) >= 3
