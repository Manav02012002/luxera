from __future__ import annotations

import numpy as np

from luxera.calculation.illuminance import DirectCalcSettings, Luminaire, calculate_direct_illuminance
from luxera.engine.near_field import AreaSourceSubdivision, LuminousArea, extract_luminous_area_from_photometry, is_near_field
from luxera.geometry.core import Transform, Vector3
from luxera.photometry.model import Photometry


def _make_photometry(
    *,
    luminous_width_m: float | None = 0.6,
    luminous_length_m: float | None = 1.2,
    gamma_angles: list[float] | None = None,
    candela_row: list[float] | None = None,
) -> Photometry:
    g = np.asarray(gamma_angles if gamma_angles is not None else [0.0, 45.0, 90.0], dtype=float)
    row = np.asarray(candela_row if candela_row is not None else [1000.0, 1000.0, 1000.0], dtype=float)
    return Photometry(
        system="C",
        c_angles_deg=np.asarray([0.0], dtype=float),
        gamma_angles_deg=g,
        candela=np.asarray([row], dtype=float),
        luminous_flux_lm=3000.0,
        symmetry="NONE",
        luminous_width_m=luminous_width_m,
        luminous_length_m=luminous_length_m,
    )


def _compute_area_illuminance(
    *,
    phot: Photometry,
    lum_pos: np.ndarray,
    point: np.ndarray,
    subdivisions: int,
) -> float:
    area = extract_luminous_area_from_photometry(phot)
    sub = AreaSourceSubdivision(subdivisions=subdivisions)
    tf = Transform(position=Vector3.from_array(lum_pos))
    srcs = sub.generate_sub_sources(lum_pos, tf, area, total_flux_lumens=float(phot.luminous_flux_lm or 1.0))
    return sub.compute_illuminance_area_source(
        sub_sources=srcs,
        calc_point=point,
        photometry=phot,
        luminaire_transform=tf,
        total_flux=float(phot.luminous_flux_lm or 1.0),
        flux_multiplier=1.0,
        maintenance_factor=1.0,
    )


def test_extract_luminous_area_ies() -> None:
    phot = _make_photometry(luminous_width_m=0.6, luminous_length_m=1.2)
    area = extract_luminous_area_from_photometry(phot)
    assert area.width_m == 0.6
    assert area.length_m == 1.2


def test_extract_luminous_area_missing() -> None:
    phot = _make_photometry(
        luminous_width_m=None,
        luminous_length_m=None,
        gamma_angles=[0.0, 35.0, 70.0, 90.0],
        candela_row=[1000.0, 500.0, 100.0, 0.0],
    )
    area = extract_luminous_area_from_photometry(phot)
    assert 0.3 <= area.width_m <= 0.6
    assert 0.3 <= area.length_m <= 0.6


def test_near_field_detection_close() -> None:
    area = LuminousArea(width_m=1.2, length_m=0.6)
    src = np.array([0.0, 0.0, 3.0])
    pt = np.array([0.0, 0.0, 2.5])
    assert is_near_field(src, pt, area)


def test_near_field_detection_far() -> None:
    area = LuminousArea(width_m=1.2, length_m=0.6)
    src = np.array([0.0, 0.0, 3.0])
    assert is_near_field(src, np.array([0.0, 0.0, 0.0]), area)
    assert not is_near_field(src, np.array([0.0, 0.0, -7.0]), area)


def test_subdivision_count() -> None:
    sub = AreaSourceSubdivision(subdivisions=4)
    area = LuminousArea(width_m=0.6, length_m=1.2)
    srcs = sub.generate_sub_sources(np.array([0.0, 0.0, 3.0]), Transform(), area, total_flux_lumens=3000.0)
    assert len(srcs) == 16


def test_subdivision_positions_symmetric() -> None:
    sub = AreaSourceSubdivision(subdivisions=4)
    area = LuminousArea(width_m=0.6, length_m=1.2)
    srcs = sub.generate_sub_sources(np.array([0.0, 0.0, 3.0]), Transform(), area, total_flux_lumens=3000.0)
    pos = np.array([s["position"] for s in srcs], dtype=float)
    assert np.allclose(np.mean(pos, axis=0), np.array([0.0, 0.0, 3.0]), atol=1e-12)


def test_area_vs_point_close_range() -> None:
    phot = _make_photometry(luminous_width_m=0.6, luminous_length_m=1.2)
    lum = Luminaire(photometry=phot, transform=Transform(position=Vector3(0.0, 0.0, 3.0)))
    point = Vector3(0.0, 0.0, 2.5)
    normal = Vector3(0.0, 0.0, 1.0)

    e_point = calculate_direct_illuminance(point, normal, lum, settings=DirectCalcSettings(near_field_correction=False))
    e_area = calculate_direct_illuminance(point, normal, lum, settings=DirectCalcSettings(near_field_correction=True))

    assert e_area < e_point
    assert abs(e_point - e_area) / max(e_point, 1e-9) > 0.1


def test_area_vs_point_far_range() -> None:
    phot = _make_photometry(luminous_width_m=0.6, luminous_length_m=1.2)
    lum_pos = np.array([0.0, 0.0, 3.0])
    point = np.array([0.0, 0.0, -7.0])
    lum = Luminaire(photometry=phot, transform=Transform(position=Vector3.from_array(lum_pos)))

    e_point = calculate_direct_illuminance(Vector3.from_array(point), Vector3(0.0, 0.0, 1.0), lum)
    e_area = _compute_area_illuminance(phot=phot, lum_pos=lum_pos, point=point, subdivisions=4)

    rel = abs(e_point - e_area) / max(e_point, 1e-9)
    assert rel < 0.02


def test_convergence_with_subdivision() -> None:
    phot = _make_photometry(luminous_width_m=0.6, luminous_length_m=1.2)
    lum_pos = np.array([0.0, 0.0, 3.0])
    point = np.array([0.0, 0.0, 2.5])

    e4 = _compute_area_illuminance(phot=phot, lum_pos=lum_pos, point=point, subdivisions=4)
    e8 = _compute_area_illuminance(phot=phot, lum_pos=lum_pos, point=point, subdivisions=8)
    e16 = _compute_area_illuminance(phot=phot, lum_pos=lum_pos, point=point, subdivisions=16)

    assert abs(e8 - e16) < abs(e4 - e8)
