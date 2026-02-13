from __future__ import annotations

import pytest

from luxera.project.schema import (
    CalcGrid,
    DaylightSpec,
    JobSpec,
    OpeningSpec,
    Project,
)
from luxera.project.validate import ProjectValidationError, validate_daylight


def _base_project() -> Project:
    p = Project(name="daylight")
    p.geometry.openings.append(
        OpeningSpec(
            id="o1",
            name="window",
            kind="window",
            vertices=[(0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 0.0, 2.0), (0.0, 0.0, 2.0)],
            is_daylight_aperture=True,
            visible_transmittance=0.65,
        )
    )
    p.grids.append(
        CalcGrid(
            id="g1",
            name="g1",
            origin=(0.0, 0.0, 0.0),
            width=2.0,
            height=2.0,
            elevation=0.8,
            nx=3,
            ny=3,
        )
    )
    return p


def test_validate_daylight_df_ok() -> None:
    p = _base_project()
    j = JobSpec(
        id="d1",
        type="daylight",
        backend="df",
        daylight=DaylightSpec(mode="df", external_horizontal_illuminance_lux=10000.0),
        targets=["g1"],
    )
    validate_daylight(p, j)


def test_validate_daylight_requires_aperture() -> None:
    p = _base_project()
    p.geometry.openings.clear()
    j = JobSpec(id="d1", type="daylight", backend="df", daylight=DaylightSpec(mode="df", external_horizontal_illuminance_lux=10000.0), targets=["g1"])
    with pytest.raises(ProjectValidationError):
        validate_daylight(p, j)
