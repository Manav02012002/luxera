from __future__ import annotations

import numpy as np

from luxera.calculation.illuminance import Luminaire
from luxera.core.transform import from_aim_up
from luxera.exterior.area_lighting import ExteriorAreaEngine, ExteriorAreaSpec, PoleSpec
from luxera.exterior.facade_lighting import FacadeLightingEngine, FacadeSpec
from luxera.exterior.standards import EXTERIOR_CLASSES, check_exterior_compliance
from luxera.geometry.core import Vector3
from luxera.geometry.spatial import point_in_polygon
from luxera.photometry.model import Photometry
from luxera.project.schema import PhotometryAsset, Project


def _uniform_photometry(cd: float = 1000.0) -> Photometry:
    c = np.array([0.0, 90.0, 180.0, 270.0], dtype=float)
    g = np.array([0.0, 30.0, 60.0, 90.0, 120.0, 150.0, 180.0], dtype=float)
    table = np.full((c.size, g.size), float(cd), dtype=float)
    return Photometry(
        system="C",
        c_angles_deg=c,
        gamma_angles_deg=g,
        candela=table,
        luminous_flux_lm=12000.0,
        symmetry="NONE",
    )


def test_area_grid_within_polygon() -> None:
    engine = ExteriorAreaEngine()
    area = ExteriorAreaSpec(
        name="Lot",
        boundary_polygon=[(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0)],
        grid_spacing=2.0,
    )
    pts = engine.generate_grid_points(area)
    assert pts.shape[0] > 0
    assert all(point_in_polygon((float(p[0]), float(p[1])), area.boundary_polygon) for p in pts)


def test_pole_luminaire_creation(monkeypatch) -> None:
    engine = ExteriorAreaEngine()
    project = Project(name="ext", root_dir=".")
    project.photometry_assets.append(PhotometryAsset(id="asset-1", format="IES", path="unused.ies"))

    monkeypatch.setattr(engine, "_photometry_from_asset", lambda _project, _asset_id: _uniform_photometry())

    poles = [
        PoleSpec(
            id="P1",
            position=(0.0, 0.0, 8.0),
            luminaire_asset_id="asset-1",
            luminaire_count=2,
            arm_length_m=2.0,
            arm_angles_deg=[0.0, 90.0],
        )
    ]

    lums = engine.create_luminaires_from_poles(poles, project)
    assert len(lums) == 2
    a = lums[0].transform.position
    b = lums[1].transform.position
    assert np.isclose(a.x, 2.0) and np.isclose(a.y, 0.0)
    assert np.isclose(b.x, 0.0) and np.isclose(b.y, 2.0)


def test_facade_vertical_grid() -> None:
    engine = FacadeLightingEngine()
    facade = FacadeSpec(
        name="Facade",
        width_m=10.0,
        height_m=5.0,
        position=(0.0, 0.0, 0.0),
        normal=(0.0, -1.0, 0.0),
        grid_spacing=1.0,
    )
    pts = engine.generate_grid_points(facade)
    assert pts.shape[0] == 50


def test_facade_normal_direction() -> None:
    engine = FacadeLightingEngine()
    facade = FacadeSpec(
        name="Facade",
        width_m=10.0,
        height_m=5.0,
        position=(0.0, 0.0, 0.0),
        normal=(0.0, -1.0, 0.0),
        grid_spacing=1.0,
    )

    phot = _uniform_photometry(1500.0)
    lum_pos = Vector3(5.0, -5.0, 2.5)
    aim = Vector3(5.0, 0.0, 2.5) - lum_pos
    tf = from_aim_up(lum_pos, aim=aim, up=Vector3.up())
    lum = Luminaire(photometry=phot, transform=tf)

    res = engine.compute(facade, [lum])
    idx = int(np.argmax(res["values_flat"]))
    p = res["grid_points"][idx]

    assert 4.0 <= float(p[0]) <= 6.0
    assert 2.0 <= float(p[2]) <= 3.0


def test_exterior_compliance_parking() -> None:
    checks = check_exterior_compliance({"E_avg": 10.0, "E_min": 3.0}, "parking_intensive")
    assert checks["E_avg"] is True
    assert checks["E_min"] is True
    assert checks["compliant"] is True


def test_all_classes_defined() -> None:
    assert len(EXTERIOR_CLASSES) >= 10
