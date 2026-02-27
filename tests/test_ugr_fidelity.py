from __future__ import annotations

import pytest

from luxera.calculation.ugr import LuminaireForUGR, UGRObserverPosition, calculate_ugr_at_position
from luxera.engine.ugr_engine import compute_ugr_default, compute_ugr_for_views
from luxera.geometry.core import Material, Room, Transform, Vector3
from luxera.calculation.illuminance import Luminaire
from luxera.photometry.model import Photometry
from luxera.project.schema import GlareViewSpec


def _photometry(intensity: float = 300.0, width: float = 0.6, length: float = 0.6) -> Photometry:
    return Photometry(
        system="C",
        c_angles_deg=[0.0, 90.0, 180.0, 270.0],
        gamma_angles_deg=[0.0, 45.0, 90.0, 180.0],
        candela=[[intensity, intensity * 0.8, intensity * 0.4, 0.0]] * 4,
        luminous_flux_lm=1000.0,
        symmetry="FULL",
        tilt=None,
        luminous_width_m=width,
        luminous_length_m=length,
    )


def _room() -> Room:
    return Room.rectangular(
        name="ugr_ref",
        width=6.0,
        length=8.0,
        height=3.0,
        origin=Vector3(0, 0, 0),
        floor_material=Material(name="floor", reflectance=0.2),
        wall_material=Material(name="wall", reflectance=0.5),
        ceiling_material=Material(name="ceiling", reflectance=0.7),
    )


def test_ugr_monotonicity_higher_intensity_increases_ugr() -> None:
    observer = UGRObserverPosition(eye_position=Vector3(0.0, 0.0, 1.2), view_direction=Vector3(1.0, 0.0, 0.0))
    low = LuminaireForUGR(
        position=Vector3(2.0, 0.0, 2.6),
        luminous_area=0.36,
        luminance=0.0,
        width=0.6,
        length=0.6,
        normal=Vector3(0.0, 0.0, -1.0),
        intensity_cd_fn=lambda _obs: 100.0,
    )
    high = LuminaireForUGR(
        position=Vector3(2.0, 0.0, 2.6),
        luminous_area=0.36,
        luminance=0.0,
        width=0.6,
        length=0.6,
        normal=Vector3(0.0, 0.0, -1.0),
        intensity_cd_fn=lambda _obs: 300.0,
    )
    low_r = calculate_ugr_at_position(observer, [low], background_luminance=20.0)
    high_r = calculate_ugr_at_position(observer, [high], background_luminance=20.0)
    assert high_r.ugr_value >= low_r.ugr_value


def test_ugr_excludes_luminaires_behind_observer() -> None:
    observer = UGRObserverPosition(eye_position=Vector3(0.0, 0.0, 1.2), view_direction=Vector3(1.0, 0.0, 0.0))
    behind = LuminaireForUGR(
        position=Vector3(-2.0, 0.0, 2.6),
        luminous_area=0.36,
        luminance=1000.0,
        width=0.6,
        length=0.6,
        normal=Vector3(0.0, 0.0, -1.0),
        intensity_cd_fn=lambda _obs: 1000.0,
    )
    r = calculate_ugr_at_position(observer, [behind], background_luminance=20.0)
    assert r.ugr_value == pytest.approx(0.0)
    assert r.luminaire_contributions == []


def test_ugr_rotation_invariance_for_rotated_scene() -> None:
    room_a = _room()
    room_b = Room.rectangular(
        name="ugr_ref_rot",
        width=8.0,
        length=6.0,
        height=3.0,
        origin=Vector3(0, 0, 0),
        floor_material=Material(name="floor", reflectance=0.2),
        wall_material=Material(name="wall", reflectance=0.5),
        ceiling_material=Material(name="ceiling", reflectance=0.7),
    )

    phot = _photometry(intensity=260.0)
    lum_a = [Luminaire(photometry=phot, transform=Transform(position=Vector3(3.0, 4.0, 2.8)))]
    lum_b = [Luminaire(photometry=phot, transform=Transform(position=Vector3(4.0, 3.0, 2.8)))]

    view_a = [GlareViewSpec(id="v1", name="A", observer=(1.0, 1.0, 1.2), view_dir=(1.0, 0.0, 0.0))]
    view_b = [GlareViewSpec(id="v1", name="B", observer=(1.0, 1.0, 1.2), view_dir=(0.0, 1.0, 0.0))]

    a = compute_ugr_for_views(room_a, lum_a, view_a)
    b = compute_ugr_for_views(room_b, lum_b, view_b)
    assert a is not None and b is not None
    assert a.worst_case_ugr == pytest.approx(b.worst_case_ugr, rel=1e-6, abs=1e-6)


def test_ugr_debug_top_contributors_payload() -> None:
    room = _room()
    phot = _photometry(intensity=280.0)
    lums = [
        Luminaire(photometry=phot, transform=Transform(position=Vector3(2.5, 4.0, 2.8))),
        Luminaire(photometry=phot, transform=Transform(position=Vector3(3.5, 4.0, 2.8))),
    ]
    views = [GlareViewSpec(id="v1", name="view", observer=(1.0, 1.0, 1.2), view_dir=(1.0, 0.0, 0.0))]
    res = compute_ugr_for_views(room, lums, views, debug_top_n=1)
    assert res is not None
    assert len(res.results) == 1
    tc = res.results[0].top_contributors
    assert len(tc) == 1
    assert "contribution" in tc[0]
    assert "luminaire_id" in tc[0]
    assert "omega" in tc[0]
    assert "luminance_est" in tc[0]
    assert "position_index" in tc[0]


def test_ugr_reference_room_golden_tolerance() -> None:
    room = _room()
    phot = _photometry(intensity=250.0)
    lum = Luminaire(photometry=phot, transform=Transform(position=Vector3(3.0, 4.0, 2.8)))
    analysis = compute_ugr_default(room, [lum], grid_spacing=2.0, eye_heights=[1.2])
    assert analysis is not None
    # Golden reference for this deterministic setup.
    assert analysis.worst_case_ugr == pytest.approx(15.4403415469, abs=0.5)
