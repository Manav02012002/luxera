from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from luxera.gui.widgets.viewer3d import CameraState, project_point


def test_project_point_returns_finite_screen_coords() -> None:
    p = project_point((2.0, 3.0, 1.0), (1.0, 1.0, 0.0), 800, 600, CameraState(yaw_deg=-30.0, pitch_deg=25.0, zoom=40.0))
    assert isinstance(p[0], float)
    assert isinstance(p[1], float)
    assert 0.0 <= p[0] <= 800.0
    assert 0.0 <= p[1] <= 600.0
