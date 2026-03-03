from __future__ import annotations

import numpy as np

from luxera.calculation.illuminance import Luminaire
from luxera.engine.ugr_advanced import AdvancedUGREngine
from luxera.geometry.core import Material, Room, Transform, Vector3
from luxera.photometry.model import Photometry


def _room() -> Room:
    return Room.rectangular(
        name="UGR Room",
        width=4.0,
        length=4.0,
        height=3.0,
        origin=Vector3(0.0, 0.0, 0.0),
        floor_material=Material(name="floor", reflectance=0.2),
        wall_material=Material(name="wall", reflectance=0.5),
        ceiling_material=Material(name="ceiling", reflectance=0.7),
    )


def _photometry(cd: float = 1200.0) -> Photometry:
    c = np.asarray([0.0, 90.0, 180.0, 270.0], dtype=float)
    g = np.asarray([0.0, 30.0, 60.0, 90.0, 120.0, 150.0, 180.0], dtype=float)
    candela = np.full((c.size, g.size), float(cd), dtype=float)
    return Photometry(
        system="C",
        c_angles_deg=c,
        gamma_angles_deg=g,
        candela=candela,
        luminous_flux_lm=4000.0,
        symmetry="NONE",
        luminous_width_m=0.6,
        luminous_length_m=0.6,
    )


def _luminaire(pos: tuple[float, float, float] = (2.0, 2.0, 2.8)) -> Luminaire:
    return Luminaire(photometry=_photometry(), transform=Transform(position=Vector3(*pos)))


def test_guth_index_increases_with_T() -> None:
    eng = AdvancedUGREngine()
    s = 15.0
    p1 = eng._guth_position_index(5.0, s)
    p2 = eng._guth_position_index(20.0, s)
    p3 = eng._guth_position_index(40.0, s)
    assert p1 < p2 < p3


def test_ugr_simple_room() -> None:
    eng = AdvancedUGREngine()
    res = eng.compute(_room(), [_luminaire()], observer_height=1.2, observer_grid_spacing=1.0)
    assert res.ugr_max > 0.0


def test_ugr_decreases_with_shielding() -> None:
    room = _room()
    lum = _luminaire()
    low_shield = AdvancedUGREngine(shielding_angle_deg=0.0).compute(room, [lum], observer_grid_spacing=1.0)
    high_shield = AdvancedUGREngine(shielding_angle_deg=45.0).compute(room, [lum], observer_grid_spacing=1.0)
    assert high_shield.ugr_max <= low_shield.ugr_max


def test_solid_angle_decreases_with_distance() -> None:
    eng = AdvancedUGREngine()
    n = np.array([0.0, 0.0, -1.0], dtype=float)
    omega_near = eng._luminous_solid_angle(np.array([0.0, 0.0, 2.0]), np.array([0.0, 0.0, 3.0]), n, 0.6, 0.6)
    omega_far = eng._luminous_solid_angle(np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 3.0]), n, 0.6, 0.6)
    assert omega_near > omega_far


def test_background_luminance_positive() -> None:
    eng = AdvancedUGREngine()
    Lb = eng._background_luminance(_room(), np.array([2.0, 2.0, 1.2], dtype=float), indirect_E_ceiling=50.0)
    assert Lb > 0.0


def test_observer_grid_coverage() -> None:
    eng = AdvancedUGREngine()
    pts = eng._generate_observer_positions(_room(), observer_height=1.2, spacing=1.0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert len(pts) >= 9
    assert min(xs) < 1.0 and max(xs) > 3.0
    assert min(ys) < 1.0 and max(ys) > 3.0
