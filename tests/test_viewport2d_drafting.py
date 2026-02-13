from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from luxera.gui.widgets.viewport2d import DraftingState, apply_drafting_constraints


def test_apply_drafting_constraints_grid_and_orthogonal() -> None:
    state = DraftingState(snap_grid=True, snap_endpoints=False, snap_midpoints=False, orthogonal=True, grid_step_m=0.25)
    out = apply_drafting_constraints((1.0, 1.0), (1.38, 1.14), [], [], state)
    assert out == (1.5, 1.0)


def test_apply_drafting_constraints_anchor_snap() -> None:
    state = DraftingState(snap_grid=False, snap_endpoints=True, snap_midpoints=True, orthogonal=False, grid_step_m=0.25)
    anchors = [(2.0, 2.0), (4.0, 4.0)]
    out = apply_drafting_constraints((0.0, 0.0), (2.04, 2.03), anchors, [], state)
    assert out == (2.0, 2.0)


def test_apply_drafting_constraints_parallel_and_fixed_length() -> None:
    state = DraftingState(
        snap_grid=False,
        snap_endpoints=False,
        snap_midpoints=False,
        orthogonal=False,
        parallel=True,
        fixed_length=True,
        fixed_length_value_m=2.0,
        grid_step_m=0.25,
    )
    segs = [((0.0, 0.0), (1.0, 1.0))]
    out = apply_drafting_constraints((1.0, 1.0), (3.0, 1.0), [], segs, state)
    # Point should lie on 45deg line from origin point with exact length 2m.
    assert abs((out[0] - 1.0) - (out[1] - 1.0)) < 1e-9
    assert abs(((out[0] - 1.0) ** 2 + (out[1] - 1.0) ** 2) ** 0.5 - 2.0) < 1e-9
